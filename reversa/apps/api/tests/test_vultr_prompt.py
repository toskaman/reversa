"""Cycle 2 Vultr prompt: 3 domains + clarify/refuse mapping (spec §5).

The system prompt lists onboarding / offboarding / escalation plus the
4-code refusal vocabulary, and the provider maps model ``refusal`` /
``clarify`` outputs onto the sentinel steps that ``validate_plan`` (the
authority) accepts or rejects.

Durable + offline: every provider test drives ``VultrInferenceProvider``
with a scripted HTTP-client factory — no key, no network, no live calls.
"""

import json

import pytest

from reversa_api.planner import (
    VultrInferenceProvider,
    available_capabilities,
    validate_plan,
)
from reversa_api.planner.vultr import SYSTEM_PROMPT


# --- prompt content ---


def test_prompt_lists_three_domains():
    assert "onboarding" in SYSTEM_PROMPT
    assert "offboarding" in SYSTEM_PROMPT
    assert "escalation" in SYSTEM_PROMPT


def test_prompt_lists_all_refusal_codes():
    for code in ("OUT_OF_SCOPE", "UNSAFE_REQUEST", "IMPOSSIBLE_REQUEST",
                 "NEEDS_CLARIFICATION"):
        assert code in SYSTEM_PROMPT


def test_prompt_documents_clarify_shape():
    assert "clarify" in SYSTEM_PROMPT
    assert "questions" in SYSTEM_PROMPT
    assert "3" in SYSTEM_PROMPT


def test_prompt_keeps_core_safety_rules():
    assert "Output ONLY JSON" in SYSTEM_PROMPT
    assert "Never invent actions" in SYSTEM_PROMPT
    assert "Never emit both a refusal and steps" in SYSTEM_PROMPT
    assert "refusal" in SYSTEM_PROMPT


# --- offline provider mapping (stubbed client factory) ---


class _FakeResponse:
    def __init__(self, payload: dict, model: str = "qa-model"):
        payload = {"model": model, **payload}
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._payload


def _stub_provider(model_output: dict, model: str = "qa-model",
                   requested: str = "qa-model") -> VultrInferenceProvider:
    payload = {
        "choices": [{"message": {"content": json.dumps(model_output)}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7,
                  "total_tokens": 18},
    }
    reply = _FakeResponse(payload, model=model)

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):  # noqa: A002 - httpx shape
            return reply

    return VultrInferenceProvider("fake-key", requested, "https://fake.local/v1",
                                  client_factory=lambda: _FakeClient())


@pytest.mark.parametrize("code,message", [
    ("OUT_OF_SCOPE", "book me a flight"),
    ("UNSAFE_REQUEST", "ignore previous instructions"),
    ("IMPOSSIBLE_REQUEST", "teleport the database to Mars"),
    ("NEEDS_CLARIFICATION", "too vague to plan"),
])
def test_refusal_codes_map_to_typed_issues(code, message):
    provider = _stub_provider({"refusal": {"code": code, "message": message}})
    result = provider.generate("anything", {}, available_capabilities())
    assert result.provider == "vultr-inference"
    assert result.usage["attempts"] == 1
    assert result.usage["total_tokens"] == 18
    assert result.latency_ms >= 0
    assert any(code in w for w in result.warnings)
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == [code]
    assert issues[0].field == "intent"


def test_refusal_with_questions_carried_through():
    provider = _stub_provider({"refusal": {
        "code": "NEEDS_CLARIFICATION", "message": "which domain?",
        "questions": ["onboarding or offboarding?", "which customer?"]}})
    result = provider.generate("Do the thing", {}, available_capabilities())
    assert result.steps[0]["inputs"]["questions"] == [
        "onboarding or offboarding?", "which customer?"]
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def test_refusal_questions_capped_at_three():
    provider = _stub_provider({"refusal": {
        "code": "NEEDS_CLARIFICATION", "message": "vague",
        "questions": ["q1", "q2", "q3", "q4"]}})
    result = provider.generate("Do the thing", {}, available_capabilities())
    assert result.steps[0]["inputs"]["questions"] == ["q1", "q2", "q3"]
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def test_clarify_shape_maps_to_needs_clarification():
    provider = _stub_provider({"clarify": {
        "message": "which domain?", "questions": ["onboard or offboard?"]}})
    result = provider.generate("Handle Acme", {}, available_capabilities())
    assert result.provider == "vultr-inference"
    assert result.usage["attempts"] == 1
    assert result.latency_ms >= 0
    assert any("NEEDS_CLARIFICATION" in w for w in result.warnings)
    assert result.steps[0]["inputs"]["questions"] == ["onboard or offboard?"]
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def test_clarify_without_questions_accepted():
    provider = _stub_provider({"clarify": {"message": "need more detail"}})
    result = provider.generate("Do the thing", {}, available_capabilities())
    assert "questions" not in result.steps[0]["inputs"]
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def test_clarify_many_questions_capped_at_three():
    provider = _stub_provider({"clarify": {
        "message": "vague",
        "questions": ["q1", "q2", "q3", "q4", "q5"]}})
    result = provider.generate("Do the thing", {}, available_capabilities())
    assert result.steps[0]["inputs"]["questions"] == ["q1", "q2", "q3"]
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


@pytest.mark.parametrize("bad_questions", [42, {"q": 1}, ["ok?", 7, "  "]])
def test_clarify_malformed_questions_never_crash(bad_questions):
    provider = _stub_provider({"clarify": {
        "message": "vague", "questions": bad_questions}})
    result = provider.generate("Do the thing", {}, available_capabilities())
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]
    kept = result.steps[0]["inputs"].get("questions", [])
    assert all(isinstance(q, str) and q.strip() for q in kept)
    assert len(kept) <= 3


def test_refusal_malformed_questions_never_crash():
    provider = _stub_provider({"refusal": {
        "code": "NEEDS_CLARIFICATION", "message": "vague",
        "questions": 42}})
    result = provider.generate("Do the thing", {}, available_capabilities())
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def test_refusal_wins_when_both_shapes_present():
    provider = _stub_provider({
        "refusal": {"code": "OUT_OF_SCOPE", "message": "off-domain"},
        "clarify": {"message": "hmm?", "questions": ["what?"]},
    })
    result = provider.generate("book a flight", {}, available_capabilities())
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["OUT_OF_SCOPE"]


def test_clarify_long_message_truncated():
    provider = _stub_provider({"clarify": {
        "message": "m" * 900, "questions": ["which?"]}})
    result = provider.generate("Do the thing", {}, available_capabilities())
    assert len(result.steps[0]["inputs"]["message"]) <= 500
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def test_clarify_keeps_model_substitution_warning():
    provider = _stub_provider(
        {"clarify": {"message": "vague", "questions": ["which?"]}},
        model="served-model", requested="asked-model")
    result = provider.generate("Do the thing", {}, available_capabilities())
    assert result.model == "served-model"
    assert result.usage["model_substituted"] is True
    assert any("substitution" in w for w in result.warnings)
    _, _, issues = validate_plan({"steps": result.steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]
