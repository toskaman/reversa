"""Planner + evidence unit tests."""

import json

from reversa_api.evidence import append_event, redact, verify_chain
from reversa_api.db import session_for
from reversa_api.models import Event, Workflow
from reversa_api.planner import (
    DeterministicPlanner,
    available_capabilities,
    plan_hash,
    validate_plan,
)


def test_deterministic_planner_valid_10_steps():
    caps = available_capabilities()
    assert len(caps) == 10
    result = DeterministicPlanner().generate("Onboard Acme please", {}, caps)
    assert result.provider == "deterministic"
    normalized, approval_required, issues = validate_plan({"steps": result.steps})
    assert issues == []
    assert len(normalized) == 10
    assert approval_required is True


def test_validate_rejects_unknown_action_bad_deps():
    _, _, issues = validate_plan({"steps": [
        {"action_type": "nope.doit", "connector_id": "demo-crm",
         "inputs": {}, "depends_on": []}]})
    assert any(i.code == "UNKNOWN_CAPABILITY" for i in issues)
    _, _, issues = validate_plan({"steps": [
        {"action_type": "crm.validate_customer", "connector_id": "demo-crm",
         "inputs": {"customer_name": "x"}, "depends_on": [2]}]})
    assert any(i.code == "BAD_DEPS" for i in issues)
    h1 = plan_hash([{"a": 1}])
    assert h1 == plan_hash([{"a": 1}]) and len(h1) == 64


def test_evidence_chain_and_tamper(fresh_db, demo_auth):
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="e", intent="e",
                      state="RUNNING", plan_json="{}", created_by="t")
        session.add(wf)
        session.flush()
        append_event(session, wf.id, wf.org_id, "a", {"n": 1})
        append_event(session, wf.id, wf.org_id, "b", {"token": "supersecretvalue1234567890"})
        session.commit()
        ok, _, _ = verify_chain(session, wf.id)
        assert ok is True
        # secrets redacted at append time
        row = session.query(Event).filter_by(workflow_id=wf.id, seq=2).first()
        assert "supersecret" not in row.payload_json
        # tamper -> invalid
        row.payload_json = json.dumps({"n": 999})
        session.commit()
        ok, bad, _ = verify_chain(session, wf.id)
        assert ok is False and bad == 2
    finally:
        session.close()


def test_redact_nested():
    assert redact({"api_key": "x", "deep": {"password": "y", "ok": 1}}) == {
        "api_key": "***REDACTED***", "deep": {"password": "***REDACTED***", "ok": 1}}
