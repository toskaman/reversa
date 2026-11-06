"""Red-team V6 regression tests (RT-V5-01/04/05b/07/10 remainders).

Pins the RC8 fixes on top of the V5 report (.agents/reviews/redteam-v5.md):
credential-mint rate limiting, bounded public-mint windows and SSE
tickets, authenticated approver attribution, plan step cap, and strict
int/bool type separation.
"""

from fastapi.testclient import TestClient  # noqa: F401 (fixture typing)

from .conftest import INTENT, make_ready
from reversa_api.connectors.github import GithubConnector
from reversa_api.connectors.sdk import REGISTRY, register
from reversa_api.planner.validate import MAX_PLAN_STEPS, validate_plan
from reversa_api.ratelimit import _TIERS, reset_rate_limit_state
from reversa_api.routes.guest_sessions import (
    _PUBLIC_WINDOWS,
    _check_public_mint,
    reset_public_mint_state,
)
from reversa_api.routes.workflows import _SSE_TICKETS, reset_sse_ticket_state


def _provision_step(**kw):
    step = {
        "action_type": "identity.provision_users",
        "connector_id": "demo-identity",
        "inputs": {"workspace": "acme",
                   "users": [{"email": "a@example.io"}]},
        "depends_on": [],
    }
    step.update(kw)
    return step


def test_owner_guest_mint_rate_limited(client, demo_auth, monkeypatch):
    """RT-V5-01: owner guest-mint cannot rotate buckets at full speed."""
    monkeypatch.setitem(_TIERS, "mint", (2, 60))
    reset_rate_limit_state()
    try:
        for _ in range(2):
            r = client.post("/api/v1/demo/guest-sessions", json={},
                            headers=demo_auth["headers"])
            assert r.status_code == 201, r.text
        r = client.post("/api/v1/demo/guest-sessions", json={},
                        headers=demo_auth["headers"])
        assert r.status_code == 429, r.text
        assert r.json()["code"] == "RATE_LIMITED"
    finally:
        reset_rate_limit_state()


def test_owner_token_mint_rate_limited(client, demo_auth, monkeypatch):
    """RT-V5-01: owner token rotation mint shares the mint tier."""
    monkeypatch.setitem(_TIERS, "mint", (2, 60))
    reset_rate_limit_state()
    try:
        for i in range(2):
            r = client.post("/api/v1/demo/tokens", json={"name": f"rt6-{i}"},
                            headers=demo_auth["headers"])
            assert r.status_code == 201, r.text
        r = client.post("/api/v1/demo/tokens", json={"name": "rt6-over"},
                        headers=demo_auth["headers"])
        assert r.status_code == 429, r.text
    finally:
        reset_rate_limit_state()


def test_public_mint_windows_bounded(monkeypatch):
    """RT-V5-07: the per-IP public-mint store cannot grow without limit."""
    monkeypatch.setattr("reversa_api.routes.guest_sessions._PUBLIC_MAX_WINDOWS", 5)
    reset_public_mint_state()
    try:
        for i in range(8):
            ok, _ = _check_public_mint(f"10.9.8.{i}", 1_700_000_000.0)
            assert ok is True
        assert len(_PUBLIC_WINDOWS) <= 5
    finally:
        reset_public_mint_state()


def test_sse_tickets_bounded_oldest_evicted(client, demo_auth, monkeypatch):
    """RT-V5-07: open SSE tickets are capped; oldest go first."""
    monkeypatch.setattr("reversa_api.routes.workflows.SSE_TICKET_MAX_OPEN", 3)
    reset_sse_ticket_state()
    try:
        body = make_ready(client, demo_auth)
        wf_id = body["workflow"]["id"]
        minted = []
        for _ in range(5):
            r = client.post(f"/api/v1/workflows/{wf_id}/stream-ticket",
                            headers=demo_auth["headers"])
            assert r.status_code == 201, r.text
            minted.append(r.json()["ticket"])
        assert len(_SSE_TICKETS) <= 3
        assert minted[0] not in _SSE_TICKETS  # oldest evicted
        assert minted[-1] in _SSE_TICKETS  # newest kept
    finally:
        reset_sse_ticket_state()


def test_approve_records_authenticated_actor(client, demo_auth):
    """RT-V5-04: durable approver is the credential actor, not the label."""
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    wf_id = body["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/approve",
                    json={"plan_hash": body["plan_hash"],
                          "decided_by": "ceo-victim"},
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    r = client.get(f"/api/v1/workflows/{wf_id}/evidence",
                   headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    bundle = r.json()
    assert bundle["approvals"][0]["decided_by"] == "token:test"
    granted = [e for e in bundle["events"] if e["type"] == "approval.granted"]
    assert len(granted) == 1
    assert granted[0]["actor"] == "token:test"
    assert granted[0]["payload"]["decided_by"] == "token:test"
    assert granted[0]["payload"]["decided_by_label"] == "ceo-victim"


def test_plan_steps_capped():
    """RT-V5-05b: oversized plans rejected; the cap itself stays valid."""
    steps = [_provision_step() for _ in range(MAX_PLAN_STEPS + 1)]
    _, _, issues = validate_plan({"steps": steps})
    assert any(i.code == "TOO_MANY_STEPS" for i in issues)
    steps = [_provision_step() for _ in range(MAX_PLAN_STEPS)]
    _, _, issues = validate_plan({"steps": steps})
    assert issues == []


def test_bool_rejected_for_int_and_deps():
    """RT-V5-10: True/False are not valid ints, in inputs or depends_on."""
    prev = REGISTRY.get(GithubConnector.id)
    register(GithubConnector(allowed_repos=["o/r"]))
    try:
        step = {"action_type": "github.add_labels",
                "connector_id": GithubConnector.id,
                "inputs": {"repo": "o/r", "issue_number": True,
                           "labels": ["a"]},
                "depends_on": []}
        _, _, issues = validate_plan({"steps": [step]})
        assert any(i.code == "BAD_INPUT_TYPE" and "issue_number" in i.field
                   for i in issues), [i.to_dict() for i in issues]
        step["inputs"]["issue_number"] = 3
        _, _, issues = validate_plan({"steps": [step]})
        assert issues == [], [i.to_dict() for i in issues]
    finally:
        if prev is None:
            REGISTRY.pop(GithubConnector.id, None)
        else:
            REGISTRY[GithubConnector.id] = prev
    steps = [_provision_step(), _provision_step(depends_on=[True])]
    _, _, issues = validate_plan({"steps": steps})
    assert any(i.code == "BAD_DEPS" for i in issues)
