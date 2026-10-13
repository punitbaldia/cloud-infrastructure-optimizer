from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


class Resource(Base):
    __tablename__ = 'resources'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    identity: Mapped[str] = mapped_column(String(300), unique=True)
    resource_id: Mapped[str] = mapped_column(String(160), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Snapshot(Base):
    __tablename__ = 'snapshots'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    resource_id: Mapped[str] = mapped_column(ForeignKey('resources.id'))
    scan_id: Mapped[str] = mapped_column(ForeignKey('scans.id'))
    payload: Mapped[dict] = mapped_column(JSON)


class DailyCostRow(Base):
    __tablename__ = 'daily_costs'
    __table_args__ = (UniqueConstraint('account_id', 'service', 'day', 'currency', 'cost_basis'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(String(32))
    service: Mapped[str] = mapped_column(String(100))
    day: Mapped[str] = mapped_column(String(10))
    currency: Mapped[str] = mapped_column(String(3))
    cost_basis: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)


class Scan(Base):
    __tablename__ = 'scans'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    active_key: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(String(500), default='Mock scan queued')
    data_source: Mapped[str] = mapped_column(String(10), default='mock', server_default='mock')


class RecommendationRow(Base):
    __tablename__ = 'recommendations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(500), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='open', index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ExecutionRow(Base):
    __tablename__ = 'executions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey('recommendations.id'), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(String(500), default='Simulation queued')
    simulated: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1')


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Preference(Base):
    __tablename__ = 'preferences'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class User(Base):
    __tablename__ = 'users'
    username: Mapped[str] = mapped_column(String(100), primary_key=True)
    salt: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(128))


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(ForeignKey('users.username'))
    expires_at: Mapped[str] = mapped_column(String(40))


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    username: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[str] = mapped_column(String(40))


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    message: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
