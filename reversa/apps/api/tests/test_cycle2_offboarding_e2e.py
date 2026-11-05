"""Cycle 2 offboarding E2E: happy-path execution + chaos compensation.

The offboarding template (validate -> checklist -> notify) must not only
plan correctly — it must execute through the real saga engine, and a
mid-run failure must compensate completed steps like any other domain.
"""
from .conftest import make_ready

OFFBOARD_INTENT = ("Offboard Dana from Acme after her departure; "
                    "revoke workspace access and reassign her queue tickets.")


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


def test_offboarding_executes_happy_path(client, demo_auth):
    body = make_ready(client, demo_auth, intent=OFFBOARD_INTENT)
    wf_id = body["workflow"]["id"]
    assert body["approval_required"] is False  # AUTO_ALLOWED template

    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert [a["action_type"] for _, a in sorted(by_seq.items())] == [
        "crm.validate_customer", "support.create_checklist",
        "notify.send_summary",
    ], by_seq
    assert all(a["state"] == "VERIFIED" for a in by_seq.values()), by_seq

    assert len(_resources(client, demo_auth, "support", kind="checklist",
                          status="active")) == 1

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True


def test_offboarding_chaos_on_support_compensates(client, demo_auth):
    """http500 x5 on demo-support -> step 2 FAILED, step 1 COMPENSATED,
    step 3 SKIPPED, workflow COMPENSATED, no active checklist left."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-support", "fault": "http500",
                          "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id = make_ready(client, demo_auth, intent=OFFBOARD_INTENT)["workflow"]["id"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text
    by_seq = {a["seq"]: a for a in r.json()["actions"]}
    assert by_seq[1]["state"] == "COMPENSATED", by_seq
    assert by_seq[2]["state"] == "FAILED", by_seq
    assert by_seq[2]["action_type"] == "support.create_checklist"
    assert by_seq[2]["attempt"] == by_seq[2]["max_attempts"], by_seq
    assert "CHAOS" in by_seq[2]["error"], by_seq[2]["error"]
    assert by_seq[3]["state"] == "SKIPPED", by_seq

    events = _events(client, demo_auth, wf_id)
    assert "chaos.injected" in [e["type"] for e in events]

    assert _resources(client, demo_auth, "support", kind="checklist",
                      status="active") == []

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.json()["chain"]["valid"] is True
