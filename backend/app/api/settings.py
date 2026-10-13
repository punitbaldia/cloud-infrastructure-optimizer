from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.database import get_db
from app.config import get_settings
from app.models import Preference, Notification, AuditEvent
from app.services.preferences import preferences, connection

router=APIRouter(prefix="/api/v1",tags=["Settings"])
class PreferencesUpdate(BaseModel):
    scan_interval_minutes:int=Field(ge=15,le=1440)
    scheduled_scans:bool
    notifications_enabled:bool

@router.get("/settings")
def settings(db=Depends(get_db)):
    s=get_settings()
    from app.remediation.policy import execution_role_error
    role_error=execution_role_error(connection())
    return {**preferences(db),"cloud_mode":s.cloud_mode,"job_mode":s.job_mode,
            "explanation_mode":s.explanation_mode,"claude_configured":bool(s.anthropic_api_key and s.claude_model),
            "slack_configured":bool(s.slack_webhook_url),"email_configured":bool(s.ses_sender and s.alert_recipient),
            "live_execution_enabled":s.live_execution_enabled,
            "live_execution_ready":s.live_execution_enabled and role_error is None,
            "execution_role_configured":bool(s.aws_execution_role_arn)}

@router.patch("/settings")
def update_settings(body:PreferencesUpdate,db=Depends(get_db)):
    row=db.get(Preference,"global")
    if not row:
        row=Preference(id="global",payload={})
        db.add(row)
    row.payload=body.model_dump()
    db.add(AuditEvent(entity_id="settings",action="settings_updated",details=body.model_dump()))
    db.commit()
    return settings(db)

@router.get("/connections")
def connections():
    s=get_settings()
    return {"items":[{"id":"primary","account_id":s.aws_account_id,"region":s.aws_region,
                     "provider":"AWS","data_source":s.cloud_mode,"role_configured":bool(s.aws_role_arn)}]}

@router.post("/connections/primary/validate")
def validate():
    try:
        if get_settings().cloud_mode=="aws":
            from app.cloud.aws import validate_connection
        else:
            from app.cloud.mock import validate_connection
        return validate_connection(connection())
    except Exception as exc:
        raise HTTPException(400,f"Connection validation failed ({type(exc).__name__}). Check server configuration and AWS permissions.")

@router.get("/notifications")
def notifications(db=Depends(get_db)):
    rows=db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(100)).all()
    return {"items":[{"id":r.id,"status":r.status,"message":r.message,"created_at":r.created_at} for r in rows]}

@router.get("/audit")
def audit(db=Depends(get_db)):
    rows=db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100)).all()
    return {"items":[{"id":r.id,"action":r.action,"entity_id":r.entity_id,"created_at":r.created_at,"details":r.details} for r in rows]}
