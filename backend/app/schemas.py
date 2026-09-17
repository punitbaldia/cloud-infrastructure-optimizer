from datetime import date
from decimal import Decimal
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metric(ContractModel):
    value: float | None = None
    unit: str
    aggregation: Literal["average", "maximum", "minimum", "sum"]
    sample_count: int = Field(ge=0)


class ResourceSnapshot(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    resource_id: str
    account_id: str
    region: str
    resource_type: Literal["ec2", "rds"]
    observed_at: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    configuration: dict = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, Metric] = Field(default_factory=dict)
    data_quality: Literal["complete", "partial", "insufficient"]
    missing_metrics: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_window(self):
        if self.window_start >= self.window_end or self.observed_at < self.window_end:
            raise ValueError('Require window_start < window_end <= observed_at')
        return self


class DailyCost(ContractModel):
    date: date
    account_id: str
    service: str
    amount: Decimal = Field(ge=0)
    currency: str = Field(default='USD', pattern='^[A-Z]{3}$')
    cost_basis: str = 'UnblendedCost'
    estimated: bool = False


class Recommendation(ContractModel):
    id: UUID
    resource_id: str | None = None
    finding_type: Literal["idle_ec2", "oversized_rds", "cost_anomaly"]
    title: str
    explanation: str
    evidence: list[str]
    proposed_action: Literal["stop_ec2", "review_rds", "investigate_cost"]
    risk_level: Literal["low", "medium", "high"]
    estimated_monthly_savings: Decimal | None = Field(default=None, ge=0)
    currency: str = "USD"
    savings_assumptions: list[str] = Field(default_factory=list)
    status: Literal["open", "approved", "dismissed", "resolved"] = "open"
    data_source: Literal["mock", "aws"] = "mock"
    created_at: AwareDatetime
    explanation_source: Literal['mock', 'claude', 'rules_fallback'] = 'mock'


class ExecutionRequest(ContractModel):
    idempotency_key: UUID


class ExecutionJob(ContractModel):
    id: UUID
    recommendation_id: UUID
    status: Literal[
        "queued", "running", "succeeded", "failed", "cancelled"
    ]
    simulated: bool = True
    message: str
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None


T = TypeVar('T')


class Page(ContractModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    data_source: Literal['mock'] = 'mock'


class ResourceResponse(ResourceSnapshot):
    id: UUID
    data_source: Literal['mock'] = 'mock'


class ScanResponse(ContractModel):
    id: UUID
    status: Literal['queued', 'running', 'succeeded', 'failed']
    message: str
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    data_source: Literal['mock'] = 'mock'


class CostPoint(ContractModel):
    date: date
    amount: Decimal


class OverviewResponse(ContractModel):
    data_source: Literal['mock'] = 'mock'
    currency: str
    month_to_date_cost: Decimal
    cost_coverage: str
    estimated_monthly_savings: Decimal
    observed_savings: Decimal | None
    resource_count: int
    open_recommendation_count: int
    critical_finding_count: int
    last_successful_scan_at: AwareDatetime | None
    daily_costs: list[CostPoint]
