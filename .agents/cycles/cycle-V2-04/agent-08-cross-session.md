# AGENT-08 — Cross-Session Isolation Attacks, REVERSA V2 cycle 4

Offsec attacker vs guest/session isolation on the LANDED cycle-4 tree
(AGENT-07 per-session ephemeral orgs + public mint + `?token=` removal).
Localhost only (live-server anon curl + isolated TestClient stacks on fresh
temp DBs). Non-destructive. Every citation read with tools; every verdict
executed, never invented.

## Verdict up front

Per-session isolation HOLDS: 27/28 attack probes matched the hardened
expectation, plus 2/2 leak-confirmation add-ons. Mutual workflow invisibility
(404 both directions + owner), org-scoped demo resources (A=1/5/2/1/1 rows,
B=0/0/0/0/0), ticket-mint oracle closed (404), cross-session
execute/approve/cancel all 404 with zero quota burn, expiry sweeps the whole
ephemeral org (org row + workflows + events + all 5 demo stores = 0 rows
left), sweep guard refuses non-guest orgs, public mint is quota-fixed (2/2),
body-override 422, per-IP 5/hour 429 + Retry-After with X-Forwarded-For
spoofing ignored, `?token=` is dead (401), and expired credentials are 403
on all 7 probed surfaces. ONE live hole, reproduced 3x: **V4-1 quota race**
— a 10-thread burst against `max_workflows=5` minted 10/10 workflows (2x
overshoot, check-then-act TOCTOU in `GuestSessionMiddleware`, no lock).
SSE tickets remain bearer instruments (V4-2, accepted design, theft impact
now relatively larger since tickets are the ONLY cross-session read path).
R4 pop-before-bind still live (V4-3, minor). Full suite: 3 failed / 251
passed / 2 skipped — all 3 failures are stale-test fallout from the
intentional cycle-4 behavior changes, not regressions.

## What changed under me (racing tree)

Session started on a clean tree (`f2a6152`, V2-03 merged). First attack run
hit the OLD shared-org model (cross-guest reads 200). Before the second run,
siblings landed the cycle-4 auth rewrite (`auth.py` +187, `guest_sessions.py`
+74, `workflows.py` SSE `?token=` removal, `evidence.py` format gate,
`test_security.py` updates, web renames) plus `.agents/cycles/cycle-V2-04/`
with agent-01/02/05/09 reports (no agent-07 report file yet, but the
AGENT-07 code — credited in `auth.py:140` — is in the tree). All verdicts
below are against the NEW model; old-model numbers are kept only as the
pre/post comparison in the matrix table.

## Attack matrix (re-runnable)

Scripts (kept under `%TEMP%`, isolated temp DBs, localhost-only):
`a08_xsession_v4.py` (28 probes), `a08_xsession_v4b.py` (2 leak add-ons),
`a08_xsession.py` (old-model run, superseded), `a08_diag.py` (org-binding
diagnostic that caught the model flip).
Run: `reversa/apps/api/.venv/Scripts/python.exe <script>` from repo root.

