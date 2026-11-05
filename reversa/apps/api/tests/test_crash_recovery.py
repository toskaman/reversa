"""Crash-boundary tests: startup reconcile per-state behavior + resume route paths.

Covers the exact crash leftovers a restart can meet (P0-REC-02) and pins the
real recovery outcome for each, plus the POST /workflows/{id}/resume endpoint
paths (accepted workflow states, refusals, honest deferral). All assertions
are against observed DB/API state; nothing here re-executes blindly.
"""

import datetime as dt
import json

from reversa_api.connectors.sdk import get_connector
from reversa_api.db import session_for
from reversa_api.engine.saga import (
    execute_workflow_sync,
    reconcile_on_startup,
)
from reversa_api.models import ActionRun, Event, Workflow, utcnow


def _seed_wf(session, org_id: int, state: str = "RUNNING") -> Workflow:
    wf = Workflow(org_id=org_id, name="crash", intent="crash",
                  state=state, plan_json="{}", created_by="test")
    session.add(wf)
    session.flush()
    return wf


def _seed_action(session, wf_id: int, seq: int, state: str, key: str,
                 inputs: dict | None = None, output=None,
                 attempt: int = 1, lease_owner: str = "dead-worker",
                 lease_expires_at=None,
                 capability: str = "FULLY_REVERSIBLE",
                 error: str = "") -> ActionRun:
    action = ActionRun(
        workflow_id=wf_id, seq=seq, action_type="identity.create_workspace",
        connector_id="demo-identity", state=state,
        input_json=json.dumps(inputs if inputs is not None else {"org_slug": "acme"}),
        output_json=(output if isinstance(output, str)
                     else json.dumps(output if output is not None else {})),
        idempotency_key=key, attempt=attempt, max_attempts=3,
        lease_owner=lease_owner, lease_expires_at=lease_expires_at,
        compensation_capability=capability, depends_on="[]", error=error)
    session.add(action)
    session.flush()
    return action


def _real_workspace(org_id: int, wf_id: int, key: str, slug: str) -> dict:
    identity = get_connector("demo-identity")
    contract = identity.contract_for("identity.create_workspace")
    return identity.execute(
        {"org_id": org_id, "is_demo": True,
         "workflow_id": wf_id, "idempotency_key": key},
        contract, {"org_slug": slug})


def _state_of(key: str) -> str:
    session = session_for("main")()
    try:
        return session.query(ActionRun).filter_by(
            idempotency_key=key).one().state
    finally:
        session.close()


# ---- startup: CLAIMED ------------------------------------------------------

def test_startup_claimed_expired_requeues_and_runs(fresh_db, demo_auth):
    """CLAIMED + expired lease -> PENDING; the pump then claims and runs it."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed_action(session, wf.id, seq=1, state="CLAIMED",
                      key="k-crash-claimed", inputs={"org_slug": "ws-cl"},
                      attempt=0,
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["requeued"] == 1, stats
    assert _state_of("k-crash-claimed") == "PENDING"
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-crash-claimed").one()
        assert action.lease_owner == "", "requeue must release the dead owner"
    finally:
        session.close()
    assert execute_workflow_sync(session_for("main"), wf_id,
                                 worker_id="worker-2") == "COMPLETED"
    assert _state_of("k-crash-claimed") == "VERIFIED"


def test_startup_fresh_leases_untouched(fresh_db, demo_auth):
    """CLAIMED/EXECUTING with a live lease belong to a live worker: no steal."""
    fresh = utcnow() + dt.timedelta(seconds=600)
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed_action(session, wf.id, seq=1, state="CLAIMED",
                      key="k-crash-cl-live", inputs={"org_slug": "ws-cll"},
                      attempt=0, lease_owner="live-worker",
                      lease_expires_at=fresh)
        _seed_action(session, wf.id, seq=2, state="EXECUTING",
                      key="k-crash-ex-live", inputs={"org_slug": "ws-exl"},
                      lease_owner="live-worker", lease_expires_at=fresh)
        session.commit()
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["requeued"] == 0, stats
    assert stats["unknown"] == 0, stats
    assert stats["reconcile_pending"] == 0, stats
    assert _state_of("k-crash-cl-live") == "CLAIMED"
    assert _state_of("k-crash-ex-live") == "EXECUTING"
    session = session_for("main")()
    try:
        owners = {a.idempotency_key: a.lease_owner for a in
                  session.query(ActionRun).filter(
                      ActionRun.idempotency_key.in_(
                          ["k-crash-cl-live", "k-crash-ex-live"])).all()}
        assert owners == {"k-crash-cl-live": "live-worker",
                          "k-crash-ex-live": "live-worker"}, owners
    finally:
        session.close()


def test_startup_null_lease_claimed_executing_ignored(fresh_db, demo_auth):
    """CLAIMED/EXECUTING with NO lease row are invisible to startup recovery.

    The startup queries match `lease_expires_at < now`, which excludes NULL,
    so these rows stay put (contrast: VERIFYING/COMPENSATING treat a missing
    lease as stale via _lease_is_stale). Pinned as observed behavior.
    """
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed_action(session, wf.id, seq=1, state="CLAIMED",
                      key="k-crash-cl-null", inputs={"org_slug": "ws-cln"},
                      attempt=0, lease_owner="", lease_expires_at=None)
        _seed_action(session, wf.id, seq=2, state="EXECUTING",
                      key="k-crash-ex-null", inputs={"org_slug": "ws-exn"},
                      lease_owner="", lease_expires_at=None)
        session.commit()
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["requeued"] == 0, stats
    assert stats["unknown"] == 0, stats
    assert _state_of("k-crash-cl-null") == "CLAIMED"
    assert _state_of("k-crash-ex-null") == "EXECUTING"


# ---- startup: EXECUTING / VERIFYING / UNKNOWN / COMPENSATING ---------------

def test_startup_executing_expired_becomes_unknown(fresh_db, demo_auth):
    """EXECUTING + expired lease -> UNKNOWN_OUTCOME, journaled, pending."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed_action(session, wf.id, seq=1, state="EXECUTING",
                      key="k-crash-exec", inputs={"org_slug": "ws-ex"},
                      lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["unknown"] == 1, stats
    assert stats["reconcile_pending"] == 1, stats
    assert _state_of("k-crash-exec") == "UNKNOWN_OUTCOME"
    session = session_for("main")()
    try:
        trail = [json.loads(e.payload_json).get("to") for e in
                 session.query(Event).filter_by(
                     workflow_id=wf_id, type="action.state").all()]
        assert trail == ["UNKNOWN_OUTCOME"], trail
    finally:
        session.close()


