import hashlib
import importlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from app.config import get_settings
from app.database import SessionLocal
from app.models import (Scan, Resource, Snapshot, DailyCostRow, RecommendationRow,
                        ExecutionRow, AuditEvent, now)
from app.schemas import ResourceSnapshot, DailyCost
from app.services.rules import detect, idle_candidate
from app.services.explanations import explain

logger = logging.getLogger(__name__)

def provider():
    return importlib.import_module(get_settings().adapter_module)

def claim(session, model, job_id):
    result = session.execute(update(model).where(model.id == job_id, model.status == 'queued').values(status='running'))
    session.commit()
    return result.rowcount == 1

def run_scan(job_id):
    with SessionLocal() as db:
        if not claim(db, Scan, job_id):
            return
        try:
            end = datetime.now(timezone.utc)
            adapter = provider()
            resources = [ResourceSnapshot.model_validate(r) for r in adapter.collect_snapshots({}, end-timedelta(days=14), end)]
            costs = [DailyCost.model_validate(c) for c in adapter.collect_daily_costs({}, end-timedelta(days=15), end)]
            costs = [c for c in costs if c.date < end.date()]
            for resource in resources:
                identity = f'{resource.account_id}:{resource.region}:{resource.resource_id}'
                row = db.scalar(select(Resource).where(Resource.identity == identity))
                payload = resource.model_dump(mode='json')
                if row is None:
                    row = Resource(identity=identity, resource_id=resource.resource_id, payload=payload)
                    db.add(row)
                    db.flush()
                else:
                    row.payload = payload
                db.add(Snapshot(resource_id=row.id, scan_id=job_id, payload=payload))
            for cost in costs:
                row = db.scalar(select(DailyCostRow).where(
                    DailyCostRow.account_id == cost.account_id, DailyCostRow.service == cost.service,
                    DailyCostRow.day == cost.date.isoformat(), DailyCostRow.currency == cost.currency,
                    DailyCostRow.cost_basis == cost.cost_basis))
                if row is None:
                    row = DailyCostRow(account_id=cost.account_id, service=cost.service,
                                       day=cost.date.isoformat(), currency=cost.currency, cost_basis=cost.cost_basis)
                    db.add(row)
                row.payload = cost.model_dump(mode='json')
            for finding in detect(resources, costs):
                # Cost findings fingerprint the target date/evidence; resource findings remain one per resource.
                scope = finding.resource_id or hashlib.sha256('|'.join(finding.evidence).encode()).hexdigest()
                fingerprint = f'{finding.finding_type}:{scope}'
                row = db.scalar(select(RecommendationRow).where(RecommendationRow.fingerprint == fingerprint))
                if row is None:
                    finding.explanation, source = explain(finding)
                    payload = finding.model_dump(mode='json')
                    payload['explanation_source'] = source
                    db.add(RecommendationRow(id=str(finding.id), fingerprint=fingerprint, status='open', payload=payload))
            scan = db.get(Scan, job_id)
            scan.status, scan.active_key, scan.completed_at = 'succeeded', None, now()
            scan.message = f'Collected {len(resources)} mock resources and {len(costs)} daily costs.'
            db.add(AuditEvent(entity_id=job_id, action='scan_succeeded'))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception('Scan failed')
            scan = db.get(Scan, job_id)
            scan.status, scan.active_key, scan.completed_at = 'failed', None, now()
            scan.message = f'Scan failed ({type(exc).__name__}); check backend logs.'
            db.commit()

def run_execution(job_id):
    with SessionLocal() as db:
        if not claim(db, ExecutionRow, job_id):
            return
        try:
            job = db.get(ExecutionRow, job_id)
            rec = db.get(RecommendationRow, job.recommendation_id)
            if rec.status != 'approved' or rec.payload['proposed_action'] != 'stop_ec2':
                raise ValueError('Approval or supported action missing')
            created = datetime.fromisoformat(rec.payload['created_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc)-created > timedelta(hours=get_settings().recommendation_ttl_hours):
                raise ValueError('Recommendation is stale')
            resource = db.scalar(select(Resource).where(Resource.resource_id == rec.payload['resource_id']))
            if resource is None:
                raise ValueError('Resource missing')
            snapshot = ResourceSnapshot.model_validate(resource.payload)
            if not idle_candidate(snapshot) or snapshot.tags.get('optimizer:managed') != 'true':
                raise ValueError('Resource is no longer eligible')
            if datetime.now(timezone.utc)-snapshot.observed_at > timedelta(hours=24):
                raise ValueError('Resource observation is stale')
            # This milestone deliberately uses the local simulator even when collectors are replaced.
            from app.services.mock_provider import execute_action
            result = execute_action({'action': 'stop_ec2', 'resource_id': snapshot.resource_id,
                                     'resource': resource.payload, 'simulated': True})
            job.status, job.message = 'succeeded', result['message']
            job.completed_at = now()
            db.add(AuditEvent(entity_id=job.id, action='simulation_succeeded', details={'simulated': True}))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception('Execution failed')
            job = db.get(ExecutionRow, job_id)
            job.status, job.completed_at = 'failed', now()
            job.message = f'Simulation failed ({type(exc).__name__}); verify eligibility and backend logs.'
            db.add(AuditEvent(entity_id=job.id, action='simulation_failed'))
            db.commit()

