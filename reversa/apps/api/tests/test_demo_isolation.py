"""F2: demo resources are namespaced per workflow run.

Two runs in one org reuse the same logical names ("acme", user emails) but
must own separate rows: a chaos run that compensates must never archive
another run's rows. Org scoping (V2-01) still applies on top of run scoping.
"""

from reversa_api.connectors.services import RUN_TAG

from .conftest import make_ready


def test_store_scopes_rows_per_run(fresh_db, demo_auth):
    """Same (org, kind, name) across two runs -> two rows; replay in one run
    -> same row (idempotency preserved within the run)."""
    from reversa_api.connectors.services import DemoStore
    store = DemoStore("crm")
    org = demo_auth["org_id"]
    a1 = store.create(org, "organization", "acme", {"company_name": "Acme"},
                      workflow_id=101)
    a2 = store.create(org, "organization", "acme", {"company_name": "Acme"},
                      workflow_id=101)
    b1 = store.create(org, "organization", "acme", {"company_name": "Acme"},
                      workflow_id=102)
    assert a1["id"] == a2["id"]  # idempotent within a run
    assert b1["id"] != a1["id"]  # isolated across runs
    assert a1["data"][RUN_TAG] == 101
    assert b1["data"][RUN_TAG] == 102
    assert store.find_active(org, "organization", "acme",
                             workflow_id=101)["id"] == a1["id"]
    assert store.find_active(org, "organization", "acme",
                             workflow_id=102)["id"] == b1["id"]
    assert store.find_active(org, "organization", "acme",
                             workflow_id=999) is None
    assert len(store.list(org, kind="organization", workflow_id=101)) == 1
    # Legacy unscoped reads still see every row of the org.
    assert len(store.list(org, kind="organization")) == 2


def test_chaos_run_never_archives_other_run(client, demo_auth):
    """Run A COMPLETES; chaos run B COMPENSATES; A's rows stay active."""
    # Run A: clean onboarding.
    made_a = make_ready(client, demo_auth)
    wf_a = made_a["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_a}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED"

    # Run B: same org, same logical names, billing chaos -> COMPENSATED.
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing", "fault": "http500",
                          "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    made_b = make_ready(client, demo_auth)
    wf_b = made_b["workflow"]["id"]
    assert wf_b != wf_a
    r = client.post(f"/api/v1/workflows/{wf_b}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text

    h = demo_auth["headers"]
    # Same name, two rows, opposite fates: B archived only its own org.
    r = client.get("/api/v1/demo/crm/resources", params={"kind": "organization"},
                   headers=h)
    orgs = r.json()["resources"]
    assert sorted(o["name"] for o in orgs) == ["acme", "acme"]
    by_run = {o["data"][RUN_TAG]: o for o in orgs}
    assert by_run[wf_a]["status"] == "active"
    assert by_run[wf_b]["status"] == "archived"

    # Scoped reads: each run sees exactly its own rows.
    r = client.get("/api/v1/demo/crm/resources",
                   params={"kind": "organization", "workflow_id": wf_a}, headers=h)
    assert [o["status"] for o in r.json()["resources"]] == ["active"]
    r = client.get("/api/v1/demo/identity/resources",
                   params={"kind": "workspace", "workflow_id": wf_a}, headers=h)
    assert len(r.json()["resources"]) == 1  # B's workspace hard-deleted, A's alive
    r = client.get("/api/v1/demo/identity/resources",
                   params={"kind": "user", "status": "active", "workflow_id": wf_a},
                   headers=h)
    assert len(r.json()["resources"]) == 4  # B archived only its own 4 users
    r = client.get("/api/v1/demo/identity/resources",
                   params={"kind": "user", "status": "archived"}, headers=h)
    assert len(r.json()["resources"]) == 4

    # Both evidence chains stay valid.
    for wf in (wf_a, wf_b):
        r = client.get(f"/api/v1/workflows/{wf}/evidence", headers=h)
        assert r.json()["chain"]["valid"] is True


def test_run_scoping_keeps_org_isolation(client, demo_auth, real_auth):
    """A workflow_id filter never leaks rows across orgs (V2-01 + F2 compose)."""
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED"
    r = client.get("/api/v1/demo/crm/resources",
                   params={"kind": "organization", "workflow_id": wf_id},
                   headers=real_auth["headers"])
    assert r.status_code == 200
    assert r.json()["resources"] == []