def test_startup_verifying_null_lease_counts_as_stale(fresh_db, demo_auth):
    """VERIFYING with a missing lease is resumed (stale), never re-executed."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        session.flush()
        output = _real_workspace(
            demo_auth["org_id"], wf.id, "k-crash-vnull", "ws-vnull")
        _seed_action(session, wf.id, seq=1, state="VERIFYING",
                      key="k-crash-vnull", inputs={"org_slug": "ws-vnull"},
                      output=output, lease_owner="", lease_expires_at=None)
        session.commit()
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["verified"] == 1, stats
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-crash-vnull").one()
        assert action.state == "VERIFIED"
        assert action.attempt == 1, "confirmed effects must never re-execute"
    finally:
        session.close()


def test_startup_verifying_fresh_lease_is_live(fresh_db, demo_auth):
    """VERIFYING with a live lease is left for its owner (counted live)."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed_action(session, wf.id, seq=1, state="VERIFYING",
                      key="k-crash-vlive", inputs={"org_slug": "ws-vl"},
                      lease_owner="live-worker",
                      lease_expires_at=utcnow() + dt.timedelta(seconds=600))
        session.commit()
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["live"] == 1, stats
    assert stats["verified"] == 0, stats
    assert stats["failed"] == 0, stats
    assert _state_of("k-crash-vlive") == "VERIFYING"


def test_startup_unknown_left_for_pump_never_forced(fresh_db, demo_auth):
    """UNKNOWN_OUTCOME at startup is counted pending, never force-resolved."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        action = _seed_action(
            session, wf.id, seq=1, state="UNKNOWN_OUTCOME",
            key="k-crash-unk", inputs={"org_slug": "ws-unk"},
            lease_expires_at=utcnow() - dt.timedelta(seconds=60))
        action.error = "CHAOS_CRASH: simulated"
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["reconcile_pending"] == 1, stats
    assert stats["failed"] == 0, stats
    assert stats["verified"] == 0, stats
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key="k-crash-unk").one()
        assert action.state == "UNKNOWN_OUTCOME"
        assert action.error == "CHAOS_CRASH: simulated"
        deferred = session.query(Event).filter_by(
            workflow_id=wf_id, type="action.reconcile_deferred").all()
        assert deferred == [], "startup must not emit resume backoff events"
    finally:
        session.close()


def test_startup_compensating_fresh_lease_is_live(fresh_db, demo_auth):
    """COMPENSATING with a live lease is left for its owner (counted live)."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"], state="COMPENSATING")
        _seed_action(session, wf.id, seq=1, state="COMPENSATING",
                      key="k-crash-clive", inputs={"org_slug": "ws-cpl"},
                      lease_owner="live-worker",
                      lease_expires_at=utcnow() + dt.timedelta(seconds=600))
        session.commit()
    finally:
        session.close()
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["live"] == 1, stats
    assert stats["compensated"] == 0, stats
    assert stats["comp_failed"] == 0, stats
    assert _state_of("k-crash-clive") == "COMPENSATING"


