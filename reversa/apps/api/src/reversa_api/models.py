"""Durable saga state: workflows, actions, events, approvals, chaos rules."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from .db import Base


def utcnow() -> dt.datetime:
    # Naive UTC everywhere: SQLite does not preserve tzinfo, and mixing
    # naive/aware datetimes breaks all lease/expiry comparisons.
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def as_naive_utc(value: dt.datetime | None) -> dt.datetime | None:
    """Coerce a DB-read datetime (naive on SQLite, aware on Postgres) to naive UTC."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = {"info": {"db": "main"}}

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    is_demo: Mapped[int] = mapped_column(Integer, default=0)


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = {"info": {"db": "main"}}

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    intent: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    execute_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by: Mapped[str] = mapped_column(String(128), default="demo-user")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionRun(Base):
    __tablename__ = "actions"
    __table_args__ = (
        Index("ix_actions_wf_seq", "workflow_id", "seq"),
        {"info": {"db": "main"}},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(128))
    connector_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_owner: Mapped[str] = mapped_column(String(64), default="")
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compensation_capability: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    depends_on: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    """Append-only evidence timeline (application level)."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_wf_seq", "workflow_id", "seq", unique=True),
        {"info": {"db": "main"}},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), index=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), default="GENESIS")
    hash: Mapped[str] = mapped_column(String(64), default="")


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = {"info": {"db": "main"}}

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), index=True)
    plan_version: Mapped[int] = mapped_column(Integer)
    plan_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), default="")
    decided_by: Mapped[str] = mapped_column(String(128), default="")
    expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = {"info": {"db": "main"}}

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(64), default="default")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChaosRule(Base):
    __tablename__ = "chaos_rules"
    __table_args__ = {"info": {"db": "main"}}

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_connector: Mapped[str] = mapped_column(String(64))
    target_action: Mapped[str] = mapped_column(String(128), default="")
    fault: Mapped[str] = mapped_column(String(32))
    times_remaining: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[int] = mapped_column(Integer, default=1)


class DemoResource(Base):
    """Generic resource row; the table is created once per demo-service store."""

    __tablename__ = "demo_resources"
    __table_args__ = {"info": {"db": "demo"}}

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
