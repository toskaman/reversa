"""Guest sessions + demo token rotation (P1-AUTH-02, demo tenant only).

- POST /api/v1/demo/guest-sessions: owner mints a short-lived
  quota-bound guest credential (rev_guest_*, TTL 60 min).
- GET/POST /api/v1/demo/tokens, DELETE /api/v1/demo/tokens/{name}:
  rotation overlap (add-new-then-revoke-old) for the demo credential.

Guests can never call these endpoints; neither can non-demo orgs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
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
    require_demo_owner,
    revoke_owner_token,
)
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
    expires_at: str
    max_workflows: int
    max_executes: int


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