# ---- resume endpoint paths -------------------------------------------------

def test_resume_route_accepts_retrying(client, demo_auth):
    """POST resume on a RETRYING workflow runs it to completion."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"], state="RETRYING")
        _seed_action(session, wf.id, seq=1, state="PENDING",
                      key="k-crash-rt", inputs={"org_slug": "ws-rt"},
                      attempt=1, lease_owner="", lease_expires_at=None)
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "COMPLETED", body
    assert body["terminal"] is True
    assert body["actions"][0]["state"] == "VERIFIED"


def test_resume_route_recovers_workflow_level_verifying(client, demo_auth):
    """Crash between the two final-check commits: wf VERIFYING, all done."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"], state="VERIFYING")
        action = _seed_action(session, wf.id, seq=1, state="VERIFIED",
                               key="k-crash-wfv", inputs={"org_slug": "ws-wfv"},
                               lease_owner="", lease_expires_at=None)
        action.output_json = json.dumps({"resource": {"id": 1}})
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "COMPLETED", body
    assert body["terminal"] is True
    session = session_for("main")()
    try:
        notes = [json.loads(e.payload_json).get("note") for e in
                 session.query(Event).filter_by(
                     workflow_id=wf_id, type="workflow.state").all()]
        assert any("final check recovered" in (n or "") for n in notes), notes
    finally:
        session.close()


def test_resume_route_recovers_compensating(client, demo_auth):
    """POST resume on COMPENSATING drains queued undos via the route."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"], state="COMPENSATING")
        session.flush()
        output = _real_workspace(
            demo_auth["org_id"], wf.id, "k-crash-cp", "ws-cp")
        action = _seed_action(session, wf.id, seq=1,
                               state="COMPENSATION_PENDING",
                               key="k-crash-cp", inputs={"org_slug": "ws-cp"},
                               output=output,
                               lease_owner="", lease_expires_at=None)
        action.attempt = 1
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "COMPENSATED", body
    assert body["terminal"] is True
    assert body["actions"][0]["state"] == "COMPENSATED"
    identity = get_connector("demo-identity")
    assert identity.db.list(
        demo_auth["org_id"], kind="workspace", status="active") == []


def test_resume_route_defers_unknown_honestly(client, demo_auth):
    """RUNNING + corrupt UNKNOWN via route: 200, still RUNNING, never forced."""
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        action = _seed_action(session, wf.id, seq=1, state="UNKNOWN_OUTCOME",
                               key="k-crash-runk", inputs={"org_slug": "ws-runk"},
                               output="{corrupt!!!",
                               error="CHAOS_TIMEOUT: simulated",
                               lease_expires_at=(
                                   utcnow() - dt.timedelta(seconds=60)))
        session.commit()
        wf_id = wf.id
        assert action.id is not None
    finally:
        session.close()
    r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "RUNNING", body
    assert body["terminal"] is False
    assert body["actions"][0]["state"] == "UNKNOWN_OUTCOME"
    assert body["resume"]["reconcile_pending"] == 1, body
    assert body["resume"]["deferred"] >= 1, body
    session = session_for("main")()
    try:
        deferred = session.query(Event).filter_by(
            workflow_id=wf_id, type="action.reconcile_deferred").all()
        assert len(deferred) >= 1
        assert json.loads(deferred[0].payload_json)["wait_s"] > 0
    finally:
        session.close()


def test_resume_route_refusals(client, demo_auth, real_auth):
    """Resume refuses non-interrupted states (409) and strangers (404)."""
    session = session_for("main")()
    try:
        wf_failed = _seed_wf(session, demo_auth["org_id"], state="FAILED")
        wf_cancelled = _seed_wf(session, demo_auth["org_id"], state="CANCELLED")
        wf_manual = _seed_wf(session, demo_auth["org_id"],
                              state="MANUAL_REQUIRED")
        wf_partial = _seed_wf(session, demo_auth["org_id"],
                               state="PARTIALLY_COMPENSATED")
        wf_running = _seed_wf(session, demo_auth["org_id"], state="RUNNING")
        _seed_action(session, wf_running.id, seq=1, state="PENDING",
                      key="k-crash-xicon", inputs={"org_slug": "ws-xi"},
                      attempt=0, lease_owner="", lease_expires_at=None)
        session.commit()
        ids = [wf_failed.id, wf_cancelled.id, wf_manual.id, wf_partial.id]
        running_id = wf_running.id
    finally:
        session.close()
    for wf_id in ids:
        r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                        headers=demo_auth["headers"])
        assert r.status_code == 409, (wf_id, r.text)
    r = client.post("/api/v1/workflows/999999/resume",
                    headers=demo_auth["headers"])
    assert r.status_code == 404, r.text
    r = client.post(f"/api/v1/workflows/{running_id}/resume",
                    headers=real_auth["headers"])
    assert r.status_code == 404, r.text
