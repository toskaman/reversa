"""Happy path: intent -> approve -> execute -> COMPLETED + real resources."""

from .conftest import INTENT, make_ready


def test_full_onboarding_happy_path(client, demo_auth):
    made = make_ready(client, demo_auth)
    assert made["approval_required"] is True  # billing step
    wf_id = made["workflow"]["id"]

    preview = client.get(f"/api/v1/workflows/{wf_id}/preview",
                         headers=demo_auth["headers"])
    assert preview.status_code == 200
    assert preview.json()["steps"] == 10
    assert preview.json()["approvals_required"] is True
    assert "notify.send_summary" in preview.json()["irreversible"]

    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED"
    assert all(a["state"] == "VERIFIED" for a in r.json()["actions"])

    # Real resources in independent service states.
    org_id = demo_auth["org_id"]
    checks = [("crm", "organization", 1), ("identity", "workspace", 1),
              ("identity", "user", 4), ("support", "queue", 1),
              ("billing", "billing_profile", 1)]
    for service, kind, count in checks:
        r = client.get(f"/api/v1/demo/{service}/resources",
                       params={"org_id": org_id, "kind": kind, "status": "active"},
                       headers=demo_auth["headers"])
        assert len(r.json()["resources"]) == count, (service, kind, r.text)

    # Evidence chain valid + CLI-verifiable export.
    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.status_code == 200
    bundle = r.json()
    assert bundle["chain"]["valid"] is True
    assert len(bundle["events"]) > 20
    from reversa_api.cli import verify_bundle
    ok, message = verify_bundle(bundle)
    assert ok, message

    html = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                      params={"format": "html"}, headers=demo_auth["headers"])
    assert html.status_code == 200
    assert "Evidence Passport" in html.text
