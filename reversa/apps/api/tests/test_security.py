"""Security P0: auth, tenant isolation, approvals, chaos guard."""

from .conftest import INTENT


def test_no_token_rejected(client):
    assert client.get("/api/v1/workflows").status_code in (401, 403)
    assert client.post("/api/v1/intents", json={"intent": INTENT}).status_code in (401, 403)


def test_bad_token_rejected(client):
    h = {"Authorization": "Bearer nope"}
    assert client.get("/api/v1/workflows", headers=h).status_code == 403


def test_cross_tenant_workflow_invisible(client, demo_auth, real_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    wf_id = r.json()["workflow"]["id"]
    assert client.get(f"/api/v1/workflows/{wf_id}",
                      headers=real_auth["headers"]).status_code == 404
    assert client.post(f"/api/v1/workflows/{wf_id}/execute",
                       headers=real_auth["headers"]).status_code == 404


def test_chaos_forbidden_for_real_tenant(client, real_auth):
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing", "fault": "http500"},
                    headers=real_auth["headers"])
    assert r.status_code == 403


def test_approval_rejects_wrong_hash(client, demo_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    body = r.json()
    wf_id = body["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/approve",
                    json={"plan_hash": "0" * 64, "decided_by": "mallory"},
                    headers=demo_auth["headers"])
    assert r.status_code == 409
    # Still awaiting approval, never executed.
    r = client.get(f"/api/v1/workflows/{wf_id}", headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "AWAITING_APPROVAL"


def test_execute_requires_ready(client, demo_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    wf_id = r.json()["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 409  # must approve first


def test_cancel_ready_workflow(client, demo_auth):
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/cancel", headers=demo_auth["headers"])
    assert r.status_code == 200
    assert r.json()["workflow"]["state"] == "CANCELLED"
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 409
