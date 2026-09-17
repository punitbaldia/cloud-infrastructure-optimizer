"""Temporary Person 2 fixture adapter. Person 1's folders are not modified."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.schemas import ResourceSnapshot, DailyCost

def collect_snapshots(connection, start, end):
    result = []
    for rid, kind, cpu, network, quality in [
        ('i-demo-idle', 'ec2', 1.2, 100, 'complete'),
        ('i-demo-active', 'ec2', 62, 500000, 'complete'),
        ('demo-rds', 'rds', 8, 10000, 'partial'),
        ('i-demo-missing', 'ec2', None, None, 'insufficient'),
    ]:
        result.append(ResourceSnapshot(
            resource_id=rid, account_id='000000000000', region='ap-south-1',
            resource_type=kind, observed_at=end, window_start=start, window_end=end,
            configuration={'state': 'running' if kind == 'ec2' else 'available',
                           'instance_type': 'demo.small', 'demo_hourly_price_usd': '0.02'},
            tags={'Name': rid, 'optimizer:managed': 'true'},
            metrics={
                'cpu_percent': {'value': cpu, 'unit': 'Percent', 'aggregation': 'maximum', 'sample_count': 336 if cpu is not None else 0},
                'network_bytes_per_hour': {'value': network, 'unit': 'Bytes/hour', 'aggregation': 'maximum', 'sample_count': 336 if network is not None else 0},
            }, data_quality=quality,
            missing_metrics=['memory_available_bytes'] if kind == 'rds' else (['cpu_percent', 'network_bytes_per_hour'] if cpu is None else [])
        ))
    return result

def collect_daily_costs(connection, start, end):
    today = end.date()
    return [DailyCost(date=today-timedelta(days=offset), account_id='000000000000',
                      service='Amazon EC2', amount=Decimal('18.00') if offset == 1 else Decimal('5.00'),
                      currency='USD', cost_basis='UnblendedCost', estimated=False)
            for offset in range(15, 0, -1)]

def validate_connection(connection):
    return {'valid': True, 'data_source': 'mock'}

def preview_action(action_request):
    return {'simulated': True, 'action': 'stop_ec2', 'resource_id': action_request['resource_id']}

def execute_action(action_request):
    if action_request.get('simulated') is not True or action_request.get('action') != 'stop_ec2':
        raise ValueError('Only simulated EC2 stops are supported')
    resource = action_request['resource']
    if resource['resource_type'] != 'ec2' or resource['tags'].get('optimizer:managed') != 'true':
        raise ValueError('Resource is not an eligible managed EC2 instance')
    if resource['configuration'].get('state') != 'running':
        raise ValueError('Resource is no longer running')
    return {'simulated': True, 'message': 'Simulated EC2 stop succeeded. No AWS action occurred.'}

