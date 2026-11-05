"""V5 (AGENT-09): rotation du credential demo historique.

Audit: seed_demo_org() conserve toute ligne ApiToken existante, ApiToken
n'a ni expiry ni flag revoked, et DELETE = revocation. Un credential
historique reste donc valide jusqu'a suppression de sa ligne + blocklist
de son hash (une restauration DB ne doit pas le ressusciter).

Ces tests n'embarquent AUCUNE valeur historique reelle: chaque credential
est genere aleatoirement par test, seuls des hashes SHA-256 transitent
par la blocklist, et l'inventaire ne contient jamais de plaintext.
"""

import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

from reversa_api import auth as auth_mod
from reversa_api import ratelimit as ratelimit_mod
from reversa_api.auth import hash_token, revoke_historic_demo_tokens
from reversa_api.db import session_for
from reversa_api.models import ApiToken, Organization
from reversa_api.routes import guest_sessions as guest_routes

from .conftest import INTENT


@pytest.fixture(autouse=True)
def _fresh_memory_state():
    auth_mod.reset_guest_state()
    auth_mod.reset_revoked_state()
    ratelimit_mod.reset_rate_limit_state()
    guest_routes.reset_public_mint_state()
    yield
    auth_mod.reset_guest_state()
    auth_mod.reset_revoked_state()
    ratelimit_mod.reset_rate_limit_state()
    guest_routes.reset_public_mint_state()


def _seed_historic_org() -> dict:
    """Cree un org demo avec un credential historique (nom seed 'demo')."""
    slug = f"hist-{uuid.uuid4().hex[:8]}"
    plain = "rev_demo_" + secrets.token_urlsafe(24)
    session = session_for("main")()
    try:
        org = Organization(slug=slug, name="Historic Demo", is_demo=1)
        session.add(org)
        session.commit()
        session.refresh(org)
        session.add(ApiToken(org_id=org.id, name="demo",
                             token_hash=hash_token(plain)))
        session.commit()
        org_id = org.id
    finally:
        session.close()
    return {"slug": slug, "org_id": org_id, "plain": plain,
            "headers": {"Authorization": f"Bearer {plain}"},
            "hash": hash_token(plain)}


def _rotate_to_new(client: TestClient, historic: dict) -> dict:
    """Overlap: mint un remplacant via l'API, les deux sont valides."""
    r = client.post("/api/v1/demo/tokens", json={"name": "rotated-v5"},
                    headers=historic["headers"])
    assert r.status_code == 201, r.text
    new_plain = r.json()["credential"]
    assert new_plain.startswith("rev_demo_")
    new = {"plain": new_plain,
           "headers": {"Authorization": f"Bearer {new_plain}"},
           "hash": hash_token(new_plain)}
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 200
    assert client.get("/api/v1/me",
                      headers=new["headers"]).status_code == 200
    return new


def test_v5_historic_stays_valid_until_revoked_then_old_refused(client):
    historic = _seed_historic_org()
    # Audit: avant revocation, l'historique est accepte (pas d'expiry).
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 200
    new = _rotate_to_new(client, historic)
    # Revocation sure: DELETE + blocklist, depuis le nouveau credential.
    out = revoke_historic_demo_tokens(historic["slug"],
                                      current_hash=new["hash"])
    assert out == {"revoked": ["demo"], "remaining": 1}
    # Ancien refuse partout avec le 403 generique.
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 403
    assert client.post("/api/v1/intents",
                       json={"intent": INTENT, "use_ai": False},
                       headers=historic["headers"]).status_code == 403
    assert client.get("/api/v1/demo/tokens",
                      headers=historic["headers"]).status_code == 403
    # Nouveau toujours valide.
    assert client.get("/api/v1/me",
                      headers=new["headers"]).status_code == 200
    # Idempotent: second appel ne change rien.
    out2 = revoke_historic_demo_tokens(historic["slug"],
                                       current_hash=new["hash"])
    assert out2 == {"revoked": [], "remaining": 1}


def test_v5_blocklist_survives_row_restore(client):
    historic = _seed_historic_org()
    new = _rotate_to_new(client, historic)
    revoke_historic_demo_tokens(historic["slug"], current_hash=new["hash"])
    assert auth_mod.is_token_hash_revoked(historic["hash"]) is True
    assert auth_mod.is_token_hash_revoked(new["hash"]) is False
    # Restauration DB (backup/reinsert): le hash ressuscite reste refuse.
    session = session_for("main")()
    try:
        session.add(ApiToken(org_id=historic["org_id"], name="demo-restored",
                             token_hash=historic["hash"]))
        session.commit()
    finally:
        session.close()
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 403
    assert client.get("/api/v1/me",
                      headers=new["headers"]).status_code == 200


