from app.models import Preference

DEFAULTS = {"scan_interval_minutes": 60, "scheduled_scans": False, "notifications_enabled": False}
def preferences(db):
    row = db.get(Preference, "global")
    return {**DEFAULTS, **(row.payload if row else {})}
def connection():
    from app.config import get_settings
    s=get_settings()
    return {"account_id":s.aws_account_id,"region":s.aws_region,"role_arn":s.aws_role_arn,"external_id":s.aws_external_id,"execution_role_arn":s.aws_execution_role_arn}
