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
    # Guest credential resolves to its OWN ephemeral org with a guest actor.
    r = client.get("/api/v1/me",
                   headers=_guest_auth(body)["headers"])
    assert r.status_code == 200
    me = r.json()
    assert body["org_slug"].startswith("guest-")
    assert me["org_slug"] == body["org_slug"]
    assert me["org_slug"] != demo_auth["slug"]
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


def test_guest_per_session_org_isolation(client, demo_auth, real_auth):
    """Per-session ephemeral orgs: a guest sees neither real nor owner-demo rows."""
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=real_auth["headers"])
    real_wf = r.json()["workflow"]["id"]
    made = make_ready(client, demo_auth)
    guest = _guest_auth(_mint(client, demo_auth))
    assert client.get(f"/api/v1/workflows/{real_wf}",
                      headers=guest["headers"]).status_code == 404
    r = client.get(f"/api/v1/workflows/{made['workflow']['id']}",
                   headers=guest["headers"])
    assert r.status_code == 404


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


# --- Cycle 3 (AGENT-12): rate/quota edge regression tests --------------------


def test_c3_tier_trailing_slash_mapped():
    # A trailing slash must not bypass the rate-limit tier.
    assert ratelimit_mod._tier_for("POST", "/api/v1/intents/") == "intents"
    assert ratelimit_mod._tier_for("POST", "/api/v1/workflows/7/execute/") == "execute"
    assert ratelimit_mod._tier_for("POST", "/api/v1/intents") == "intents"
    assert ratelimit_mod._tier_for("GET", "/api/v1/intents") is None
    assert ratelimit_mod._tier_for("POST", "/api/v1/workflows/abc/execute") is None


def test_c3_check_unknown_tier_fails_open():
    ok, retry = ratelimit_mod._check("no-such-tier", "k", time.time())
    assert ok is True
    assert retry == 0.0


def test_c3_check_degenerate_config_clamped(monkeypatch):
    # limit/window of 0 must not crash or divide; clamped to >= 1.
    monkeypatch.setitem(ratelimit_mod._TIERS, "intents", (0, 0))
    now = time.time()
    assert ratelimit_mod._check("intents", "k", now)[0] is True
    ok, retry = ratelimit_mod._check("intents", "k", now)
    assert ok is False
    assert retry >= 0.0


def test_c3_window_rollover_allows_again(monkeypatch):
    monkeypatch.setitem(ratelimit_mod._TIERS, "intents", (2, 60))
    t0 = time.time()
    assert ratelimit_mod._check("intents", "k", t0)[0] is True
    assert ratelimit_mod._check("intents", "k", t0)[0] is True
    assert ratelimit_mod._check("intents", "k", t0)[0] is False
    # After the window expires the same key is admitted with a fresh count.
    assert ratelimit_mod._check("intents", "k", t0 + 61)[0] is True
    assert ratelimit_mod._check("intents", "k", t0 + 61)[0] is True
    assert ratelimit_mod._check("intents", "k", t0 + 61)[0] is False


def test_c3_window_store_bounded_expired_purged(monkeypatch):
    monkeypatch.setattr(ratelimit_mod, "_MAX_WINDOWS", 5)
    now = time.time()
    for i in range(8):  # all expired long ago
        ratelimit_mod._WINDOWS[("intents", f"stale-{i}")] = [now - 3600, 3]
    assert ratelimit_mod._check("intents", "fresh", now)[0] is True
    # 8 stale -> purged down to cap (5), then the fresh insert lands: 6.
    assert len(ratelimit_mod._WINDOWS) == 6
    assert ("intents", "fresh") in ratelimit_mod._WINDOWS


