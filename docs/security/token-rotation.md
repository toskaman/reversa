# P1-AUTH-01 — Demo credential rotation / revocation / expiry

- Status: design (no migration applied in cycle 1)
- Owner: AGENT-12 (REVERSA V2 cycle 1, Defensive Security Engineer)
- Date: 2026-11-05
- Scope: `reversa/apps/api/src/reversa_api/auth.py`, `models.py` (`ApiToken`),
  all routes under `reversa_api/routes/`, SSE stream auth, web credential handling

## 1. Problem

The demo-organization credential is a long-lived, never-expiring bearer
credential:

- Minted once in `seed_demo_org()` (`auth.py`); if ANY credential row already
  exists for the demo org, no new credential is ever minted — there is no
  rotation path, only manual DB surgery.
- `ApiToken` (`models.py`) stores only `token_hash` (SHA-256, good) with no
  `expires_at`, no `revoked` flag, no `last_used_at`, no name prefix for
  identification.
- The plaintext credential is printed to the server log at startup (`main.py`
  lifespan). Anyone with log access owns the demo org until the DB row is
  deleted by hand.
- The SSE route (`routes/workflows.py::stream_events`) accepts `?token=`
  because EventSource cannot send headers; the web client
  (`components/EventTimeline.tsx`) uses it. Credentials in URLs land in
  browser history, proxies, and access logs.
- The web app stores the credential in `localStorage` (`app/settings/page.tsx`,
  `lib/api.ts`) — any XSS in the demo UI exfiltrates it.
- No rate limiting exists anywhere (verified: `main.py` registers only
  `CORSMiddleware`; no limiter in any route). A leaked demo credential allows
  unbounded intent/workflow/chaos creation.

Threat: credential disclosure (log scrape, URL leak, XSS, shared screenshot)
gives persistent, unthrottled control of the demo tenant, including chaos
injection. There is no way to revoke without code-level DB access, and no
expiry to bound the blast radius.

## 2. Immediate rotation procedure (works TODAY, no migration)

Use this the moment a demo credential is suspected exposed.

1. Mint a replacement (overlap, zero downtime):
   - Generate: `python -c "import secrets; print('rev_demo_' + secrets.token_urlsafe(24))"`
     on the deploy host (never in chat/CI logs).
   - Hash: `python -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" '<new>'`.
   - Insert: `python reversa/infrastructure/scripts/add_token.py <demo-org-slug> demo-rotated <sha256>`.
2. Verify the new credential: `GET /api/v1/me` returns the demo org; run
   `pytest tests/test_security.py` in `reversa/apps/api`.
3. Revoke the old credential: delete its `api_tokens` row for the demo org
   (keep the new row). There is no `revoked` flag yet, so DELETE is revocation.
4. Scrub: rotate/truncate server logs containing the startup print line; purge
   any proxy/access logs holding `?token=`; tell demo users to replace the
   credential in Settings (localStorage).
5. Confirm: old credential gets 403 on `/api/v1/me`; new credential gets 200.

Note: restarting the API does NOT rotate anything — `seed_demo_org()` returns
`(org, None)` while a row exists. Restart alone is not a fix.

## 3. Design: short-lived guest sessions (requires follow-up migration)

Goal: the long-lived demo credential is never handed to browsers or jurors;
guests get short-lived, quota-bound session credentials.

### 3.1 Model change (proposed, NOT applied — `models.py` is out of mandate)

```python
class ApiToken(Base):
    # ... existing columns ...
    prefix: Mapped[str] = mapped_column(String(16), default="")      # e.g. "rev_demo_a1b2" for support ID
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[int] = mapped_column(Integer, default=0)          # 1 = revoked, row kept for audit
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_workflows: Mapped[int] = mapped_column(Integer, default=0)    # 0 = unlimited (owner keys only)
```

`resolve_org_from_token()` then rejects revoked/expired rows (403) and stamps
`last_used_at`. SQLite/Postgres both support this; `as_naive_utc()` already
handles the tz asymmetry.

### 3.2 Guest mint endpoint (demo org only)

- `POST /api/v1/demo/guest-sessions` — requires the owner demo credential,
  returns `{credential, expires_at, max_workflows}`.
- Guest credential: `rev_guest_<32 urlsafe chars>`, TTL 60 minutes, default
  `max_workflows = 5`.
- Guest credentials CANNOT: call chaos endpoints, mint further guests, or
  touch non-demo orgs (enforced by `is_demo` + actor prefix `guest:`).
- Expiry enforced in `resolve_org_from_token()`; a janitor deletes expired
  guest rows hourly (or they linger harmlessly — expired = rejected).

### 3.3 Quotas

| Subject | Intent creates | Workflow executes | Chaos | Concurrent SSE |
|---|---|---|---|---|
| Owner demo credential | 60/hour | 120/hour | allowed | 5 |
| Guest session | 5/lifetime (then 410 Gone, re-mint) | 10/lifetime | denied (403) | 2 |
| Real org credential | 600/hour | 1200/hour | denied (403) | 10 |
| Unauthenticated IP | 0 (401/403 as today) | 0 | 0 | 0 |

Counts enforced per credential hash in `main.db` (new tiny table or reuse
`events` counts for workflow quota); rate windows in-process for the demo,
Redis/Postgres-backed when `DATABASE_URL` is set.

