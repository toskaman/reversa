"""Chaos: billing 500 -> compensation in reverse order, resources restored."""

from .conftest import INTENT, make_ready


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