def test_v5_legitimate_sessions_preserved(client, real_auth):
    historic = _seed_historic_org()
    new = _rotate_to_new(client, historic)
    revoke_historic_demo_tokens(historic["slug"], current_hash=new["hash"])
    # Owner: intents illimites, chaos own-org, mint guests/tokens.
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False},
                    headers=new["headers"])
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "http500"},
                    headers=new["headers"])
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/demo/guest-sessions", json={},
                    headers=new["headers"])
    assert r.status_code == 201, r.text
    minted = r.json()
    guest_headers = {"Authorization": f"Bearer {minted['credential']}"}
    # Guest: me 200 sur org ephemere, intent 201, chaos own-org 201.
    r = client.get("/api/v1/me", headers=guest_headers)
    assert r.status_code == 200
    assert r.json()["org_slug"] == minted["org_slug"]
    assert r.json()["actor"] == f"guest:{minted['session_id']}"
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False},
                    headers=guest_headers)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing",
                          "fault": "http500"},
                    headers=guest_headers)
    assert r.status_code == 201, r.text
    # Guest ne mint ni guests ni tokens (403), comme avant.
    assert client.post("/api/v1/demo/guest-sessions", json={},
                       headers=guest_headers).status_code == 403
    assert client.post("/api/v1/demo/tokens", json={"name": "x"},
                       headers=guest_headers).status_code == 403
    # Real tenant isole: chaos refuse, intents OK.
    assert client.post("/api/v1/demo/chaos",
                       json={"target_connector": "demo-billing",
                             "fault": "http500"},
                       headers=real_auth["headers"]).status_code == 403
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False},
                    headers=real_auth["headers"])
    assert r.status_code == 201, r.text


def test_v5_guest_quota_and_expiry_still_enforced(client):
    import time

    historic = _seed_historic_org()
    new = _rotate_to_new(client, historic)
    revoke_historic_demo_tokens(historic["slug"], current_hash=new["hash"])
    r = client.post("/api/v1/demo/guest-sessions",
                    json={"max_workflows": 1, "max_executes": 1},
                    headers=new["headers"])
    assert r.status_code == 201, r.text
    minted = r.json()
    guest_headers = {"Authorization": f"Bearer {minted['credential']}"}
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False},
                    headers=guest_headers)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/intents",
                    json={"intent": INTENT, "use_ai": False},
                    headers=guest_headers)
    assert r.status_code == 410
    # Expiry: passe en 403 via le chemin auth standard.
    auth_mod._GUEST_SESSIONS[hash_token(
        minted["credential"])]["expires_at"] = time.time() - 1
    assert client.get("/api/v1/me",
                      headers=guest_headers).status_code == 403


def test_v5_revocation_guards(client):
    from fastapi import HTTPException

    historic = _seed_historic_org()
    # Dernier credential: 409, historique toujours valide (pas de lockout).
    try:
        revoke_historic_demo_tokens(historic["slug"],
                                    current_hash="0" * 64)
        raise AssertionError("expected 409 last credential")
    except HTTPException as exc:
        assert exc.status_code == 409
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 200
    new = _rotate_to_new(client, historic)
    # Credential en cours: 409.
    try:
        revoke_historic_demo_tokens(historic["slug"],
                                    current_hash=historic["hash"])
        raise AssertionError("expected 409 current credential")
    except HTTPException as exc:
        assert exc.status_code == 409
    # Org inconnue: 404. Nom invalide: 422.
    try:
        revoke_historic_demo_tokens("no-such-org", current_hash=new["hash"])
        raise AssertionError("expected 404")
    except HTTPException as exc:
        assert exc.status_code == 404
    try:
        revoke_historic_demo_tokens(historic["slug"],
                                    current_hash=new["hash"],
                                    names=["bad name!"])
        raise AssertionError("expected 422")
    except HTTPException as exc:
        assert exc.status_code == 422
    # Apres echecs, la revocation nominale passe toujours.
    out = revoke_historic_demo_tokens(historic["slug"],
                                      current_hash=new["hash"])
    assert out == {"revoked": ["demo"], "remaining": 1}


def test_v5_env_blocklist_refuses_without_db_change(client, monkeypatch):
    historic = _seed_historic_org()
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 200
    # Entree malformee ignoree, entree valide bloquee (aucune ecriture DB).
    monkeypatch.setenv("REVERSA_REVOKED_TOKEN_HASHES",
                       f"not-hex, {historic['hash']}")
    assert auth_mod.is_token_hash_revoked(historic["hash"]) is True
    assert auth_mod.is_token_hash_revoked("0" * 64) is False
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 403
    monkeypatch.delenv("REVERSA_REVOKED_TOKEN_HASHES")
    assert client.get("/api/v1/me",
                      headers=historic["headers"]).status_code == 200


def test_v5_revoke_token_hash_validates_shape():
    import pytest as _pytest

    good = "ab" * 32
    assert auth_mod.is_token_hash_revoked(good) is False
    assert auth_mod.is_token_hash_revoked("") is False
    assert auth_mod.revoke_token_hash(good) is True
    assert auth_mod.is_token_hash_revoked(good) is True
    assert auth_mod.revoke_token_hash(good) is False  # idempotent
    for bad in ("", "abc", "zz" * 32, "AB" * 31 + "!", "plaintext-secret"):
        with _pytest.raises(ValueError):
            auth_mod.revoke_token_hash(bad)


def test_v5_inventory_never_exposes_plaintext(client):
    historic = _seed_historic_org()
    new = _rotate_to_new(client, historic)
    revoke_historic_demo_tokens(historic["slug"], current_hash=new["hash"])
    r = client.get("/api/v1/demo/tokens", headers=new["headers"])
    assert r.status_code == 200
    rows = r.json()["data"]
    assert [row["name"] for row in rows] == ["rotated-v5"]
    for row in rows:
        assert set(row) == {"name", "token_id", "created_at"}
        assert row["token_id"] == new["hash"][:12]
        assert new["plain"] not in str(row)
        assert historic["plain"] not in str(row)
    # Le retour de revocation ne contient ni hash ni plaintext.
    out = revoke_historic_demo_tokens(historic["slug"],
                                      current_hash=new["hash"])
    assert out == {"revoked": [], "remaining": 1}
    assert new["hash"] not in str(out)
