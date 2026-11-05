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
    resume_workflow_sync,
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


def test_verifying_to_unknown_outcome_allowed():
    """VERIFYING -> UNKNOWN_OUTCOME is allowlisted (uncertain verification)."""
    check_action_transition("VERIFYING", "UNKNOWN_OUTCOME")
    check_action_transition("UNKNOWN_OUTCOME", "VERIFYING")
    check_action_transition("VERIFYING", "VERIFIED")
    with pytest.raises(InvalidTransition):
        check_action_transition("VERIFYING", "PENDING")


def test_resume_claimed_stale_requeues_and_completes(fresh_db, demo_auth):
    import datetime as dt
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        _seed_action(session, wf.id, seq=1, state="CLAIMED", key="k-rv-claimed",
                      inputs={"org_slug": "ws-claimed"},
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "COMPLETED", result
    assert result["stats"]["requeued"] == 1, result
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-rv-claimed").one()
        assert action.state == "VERIFIED"
    finally:
        session.close()


def test_resume_executing_stale_recovers_via_unknown(fresh_db, demo_auth):
    import datetime as dt
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        _seed_action(session, wf.id, seq=1, state="EXECUTING", key="k-rv-exec",
                      inputs={"org_slug": "ws-exec"},
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "COMPLETED", result
    assert result["stats"]["unknown"] == 1, result
    assert result["stats"]["failed"] == 1, result
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-rv-exec").one()
        assert action.state == "VERIFIED"
    finally:
        session.close()


def test_resume_succeeded_with_effect_confirms_without_reexecution(
        fresh_db, demo_auth):
    """SUCCEEDED-stale with a real effect -> VERIFIED, attempt untouched."""
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
        output = identity.execute(
            {"org_id": demo_auth["org_id"], "is_demo": True,
             "workflow_id": wf.id, "idempotency_key": "k-rv-succ"},
            contract, {"org_slug": "ws-succ"})
        _seed_action(session, wf.id, seq=1, state="SUCCEEDED", key="k-rv-succ",
                      inputs={"org_slug": "ws-succ"}, output=output,
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "COMPLETED", result
    assert result["stats"]["verified"] == 1, result
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-rv-succ").one()
        assert action.state == "VERIFIED"
        assert action.attempt == 1, "confirmed effects must never re-execute"
        assert len(identity.db.list(demo_auth["org_id"], kind="workspace")) == 1
    finally:
        session.close()


def test_resume_verifying_absent_retries_to_completed(fresh_db, demo_auth):
    import datetime as dt
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        _seed_action(session, wf.id, seq=1, state="VERIFYING", key="k-rv-verify",
                      inputs={"org_slug": "ws-verify"},
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "COMPLETED", result
    assert result["stats"]["failed"] == 1, result
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-rv-verify").one()
        assert action.state == "VERIFIED"
    finally:
        session.close()


def test_resume_unknown_indeterminate_defers_with_backoff(fresh_db, demo_auth):
    """Stale UNKNOWN with unreadable state defers with backoff, never forced.

    While corrupt the resume honestly reports RUNNING with the action still
    UNKNOWN_OUTCOME; after repair the same resume completes the workflow.
    """
    import datetime as dt

    from reversa_api.models import Event
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        _seed_action(session, wf.id, seq=1, state="UNKNOWN_OUTCOME",
                      key="k-rv-unk", inputs={"org_slug": "ws-unk"},
                      output="{corrupt!!!", error="CHAOS_TIMEOUT: simulated",
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "RUNNING", result
    assert result["stats"]["deferred"] >= 1, result
    assert result["stats"]["reconcile_pending"] == 1, result
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-rv-unk").one()
        assert action.state == "UNKNOWN_OUTCOME", "never force-resolved"
        deferred = session.query(Event).filter_by(
            workflow_id=wf_id, type="action.reconcile_deferred").all()
        assert len(deferred) >= 1, "stale UNKNOWN must log a backoff event"
        payload = json.loads(deferred[0].payload_json)
        assert payload["wait_s"] > 0, payload
        action.output_json = "{}"
        session.commit()
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "COMPLETED", result


def test_resume_compensating_states_recover(fresh_db, demo_auth):
    """COMPENSATING-stale: gone -> COMPENSATED, present -> failed then undone."""
    import datetime as dt

    from reversa_api.connectors.sdk import get_connector
    identity = get_connector("demo-identity")
    contract = identity.contract_for("identity.create_workspace")
    stale = utcnow() - dt.timedelta(seconds=60)
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="b", intent="b",
                      state="COMPENSATING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()

        def ctx(key: str) -> dict:
            return {"org_id": demo_auth["org_id"], "is_demo": True,
                    "workflow_id": wf.id, "idempotency_key": key}

        out_gone = identity.execute(
            ctx("k-rv-c5"), contract, {"org_slug": "ws-rv-e"})
        identity.db.set_status(out_gone["resource"]["id"],
                               out_gone["resource"]["version"], "archived")
        out_present = identity.execute(
            ctx("k-rv-c6"), contract, {"org_slug": "ws-rv-f"})
        _seed_action(session, wf.id, seq=5, state="COMPENSATING", key="k-rv-c5",
                      inputs={"org_slug": "ws-rv-e"}, output=out_gone,
                      lease_expires_at=stale)
        _seed_action(session, wf.id, seq=6, state="COMPENSATING", key="k-rv-c6",
                      inputs={"org_slug": "ws-rv-f"}, output=out_present,
                      lease_expires_at=stale)
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "COMPENSATED", result
    assert result["stats"]["compensated"] == 1, result
    assert result["stats"]["comp_failed"] == 1, result


def test_resume_live_lease_untouched(fresh_db, demo_auth):
    """Fresh leases are never stolen by resume (counted as live)."""
    import datetime as dt
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        _seed_action(session, wf.id, seq=1, state="VERIFYING", key="k-rv-live",
                      inputs={"org_slug": "ws-live"},
                      lease_owner="live-worker",
                      lease_expires_at=utcnow() + dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    result = resume_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert result["state"] == "RUNNING", result
    assert result["stats"]["live"] == 1, result
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-rv-live").one()
        assert action.state == "VERIFYING"
        assert action.lease_owner == "live-worker"
    finally:
        session.close()


def test_resume_route_recovers_interrupted_workflow(client, demo_auth):
    import datetime as dt
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        _seed_action(session, wf.id, seq=1, state="CLAIMED", key="k-rv-route",
                      inputs={"org_slug": "ws-route"},
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "COMPLETED", body
    assert body["resume"]["requeued"] == 1, body
    assert body["terminal"] is True
    assert body["actions"][0]["state"] == "VERIFIED"


def test_resume_route_rejects_terminal_and_ready(client, demo_auth):
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    # READY has nothing to resume: use execute, not resume.
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 409, r.text
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED"
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 409, r.text


def _seed_chaos_rule(session, org_id: int, connector: str, fault: str,
                     target_action: str = "", times: int = 1):
    from reversa_api.models import ChaosRule
    rule = ChaosRule(org_id=org_id, target_connector=connector,
                     target_action=target_action, fault=fault,
                     times_remaining=times, enabled=1)
    session.add(rule)
    session.flush()
    return rule


def test_chaos_earlier_mismatch_does_not_shadow_later_match(
        fresh_db, demo_auth):
    """F3: a lower-id rule for another action must not shadow a match.

    Rule 1 (older): demo-crm/crm.create_organization http500.
    Rule 2 (newer): demo-crm/crm.validate_customer malformed.
    Firing for validate_customer must raise the malformed fault, consume
    only rule 2, and leave rule 1's budget untouched.
    """
    from reversa_api.connectors.sdk import ChaosTriggered
    from reversa_api.engine import saga as saga_mod
    from reversa_api.models import Event
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        org = session.get(Organization, demo_auth["org_id"])
        action = _seed_action(
            session, wf.id, seq=1, state="PENDING", key="k-f3-shadow",
            action_type="crm.validate_customer", connector_id="demo-crm",
            inputs={"customer_name": "x"})
        decoy = _seed_chaos_rule(session, demo_auth["org_id"], "demo-crm",
                                 "http500",
                                 target_action="crm.create_organization")
        match = _seed_chaos_rule(session, demo_auth["org_id"], "demo-crm",
                                 "malformed",
                                 target_action="crm.validate_customer")
        session.commit()
        assert decoy.id < match.id
        with pytest.raises(ChaosTriggered) as exc_info:
            saga_mod._consume_chaos(
                session, wf, org, session.get(ActionRun, action.id), "w")
        assert exc_info.value.code == "CHAOS_MALFORMED", exc_info.value.code
        assert decoy.times_remaining == 1, "mismatch must consume no budget"
        assert match.times_remaining == 0
        injected = session.query(Event).filter_by(
            workflow_id=wf.id, type="chaos.injected").all()
        assert len(injected) == 1
        assert json.loads(injected[0].payload_json)["fault"] == "malformed"
    finally:
        session.close()


def test_chaos_matching_precedence_is_lowest_id(fresh_db, demo_auth):
    """F3: when several rules match, the lowest-id (oldest) fires.

    Rule 1 (older): demo-crm wildcard "" http500.
    Rule 2 (newer): demo-crm/crm.validate_customer malformed.
    Both match validate_customer, so rule 1 fires and only rule 1 pays.
    """
    from reversa_api.connectors.sdk import ChaosTriggered
    from reversa_api.engine import saga as saga_mod
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        org = session.get(Organization, demo_auth["org_id"])
        action = _seed_action(
            session, wf.id, seq=1, state="PENDING", key="k-f3-precedence",
            action_type="crm.validate_customer", connector_id="demo-crm",
            inputs={"customer_name": "x"})
        first = _seed_chaos_rule(session, demo_auth["org_id"], "demo-crm",
                                 "http500")
        second = _seed_chaos_rule(session, demo_auth["org_id"], "demo-crm",
                                  "malformed",
                                  target_action="crm.validate_customer")
        session.commit()
        assert first.id < second.id
        with pytest.raises(ChaosTriggered) as exc_info:
            saga_mod._consume_chaos(
                session, wf, org, session.get(ActionRun, action.id), "w")
        assert exc_info.value.code == "CHAOS_HTTP500", exc_info.value.code
        assert first.times_remaining == 0
        assert second.times_remaining == 1
    finally:
        session.close()


def test_raising_verify_defers_indeterminate_end_to_end(
        fresh_db, demo_auth, monkeypatch):
    """A raising verifier must defer (INDETERMINATE), never fail or retry.

    Engine-level end-to-end mirror of the route-level verifier-outage
    test: while verify raises (ConnectorError for seq 1, a raw crash for
    seq 2), UNKNOWN_OUTCOME and VERIFYING actions stay put through direct
    reconciliation, startup recovery, and the forward pump (RUNNING,
    attempts untouched); after the verifier recovers the run completes.
    """
    import datetime as dt

    from reversa_api.connectors.sdk import ConnectorError, get_connector
    from reversa_api.engine import saga as saga_mod
    from reversa_api.models import Event

    identity = get_connector("demo-identity")
    real_verify = identity.verify

    def down_verify(ctx, contract, inputs, output):
        if inputs.get("org_slug") == "ws-r1":
            raise ConnectorError("VERIFY_TIMEOUT", "simulated verifier outage",
                                 retryable=True)
        raise RuntimeError("simulated verifier crash")

    monkeypatch.setattr(identity, "verify", down_verify)
    stale = utcnow() - dt.timedelta(seconds=60)
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        org = session.get(Organization, demo_auth["org_id"])
        a1 = _seed_action(session, wf.id, seq=1, state="UNKNOWN_OUTCOME",
                           key="k-raise-1", inputs={"org_slug": "ws-r1"},
                           output={}, error="CHAOS_TIMEOUT: simulated",
                           lease_expires_at=stale)
        a2 = _seed_action(session, wf.id, seq=2, state="VERIFYING",
                           key="k-raise-2", inputs={"org_slug": "ws-r2"},
                           output={}, lease_expires_at=stale)
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
        attempts_before = {a.seq: a.attempt for a in
                           session.query(ActionRun).filter_by(
                               workflow_id=wf.id).all()}
        wf_id = wf.id
    finally:
        session.close()
    # Startup path: same raising verifier must defer, not crash.
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["deferred"] >= 1, stats
    assert stats["failed"] == 0, stats
    # The pump must not crash, fail, or retry on a raising verifier.
    assert execute_workflow_sync(session_for("main"), wf_id, worker_id="w") == "RUNNING"
    session = session_for("main")()
    try:
        states = {a.seq: a.state for a in
                  session.query(ActionRun).filter_by(workflow_id=wf_id).all()}
        assert states == {1: "UNKNOWN_OUTCOME", 2: "VERIFYING"}, states
        attempts_after = {a.seq: a.attempt for a in
                          session.query(ActionRun).filter_by(
                              workflow_id=wf_id).all()}
        assert attempts_after == attempts_before, "deferred work never re-runs"
        types = [e.type for e in session.query(Event).filter_by(
            workflow_id=wf_id).all()]
        assert "action.reconcile_indeterminate" in types, types
        assert "action.verify_indeterminate" in types, types
    finally:
        session.close()
    # Verifier recovers: absent effects retry idempotently to COMPLETED.
    monkeypatch.setattr(identity, "verify", real_verify)
    assert execute_workflow_sync(session_for("main"), wf_id, worker_id="w") == "COMPLETED"


def test_chaos_disabled_exhausted_and_foreign_rules_do_not_shadow(
        fresh_db, demo_auth):
    """F3: only live rules for this connector+action compete.

    Older decoys — disabled, budget-exhausted, and other-connector —
    must all be skipped; the live match fires, pays the only budget,
    and journals exactly one chaos.injected event.
    """
    from reversa_api.connectors.sdk import ChaosTriggered
    from reversa_api.engine import saga as saga_mod
    from reversa_api.models import Event
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="t", intent="t",
                      state="RUNNING", plan_json="{}", created_by="test")
        session.add(wf)
        session.flush()
        org = session.get(Organization, demo_auth["org_id"])
        action = _seed_action(
            session, wf.id, seq=1, state="PENDING", key="k-f3-live",
            action_type="crm.validate_customer", connector_id="demo-crm",
            inputs={"customer_name": "x"})
        disabled = _seed_chaos_rule(session, demo_auth["org_id"], "demo-crm",
                                    "http500",
                                    target_action="crm.validate_customer")
        disabled.enabled = 0
        exhausted = _seed_chaos_rule(session, demo_auth["org_id"], "demo-crm",
                                     "http429",
                                     target_action="crm.validate_customer",
                                     times=0)
        foreign = _seed_chaos_rule(session, demo_auth["org_id"], "demo-identity",
                                   "crash",
                                   target_action="crm.validate_customer")
        match = _seed_chaos_rule(session, demo_auth["org_id"], "demo-crm",
                                 "malformed",
                                 target_action="crm.validate_customer")
        session.commit()
        assert disabled.id < exhausted.id < foreign.id < match.id
        with pytest.raises(ChaosTriggered) as exc_info:
            saga_mod._consume_chaos(
                session, wf, org, session.get(ActionRun, action.id), "w")
        assert exc_info.value.code == "CHAOS_MALFORMED", exc_info.value.code
        assert (disabled.times_remaining, disabled.enabled) == (1, 0)
        assert exhausted.times_remaining == 0, "spent rule stays spent"
        assert foreign.times_remaining == 1, "other connector untouched"
        assert match.times_remaining == 0
        injected = session.query(Event).filter_by(
            workflow_id=wf.id, type="chaos.injected").all()
        assert len(injected) == 1
        assert json.loads(injected[0].payload_json)["fault"] == "malformed"
    finally:
        session.close()
