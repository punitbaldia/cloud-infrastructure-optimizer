import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock
import pytest
from app.cloud.pricing import EC2Pricing
from app.cloud.mock import MockCloudAdapter
from app.services.rules import detect
from app.remediation.terraform import stop_bundle


def product(rate):
    return json.dumps({'product': {'productFamily': 'Compute Instance'}, 'terms': {'OnDemand': {'term': {
        'priceDimensions': {'rate': {'unit': 'Hrs', 'beginRange': '0', 'endRange': 'Inf', 'pricePerUnit': {'USD': rate}}}}}}})


def instance():
    return {'InstanceType': 't3.micro', 'Placement': {'Tenancy': 'default'}, 'PlatformDetails': 'Linux/UNIX'}


def test_pricing_paginates_and_caches():
    sdk = Mock()
    sdk.client.return_value.get_products.side_effect = [{'PriceList': [], 'NextToken': 'next'}, {'PriceList': [product('0.01')]}]
    pricing = EC2Pricing(sdk)
    result = pricing.quote(instance(), 'ap-south-1')
    assert result['on_demand_hourly_usd'] == '0.01'
    assert pricing.quote(instance(), 'ap-south-1') == result
    assert sdk.client.return_value.get_products.call_count == 2
    args = sdk.client.return_value.get_products.call_args.kwargs
    assert args['NextToken'] == 'next'
    assert {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': 'ap-south-1'} in args['Filters']


@pytest.mark.parametrize('changes', [{'InstanceLifecycle': 'spot'}, {'ProductCodes': ['marketplace']}, {'PlatformDetails': 'Red Hat Enterprise Linux'}, {'Placement': {'Tenancy': 'dedicated'}}])
def test_unsupported_instances_never_get_generic_price(changes):
    sdk = Mock()
    assert EC2Pricing(sdk).quote({**instance(), **changes}, 'ap-south-1')['pricing_status'] == 'unsupported'
    sdk.client.assert_not_called()


def test_ambiguous_and_failed_prices_remain_unavailable():
    from botocore.exceptions import ClientError
    sdk = Mock()
    sdk.client.return_value.get_products.return_value = {'PriceList': [product('0.01'), product('0.02')]}
    assert EC2Pricing(sdk).quote(instance(), 'ap-south-1')['pricing_status'] == 'unavailable'
    sdk.client.return_value.get_products.side_effect = ClientError({'Error': {'Code': 'AccessDenied'}}, 'GetProducts')
    assert EC2Pricing(sdk).quote(instance(), 'ap-south-1')['pricing_status'] == 'unavailable'


def snapshot():
    end = datetime.now(timezone.utc)
    return MockCloudAdapter().collect_snapshots({}, end-timedelta(days=14), end)[0]


def test_live_savings_are_public_rate_estimates():
    resource = snapshot()
    resource.data_source = 'aws'
    resource.configuration.update(pricing_status='available', on_demand_hourly_usd='0.01')
    finding = detect([resource], [])[0]
    assert finding.estimated_monthly_savings == Decimal('7.30')
    assert 'Free Tier' in finding.savings_assumptions[0]


def test_terraform_guardrails_and_demo():
    resource = snapshot()
    assert 'resource' not in stop_bundle(resource, {}, 'demo', True)['files']['demo-stop.tf.json']
    conn = {'account_id': '123456789012', 'region': 'ap-south-1', 'execution_role_arn': 'arn:aws:iam::123456789012:role/Executor'}
    resource.account_id, resource.region = conn['account_id'], conn['region']
    resource.resource_id = 'i-0123456789abcdef0'
    resource.tags = {'optimizer:managed': 'true', 'Environment': 'demo'}
    resource.configuration['root_device_type'] = 'ebs'
    bundle = stop_bundle(resource, conn, 'recommendation')
    doc = bundle['files']['main.tf.json']
    assert doc['provider']['aws']['allowed_account_ids'] == [conn['account_id']]
    assert doc['resource']['aws_ec2_instance_state']['approved_stop']['state'] == 'stopped'
    assert len(doc['resource']['aws_ec2_instance_state']['approved_stop']['lifecycle']['precondition']) == 2
    resource.tags = {}
    with pytest.raises(ValueError, match='tagged'):
        stop_bundle(resource, conn, 'recommendation')


def test_export_requires_approval_and_records_audit(client):
    client.post('/api/v1/scans')
    rec = next(r for r in client.get('/api/v1/recommendations').json()['items'] if r['proposed_action'] == 'stop_ec2')
    path = '/api/v1/recommendations/' + rec['id']
    assert client.post(path + '/terraform').status_code == 409
    client.post(path + '/approve')
    response = client.post(path + '/terraform')
    assert response.status_code == 200 and response.json()['simulated']
    assert any(a['action'] == 'terraform_exported' for a in client.get('/api/v1/audit').json()['items'])


def test_live_stop_waits_for_confirmation(monkeypatch):
    from app.remediation import aws
    ec2 = Mock()
    ec2.describe_instances.return_value = {'Reservations': [{'Instances': [{'State': {'Name': 'running'}, 'RootDeviceType': 'ebs',
        'Tags': [{'Key': 'optimizer:managed', 'Value': 'true'}, {'Key': 'Environment', 'Value': 'demo'}]}]}]}
    ec2.stop_instances.return_value = {'ResponseMetadata': {'RequestId': 'request'}}
    sdk = Mock(); sdk.client.return_value = ec2
    monkeypatch.setattr(aws, 'session', lambda *a, **k: sdk)
    assert 'confirmed' in aws.stop_instance({}, 'i-0123456789abcdef0')['message']
    ec2.get_waiter.assert_called_once_with('instance_stopped')
    ec2.get_waiter.return_value.wait.assert_called_once()


def rds_plan():
    before = {'identifier': 'demo-db', 'instance_class': 'db.t3.large', 'apply_immediately': False,
              'backup_retention_period': 7, 'deletion_protection': True,
              'tags': {'Environment': 'demo', 'optimizer:managed': 'true'}}
    return {'resource_changes': [{'address': 'aws_db_instance.demo', 'type': 'aws_db_instance',
                                 'change': {'actions': ['update'], 'before': before,
                                            'after': {**before, 'instance_class': 'db.t3.medium'}}}]}


def test_rds_review_plan_accepts_only_scoped_class_update():
    from app.remediation.rds_plan import validate_rds_plan
    summary = validate_rds_plan(rds_plan(), 'aws_db_instance.demo', 'demo-db', 'db.t3.medium')
    assert summary['from_class'] == 'db.t3.large'


@pytest.mark.parametrize('field,value', [('allocated_storage', 99), ('apply_immediately', True),
                                        ('deletion_protection', False), ('identifier', 'production-db')])
def test_rds_plan_rejects_unrelated_or_unsafe_changes(field, value):
    from app.remediation.rds_plan import validate_rds_plan
    plan = rds_plan()
    plan['resource_changes'][0]['change']['after'][field] = value
    with pytest.raises(ValueError):
        validate_rds_plan(plan, 'aws_db_instance.demo', 'demo-db', 'db.t3.medium')


def test_rds_plan_rejects_replacement_and_extra_resources():
    from app.remediation.rds_plan import validate_rds_plan
    plan = rds_plan()
    plan['resource_changes'][0]['change']['actions'] = ['delete', 'create']
    with pytest.raises(ValueError):
        validate_rds_plan(plan, 'aws_db_instance.demo', 'demo-db', 'db.t3.medium')
    plan = rds_plan()
    plan['resource_changes'] *= 2
    with pytest.raises(ValueError):
        validate_rds_plan(plan, 'aws_db_instance.demo', 'demo-db', 'db.t3.medium')


def test_rescan_resolves_stopped_instance_without_claiming_realized_savings(client, monkeypatch):
    import app.services.mock_provider as provider
    client.post('/api/v1/scans')
    original = provider.collect_snapshots
    def stopped(*args):
        rows = original(*args)
        for row in rows:
            if row.resource_type == 'ec2':
                row.configuration['state'] = 'stopped'
        return rows
    monkeypatch.setattr(provider, 'collect_snapshots', stopped)
    client.post('/api/v1/scans')
    idle = [r for r in client.get('/api/v1/recommendations').json()['items'] if r['finding_type'] == 'idle_ec2']
    assert all(r['status'] == 'resolved' for r in idle)
    assert client.get('/api/v1/overview').json()['observed_savings'] is None
