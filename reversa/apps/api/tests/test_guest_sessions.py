"""P1-AUTH-02: guest sessions, quotas, rotation overlap, rate limits."""

import datetime as dt
import time

import pytest

from reversa_api import auth as auth_mod
from reversa_api import ratelimit as ratelimit_mod
from reversa_api.auth import GUEST_TTL_SECONDS, hash_token

from .conftest import INTENT, make_ready


@pytest.fixture(autouse=True)
def _fresh_memory_state():
    auth_mod.reset_guest_state()
    ratelimit_mod.reset_rate_limit_state()
    yield
    auth_mod.reset_guest_state()
    ratelimit_mod.reset_rate_limit_state()


def _mint(client, auth, **kw):
    r = client.post("/api/v1/demo/guest-sessions", json=kw,
                    headers=auth["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def _guest_auth(minted):
    return {"headers": {"Authorization": f"Bearer {minted['credential']}"}}


def test_owner_can_mint_guest_session(client, demo_auth):
    body = _mint(client, demo_auth)
    assert body["credential"].startswith("rev_guest_")
    assert len(body["credential"]) > 40
    assert body["session_id"]
    assert body["max_workflows"] == 5
    assert body["max_executes"] == 10
    delta = (dt.datetime.fromisoformat(body["expires_at"])
             - dt.datetime.now(dt.timezone.utc)).total_seconds()
    assert GUEST_TTL_SECONDS - 120 < delta <= GUEST_TTL_SECONDS
    # Guest credential resolves to the demo org with a guest actor.
    r = client.get("/api/v1/me",
                   headers=_guest_auth(body)["headers"])
    assert r.status_code == 200
    me = r.json()
    assert me["org_slug"] == demo_auth["slug"]
    assert me["is_demo"] is True
    assert me["actor"] == f"guest:{body['session_id']}"


def test_guest_mint_restricted_to_demo_owner(client, demo_auth, real_auth):
    assert client.post("/api/v1/demo/guest-sessions",
                       json={}).status_code in (401, 403)
    r = client.post("/api/v1/demo/guest-sessions", json={},
                    headers=real_auth["headers"])
    assert r.status_code == 403
    guest = _guest_auth(_mint(client, demo_auth))
    r = client.post("/api/v1/demo/guest-sessions", json={},
                    headers=guest["headers"])
    assert r.status_code == 403  # guests cannot mint further guests


def test_guest_intent_quota_then_gone(client, demo_auth):
    guest = _guest_auth(_mint(client, demo_auth, max_workflows=2))
    for _ in range(2):
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=guest["headers"])
        assert r.status_code == 201, r.text
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=guest["headers"])
    assert r.status_code == 410
    assert r.json()["code"] == "QUOTA_EXHAUSTED"
    # Owner quota is independent of the guest's.
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text


def test_guest_execute_quota(client, demo_auth):
    guest = _guest_auth(_mint(client, demo_auth, max_workflows=3,
                                         max_executes=1))
    first = make_ready(client, guest)
    second = make_ready(client, guest)
    r = client.post(f"/api/v1/workflows/{first['workflow']['id']}/execute",
                    headers=guest["headers"])
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/workflows/{second['workflow']['id']}/execute",
                    headers=guest["headers"])
    assert r.status_code == 410
    assert r.json()["code"] == "QUOTA_EXHAUSTED"


def test_guest_chaos_denied(client, demo_auth):
    guest = _guest_auth(_mint(client, demo_auth))
    payload = {"target_connector": "demo-billing", "fault": "http500"}
    r = client.post("/api/v1/demo/chaos", json=payload,
                    headers=guest["headers"])
    assert r.status_code == 403
    r = client.get("/api/v1/demo/chaos", headers=guest["headers"])
    assert r.status_code == 403
    # Owner sanity: chaos still allowed for the demo owner.
    r = client.post("/api/v1/demo/chaos", json=payload,
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text


def test_expired_guest_rejected(client, demo_auth):
    minted = _mint(client, demo_auth)
    auth_mod._GUEST_SESSIONS[hash_token(
        minted["credential"])]["expires_at"] = time.time() - 1
    guest = _guest_auth(minted)
    assert client.get("/api/v1/me",
                      headers=guest["headers"]).status_code == 403
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=guest["headers"])
    assert r.status_code == 403


