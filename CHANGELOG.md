# Changelog — REVERSA V2

All entries describe **committed** state only (exact commit hashes below).
Test counts were observed by executing the API suite against pristine
`git archive` extracts of each commit with the workspace `.venv`
(Python 3.14.4, pytest 9.2.0) on 2026-11-05, and independently re-run by
the orchestrator on the merged trees before commit (see VERIFIED notes).

Skips in all releases are the same two honest conditional skips
(Vultr live-provider eval, GitHub live cycle); no Vultr/GitHub secrets
were present in the environment when the counts were observed.

## V2-04 — Guest isolation P0, zero-token Jury Mode, CM 20/20 (RC1)

- Commit: `63bdada` ("V2-04: guest isolation P0, zero-token Jury Mode,
  CM 20/20, V4-1/V4-5, 0.2.0-rc.1"), tag `v0.2.0-rc.1`, 2026-11-05.
- API suite: **255 passed, 2 skipped, 0 failed (VERIFIED by orchestrator
  re-run on the merged tree)** — 257 collected, ~66 s (same standing
  Starlette warning). Delta +51 vs V2-03.
- CI: 4/4 jobs green on the RC commit (api, web, docker, secrets-scan).

### Added

- Per-session ephemeral guest orgs (`guest-<sid>`): true A/B isolation
  with zero schema change; expiry sweeps the org and its rows.
- Public guest mint (`POST /api/v1/demo/guest-sessions/public`): no
  credential, fixed 2/2 quotas, chaos-disabled, 5/hr/IP rate limit.
- Zero-token Jury Mode: Launch Interactive Demo works with no
  preconfigured token; detail views fall back to the guest token.
- Chaos matrix 20/20 (CM-14/06/07/16/12/17/18); crash-recovery suite
  (13 tests); INDETERMINATE + MANUAL_REQUIRED manifest scenarios.
- `transition_action` public engine helper; unknown evidence format → 422;
  deprecated SSE `?token=` fallback removed (header + `?ticket=` remain).
- A11y pass (contrast AA, focus-visible, skip-link, reduced-motion);
  Execution Comparison rename; ManifestPanel on Race/Time Machine.
- Concurrency bench results (`docs/benchmarks/concurrency-results.md`);
  rollback runbook; RC release notes (`.agents/release-v0.2.0-rc.1.md`).

### Fixed

- V4-1 guest quota race: per-session asyncio lock across quota check +
  route (threaded regression test proves exact-quota admission).
- V4-5 guest detail views: central token fallback (owner wins, else guest).
- CI secrets-scan errexit bug (`set +e` around grep; status preserved).

## V2-03 — Jury Mode, F3/F4, 30-case AI eval, CM 13/20, CI gates, video V2

- Commit: `f777543` ("V2-03: Jury Mode, F3/F4, 30-case AI eval, CM 13/20,
  CI gates, video V2, 404-sniff+CLI fixes"), 2026-11-05.
- API suite: **204 passed, 2 skipped, 0 failed (VERIFIED by orchestrator
  re-run on the merged tree)** — 206 collected, ~49 s (same standing
  Starlette warning). Delta +61 vs V2-02: +4 AI eval, +11 guest/ratelimit,
  +2 engine (F3), +3 chaos matrix, +1 perf (F4), +6 connectors routes (new),
  +30 negative matrix (new), +3 CLI malformed-bundle, +1 GitHub 403/404.

### Added

- Jury Mode 1-click (`components/JuryLaunch.tsx`, `lib/api.ts` `apiAs()`
  helper): check → mint guest → create → approve → execute with honest
  per-phase states and separate guest localStorage keys.
- Nav links for `/recovery-race` + `/time-machine`; DecisionInspector card
  on the workflow detail view (real created-payload data).
- CI gates: docker image-build job (api+web, no push) + secrets-scan job
  (fail-closed on token patterns / PEM headers).
- Video V2: `docs/jury/demo-v2.mp4` (85 s, 1280×800, h264+AAC voiceover)
  + `demo-v2.srt` + 6 scene clips; v1 kept as fallback.
- Chaos CM-11 (scoping+budget), CM-13 (conditional refusal),
  CM-15 (irreversible → MANUAL_REQUIRED): tally 13/20.
- AI eval 10 → 30 offline cases (legit/ambiguous/contradictory/
  impossible/injection/dangerous) with per-category summary.
- RPE spec sections 4.4–6 restored incl. section 5 refusal codes;
  GitHub live-enablement runbook.

### Fixed

- F3 chaos multi-rule shadowing: matching-rule predicate in query,
  lowest-id MATCHING rule fires (was: first rule shadowed the rest).
- F4 evidence export double-read: single-pass `_bundle()` via
  `verify_chain_rows` (~11% faster, byte-identical output).
- P0 404-sniff: `ConnectorError.status_code` is now structured; only a
  real HTTP 404 reads as absence (a 403 mentioning "404" raises).
- CLI verifier: malformed bundles / garbage files / missing files return
  INVALID (exit 1), never traceback.
- Docs: README counts, chaos tally + row cells, refused-by-design
  narrowing (only `no_real_payment` + mid-flight-cancel are
  code-enforced), recovery.py docstring.

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
