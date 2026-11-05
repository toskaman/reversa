# AGENT-11 — Prod-Area Security Re-probe (REVERSA V2 cycle 3)

- Target: LOCAL stack only — `http://127.0.0.1:18224` (own throwaway uvicorn,
  isolated `REVERSA_DATA_DIR` under `%TEMP%`, destroyed after). Prod was never
  touched; no SSH; localhost probes only.
- Repo root: `D:/Hackatons/Vultr`
- Date (UTC): 2026-11-05
- Base: HEAD `3fad9e4` ("V2-02 … R1/D1/R3 (143 green)"). Working tree was DIRTY
  (16 modified + 3 untracked from concurrent cycle-3 siblings) at probe time;
  see Issues. All live probes ran against the tree as booted ~15:50 UTC.
- Method: `curl.exe` probes + `pytest` only. Non-destructive (all writes went
  to the temp stack's own SQLite files, since deleted).

## Verdict

All four mandated checks **hold on the local stack**: Recovery Manifest and
guest-mint reject anonymous callers with **401**; rate limiting emits **429 +
`retry-after`** past the tier budget; the scratch create-then-cancel flow in
the demo tenant behaves (`201 → 200 CANCELLED → 409` on re-cancel, `409` on
cancel-after-completion, `409 R4_NOT_TERMINAL` manifest on live workflows).
A genuine live **in-flight** cancel `409` has no curl-only path on the
synchronous engine (in-flight states are transient); that slice is covered by
committed tests, all green (named below).

## Auth-credential discipline (read before judging the authed probes)

- There is **no unauthenticated public guest-mint flow**: `POST
  /api/v1/demo/guest-sessions` requires `get_current_org` +
  `require_demo_owner` (committed `routes/guest_sessions.py:74-80`,
  `auth.py:182-190`), and the Jury Mode UI requires a pre-configured
  demo-owner token (`components/JuryLaunch.tsx:57-65` — sibling's uncommitted
  file, read as corroboration only).
- Per mandate ("authed checks use ONLY a guest credential … else mark
  unprobed"): on a foreign stack the authed checks would be unprobed. On my
  own throwaway localhost stack I am the demo owner, so I minted **one**
  guest via the documented Jury flow (owner token used for exactly that one
  mint call) and ran **every** subsequent authed probe with the guest
  credential only (`rev_guest_*`, 60-min TTL, quota-bound). Owner token and
  guest credential are redacted everywhere and were destroyed with the temp
  stack. No prod or foreign-stack secret was ever used.

## Observed results (curl, localhost only)

Base URL `http://127.0.0.1:18224`; demo tenant `acme-demo`.

| # | Probe | Result |
|---|-------|--------|
| A1 | Anon `GET /api/v1/workflows/1/recovery-manifest` | **401** `{"detail":"missing Bearer [REDACTED]"}` |
| A2 | Anon `POST /api/v1/demo/guest-sessions` `{}` | **401** same body |
| A3 | Anon `POST /api/v1/workflows/1/execute` | **401** same body |
| A4 | Anon `GET /api/v1/me` | **401** same body |
| A5 | 35× rapid anon `POST /api/v1/intents` (invalid body) | 30× **422**, then **429** ×5; 429 body `RATE_LIMITED`/`tier=intents`, header **`retry-after: 60`** |
| G0 | Guest `GET /api/v1/me` | **200** `actor=guest:<sid>`, demo tenant |
| G1 | Guest manifest for missing wf `999999` | **404** `workflow not found` (no oracle) |
| G2 | Guest `POST /api/v1/demo/guest-sessions` | **403** `guest sessions cannot mint credentials` |
| G3 | Guest `POST /api/v1/demo/chaos` | **403** `FORBIDDEN` middleware body (guests barred from chaos) |
| S1 | Guest create scratch wf A | **201**, `AWAITING_APPROVAL`, 10 steps |
| S2 | Guest manifest on live wf A | **409** `R4_NOT_TERMINAL` |
| S3 | Guest cancel wf A | **200**, `CANCELLED` |
| S4 | Guest cancel wf A again | **409** `workflow already CANCELLED` |
| S5–S6 | Guest create + approve wf B | **201** then **200** `READY` |
| S7 | Guest execute wf B | **200**, `COMPLETED` |
| S8 | Guest manifest on completed wf B | **200**, per-action `RESTORED` verdicts |
| S9 | Guest cancel completed wf B | **409** `workflow already COMPLETED` |
| S10 | Guest `GET /api/v1/demo/crm/resources` | **200** |
| S11 | Bad-token demo resources | **403** `invalid token` |

Notes:

- A5 nuance: the invalid intent body returned **422, not 401** — request-body
  validation surfaces before the auth dependency. The rate limiter still
  counted those hits (fixed window keyed by IP for anonymous callers), so
  the 30-then-429 boundary plus `retry-after` is genuine. A valid-body anon
  intent was not separately fired (window exhausted, server since stopped);
  anonymous-intent rejection is covered by the green suite.
- "Rate-limit headers present": the ONLY such header observed is
  `retry-after` on 429s. No `X-RateLimit-*` headers exist on any response
  (normal `200` responses carry just `date/server/content-length/
  content-type/vary`). `Retry-After` was `60` (positive integer).
- Live in-flight cancel `409` (D1 policy: actions stuck in
  `CLAIMED/EXECUTING/…`): **not producible via curl alone** — execution is
  synchronous, so no API sequence parks an action mid-flight. Covered by
  committed tests instead (below), all passing.

## Tests (`reversa/apps/api/.venv` pytest, real counts)

- Targeted security slice — `test_security.py` + `test_guest_sessions.py` +
  `test_negative_matrix.py` + `test_recovery_manifest.py` +
  `test_demo_isolation.py`: **87 passed** (24.20 s).
- Full suite `tests/`: **200 passed, 2 skipped** (53.69 s).
- Named subsets: `-k "inflight or in_flight or cancel"` on
  `test_negative_matrix.py` + `test_security.py` → **11 passed**
  (includes `test_cancel_inflight_action_409` and
  `test_cancel_refused_with_inflight_action`); `-k "rate_limit or
  retry_after or mint"` on `test_guest_sessions.py` → **8 passed**
  (includes `test_intent_rate_limit_429_and_recovery`,
  `test_execute_rate_limit`, `test_c3_rate_limit_retry_after_positive_int`).
- One pre-fix self-error (mine, corrected mid-session): a greedy credential
  regex captured trailing JSON, so the first guest batch 403'd; re-minted
  with a correct parse and re-ran — results above are the clean rerun.

## Issues

1. **Dirty tree / sibling-edit concurrency:** 16 tracked files modified + 3
   untracked by concurrent cycle-3 siblings during this probe (incl.
   `ratelimit.py`, `saga.py`, `evidence.py`, new `test_negative_matrix.py`
   and `JuryLaunch.tsx`). Nothing was stashed, reverted, or touched. Files
   my verdict depends on (`auth.py`, `routes/workflows.py`,
   `routes/recovery.py`, `routes/guest_sessions.py`) are **unmodified** vs
   `3fad9e4`. The `ratelimit.py` sibling diff was read in full: hardening
   only (window-store cap, trailing-slash tier norm, tier/clamp fail-safes,
   `max(int+1,1)` Retry-After) — the observed 30-then-429 + `retry-after`
   behavior is identical on the committed base.
2. **Ports 8123 and 18223 already LISTEN** (unknown/other-agent processes,
   both serving `/health` 200) — left alone as protected; probe stack used
   free port **18224** (verified free before boot, verified silent after
   stop; own PID 2408 stopped at end of session).
3. `JuryLaunch.tsx` (cited for the no-public-mint corroboration) is an
   uncommitted sibling file — the normative evidence is the committed route
   + `require_demo_owner`, which says the same thing.

## Risks

- Prod re-probe not done (out of mandate: localhost only). Whatever is live
  on prod still needs this exact probe set post-deploy.
- Rate limiting covers only `POST /api/v1/intents` and `POST
  /api/v1/workflows/{id}/execute` (fixed window, single-process memory
  store); all other routes unthrottled. No `X-RateLimit-*` budget headers —
  clients learn the limit only when 429'd.
- Guest sessions + SSE tickets remain in-memory (single-process); restart
  invalidates guests (fail closed — correct for guests).
- The 422-before-401 ordering on invalid bodies is a minor information
  nicety (anonymous callers can distinguish "bad shape" from "no auth"),
  not a vulnerability — no data leaks.

## Confidence

- **HIGH** on manifest-anon-401, guest-mint-anon-401, 429 + `retry-after`
  boundary, guest 403 edges (mint/chaos), and the full guest
  create→cancel→409 / create→approve→execute→manifest-200 flow — all
  observed as live bytes/status codes on localhost.
- **HIGH** on in-flight cancel 409 via committed tests (11/11 named subset
  green), **unprobed live** (no curl-only path; stated, not faked).

## Structured report

- identity: AGENT-11, Offensive Security Auditor (re-probe), REVERSA V2
  cycle 3.
- mandate: re-probe read-only endpoints + safe auth edges with curl only
  (manifest anon 401, guest-mint anon rejection, cancel in-flight 409 on a
  scratch create-then-cancel workflow in the demo tenant, rate-limit headers
  present); non-destructive; guest-credential-only authed checks; localhost
  only; no prod SSH; no secrets committed; no push.
- files read (12): `.agents/cycles/cycle-V2-01/agent-11-offsec.md`,
  `.agents/cycles/cycle-V2-02/agent-11-local-reprobe.md`,
  `reversa/apps/api/{tests/conftest.py}`,
  `reversa/apps/api/src/reversa_api/{main,auth,config,ratelimit}.py`,
  `routes/{workflows,recovery,guest_sessions}.py`,
  `reversa/apps/web/components/JuryLaunch.tsx` (uncommitted), plus
  `git diff` of `ratelimit.py`.
- files modified: `.agents/cycles/cycle-V2-03/agent-11-prod-reprobe.md`
  (this report only). No source files touched.
- commands run: workspace listings; `git log/status/diff`; own uvicorn on
  127.0.0.1:18224 with temp data dir (started, health-checked, stopped;
  temp dir deleted); ~9 curl batches (anon 401s ×4, 35× rate-limit + 429
  header/body capture, owner→guest mint ×2 incl. one re-mint after a
  self-inflicted regex error, guest 403 edges ×3, guest scratch
  create/cancel/recancel ×4, guest create/approve/execute/manifest ×4,
  cancel-terminal/guest-read/bad-token ×3); `pytest` targeted (87),
  full (200 passed, 2 skipped), named subsets (11 + 8).
- observed results: table above — all auth boundaries hold; `retry-after:
  60` on 429; no `X-RateLimit-*` anywhere; live in-flight 409 not
  curl-reachable, pytest-covered.
- tests: quoted above; zero failures in this session.
- issues: sibling dirty-tree concurrency (verdict files unmodified;
  ratelimit diff read and behavior-preserving); ports 8123/18223 occupied;
  JuryLaunch uncommitted.
- risks: prod not re-probed; rate limits cover 2 tiers only, no budget
  headers; in-memory guest/ticket stores; 422-before-401 ordering noted.
- confidence: HIGH (live bytes) except live in-flight 409 (pytest-only,
  11/11 green).
- next task: deploy current HEAD to prod, re-run this exact probe set
  against prod (A1/A2/A5 must reproduce there), then track `X-RateLimit-*`
  budget headers + shared ticket/guest stores for multi-worker deploy.

## Scope honesty

- Never touched prod or any foreign stack (ports 8123/18223 probed with one
  read-only `/health` GET each for identification, otherwise untouched);
  never authenticated anywhere except the local temp stack; created/modified
  nothing outside `%TEMP%/reversa-a11-v203` (deleted with all credentials)
  and this report. No brute force, no secret exfiltration (owner boot token
  + guest credential redacted; temp stack destroyed with its data dir).
  Server process stopped; port verified silent.
