"""Cycle 4 (AGENT-07): true per-session guest isolation.

Every guest session owns an ephemeral demo org (slug "guest-<session>").
The 12 A/B checks prove two sibling sessions (and the owner) are mutually
invisible across approve/execute/resume/cancel/evidence/SSE/resources/chaos,
that expiry + quotas are per-session, and that the expiry sweep deletes only
the expired session's org. Plus PUBLIC mint endpoint coverage.
"""

import time

import pytest
from sqlalchemy import select

from reversa_api import auth as auth_mod
from reversa_api import ratelimit as ratelimit_mod
from reversa_api.auth import (
    PUBLIC_GUEST_MAX_EXECUTES,
    PUBLIC_GUEST_MAX_WORKFLOWS,
    hash_token,
)
from reversa_api.db import session_for
from reversa_api.models import Organization, Workflow
from reversa_api.routes import guest_sessions as guest_routes

from .conftest import INTENT, make_ready


@pytest.fixture(autouse=True)
def _fresh_memory_state():
    auth_mod.reset_guest_state()
    ratelimit_mod.reset_rate_limit_state()
    guest_routes.reset_public_mint_state()
    auth_mod._LAST_SWEEP_ERRORS.clear()
    yield
    auth_mod.reset_guest_state()
    ratelimit_mod.reset_rate_limit_state()
    guest_routes.reset_public_mint_state()
    auth_mod._LAST_SWEEP_ERRORS.clear()


