"""Run only with the API and every worker stopped."""
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Scan, ExecutionRow, AuditEvent, now

with SessionLocal() as db:
    count=0
    for model in (Scan,ExecutionRow):
        for row in db.scalars(select(model).where(model.status.in_(['queued','running']))):
            row.status='failed'
            row.completed_at=now()
            row.message='Marked failed during manual stopped-worker recovery; no action retried.'
            if isinstance(row,Scan):
                row.active_key=None
            db.add(AuditEvent(entity_id=row.id,action='manual_job_recovery'))
            count+=1
    db.commit()
    print(f'Recovered {count} abandoned jobs.')

