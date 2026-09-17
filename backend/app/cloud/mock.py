from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from contracts.cloud_contracts import (
    ConnectionConfig,
    ConnectionResult,
    DailyCost,
    DataQuality,
    MetricValue,
    ResourceSnapshot,
    ResourceType,
)


DEMO_ACCOUNT_ID = "demo-account"
DEMO_REGION = "ap-south-1"


class MockCloudAdapter:
    """Deterministic, network-free cloud adapter for the first integrated demo."""

    def __init__(self, *, account_id: str = DEMO_ACCOUNT_ID, region: str = DEMO_REGION) -> None:
        self.account_id = account_id
        self.region = region

    def validate_connection(self, connection: ConnectionConfig) -> ConnectionResult:
        if connection.account_id == "permission-denied":
            return ConnectionResult(
                valid=False,
                account_id=connection.account_id,
                region=connection.region,
                message="Mock connection rejected: simulated permission denied while validating the read-only cloud role.",
                provider_request_id="mock-validate-permission-denied",
            )
        if connection.account_id != self.account_id:
            return ConnectionResult(
                valid=False,
                account_id=connection.account_id,
                region=connection.region,
                message=f"Mock adapter is configured for account {self.account_id}, not {connection.account_id}.",
                provider_request_id="mock-validate-account-mismatch",
            )
        if connection.region != self.region:
            return ConnectionResult(
                valid=False,
                account_id=connection.account_id,
                region=connection.region,
                message=f"Mock adapter is configured for region {self.region}, not {connection.region}.",
                provider_request_id="mock-validate-region-mismatch",
            )
        return ConnectionResult(
            valid=True,
            account_id=connection.account_id,
            region=connection.region,
            message="Mock cloud connection validated; no AWS credentials or network calls were used.",
            provider_request_id="mock-validate-ok",
        )

    def collect_snapshots(
        self, connection: ConnectionConfig, start: datetime, end: datetime
    ) -> list[ResourceSnapshot]:
        now = datetime.now(timezone.utc)
        return build_demo_snapshots(
            account_id=connection.account_id,
            region=connection.region,
            start=start,
            end=end,
            observed_at=now,
        )

    def collect_daily_costs(
        self, connection: ConnectionConfig, start: datetime, end: datetime
    ) -> list[DailyCost]:
        return build_demo_costs(
            account_id=connection.account_id,
            start=start,
            end=end,
        )


def _metric(value: str | int | float | Decimal | None, unit: str, aggregation: str, samples: int) -> MetricValue:
    return MetricValue(value=None if value is None else Decimal(str(value)), unit=unit, aggregation=aggregation, sample_count=samples)


def build_demo_snapshots(
    *,
    account_id: str = DEMO_ACCOUNT_ID,
    region: str = DEMO_REGION,
    start: datetime | None = None,
    end: datetime | None = None,
    observed_at: datetime | None = None,
) -> list[ResourceSnapshot]:
    now = observed_at or datetime.now(timezone.utc)
    start = start or now - timedelta(hours=1)
    end = end or now

    base = dict(
        account_id=account_id,
        region=region,
        observed_at=now,
        window_start=start,
        window_end=end,
    )
    return [
        ResourceSnapshot(
            **base,
            resource_id="i-idle-demo",
            resource_type=ResourceType.EC2,
            configuration={"instance_type": "t3.medium", "state": "running", "platform": "linux"},
            tags={"optimizer:managed": "true", "Name": "idle-demo", "Environment": "demo"},
            metrics={
                "cpu_utilization": _metric("2.5", "percent", "avg", 6),
                "network_bytes": _metric("1200", "bytes", "avg", 6),
            },
            data_quality=DataQuality.COMPLETE,
        ),
        ResourceSnapshot(
            **base,
            resource_id="i-active-demo",
            resource_type=ResourceType.EC2,
            configuration={"instance_type": "t3.medium", "state": "running", "platform": "linux"},
            tags={"optimizer:managed": "true", "Name": "active-demo", "Environment": "demo"},
            metrics={
                "cpu_utilization": _metric("57.0", "percent", "avg", 6),
                "network_bytes": _metric("18000000", "bytes", "avg", 6),
            },
            data_quality=DataQuality.COMPLETE,
        ),
        ResourceSnapshot(
            **base,
            resource_id="i-untagged-demo",
            resource_type=ResourceType.EC2,
            configuration={"instance_type": "t3.small", "state": "running", "platform": "linux"},
            tags={"Name": "untagged-idle-demo", "Environment": "demo"},
            metrics={
                "cpu_utilization": _metric("1.8", "percent", "avg", 6),
                "network_bytes": _metric("900", "bytes", "avg", 6),
            },
            data_quality=DataQuality.COMPLETE,
        ),
        ResourceSnapshot(
            **base,
            resource_id="db-rds-demo",
            resource_type=ResourceType.RDS,
            configuration={"db_instance_class": "db.m6g.large", "engine": "postgres", "status": "available"},
            tags={"optimizer:managed": "true", "Name": "rds-demo", "Environment": "demo"},
            metrics={
                "cpu_utilization": _metric("12.0", "percent", "avg", 6),
                "freeable_memory": _metric("2147483648", "bytes", "avg", 6),
                "database_connections": _metric("7", "count", "avg", 6),
            },
            data_quality=DataQuality.COMPLETE,
        ),
        ResourceSnapshot(
            **base,
            resource_id="i-missing-metrics",
            resource_type=ResourceType.EC2,
            configuration={"instance_type": "t3.small", "state": "running", "platform": "linux"},
            tags={"optimizer:managed": "true", "Name": "missing-metrics-demo", "Environment": "demo"},
            metrics={},
            data_quality=DataQuality.PARTIAL,
            missing_metrics=["cpu_utilization", "network_bytes"],
        ),
    ]


def build_demo_costs(
    *,
    account_id: str = DEMO_ACCOUNT_ID,
    start: datetime,
    end: datetime,
) -> list[DailyCost]:
    """Return 14 baseline days plus one clearly anomalous day."""
    start_day = start.astimezone(timezone.utc).date()
    end_day = end.astimezone(timezone.utc).date()
    requested_days = max(1, (end_day - start_day).days + 1)
    days = max(15, requested_days)

    baseline = Decimal("12.50")
    costs: list[DailyCost] = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        # Put the anomaly on the final returned day so the fixture is easy to demonstrate.
        amount = Decimal("75.00") if offset == days - 1 and days >= 15 else baseline
        costs.append(
            DailyCost(
                date=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
                account_id=account_id,
                service="AmazonEC2",
                amount=amount,
                currency="USD",
                cost_basis="unblended",
                estimated=False,
            )
        )
    return costs