def _mint(client, auth, **kw):
    r = client.post("/api/v1/demo/guest-sessions", json=kw,
                    headers=auth["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def _public(client, body=None):
    r = client.post("/api/v1/demo/guest-sessions/public", json=body or {})
    assert r.status_code == 201, r.text
    return r.json()


def _auth(minted):
    return {"headers": {"Authorization": f"Bearer {minted['credential']}"}}


def _mint_ab(client, demo_auth, **kw):
    ma = _mint(client, demo_auth, **kw)
    mb = _mint(client, demo_auth, **kw)
    assert ma["org_slug"] != mb["org_slug"]
    assert ma["org_slug"].startswith("guest-")
    return ma, mb, _auth(ma), _auth(mb)


def _intent(client, auth):
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False},
                    headers=auth["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def _expire(minted):
    auth_mod._GUEST_SESSIONS[hash_token(
        minted["credential"])]["expires_at"] = time.time() - 1


def _org_by_slug(slug):
    session = session_for("main")()
    try:
        return session.scalar(
            select(Organization).where(Organization.slug == slug))
    finally:
        session.close()


def _workflows_of(org_id):
    session = session_for("main")()
    try:
        return session.scalars(
            select(Workflow.id).where(Workflow.org_id == org_id)).all()
    finally:
        session.close()


# --- 12 A/B checks ------------------------------------------------------

def test_01_invisible_across_sessions_and_owner(client, demo_auth):
    made_owner = make_ready(client, demo_auth)
    _, _, ga, gb = _mint_ab(client, demo_auth)
    wa = _intent(client, ga)["workflow"]["id"]
    wb = _intent(client, gb)["workflow"]["id"]
    # Cross-session reads are 404 (no oracle, no leak)...
    assert client.get(f"/api/v1/workflows/{wb}",
                      headers=ga["headers"]).status_code == 404
    assert client.get(f"/api/v1/workflows/{wa}",
                      headers=gb["headers"]).status_code == 404
    # ... neither session sees the owner's workflows, nor vice versa.
    assert client.get(f"/api/v1/workflows/{made_owner['workflow']['id']}",
                      headers=ga["headers"]).status_code == 404
    assert client.get(f"/api/v1/workflows/{wa}",
                      headers=demo_auth["headers"]).status_code == 404
    # Listings are scoped to the caller's own ephemeral org.
    ids_a = [w["id"] for w in client.get(
        "/api/v1/workflows", headers=ga["headers"]).json()["data"]]
    ids_b = [w["id"] for w in client.get(
        "/api/v1/workflows", headers=gb["headers"]).json()["data"]]
    assert ids_a == [wa]
    assert ids_b == [wb]


def test_02_approve_isolated(client, demo_auth):
    _, _, ga, gb = _mint_ab(client, demo_auth)
    made_b = _intent(client, gb)
    assert made_b["approval_required"] is True
    wb = made_b["workflow"]["id"]
    approve = {"plan_hash": made_b["plan_hash"], "decided_by": "mallory"}
    # A cannot approve B's workflow (404, not 409/200)...
    r = client.post(f"/api/v1/workflows/{wb}/approve", json=approve,
                    headers=ga["headers"])
    assert r.status_code == 404
    # ... B approves its own normally.
    r = client.post(f"/api/v1/workflows/{wb}/approve", json=approve,
                    headers=gb["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "READY"


def test_03_execute_isolated(client, demo_auth):
    _, _, ga, gb = _mint_ab(client, demo_auth)
    wb = make_ready(client, gb)["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wb}/execute", headers=ga["headers"])
    assert r.status_code == 404
    wa = make_ready(client, ga)["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wa}/execute", headers=ga["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED"


def test_04_resume_isolated(client, demo_auth):
    _, _, ga, gb = _mint_ab(client, demo_auth)
    wb = make_ready(client, gb)["workflow"]["id"]
    # Cross-session resume is 404...
    r = client.post(f"/api/v1/workflows/{wb}/resume", headers=ga["headers"])
    assert r.status_code == 404
    # ... while a same-session resume on a READY workflow reaches the
    # state check (409), proving ownership routing works.
    wa = make_ready(client, ga)["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wa}/resume", headers=ga["headers"])
    assert r.status_code == 409


def test_05_cancel_isolated(client, demo_auth):
    _, _, ga, gb = _mint_ab(client, demo_auth)
    wb = make_ready(client, gb)["workflow"]["id"]
    wa = make_ready(client, ga)["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wb}/cancel", headers=ga["headers"])
    assert r.status_code == 404
    r = client.post(f"/api/v1/workflows/{wa}/cancel", headers=ga["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "CANCELLED"
    # B's workflow is untouched by A's cancel.
    r = client.get(f"/api/v1/workflows/{wb}", headers=gb["headers"])
    assert r.json()["workflow"]["state"] == "READY"


def test_06_evidence_isolated(client, demo_auth):
    _, _, ga, gb = _mint_ab(client, demo_auth)
    wb = make_ready(client, gb)["workflow"]["id"]
    wa = make_ready(client, ga)["workflow"]["id"]
    r = client.get(f"/api/v1/workflows/{wb}/evidence", headers=ga["headers"])
    assert r.status_code == 404
    r = client.get(f"/api/v1/workflows/{wa}/evidence", headers=ga["headers"])
    assert r.status_code == 200
    assert r.json()["chain"]["valid"] is True


def test_07_sse_isolated(client, demo_auth):
    ma, mb, ga, gb = _mint_ab(client, demo_auth)
    wa = make_ready(client, ga)["workflow"]["id"]
    wb = make_ready(client, gb)["workflow"]["id"]
    # A cannot mint a stream ticket for B's workflow...
    r = client.post(f"/api/v1/workflows/{wb}/stream-ticket",
                    headers=ga["headers"])
    assert r.status_code == 404
    # ... but can for its own.
    r = client.post(f"/api/v1/workflows/{wa}/stream-ticket",
                    headers=ga["headers"])
    assert r.status_code == 201, r.text
    ticket = r.json()["ticket"]
    # A's ticket is bound to A's workflow: redeeming it for B's fails 403.
    r = client.get(f"/api/v1/workflows/{wb}/events/stream?ticket={ticket}")
    assert r.status_code == 403
    # Streaming A's workflow with B's header credential yields the
    # in-stream not-found error (?token= is not honored; header path used).
    r = client.get(f"/api/v1/workflows/{wa}/events/stream",
                   headers=gb["headers"])
    assert r.status_code == 200
    assert "not found" in r.text
    assert '"seq"' not in r.text


def test_08_resources_isolated(client, demo_auth):
    _, _, ga, gb = _mint_ab(client, demo_auth)
    wa = make_ready(client, ga)["workflow"]["id"]
    wb = make_ready(client, gb)["workflow"]["id"]
    for wf, g in ((wa, ga), (wb, gb)):
        r = client.post(f"/api/v1/workflows/{wf}/execute",
                        headers=g["headers"])
        assert r.status_code == 200, r.text
    # Same logical names ("acme"), disjoint rows per session org.
    ra = client.get("/api/v1/demo/crm/resources",
                    params={"kind": "organization"},
                    headers=ga["headers"]).json()["resources"]
    rb = client.get("/api/v1/demo/crm/resources",
                    params={"kind": "organization"},
                    headers=gb["headers"]).json()["resources"]
    assert [o["name"] for o in ra] == ["acme"]
    assert [o["name"] for o in rb] == ["acme"]
    assert {o["id"] for o in ra}.isdisjoint({o["id"] for o in rb})
    # A run filter for the sibling run returns nothing cross-session.
    r = client.get("/api/v1/demo/crm/resources",
                   params={"kind": "organization", "workflow_id": wb},
                   headers=ga["headers"])
    assert r.json()["resources"] == []


def test_09_chaos_isolated_between_guests(client, demo_auth):
    _, _, ga, gb = _mint_ab(client, demo_auth)
    payload = {"target_connector": "demo-billing", "fault": "http500"}
    ra = client.post("/api/v1/demo/chaos", json=payload,
                     headers=ga["headers"])
    assert ra.status_code == 201, ra.text
    rule_a = ra.json()["id"]
    rb = client.post("/api/v1/demo/chaos", json=payload,
                     headers=gb["headers"])
    assert rb.status_code == 201, rb.text
    rule_b = rb.json()["id"]
    # Each guest lists exactly its own rule.
    la = client.get("/api/v1/demo/chaos", headers=ga["headers"])
    assert [row["id"] for row in la.json()["data"]] == [rule_a]
    lb = client.get("/api/v1/demo/chaos", headers=gb["headers"])
    assert [row["id"] for row in lb.json()["data"]] == [rule_b]
    # Cross-guest delete is a 404 (no existence oracle, no effect).
    assert client.delete(f"/api/v1/demo/chaos/{rule_a}",
                         headers=gb["headers"]).status_code == 404
    assert client.delete(f"/api/v1/demo/chaos/{rule_b}",
                         headers=ga["headers"]).status_code == 404
    # Owner rules stay invisible to guests (org-scoped list).
    r = client.post("/api/v1/demo/chaos", json=payload,
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    rule_owner = r.json()["id"]
    la = client.get("/api/v1/demo/chaos", headers=ga["headers"])
    assert [row["id"] for row in la.json()["data"]] == [rule_a]
    assert client.delete(f"/api/v1/demo/chaos/{rule_owner}",
                         headers=ga["headers"]).status_code == 404
    # Cleanup: everyone deletes their own.
    assert client.delete(f"/api/v1/demo/chaos/{rule_a}",
                         headers=ga["headers"]).status_code == 200
    assert client.delete(f"/api/v1/demo/chaos/{rule_b}",
                         headers=gb["headers"]).status_code == 200
    assert client.delete(f"/api/v1/demo/chaos/{rule_owner}",
                         headers=demo_auth["headers"]).status_code == 200


def test_10_expiry_is_per_session(client, demo_auth):
    ma, _, ga, gb = _mint_ab(client, demo_auth)
    _expire(ma)
    assert client.get("/api/v1/me",
                      headers=ga["headers"]).status_code == 403
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=ga["headers"])
    assert r.status_code == 403
    # Sibling session B is fully unaffected.
    assert client.get("/api/v1/me",
                      headers=gb["headers"]).status_code == 200
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=gb["headers"])
    assert r.status_code == 201, r.text


def test_11_concurrent_quotas_independent(client, demo_auth):
    ma = _mint(client, demo_auth, max_workflows=2, max_executes=1)
    mb = _mint(client, demo_auth, max_workflows=2, max_executes=1)
    ga, gb = _auth(ma), _auth(mb)
    first_a = make_ready(client, ga)
    second_a = make_ready(client, ga)
    # A exhausts its execute quota...
    r = client.post(
        f"/api/v1/workflows/{first_a['workflow']['id']}/execute",
        headers=ga["headers"])
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/v1/workflows/{second_a['workflow']['id']}/execute",
        headers=ga["headers"])
    assert r.status_code == 410
    assert r.json()["code"] == "QUOTA_EXHAUSTED"
    # ... while B's identical quotas are untouched.
    first_b = make_ready(client, gb)
    r = client.post(f"/api/v1/workflows/{first_b['workflow']['id']}/execute",
                    headers=gb["headers"])
    assert r.status_code == 200, r.text
    # Intent quotas are likewise per-session.
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=ga["headers"])
    assert r.status_code == 410
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=gb["headers"])
    assert r.status_code == 201, r.text


def test_12_expiry_sweep_cleans_only_expired_org(client, demo_auth):
    from reversa_api.connectors.services import DemoStore

    made_owner = make_ready(client, demo_auth)
    ma = _mint(client, demo_auth)
    mb = _mint(client, demo_auth)
    ga, gb = _auth(ma), _auth(mb)
    wa = make_ready(client, ga)["workflow"]["id"]
    wb = make_ready(client, gb)["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wa}/execute", headers=ga["headers"])
    assert r.status_code == 200, r.text
    org_a = _org_by_slug(ma["org_slug"])
    org_b = _org_by_slug(mb["org_slug"])
    assert org_a is not None and org_b is not None
    assert len(DemoStore("crm").list(org_a.id, kind="organization")) == 1

    _expire(ma)
    report = auth_mod.sweep_expired_guests()
    assert report["errors"] == []
    assert report["sessions"] == 1
    assert [s["org_id"] for s in report["swept"]] == [org_a.id]
    assert report["swept"][0]["deleted"] is True
    assert auth_mod._LAST_SWEEP_ERRORS == []

    # A's org, workflows, and demo rows are gone...
    assert _org_by_slug(ma["org_slug"]) is None
    assert _workflows_of(org_a.id) == []
    assert DemoStore("crm").list(org_a.id, kind="organization") == []
    assert client.get(f"/api/v1/workflows/{wa}",
                      headers=gb["headers"]).status_code == 404
    # ... B's and the owner's state is fully intact.
    assert _org_by_slug(mb["org_slug"]) is not None
    assert _workflows_of(org_b.id) == [wb]
    assert client.get(f"/api/v1/workflows/{wb}",
                      headers=gb["headers"]).status_code == 200
    assert client.get(f"/api/v1/workflows/{made_owner['workflow']['id']}",
                      headers=demo_auth["headers"]).status_code == 200
    # Lazy path: a request with an expired credential also sweeps its org.
    mc = _mint(client, demo_auth)
    org_c = _org_by_slug(mc["org_slug"])
    _expire(mc)
    assert client.get("/api/v1/me",
                      headers=_auth(mc)["headers"]).status_code == 403
    assert _org_by_slug(mc["org_slug"]) is None
    assert _workflows_of(org_c.id) == []
    assert _org_by_slug(mb["org_slug"]) is not None  # sibling still intact


# --- PUBLIC mint endpoint -------------------------------------------------

def test_public_mint_no_auth_fixed_tiny_quotas(client):
    r = client.post("/api/v1/demo/guest-sessions/public", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["credential"].startswith("rev_guest_")
    assert body["org_slug"].startswith("guest-")
    assert body["max_workflows"] == PUBLIC_GUEST_MAX_WORKFLOWS == 2
    assert body["max_executes"] == PUBLIC_GUEST_MAX_EXECUTES == 2
    r = client.get("/api/v1/me",
                   headers=_auth(body)["headers"])
    assert r.status_code == 200
    me = r.json()
    assert me["org_slug"] == body["org_slug"]
    assert me["is_demo"] is True
    assert me["actor"] == f"guest:{body['session_id']}"


def test_public_mint_quota_override_rejected_422(client):
    for payload in ({"max_workflows": 5}, {"max_executes": 9},
                    {"max_workflows": 1, "max_executes": 1}):
        r = client.post("/api/v1/demo/guest-sessions/public", json=payload)
        assert r.status_code == 422, (payload, r.text)


def test_public_guest_flow_quota_and_chaos(client, demo_auth):
    body = _public(client)
    g = _auth(body)
    # Tiny lifetime quota: exactly 2 intents, then 410.
    for _ in range(2):
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=g["headers"])
        assert r.status_code == 201, r.text
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=g["headers"])
    assert r.status_code == 410
    assert r.json()["code"] == "QUOTA_EXHAUSTED"
    # Chaos allowed for public guests (own ephemeral org only).
    payload = {"target_connector": "demo-billing", "fault": "http500"}
    r = client.post("/api/v1/demo/chaos", json=payload,
                    headers=g["headers"])
    assert r.status_code == 201, r.text
    # Invisible vs an owner-minted session and vice versa.
    owner_guest = _auth(_mint(client, demo_auth))
    assert client.get("/api/v1/workflows",
                      headers=g["headers"]).json()["data"]
    other = make_ready(client, owner_guest)["workflow"]["id"]
    assert client.get(f"/api/v1/workflows/{other}",
                      headers=g["headers"]).status_code == 404


def test_public_mint_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(guest_routes, "PUBLIC_MINT_MAX_PER_WINDOW", 2)
    monkeypatch.setattr(guest_routes, "PUBLIC_MINT_WINDOW_SECONDS", 60)
    assert client.post("/api/v1/demo/guest-sessions/public",
                       json={}).status_code == 201
    assert client.post("/api/v1/demo/guest-sessions/public",
                       json={}).status_code == 201
    r = client.post("/api/v1/demo/guest-sessions/public", json={})
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"
    assert r.json()["retryable"] is True
    assert int(r.headers["Retry-After"]) >= 1
    guest_routes.reset_public_mint_state()
    assert client.post("/api/v1/demo/guest-sessions/public",
                       json={}).status_code == 201


def test_public_expiry_swept(client):
    body = _public(client)
    g = _auth(body)
    assert make_ready(client, g)["workflow"]["id"]
    org = _org_by_slug(body["org_slug"])
    assert org is not None
    _expire(body)
    report = auth_mod.sweep_expired_guests()
    assert report["errors"] == []
    assert _org_by_slug(body["org_slug"]) is None
    assert _workflows_of(org.id) == []
    assert client.get("/api/v1/me",
                      headers=g["headers"]).status_code == 403
