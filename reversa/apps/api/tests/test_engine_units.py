"""Engine unit tests: transitions, claims, idempotence, recovery."""

import json
import threading

import pytest

from reversa_api.db import session_for
from reversa_api.engine.saga import (
    claim_action,
    execute_workflow_sync,
    reconcile_on_startup,
)
from reversa_api.engine.states import (
    InvalidTransition,
    check_action_transition,
    check_workflow_transition,
)
from reversa_api.evidence import append_event
from reversa_api.models import ActionRun, Workflow, utcnow


def test_illegal_transitions_refused():
    with pytest.raises(InvalidTransition):
        check_workflow_transition("COMPLETED", "RUNNING")
    with pytest.raises(InvalidTransition):
        check_workflow_transition("DRAFT", "RUNNING")
    with pytest.raises(InvalidTransition):
        check_action_transition("VERIFIED", "EXECUTING")
    with pytest.raises(InvalidTransition):
        check_action_transition("PENDING", "VERIFIED")
    # legal ones pass silently
    check_workflow_transition("READY", "RUNNING")
    check_action_transition("PENDING", "CLAIMED")


def _seed_wf(session, org_id: int) -> Workflow:
    wf = Workflow(org_id=org_id, name="t", intent="t", state="RUNNING",
                  plan_json="{}", created_by="test")
    session.add(wf)
    session.flush()
    session.add(ActionRun(
        workflow_id=wf.id, seq=1, action_type="crm.validate_customer",
        connector_id="demo-crm", state="PENDING", input_json='{"customer_name": "x"}',
        idempotency_key="k-seed-1", max_attempts=1,
        compensation_capability="COMPENSATABLE", depends_on="[]"))
    session.commit()
    return wf


def test_claim_race_single_winner(fresh_db, demo_auth):
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        action_id = session.query(ActionRun).filter_by(workflow_id=wf.id).first().id
    finally:
        session.close()
    winners = []

    def attempt(worker: str):
        s = session_for("main")()
        try:
            wf2 = s.get(Workflow, wf.id)
            won = claim_action(s, wf2, action_id, worker)
            if won is not None:
                winners.append(worker)
        finally:
            s.close()

    threads = [threading.Thread(target=attempt, args=(f"w{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(winners) == 1, f"exactly one claim must win, got {winners}"


def test_double_execute_is_idempotent(client, demo_auth):
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    first = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert first.status_code == 200, first.text
    assert first.json()["workflow"]["state"] == "COMPLETED"
    assert first.json()["replay"] is False
    second = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert second.status_code == 200
    assert second.json()["replay"] is True
    assert second.json()["workflow"]["state"] == "COMPLETED"
    # Still exactly one workspace: no duplicate effects.
    r = client.get("/api/v1/demo/identity/resources",
                   params={"org_id": demo_auth["org_id"], "kind": "workspace"},
                   headers=demo_auth["headers"])
    assert len(r.json()["resources"]) == 1


def test_reconcile_startup_marks_unknown(fresh_db, demo_auth):
    import datetime as dt
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        action = session.query(ActionRun).filter_by(workflow_id=wf.id).first()
        action.state = "EXECUTING"
        action.attempt = 1
        action.lease_owner = "dead-worker"
        action.lease_expires_at = utcnow() - dt.timedelta(seconds=60)
        session.commit()
        action_id = action.id
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["unknown"] == 1
    session = session_for("main")()
    try:
        assert session.get(ActionRun, action_id).state == "UNKNOWN_OUTCOME"
    finally:
        session.close()


def test_unknown_outcome_reconciles_to_failed_then_retries(client, demo_auth):
    """Chaos timeout -> UNKNOWN -> reconcile (absent) -> retry -> COMPLETED."""
    from .conftest import INTENT
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-crm",
                          "target_action": "crm.validate_customer",
                          "fault": "timeout", "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    body = r.json()
    wf_id = body["workflow"]["id"]
    client.post(f"/api/v1/workflows/{wf_id}/approve",
                json={"plan_hash": body["plan_hash"], "decided_by": "t"},
                headers=demo_auth["headers"])
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    r = client.get(f"/api/v1/workflows/{wf_id}/events", headers=demo_auth["headers"])
    types = [e["type"] for e in r.json()["data"]]
    assert "chaos.injected" in types
    states = [e["payload"].get("to") for e in r.json()["data"]
              if e["type"] == "action.state"]
    assert "UNKNOWN_OUTCOME" in states
    assert states.count("VERIFIED") == 10