def test_c3_window_store_bounded_oldest_evicted(monkeypatch):
    monkeypatch.setattr(ratelimit_mod, "_MAX_WINDOWS", 3)
    now = time.time()
    for i in range(5):  # all fresh: oldest-first eviction must kick in
        ratelimit_mod._WINDOWS[("intents", f"old-{i}")] = [now - i, 1]
    assert ratelimit_mod._check("intents", "new", now)[0] is True
    keys = {k[1] for k in ratelimit_mod._WINDOWS}
    assert "new" in keys
    assert "old-4" not in keys and "old-3" not in keys  # oldest evicted
    assert len(ratelimit_mod._WINDOWS) <= 4  # cap + one in-flight insert


def test_c3_rate_limit_retry_after_positive_int(client, demo_auth, monkeypatch):
    monkeypatch.setitem(ratelimit_mod._TIERS, "intents", (1, 60))
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_c3_guest_mint_bounds_rejected(client, demo_auth):
    for payload in ({"max_workflows": 0}, {"max_workflows": 21},
                    {"max_executes": 0}, {"max_executes": 51},
                    {"max_workflows": -1, "max_executes": -5}):
        r = client.post("/api/v1/demo/guest-sessions", json=payload,
                        headers=demo_auth["headers"])
        assert r.status_code == 422, (payload, r.text)


def test_c3_guest_mint_at_maximum_ok(client, demo_auth):
    body = _mint(client, demo_auth, max_workflows=20, max_executes=50)
    assert body["max_workflows"] == 20
    assert body["max_executes"] == 50


def test_c3_quota_exhaustion_isolated_to_session(client, demo_auth):
    # Boundary: max_workflows=1 allows exactly one intent, then 410 ...
    guest_a = _guest_auth(_mint(client, demo_auth, max_workflows=1))
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=guest_a["headers"])
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=guest_a["headers"])
    assert r.status_code == 410
    assert r.json()["code"] == "QUOTA_EXHAUSTED"
    # ... while a fresh sibling session from the same owner still works.
    guest_b = _guest_auth(_mint(client, demo_auth, max_workflows=1))
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=guest_b["headers"])
    assert r.status_code == 201, r.text


def test_c3_expired_guest_execute_rejected_403(client, demo_auth):
    minted = _mint(client, demo_auth)
    guest = _guest_auth(minted)
    made = make_ready(client, guest)
    auth_mod._GUEST_SESSIONS[hash_token(
        minted["credential"])]["expires_at"] = time.time() - 1
    r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/execute",
                    headers=guest["headers"])
    assert r.status_code == 403  # expired: auth rejection, never 410/500


def test_v41_concurrent_intents_admit_exactly_quota(client, demo_auth):
    """V4-1: racing intents against max M admit exactly M (410 for rest)."""
    import threading

    body = _mint(client, demo_auth, max_workflows=3, max_executes=1)
    headers = _guest_auth(body)["headers"]
    results = []
    barrier = threading.Barrier(9)

    def fire():
        barrier.wait(timeout=10)
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=headers)
        results.append(r.status_code)

    threads = [threading.Thread(target=fire) for _ in range(9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads)
    assert sorted(results).count(201) == 3, results
    assert set(results) <= {201, 410}, results


def test_guest_chaos_403_carries_cors_headers(client, demo_auth):
    """Middleware 403s must carry ACAO headers: without them the browser
    reports a CORS failure and hides the real FORBIDDEN error."""
    guest = _guest_auth(_mint(client, demo_auth))
    headers = {**guest["headers"], "Origin": "http://localhost:3000"}
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "http500", "times": 1},
                    headers=headers)
    assert r.status_code == 403, r.text
    assert r.headers.get("access-control-allow-origin") == \
        "http://localhost:3000", dict(r.headers)


def test_preflight_short_circuits_before_auth(client):
    """OPTIONS preflight needs no credential and answers CORS headers."""
    r = client.options(
        "/api/v1/demo/chaos",
        headers={"Origin": "http://localhost:3000",
                 "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200, r.text
    assert r.headers.get("access-control-allow-origin") == \
        "http://localhost:3000", dict(r.headers)
