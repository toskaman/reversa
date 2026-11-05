"""Connector Hub routes: list + per-connector health (AGENT-06, cycle 3).

Covers GET /api/v1/connectors and GET /api/v1/connectors/{id}/health:
shape, auth, unknown-connector 404, and tenant-scoped resource counts.
"""

from reversa_api.connectors.sdk import REGISTRY

EXPECTED_CONNECTORS = {
    "demo-crm": "crm",
    "demo-identity": "identity",
    "demo-support": "support",
    "demo-billing": "billing",
    "demo-notify": "notify",
    "reversa-core": "",  # core actions: no demo store
}

CAPABILITY_KEYS = {"action_type", "connector_id", "schema_version",
                   "compensation_capability", "risk_level",
                   "approval_policy", "description"}


def test_list_connectors_shape(client, demo_auth):
    r = client.get("/api/v1/connectors", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"connectors", "capabilities"}
    by_id = {c["connector_id"]: c for c in body["connectors"]}
    # Subset: the github connector registers only when configured.
    assert set(EXPECTED_CONNECTORS) <= set(by_id)
    for cid, store in EXPECTED_CONNECTORS.items():
        entry = by_id[cid]
        assert set(entry) == {"connector_id", "store", "healthy", "resources"}
        assert entry["store"] == (store or "none (core)")
        assert entry["healthy"] is True
        assert entry["resources"] == 0  # fresh org: no demo resources yet
    assert len(body["capabilities"]) > 0
    for cap in body["capabilities"]:
        assert CAPABILITY_KEYS <= set(cap), cap


def test_list_connectors_requires_auth(client, demo_auth):
    assert client.get("/api/v1/connectors").status_code == 401
    bad = {"headers": {"Authorization": "Bearer rev_test_nope"}}
    assert client.get("/api/v1/connectors", headers=bad["headers"]).status_code == 403
    # Sanity: the valid credential still works.
    r = client.get("/api/v1/connectors", headers=demo_auth["headers"])
    assert r.status_code == 200


def test_health_each_registered_connector(client, demo_auth):
    assert len(REGISTRY) >= len(EXPECTED_CONNECTORS)
    for cid, connector in REGISTRY.items():
        r = client.get(f"/api/v1/connectors/{cid}/health",
                       headers=demo_auth["headers"])
        assert r.status_code == 200, (cid, r.text)
        body = r.json()
        assert body["connector_id"] == cid
        assert body["healthy"] is True
        assert body["actions"] == sorted(body["actions"])
        assert set(body["actions"]) == set(connector.capabilities)
        assert isinstance(body["resources"], list)


def test_health_unknown_connector_404(client, demo_auth):
    r = client.get("/api/v1/connectors/demo-nope/health",
                   headers=demo_auth["headers"])
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown connector"


def test_health_requires_auth(client):
    url = "/api/v1/connectors/demo-crm/health"
    assert client.get(url).status_code == 401
    bad = {"headers": {"Authorization": "Bearer rev_test_nope"}}
    assert client.get(url, headers=bad["headers"]).status_code == 403


def test_resources_reflect_workflow_and_stay_tenant_scoped(client, demo_auth,
                                                           real_auth):
    before = client.get("/api/v1/connectors", headers=demo_auth["headers"])
    assert before.status_code == 200
    assert sum(c["resources"] for c in before.json()["connectors"]) == 0
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED"

    demo = client.get("/api/v1/connectors", headers=demo_auth["headers"]).json()
    assert sum(c["resources"] for c in demo["connectors"]) > 0
    crm = next(c for c in demo["connectors"] if c["connector_id"] == "demo-crm")
    assert crm["resources"] == 1  # one organization row for the demo org

    # A different tenant sees zero resources on both endpoints.
    real = client.get("/api/v1/connectors", headers=real_auth["headers"]).json()
    assert sum(c["resources"] for c in real["connectors"]) == 0
    h_demo = client.get("/api/v1/connectors/demo-crm/health",
                        headers=demo_auth["headers"]).json()
    h_real = client.get("/api/v1/connectors/demo-crm/health",
                        headers=real_auth["headers"]).json()
    assert len(h_demo["resources"]) == 1
    assert h_real["resources"] == []
