import secrets
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth import ensure_admin, password_hash
from app.config import get_settings
from app.database import SessionLocal
from app.models import AuditEvent, LoginSession, RecommendationRow, User


def admin_login(client, monkeypatch):
    password = secrets.token_urlsafe(20)
    settings = get_settings()
    monkeypatch.setattr(settings, 'auth_enabled', True)
    monkeypatch.setattr(settings, 'admin_username', 'admin')
    monkeypatch.setattr(settings, 'admin_password', password)
    with SessionLocal() as db:
        ensure_admin(db)
    response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': password})
    assert response.status_code == 200
    return password, {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_password_change_revokes_every_session_and_preserves_bootstrap(client, monkeypatch):
    password, first = admin_login(client, monkeypatch)
    second = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': password}).json()
    new_password = secrets.token_urlsafe(22)
    result = client.post('/api/v1/auth/password', headers=first,
                         json={'current_password': password, 'new_password': new_password})
    assert result.status_code == 200
    for headers in [first, {'Authorization': 'Bearer ' + second['access_token']}]:
        assert client.get('/api/v1/auth/me', headers=headers).status_code == 401
    assert client.post('/api/v1/auth/login', json={'username': 'admin', 'password': password}).status_code == 401
    with SessionLocal() as db:
        ensure_admin(db)  # Restart must not reset password from original .env.
        user = db.get(User, 'admin')
        assert user.password_hash == password_hash(new_password, user.salt)
        assert db.scalars(select(LoginSession)).all() == []
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'password_changed'))
        assert event.details == {'sessions_revoked': True}
        assert new_password not in str(event.details) and password not in str(event.details)
    assert client.post('/api/v1/auth/login', json={'username': 'admin', 'password': new_password}).status_code == 200


def test_password_change_rejects_wrong_short_same_and_anonymous(client, monkeypatch):
    password, headers = admin_login(client, monkeypatch)
    new_password = secrets.token_urlsafe(20)
    body = {'current_password': password, 'new_password': new_password}
    assert client.post('/api/v1/auth/password', json=body).status_code == 401
    assert client.post('/api/v1/auth/password', headers=headers,
                       json={**body, 'current_password': 'wrong'}).status_code == 400
    assert client.post('/api/v1/auth/password', headers=headers,
                       json={**body, 'new_password': 'short'}).status_code == 422
    assert client.post('/api/v1/auth/password', headers=headers,
                       json={**body, 'new_password': password}).status_code == 400
    assert client.get('/api/v1/auth/me', headers=headers).status_code == 200


def test_password_change_throttles_repeated_wrong_passwords(client, monkeypatch):
    password, headers = admin_login(client, monkeypatch)
    body = {'current_password': 'incorrect', 'new_password': secrets.token_urlsafe(20)}
    for _ in range(10):
        assert client.post('/api/v1/auth/password', headers=headers, json=body).status_code == 400
    assert client.post('/api/v1/auth/password', headers=headers,
                       json={**body, 'current_password': password}).status_code == 429


@pytest.mark.parametrize('execution_role,monitor_role', [
    ('', ''),
    ('not-a-role', ''),
    ('arn:aws:iam::999999999999:role/Executor', ''),
    ('arn:aws:iam::123456789012:role/Shared', 'arn:aws:iam::123456789012:role/Shared'),
])
def test_bad_execution_roles_rejected_before_sdk_use(monkeypatch, execution_role, monitor_role):
    from app.cloud import aws
    def forbid_sdk(*args, **kwargs):
        pytest.fail('No AWS session may be created for invalid execution configuration')
    monkeypatch.setattr(aws.boto3, 'Session', forbid_sdk)
    with pytest.raises(ValueError):
        aws.session({'account_id': '123456789012', 'region': 'ap-south-1',
                     'role_arn': monitor_role, 'execution_role_arn': execution_role}, execution=True)


def test_valid_execution_role_uses_assume_role_and_checks_identity(monkeypatch):
    from app.cloud import aws
    calls = []
    class STS:
        def assume_role(self, **kwargs):
            calls.append(kwargs)
            return {'Credentials': {'AccessKeyId': 'test', 'SecretAccessKey': 'test', 'SessionToken': 'test'}}
        def get_caller_identity(self):
            return {'Account': '123456789012'}
    class Session:
        def client(self, service, **kwargs):
            assert service == 'sts'
            return STS()
    monkeypatch.setattr(aws.boto3, 'Session', lambda **kwargs: Session())
    connection = {'account_id': '123456789012', 'region': 'ap-south-1',
                  'role_arn': 'arn:aws:iam::123456789012:role/Monitor',
                  'execution_role_arn': 'arn:aws:iam::123456789012:role/Executor', 'external_id': 'test-id'}
    aws.session(connection, execution=True)
    assert calls[0]['RoleArn'] == connection['execution_role_arn']
    assert calls[0]['ExternalId'] == 'test-id'


def test_api_blocks_live_execution_and_preview_without_role(client, monkeypatch):
    client.post('/api/v1/scans')
    with SessionLocal() as db:
        row = next(r for r in db.scalars(select(RecommendationRow)) if r.payload['finding_type'] == 'idle_ec2')
        row.payload = {**row.payload, 'data_source': 'aws'}
        row.status = 'approved'
        rec_id = row.id
        db.commit()
    monkeypatch.setattr(get_settings(), 'live_execution_enabled', True)
    monkeypatch.setattr(get_settings(), 'aws_execution_role_arn', '')
    preview = client.get(f'/api/v1/recommendations/{rec_id}/preview').json()
    assert preview['enabled'] is False
    result = client.post(f'/api/v1/recommendations/{rec_id}/execute', json={'idempotency_key': str(uuid4())})
    assert result.status_code == 409
    assert result.json()['error']['code'] == 'execution_role_required'
    assert client.get('/api/v1/executions').json()['total'] == 0
