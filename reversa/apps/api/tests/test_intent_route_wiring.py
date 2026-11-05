"""Cycle 2 intent-route wiring (AGENT-08): gate -> template selection,
domain-aware naming, and provenance response headers on POST /intents.

Complements test_intents_contracts.py (AGENT-03: clarify/refuse shapes,
validator authority, rate parity, gate short-circuit): this file pins the
wiring that turns a gate domain label into the right deterministic plan
(offboarding / escalation builders via soft import, onboarding fallback
with an explicit warning), per-domain default workflow names, and the
X-Reversa-* provenance headers on every intent outcome (201 plan,
200 clarify, 200 refuse).

Durable + offline: the gate and the template modules are stubbed via
``sys.modules`` (same pattern as AGENT-03); tests prefixed ``real_``
exercise the merged sibling branches when present and skip honestly
until then.
"""

import sys
import types
from types import SimpleNamespace

import pytest

from reversa_api.planner import PlanResult, refusal_steps
from reversa_api.planner.deterministic import DeterministicPlanner
from reversa_api.templates.onboarding import build_onboarding_plan

from .conftest import INTENT


OFFBOARDING_STEPS = [
    {"action_type": "crm.validate_customer", "connector_id": "demo-crm",
     "inputs": {"customer_name": "Acme"}, "depends_on": []},
    {"action_type": "notify.send_summary", "connector_id": "demo-notify",
     "inputs": {"channel": "email", "message": "offboarded"}, "depends_on": [1]},
]

ESCALATION_STEPS = [
    {"action_type": "support.create_queue", "connector_id": "demo-support",
     "inputs": {"org_slug": "acme", "tier": "priority"}, "depends_on": []},
    {"action_type": "notify.send_summary", "connector_id": "demo-notify",
     "inputs": {"channel": "email", "message": "escalated"}, "depends_on": [1]},
]

_BUILDER_ATTR = {
    "offboarding": "build_offboarding_plan",
    "escalation": "build_escalation_plan",
}


def _post_intent(client, auth, intent, use_ai=False, **extra):
    payload = {"intent": intent, "use_ai": use_ai}
    payload.update(extra)
    return client.post("/api/v1/intents", json=payload,
                       headers=auth["headers"])


def _no_gate(monkeypatch):
    """Pin the legacy path: ignore the deterministic gate if merged."""
    from reversa_api.routes import workflows
    monkeypatch.setattr(workflows, "_cycle2_gate_verdict", lambda intent: None)


def _stub_gate(monkeypatch, label, reason="", matched=()):
    """Inject a fake planner/intent.py behind the soft imports."""
    fake = types.ModuleType("reversa_api.planner.intent")
    verdict = SimpleNamespace(label=label, reason=reason, matched=tuple(matched))
    fake.classify_intent = lambda intent, caps=None: verdict  # noqa: E731
    monkeypatch.setitem(sys.modules, "reversa_api.planner.intent", fake)
    return verdict


def _stub_template(monkeypatch, label, steps):
    """Inject a fake templates/<label>.py builder behind the soft import."""
    fake = types.ModuleType(f"reversa_api.templates.{label}")
    setattr(fake, _BUILDER_ATTR[label],
            lambda customer=None: [dict(s) for s in steps])
    monkeypatch.setitem(sys.modules, f"reversa_api.templates.{label}", fake)


def _no_vultr_key(monkeypatch):
    """Force the deterministic fallback even if a key is configured."""
    import reversa_api.planner as planner_mod
    from reversa_api.config import settings
    # settings is a frozen dataclass: swap the planner's reference for a
    # keyless copy instead of mutating the singleton.
    fake = SimpleNamespace(vultr_api_key="", vultr_model=settings.vultr_model,
                           vultr_base_url=settings.vultr_base_url)
    monkeypatch.setattr(planner_mod, "settings", fake)


def _actions(client, auth, wf_id):
    r = client.get(f"/api/v1/workflows/{wf_id}", headers=auth["headers"])
    assert r.status_code == 200, r.text
    return [a["action_type"] for a in r.json()["actions"]]


def _provenance(r):
    h = r.headers
    return {
        "provider": h.get("x-reversa-provider"),
        "model": h.get("x-reversa-model"),
        "latency_ms": h.get("x-reversa-latency-ms"),
        "warnings": h.get("x-reversa-warnings"),
    }


# --- template selection (stubbed gate + stubbed builders) ---


