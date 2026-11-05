"""Chaos Matrix V2 cycle 4 (FINAL): CM-04, CM-03, CM-05, CM-10, CM-09 (cycle 2)
+ CM-11, CM-13, CM-15 (cycle 3) + CM-14, CM-06, CM-07, CM-16, CM-12, CM-17,
CM-18 (cycle 4). Covered: 20/20.

Spec: docs/benchmarks/chaos-matrix-v2.md (priority order). Each test asserts
real terminal states, action states, journaled events, and demo resources --
never bare status codes alone.
"""

from .conftest import make_ready


def _transitions(events: list, action_type: str) -> list:
    return [e["payload"].get("to") for e in events
            if e["type"] == "action.state"
            and e["payload"].get("action_type") == action_type]


def _types(events: list) -> list:
    return [e["type"] for e in events]


def _events(client, demo_auth, wf_id) -> list:
    r = client.get(f"/api/v1/workflows/{wf_id}/events", params={"limit": 1000},
                   headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _resources(client, demo_auth, service, kind=None, status=None) -> list:
    params = {}
    if kind is not None:
        params["kind"] = kind
    if status is not None:
        params["status"] = status
    r = client.get(f"/api/v1/demo/{service}/resources", params=params,
                   headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    return r.json()["resources"]


def test_cm04_malformed_fails_fast_no_retry(client, demo_auth):
    """CM-04: malformed x1 on demo-billing -> COMPENSATED, FAILED, no retry."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing", "fault": "malformed",
                          "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[6]["state"] == "FAILED", by_seq
    assert by_seq[6]["action_type"] == "billing.create_profile"
    assert by_seq[6]["attempt"] == 1  # fail fast: single attempt, no retry
    assert "CHAOS_MALFORMED" in by_seq[6]["error"], by_seq[6]["error"]
    # Billing dies on first attempt, so dependents never run; completed work undone.
    assert all(by_seq[s]["state"] == "COMPENSATED" for s in (1, 2, 3, 4, 5)), by_seq
    assert all(by_seq[s]["state"] == "SKIPPED" for s in (7, 8, 9, 10)), by_seq

    events = _events(client, demo_auth, wf_id)
    trail = _transitions(events, "billing.create_profile")
    assert "RETRY_SCHEDULED" not in trail, trail  # non-retryable: never scheduled
    assert "action.retry_wait" not in _types(events)
    assert "chaos.injected" in _types(events)

    # Resources actually restored: workspace hard-deleted, users/org archived.
    assert _resources(client, demo_auth, "identity", kind="workspace") == []
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="archived")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="archived")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm03_rate_limit_retries_then_compensates(client, demo_auth):
    """CM-03: http429 x5 on demo-billing -> retries with backoff, COMPENSATED."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing", "fault": "http429",
                          "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[6]["state"] == "FAILED", by_seq
    assert by_seq[6]["attempt"] == by_seq[6]["max_attempts"] == 2  # retries exhausted
    assert "CHAOS_HTTP429" in by_seq[6]["error"], by_seq[6]["error"]
    # Independent branches (7, 8) ran during the retry wait, then all undone.
    assert all(by_seq[s]["state"] == "COMPENSATED"
               for s in (1, 2, 3, 4, 5, 7, 8)), by_seq
    assert all(by_seq[s]["state"] == "SKIPPED" for s in (9, 10)), by_seq

    events = _events(client, demo_auth, wf_id)
    trail = _transitions(events, "billing.create_profile")
    assert "RETRY_SCHEDULED" in trail, trail  # retryable: scheduled
    waits = [e for e in events if e["type"] == "action.retry_wait"]
    assert len(waits) >= 1  # backoff actually waited between attempts
    assert all(w["payload"]["seq"] == 6 for w in waits)
    assert "chaos.injected" in _types(events)

    assert _resources(client, demo_auth, "identity", kind="workspace") == []
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="archived")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="archived")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm05_worker_crash_reconciles_to_completed(client, demo_auth):
    """CM-05: crash x1 on validate_customer -> UNKNOWN_OUTCOME -> COMPLETED.

    Distinct from the CM-01 sibling crash test: pins the CHAOS_CRASH code in
    the journal and verifies all 10 actions plus live resources.
    """
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-crm",
                          "target_action": "crm.validate_customer",
                          "fault": "crash", "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    by_seq = {a["seq"]: a["state"] for a in r.json()["actions"]}
    assert all(by_seq[s] == "VERIFIED" for s in range(1, 11)), by_seq

    events = _events(client, demo_auth, wf_id)
    trail = _transitions(events, "crm.validate_customer")
    assert "UNKNOWN_OUTCOME" in trail, trail
    assert trail.count("EXECUTING") == 2, trail  # one uncertain + one retry
    assert trail[-1] == "VERIFIED", trail
    notes = [e["payload"].get("note", "") for e in events
             if e["type"] == "action.state"
             and e["payload"].get("action_type") == "crm.validate_customer"]
    assert any("CHAOS_CRASH" in n for n in notes), notes  # distinct crash code
    assert "chaos.injected" in _types(events)

    # Real effects present: workspace live, users live, org live.
    assert len(_resources(client, demo_auth, "identity", kind="workspace")) == 1
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="active")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="active")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm10_chaos_input_validation(client, demo_auth):
    """CM-10: unknown fault / connector / bad times -> 422, nothing stored."""
    h = demo_auth["headers"]
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing", "fault": "nonsense"},
                    headers=h)
    assert r.status_code == 422, r.text
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-missing", "fault": "http500"},
                    headers=h)
    assert r.status_code == 422, r.text
    for bad_times in (0, 11):
        r = client.post("/api/v1/demo/chaos",
                        json={"target_connector": "demo-billing",
                              "fault": "http500", "times": bad_times},
                        headers=h)
        assert r.status_code == 422, (bad_times, r.text)
    # All rejected: no rule rows persisted.
    r = client.get("/api/v1/demo/chaos", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


def test_cm09_chaos_rule_lifecycle(client, demo_auth):
    """CM-09: POST -> GET lists -> DELETE -> GET empty; unknown DELETE -> 404."""
    h = demo_auth["headers"]
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "target_action": "billing.create_profile",
                          "fault": "http500", "times": 3},
                    headers=h)
    assert r.status_code == 201, r.text
    rule_id = r.json()["id"]

    r = client.get("/api/v1/demo/chaos", headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 1, rows
    assert rows[0]["id"] == rule_id
    assert rows[0]["target_connector"] == "demo-billing"
    assert rows[0]["target_action"] == "billing.create_profile"
    assert rows[0]["fault"] == "http500"
    assert rows[0]["times_remaining"] == 3

    r = client.delete(f"/api/v1/demo/chaos/{rule_id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == rule_id

    r = client.get("/api/v1/demo/chaos", headers=h)
    assert r.json()["data"] == []

    r = client.delete("/api/v1/demo/chaos/999999", headers=h)
    assert r.status_code == 404, r.text


def test_cm11_action_scoping_and_times_budget(client, demo_auth):
    """CM-11: mismatch never fires/consumes; single-shot http500 -> COMPLETED.

    Rule targets demo-crm/crm.create_organization (seq 2) with times=1.
    Seq 1 (same connector, different action) must run clean without
    consuming budget; seq 2 fires once, retries, then succeeds.
    """
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-crm",
                          "target_action": "crm.create_organization",
                          "fault": "http500", "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    rule_id = r.json()["id"]
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    by_seq = {a["seq"]: a["state"] for a in r.json()["actions"]}
    assert all(by_seq[s] == "VERIFIED" for s in range(1, 11)), by_seq

    events = _events(client, demo_auth, wf_id)
    # Mismatch proof: seq 1 (same connector) never failed nor retried.
    trail1 = _transitions(events, "crm.validate_customer")
    assert "FAILED" not in trail1, trail1
    assert "RETRY_SCHEDULED" not in trail1, trail1
    assert trail1[-1] == "VERIFIED", trail1
    # Single-shot proof: seq 2 failed once, retried, then verified.
    trail2 = _transitions(events, "crm.create_organization")
    assert "FAILED" in trail2, trail2
    assert "RETRY_SCHEDULED" in trail2, trail2
    assert trail2[-1] == "VERIFIED", trail2

    # Chaos fired exactly once, on seq 2 only.
    injected = [e for e in events if e["type"] == "chaos.injected"]
    assert len(injected) == 1, injected
    assert injected[0]["payload"]["seq"] == 2, injected
    assert injected[0]["payload"]["fault"] == "http500"
    waits = [e for e in events if e["type"] == "action.retry_wait"]
    assert len(waits) >= 1
    assert all(w["payload"]["seq"] == 2 for w in waits)

    # Budget consumed exactly once: mismatch did not consume, shot did.
    r = client.get("/api/v1/demo/chaos", headers=demo_auth["headers"])
    rows = r.json()["data"]
    assert len(rows) == 1, rows
    assert rows[0]["id"] == rule_id
    assert rows[0]["times_remaining"] == 0, rows

    assert len(_resources(client, demo_auth, "identity", kind="workspace")) == 1
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="active")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="active")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm13_conditional_compensation_refused(client, demo_auth, monkeypatch):
    """CM-13: invoice_issued mid-run blocks billing undo -> PARTIALLY_COMPENSATED.

    Chaos fires forward-only (never inside compensation), so per the matrix
    observation #2 the blocked compensation is arranged via a direct store
    write: when seq 9 (core.consistency_check) fires, an external actor
    issues the invoice on the already-VERIFIED billing profile. Seq 9 then
    fails (max_attempts=1, no retry wait) and billing undo refuses x3.
    """
    from reversa_api.connectors.services import DemoStore
    from reversa_api.engine import saga as saga_mod

    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "reversa-core",
                          "fault": "http500", "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text

    real_consume = saga_mod._consume_chaos

    def mid_run_consume(session, wf, org, action, worker_id):
        if action.action_type == "core.consistency_check":
            store = DemoStore("billing")
            prof = store.get_by_name(org.id, "billing_profile", "acme",
                                     workflow_id=wf.id)
            if prof is not None:
                store.update_data(prof["id"], prof["version"],
                                  {"invoice_issued": True})
        return real_consume(session, wf, org, action, worker_id)

    monkeypatch.setattr(saga_mod, "_consume_chaos", mid_run_consume)
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "PARTIALLY_COMPENSATED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[9]["state"] == "FAILED", by_seq
    assert by_seq[9]["action_type"] == "core.consistency_check"
    assert by_seq[10]["state"] == "SKIPPED", by_seq
    assert by_seq[6]["state"] == "COMPENSATION_FAILED", by_seq
    assert "invoice already issued" in by_seq[6]["error"], by_seq[6]["error"]
    assert all(by_seq[s]["state"] == "COMPENSATED"
               for s in (1, 2, 3, 4, 5, 7, 8)), by_seq

    events = _events(client, demo_auth, wf_id)
    types = _types(events)
    assert "compensation.started" in types
    assert "workflow.manual_required" not in types
    trail_billing = _transitions(events, "billing.create_profile")
    assert "COMPENSATION_FAILED" in trail_billing, trail_billing
    wf_trail = [e["payload"].get("to") for e in events
                if e["type"] == "workflow.state"]
    assert wf_trail[-1] == "PARTIALLY_COMPENSATED", wf_trail

    # Billing profile still active with the invoice flag (undo refused).
    billing_active = _resources(client, demo_auth, "billing",
                                kind="billing_profile", status="active")
    assert len(billing_active) == 1, billing_active
    assert billing_active[0]["data"].get("invoice_issued") is True, billing_active
    assert _resources(client, demo_auth, "billing",
                      kind="billing_profile", status="cancelled") == []
    # Everything else restored.
    assert _resources(client, demo_auth, "identity", kind="workspace") == []
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="archived")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="archived")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm15_irreversible_step_forces_manual_path(client, demo_auth):
    """CM-15: notify VERIFIED then billing fails -> MANUAL_REQUIRED naming notify.

    Custom 2-step plan seeded via DB (the intents API only builds the
    10-step onboarding graph): seq 1 notify.send_summary (IRREVERSIBLE),
    seq 2 billing.create_profile failing via chaos x5.
    """
    import json
    import uuid

    from reversa_api.db import session_for
    from reversa_api.models import ActionRun, Workflow

    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "http500", "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text

    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="CM-15 irreversible",
                      intent="CM-15 custom plan", state="READY", plan_version=1,
                      plan_json=json.dumps({"goal": "CM-15", "steps": [
                          {"seq": 1, "action_type": "notify.send_summary",
                           "connector_id": "demo-notify"},
                          {"seq": 2, "action_type": "billing.create_profile",
                           "connector_id": "demo-billing"}]}),
                      created_by="test")
        session.add(wf)
        session.flush()
        session.add(ActionRun(
            workflow_id=wf.id, seq=1, action_type="notify.send_summary",
            connector_id="demo-notify", state="PENDING",
            input_json=json.dumps({"channel": "email",
                                   "message": "CM-15 irreversible"}),
            idempotency_key=f"k-cm15-1-{uuid.uuid4().hex}", max_attempts=3,
            compensation_capability="IRREVERSIBLE", depends_on="[]"))
        session.add(ActionRun(
            workflow_id=wf.id, seq=2, action_type="billing.create_profile",
            connector_id="demo-billing", state="PENDING",
            input_json=json.dumps({"org_slug": "acme", "plan": "enterprise"}),
            idempotency_key=f"k-cm15-2-{uuid.uuid4().hex}", max_attempts=2,
            compensation_capability="CONDITIONALLY_REVERSIBLE",
            depends_on="[1]"))
        session.commit()
        wf_id = wf.id
    finally:
        session.close()

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "MANUAL_REQUIRED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[1]["state"] == "VERIFIED", by_seq
    assert by_seq[1]["compensation_capability"] == "IRREVERSIBLE"
    assert by_seq[2]["state"] == "FAILED", by_seq
    assert by_seq[2]["attempt"] == 2, by_seq
    assert "CHAOS_HTTP500" in by_seq[2]["error"], by_seq[2]["error"]

    events = _events(client, demo_auth, wf_id)
    injected = [e for e in events if e["type"] == "chaos.injected"]
    assert len(injected) == 2, injected
    assert all(e["payload"]["seq"] == 2 for e in injected)
    manual_comp = [e for e in events if e["type"] == "compensation.manual_required"]
    assert len(manual_comp) == 1, manual_comp
    assert manual_comp[0]["payload"]["seq"] == 1
    assert manual_comp[0]["payload"]["action_type"] == "notify.send_summary"
    assert manual_comp[0]["payload"]["capability"] == "IRREVERSIBLE"
    wf_manual = [e for e in events if e["type"] == "workflow.manual_required"]
    assert len(wf_manual) == 1, wf_manual
    items = wf_manual[0]["payload"]["items"]
    assert len(items) == 1 and items[0]["action_type"] == "notify.send_summary", items
    assert items[0]["seq"] == 1
    states_seen = [e["payload"].get("to") for e in events
                   if e["type"] == "action.state"]
    assert "COMPENSATED" not in states_seen, states_seen

    notify_active = _resources(client, demo_auth, "notify",
                               kind="message", status="active")
    assert len(notify_active) == 1, notify_active
    assert notify_active[0]["data"].get("sent") is True, notify_active
    assert _resources(client, demo_auth, "billing", kind="billing_profile") == []

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm14_external_change_blocks_compensation_e2e(client, demo_auth, monkeypatch):
    """CM-14: external version-bump mid-run blocks undo -> PARTIALLY_COMPENSATED.

    E2E sibling of the store-level check
    (`test_chaos.py::test_concurrent_modification_blocks_compensation`): when
    billing fires, an external actor touches the already-VERIFIED CRM org
    (version bump). Billing then exhausts retries; the seq 2 undo refuses
    with a version conflict while everything else compensates.
    """
    from reversa_api.connectors.services import DemoStore
    from reversa_api.engine import saga as saga_mod

    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "http500", "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text

    real_consume = saga_mod._consume_chaos
    bumped = []

    def mid_run_consume(session, wf, org, action, worker_id):
        if action.action_type == "billing.create_profile" and not bumped:
            bumped.append(True)
            store = DemoStore("crm")
            org_row = store.get_by_name(org.id, "organization", "acme",
                                        workflow_id=wf.id)
            assert org_row is not None
            store.update_data(org_row["id"], org_row["version"],
                              {"external_audit": "touched mid-run"})
        return real_consume(session, wf, org, action, worker_id)

    monkeypatch.setattr(saga_mod, "_consume_chaos", mid_run_consume)
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "PARTIALLY_COMPENSATED", r.text
    assert bumped == [True]
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[6]["state"] == "FAILED", by_seq
    assert by_seq[6]["attempt"] == by_seq[6]["max_attempts"] == 2
    assert "CHAOS_HTTP500" in by_seq[6]["error"], by_seq[6]["error"]
    assert by_seq[2]["state"] == "COMPENSATION_FAILED", by_seq
    assert by_seq[2]["action_type"] == "crm.create_organization"
    assert "changed" in by_seq[2]["error"], by_seq[2]["error"]
    assert all(by_seq[s]["state"] == "COMPENSATED"
               for s in (1, 3, 4, 5, 7, 8)), by_seq
    assert all(by_seq[s]["state"] == "SKIPPED" for s in (9, 10)), by_seq

    events = _events(client, demo_auth, wf_id)
    types = _types(events)
    assert "compensation.started" in types
    assert "workflow.manual_required" not in types
    trail_crm = _transitions(events, "crm.create_organization")
    assert "COMPENSATION_FAILED" in trail_crm, trail_crm
    assert trail_crm.count("COMPENSATING") == 3, trail_crm  # bounded retry
    wf_trail = [e["payload"].get("to") for e in events
                if e["type"] == "workflow.state"]
    assert wf_trail[-1] == "PARTIALLY_COMPENSATED", wf_trail

    # Externally touched org still active with the audit flag (undo refused).
    org_active = _resources(client, demo_auth, "crm",
                            kind="organization", status="active")
    assert len(org_active) == 1, org_active
    assert org_active[0]["data"].get("external_audit") == "touched mid-run"
    assert _resources(client, demo_auth, "crm",
                      kind="organization", status="archived") == []
    # Everything else restored.
    assert _resources(client, demo_auth, "identity", kind="workspace") == []
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="archived")) == 4

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm06_latency_degrades_never_fails(client, demo_auth):
    """CM-06: latency x1 on demo-billing -> COMPLETED, delay tolerated."""
    import time

    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "latency", "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    start = time.monotonic()
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    elapsed = time.monotonic() - start
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    by_seq = {a["seq"]: a["state"] for a in r.json()["actions"]}
    assert all(by_seq[s] == "VERIFIED" for s in range(1, 11)), by_seq
    assert elapsed >= 1.9, elapsed  # the 2 s fault actually fired

    events = _events(client, demo_auth, wf_id)
    injected = [e for e in events if e["type"] == "chaos.injected"]
    assert len(injected) == 1, injected
    assert injected[0]["payload"]["fault"] == "latency"
    assert injected[0]["payload"]["seq"] == 6
    states_seen = [e["payload"].get("to") for e in events
                   if e["type"] == "action.state"]
    assert "FAILED" not in states_seen, states_seen
    assert "RETRY_SCHEDULED" not in states_seen, states_seen
    assert "action.retry_wait" not in _types(events)

    r = client.get("/api/v1/demo/chaos", headers=demo_auth["headers"])
    assert r.json()["data"][0]["times_remaining"] == 0

    assert len(_resources(client, demo_auth, "identity", kind="workspace")) == 1
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="active")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="active")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm07_early_step_failure_minimal_compensation(client, demo_auth):
    """CM-07: http500 x5 on seq 2 -> COMPENSATED; seq 1 undone, 3-10 SKIPPED."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-crm",
                          "target_action": "crm.create_organization",
                          "fault": "http500", "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[2]["state"] == "FAILED", by_seq
    assert by_seq[2]["attempt"] == by_seq[2]["max_attempts"] == 3
    assert "CHAOS_HTTP500" in by_seq[2]["error"], by_seq[2]["error"]
    assert by_seq[1]["state"] == "COMPENSATED", by_seq  # read-only noop undone
    assert all(by_seq[s]["state"] == "SKIPPED" for s in range(3, 11)), by_seq

    events = _events(client, demo_auth, wf_id)
    trail = _transitions(events, "crm.create_organization")
    assert "RETRY_SCHEDULED" in trail, trail
    injected = [e for e in events if e["type"] == "chaos.injected"]
    assert len(injected) == 3, injected  # one per attempt, budget of 5
    assert all(e["payload"]["seq"] == 2 for e in injected)
    waits = [e for e in events if e["type"] == "action.retry_wait"]
    assert len(waits) == 2, waits  # backoff between the 3 attempts
    comp_order = [e["payload"]["seq"] for e in events
                  if e["type"] == "action.state"
                  and e["payload"].get("to") == "COMPENSATED"]
    assert comp_order == [1], comp_order  # minimal: only seq 1 undone

    # Nothing was ever created downstream.
    assert _resources(client, demo_auth, "crm", kind="organization") == []
    assert _resources(client, demo_auth, "identity", kind="workspace") == []
    assert _resources(client, demo_auth, "identity", kind="user") == []

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm16_late_readonly_failure_compensates(client, demo_auth):
    """CM-16: http500 x5 on seq 9 (max_attempts=1) -> COMPENSATED, 10 SKIPPED."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "reversa-core",
                          "fault": "http500", "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[9]["state"] == "FAILED", by_seq
    assert by_seq[9]["action_type"] == "core.consistency_check"
    assert by_seq[9]["attempt"] == by_seq[9]["max_attempts"] == 1  # no retry
    assert "CHAOS_HTTP500" in by_seq[9]["error"], by_seq[9]["error"]
    assert by_seq[10]["state"] == "SKIPPED", by_seq  # summary never sent
    assert all(by_seq[s]["state"] == "COMPENSATED" for s in range(1, 9)), by_seq

    events = _events(client, demo_auth, wf_id)
    trail = _transitions(events, "core.consistency_check")
    assert "RETRY_SCHEDULED" not in trail, trail
    assert "action.retry_wait" not in _types(events)
    injected = [e for e in events if e["type"] == "chaos.injected"]
    assert len(injected) == 1, injected
    assert injected[0]["payload"]["seq"] == 9
    comp_order = [e["payload"]["seq"] for e in events
                  if e["type"] == "action.state"
                  and e["payload"].get("to") == "COMPENSATED"]
    assert comp_order == [8, 7, 6, 5, 4, 3, 2, 1], comp_order  # full reverse

    # Notify never fired; everything else restored.
    assert _resources(client, demo_auth, "notify", kind="message") == []
    assert _resources(client, demo_auth, "identity", kind="workspace") == []
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="archived")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="archived")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm12_flag_off_forbids_and_rules_are_org_scoped(client, demo_auth):
    """CM-12: REVERSA_CHAOS=0 -> 403, nothing stored; org-A rule vs org-B run."""
    import uuid

    from reversa_api.auth import hash_token
    from reversa_api.config import settings
    from reversa_api.db import session_for
    from reversa_api.models import ApiToken, Organization

    # Part 1: flag off forbids injection and listing, stores nothing.
    object.__setattr__(settings, "chaos_enabled", False)
    try:
        r = client.post("/api/v1/demo/chaos",
                        json={"target_connector": "demo-billing",
                              "fault": "http500"},
                        headers=demo_auth["headers"])
        assert r.status_code == 403, r.text
        r = client.get("/api/v1/demo/chaos", headers=demo_auth["headers"])
        assert r.status_code == 403, r.text
    finally:
        object.__setattr__(settings, "chaos_enabled", True)
    r = client.get("/api/v1/demo/chaos", headers=demo_auth["headers"])
    assert r.json()["data"] == []

    # Part 2: org-A rule never touches org-B's workflow.
    session = session_for("main")()
    try:
        org_b = Organization(slug=f"demo-b-{uuid.uuid4().hex[:8]}",
                             name="Test Demo B", is_demo=1)
        session.add(org_b)
        session.commit()
        session.refresh(org_b)
        token_b = f"rev_test_{uuid.uuid4().hex}"
        session.add(ApiToken(org_id=org_b.id, name="test-b",
                             token_hash=hash_token(token_b)))
        session.commit()
        auth_b = {"headers": {"Authorization": f"Bearer {token_b}"},
                  "org_id": org_b.id}
    finally:
        session.close()

    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "http500", "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text

    wf_b = make_ready(client, auth_b)["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_b}/execute", headers=auth_b["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    by_seq = {a["seq"]: a["state"] for a in r.json()["actions"]}
    assert all(by_seq[s] == "VERIFIED" for s in range(1, 11)), by_seq

    events_b = _events(client, auth_b, wf_b)
    assert "chaos.injected" not in _types(events_b), events_b

    # Org B sees no rules; org A's budget is untouched.
    r = client.get("/api/v1/demo/chaos", headers=auth_b["headers"])
    assert r.json()["data"] == []
    r = client.get("/api/v1/demo/chaos", headers=demo_auth["headers"])
    rows = r.json()["data"]
    assert len(rows) == 1 and rows[0]["times_remaining"] == 5, rows

    assert len(_resources(client, auth_b, "identity", kind="workspace")) == 1

    r = client.get(f"/api/v1/workflows/{wf_b}/evidence",
                   headers=auth_b["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm17_crash_mid_compensation_recovers_bounded(client, demo_auth):
    """CM-17: COMPENSATING leftover -> COMPENSATION_FAILED -> x3 -> PARTIAL."""
    import datetime as dt
    import json
    import uuid

    from reversa_api.connectors.sdk import get_connector
    from reversa_api.db import session_for
    from reversa_api.engine.saga import execute_workflow_sync, reconcile_on_startup
    from reversa_api.models import ActionRun, Workflow, utcnow

    support = get_connector("demo-support")
    contract = support.contract_for("support.create_queue")
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="CM-17 crash",
                      intent="CM-17", state="COMPENSATING", plan_json="{}",
                      created_by="test")
        session.add(wf)
        session.flush()
        output = support.execute(
            {"org_id": demo_auth["org_id"], "is_demo": True,
             "workflow_id": wf.id, "idempotency_key": "k-cm17-1"},
            contract, {"org_slug": "acme", "tier": "enterprise"})
        session.add(ActionRun(
            workflow_id=wf.id, seq=1, action_type="support.create_queue",
            connector_id="demo-support", state="COMPENSATING",
            input_json=json.dumps({"org_slug": "acme", "tier": "enterprise"}),
            output_json=json.dumps(output),
            idempotency_key=f"k-cm17-1-{uuid.uuid4().hex}", attempt=1,
            max_attempts=3, lease_owner="dead-worker",
            lease_expires_at=utcnow() - dt.timedelta(seconds=60),
            compensation_capability="COMPENSATABLE", depends_on="[]"))
        session.commit()
        wf_id = wf.id
        ref = output["resource"]
    finally:
        session.close()

    # Startup: effect still present -> COMPENSATION_FAILED (re-compensate).
    stats = reconcile_on_startup(session_for("main"), "worker-2")
    assert stats["comp_failed"] == 1, stats

    # Before the retry, an external actor touches the resource: every
    # re-compensation now refuses with a version conflict.
    support.db.update_data(ref["id"], ref["version"], {"external": "auditor"})

    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="worker-2")
    assert final == "PARTIALLY_COMPENSATED", final

    events = _events(client, demo_auth, wf_id)
    trail = _transitions(events, "support.create_queue")
    assert "COMPENSATION_FAILED" in trail, trail
    assert trail.count("COMPENSATING") == 3, trail  # bounded: exactly 3 tries
    assert trail[-1] == "COMPENSATION_FAILED", trail
    wf_trail = [e["payload"].get("to") for e in events
                if e["type"] == "workflow.state"]
    assert wf_trail[-1] == "PARTIALLY_COMPENSATED", wf_trail

    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(workflow_id=wf_id).one()
        assert action.state == "COMPENSATION_FAILED"
        assert "changed" in action.error, action.error
        attempts = json.loads(action.output_json).get("_comp_attempts")
        assert attempts == 3, attempts
    finally:
        session.close()

    # Undo refused: queue still active.
    assert len(_resources(client, demo_auth, "support",
                          kind="queue", status="active")) == 1
    assert _resources(client, demo_auth, "support",
                      kind="queue", status="archived") == []

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_cm18_compensated_replay_is_idempotent(client, demo_auth):
    """CM-18: re-executing a COMPENSATED workflow replays without new effects."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "http500", "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth)["workflow"]["id"]

    first = client.post(f"/api/v1/workflows/{wf_id}/execute",
                        headers=demo_auth["headers"])
    assert first.status_code == 200, first.text
    assert first.json()["replay"] is False
    assert first.json()["workflow"]["state"] == "COMPENSATED", first.text
    events_before = _events(client, demo_auth, wf_id)

    second = client.post(f"/api/v1/workflows/{wf_id}/execute",
                         headers=demo_auth["headers"])
    assert second.status_code == 200, second.text
    assert second.json()["replay"] is True
    assert second.json()["workflow"]["state"] == "COMPENSATED"
    assert second.json()["actions"] == first.json()["actions"]

    # No duplicate effects: same journal, same restored resources.
    events_after = _events(client, demo_auth, wf_id)
    assert len(events_after) == len(events_before)
    assert _resources(client, demo_auth, "identity", kind="workspace") == []
    assert len(_resources(client, demo_auth, "identity", kind="user",
                          status="archived")) == 4
    assert len(_resources(client, demo_auth, "crm", kind="organization",
                          status="archived")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True
