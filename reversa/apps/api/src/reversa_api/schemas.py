"""Strict API + plan schemas (Pydantic v2, extra=forbid everywhere)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanStepIn(Strict):
    action_type: str
    connector_id: str
    inputs: dict = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)


class PlanIn(Strict):
    goal: str = ""
    steps: list[PlanStepIn] = Field(default_factory=list)


class IntentIn(Strict):
    intent: str = Field(min_length=3, max_length=2000)
    name: str = Field(default="", max_length=128)
    customer: dict = Field(default_factory=dict)
    use_ai: bool = True


class ApproveIn(Strict):
    plan_hash: str
    decided_by: str = "demo-user"


class ChaosIn(Strict):
    target_connector: str
    target_action: str = ""
    fault: str
    times: int = Field(default=1, ge=1, le=10)


class WorkflowOut(Strict):
    id: int
    org_slug: str
    name: str
    intent: str
    state: str
    plan_version: int
    plan_hash: str
    steps: int
    created_by: str


class ActionOut(Strict):
    seq: int
    action_type: str
    connector_id: str
    state: str
    attempt: int
    max_attempts: int
    compensation_capability: str
    depends_on: list[int]
    error: str


class EventOut(Strict):
    seq: int
    ts: str
    type: str
    actor: str
    payload: dict
    prev_hash: str
    hash: str


class PreviewEffect(Strict):
    connector_id: str
    effects: list[str]
    compensation_capability: str
    approval_policy: str
    risk_level: str


class PreviewOut(Strict):
    plan_hash: str
    steps: int
    effects: list[PreviewEffect]
    approvals_required: bool
    irreversible: list[str]
    limits: list[str]


class ErrorOut(Strict):
    code: str
    type: str
    message: str
    details: dict = Field(default_factory=dict)
    retryable: bool = False
