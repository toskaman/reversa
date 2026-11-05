"""Test isolation: every test gets a fresh data dir (6 sqlite files)."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# Fresh, unique data dir per test BEFORE any reversa_api import caches engines.
os.environ.setdefault("REVERSA_DATA_DIR", os.path.join("tests", ".tmpdata-default"))

import reversa_api.connectors  # noqa: E402,F401  (register connectors)
from reversa_api import main as app_module  # noqa: E402
from reversa_api.auth import hash_token  # noqa: E402
from reversa_api.db import init_db, reset_engine_cache, session_for  # noqa: E402
from reversa_api.config import settings  # noqa: E402
from reversa_api.models import ApiToken, Organization  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path):
    original = settings.data_dir
    object.__setattr__(settings, "data_dir", str(tmp_path))  # frozen dataclass
    reset_engine_cache()
    init_db()
    yield tmp_path
    reset_engine_cache()
    object.__setattr__(settings, "data_dir", original)


@pytest.fixture()
def client(fresh_db):
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture()
def demo_auth(fresh_db):
    """A demo org + bearer token (chaos allowed)."""
    slug = f"demo-{uuid.uuid4().hex[:8]}"
    token = f"rev_test_{uuid.uuid4().hex}"
    session = session_for("main")()
    try:
        org = Organization(slug=slug, name="Test Demo", is_demo=1)
        session.add(org)
        session.commit()
        session.refresh(org)
        session.add(ApiToken(org_id=org.id, name="test", token_hash=hash_token(token)))
        session.commit()
        return {"headers": {"Authorization": f"Bearer {token}"},
                "org_id": org.id, "slug": slug}
    finally:
        session.close()


@pytest.fixture()
def real_auth(fresh_db):
    """A NON-demo org (chaos forbidden)."""
    slug = f"real-{uuid.uuid4().hex[:8]}"
    token = f"rev_test_{uuid.uuid4().hex}"
    session = session_for("main")()
    try:
        org = Organization(slug=slug, name="Test Real", is_demo=0)
        session.add(org)
        session.commit()
        session.refresh(org)
        session.add(ApiToken(org_id=org.id, name="test", token_hash=hash_token(token)))
        session.commit()
        return {"headers": {"Authorization": f"Bearer {token}"},
                "org_id": org.id, "slug": slug}
    finally:
        session.close()


INTENT = ("Onboard Acme Corporation as an enterprise customer. Create their "
          "workspace, provision accounts, configure support, prepare billing, "
          "assign an account manager and verify everything.")


def make_ready(client: TestClient, auth: dict, intent: str = INTENT) -> dict:
    r = client.post("/api/v1/intents", json={"intent": intent, "use_ai": False},
                    headers=auth["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    wf_id = body["workflow"]["id"]
    if body["approval_required"]:
        r = client.post(f"/api/v1/workflows/{wf_id}/approve",
                        json={"plan_hash": body["plan_hash"], "decided_by": "tester"},
                        headers=auth["headers"])
        assert r.status_code == 200, r.text
    return body
