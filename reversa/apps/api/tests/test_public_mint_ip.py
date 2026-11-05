"""Public-mint buckets must be per visitor, not per proxy (P0-2).

Behind the Caddy reverse proxy every request arrives from the proxy's own
(container) IP. Keying the public-mint bucket on request.client.host
collapsed ALL visitors into ONE global 5/hour bucket — a single juror (or
bot) could lock Jury Mode out for everyone until the window expired.

Fix contract: when the direct peer belongs to a trusted proxy network,
the bucket key comes from the last X-Forwarded-For entry (the address our
proxy appended for its own peer). Anything else — untrusted peer,
missing/malformed header — falls back to the peer address, so a forged
header can neither poison another visitor's bucket nor rotate buckets to
dodge the limit.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from reversa_api import main as app_module
from reversa_api.routes import guest_sessions as guest_routes

MINT = "/api/v1/demo/guest-sessions/public"
PROXY_PEER = ("172.18.0.5", 50000)  # docker bridge: trusted by default


@pytest.fixture()
def proxied_client(fresh_db):
    with TestClient(app_module.app, client=PROXY_PEER) as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh_mint_state():
    guest_routes.reset_public_mint_state()
    yield
    guest_routes.reset_public_mint_state()


def _mint(client, xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return client.post(MINT, json={}, headers=headers)


def test_buckets_are_per_visitor_behind_trusted_proxy(proxied_client):
    """5 mints for visitor A, then visitor B still gets a full bucket."""
    for _ in range(5):
        r = _mint(proxied_client, "203.0.113.7")
        assert r.status_code == 201, r.text
    r = _mint(proxied_client, "203.0.113.7")
    assert r.status_code == 429, r.text
    assert r.json()["details"]["tier"] == "public-mint"
    assert "Retry-After" in r.headers
    # A different visitor behind the same proxy is NOT locked out.
    r = _mint(proxied_client, "203.0.113.8")
    assert r.status_code == 201, r.text


def test_forged_xff_from_untrusted_peer_cannot_rotate_buckets(client):
    """Direct clients share the peer bucket no matter what XFF they send."""
    for i in range(5):
        r = _mint(client, f"9.9.9.{i + 1}")
        assert r.status_code == 201, r.text
    r = _mint(client, "9.9.9.99")
    assert r.status_code == 429, r.text


def _req(peer, xff=None):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "method": "POST", "path": MINT,
                    "headers": headers, "client": peer})


def test_spoofed_chain_uses_last_hop_only():
    """First XFF entries are attacker-controlled; only the last (added by
    our trusted proxy) identifies the visitor."""
    req = _req(("172.18.0.5", 1234), "1.2.3.4, 203.0.113.9")
    assert guest_routes.public_mint_ip(req) == "203.0.113.9"


def test_malformed_xff_falls_back_to_peer():
    req = _req(("172.18.0.5", 1234), "not-an-ip")
    assert guest_routes.public_mint_ip(req) == "172.18.0.5"
    req = _req(("172.18.0.5", 1234), "")
    assert guest_routes.public_mint_ip(req) == "172.18.0.5"


def test_untrusted_peer_ignores_xff():
    req = _req(("203.0.113.50", 1234), "10.9.9.9")
    assert guest_routes.public_mint_ip(req) == "203.0.113.50"
    req = _req(("testclient", 50000), "10.9.9.9")
    assert guest_routes.public_mint_ip(req) == "testclient"
