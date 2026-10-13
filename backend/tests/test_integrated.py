from datetime import datetime,timedelta,timezone
import secrets
from sqlalchemy import select
from app.database import SessionLocal
from app.config import get_settings
from app.cloud.mock import MockCloudAdapter
from app.services.rules import detect
from app.remediation.mock import execute_action

def test_person1_contracts_and_rds_rule():
    end=datetime.now(timezone.utc)
    provider=MockCloudAdapter()
    rows=provider.collect_snapshots({},end-timedelta(days=14),end)
    costs=provider.collect_daily_costs({},end-timedelta(days=15),end)
    assert len(rows)==4 and all(c.date<end.date() for c in costs)
    assert {r.finding_type for r in detect(rows,costs)}=={'idle_ec2','oversized_rds','cost_anomaly'}

def test_auth_sessions_and_logout(client,monkeypatch):
    from app.auth import ensure_admin
    settings=get_settings()
    password=secrets.token_urlsafe(20)
    monkeypatch.setattr(settings,'auth_enabled',True)
    monkeypatch.setattr(settings,'admin_password',password)
    with SessionLocal() as db:
        ensure_admin(db)
    assert client.get('/api/v1/resources').status_code==401
    assert client.get('/api/v1/health').status_code==200
    assert client.post('/api/v1/auth/login',json={'username':'admin','password':'incorrect'}).status_code==401
    result=client.post('/api/v1/auth/login',json={'username':'admin','password':password})
    assert result.status_code==200
    headers={'Authorization':'Bearer '+result.json()['access_token']}
    assert client.get('/api/v1/resources',headers=headers).status_code==200
    client.post('/api/v1/auth/logout',headers=headers)
    assert client.get('/api/v1/resources',headers=headers).status_code==401

def test_preferences_and_cloud_connection(client):
    response=client.patch('/api/v1/settings',json={'scan_interval_minutes':30,'scheduled_scans':False,'notifications_enabled':False})
    assert response.status_code==200
    assert client.get('/api/v1/settings').json()['scan_interval_minutes']==30
    assert client.post('/api/v1/connections/primary/validate').json()['valid']
    assert 'slack_webhook_url' not in client.get('/api/v1/settings').json()

def test_daily_cost_collection_is_cached(client,monkeypatch):
    import app.services.mock_provider as provider
    calls=[]
    original=provider.collect_daily_costs
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(provider,'collect_daily_costs',counted)
    client.post('/api/v1/scans')
    client.post('/api/v1/scans')
    assert len(calls)==1

def test_notifications_disabled_never_send(client,monkeypatch):
    from app.services.notifications import enqueue,deliver
    from app.models import Notification
    import httpx
    def forbid(*args,**kwargs):
        raise AssertionError('Network must not be called')
    monkeypatch.setattr(httpx,'post',forbid)
    with SessionLocal() as db:
        enqueue(db,'test','Test only')
        db.commit()
    deliver()
    with SessionLocal() as db:
        assert db.scalar(select(Notification)).status=='pending'

def test_aws_metric_missing_and_units():
    from app.cloud.aws import metric
    class CW:
        def get_metric_statistics(self,**kwargs):
            assert kwargs['Period']==3600
            return {'Datapoints':[]}
    end=datetime.now(timezone.utc)
    value=metric(CW(),'AWS/EC2','InstanceId','i-test','CPUUtilization',end-timedelta(days=14),end,'Maximum','Percent','maximum')
    assert value['value'] is None and value['sample_count']==0

def test_live_executor_rejects_untagged(monkeypatch):
    from app.remediation import aws
    class EC2:
        def describe_instances(self,**kwargs):
            return {'Reservations':[{'Instances':[{'Tags':[],'State':{'Name':'running'}}]}]}
        def stop_instances(self,**kwargs):
            raise AssertionError('Must never stop an untagged instance')
    class Session:
        def client(self,*args,**kwargs):
            return EC2()
    monkeypatch.setattr(aws,'session',lambda *args,**kwargs:Session())
    import pytest
    with pytest.raises(ValueError,match='requires'):
        aws.stop_instance({},'i-test')
