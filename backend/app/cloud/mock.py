"""Contract-compatible demo cloud adapter. No network access."""
from datetime import datetime, timedelta, timezone
from app.schemas import ResourceSnapshot, DailyCost, Metric
from app.services.mock_provider import collect_snapshots as legacy_snapshots, collect_daily_costs as legacy_costs

DEMO_ACCOUNT_ID = "000000000000"
DEMO_REGION = "ap-south-1"

def validate_connection(connection):
    account = connection.get("account_id", DEMO_ACCOUNT_ID)
    region = connection.get("region", DEMO_REGION)
    return {"valid": account == DEMO_ACCOUNT_ID and region == DEMO_REGION,
            "account_id": account, "region": region, "data_source": "mock",
            "message": "Demo connection uses generated data. No AWS request was sent."}

def collect_snapshots(connection, start, end):
    items = legacy_snapshots(connection, start, end)
    rds = next(r for r in items if r.resource_type == "rds")
    rds.data_quality = "complete"
    rds.missing_metrics = []
    rds.configuration.update({"db_instance_class": "db.m6g.large", "engine": "postgres"})
    rds.metrics.update({key: Metric.model_validate(value) for key,value in {
        "freeable_memory_bytes": {"value": 6000000000, "unit": "Bytes", "aggregation": "minimum", "sample_count": 336},
        "database_connections": {"value": 4, "unit": "Count", "aggregation": "maximum", "sample_count": 336},
        "read_iops": {"value": 3, "unit": "Count/Second", "aggregation": "maximum", "sample_count": 336},
        "write_iops": {"value": 2, "unit": "Count/Second", "aggregation": "maximum", "sample_count": 336},
    }.items()})
    # Revalidate after modifying metrics.
    return [ResourceSnapshot.model_validate(r.model_dump()) for r in items]

def collect_daily_costs(connection, start, end):
    return legacy_costs(connection, start, end)

def build_demo_snapshots(**kwargs):
    end = kwargs.get("end") or datetime.now(timezone.utc)
    return collect_snapshots({}, kwargs.get("start") or end-timedelta(days=14), end)

def build_demo_costs(*, start, end, **kwargs):
    return collect_daily_costs({}, start, end)

class MockCloudAdapter:
    validate_connection = staticmethod(validate_connection)
    collect_snapshots = staticmethod(collect_snapshots)
    collect_daily_costs = staticmethod(collect_daily_costs)