## 4. Rate-limiting review (as found)

Finding: NO rate limiting, throttling, or brute-force protection exists.
`main.py` registers only CORS; no middleware, dependency, or decorator in
`routes/*.py` limits requests. Attack consequences: credential guessing at
full speed (though 192-bit secrets make guessing infeasible), intent-flood
cost abuse against the Vultr planner endpoint, SSE connection exhaustion
(each stream holds a DB-polling loop for up to 120 s).

Recommended minimal fix (follow-up task, not this cycle):

1. Dependency `rate_limit(tier)` in a new `reversa_api/ratelimit.py`:
   in-memory fixed window per (credential-hash, route-tier), returning 429
   with the existing `ErrorOut` shape (`code: "RATE_LIMITED"`, `retryable: true`,
   `Retry-After` header).
2. Tiers: `intents: 30/min`, `execute: 10/min`, `chaos: 10/min`,
   `default: 300/min`, `sse: max N concurrent per credential` (counter with
   try/finally on stream close).
3. Auth failures: no extra delay needed (hashes are salted-lookalike random
   192-bit secrets), but log-and-count 403 bursts per IP for ops visibility.
4. Tests: new `tests/test_ratelimit.py` — burst over tier returns 429 then
   recovers after window; SSE concurrency cap returns 429 on N+1.

## 5. Input-validation review (as found)

Strengths (verified by reading `schemas.py`, `routes/*.py`, `evidence.py`):

- All request schemas inherit `Strict` (`extra="forbid"`) — unknown fields rejected.
- `IntentIn.intent` bounded (3–2000 chars); `ChaosIn.times` bounded 1–10.
- List endpoints clamp `limit` (workflows 1–100, events 1–500).
- Tenant isolation checked on every owned-object route (404 on cross-tenant).
- Approval binds `plan_hash` with expiry (410 past deadline).
- `evidence.redact()` scrubs secret-looking keys/values at append AND export.

Gaps (ordered by severity; fixes are follow-up tasks — routes are out of
this agent's mandate, so nothing below was changed):

1. **SSE `Last-Event-ID` crash (medium).** `stream_events()` does
   `int(request.headers.get("last-event-id", "0") or 0)` with no try/except:
   a non-numeric header raises `ValueError` → 500. Fix: sanitize to int with
   fallback 0 (one-line, safe).
2. **Unbounded `customer` dict (low-medium).** `IntentIn.customer` is a bare
   `dict` — no size/depth cap; it is persisted into `plan_json` and rendered
   in evidence. Fix: `max_length`-style validator (e.g. JSON ≤ 8 KB, depth ≤ 3).
3. **`decided_by` / `plan_hash` unshaped (low).** `ApproveIn.decided_by` is an
   unbounded string persisted to the approval row; `plan_hash` has no
   64-hex format check (equality-compared, so no bypass — cosmetic hardening).
4. **`?format=` unvalidated (negligible).** `export_evidence(format=...)`
   treats anything non-`"html"` as JSON. Fix: `Literal["json","html"]`
   (would turn typos into clean 422s).
5. **`?token=` URL exposure (medium, architectural).** Mitigated only by
   guest sessions (§3): short TTL + quotas bound what a logged URL leaks.
   Additionally: document that access logs must strip query strings, and
   prefer the header path wherever the client allows it.

## 6. Cycle-1 hardening actually applied (this agent)

Small, behavior-preserving changes in `reversa_api/auth.py` ONLY:

- `_MAX_TOKEN_LEN = 512` — overlong credentials rejected 403 before hashing
  (covers both the header and `?token=` paths, which share
  `resolve_org_from_token()`).
- `secrets.compare_digest()` verification of the looked-up hash row
  (defense in depth on top of the indexed equality lookup).
- Strict `Authorization` scheme parsing in `get_current_org()`: only
  `Bearer <credentials>` (RFC 6750 case-insensitive scheme) is accepted;
  missing/malformed values map to the existing 401 path. Previous code
  accepted any header shape via `removeprefix`.

Verification: `pytest tests/test_security.py` → 7 passed before AND after
(see agent report). No other files modified; no secrets committed.

## 7. Test plan for the follow-up

- `tests/test_token_rotation.py`: old credential 403 after rotation;
  expired guest 403; revoked flag 403; guest over `max_workflows` 410;
  guest chaos 403; `?token=` overlong value 403 (no 500).
- `tests/test_ratelimit.py`: per-tier 429 + recovery (see §4).
- Update `tests/test_security.py` minimally if status codes for malformed
  schemes are asserted (currently only missing→401/403 and wrong→403,
  both preserved).

## 8. Risks / non-goals

- No migration was applied: expiry/revocation/quotas are design-only until
  the `ApiToken` change in §3.1 lands with an Alembic/manual migration for
  both SQLite (`data/*.db`) and Postgres (`DATABASE_URL`).
- The startup log print of the demo credential remains (needed for first
  boot UX); rotation procedure (§2) + log scrubbing is the mitigation until
  guest sessions (§3) remove the need to share it.
- `localStorage` credential storage in the web app is accepted demo risk;
  guest sessions reduce its value to ≤60 min / ≤5 workflows.
