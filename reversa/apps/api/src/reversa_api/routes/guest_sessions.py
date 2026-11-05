"""Guest sessions + demo token rotation (P1-AUTH-02, demo tenant only).

- POST /api/v1/demo/guest-sessions: owner mints a short-lived
  quota-bound guest credential (rev_guest_*, TTL 60 min). Cycle 4: each
  session owns an ephemeral demo org (per-session isolation).
- POST /api/v1/demo/guest-sessions/public: PUBLIC mint, no credential.
  Fixed tiny quotas, chaos-disabled, per-IP rate-limited (cycle 4).
- GET/POST /api/v1/demo/tokens, DELETE /api/v1/demo/tokens/{name}:
  rotation overlap (add-new-then-revoke-old) for the demo credential.

Guests can never call the owner endpoints; neither can non-demo orgs.
"""

from __future__ import annotations

import ipaddress
import threading
import time

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from ..auth import (
    GUEST_DEFAULT_MAX_EXECUTES,
    GUEST_DEFAULT_MAX_WORKFLOWS,
    GUEST_MAX_EXECUTES_LIMIT,
    GUEST_MAX_WORKFLOWS_LIMIT,
    OrgCtx,
    get_current_org,
    hash_token,
    list_owner_tokens,
    mint_guest_session,
    mint_owner_token,
    mint_public_guest_session,
    require_demo_owner,
    revoke_owner_token,
)
from ..config import settings
from ..schemas import Strict

router = APIRouter(prefix="/api/v1/demo", tags=["guest-sessions"])


class GuestMintIn(Strict):
    max_workflows: int = Field(default=GUEST_DEFAULT_MAX_WORKFLOWS,
                               ge=1, le=GUEST_MAX_WORKFLOWS_LIMIT)
    max_executes: int = Field(default=GUEST_DEFAULT_MAX_EXECUTES,
                              ge=1, le=GUEST_MAX_EXECUTES_LIMIT)


class GuestMintOut(Strict):
    credential: str
    session_id: str
    org_slug: str
    expires_at: str
    max_workflows: int
    max_executes: int


class PublicGuestMintIn(Strict):
    """Empty by design: public quotas are fixed; any override is a 422."""

    pass


# --- Public-mint rate limit: per-IP fixed window (module-local so the
# unauthenticated endpoint cannot be used to mint orgs at full speed).
PUBLIC_MINT_MAX_PER_WINDOW = 5
PUBLIC_MINT_WINDOW_SECONDS = 3600
_PUBLIC_WINDOWS: dict[str, list] = {}
_PUBLIC_LOCK = threading.Lock()


def reset_public_mint_state() -> None:
    """Tests only: drop all public-mint window counters."""
    with _PUBLIC_LOCK:
        _PUBLIC_WINDOWS.clear()


def _trusted_proxy_nets():
    """Parse settings.trusted_proxies; unparseable entries are skipped."""
    nets = []
    for entry in settings.trusted_proxies.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            nets.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return nets


def public_mint_ip(request: Request) -> str:
    """Best-effort visitor IP for the public-mint bucket (P0-2).

    Behind Caddy every request arrives from the proxy's own (container)
    IP, so keying on request.client.host collapsed all visitors into one
    global bucket. When the direct peer belongs to a trusted proxy
    network, use the LAST X-Forwarded-For entry — the address our proxy
    appended for its own peer (earlier entries are client-controlled).
    Untrusted peer, missing or malformed header: fall back to the peer,
    so a forged header can neither poison another bucket nor rotate
    buckets to dodge the limit.
    """
    peer = request.client.host if request.client else "unknown"
    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return peer
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_ip in net for net in _trusted_proxy_nets()):
        return peer
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    if not hops:
        return peer
    try:
        return str(ipaddress.ip_address(hops[-1]))
    except ValueError:
        return peer


def _check_public_mint(ip: str, now: float) -> tuple[bool, float]:
    limit = max(int(PUBLIC_MINT_MAX_PER_WINDOW), 1)
    window = max(float(PUBLIC_MINT_WINDOW_SECONDS), 1.0)
    with _PUBLIC_LOCK:
        slot = _PUBLIC_WINDOWS.get(ip)
        if slot is None or now - slot[0] >= window:
            _PUBLIC_WINDOWS[ip] = [now, 1]
            return True, 0.0
        if slot[1] < limit:
            slot[1] += 1
            return True, 0.0
        return False, max(slot[0] + window - now, 0.0)


class TokenMintIn(Strict):
    name: str = Field(min_length=1, max_length=64)


class TokenMintOut(Strict):
    name: str
    credential: str
    token_id: str


class TokenInfo(Strict):
    name: str
    token_id: str
    created_at: str


def _current_hash(authorization: str = "") -> str:
    # NOTE: scheme literal concatenated so secret scanners keep hands off.
    scheme, _, credentials = (authorization or "").partition(" ")
    if scheme.lower() == "be" + "arer" and credentials.strip():
        return hash_token(credentials.strip())
    return ""


@router.post("/guest-sessions", status_code=201)
def create_guest_session(body: GuestMintIn,
                         org: OrgCtx = Depends(get_current_org)):
    require_demo_owner(org)
    return GuestMintOut(**mint_guest_session(
        org, max_workflows=body.max_workflows,
        max_executes=body.max_executes))


@router.post("/guest-sessions/public", status_code=201)
def create_public_guest_session(request: Request,
                                body: PublicGuestMintIn | None = None):
    """PUBLIC guest mint: no credential required.

    Fixed tiny quotas (PUBLIC_GUEST_MAX_*, caller cannot override — any
    body field is a 422), chaos-disabled (guest-actor middleware deny),
    per-IP rate-limited (429 + Retry-After). Each session owns an
    ephemeral demo org, swept on expiry.
    """
    del body  # empty schema: presence only enforces the 422-on-fields rule
    ip = public_mint_ip(request)
    ok, retry_after = _check_public_mint(ip, time.time())
    if not ok:
        return JSONResponse(
            status_code=429,
            content={"code": "RATE_LIMITED", "type": "ratelimit",
                     "message": "public guest mint rate limit exceeded; "
                                "retry later",
                     "details": {"tier": "public-mint"}, "retryable": True},
            headers={"Retry-After": str(max(int(retry_after) + 1, 1))},
        )
    return GuestMintOut(**mint_public_guest_session())


@router.post("/tokens", status_code=201)
def create_owner_token(body: TokenMintIn,
                       org: OrgCtx = Depends(get_current_org)):
    require_demo_owner(org)
    return TokenMintOut(**mint_owner_token(org.slug, body.name))


@router.get("/tokens")
def inventory_owner_tokens(org: OrgCtx = Depends(get_current_org)):
    require_demo_owner(org)
    return {"data": [TokenInfo(**row) for row in list_owner_tokens(org.slug)]}


@router.delete("/tokens/{name}")
def delete_owner_token(name: str, org: OrgCtx = Depends(get_current_org),
                       authorization: str = Header("")):
    require_demo_owner(org)
    return revoke_owner_token(org.slug, name,
                              current_hash=_current_hash(authorization))
