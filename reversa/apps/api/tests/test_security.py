"""Security P0: auth, tenant isolation, approvals, chaos guard."""

from .conftest import INTENT


def _seed_workspaces(demo_auth, real_auth):
    from reversa_api.connectors.services import DemoStore
    DemoStore("identity").create(
        demo_auth["org_id"], "workspace", "demo-ws", {"manager": None})
    DemoStore("identity").create(
        real_auth["org_id"], "workspace", "real-ws", {"manager": None})


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


# --- P0-SEC-01: demo resources take org from auth context, never client org_id ---


def test_demo_resources_anonymous_rejected(client):
    r = client.get("/api/v1/demo/identity/resources")
    assert r.status_code in (401, 403)
    # Unknown service must not oracle past auth either.
    r = client.get("/api/v1/demo/nope/resources")
    assert r.status_code in (401, 403)


def test_demo_resources_bad_token_rejected(client):
    h = {"Authorization": "Bearer invalid-token-for-test"}
    r = client.get("/api/v1/demo/identity/resources", headers=h)
    assert r.status_code == 403


def test_demo_resources_unknown_service(client, demo_auth):
    r = client.get("/api/v1/demo/nope/resources", headers=demo_auth["headers"])
    assert r.status_code == 404


def test_demo_resources_cross_tenant_isolated(client, demo_auth, real_auth):
    _seed_workspaces(demo_auth, real_auth)
    r = client.get("/api/v1/demo/identity/resources",
                   params={"kind": "workspace"}, headers=demo_auth["headers"])
    assert r.status_code == 200
    assert [x["name"] for x in r.json()["resources"]] == ["demo-ws"]
    r = client.get("/api/v1/demo/identity/resources",
                   params={"kind": "workspace"}, headers=real_auth["headers"])
    assert r.status_code == 200
    assert [x["name"] for x in r.json()["resources"]] == ["real-ws"]


def test_demo_resources_client_org_id_ignored(client, demo_auth, real_auth):
    """IDOR: a forged ?org_id= must not leak another tenant's resources."""
    _seed_workspaces(demo_auth, real_auth)
    r = client.get("/api/v1/demo/identity/resources",
                   params={"org_id": demo_auth["org_id"], "kind": "workspace"},
                   headers=real_auth["headers"])
    assert r.status_code == 200
    assert [x["name"] for x in r.json()["resources"]] == ["real-ws"]
    r = client.get("/api/v1/demo/identity/resources",
                   params={"org_id": real_auth["org_id"], "kind": "workspace"},
                   headers=demo_auth["headers"])
    assert r.status_code == 200
    assert [x["name"] for x in r.json()["resources"]] == ["demo-ws"]


# --- P1-SSE-01: short single-use connection tickets instead of ?token= ---


def test_stream_ticket_requires_auth(client, demo_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    wf_id = r.json()["workflow"]["id"]
    url = f"/api/v1/workflows/{wf_id}/stream-ticket"
    assert client.post(url).status_code in (401, 403)
    h = {"Authorization": "Bearer invalid-token-for-test"}
    assert client.post(url, headers=h).status_code == 403
    # Anonymous stream open is rejected immediately (no hang).
    r = client.get(f"/api/v1/workflows/{wf_id}/events/stream")
    assert r.status_code in (401, 403)


def test_stream_ticket_cross_tenant_mint_404(client, demo_auth, real_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    wf_id = r.json()["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/stream-ticket",
                    headers=real_auth["headers"])
    assert r.status_code == 404


def test_stream_ticket_single_use_flow(client, demo_auth):
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED"
    r = client.post(f"/api/v1/workflows/{wf_id}/stream-ticket",
                    headers=demo_auth["headers"])
    assert r.status_code == 201
    assert r.json()["expires_in"] == 30
    ticket = r.json()["ticket"]
    assert len(ticket) >= 32
    stream_url = f"/api/v1/workflows/{wf_id}/events/stream"
    r = client.get(stream_url, params={"ticket": ticket})
    assert r.status_code == 200
    assert "event: done" in r.text
    assert '"state": "COMPLETED"' in r.text
    # Single-use: replay is rejected.
    r = client.get(stream_url, params={"ticket": ticket})
    assert r.status_code == 403
    # Forged ticket rejected.
    r = client.get(stream_url, params={"ticket": "forged-ticket-value"})
    assert r.status_code == 403
    # Deprecated ?token= fallback still works during web migration.
    raw = demo_auth["headers"]["Authorization"].split(" ", 1)[1]
    r = client.get(stream_url, params={"token": raw})
    assert r.status_code == 200
    assert "event: done" in r.text


def test_stream_ticket_bound_to_workflow(client, demo_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    wf_id = r.json()["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/stream-ticket",
                    headers=demo_auth["headers"])
    ticket = r.json()["ticket"]
    # Redeem against a different workflow id: rejected immediately (no hang).
    r = client.get("/api/v1/workflows/999999/events/stream", params={"ticket": ticket})
    assert r.status_code == 403


def test_stream_ticket_expiry_rejected(client, demo_auth):
    import time

    from reversa_api.routes import workflows as wf_routes
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    wf_id = r.json()["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/stream-ticket",
                    headers=demo_auth["headers"])
    ticket = r.json()["ticket"]
    wf_routes._SSE_TICKETS[ticket]["expires_at"] = time.time() - 1
    r = client.get(f"/api/v1/workflows/{wf_id}/events/stream", params={"ticket": ticket})
    assert r.status_code == 403


def test_stream_garbage_last_event_id_is_ignored(client, demo_auth):
    """A malformed Last-Event-ID header must not crash the stream (500)."""
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED"
    raw = demo_auth["headers"]["Authorization"].split(" ", 1)[1]
    headers = {"Authorization": demo_auth["headers"]["Authorization"],
               "Last-Event-ID": "not-a-number"}
    r = client.get(f"/api/v1/workflows/{wf_id}/events/stream?token={raw}",
                   headers=headers)
    assert r.status_code == 200
    assert "event: done" in r.text
