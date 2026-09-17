from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.models import Resource, Scan, DailyCostRow, RecommendationRow, ExecutionRow, AuditEvent, now
from app.schemas import Recommendation, ExecutionJob, ExecutionRequest
from app.schemas import Page, ResourceResponse, ScanResponse, OverviewResponse

router = APIRouter(prefix='/api/v1')

def fail(status, code, message):
    raise HTTPException(status_code=status, detail={'code': code, 'message': message, 'details': {}})

def required(db, model, key):
    row = db.get(model, str(key))
    if row is None:
        fail(404, 'not_found', 'The requested record does not exist.')
    return row

def scan_view(r):
    return {k: getattr(r,k) for k in ('id','status','message','created_at','completed_at')} | {'data_source':'mock'}

def execution_view(r):
    return ExecutionJob(**{k:getattr(r,k) for k in ('id','recommendation_id','status','message','created_at','completed_at')}, simulated=True)

def rec_view(r):
    return Recommendation.model_validate({**r.payload,'status':r.status})

def dispatch(kind, job_id, background, db):
    from app.services.jobs import run_scan, run_execution
    if get_settings().job_mode == 'local':
        background.add_task(run_scan if kind == 'scan' else run_execution, job_id)
        return
    try:
        from app.workers.tasks import scan_task, execute_task
        (scan_task if kind == 'scan' else execute_task).delay(job_id)
    except Exception:
        row = db.get(Scan if kind == 'scan' else ExecutionRow, job_id)
        row.status, row.completed_at, row.message = 'failed', now(), 'Queue unavailable; check Redis.'
        if kind == 'scan':
            row.active_key = None
        db.commit()
        fail(503,'queue_unavailable','Job was recorded as failed; Redis could not accept it.')

@router.get('/health', tags=['Health'])
def health():
    return {'status':'ok','service':'cloud-optimizer-backend','data_source':'mock'}

@router.get('/ready', tags=['Health'])
def ready(db:Session=Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
    except Exception:
        fail(503,'database_unavailable','Database is unavailable.')
    return {'status':'ok','job_mode':get_settings().job_mode}

@router.post('/scans',status_code=202,response_model=ScanResponse,tags=['Scans'])
def create_scan(background:BackgroundTasks,db:Session=Depends(get_db)):
    row=Scan(active_key='single-account')
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Scan).where(Scan.active_key=='single-account'))
        if existing:
            return scan_view(existing)
        raise
    view=scan_view(row)
    dispatch('scan',row.id,background,db)
    return view

@router.get('/scans/{scan_id}',response_model=ScanResponse,tags=['Scans'])
def get_scan(scan_id:UUID,db:Session=Depends(get_db)):
    return scan_view(required(db,Scan,scan_id))

@router.get('/resources',response_model=Page[ResourceResponse],tags=['Resources'])
def resources(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),
              resource_type:Literal['ec2','rds']|None=None,db:Session=Depends(get_db)):
    rows=db.scalars(select(Resource).order_by(Resource.id)).all()
    if resource_type:
        rows=[r for r in rows if r.payload['resource_type']==resource_type]
    return {'items':[{'id':r.id,**r.payload,'data_source':'mock'} for r in rows[offset:offset+limit]],
            'total':len(rows),'limit':limit,'offset':offset,'data_source':'mock'}

@router.get('/resources/{resource_id}',response_model=ResourceResponse,tags=['Resources'])
def resource_detail(resource_id:UUID,db:Session=Depends(get_db)):
    r=required(db,Resource,resource_id)
    return {'id':r.id,**r.payload,'data_source':'mock'}

@router.get('/recommendations',response_model=Page[Recommendation],tags=['Recommendations'])
def recommendations(status:Literal['open','approved','dismissed','resolved']|None=None,
                    limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    query=select(RecommendationRow)
    if status:
        query=query.where(RecommendationRow.status==status)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(RecommendationRow.id).offset(offset).limit(limit)).all()
    return {'items':[rec_view(r).model_dump(mode='json') for r in rows],'total':total,
            'limit':limit,'offset':offset,'data_source':'mock'}

@router.get('/recommendations/{recommendation_id}',response_model=Recommendation,tags=['Recommendations'])
def recommendation_detail(recommendation_id:UUID,db:Session=Depends(get_db)):
    return rec_view(required(db,RecommendationRow,recommendation_id))

@router.post('/recommendations/{recommendation_id}/approve',response_model=Recommendation,tags=['Recommendations'])
def approve(recommendation_id:UUID,db:Session=Depends(get_db)):
    row=required(db,RecommendationRow,recommendation_id)
    if row.status not in ('open','approved'):
        fail(409,'invalid_transition','Only open recommendations can be approved.')
    if row.payload['proposed_action']!='stop_ec2':
        fail(409,'advisory_only','This finding has no executable action.')
    if row.status=='open':
        row.status='approved'
        db.add(AuditEvent(entity_id=row.id,action='approved'))
        db.commit()
    return rec_view(row)

