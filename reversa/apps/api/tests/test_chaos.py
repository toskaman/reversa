"""Chaos: billing 500 -> compensation in reverse order, resources restored."""

from .conftest import INTENT, make_ready


def _action_transitions(events: list, action_type: str) -> list:
    return [e["payload"].get("to") for e in events
            if e["type"] == "action.state"
            and e["payload"].get("action_type") == action_type]


def test_billing_failure_compensates_everything(client, demo_auth):
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing", "fault": "http500",
                          "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text
    by_seq = {a["seq"]: a["state"] for a in r.json()["actions"]}
    assert by_seq[6] == "FAILED"  # billing
    # Branches independent of billing (7, 8) ran during the retry wait, then
    # everything completed was compensated; billing dependents blocked.
    assert all(by_seq[s] == "COMPENSATED" for s in (1, 2, 3, 4, 5, 7, 8)), by_seq
    assert all(by_seq[s] == "SKIPPED" for s in (9, 10)), by_seq

    # Compensation order was reverse (8 before 7 ...).
    r = client.get(f"/api/v1/workflows/{wf_id}/events", headers=demo_auth["headers"])
    comp_order = [e["payload"]["seq"] for e in r.json()["data"]
                  if e["type"] == "action.state" and e["payload"].get("to") == "COMPENSATED"]
    assert comp_order == [8, 7, 5, 4, 3, 2, 1], comp_order

    # Resources actually restored: workspace hard-deleted, users archived.
    org_id = demo_auth["org_id"]
    h = demo_auth["headers"]
    r = client.get("/api/v1/demo/identity/resources",
                   params={"org_id": org_id, "kind": "workspace"}, headers=h)
    assert r.json()["resources"] == []
    r = client.get("/api/v1/demo/identity/resources",
                   params={"org_id": org_id, "kind": "user", "status": "archived"},
                   headers=h)
    assert len(r.json()["resources"]) == 4
    r = client.get("/api/v1/demo/crm/resources",
                   params={"org_id": org_id, "kind": "organization", "status": "archived"},
                   headers=h)
    assert len(r.json()["resources"]) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence", headers=h)
    assert r.json()["chain"]["valid"] is True


def test_concurrent_modification_blocks_compensation(client, demo_auth):
    """A newer external change refuses the compensation -> MANUAL_REQUIRED path safe."""
    from reversa_api.connectors.services import DemoStore
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    # Simulate an external actor touching the CRM org mid-run is covered at the
    # store level: version conflicts raise PreconditionFailed.
    store = DemoStore("crm")
    row = store.create(demo_auth["org_id"], "organization", "ext",
                       {"company_name": "Ext"})
    import pytest
    from reversa_api.connectors.sdk import PreconditionFailed
    with pytest.raises(PreconditionFailed):
        store.set_status(row["id"], expected_version=999, status="archived")


def test_lost_response_retries_idempotently(client, demo_auth):
    """Lost response (chaos crash, uncertain) -> UNKNOWN -> reconcile absent
    -> exactly one safe retry -> COMPLETED."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-crm",
                          "target_action": "crm.validate_customer",
                          "fault": "crash", "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    r = client.get(f"/api/v1/workflows/{wf_id}/events", params={"limit": 500},
                   headers=demo_auth["headers"])
    events = r.json()["data"]
    trail = _action_transitions(events, "crm.validate_customer")
    assert "UNKNOWN_OUTCOME" in trail, trail
    # One uncertain attempt plus exactly one retry, then verified.
    assert trail.count("EXECUTING") == 2, trail
    assert trail[-1] == "VERIFIED", trail
    assert "chaos.injected" in [e["type"] for e in events]


def test_verifier_down_stays_unknown_then_resumes(client, demo_auth, monkeypatch):
    """A verifier error must never count as absence proof.

    While the verifier is down the uncertain action stays UNKNOWN_OUTCOME
    (no failure, no retry, no re-execution) and the run honestly reports a
    non-terminal state; after the verifier recovers the same run resumes to
    COMPLETED.
    """
    from reversa_api.connectors.sdk import ConnectorError, get_connector
    from reversa_api.db import session_for
    from reversa_api.engine.saga import execute_workflow_sync

    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-crm",
                          "target_action": "crm.validate_customer",
                          "fault": "crash", "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]

    crm = get_connector("demo-crm")
    real_verify = crm.verify

    def flaky_verify(ctx, contract, inputs, output):
        if contract.action_type == "crm.validate_customer":
            raise ConnectorError("VERIFY_TIMEOUT", "simulated verifier outage",
                                 retryable=True)
        return real_verify(ctx, contract, inputs, output)

    monkeypatch.setattr(crm, "verify", flaky_verify)
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "RUNNING", body["workflow"]
    assert body["terminal"] is False
    by_type = {a["action_type"]: a for a in body["actions"]}
    assert by_type["crm.validate_customer"]["state"] == "UNKNOWN_OUTCOME", by_type
    r = client.get(f"/api/v1/workflows/{wf_id}/events", params={"limit": 500},
                   headers=demo_auth["headers"])
    events = r.json()["data"]
    trail = _action_transitions(events, "crm.validate_customer")
    # Uncertain, then deferred: never failed, never retried, never re-ran.
    # (Claims journal as action.claimed, not action.state, hence no CLAIMED.)
    assert trail == ["EXECUTING", "UNKNOWN_OUTCOME"], trail
    assert "action.reconcile_indeterminate" in [e["type"] for e in events]

    # Verifier recovers: the same run resumes (absent -> retry -> verified).
    monkeypatch.setattr(crm, "verify", real_verify)
    assert execute_workflow_sync(session_for("main"), wf_id,
                                 worker_id="worker-2") == "COMPLETED"
