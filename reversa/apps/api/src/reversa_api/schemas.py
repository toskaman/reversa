"""Strict API + plan schemas (Pydantic v2, extra=forbid everywhere)."""

from __future__ import annotations

import json

MAX_CUSTOMER_JSON_BYTES = 8192
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    @field_validator("customer")
    @classmethod
    def _bound_customer(cls, v: dict) -> dict:
        # RT-V5-05: customer merges into plan inputs; cap its size.
        if len(json.dumps(v, default=str)) > MAX_CUSTOMER_JSON_BYTES:
            raise ValueError("customer must serialize to at most 8192 bytes")
        return v


class ApproveIn(Strict):
    plan_hash: str
    decided_by: str = Field(default="demo-user", max_length=64)


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


# Cycle 2 clarify/refuse contracts (spec 2026-11-05-cycle2-agentic-design
# §2/§3): POST /api/v1/intents answers HTTP 200 with exactly one of these
# when no workflow is created. The accepted-plan shape (201, no `status`
# key) is unchanged so the UI classifier keeps working. Codes mirror
# REFUSAL_CODES in planner/validate.py minus NEEDS_CLARIFICATION (pinned
# by test_intents_contracts.py::test_refusal_codes_mirror_validator).


class ClarificationOut(Strict):
    status: Literal["needs_clarification"] = "needs_clarification"
    questions: list[str] = Field(min_length=1, max_length=3)
    provider: str = "deterministic"
    warnings: list[str] = Field(default_factory=list)


class RefusalOut(Strict):
    status: Literal["refused"] = "refused"
    code: Literal["OUT_OF_SCOPE", "UNSAFE_REQUEST", "IMPOSSIBLE_REQUEST"]
    reason: str = Field(min_length=1, max_length=500)
    provider: str = "deterministic"
    warnings: list[str] = Field(default_factory=list)