| ID | Attack | Old model | New model (observed) |
|----|--------|-----------|----------------------|
| V4-00 | Mint shape | shared org | `org_slug=guest-<sid>`, distinct per session, `/me` matches |
| V4-01 | B↔A + owner↔A workflow reads | 200 (shared) | 404 x4 |
| V4-02 | B lists workflows | saw A's + owner's | only own |
| V4-03 | B reads A's evidence/events/preview | 200 | 404; A reads own 200 |
| V4-03c/b | B reads A's demo resources | all rows | 0 rows (A has 1/5/2/1/1) |
| V4-04 | B mints ticket for A's wf | 201 | 404 (no oracle) |
| V4-05 | Stolen ticket redeemed anonymously | 200 stream | 200 stream (bearer — V4-2) |
| V4-05b | Ticket replay | 403 | 403 |
| V4-05c | Wrong-wf redeem | 403 + burned (R4) | 403 + burned (R4 live — V4-3) |
| V4-06 | Real-tenant caller redeems stolen guest ticket | 200 | 200 (bearer — V4-2) |
| V4-07 | Cross-session execute/approve/cancel | 200 + quota burn on victim | 404 x3, zero counter drift |
| V4-08 | Expire C → purge sweeps org | 403 only (org shared, kept) | 403 + org/wfs/events/demo rows all gone |
| V4-08b | `sweep_expired_guests()` report | n/a | sessions=1, swept=1, errors=[] |
| V4-08c | `_sweep_guest_org(owner)` guard | n/a | ValueError, owner intact; missing id → already gone |
| V4-09 | 10-thread burst vs quota 5 | 10x201 BREAK | 10x201 BREAK (V4-1, 3x reproduced) |
| V4-09b | Post-burst intent | 410 | 410 |
| V4-10 | Public anon mint | n/a (no endpoint) | 201, fixed 2/2 |
| V4-10b | Public mint with quota body | n/a | 422 |
| V4-10c | Public-guest isolation + chaos/owner-endpoint deny | n/a | 404, 403, 403, 403 |
| V4-10d/e | Public-mint rate limit + XFF spoof | n/a | 5x201 then 429 + Retry-After=3600; XFF still 429 |
| V4-11 | Rate buckets per credential | isolated | [201,201,429] vs sibling 201 |
| V4-12 | `?token=` with valid guest credential | 200 stream | 401 (removed) |
| V4-12b/c | Header stream own vs sibling wf | 200 done | 200 done; sibling = exactly `event: error / not found`, zero bytes |
| V4-13 | Expired credential, 7-surface sweep | 403 x8 | 403 x7 (no `?token=` surface left) |
| V4-14 | Expired SSE ticket | 403 | 403 |

Live-server curl (localhost:8000, anonymous only — no credentials sought or
used): `/api/v1/me` → 401, `/api/v1/workflows` → 401, forged-ticket stream →
401, `/openapi.json` → 200. Route dump proves the live build PREDATES the
guest/ticket/recovery/resume surface (no `/stream-ticket`,
`/demo/guest-sessions`, `/demo/tokens`, `/recovery-manifest`, `/resume`),
so authed attacks ran against isolated current-code stacks instead; the
matrix above is the re-run set for a freshly deployed server.

## Issues

- V4-1 [LIVE HOLE, quota race, 3x reproduced]: 10 concurrent
  `POST /api/v1/intents` against `max_workflows=5` all returned 201
  (`codes=['201' x10]`), then the 11th correctly 410s. Root cause:
  `GuestSessionMiddleware` (`auth.py:358-406` read) does check-then-act
  with no lock; `check_guest_quota` → `guest_usage` counts durable rows
  that concurrent requests have not committed yet. Same shape on the
  execute tier (not burst-tested). Impact: 2x quota overshoot demonstrated;
  larger bursts likely scale it. Fix: serialize per-session quota
  check+insert (e.g. hold `_GUEST_LOCK` across middleware check and route
  commit, or a per-session insert ticket consumed by the route), plus a
  threaded regression test. Non-destructive repro in `a08_xsession_v4.py`
  (V4-09); old-model run showed the identical 10x201.
- V4-2 [ACCEPTED DESIGN, note the shifted impact]: SSE tickets are bearer
  instruments with no actor binding (`workflows.py:332-349` read): anyone
  holding the 30s ticket URL — anonymous, sibling guest, or real-tenant
  caller — streams that workflow's events (V4-05/V4-06 both 200). Under the
  old model this added nothing (siblings could already read); under
  per-session isolation the ticket is now the ONLY cross-session read path,
  so ticket-URL handling (30s TTL, single-use, no logs) carries the whole
  guarantee. No change requested; keep TTL short and tickets out of logs.
- V4-3 [MINOR, carryover R4 confirmed live]: `_redeem_stream_ticket` pops
  before binding (`workflows.py:336-340` read): redeeming a valid ticket
  against the wrong workflow id returns 403 AND burns the ticket (V4-05c
  403/403). Effect is attacker self-DoS of a stolen ticket, not a leak.
  Fix when convenient: peek-then-pop.
- V4-4 [STALE TESTS, sibling fallout, suite red]: 3 failures on the current
  tree, all asserting intentionally-removed behavior — `test_guest_sessions
  .py:50` (`org_slug == demo slug`, now `guest-*`),
  `test_guest_sessions.py:134` (guest reads owner's wf 200, now 404 by
  design), `test_negative_matrix.py:305` (unknown evidence format falls
  back to JSON 200, now 422 by design). Owners of the cycle-4 diffs should
  update these three assertions; no product-code change implied.

