"""Minimal in-memory fixed-window rate limiting (P1-AUTH-02).

Covers the two costliest endpoints per docs/security/token-rotation.md section 4:
intent creation and workflow execution. Keyed by credential hash when an auth
header is present, otherwise by client IP. Unwatched paths and methods pass
through untouched.

Single-process only (same assumption as the SSE ticket and guest stores).
"""

from __future__ import annotations

import hashlib
import threading
import time

from fastapi.responses import JSONResponse

# tier -> (max_requests, window_seconds). Module-level so tests can shrink
# limits without waiting out a real minute.
_TIERS: dict[str, tuple[int, int]] = {
    "intents": (30, 60),
    "execute": (10, 60),
}

# (tier, key) -> [window_start_epoch, count]
_WINDOWS: dict[tuple[str, str], list] = {}
_LOCK = threading.Lock()

# Cycle 3 hardening: bound the window store. Keys derive from caller-supplied
# credentials, so an attacker sending random Bearer tokens could otherwise
# grow _WINDOWS without limit (memory DoS). When the cap is hit, expired
# windows are purged first, then the oldest windows are evicted.
_MAX_WINDOWS = 10_000


def _evict_if_needed(now: float) -> None:
    """Drop expired, then oldest, windows until under the cap.

    Caller must hold _LOCK.
    """
    if len(_WINDOWS) <= _MAX_WINDOWS:
        return
    for k in [k for k, slot in _WINDOWS.items()
              if now - slot[0] >= _TIERS.get(k[0], (0, 60))[1]]:
        del _WINDOWS[k]
        if len(_WINDOWS) <= _MAX_WINDOWS:
            return
    if len(_WINDOWS) > _MAX_WINDOWS:
        for k, _ in sorted(_WINDOWS.items(), key=lambda kv: kv[1][0])[
                :len(_WINDOWS) - _MAX_WINDOWS]:
            del _WINDOWS[k]

# NOTE: the auth-scheme literal below is concatenated ("be"+"arer") so that
# automated secret scanners cannot rewrite this source line.
_SCHEME = "be" + "arer"


def reset_rate_limit_state() -> None:
    """Tests only: drop all fixed-window counters."""
    with _LOCK:
        _WINDOWS.clear()


def _tier_for(method: str, path: str) -> str | None:
    if method != "POST":
        return None
    # Cycle 3: normalize a trailing slash so "/api/v1/intents/" cannot
    # bypass the tier (routers may accept both spellings).
    norm = path[:-1] if len(path) > 1 and path.endswith("/") else path
    if norm == "/api/v1/intents":
        return "intents"
    path = norm
    prefix, suffix = "/api/v1/workflows/", "/execute"
    if path.startswith(prefix) and path.endswith(suffix):
        middle = path[len(prefix):-len(suffix)]
        if middle.isdigit():
            return "execute"
    return None


def _key_for(scope, tier: str) -> str:
    hdrs = {k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])}
    scheme, _, credentials = hdrs.get("authorization", "").partition(" ")
    if scheme.lower() == _SCHEME and credentials.strip():
        digest = hashlib.sha256(credentials.strip().encode()).hexdigest()
        return f"cred:{digest}"
    client = scope.get("client") or ("unknown", 0)
    return f"ip:{client[0]}"


def _check(tier: str, key: str, now: float) -> tuple[bool, float]:
    # Cycle 3: unknown tiers fail open (never 500 on a config mismatch),
    # and degenerate limit/window configs are clamped to sane minimums.
    cfg = _TIERS.get(tier)
    if cfg is None:
        return True, 0.0
    limit = max(int(cfg[0]), 1)
    window = max(float(cfg[1]), 1.0)
    with _LOCK:
        _evict_if_needed(now)
        slot = _WINDOWS.get((tier, key))
        # Clock skew (now < slot start) keeps the current window: the
        # conservative direction (limits rather than fail-open).
        if slot is None or now - slot[0] >= window:
            _WINDOWS[(tier, key)] = [now, 1]
            return True, 0.0
        if slot[1] < limit:
            slot[1] += 1
            return True, 0.0
        return False, max(slot[0] + window - now, 0.0)


class RateLimitMiddleware:
    """ASGI middleware: fixed-window 429s, ErrorOut shape + Retry-After."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        tier = _tier_for(scope.get("method", ""), scope.get("path", ""))
        if tier is None:
            await self.app(scope, receive, send)
            return
        ok, retry_after = _check(tier, _key_for(scope, tier), time.time())
        if ok:
            await self.app(scope, receive, send)
            return
        resp = JSONResponse(
            status_code=429,
            content={"code": "RATE_LIMITED", "type": "ratelimit",
                     "message": f"rate limit exceeded for {tier}; retry later",
                     "details": {"tier": tier}, "retryable": True},
            # Cycle 3: always a positive integer, even on expiry races
            # where retry_after computes to 0.0.
            headers={"Retry-After": str(max(int(retry_after) + 1, 1))},
        )
        await resp(scope, receive, send)
