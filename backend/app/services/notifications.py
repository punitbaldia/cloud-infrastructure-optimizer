"""Explicitly enabled, deduplicated notification delivery. Secrets stay server-side."""
import httpx
from sqlalchemy import select, update
from app.config import get_settings
from app.database import SessionLocal
from app.models import Notification
from app.services.preferences import preferences

def enqueue(db,key,message):
    if not db.scalar(select(Notification).where(Notification.event_key==key)):
        db.add(Notification(event_key=key,message=message,status="pending"))

def deliver():
    s=get_settings()
    with SessionLocal() as db:
        if not preferences(db)["notifications_enabled"]:
            return
        rows=db.scalars(select(Notification).where(Notification.status=="pending").limit(20)).all()
        for row in rows:
            # Claim before sending; failed/uncertain deliveries are not automatically retried.
            claimed=db.execute(update(Notification).where(Notification.id==row.id,Notification.status=='pending').values(status='sending'))
            db.commit()
            if claimed.rowcount!=1:
                continue
            try:
                sent=False
                if s.slack_webhook_url:
                    if not s.slack_webhook_url.startswith("https://hooks.slack.com/services/"):
                        raise ValueError("Invalid Slack webhook host")
                    response=httpx.post(s.slack_webhook_url,json={"text":row.message},timeout=10)
                    response.raise_for_status()
                    sent=True
                if s.ses_sender and s.alert_recipient:
                    import boto3
                    boto3.Session(profile_name=s.aws_profile or None, region_name=s.aws_region).client("ses").send_email(
                        Source=s.ses_sender,Destination={"ToAddresses":[s.alert_recipient]},
                        Message={"Subject":{"Data":"Cloud optimizer alert"},"Body":{"Text":{"Data":row.message}}})
                    sent=True
                row.status="sent" if sent else "unconfigured"
            except Exception:
                row.status="failed"
            db.commit()
