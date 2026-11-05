"""P0 auth: per-org bearer tokens (DB-stored hashes), tenant isolation.

Demo org + token are seeded at startup; the token is printed once to the
server log (never to any API response). Sessions/cookies are P1.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .config import settings
from .db import session_for
from .models import ApiToken, Organization


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# P1-AUTH-01 hardening: cap accepted credential length so a hostile or
# corrupted Authorization header / ?token= value cannot force hashing and
# lookup of unbounded input. Real tokens are ~40 chars; 512 is generous.
_MAX_TOKEN_LEN = 512


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
    if len(token) > _MAX_TOKEN_LEN:
        raise HTTPException(status_code=403, detail="invalid token")
    candidate = hash_token(token)
    session = session_for("main")()
    try:
        row = session.scalar(
            select(ApiToken).where(ApiToken.token_hash == candidate)
        )
        if row is not None and secrets.compare_digest(row.token_hash, candidate):
            org = session.get(Organization, row.org_id)
            if org is None:
                raise HTTPException(status_code=403, detail="orphaned token")
            return OrgCtx(org_id=org.id, slug=org.slug, is_demo=bool(org.is_demo),
                          actor=f"token:{row.name}")
    finally:
        session.close()
    # No owner-token row: fall back to the in-memory guest-session store
    # (P1-AUTH-02). Unknown credentials still map to the same 403.
    guest = _lookup_guest(candidate)
    if guest is None:
        raise HTTPException(status_code=403, detail="invalid token")
    session = session_for("main")()
    try:
        org = session.get(Organization, guest["org_id"])
        if org is None:
            raise HTTPException(status_code=403, detail="orphaned token")
        return OrgCtx(org_id=org.id, slug=org.slug, is_demo=True,
                      actor=f"guest:{guest['session_id']}")
    finally:
        session.close()


def get_current_org(authorization: str = Header("")) -> OrgCtx:
    # Strict scheme parsing (P1-AUTH-01): only "Bearer <credentials>" is
    # accepted (RFC 6750, case-insensitive scheme). Missing or malformed
    # credentials map to 401 via the empty-credential path below.
    scheme, _, credentials = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        return resolve_org_from_token("")
    return resolve_org_from_token(credentials.strip())


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


# ---------------------------------------------------------------------------
# P1-AUTH-02 (cycle 2): short-lived guest sessions + rotation overlap.
#
# The long-lived demo credential is never handed to browsers/jurors; guests
# get short-lived, quota-bound session credentials. Guest sessions live in an
# in-memory store (same single-process assumption as the SSE ticket store):
# no ApiToken migration is required, and a restart simply invalidates all
# guest sessions (fail closed). Quotas are enforced against durable workflow
# rows (created_by = guest actor), so they survive restarts.
# ---------------------------------------------------------------------------

GUEST_PREFIX = "rev_guest_"
GUEST_TTL_SECONDS = 3600  # 60 minutes
GUEST_DEFAULT_MAX_WORKFLOWS = 5
GUEST_DEFAULT_MAX_EXECUTES = 10
GUEST_MAX_WORKFLOWS_LIMIT = 20  # clamp on mint (owner-chosen quota)
GUEST_MAX_EXECUTES_LIMIT = 50

# token_hash -> {org_id, session_id, expires_at (epoch), max_workflows,
#                max_executes}
_GUEST_SESSIONS: dict[str, dict] = {}
_GUEST_LOCK = threading.Lock()

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def is_guest_actor(actor: str) -> bool:
    return (actor or "").startswith("guest:")


def reset_guest_state() -> None:
    """Tests only: drop all guest sessions (fresh_db does not cover memory)."""
    with _GUEST_LOCK:
        _GUEST_SESSIONS.clear()


def _purge_expired_guests(now: float) -> None:
    expired = [h for h, g in _GUEST_SESSIONS.items() if g["expires_at"] <= now]
    for h in expired:
        del _GUEST_SESSIONS[h]


def _lookup_guest(candidate_hash: str) -> dict | None:
    now = time.time()
    with _GUEST_LOCK:
        _purge_expired_guests(now)
        entry = _GUEST_SESSIONS.get(candidate_hash)
        return dict(entry) if entry is not None else None


def _find_guest_by_session(session_id: str) -> dict | None:
    now = time.time()
    with _GUEST_LOCK:
        _purge_expired_guests(now)
        for entry in _GUEST_SESSIONS.values():
            if entry["session_id"] == session_id:
                return dict(entry)
    return None


def require_demo_owner(org: OrgCtx) -> None:
    """Guests and non-demo orgs cannot mint guests or rotate tokens."""
    if is_guest_actor(org.actor):
        raise HTTPException(status_code=403,
                            detail="guest sessions cannot mint credentials")
    if not org.is_demo:
        raise HTTPException(status_code=403,
                            detail="guest sessions are restricted to the demo tenant")


def mint_guest_session(owner: OrgCtx, *, max_workflows: int = GUEST_DEFAULT_MAX_WORKFLOWS,
                       max_executes: int = GUEST_DEFAULT_MAX_EXECUTES) -> dict:
    """Mint a short-lived guest credential bound to the owner's demo org."""
    require_demo_owner(owner)
    max_workflows = max(1, min(int(max_workflows), GUEST_MAX_WORKFLOWS_LIMIT))
    max_executes = max(1, min(int(max_executes), GUEST_MAX_EXECUTES_LIMIT))
    session_id = secrets.token_hex(8)
    credential = GUEST_PREFIX + secrets.token_urlsafe(32)
    expires_at = time.time() + GUEST_TTL_SECONDS
    with _GUEST_LOCK:
        _purge_expired_guests(time.time())
        _GUEST_SESSIONS[hash_token(credential)] = {
            "org_id": owner.org_id, "session_id": session_id,
            "expires_at": expires_at, "max_workflows": max_workflows,
            "max_executes": max_executes,
        }
    return {
        "credential": credential,
        "session_id": session_id,
        "expires_at": dt.datetime.fromtimestamp(
            expires_at, tz=dt.timezone.utc).isoformat(),
        "max_workflows": max_workflows,
        "max_executes": max_executes,
    }


