"""Agentic structured refusal (Cycle 1 V3): OUT_OF_SCOPE / NEEDS_CLARIFICATION.

Contract:
- A provider that cannot plan safely returns sentinel ``meta.refusal``
  steps (see ``refusal_steps``); ``validate_plan`` translates them into
  typed ``ValidationIssue`` codes.
- Cycle 2 route contract (spec 2026-11-05-cycle2-agentic-design §2/§3):
  POST /api/v1/intents maps those codes onto HTTP 200
  ``{status: needs_clarification, questions}`` /
  ``{status: refused, code, reason}`` with no workflow created. The 422
  PLAN_REJECTED path now serves malformed plans only.

NOTE: the deterministic baseline intentionally never refuses (pinned by
``test_deterministic_baseline_measured``); refusal is an AI-provider
behavior surfaced through validation.
"""

import json

from reversa_api.planner import (
    PlanResult,
    VultrInferenceProvider,
    available_capabilities,
    refusal_steps,
    validate_plan,
)
from reversa_api.planner.vultr import SYSTEM_PROMPT


def test_refusal_steps_shape():
    steps = refusal_steps("OUT_OF_SCOPE", "not onboarding")
    assert steps == [{
        "action_type": "meta.refusal", "connector_id": "meta",
        "inputs": {"code": "OUT_OF_SCOPE", "message": "not onboarding"},
        "depends_on": [],
    }]


def test_validate_out_of_scope_refusal():
    normalized, approval, issues = validate_plan(
        {"steps": refusal_steps("OUT_OF_SCOPE", "Delete everything instead")})
    assert normalized == []
    assert approval is False
    assert len(issues) == 1
    assert issues[0].code == "OUT_OF_SCOPE"
    assert issues[0].step == 1
    assert issues[0].field == "intent"
    assert "Delete everything" in issues[0].message


def test_validate_needs_clarification_refusal():
    normalized, approval, issues = validate_plan(
        {"steps": refusal_steps("NEEDS_CLARIFICATION", "too vague to plan")})
    assert normalized == []
    assert approval is False
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]
    assert issues[0].to_dict()["field"] == "intent"


def test_validate_bad_refusal_code_rejected():
    _, _, issues = validate_plan({"steps": refusal_steps("MAYBE", "x")})
    assert [i.code for i in issues] == ["BAD_REFUSAL"]
    assert issues[0].field == "inputs.code"


def test_validate_refusal_message_truncated():
    _, _, issues = validate_plan(
        {"steps": refusal_steps("OUT_OF_SCOPE", "y" * 900)})
    assert len(issues[0].message) <= 500


def test_system_prompt_instructs_structured_refusal():
    assert "refusal" in SYSTEM_PROMPT
    assert "OUT_OF_SCOPE" in SYSTEM_PROMPT
    assert "NEEDS_CLARIFICATION" in SYSTEM_PROMPT
    assert "Never emit both a refusal and steps" in SYSTEM_PROMPT


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._payload


def _refusal_provider(code: str, message: str) -> VultrInferenceProvider:
    content = json.dumps({"refusal": {"code": code, "message": message}})
    payload = {"model": "qa-model",
               "choices": [{"message": {"content": content}}],
               "usage": {"prompt_tokens": 11, "completion_tokens": 7,
                         "total_tokens": 18}}
    reply = _FakeResponse(payload)

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):  # noqa: A002 - httpx shape
            return reply

    return VultrInferenceProvider("fake-key", "qa-model", "https://fake.local/v1",
                                  client_factory=lambda: _FakeClient())


def test_vultr_refusal_out_of_scope_offline():
    provider = _refusal_provider("OUT_OF_SCOPE", "not an onboarding request")
    result = provider.generate("Delete all workspaces", {}, available_capabilities())
    assert result.provider == "vultr-inference"
    assert result.model == "qa-model"
    assert result.usage["attempts"] == 1
    assert result.usage["total_tokens"] == 18
    assert any("OUT_OF_SCOPE" in w for w in result.warnings)
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["OUT_OF_SCOPE"]


def test_vultr_refusal_needs_clarification_offline():
    provider = _refusal_provider("NEEDS_CLARIFICATION", "which customer?")
    result = provider.generate("Do the thing", {}, available_capabilities())
    assert result.usage["attempts"] == 1
    assert any("NEEDS_CLARIFICATION" in w for w in result.warnings)
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]
    assert issues[0].field == "intent"


def test_intent_route_returns_refused_contract_on_refusal(client, demo_auth, monkeypatch):
    """Cycle 2 §3: refusal sentinel steps map to HTTP 200 refused, no workflow."""
    from reversa_api.routes import workflows

    def _fake_plan(intent: str, customer: dict, use_ai: bool) -> PlanResult:
        return PlanResult(
            steps=refusal_steps("OUT_OF_SCOPE", "not an onboarding request"),
            provider="vultr-inference", model="qa-model")

    monkeypatch.setattr(workflows, "plan_from_intent", _fake_plan)
    r = client.post("/api/v1/intents",
                    json={"intent": "Delete all workspaces to save money",
                          "use_ai": True},
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "refused"
    assert body["code"] == "OUT_OF_SCOPE"
    assert "not an onboarding request" in body["reason"]
    assert body["provider"] == "vultr-inference"
    assert "workflow" not in body
    r = client.get("/api/v1/workflows", headers=demo_auth["headers"])
    assert r.json()["data"] == []
