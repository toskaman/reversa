# Changelog — REVERSA V2

All entries describe **committed** state only (exact commit hashes below).
Test counts were observed by executing the API suite against pristine
`git archive` extracts of each commit with the workspace `.venv`
(Python 3.14.4, pytest 9.2.0) on 2026-11-05, and independently re-run by
the orchestrator on the merged trees before commit (see VERIFIED notes).

Skips in both releases are the same two honest conditional skips
(Vultr live-provider eval, GitHub live cycle); no Vultr/GitHub secrets
were present in the environment when the counts were observed.

## V2-02 — Recovery Proof, resume, guest sessions, rate limits

- Commit: `3fad9e4` ("V2-02: Recovery Proof manifest, resume, guest
  sessions, rate limits, F2 fix, tickets UX, R1/D1/R3"), 2026-11-05.
- API suite: **143 passed, 2 skipped, 0 failed (VERIFIED by orchestrator
  re-run on the merged tree)** — 145 collected, ~42 s. One standing
  pre-existing warning (Starlette/httpx `TestClient` deprecation).

### Added

- Recovery Proof manifest (RPE v1):
  `GET /api/v1/workflows/{wf_id}/recovery-manifest` with evaluator rules
  C0–C7, event-ref resolution, tamper → INDETERMINATE and divergence
  handling (`routes/recovery.py`, new).
- Workflow resume: `POST /api/v1/workflows/{wf_id}/resume` for
  interrupted RUNNING / RETRYING / VERIFYING / COMPENSATING workflows,
  backed by `resume_workflow_sync` (`routes/workflows.py`,
  `engine/saga.py`).
- Guest sessions (demo): `POST /api/v1/demo/guest-sessions`,
  `POST|GET /api/v1/demo/tokens`,
  `DELETE /api/v1/demo/tokens/{name}` with demo-owner-only minting,
  quotas (410), expiry, isolation and rotation overlap
  (`routes/guest_sessions.py`, new; `GuestSessionMiddleware`).
- Rate limiting: `ratelimit.py` + `RateLimitMiddleware` (429 with
  `Retry-After`; owner unaffected).
- CLI strict verify: `--strict` with count/head anchors; plain verify
  stays prefix-consistency over events 1..N (`cli.py`).
- Health honesty: `/health`, `/healthz`, `/api/v1/health` return 503
  when degraded; `/readyz` gains a `ready` flag and 503s while the DB
  is unreachable (`routes/health.py`).
- Web Recovery views: race comparison, time machine, decision
  inspector, recovery utils; new `/recovery-race` and `/time-machine`
  pages.
- Jury evidence clips s1–s6 (plan/execution/chaos/recovery JSON,
  happy + chaos evidence bundles, passport HTML, CLI verify
  transcript, shot log) and storyboard update.
- Pilot offer, competition-v2 analysis; release-gates RC checklist
  (`.agents/release-gates.md`); infra `RUNBOOK.md`, `backup.sh`,
  `.gitignore`/`.gitattributes` for `.env`.

### Fixed

- F2 run scoping: run-scoped `DemoStore` + `workflow_id` demo-filter
  param; cross-run compensation fence (`connectors/services.py`).
- F1/F3 query shapes: workflow-list count via single GROUP BY
  (`routes/workflows.py`); `evidence.py`/`db.py` statement fixes with
  perf statement-count locks (`test_perf_regressions.py`).
- R1 (HIGH, latent): `GithubConnector.verify()` now raises
  `ConnectorError` on every error path (token/transport/unreadable
  refs/allowlist/unknown action) so saga reconciliation reads
  INDETERMINATE; only a clean 404 read returns `False`
  (`connectors/github.py`).
- D1: cancel routes every hop through the action-transition allowlist
  with journaling, and refuses with 409 while actions are in flight
  ("resume to reconcile, then cancel") instead of freezing them
  (`routes/workflows.py`).
- R3: SSE `?token=` fallback parses the auth scheme
  case-insensitively per RFC 6750 (`routes/workflows.py`).
- F5: `/readyz` no longer reports 200-when-degraded (see Health
  honesty above).
- GitHub hardening: deny-by-default repo allowlist
  (`REVERSA_GITHUB_ALLOWED_REPOS`, `GITHUB_REPO_NOT_ALLOWED`),
  token+allowlist registration decision
  (`GITHUB_NOT_CONFIGURED`), honest no-server-idempotency stance
  (no `Idempotency-Key` header sent).
- Vultr planner metering + substitution detection (`planner/vultr.py`).
- New `VERIFYING → UNKNOWN_OUTCOME` transition (`engine/states.py`).
- `deploy.sh` / `healthcheck.sh` fixes (`DOMAIN` handling).

### Changed

- Web live view migrated from SSE `?token=` to single-use
  `?ticket=` minted via `POST /workflows/{id}/stream-ticket`
  (`EventTimeline.tsx`); server fallback retained while clients
  migrate.
- README test/benchmark figures updated for V2.

### Known gaps carried (not regressions; see cycle QA reports)

- `GET /api/v1/connectors*` is the only route family with zero tests.
- Chaos-matrix CM-06/07/11/12/13/14/16/17/18 still missing (CM-01–05,
  CM-08–10 covered); no MANUAL_REQUIRED end-to-end test.
- Approval-expiry (410) path still untested; cancel/evidence/events
  negative matrices incomplete.

## V2-01 — P0 SEC/REC fixes, SSE tickets, GitHub skeleton

- Commit: `63bb949` ("V2-01: P0 SEC/REC fixes, SSE tickets, XSS escape,
  GitHub skeleton, audits"), 2026-11-05.
- API suite: **49 passed, 2 skipped, 0 failed (VERIFIED by orchestrator
  re-run on the merged tree)** — 51 collected, ~25 s (same standing
  Starlette warning).

### Fixed (security)

- P0-SEC-01: anonymous demo reads closed — `GET
  /api/v1/demo/{service}/resources` dropped the `org_id` query param;
  org now comes from auth context; legacy `?org_id=` is ignored
  (`connectors/services.py`). Locally re-probed: former 200s now 401.
- SSE tickets (P1-SSE-01): `POST /workflows/{id}/stream-ticket`
  mints single-use, workflow-bound, 30 s-TTL tickets; stream accepts
  `?ticket=`; replay/forgery/cross-workflow/expiry all 403
  (`routes/workflows.py`). Malformed `Last-Event-ID` no longer risks
  a 500.
- Stored XSS: HTML evidence export escapes every interpolated value
  (`routes/evidence.py`); payload re-probe inert.
- Strict `Bearer` parsing + 512-char cap (`auth.py`).

### Added

- Tri-state recovery: UNKNOWN_OUTCOME / INDETERMINATE semantics —
  verifier errors defer instead of proving absence; fail-closed
  compensation; startup reconciliation with additive stats
  (`engine/saga.py`).
- GitHub connector skeleton: real REST shape for a dedicated test
  repo (create/label/update/close, verify re-read, close-based
  compensation), deliberately unregistered, 13 contract tests
  (offline MockTransport + 1 live skip) (`connectors/github.py`).
- Specs and plans: recovery-proof-engine, commercial-v2,
  competition-v2, ux-v2-wireframes, token-rotation, chaos-matrix-v2,
  concurrency-plan, video-v2-storyboard.
- Full audit pack: architecture, inference-path, frontend, infra,
  release, offensive-security, QA baseline, evidence-verify,
  redteam (`.agents/cycles/cycle-V2-01/`).

### Known gaps carried (fixed or still open in V2-02, see above)

- V2-01 left R1 (GitHub `verify()` conflating error with absence),
  D1 (cancel allowlist bypass) and R3 (case-sensitive SSE fallback)
  open; all three are fixed in V2-02.
