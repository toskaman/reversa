"""Negative matrix: approve / cancel / evidence / resume / guest.

Pins the failure contract for the workflow lifecycle: 401 anonymous,
403 forbidden, 404 unknown-or-cross-tenant, 409 state conflict,
410 expired/quota-exhausted, 422 schema rejection. (AGENT-06, cycle 3.)
"""

import datetime as dt
import time

import pytest
from sqlalchemy import select

from reversa_api import auth as auth_mod
from reversa_api import ratelimit as ratelimit_mod
from reversa_api.auth import hash_token
from reversa_api.db import session_for
from reversa_api.models import ActionRun, Approval, Workflow, utcnow

from .conftest import INTENT, make_ready


@pytest.fixture(autouse=True)
def _fresh_memory_state():
    auth_mod.reset_guest_state()
    ratelimit_mod.reset_rate_limit_state()
    yield
    auth_mod.reset_guest_state()
    ratelimit_mod.reset_rate_limit_state()


def _awaiting(client, auth):
    """A fresh workflow in AWAITING_APPROVAL (INTENT always needs approval)."""
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False},
                    headers=auth["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["approval_required"] is True
    return body


def _expire_approval(wf_id):
    session = session_for("main")()
    try:
        approval = session.scalar(
            select(Approval).where(Approval.workflow_id == wf_id,
                                   Approval.status == "PENDING"))
        assert approval is not None
        approval.expires_at = utcnow() - dt.timedelta(minutes=1)
        session.commit()
    finally:
        session.close()


def _set_workflow_state(wf_id, state):
    session = session_for("main")()
    try:
        wf = session.get(Workflow, wf_id)
        assert wf is not None
        wf.state = state
        session.commit()
    finally:
        session.close()


def _set_first_action_state(wf_id, state):
    session = session_for("main")()
    try:
        action = session.scalar(
            select(ActionRun).where(ActionRun.workflow_id == wf_id)
            .order_by(ActionRun.seq))
        assert action is not None
        action.state = state
        session.commit()
        return action.seq
    finally:
        session.close()


def _mint_guest(client, auth, **kw):
    r = client.post("/api/v1/demo/guest-sessions", json=kw,
                    headers=auth["headers"])
    assert r.status_code == 201, r.text
    minted = r.json()
    return minted, {"headers": {"Authorization": f"Bearer {minted['credential']}"}}


# --- approve ---------------------------------------------------------------

class TestApproveNegatives:
    def test_approve_unknown_workflow_404(self, client, demo_auth):
        r = client.post("/api/v1/workflows/999999/approve",
                        json={"plan_hash": "x"}, headers=demo_auth["headers"])
        assert r.status_code == 404
        assert r.json()["detail"] == "workflow not found"

    def test_approve_cross_tenant_404(self, client, demo_auth, real_auth):
        made = _awaiting(client, demo_auth)
        wf_id = made["workflow"]["id"]
        r = client.post(f"/api/v1/workflows/{wf_id}/approve",
                        json={"plan_hash": made["plan_hash"]},
                        headers=real_auth["headers"])
        assert r.status_code == 404

    def test_approve_anonymous_401(self, client, demo_auth):
        made = _awaiting(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/approve",
                        json={"plan_hash": made["plan_hash"]})
        assert r.status_code == 401

    def test_approve_wrong_hash_409(self, client, demo_auth):
        made = _awaiting(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/approve",
                        json={"plan_hash": "0" * 64},
                        headers=demo_auth["headers"])
        assert r.status_code == 409
        assert "plan changed" in r.json()["detail"]

    def test_approve_missing_hash_422(self, client, demo_auth):
        made = _awaiting(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/approve",
                        json={}, headers=demo_auth["headers"])
        assert r.status_code == 422

    def test_approve_twice_second_409(self, client, demo_auth):
        made = _awaiting(client, demo_auth)
        wf_id = made["workflow"]["id"]
        first = client.post(f"/api/v1/workflows/{wf_id}/approve",
                            json={"plan_hash": made["plan_hash"],
                                  "decided_by": "tester"},
                            headers=demo_auth["headers"])
        assert first.status_code == 200, first.text
        second = client.post(f"/api/v1/workflows/{wf_id}/approve",
                             json={"plan_hash": made["plan_hash"]},
                             headers=demo_auth["headers"])
        assert second.status_code == 409
        assert "nothing to approve" in second.json()["detail"]

    def test_approve_expired_410_then_409(self, client, demo_auth):
        made = _awaiting(client, demo_auth)
        wf_id = made["workflow"]["id"]
        _expire_approval(wf_id)
        r = client.post(f"/api/v1/workflows/{wf_id}/approve",
                        json={"plan_hash": made["plan_hash"]},
                        headers=demo_auth["headers"])
        assert r.status_code == 410
        assert "expired" in r.json()["detail"]
        # The approval row is consumed as EXPIRED: no second chance.
        again = client.post(f"/api/v1/workflows/{wf_id}/approve",
                            json={"plan_hash": made["plan_hash"]},
                            headers=demo_auth["headers"])
        assert again.status_code == 409
        events = client.get(f"/api/v1/workflows/{wf_id}/events",
                            headers=demo_auth["headers"]).json()["data"]
        assert any(e["type"] == "approval.expired" for e in events)


# --- cancel ----------------------------------------------------------------

class TestCancelNegatives:
    def test_cancel_unknown_404(self, client, demo_auth):
        r = client.post("/api/v1/workflows/999999/cancel",
                        headers=demo_auth["headers"])
        assert r.status_code == 404

    def test_cancel_cross_tenant_404(self, client, demo_auth, real_auth):
        made = make_ready(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/cancel",
                        headers=real_auth["headers"])
        assert r.status_code == 404

    def test_cancel_anonymous_401(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/cancel")
        assert r.status_code == 401

    def test_cancel_completed_409(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        wf_id = made["workflow"]["id"]
        r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                        headers=demo_auth["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["workflow"]["state"] == "COMPLETED"
        r = client.post(f"/api/v1/workflows/{wf_id}/cancel",
                        headers=demo_auth["headers"])
        assert r.status_code == 409
        assert "already COMPLETED" in r.json()["detail"]

    def test_cancel_twice_second_409(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        wf_id = made["workflow"]["id"]
        first = client.post(f"/api/v1/workflows/{wf_id}/cancel",
                            headers=demo_auth["headers"])
        assert first.status_code == 200, first.text
        assert first.json()["workflow"]["state"] == "CANCELLED"
        second = client.post(f"/api/v1/workflows/{wf_id}/cancel",
                             headers=demo_auth["headers"])
        assert second.status_code == 409
        assert "already CANCELLED" in second.json()["detail"]

    def test_cancel_compensating_409(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        wf_id = made["workflow"]["id"]
        _set_workflow_state(wf_id, "COMPENSATING")
        r = client.post(f"/api/v1/workflows/{wf_id}/cancel",
                        headers=demo_auth["headers"])
        assert r.status_code == 409
        assert "compensation in progress" in r.json()["detail"]

    def test_cancel_inflight_action_409(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        wf_id = made["workflow"]["id"]
        seq = _set_first_action_state(wf_id, "EXECUTING")
        r = client.post(f"/api/v1/workflows/{wf_id}/cancel",
                        headers=demo_auth["headers"])
        assert r.status_code == 409
        assert "in flight" in r.json()["detail"]
        assert str(seq) in r.json()["detail"]
        # Nothing was cancelled: the workflow is still READY.
        wf = client.get(f"/api/v1/workflows/{wf_id}",
                        headers=demo_auth["headers"]).json()["workflow"]
        assert wf["state"] == "READY"


# --- resume ----------------------------------------------------------------

class TestResumeNegatives:
    def test_resume_unknown_404(self, client, demo_auth):
        r = client.post("/api/v1/workflows/999999/resume",
                        headers=demo_auth["headers"])
        assert r.status_code == 404

    def test_resume_cross_tenant_404(self, client, demo_auth, real_auth):
        made = make_ready(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/resume",
                        headers=real_auth["headers"])
        assert r.status_code == 404

    def test_resume_anonymous_401(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/resume")
        assert r.status_code == 401

    def test_resume_ready_409(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/resume",
                        headers=demo_auth["headers"])
        assert r.status_code == 409
        assert "only interrupted" in r.json()["detail"]

    def test_resume_awaiting_approval_409(self, client, demo_auth):
        made = _awaiting(client, demo_auth)
        r = client.post(f"/api/v1/workflows/{made['workflow']['id']}/resume",
                        headers=demo_auth["headers"])
        assert r.status_code == 409

    def test_resume_completed_409(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        wf_id = made["workflow"]["id"]
        r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                        headers=demo_auth["headers"])
        assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                        headers=demo_auth["headers"])
        assert r.status_code == 409
        assert "nothing to resume" in r.json()["detail"]

    def test_resume_cancelled_409(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        wf_id = made["workflow"]["id"]
        r = client.post(f"/api/v1/workflows/{wf_id}/cancel",
                        headers=demo_auth["headers"])
        assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/workflows/{wf_id}/resume",
                        headers=demo_auth["headers"])
        assert r.status_code == 409


# --- evidence --------------------------------------------------------------

class TestEvidenceNegatives:
    def test_evidence_unknown_404(self, client, demo_auth):
        r = client.get("/api/v1/workflows/999999/evidence",
                       headers=demo_auth["headers"])
        assert r.status_code == 404

    def test_evidence_cross_tenant_404(self, client, demo_auth, real_auth):
        made = make_ready(client, demo_auth)
        r = client.get(f"/api/v1/workflows/{made['workflow']['id']}/evidence",
                       headers=real_auth["headers"])
        assert r.status_code == 404

    def test_evidence_anonymous_401(self, client, demo_auth):
        made = make_ready(client, demo_auth)
        r = client.get(f"/api/v1/workflows/{made['workflow']['id']}/evidence")
        assert r.status_code == 401

    def test_evidence_unknown_format_falls_back_to_json(self, client,
                                                        demo_auth):
        # Documents current behavior: any non-html format returns the bundle.
        made = make_ready(client, demo_auth)
        r = client.get(f"/api/v1/workflows/{made['workflow']['id']}/evidence",
                       params={"format": "xml"}, headers=demo_auth["headers"])
        assert r.status_code == 200
        assert "chain" in r.json()


# --- guest -----------------------------------------------------------------

class TestGuestNegatives:
    def test_guest_intent_quota_410(self, client, demo_auth):
        _, guest = _mint_guest(client, demo_auth, max_workflows=1)
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=guest["headers"])
        assert r.status_code == 201, r.text
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=guest["headers"])
        assert r.status_code == 410
        assert r.json()["code"] == "QUOTA_EXHAUSTED"

    def test_guest_execute_quota_410(self, client, demo_auth):
        _, guest = _mint_guest(client, demo_auth, max_workflows=2,
                               max_executes=1)
        first = make_ready(client, guest)
        second = make_ready(client, guest)
        r = client.post(f"/api/v1/workflows/{first['workflow']['id']}/execute",
                        headers=guest["headers"])
        assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/workflows/{second['workflow']['id']}/execute",
                        headers=guest["headers"])
        assert r.status_code == 410
        assert r.json()["code"] == "QUOTA_EXHAUSTED"

    def test_guest_cannot_mint_or_rotate_403(self, client, demo_auth):
        _, guest = _mint_guest(client, demo_auth)
        r = client.post("/api/v1/demo/guest-sessions", json={},
                        headers=guest["headers"])
        assert r.status_code == 403
        assert client.post("/api/v1/demo/tokens", json={"name": "x"},
                           headers=guest["headers"]).status_code == 403
        assert client.get("/api/v1/demo/tokens",
                          headers=guest["headers"]).status_code == 403
        assert client.delete("/api/v1/demo/tokens/test",
                             headers=guest["headers"]).status_code == 403

    def test_guest_mint_validation_422(self, client, demo_auth):
        r = client.post("/api/v1/demo/guest-sessions",
                        json={"max_workflows": 999},
                        headers=demo_auth["headers"])
        assert r.status_code == 422
        r = client.post("/api/v1/demo/guest-sessions",
                        json={"max_executes": 0},
                        headers=demo_auth["headers"])
        assert r.status_code == 422

    def test_expired_guest_forbidden_403(self, client, demo_auth):
        minted, guest = _mint_guest(client, demo_auth)
        auth_mod._GUEST_SESSIONS[hash_token(
            minted["credential"])]["expires_at"] = time.time() - 1
        assert client.get("/api/v1/me",
                          headers=guest["headers"]).status_code == 403
        r = client.post("/api/v1/intents",
                        json={"intent": INTENT, "use_ai": False},
                        headers=guest["headers"])
        assert r.status_code == 403
