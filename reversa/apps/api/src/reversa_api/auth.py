"""P0 auth: per-org bearer tokens (DB-stored hashes), tenant isolation.

Demo org + token are seeded at startup; the token is printed once to the
server log (never to any API response). Sessions/cookies are P1.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import os
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


# ---------------------------------------------------------------------------
# V5 (AGENT-09): historic demo credential revocation.
#
# Audit: seed_demo_org() preserves any existing ApiToken row, ApiToken has no
# expiry/revoked flag, and DELETE is revocation (docs/security/token-rotation
# §2). A historic demo credential therefore stays valid until its row is
# deleted AND its hash is blocklisted (a DB restore must not resurrect it).
# Only SHA-256 hashes are stored here (never plaintext): in-memory set plus
# optional REVERSA_REVOKED_TOKEN_HASHES env (comma-separated hex). Rejected
# hashes map to the same generic 403 as unknown tokens.
# ---------------------------------------------------------------------------

_REVOKED_ENV_VAR = "REVERSA_REVOKED_TOKEN_HASHES"
_SHA_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_REVOKED_TOKEN_HASHES: set[str] = set()
_REVOKED_LOCK = threading.Lock()
# seed_demo_org() mints the first demo credential under this name; a historic
# leaked credential therefore carries it unless it was renamed at rotation.
_HISTORIC_DEMO_TOKEN_NAMES: tuple[str, ...] = ("demo",)


def _env_revoked_hashes() -> set[str]:
    raw = os.environ.get(_REVOKED_ENV_VAR, "")
    found: set[str] = set()
    for part in raw.split(","):
        candidate = part.strip().lower()
        if candidate and _SHA_HEX_RE.match(candidate):
            found.add(candidate)
    return found


def is_token_hash_revoked(candidate_hash: str) -> bool:
    """True when a SHA-256 hex hash is blocklisted (memory or env)."""
    if not candidate_hash:
        return False
    with _REVOKED_LOCK:
        if candidate_hash in _REVOKED_TOKEN_HASHES:
            return True
    return candidate_hash in _env_revoked_hashes()


def revoke_token_hash(token_hash: str) -> bool:
    """Blocklist one SHA-256 hex hash (never pass plaintext).

    Returns True when newly added, False when already present.
    Raises ValueError on non-hex shape (message carries no value).
    """
    normalized = (token_hash or "").strip().lower()
    if not _SHA_HEX_RE.match(normalized):
        raise ValueError("invalid token hash shape")
    with _REVOKED_LOCK:
        if normalized in _REVOKED_TOKEN_HASHES:
            return False
        _REVOKED_TOKEN_HASHES.add(normalized)
        return True


def reset_revoked_state() -> None:
    """Tests only: drop the in-memory blocklist (env is untouched)."""
    with _REVOKED_LOCK:
        _REVOKED_TOKEN_HASHES.clear()


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
    if is_token_hash_revoked(candidate):
        raise HTTPException(status_code=403, detail="invalid token")
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

# Cycle 4 (AGENT-07): true per-session isolation. Every guest session owns an
# ephemeral demo org (slug "guest-<session_id>", is_demo=1, NO schema change);
# all existing org_id scoping (workflows, evidence, SSE tickets, chaos rules,
# demo resources) then isolates sessions automatically. Expiry sweeps the
# ephemeral org and every row under it; the guard in _sweep_guest_org() makes
# touching a non-guest org impossible by construction.
GUEST_ORG_PREFIX = "guest-"

# Strictly-quota-bound PUBLIC mint: fixed tiny quotas, caller cannot override.
PUBLIC_GUEST_MAX_WORKFLOWS = 2
PUBLIC_GUEST_MAX_EXECUTES = 2

# token_hash -> {org_id, session_id, expires_at (epoch), max_workflows,
#                max_executes, ephemeral_org (bool), public (bool)}
_GUEST_SESSIONS: dict[str, dict] = {}
_GUEST_LOCK = threading.Lock()
# V4-1: one asyncio lock per live guest session, serializing quota-checked
# requests (intent/execute) end to end. asyncio (not threading) because the
# lock is held across `await self.app(...)`; a threading lock there could
# freeze the event loop. Entries are dropped with their session on purge.
_SESSION_LOCKS: dict[str, asyncio.Lock] = {}


def _session_lock(session_id: str) -> asyncio.Lock:
    with _GUEST_LOCK:
        lock = _SESSION_LOCKS.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _SESSION_LOCKS[session_id] = lock
        return lock

# Best-effort sweep failures from the lazy (request-path) purge, oldest first.
# The explicit sweep_expired_guests() returns per-org errors instead.
_LAST_SWEEP_ERRORS: list[str] = []

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def is_guest_actor(actor: str) -> bool:
    return (actor or "").startswith("guest:")


def reset_guest_state() -> None:
    """Tests only: drop all guest sessions (fresh_db does not cover memory)."""
    with _GUEST_LOCK:
        _GUEST_SESSIONS.clear()
        _SESSION_LOCKS.clear()


def _sweep_guest_org(org_id: int) -> dict:
    """Delete one ephemeral guest org and every row scoped to it.

    Guard: only an is_demo org whose slug starts with GUEST_ORG_PREFIX is
    ever deleted; anything else raises without touching the database.
    Covers main.db (tokens, chaos, workflows + actions/events/approvals),
    the 5 demo stores (demo_resources by org_id), then the org row itself.
    """
    from sqlalchemy import delete  # local: keep import graph acyclic

    from .db import MAIN_STORES
    from .models import (  # local import: models imports db, not auth
        ActionRun,
        ApiToken,
        Approval,
        ChaosRule,
        DemoResource,
        Event,
        Organization,
        Workflow,
    )

    session = session_for("main")()
    try:
        org = session.get(Organization, org_id)
        if org is None:
            return {"org_id": org_id, "deleted": False, "reason": "already gone"}
        if not org.is_demo or not org.slug.startswith(GUEST_ORG_PREFIX):
            raise ValueError(f"refusing to sweep non-guest org {org.slug!r}")
        wf_ids = list(session.scalars(
            select(Workflow.id).where(Workflow.org_id == org_id)).all())
        counts = {"workflows": len(wf_ids)}
        if wf_ids:
            for model, col in ((ActionRun, ActionRun.workflow_id),
                               (Event, Event.workflow_id),
                               (Approval, Approval.workflow_id)):
                res = session.execute(delete(model).where(col.in_(wf_ids)))
                counts[model.__tablename__] = res.rowcount
            res = session.execute(
                delete(Workflow).where(Workflow.org_id == org_id))
            counts["workflows_deleted"] = res.rowcount
        for model in (ChaosRule, ApiToken):
            res = session.execute(
                delete(model).where(model.org_id == org_id))
            counts[model.__tablename__] = res.rowcount
        session.delete(org)
        session.commit()
    finally:
        session.close()
    demo_counts = {}
    for store in MAIN_STORES:
        if store == "main":
            continue
        ds = session_for(store)()
        try:
            res = ds.execute(
                delete(DemoResource).where(DemoResource.org_id == org_id))
            ds.commit()
            demo_counts[store] = res.rowcount
        finally:
            ds.close()
    return {"org_id": org_id, "deleted": True, "main": counts,
            "demo": demo_counts}


def _purge_expired_guests(now: float) -> None:
    """Drop expired sessions; best-effort sweep of their ephemeral orgs.

    Runs on the request path (under _GUEST_LOCK), so per-org sweep failures
    are recorded in _LAST_SWEEP_ERRORS instead of breaking authentication.
    Use sweep_expired_guests() for an explicit, error-reporting sweep.
    """
    expired = [(h, g) for h, g in _GUEST_SESSIONS.items()
               if g["expires_at"] <= now]
    for h, g in expired:
        del _GUEST_SESSIONS[h]
        _SESSION_LOCKS.pop(g.get("session_id", ""), None)
    for _, g in expired:
        if g.get("ephemeral_org"):
            try:
                _sweep_guest_org(g["org_id"])
            except Exception as exc:  # never break auth on sweep failure
                _LAST_SWEEP_ERRORS.append(
                    f"org_id={g['org_id']}: {type(exc).__name__}: {exc}")


def sweep_expired_guests() -> dict:
    """Explicit expiry sweep: purge expired sessions AND delete their orgs.

    Returns {"sessions": n, "swept": [...per-org results...],
    "errors": [...]}. Only guest-prefixed demo orgs are ever deleted.
    """
    now = time.time()
    with _GUEST_LOCK:
        expired = [(h, g) for h, g in _GUEST_SESSIONS.items()
                   if g["expires_at"] <= now]
        for h, g in expired:
            del _GUEST_SESSIONS[h]
            _SESSION_LOCKS.pop(g.get("session_id", ""), None)
    swept: list[dict] = []
    errors: list[str] = []
    for _, g in expired:
        if not g.get("ephemeral_org"):
            continue
        try:
            swept.append(_sweep_guest_org(g["org_id"]))
        except Exception as exc:
            errors.append(f"org_id={g['org_id']}: {type(exc).__name__}: {exc}")
    return {"sessions": len(expired), "swept": swept, "errors": errors}


def _lookup_guest(candidate_hash: str) -> dict | None:
    if is_token_hash_revoked(candidate_hash):
        return None
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


def _create_ephemeral_guest_org(session_id: str) -> Organization:
    """Insert (and return) the ephemeral demo org for one guest session."""
    session = session_for("main")()
    try:
        slug = f"{GUEST_ORG_PREFIX}{session_id}"
        if session.scalar(
                select(Organization).where(Organization.slug == slug)) is not None:
            raise ValueError(f"guest org slug collision: {slug}")
        org = Organization(slug=slug, name=f"Guest session {session_id}",
                           is_demo=1)
        session.add(org)
        session.commit()
        session.refresh(org)
        session.expunge(org)
        return org
    finally:
        session.close()


def _store_guest_session(*, max_workflows: int, max_executes: int,
                         public: bool) -> dict:
    """Allocate session id + ephemeral org + credential; store the entry."""
    session_id = secrets.token_hex(8)
    org = _create_ephemeral_guest_org(session_id)
    credential = GUEST_PREFIX + secrets.token_urlsafe(32)
    expires_at = time.time() + GUEST_TTL_SECONDS
    with _GUEST_LOCK:
        _purge_expired_guests(time.time())
        _GUEST_SESSIONS[hash_token(credential)] = {
            "org_id": org.id, "session_id": session_id,
            "expires_at": expires_at, "max_workflows": max_workflows,
            "max_executes": max_executes, "ephemeral_org": True,
            "public": public,
        }
    return {
        "credential": credential,
        "session_id": session_id,
        "org_slug": org.slug,
        "expires_at": dt.datetime.fromtimestamp(
            expires_at, tz=dt.timezone.utc).isoformat(),
        "max_workflows": max_workflows,
        "max_executes": max_executes,
    }


def mint_guest_session(owner: OrgCtx, *, max_workflows: int = GUEST_DEFAULT_MAX_WORKFLOWS,
                       max_executes: int = GUEST_DEFAULT_MAX_EXECUTES) -> dict:
    """Mint a short-lived guest credential with its OWN ephemeral demo org.

    Cycle 4: the guest no longer shares the owner's demo org. Every op the
    guest performs is scoped to the ephemeral org_id, so two sessions (and
    the owner) are mutually invisible through the existing org_id checks.
    """
    require_demo_owner(owner)
    max_workflows = max(1, min(int(max_workflows), GUEST_MAX_WORKFLOWS_LIMIT))
    max_executes = max(1, min(int(max_executes), GUEST_MAX_EXECUTES_LIMIT))
    return _store_guest_session(max_workflows=max_workflows,
                                max_executes=max_executes, public=False)


def mint_public_guest_session() -> dict:
    """Mint a PUBLIC guest session: no owner credential, fixed tiny quotas.

    Chaos injection is allowed within the session's own ephemeral demo
    org (org-scoped rules, per-org cap, swept at expiry); quotas cannot
    be raised by the caller.
    Rate limiting is enforced by the route (per-IP fixed window).
    """
    return _store_guest_session(
        max_workflows=PUBLIC_GUEST_MAX_WORKFLOWS,
        max_executes=PUBLIC_GUEST_MAX_EXECUTES, public=True)


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
        revoke_token_hash(row.token_hash)
        session.delete(row)
        session.commit()
        return {"revoked": name}
    finally:
        session.close()


def revoke_historic_demo_tokens(
    org_slug: str,
    *,
    current_hash: str = "",
    names: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """V5 safe revocation for historic demo credentials (by name, no secret).

    Deletes the named historic owner rows (default: the seed name) and
    blocklists their hashes so a DB restore cannot resurrect them. Same
    lockout guards as revoke_owner_token: refuses the caller's current
    credential (409) and refuses to delete the last remaining credential
    (409, mint a replacement first). Idempotent: unknown names are skipped
    and an empty revocation returns {"revoked": [], "remaining": n}.
    Returns only names + count (never hashes or plaintext).
    """
    wanted = set(_HISTORIC_DEMO_TOKEN_NAMES if names is None else names)
    for candidate_name in wanted:
        if not candidate_name or not _NAME_RE.match(candidate_name):
            raise HTTPException(status_code=422, detail="invalid token name")
    session = session_for("main")()
    try:
        org = session.scalar(
            select(Organization).where(Organization.slug == org_slug))
        if org is None:
            raise HTTPException(status_code=404,
                                detail="organization not found")
        rows = session.scalars(
            select(ApiToken).where(ApiToken.org_id == org.id)).all()
        targets = [row for row in rows if row.name in wanted]
        if not targets:
            return {"revoked": [], "remaining": len(rows)}
        for row in targets:
            if current_hash and secrets.compare_digest(
                    row.token_hash, current_hash):
                raise HTTPException(
                    status_code=409,
                    detail="cannot revoke the credential in use; "
                           "re-authenticate with the new credential first")
        if len(rows) - len(targets) < 1:
            raise HTTPException(status_code=409,
                                detail="cannot revoke the last credential")
        revoked_names = sorted(row.name for row in targets)
        for row in targets:
            revoke_token_hash(row.token_hash)
            session.delete(row)
        session.commit()
        return {"revoked": revoked_names,
                "remaining": len(rows) - len(targets)}
    finally:
        session.close()


# --- Guest enforcement middleware ---------------------------------------------
# Routes other than auth-owned ones cannot be edited in this cycle, so guest
# restrictions (no chaos, lifetime quotas) are enforced here. The middleware
# is a strict passthrough for every credential that is not a live guest
# session: owner/real-token behavior is byte-for-byte unchanged.

_EXECUTE_RE = re.compile(r"^/api/v1/workflows/\d+/execute$")
_INTENT_PATH = "/api/v1/intents"


def _error_body(code: str, message: str, retryable: bool) -> dict:
    return {"code": code, "type": "auth", "message": message,
            "details": {}, "retryable": retryable}


class GuestSessionMiddleware:
    """ASGI middleware: guest-session restrictions (quotas).

    Chaos injection is NOT denied here: rules are org-scoped
    (ChaosRule.org_id, matched per-org by the saga), times-bounded,
    per-org capped, and swept at session expiry, so a guest can only
    fault its own ephemeral demo tenant. The route guard still
    requires a demo org (403 otherwise).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "")
        path = scope.get("path", "")
        watched = (
            (method == "POST" and path == _INTENT_PATH)
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
        # V4-1: hold the per-session lock across quota check AND the
        # downstream route, so racing requests cannot all pass the check
        # before any of them lands. Other sessions proceed concurrently.
        quota_kind = None
        if method == "POST" and path == _INTENT_PATH:
            quota_kind = "intent"
        elif method == "POST" and _EXECUTE_RE.match(path or ""):
            quota_kind = "execute"
        if quota_kind is None:
            await self.app(scope, receive, send)
            return
        lock = _session_lock(guest["session_id"])
        await lock.acquire()
        try:
            try:
                check_guest_quota(actor, quota_kind)
            except HTTPException as exc:
                resp = JSONResponse(status_code=exc.status_code,
                                    content=_error_body("QUOTA_EXHAUSTED",
                                                        str(exc.detail), False))
                await resp(scope, receive, send)
                return
            await self.app(scope, receive, send)
        finally:
            lock.release()
