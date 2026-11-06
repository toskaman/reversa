"""V7-B1: shareable evidence view (?view=shared).

Canonical export (default) keeps full detail for the owning org. The shared
view omits user-controlled non-chained fields (intent, plan, action
inputs/output/error) so the bundle can be posted externally, while event
payloads stay byte-identical so offline `verify_bundle` still returns VALID.
"""
import copy
import json

from reversa_api.cli import verify_bundle

INTENT = ("Onboard SharedView Ltd across CRM, identity, support and billing; "
          "internal note hunter2-not-a-real-secret for the ops team.")


def _completed(client, demo_auth):
    from .conftest import make_ready
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED"
    return wf_id


def test_canonical_default_keeps_full_detail(client, demo_auth):
    wf_id = _completed(client, demo_auth)
    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.status_code == 200
    bundle = r.json()
    assert bundle.get("view", "canonical") == "canonical"
    assert "intent" in bundle["workflow"]
    assert isinstance(bundle["plan"], dict) and bundle["plan"]
    assert any("inputs" in a for a in bundle["actions"])


def test_shared_view_omits_nonchained_but_verifies(client, demo_auth):
    wf_id = _completed(client, demo_auth)
    h = demo_auth["headers"]
    canon = client.get(f"/api/v1/workflows/{wf_id}/evidence", headers=h).json()
    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   params={"view": "shared"}, headers=h)
    assert r.status_code == 200
    shared = r.json()
    assert shared["view"] == "shared"
    assert "intent" not in shared["workflow"]
    assert shared["workflow"]["name"] != canon["workflow"]["name"]
    assert shared["plan"].get("omitted") == "shared"
    assert "redactions" in shared and isinstance(shared["redactions"], list)
    for a in shared["actions"]:
        assert "inputs" not in a and "output" not in a
        assert a.get("inputs_omitted") == "shared"
    # Events byte-identical -> offline verification still VALID.
    assert json.dumps(shared["events"], sort_keys=True) == \
        json.dumps(canon["events"], sort_keys=True)
    ok, message = verify_bundle(shared)
    assert ok is True, message
    ok, _ = verify_bundle(canon)
    assert ok is True


def test_shared_view_unknown_rejected(client, demo_auth):
    wf_id = _completed(client, demo_auth)
    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   params={"view": "nope"}, headers=demo_auth["headers"])
    assert r.status_code == 422


def test_shared_view_tamper_still_invalid(client, demo_auth):
    wf_id = _completed(client, demo_auth)
    shared = client.get(
        f"/api/v1/workflows/{wf_id}/evidence", params={"view": "shared"},
        headers=demo_auth["headers"]).json()
    assert len(shared["events"]) > 1
    bad = copy.deepcopy(shared)
    bad["events"][1]["payload"]["n"] = "tampered"
    ok, message = verify_bundle(bad)
    assert ok is False
    assert "mismatch" in message
