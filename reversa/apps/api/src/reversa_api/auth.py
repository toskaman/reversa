"""P0 auth: per-org bearer tokens (DB-stored hashes), tenant isolation.

Demo org + token are seeded at startup; the token is printed once to the
server log (never to any API response). Sessions/cookies are P1.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

from .config import settings
from .db import session_for
from .models import ApiToken, Organization


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class OrgCtx:
    org_id: int
    slug: str
    is_demo: bool
    actor: str


def get_session():
    session = session_for("main")()
    try:
        yield session
    finally:
        session.close()


def resolve_org_from_token(token: str) -> OrgCtx:
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    session = session_for("main")()
    try:
        row = session.scalar(
            select(ApiToken).where(ApiToken.token_hash == hash_token(token))
        )
        if row is None:
            raise HTTPException(status_code=403, detail="invalid token")
        org = session.get(Organization, row.org_id)
        if org is None:
            raise HTTPException(status_code=403, detail="orphaned token")
        return OrgCtx(org_id=org.id, slug=org.slug, is_demo=bool(org.is_demo),
                      actor=f"token:{row.name}")
    finally:
        session.close()


def get_current_org(authorization: str = Header("")) -> OrgCtx:
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    return resolve_org_from_token(token)


def seed_demo_org() -> tuple[Organization, str | None]:
    """Ensure the demo org exists. Returns (org, new_token_or_None)."""
    session = session_for("main")()
    try:
        org = session.scalar(
            select(Organization).where(Organization.slug == settings.demo_org_slug)
        )
        if org is None:
            org = Organization(slug=settings.demo_org_slug, name="Acme Demo", is_demo=1)
            session.add(org)
            session.commit()
            session.refresh(org)
        existing = session.scalar(
            select(ApiToken).where(ApiToken.org_id == org.id)
        )
        if existing is not None:
            return org, None
        token = f"rev_demo_{secrets.token_urlsafe(24)}"
        session.add(ApiToken(org_id=org.id, name="demo", token_hash=hash_token(token)))
        session.commit()
        return org, token
    finally:
        session.close()
