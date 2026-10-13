import hashlib
import importlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from app.config import get_settings
from app.database import SessionLocal
from app.models import (Scan, Resource, Snapshot, DailyCostRow, RecommendationRow,
                        ExecutionRow, AuditEvent, Preference, now)
from app.schemas import ResourceSnapshot, DailyCost
from app.services.rules import detect, idle_candidate
from app.services.explanations import explain

logger = logging.getLogger(__name__)

def provider():
    return importlib.import_module('app.cloud.aws' if get_settings().cloud_mode=='aws' else get_settings().adapter_module)

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
            from app.services.preferences import connection
            from app.services.notifications import enqueue, deliver
            mode=get_settings().cloud_mode
            conn=connection()
            account_key=f"{mode}:{conn['account_id']}:{conn['region']}"
            stored_mode=db.get(Preference,'database_mode')
            if stored_mode and stored_mode.payload['mode']!=mode:
                raise ValueError('Use separate databases for demo and live accounts')
            if stored_mode and stored_mode.payload.get('account_key',account_key)!=account_key:
                raise ValueError('Use a separate database for each account and region')
            if not stored_mode:
                db.add(Preference(id='database_mode',payload={'mode':mode,'account_key':account_key}))
            conn=connection()
            resources = [ResourceSnapshot.model_validate(r) for r in adapter.collect_snapshots(conn, end-timedelta(days=14), end)]
            cached=db.get(Preference,'cost_collection')
            if cached and cached.payload.get('date')==end.date().isoformat():
                costs=[DailyCost.model_validate(r.payload) for r in db.scalars(select(DailyCostRow))]
            else:
                costs=[DailyCost.model_validate(c) for c in adapter.collect_daily_costs(conn,end-timedelta(days=15),end)]
                if not cached:
                    cached=Preference(id='cost_collection',payload={})
                    db.add(cached)
                cached.payload={'date':end.date().isoformat()}
            costs = [c for c in costs if c.date < end.date()]
            for resource in resources:
                identity = f'{resource.account_id}:{resource.region}:{resource.resource_id}'
                row = db.scalar(select(Resource).where(Resource.identity == identity))
                resource.data_source=mode
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
            findings = detect(resources, costs)
            current_findings = {(f.finding_type, f.resource_id) for f in findings}
            current_resources = {r.resource_id: r for r in resources}
            for existing in db.scalars(select(RecommendationRow).where(RecommendationRow.status.in_(['open', 'approved']))):
                fresh = current_resources.get(existing.payload.get('resource_id'))
                kind = existing.payload['finding_type']
                # Missing metrics are not proof that waste disappeared. A stopped EC2 is.
                clear = fresh and (fresh.data_quality == 'complete' or
                                  (kind == 'idle_ec2' and fresh.configuration.get('state') == 'stopped'))
                if clear and kind in ('idle_ec2', 'oversized_rds') and (kind, fresh.resource_id) not in current_findings:
                    existing.status = 'resolved'
                    db.add(AuditEvent(entity_id=existing.id, action='finding_no_longer_detected'))
            for finding in findings:
                # Cost findings fingerprint the target date/evidence; resource findings remain one per resource.
                finding.data_source=mode
                scope = finding.resource_id or hashlib.sha256('|'.join(finding.evidence).encode()).hexdigest()
                fingerprint = f'{finding.finding_type}:{scope}'
                row = db.scalar(select(RecommendationRow).where(RecommendationRow.fingerprint == fingerprint))
                if row is None:
                    finding.explanation, source = explain(finding)
                    payload = finding.model_dump(mode='json')
                    payload['explanation_source'] = source
                    db.add(RecommendationRow(id=str(finding.id), fingerprint=fingerprint, status='open', payload=payload))
                    if finding.risk_level=='high':
                        enqueue(db,'finding:'+str(finding.id),f'[{mode.upper()}] {finding.title}: {finding.explanation}')
                elif row.status in ('open','approved') and not db.scalar(select(ExecutionRow).where(ExecutionRow.recommendation_id==row.id)):
                    # A fresh scan must invalidate approval of older evidence.
                    payload=finding.model_dump(mode='json')
                    payload['id']=row.id
                    payload['explanation']=row.payload['explanation']
                    payload['explanation_source']=row.payload.get('explanation_source','mock')
                    row.payload=payload
                    row.status='open'
            scan = db.get(Scan, job_id)
            scan.status, scan.active_key, scan.completed_at = 'succeeded', None, now()
            scan.message = f'Collected {len(resources)} {mode} resources and {len(costs)} daily costs.'
            db.add(AuditEvent(entity_id=job_id, action='scan_succeeded'))
            db.commit()
            deliver()
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
            if rec.payload.get('data_source','mock')=='aws':
                if not get_settings().live_execution_enabled:
                    raise ValueError('Live execution disabled')
                from app.services.preferences import connection
                from app.remediation.policy import execution_role_error
                role_error=execution_role_error(connection())
                if role_error:
                    raise ValueError(role_error)
                from app.cloud.aws import collect_snapshots
                current=next((r for r in collect_snapshots(connection(),datetime.now(timezone.utc)-timedelta(days=14),datetime.now(timezone.utc)) if r.resource_id==snapshot.resource_id),None)
                if current is None or not idle_candidate(current):
                    raise ValueError('Live resource eligibility changed')
                from app.remediation.aws import stop_instance
                result=stop_instance(connection(),snapshot.resource_id)
            else:
                from app.remediation.mock import execute_action
                result = execute_action({'action': 'stop_ec2', 'resource_id': snapshot.resource_id,
                                     'resource': resource.payload, 'simulated': True})
            job.simulated=result['simulated']
            job.status, job.message = 'succeeded', result['message']
            job.completed_at = now()
            if not job.simulated:
                rec.status = 'resolved'
                resource.payload = {**resource.payload, 'configuration': {**resource.payload['configuration'], 'state': 'stopped'}}
            db.add(AuditEvent(entity_id=job.id, action='execution_succeeded', details={'simulated': job.simulated}))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception('Execution failed')
            job = db.get(ExecutionRow, job_id)
            job.status, job.completed_at = 'failed', now()
            job.message = f'Execution not confirmed ({type(exc).__name__}); check AWS state before any manual retry. The action may have been accepted.' if not job.simulated else f'Execution failed ({type(exc).__name__}); verify eligibility and backend logs.'
            db.add(AuditEvent(entity_id=job.id, action='execution_failed'))
            from app.services.notifications import enqueue
            enqueue(db,'execution:'+job.id,job.message)
            db.commit()

