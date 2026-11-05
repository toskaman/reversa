"""Chaos Matrix V2 cycle 3: CM-04, CM-03, CM-05, CM-10, CM-09 (cycle 2)
+ CM-11, CM-13, CM-15 (cycle 3). Covered: 13/20.

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
