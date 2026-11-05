"""Chaos Matrix V2 cycle 2: CM-04, CM-03, CM-05, CM-10, CM-09.

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
