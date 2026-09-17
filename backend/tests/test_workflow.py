from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Resource, Scan, RecommendationRow
from app.services.mock_provider import collect_snapshots, collect_daily_costs
from app.services.rules import detect, idle_candidate

def scan(client):
    response=client.post('/api/v1/scans')
    assert response.status_code==202
    result=client.get('/api/v1/scans/'+response.json()['id'])
    assert result.json()['status']=='succeeded', result.text
    return client.get('/api/v1/recommendations').json()['items']

def idle(client):
    return next(r for r in scan(client) if r['finding_type']=='idle_ec2')

def test_full_workflow_and_idempotency(client):
    assert client.get('/api/v1/overview').json()['resource_count']==0
    rec=idle(client)
    assert client.get('/api/v1/resources').json()['total']==4
    assert rec['estimated_monthly_savings']=='14.60'
    path='/api/v1/recommendations/'+rec['id']
    key={'idempotency_key':str(uuid4())}
    assert client.post(path+'/execute',json=key).status_code==409
    assert client.post(path+'/approve',json={}).status_code==200
    job=client.post(path+'/execute',json=key)
    assert job.status_code==202, job.text
    result=client.get('/api/v1/executions/'+job.json()['id']).json()
    assert result['status']=='succeeded' and result['simulated'] is True
    assert client.post(path+'/execute',json=key).json()['id']==job.json()['id']
    assert client.post(path+'/execute',json={'idempotency_key':str(uuid4())}).json()['id']==job.json()['id']
    assert client.get('/api/v1/executions').json()['total']==1
    assert client.get('/api/v1/overview').json()['observed_savings'] is None
    assert client.get(path).json()['status']=='approved'
    # Repeated scans don't duplicate resource findings or same-day costs.
    scan(client)
    assert client.get('/api/v1/recommendations').json()['total']==2
    assert len(client.get('/api/v1/overview').json()['daily_costs'])==15

def test_missing_or_insufficient_metrics():
    end=datetime.now(timezone.utc)
    resources=collect_snapshots({},end-timedelta(days=14),end)
    assert idle_candidate(resources[0])
    assert not idle_candidate(resources[-1])
    assert not idle_candidate(resources[1])
    resources[0].metrics['cpu_percent'].value=None
    assert not idle_candidate(resources[0])

def test_anomaly_missing_baseline_and_zero():
    end=datetime.now(timezone.utc)
    costs=collect_daily_costs({},end-timedelta(days=15),end)
    assert len(detect([],costs))==1
    assert detect([],costs[1:])==[]
    for c in costs[:-1]:
        c.amount=Decimal(0)
    assert detect([],costs)==[]

def test_execution_rechecks_tags(client):
    rec=idle(client)
    with SessionLocal() as db:
        row=db.scalar(select(Resource).where(Resource.resource_id==rec['resource_id']))
        row.payload={**row.payload,'tags':{}}
        db.commit()
    path='/api/v1/recommendations/'+rec['id']
    client.post(path+'/approve')
    job=client.post(path+'/execute',json={'idempotency_key':str(uuid4())}).json()
    assert client.get('/api/v1/executions/'+job['id']).json()['status']=='failed'

def test_advisory_and_invalid_requests(client):
    rec=next(r for r in scan(client) if r['finding_type']=='cost_anomaly')
    assert client.post('/api/v1/recommendations/'+rec['id']+'/approve').status_code==409
    response=client.get('/api/v1/recommendations/not-a-uuid')
    assert response.status_code==422 and response.json()['error']['code']=='validation_error'
    assert client.get('/api/v1/resources?limit=0').status_code==422
    assert client.get('/api/v1/recommendations/'+str(uuid4())).status_code==404

def test_stale_recommendation(client):
    rec=idle(client)
    with SessionLocal() as db:
        row=db.get(RecommendationRow,rec['id'])
        row.payload={**row.payload,'created_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}
        db.commit()
    path='/api/v1/recommendations/'+rec['id']
    client.post(path+'/approve')
    job=client.post(path+'/execute',json={'idempotency_key':str(uuid4())}).json()
    assert client.get('/api/v1/executions/'+job['id']).json()['status']=='failed'

def test_active_scan_is_reused(client):
    with SessionLocal() as db:
        row=Scan(active_key='single-account')
        db.add(row)
        db.commit()
        key=row.id
    assert client.post('/api/v1/scans').json()['id']==key

def test_explanation_fallback(client,monkeypatch):
    from app.config import get_settings
    from app.services.explanations import explain
    from app.schemas import Recommendation
    rec=Recommendation.model_validate(idle(client))
    settings=get_settings()
    monkeypatch.setattr(settings,'explanation_mode','claude')
    monkeypatch.setattr(settings,'anthropic_api_key','')
    text,source=explain(rec)
    assert text and source=='rules_fallback'

def test_failed_scan_releases_active_slot(client,monkeypatch):
    import app.services.mock_provider as adapter
    original=adapter.collect_snapshots
    def broken(*args):
        raise RuntimeError('Temporary provider failure')
    monkeypatch.setattr(adapter,'collect_snapshots',broken)
    job=client.post('/api/v1/scans').json()
    assert client.get('/api/v1/scans/'+job['id']).json()['status']=='failed'
    monkeypatch.setattr(adapter,'collect_snapshots',original)
    assert len(scan(client))==2

def test_celery_task_entrypoints(client):
    from app.workers.tasks import scan_task
    with SessionLocal() as db:
        row=Scan(active_key='single-account')
        db.add(row)
        db.commit()
        key=row.id
    # Execute task locally: validates task registration without a Redis server.
    result=scan_task.apply(args=[key],throw=True)
    assert result.successful()
    assert client.get('/api/v1/scans/'+key).json()['status']=='succeeded'

def test_malformed_claude_output_falls_back(client,monkeypatch):
    from app.config import get_settings
    from app.services.explanations import explain
    from app.schemas import Recommendation
    import anthropic
    from types import SimpleNamespace
    rec=Recommendation.model_validate(idle(client))
    settings=get_settings()
    monkeypatch.setattr(settings,'explanation_mode','claude')
    monkeypatch.setattr(settings,'anthropic_api_key','test-only')
    monkeypatch.setattr(settings,'claude_model','test-only')
    fake=SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        content=[SimpleNamespace(type='text',text='not valid JSON')]
    )))
    monkeypatch.setattr(anthropic,'Anthropic',lambda **kwargs:fake)
    assert explain(rec)==(rec.explanation,'rules_fallback')