def test_guest_demo_org_only_isolation(client, demo_auth, real_auth):
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=real_auth["headers"])
    real_wf = r.json()["workflow"]["id"]
    made = make_ready(client, demo_auth)
    guest = _guest_auth(_mint(client, demo_auth))
    assert client.get(f"/api/v1/workflows/{real_wf}",
                      headers=guest["headers"]).status_code == 404
    r = client.get(f"/api/v1/workflows/{made['workflow']['id']}",
                   headers=guest["headers"])
    assert r.status_code == 200


def test_rotation_overlap_mint_then_revoke(client, demo_auth):
    r = client.get("/api/v1/demo/tokens", headers=demo_auth["headers"])
    assert r.status_code == 200
    assert [t["name"] for t in r.json()["data"]] == ["test"]
    r = client.post("/api/v1/demo/tokens", json={"name": "rotated"},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    new_cred = r.json()["credential"]
    assert new_cred.startswith("rev_demo_")
    new_auth = {"headers": {"Authorization": f"Bearer {new_cred}"}}
    # Overlap: old AND new are both valid.
    assert client.get("/api/v1/me",
                      headers=demo_auth["headers"]).status_code == 200
    assert client.get("/api/v1/me",
                      headers=new_auth["headers"]).status_code == 200
    # Revoke old while authed as new.
    r = client.delete("/api/v1/demo/tokens/test", headers=new_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == {"revoked": "test"}
    assert client.get("/api/v1/me",
                      headers=demo_auth["headers"]).status_code == 403
    assert client.get("/api/v1/me",
                      headers=new_auth["headers"]).status_code == 200


def test_rotation_guards(client, demo_auth, real_auth):
    # Cannot revoke the credential in use.
    r = client.delete("/api/v1/demo/tokens/test",
                      headers=demo_auth["headers"])
    assert r.status_code == 409
    assert client.get("/api/v1/me",
                      headers=demo_auth["headers"]).status_code == 200
    # Unknown name, duplicate name, bad name.
    assert client.delete("/api/v1/demo/tokens/nope",
                         headers=demo_auth["headers"]).status_code == 404
    assert client.post("/api/v1/demo/tokens", json={"name": "test"},
                       headers=demo_auth["headers"]).status_code == 409
    assert client.post("/api/v1/demo/tokens", json={"name": "bad name!"},
                       headers=demo_auth["headers"]).status_code == 422
    # Guests, real orgs, and anonymous callers are all refused.
    guest = _guest_auth(_mint(client, demo_auth))
    for auth in (guest, real_auth):
        assert client.post("/api/v1/demo/tokens", json={"name": "x"},
                           headers=auth["headers"]).status_code == 403
        assert client.get("/api/v1/demo/tokens",
                          headers=auth["headers"]).status_code == 403
        assert client.delete("/api/v1/demo/tokens/test",
                             headers=auth["headers"]).status_code == 403
    assert client.get("/api/v1/demo/tokens").status_code in (401, 403)


def test_intent_rate_limit_429_and_recovery(client, demo_auth, monkeypatch):
    monkeypatch.setitem(ratelimit_mod._TIERS, "intents", (3, 60))
    for _ in range(3):
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=demo_auth["headers"])
        assert r.status_code == 201, r.text
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"
    assert r.json()["retryable"] is True
    assert "Retry-After" in r.headers
    ratelimit_mod.reset_rate_limit_state()
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text


def test_execute_rate_limit(client, demo_auth, monkeypatch):
    monkeypatch.setitem(ratelimit_mod._TIERS, "execute", (1, 60))
    first = make_ready(client, demo_auth)
    second = make_ready(client, demo_auth)
    r = client.post(f"/api/v1/workflows/{first['workflow']['id']}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/workflows/{second['workflow']['id']}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"


def test_owner_traffic_unaffected(client, demo_auth):
    # Owners have no lifetime quota: 6 intents (over the guest default of 5).
    for _ in range(6):
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=demo_auth["headers"])
        assert r.status_code == 201, r.text