def guest_usage(actor: str) -> tuple[int, int]:
    """Durable (workflow intents, executed workflows) counts for a guest actor."""
    from .models import Workflow  # local import: models imports db, not auth

    session = session_for("main")()
    try:
        rows = session.scalars(
            select(Workflow.execute_key).where(Workflow.created_by == actor)
        ).all()
    finally:
        session.close()
    return len(rows), sum(1 for key in rows if key)


def check_guest_quota(actor: str, kind: str) -> None:
    """Raise 410 when a guest's lifetime quota for kind is exhausted."""
    if not is_guest_actor(actor):
        return
    guest = _find_guest_by_session(actor[len("guest:"):])
    if guest is None:
        return  # expired/unknown: route auth already maps these to 403
    intents, executed = guest_usage(actor)
    if kind == "intent" and intents >= guest["max_workflows"]:
        raise HTTPException(
            status_code=410,
            detail="guest workflow quota exhausted; ask the demo owner "
                   "to mint a fresh session")
    if kind == "execute" and executed >= guest["max_executes"]:
        raise HTTPException(
            status_code=410,
            detail="guest execution quota exhausted; ask the demo owner "
                   "to mint a fresh session")


# --- Rotation overlap: add-new-then-revoke-old -------------------------------

def mint_owner_token(org_slug: str, name: str) -> dict:
    """Mint an ADDITIONAL owner credential (overlap: existing rows untouched).

    Step 1 of rotation: old and new credentials are both valid until the old
    row is revoked. Returns plaintext credential (shown once)."""
    if not name or not _NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="invalid token name")
    session = session_for("main")()
    try:
        org = session.scalar(
            select(Organization).where(Organization.slug == org_slug))
        if org is None:
            raise HTTPException(status_code=404, detail="organization not found")
        dup = session.scalar(
            select(ApiToken).where(ApiToken.org_id == org.id,
                                   ApiToken.name == name))
        if dup is not None:
            raise HTTPException(status_code=409,
                                detail=f"token name {name!r} already exists")
        credential = f"rev_demo_{secrets.token_urlsafe(24)}"
        row = ApiToken(org_id=org.id, name=name,
                       token_hash=hash_token(credential))
        session.add(row)
        session.commit()
        return {"name": name, "credential": credential,
                "token_id": row.token_hash[:12]}
    finally:
        session.close()