def test_offboarding_label_selects_offboarding_template(
        client, demo_auth, monkeypatch):
    _stub_gate(monkeypatch, "offboarding", reason="offboarding keywords: revoke")
    _stub_template(monkeypatch, "offboarding", OFFBOARDING_STEPS)
    r = _post_intent(client, demo_auth, "Revoke the departing employee access",
                     customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Offboard Acme"
    assert "status" not in body
    assert body["warnings"] == []
    assert _actions(client, demo_auth, body["workflow"]["id"]) == [
        "crm.validate_customer", "notify.send_summary"]


def test_escalation_label_selects_escalation_template(
        client, demo_auth, monkeypatch):
    _stub_gate(monkeypatch, "escalation", reason="escalation keywords: outage")
    _stub_template(monkeypatch, "escalation", ESCALATION_STEPS)
    r = _post_intent(client, demo_auth, "Escalate the outage to oncall",
                     customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Escalate Acme"
    assert body["warnings"] == []
    assert _actions(client, demo_auth, body["workflow"]["id"]) == [
        "support.create_queue", "notify.send_summary"]


def test_onboarding_label_uses_onboarding_template(
        client, demo_auth, monkeypatch):
    _stub_gate(monkeypatch, "onboarding", reason="onboarding keywords: onboard")
    r = _post_intent(client, demo_auth, INTENT,
                     customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Onboard Acme"
    assert body["warnings"] == []
    assert len(_actions(client, demo_auth, body["workflow"]["id"])) == 10


def test_missing_template_falls_back_to_onboarding_with_warning(
        client, demo_auth, monkeypatch):
    """Template module absent post-stub: still executable, warning set."""
    from reversa_api.planner import deterministic as det_mod
    _stub_gate(monkeypatch, "offboarding", reason="offboarding keywords: revoke")
    monkeypatch.setattr(det_mod, "_template_builder", lambda label: None)
    r = _post_intent(client, demo_auth, "Revoke the departing employee access",
                     customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Offboard Acme"
    assert body["warnings"] == [
        "offboarding template unavailable; default template used"]
    assert len(_actions(client, demo_auth, body["workflow"]["id"])) == 10


def test_unknown_gate_label_falls_back_to_onboarding(
        client, demo_auth, monkeypatch):
    _stub_gate(monkeypatch, "frobnicate", reason="unknown future label")
    r = _post_intent(client, demo_auth, "Xqzt blorpt fnord",
                     customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Onboard Acme"
    assert len(_actions(client, demo_auth, body["workflow"]["id"])) == 10


def test_explicit_name_wins_over_domain_naming(client, demo_auth, monkeypatch):
    _stub_gate(monkeypatch, "escalation", reason="escalation keywords: outage")
    _stub_template(monkeypatch, "escalation", ESCALATION_STEPS)
    r = _post_intent(client, demo_auth, "Escalate the outage to oncall",
                     name="Custom ticket name")
    assert r.status_code == 201, r.text
    assert r.json()["workflow"]["name"] == "Custom ticket name"


def test_legacy_naming_without_gate(client, demo_auth, monkeypatch):
    _no_gate(monkeypatch)
    r = _post_intent(client, demo_auth, INTENT,
                     customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    assert r.json()["workflow"]["name"] == "Onboard Acme"


# --- planner-level wiring (no HTTP) ---


def test_planner_selects_stubbed_builder_without_warning(monkeypatch):
    _stub_gate(monkeypatch, "offboarding")
    _stub_template(monkeypatch, "offboarding", OFFBOARDING_STEPS)
    result = DeterministicPlanner().generate("Revoke access", {}, [])
    assert [s["action_type"] for s in result.steps] == [
        "crm.validate_customer", "notify.send_summary"]
    assert result.warnings == []


def test_planner_fallback_warning_names_domain(monkeypatch):
    from reversa_api.planner import deterministic as det_mod
    _stub_gate(monkeypatch, "escalation")
    monkeypatch.setattr(det_mod, "_template_builder", lambda label: None)
    result = DeterministicPlanner().generate("Escalate the outage", {}, [])
    assert len(result.steps) == len(build_onboarding_plan(None))
    assert result.warnings == [
        "escalation template unavailable; default template used"]


def test_planner_legacy_warning_without_gate(monkeypatch):
    """Gate unavailable (blocked import): legacy behavior preserved."""
    import importlib as _il
    real_import = _il.import_module

    def _blocked(name, *args, **kwargs):
        if name == "reversa_api.planner.intent":
            raise ImportError("gate unavailable (test)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(_il, "import_module", _blocked)
    result = DeterministicPlanner().generate("Xqzt blorpt fnord", {}, [])
    assert len(result.steps) == 10
    assert result.warnings == [
        "intent does not clearly match onboarding; default template used"]
    result = DeterministicPlanner().generate("Onboard Acme please", {}, [])
    assert result.warnings == []


# --- provenance headers on every intent outcome ---


def test_plan_response_carries_provenance_headers(client, demo_auth, monkeypatch):
    _no_gate(monkeypatch)
    r = _post_intent(client, demo_auth, INTENT)
    assert r.status_code == 201, r.text
    body = r.json()
    prov = _provenance(r)
    assert prov["provider"] == body["provider"] == "deterministic"
    assert prov["model"] == ""
    assert prov["latency_ms"] is not None and int(prov["latency_ms"]) >= 0
    assert prov["warnings"] == str(len(body["warnings"]))


def test_gate_clarify_response_carries_provenance_headers(
        client, demo_auth, monkeypatch):
    _stub_gate(monkeypatch, "ambiguous", reason="no domain signal")
    r = _post_intent(client, demo_auth, "Do the thing")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "needs_clarification"
    prov = _provenance(r)
    assert prov["provider"] == "deterministic"
    assert prov["model"] == ""
    assert int(prov["latency_ms"]) >= 0
    assert prov["warnings"] == str(len(r.json()["warnings"]))


def test_gate_refuse_response_carries_provenance_headers(
        client, demo_auth, monkeypatch):
    _stub_gate(monkeypatch, "offscope", reason="no domain signal")
    r = _post_intent(client, demo_auth, "Xqzt blorpt fnord")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refused"
    assert _provenance(r)["provider"] == "deterministic"


def test_validator_refuse_headers_mirror_provider_result(
        client, demo_auth, monkeypatch):
    from reversa_api.routes import workflows
    _no_gate(monkeypatch)
    result = PlanResult(
        steps=refusal_steps("OUT_OF_SCOPE", "off-domain"),
        provider="vultr-inference", model="qa-model", latency_ms=42,
        warnings=["w1", "w2"])
    monkeypatch.setattr(workflows, "plan_from_intent",
                        lambda intent, customer, use_ai: result)
    r = _post_intent(client, demo_auth, "Write me a poem", use_ai=True)
    assert r.status_code == 200, r.text
    assert _provenance(r) == {
        "provider": "vultr-inference", "model": "qa-model",
        "latency_ms": "42", "warnings": "2"}


def test_provenance_headers_ascii_safe_with_unicode_warnings(
        client, demo_auth, monkeypatch):
    from reversa_api.routes import workflows
    _no_gate(monkeypatch)
    result = PlanResult(
        steps=refusal_steps("NEEDS_CLARIFICATION", "vague",
                            questions=["Which domain?"]),
        provider="vultr-inference", model="modèle-☃", latency_ms=7,
        warnings=["détail ☃"])
    monkeypatch.setattr(workflows, "plan_from_intent",
                        lambda intent, customer, use_ai: result)
    r = _post_intent(client, demo_auth, "Do the thing", use_ai=True)
    assert r.status_code == 200, r.text
    # Body keeps full unicode; headers degrade to ASCII, never 500.
    assert r.json()["warnings"] == ["détail ☃"]
    for value in _provenance(r).values():
        assert value is not None
        value.encode("ascii")
    assert _provenance(r)["warnings"] == "1"


def test_cors_exposes_provenance_headers(client, demo_auth, monkeypatch):
    _no_gate(monkeypatch)
    headers = dict(demo_auth["headers"])
    headers["Origin"] = "http://localhost:3000"
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=headers)
    assert r.status_code == 201, r.text
    exposed = r.headers.get("access-control-expose-headers", "").lower()
    for name in ("x-reversa-provider", "x-reversa-model",
                 "x-reversa-latency-ms", "x-reversa-warnings"):
        assert name in exposed, exposed


# --- real gate + real templates (run once siblings merge; skip until then) ---


def test_real_offboarding_intent_builds_offboarding_plan(
        client, demo_auth):
    pytest.importorskip("reversa_api.planner.intent")
    templates = pytest.importorskip("reversa_api.templates.offboarding")
    r = _post_intent(
        client, demo_auth,
        "Offboard Acme Corporation: revoke workspace access and disable "
        "the departing employee accounts.",
        customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Offboard Acme"
    assert body["warnings"] == []
    expected = [s["action_type"]
                for s in templates.build_offboarding_plan(None)]
    assert _actions(client, demo_auth, body["workflow"]["id"]) == expected


def test_real_escalation_intent_builds_escalation_plan(
        client, demo_auth):
    pytest.importorskip("reversa_api.planner.intent")
    templates = pytest.importorskip("reversa_api.templates.escalation")
    r = _post_intent(
        client, demo_auth,
        "Escalate the Acme support outage to the oncall team, P1 "
        "incident, respond urgently.",
        customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow"]["name"] == "Escalate Acme"
    assert body["warnings"] == []
    expected = [s["action_type"]
                for s in templates.build_escalation_plan(None)]
    assert _actions(client, demo_auth, body["workflow"]["id"]) == expected


def test_real_ai_fallback_keeps_domain_template(client, demo_auth, monkeypatch):
    """Vultr unconfigured + use_ai: deterministic fallback still routes."""
    pytest.importorskip("reversa_api.planner.intent")
    templates = pytest.importorskip("reversa_api.templates.offboarding")
    _no_vultr_key(monkeypatch)
    r = _post_intent(
        client, demo_auth,
        "Offboard Acme Corporation: revoke workspace access and disable "
        "the departing employee accounts.",
        use_ai=True, customer={"company_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert any("deterministic planner used" in w for w in body["warnings"])
    expected = [s["action_type"]
                for s in templates.build_offboarding_plan(None)]
    assert _actions(client, demo_auth, body["workflow"]["id"]) == expected
