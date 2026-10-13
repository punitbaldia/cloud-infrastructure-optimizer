from datetime import datetime,timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.config import get_settings
from app.database import SessionLocal
from app.models import Scan
from app.services.preferences import preferences

def tick():
    with SessionLocal() as db:
        prefs=preferences(db)
        if not prefs["scheduled_scans"]:
            return
        last=db.scalar(select(Scan).order_by(Scan.created_at.desc()))
        if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last.created_at)).total_seconds()<prefs["scan_interval_minutes"]*60:
            return
        job=Scan(active_key="single-account",data_source=get_settings().cloud_mode)
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return
        job_id=job.id
    from app.services.jobs import run_scan
    run_scan(job_id)