## Structured report

- identity: AGENT-08, Offsec Attacker (guest/session isolation), REVERSA V2
  cycle 4 (FINAL ASCENT).
- mandate: attack guest/session isolation localhost-only (cross-guest
  reads, replay, ticket theft across sessions, quota races, expired reuse),
  curl + pytest, non-destructive; AGENT-07's code LANDED mid-session
  (credited `auth.py:140`, no agent-07 report file yet), so this attacks
  the NEW per-session-org model and the matrix doubles as the re-run set.
  Never touch prod (no SSH); never commit secrets; no push.
- files read (14): `auth.py` (full, pre- AND post-flip),
  `routes/guest_sessions.py` (full + diff), `routes/workflows.py` (cancel +
  SSE ticket/stream blocks + diff), `routes/evidence.py` (+ diff),
  `routes/recovery.py` (+ diff), `routes/chaos.py`, `main.py`,
  `ratelimit.py` (full), `models.py` (full), `config.py`,
  `connectors/services.py` (DemoStore head + `demo_router` block),
  `tests/conftest.py`, `tests/test_guest_sessions.py` (full),
  `tests/test_security.py` (full + diff), `tests/test_demo_isolation.py`
  (full), `.agents/cycles/cycle-V2-03/agent-20-redteam.md` (full).
- files modified: `.agents/cycles/cycle-V2-04/agent-08-cross-session.md`
  (this file) ONLY. Scratch: 4 probe scripts under `%TEMP%` (kept for
  re-run); all scratch SQLite dirs deleted after the runs (killing their
  throwaway demo tokens, which were never committed).
- commands run: live anon curl-equivalents (`/me` 401, `/workflows` 401,
  forged-ticket stream 401, `/openapi.json` route dump); old-model matrix
  (10x201 race first seen); org-binding diagnostic (caught the model flip);
  v4 matrix 28 probes (27/28, re-ran twice, identical); leak add-ons 2/2;
  `pytest tests/test_guest_sessions.py tests/test_security.py` → 2 failed,
  45 passed; full `pytest tests/` → 3 failed, 251 passed, 2 skipped in
  77.82s; 2-test stale-assertion pin run.
- observed results: per-session isolation holds on reads, lists, evidence,
  events, preview, tickets-mint, execute/approve/cancel, demo resources,
  and expiry sweep; public mint correctly fixed-quota + IP-throttled;
  `?token=` fully dead; tickets bearer + single-use + expiring; quota race
  overshoots 2x under 10-thread burst (3x reproduced, both models).
- tests: quoted above; the only reds are the 3 stale-assertion failures in
  V4-4 (old behavior asserted: shared-org slug/read, JSON fallback).
- issues: V4-1 quota race (live hole, fix + threaded regression test),
  V4-2 bearer-ticket design note, V4-3 R4 pop-before-bind carryover,
  V4-4 three stale tests to update.
- risks: (1) racing tree — 15 files + 3 new files got dirty DURING this
  audit; re-run the FULL suite at tag time on the exact commit set;
  (2) live localhost:8000 runs a STALE pre-guest build — nothing here
  re-probes until it is redeployed, then re-run this matrix against it;
  (3) in-memory stores (guests, tickets, rate windows, public-mint
  windows) remain single-process — disclosed, unchanged;
  (4) public mint rows accumulate until lazy expiry sweep; floods are
  IP-capped at 5/hour but sweeps only run on the guest-auth request path.
- confidence: HIGH on isolation verdicts (28 executed probes + 2 leak
  add-ons with bytes, re-ran identically); HIGH on V4-1 (3x reproduced,
  both models); HIGH on test counts (executed, quoted verbatim); HIGH on
  V4-4 staleness (exact lines + intentional diffs read); MEDIUM on
  public-mint abuse economics (IP-cap verified, distributed-source flood
  not modeled); LOW on prod (never touched — localhost-only by mandate).
- next task: (1) fix V4-1 (per-session quota serialization + threaded
  regression test); (2) update the 3 stale assertions in V4-4 to the
  cycle-4 contracts; (3) redeploy localhost/prod from the tagged tree,
  then re-run this exact matrix (`a08_xsession_v4.py` + `v4b`) against the
  fresh server; (4) optional V4-3 peek-then-pop; (5) re-run FULL suite at
  tag time on the exact commit set.