@router.post('/recommendations/{recommendation_id}/dismiss',response_model=Recommendation,tags=['Recommendations'])
def dismiss(recommendation_id:UUID,db:Session=Depends(get_db)):
    row=required(db,RecommendationRow,recommendation_id)
    if row.status not in ('open','dismissed'):
        fail(409,'invalid_transition','Only open recommendations can be dismissed.')
    if row.status=='open':
        row.status='dismissed'
        db.add(AuditEvent(entity_id=row.id,action='dismissed'))
        db.commit()
    return rec_view(row)

@router.post('/recommendations/{recommendation_id}/execute',status_code=202,response_model=ExecutionJob,tags=['Executions'])
def execute(recommendation_id:UUID,request:ExecutionRequest,background:BackgroundTasks,db:Session=Depends(get_db)):
    row=required(db,RecommendationRow,recommendation_id)
    previous=db.scalar(select(ExecutionRow).where(ExecutionRow.idempotency_key==str(request.idempotency_key)))
    if previous:
        if previous.recommendation_id!=row.id:
            fail(409,'idempotency_conflict','This key belongs to another recommendation.')
        return execution_view(previous)
    if row.status!='approved':
        fail(409,'approval_required','Approve the recommendation first.')
    if row.payload['proposed_action']!='stop_ec2':
        fail(409,'unsupported_action','Only simulated EC2 stops are supported.')
    previous=db.scalar(select(ExecutionRow).where(ExecutionRow.recommendation_id==row.id))
    if previous:
        return execution_view(previous)
    job=ExecutionRow(recommendation_id=row.id,idempotency_key=str(request.idempotency_key))
    db.add(job)
    try:
        db.flush()
        db.add(AuditEvent(entity_id=job.id,action='simulation_requested'))
        db.commit()
    except IntegrityError:
        db.rollback()
        previous=db.scalar(select(ExecutionRow).where(ExecutionRow.recommendation_id==row.id))
        if previous:
            return execution_view(previous)
        fail(409,'idempotency_conflict','Execution key is already used.')
    view=execution_view(job)
    dispatch('execution',job.id,background,db)
    return view

@router.get('/executions',response_model=Page[ExecutionJob],tags=['Executions'])
def executions(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    rows=db.scalars(select(ExecutionRow).order_by(ExecutionRow.created_at.desc()).offset(offset).limit(limit)).all()
    return {'items':[execution_view(r).model_dump(mode='json') for r in rows],
            'total':db.scalar(select(func.count()).select_from(ExecutionRow)),
            'limit':limit,'offset':offset,'data_source':'mock'}

@router.get('/executions/{execution_id}',response_model=ExecutionJob,tags=['Executions'])
def execution_detail(execution_id:UUID,db:Session=Depends(get_db)):
    return execution_view(required(db,ExecutionRow,execution_id))

@router.get('/overview',response_model=OverviewResponse,tags=['Overview'])
def overview(db:Session=Depends(get_db)):
    daily={}
    month=datetime.now(timezone.utc).strftime('%Y-%m')
    mtd=Decimal(0)
    for r in db.scalars(select(DailyCostRow)).all():
        c=r.payload
        if c['currency']!='USD' or c['cost_basis']!='UnblendedCost':
            continue
        daily[c['date']]=daily.get(c['date'],Decimal(0))+Decimal(c['amount'])
        if c['date'].startswith(month):
            mtd+=Decimal(c['amount'])
    findings=db.scalars(select(RecommendationRow)).all()
    actionable=[r for r in findings if r.status in ('open','approved')]
    savings=sum((Decimal(r.payload['estimated_monthly_savings']) for r in actionable
                 if r.payload['currency']=='USD' and r.payload['estimated_monthly_savings'] is not None),Decimal(0))
    scan=db.scalar(select(Scan).where(Scan.status=='succeeded').order_by(Scan.completed_at.desc()))
    return {'data_source':'mock','currency':'USD','month_to_date_cost':str(mtd),
            'cost_coverage':'Collected dates only; fixtures may not cover the full month.',
            'estimated_monthly_savings':str(savings),'observed_savings':None,
            'resource_count':db.scalar(select(func.count()).select_from(Resource)),
            'open_recommendation_count':len(actionable),
            'critical_finding_count':sum(r.payload['risk_level']=='high' for r in actionable),
            'last_successful_scan_at':scan.completed_at if scan else None,
            'daily_costs':[{'date':d,'amount':str(a)} for d,a in sorted(daily.items())]}