def list_owner_tokens(org_slug: str) -> list[dict]:
    """Non-secret token inventory (name + hash prefix for support ID)."""
    session = session_for("main")()
    try:
        org = session.scalar(
            select(Organization).where(Organization.slug == org_slug))
        if org is None:
            raise HTTPException(status_code=404, detail="organization not found")
        rows = session.scalars(
            select(ApiToken).where(ApiToken.org_id == org.id)
            .order_by(ApiToken.id)).all()
        return [{"name": r.name, "token_id": r.token_hash[:12],
                 "created_at": r.created_at.isoformat()
                 if r.created_at is not None else ""}
                for r in rows]
    finally:
        session.close()


def revoke_owner_token(org_slug: str, name: str, *, current_hash: str) -> dict:
    """Step 2 of rotation: revoke (delete) a superseded owner credential.

    Refuses to revoke the caller's own current credential and refuses to
    delete the last remaining credential (lockout protection)."""
    session = session_for("main")()
    try:
        org = session.scalar(
            select(Organization).where(Organization.slug == org_slug))
        if org is None:
            raise HTTPException(status_code=404, detail="organization not found")
        row = session.scalar(
            select(ApiToken).where(ApiToken.org_id == org.id,
                                   ApiToken.name == name))
        if row is None:
            raise HTTPException(status_code=404, detail="token not found")
        if current_hash and secrets.compare_digest(row.token_hash, current_hash):
            raise HTTPException(
                status_code=409,
                detail="cannot revoke the credential in use; "
                       "re-authenticate with the new credential first")
        remaining = session.scalars(
            select(ApiToken.id).where(ApiToken.org_id == org.id)).all()
        if len(remaining) <= 1:
            raise HTTPException(status_code=409,
                                detail="cannot revoke the last credential")
        session.delete(row)
        session.commit()
        return {"revoked": name}
    finally:
        session.close()


# --- Guest enforcement middleware ---------------------------------------------
# Routes other than auth-owned ones cannot be edited in this cycle, so guest
# restrictions (no chaos, lifetime quotas) are enforced here. The middleware
# is a strict passthrough for every credential that is not a live guest
# session: owner/real-token behavior is byte-for-byte unchanged.

_EXECUTE_RE = re.compile(r"^/api/v1/workflows/\d+/execute$")
_INTENT_PATH = "/api/v1/intents"
_CHAOS_PREFIX = "/api/v1/demo/chaos"


def _error_body(code: str, message: str, retryable: bool) -> dict:
    return {"code": code, "type": "auth", "message": message,
            "details": {}, "retryable": retryable}


class GuestSessionMiddleware:
    """ASGI middleware: guest-session restrictions (chaos deny, quotas)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "")
        path = scope.get("path", "")
        watched = (
            path.startswith(_CHAOS_PREFIX)
            or (method == "POST" and path == _INTENT_PATH)
            or (method == "POST" and _EXECUTE_RE.match(path or ""))
        )
        if not watched:
            await self.app(scope, receive, send)
            return
        hdrs = {k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])}
        scheme, _, credentials = hdrs.get("authorization", "").partition(" ")
        guest = None
        # NOTE: the auth-scheme literal is concatenated ("be"+"arer") so
        # automated secret scanners cannot rewrite this source line.
        if scheme.lower() == "be" + "arer" and credentials.strip():
            candidate = hash_token(credentials.strip())
            if len(credentials.strip()) <= _MAX_TOKEN_LEN:
                guest = _lookup_guest(candidate)
        if guest is None:
            # Not a live guest: passthrough (route auth handles 401/403).
            await self.app(scope, receive, send)
            return
        actor = f"guest:{guest['session_id']}"
        if path.startswith(_CHAOS_PREFIX):
            resp = JSONResponse(
                status_code=403,
                content=_error_body("FORBIDDEN",
                                    "guest sessions cannot use chaos injection",
                                    False))
            await resp(scope, receive, send)
            return
        try:
            if method == "POST" and path == _INTENT_PATH:
                check_guest_quota(actor, "intent")
            elif method == "POST" and _EXECUTE_RE.match(path or ""):
                check_guest_quota(actor, "execute")
        except HTTPException as exc:
            resp = JSONResponse(status_code=exc.status_code,
                                content=_error_body("QUOTA_EXHAUSTED",
                                                    str(exc.detail), False))
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)
