from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from app.models import now
from app.schemas import Recommendation

def idle_candidate(resource):
    if resource.resource_type != 'ec2' or resource.data_quality != 'complete':
        return False
    if resource.configuration.get('state') != 'running':
        return False
    if resource.window_end-resource.window_start < timedelta(days=7):
        return False
    cpu = resource.metrics.get('cpu_percent')
    network = resource.metrics.get('network_bytes_per_hour')
    return bool(cpu and network and cpu.value is not None and network.value is not None
                and cpu.unit == 'Percent' and network.unit == 'Bytes/hour'
                and cpu.aggregation == network.aggregation == 'maximum'
                and cpu.sample_count >= 168 and network.sample_count >= 168
                and 0 <= cpu.value < 5 and 0 <= network.value < 1000000)

def detect(snapshots, costs):
    findings = []
    for r in snapshots:
        if not idle_candidate(r):
            continue
        price = (r.configuration.get('demo_hourly_price_usd') if r.data_source=='mock'
                 else r.configuration.get('on_demand_hourly_usd') if r.configuration.get('pricing_status')=='available' else None)
        savings = (Decimal(price)*Decimal(730)).quantize(Decimal('0.01')) if price is not None else None
        findings.append(Recommendation(
            id=uuid4(), resource_id=r.resource_id, finding_type='idle_ec2',
            title='Review idle EC2 instance',
            explanation='Low maximum CPU and network activity over a sustained observation window.',
            evidence=[f'Maximum CPU: {r.metrics["cpu_percent"].value}%',
                      f'Maximum network: {r.metrics["network_bytes_per_hour"].value} Bytes/hour',
                      f'Observation window: {r.window_start.isoformat()} to {r.window_end.isoformat()}'],
            proposed_action='stop_ec2', risk_level='medium',
            estimated_monthly_savings=savings,
            savings_assumptions=([('Synthetic USD price, not an AWS quote.' if r.data_source=='mock'
                else 'AWS public On-Demand USD rate; not your effective bill. Savings Plans, Reserved Instances, credits and Free Tier can reduce or eliminate savings.'),
                'Assumes 730 stopped compute hours/month. Storage, IP, data transfer and other charges excluded.'] if savings is not None else []),
            created_at=now()))
    for r in snapshots:
        keys = ['cpu_percent', 'freeable_memory_bytes', 'database_connections', 'read_iops', 'write_iops']
        if r.resource_type != 'rds' or r.data_quality != 'complete' or r.configuration.get('state')!='available' or r.window_end-r.window_start < timedelta(days=7):
            continue
        if any(k not in r.metrics or r.metrics[k].value is None or r.metrics[k].sample_count < 168 for k in keys):
            continue
        expected=[('Percent','maximum'),('Bytes','minimum'),('Count','maximum'),('Count/Second','maximum'),('Count/Second','maximum')]
        if any((r.metrics[k].unit,r.metrics[k].aggregation)!=spec for k,spec in zip(keys,expected)):
            continue
        if (r.metrics['cpu_percent'].value < 15 and r.metrics['freeable_memory_bytes'].value > 4_000_000_000
            and r.metrics['database_connections'].value < 10 and r.metrics['read_iops'].value < 10 and r.metrics['write_iops'].value < 10):
            findings.append(Recommendation(id=uuid4(),resource_id=r.resource_id,finding_type='oversized_rds',
                title='Review database capacity',explanation='Low CPU, connections and I/O with substantial available memory suggest a capacity review. Validate workload peaks before resizing.',
                evidence=[f'{key}: {r.metrics[key].value} {r.metrics[key].unit}' for key in keys],
                proposed_action='review_rds',risk_level='high',created_at=now(),
                savings_assumptions=['Advisory only. Target class, memory capacity, workload peaks and pricing require validation.']))
    groups = defaultdict(dict)
    for cost in costs:
        if not cost.estimated:
            groups[(cost.account_id, cost.service, cost.currency, cost.cost_basis)][cost.date] = cost
    for (account, service, currency, basis), series in groups.items():
        target = max(series)
        # Require fourteen consecutive completed baseline days. Never include target in baseline.
        days = [target-timedelta(days=n) for n in range(1,15)]
        if any(day not in series for day in days):
            continue
        baseline = sum((series[day].amount for day in days), Decimal(0))/14
        current = series[target].amount
        if baseline <= 0 or current < baseline*2 or current-baseline < 5:
            continue
        findings.append(Recommendation(
            id=uuid4(), finding_type='cost_anomaly', title=f'Unusual daily cost: {service}',
            explanation='Completed daily spending exceeds twice the previous fourteen-day average.',
            evidence=[f'Account: {account}; service: {service}; cost basis: {basis}',
                      f'{target}: {current} {currency}; baseline: {baseline:.2f} {currency}'],
            proposed_action='investigate_cost', risk_level='high', currency=currency,
            created_at=now()))
    return findings

