"""Red-team V5 regression tests (RT-V5-02/03/04/05/08/10 fixes).

Each test pins a finding from .agents/reviews/redteam-v5.md:
untrusted stored JSON must verify INVALID (not 500), stream tickets must
not burn on cross-workflow use, approval labels and plan inputs must be
bounded, unknown plan inputs must be stripped, redaction must cover
dotted tokens.
"""

import pytest
from fastapi.testclient import TestClient  # noqa: F401 (fixture typing)
from sqlalchemy import select

from .conftest import INTENT, make_ready
from reversa_api.db import session_for
from reversa_api.evidence import redact, verify_chain_rows
from reversa_api.models import Event
from reversa_api.planner.validate import validate_plan
from reversa_api.routes.workflows import _redeem_stream_ticket


def _provision_step(n_users=1, email="a@example.io", extra=None):
    inputs = {
        "workspace": "acme",
        "users": [{"email": email, "name": "U%d" % i} for i in range(n_users)],
    }
    if extra:
        inputs.update(extra)
    return {
        "action_type": "identity.provision_users",
        "connector_id": "demo-identity",
        "inputs": inputs,
        "depends_on": [],
    }


def test_corrupt_event_payload_verifies_invalid(client, demo_auth):
    """RT-V5-03: corrupt payload_json -> INVALID verdict, not an exception."""
    body = make_ready(client, demo_auth)
    wf_id = body["workflow"]["id"]
    session = session_for("main")()
    try:
        row = session.scalars(
            select(Event).where(Event.workflow_id == wf_id).order_by(Event.seq)
        ).first()
        assert row is not None
        row.payload_json = "{corrupt"
        session.commit()
        rows = session.scalars(
            select(Event).where(Event.workflow_id == wf_id).order_by(Event.seq)
        ).all()
        ok, bad_seq, message = verify_chain_rows(rows)
    finally:
        session.close()
    assert ok is False
    assert bad_seq == 1
    assert "seq 1" in message


def test_corrupt_event_payload_export_invalid_not_500(client, demo_auth):
    """RT-V5-03: evidence export of a corrupt chain -> 200 + INVALID badge."""
    body = make_ready(client, demo_auth)
    wf_id = body["workflow"]["id"]
    session = session_for("main")()
    try:
        row = session.scalars(
            select(Event).where(Event.workflow_id == wf_id).order_by(Event.seq)
        ).first()
        row.payload_json = "{corrupt"
        session.commit()
    finally:
        session.close()
    r = client.get(f"/api/v1/workflows/{wf_id}/evidence", headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["chain"]["valid"] is False


def test_stream_ticket_cross_workflow_does_not_burn(client, demo_auth):
    """RT-V5-08: cross-workflow use -> 403 but the ticket stays redeemable."""
    body_a = make_ready(client, demo_auth)
    body_b = make_ready(client, demo_auth)
    wf_a = body_a["workflow"]["id"]
    wf_b = body_b["workflow"]["id"]
    assert wf_a != wf_b
    r = client.post(f"/api/v1/workflows/{wf_a}/stream-ticket",
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    ticket = r.json()["ticket"]
    with pytest.raises(Exception, match="another workflow"):
        _redeem_stream_ticket(ticket, wf_b)
    org = _redeem_stream_ticket(ticket, wf_a)
    assert org.org_id == demo_auth["org_id"]


def test_decided_by_length_bounded(client, demo_auth):
    """RT-V5-04: unbounded approval label -> 422."""
    r = client.post("/api/v1/intents", json={"intent": INTENT, "use_ai": False},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["approval_required"] is True
    wf_id = body["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/approve",
                    json={"plan_hash": body["plan_hash"], "decided_by": "x" * 500},
                    headers=demo_auth["headers"])
    assert r.status_code == 422, r.text


def test_provision_users_count_capped():
    """RT-V5-05: 5000 users must be rejected; a small team stays valid."""
    _, _, issues = validate_plan({"steps": [_provision_step(n_users=5000)]})
    assert any(i.code == "TOO_MANY_USERS" for i in issues)
    _, _, issues = validate_plan({"steps": [_provision_step(n_users=2)]})
    assert [i for i in issues if "users" in i.field] == []


def test_provision_user_email_length_capped():
    """RT-V5-05: absurd email length must be rejected (PG String(128))."""
    _, _, issues = validate_plan(
        {"steps": [_provision_step(email="a" * 300 + "@example.io")]})
    assert issues != []


def test_customer_blob_capped(client, demo_auth):
    """RT-V5-05: oversized customer dict -> 422, small stays 201."""
    big = {"blob": "x" * 100000}
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False, "customer": big},
                    headers=demo_auth["headers"])
    assert r.status_code == 422, r.text
    small = {"company_name": "Acme"}
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False, "customer": small},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text


def test_unknown_input_keys_stripped():
    """RT-V5-10: model-injected extras must not survive normalization."""
    normalized, _, issues = validate_plan(
        {"steps": [_provision_step(extra={"injected_extra": "ZZZ"})]})
    assert issues == []
    assert "injected_extra" not in normalized[0]["inputs"]
    assert normalized[0]["inputs"]["workspace"] == "acme"


def test_redact_covers_dotted_tokens():
    """RT-V5-02: JWT-shaped secrets must be redacted; text/URLs untouched."""
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw0c"
    assert redact({"note": jwt}) == {"note": "***REDACTED***"}
    assert redact("just a plain sentence here") == "just a plain sentence here"
    assert redact("https://217.69.7.155.nip.io") == "https://217.69.7.155.nip.io"
