"""Engine unit tests: transitions, claims, idempotence, recovery."""

import json
import threading

import pytest

from reversa_api.db import session_for
from reversa_api.engine.saga import (
    VerificationOutcome,
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
from reversa_api.models import ActionRun, Organization, Workflow, utcnow


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


def _seed_action(session, wf_id: int, seq: int, state: str, key: str,
                 action_type: str = "identity.create_workspace",
                 connector_id: str = "demo-identity",
                 inputs: dict | None = None, output: dict | str | None = None,
                 attempt: int = 1, max_attempts: int = 3,
                 lease_owner: str = "dead-worker",
                 lease_expires_at=None, capability: str = "FULLY_REVERSIBLE",
                 error: str = "") -> ActionRun:
    action = ActionRun(
        workflow_id=wf_id, seq=seq, action_type=action_type,
        connector_id=connector_id, state=state,
        input_json=json.dumps(inputs if inputs is not None else {"org_slug": "acme"}),
        output_json=(output if isinstance(output, str)
                     else json.dumps(output if output is not None else {})),
        idempotency_key=key, attempt=attempt, max_attempts=max_attempts,
        lease_owner=lease_owner, lease_expires_at=lease_expires_at,
        compensation_capability=capability, depends_on="[]", error=error)
    session.add(action)
    session.flush()
    return action


def test_timeout_after_success_confirms_without_reexecution(fresh_db, demo_auth):
    """Timeout struck after the effect+output were durable (VERIFYING leftover).

    Resume must confirm PRESENT and never re-execute: exactly one effect,
    attempt counter untouched, workflow COMPLETED.
    """
    import datetime as dt

    from reversa_api.connectors.sdk import get_connector
    identity = get_connector("demo-identity")
    contract = identity.contract_for("identity.create_workspace")
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        # The effect really happened; only the confirmation was lost.
        output = identity.execute(
            {"org_id": demo_auth["org_id"], "is_demo": True,
             "workflow_id": wf.id, "idempotency_key": "k-succ-1"},
            contract, {"org_slug": "acme"})
        action = _seed_action(
            session, wf.id, seq=1, state="VERIFYING", key="k-succ-1",
            inputs={"org_slug": "acme"}, output=output,
            lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id, action_id = wf.id, action.id
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["verified"] == 1, stats
    assert stats["failed"] == 0, stats
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert final == "COMPLETED"
    session = session_for("main")()
    try:
        action = session.get(ActionRun, action_id)
        assert action.state == "VERIFIED"
        assert action.attempt == 1, "confirmed effects must never re-execute"
        assert len(identity.db.list(demo_auth["org_id"], kind="workspace")) == 1
    finally:
        session.close()


def test_unreadable_state_defers_reconciliation(fresh_db, demo_auth):
    """Corrupt stored JSON must defer (INDETERMINATE), never crash or retry.

    While the rows are corrupt the run honestly reports RUNNING; after the
    rows are repaired the same run resumes to COMPLETED.
    """
    from reversa_api.engine import saga as saga_mod
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        org = session.get(Organization, demo_auth["org_id"])
        a1 = _seed_action(session, wf.id, seq=1, state="UNKNOWN_OUTCOME",
                           key="k-unread-1", inputs={"org_slug": "ws-1"},
                           output="{corrupt!!!", error="CHAOS_TIMEOUT: simulated")
        a2 = _seed_action(session, wf.id, seq=2, state="VERIFYING",
                           key="k-unread-2", inputs={"org_slug": "ws-2"},
                           output="not json at all")
        session.commit()
        # Direct helper calls: must not raise, must stay put.
        assert saga_mod._reconcile_unknown(
            session, wf, org, session.get(ActionRun, a1.id), "w"
        ) is VerificationOutcome.INDETERMINATE
        assert session.get(ActionRun, a1.id).state == "UNKNOWN_OUTCOME"
        assert saga_mod._resume_interrupted_verification(
            session, wf, org, session.get(ActionRun, a2.id), "w"
        ) is VerificationOutcome.INDETERMINATE
        assert session.get(ActionRun, a2.id).state == "VERIFYING"
        wf_id = wf.id
    finally:
        session.close()
    # Startup path: same corrupt rows must defer, not crash.
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["deferred"] >= 1, stats
    assert stats["failed"] == 0, stats
    # The pump must not crash, fail, or retry on unreadable state.
    assert execute_workflow_sync(session_for("main"), wf_id, worker_id="w") == "RUNNING"
    session = session_for("main")()
    try:
        states = {a.seq: a.state for a in
                  session.query(ActionRun).filter_by(workflow_id=wf_id).all()}
        assert states == {1: "UNKNOWN_OUTCOME", 2: "VERIFYING"}, states
        for a in session.query(ActionRun).filter_by(workflow_id=wf_id).all():
            a.output_json = "{}"
        session.commit()
    finally:
        session.close()
    assert execute_workflow_sync(session_for("main"), wf_id, worker_id="w") == "COMPLETED"


def test_restart_resume_recovers_all_inflight_states(fresh_db, demo_auth):
    """Restart resume reconciles every in-flight state with verification.

    wfA (RUNNING): EXECUTING-stale -> UNKNOWN (lazy, pump-owned),
    SUCCEEDED-stale with a real effect -> VERIFIED without re-execution,
    VERIFYING-stale with no effect -> retry, pre-existing UNKNOWN untouched.
    wfB (COMPENSATING): COMPENSATING with the effect gone -> COMPENSATED,
    COMPENSATING with the effect present -> COMPENSATION_FAILED (retried).
    """
    import datetime as dt

    from reversa_api.connectors.sdk import get_connector
    identity = get_connector("demo-identity")
    contract = identity.contract_for("identity.create_workspace")
    stale = utcnow() - dt.timedelta(seconds=60)
    session = session_for("main")()
    try:
        wf_a = Workflow(org_id=demo_auth["org_id"], name="a", intent="a",
                        state="RUNNING", plan_json="{}", created_by="test")
        wf_b = Workflow(org_id=demo_auth["org_id"], name="b", intent="b",
                        state="COMPENSATING", plan_json="{}", created_by="test")
        session.add_all([wf_a, wf_b])
        session.flush()
        org_id = demo_auth["org_id"]

        def ctx(wf_id: int, key: str) -> dict:
            return {"org_id": org_id, "is_demo": True,
                    "workflow_id": wf_id, "idempotency_key": key}

        out_present = identity.execute(
            ctx(wf_a.id, "k-rs-2"), contract, {"org_slug": "ws-b"})
        out_gone = identity.execute(
            ctx(wf_b.id, "k-rs-5"), contract, {"org_slug": "ws-e"})
        identity.db.set_status(out_gone["resource"]["id"],
                               out_gone["resource"]["version"], "archived")
        out_still_there = identity.execute(
            ctx(wf_b.id, "k-rs-6"), contract, {"org_slug": "ws-f"})
        _seed_action(session, wf_a.id, seq=1, state="EXECUTING", key="k-rs-1",
                      inputs={"org_slug": "ws-a"}, lease_expires_at=stale)
        _seed_action(session, wf_a.id, seq=2, state="SUCCEEDED", key="k-rs-2",
                      inputs={"org_slug": "ws-b"}, output=out_present,
                      lease_expires_at=stale)
        _seed_action(session, wf_a.id, seq=3, state="VERIFYING", key="k-rs-3",
                      inputs={"org_slug": "ws-c"}, lease_expires_at=stale)
        _seed_action(session, wf_a.id, seq=4, state="UNKNOWN_OUTCOME",
                      key="k-rs-4", inputs={"org_slug": "ws-d"},
                      lease_expires_at=stale, error="CHAOS_CRASH: simulated")
        _seed_action(session, wf_b.id, seq=5, state="COMPENSATING", key="k-rs-5",
                      inputs={"org_slug": "ws-e"}, output=out_gone,
                      lease_expires_at=stale)
        _seed_action(session, wf_b.id, seq=6, state="COMPENSATING", key="k-rs-6",
                      inputs={"org_slug": "ws-f"}, output=out_still_there,
                      lease_expires_at=stale)
        session.commit()
        wf_a_id, wf_b_id = wf_a.id, wf_b.id
    finally:
        session.close()

    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["unknown"] == 1, stats
    assert stats["verified"] == 1, stats
    assert stats["failed"] == 1, stats
    assert stats["reconcile_pending"] == 2, stats  # seq1 fresh + seq4 pre-existing
    assert stats["compensated"] == 1, stats
    assert stats["comp_failed"] == 1, stats
    assert stats["deferred"] == 0, stats

    session = session_for("main")()
    try:
        by_id = {}
        for a in session.query(ActionRun).all():
            by_id[a.idempotency_key] = a.state
        assert by_id["k-rs-1"] == "UNKNOWN_OUTCOME", by_id
        assert by_id["k-rs-2"] == "VERIFIED", by_id
        assert by_id["k-rs-3"] == "RETRY_SCHEDULED", by_id
        assert by_id["k-rs-4"] == "UNKNOWN_OUTCOME", by_id
        assert by_id["k-rs-5"] == "COMPENSATED", by_id
        assert by_id["k-rs-6"] == "COMPENSATION_FAILED", by_id
    finally:
        session.close()

    assert execute_workflow_sync(session_for("main"), wf_a_id,
                                 worker_id="worker-2") == "COMPLETED"
    assert execute_workflow_sync(session_for("main"), wf_b_id,
                                 worker_id="worker-2") == "COMPENSATED"
    # Exactly-once per effect: the confirmed one never re-ran (attempt still
    # 1), the absent ones each materialized exactly one resource.
    session = session_for("main")()
    try:
        seq2 = session.query(ActionRun).filter_by(idempotency_key="k-rs-2").one()
        assert seq2.attempt == 1
        names = sorted(r["name"] for r in
                       identity.db.list(org_id, kind="workspace", status="active"))
        assert names == ["ws-a", "ws-b", "ws-c", "ws-d"], names
    finally:
        session.close()
