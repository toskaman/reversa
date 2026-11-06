# Changelog — REVERSA V2

All entries describe **committed** state only (exact commit hashes below).
Test counts were observed by executing the API suite against pristine
`git archive` extracts of each commit with the workspace `.venv`
(Python 3.14.4, pytest 9.2.0) on 2026-11-05, and independently re-run by
the orchestrator on the merged trees before commit (see VERIFIED notes).

Skips in all releases are the same two honest conditional skips
(Vultr live-provider eval, GitHub live cycle); no Vultr/GitHub secrets
were present in the environment when the counts were observed.

## RC8 — Red-team replay remainders closed (0.2.0-rc.8)

- Commit: `06651ab`, 2026-11-06 (joint API+web bump; tag `v0.2.0-rc.8` after CI + prod verification).
- Post-RC7 replay of `.agents/reviews/redteam-v5.md` (11 findings re-read
  against code+tests): 03 already FIXED in RC7; RC8 fixes 01 (mint tier
  20/60 on owner guest-session + token mint), 04 (durable approver =
  authenticated `token:`/`guest:` actor, client label kept as
  `decided_by_label`), 05b (`MAX_PLAN_STEPS = 32`), 07 (public-mint
  windows ≤10k, SSE tickets ≤1k, oldest-first eviction), 10 (bool
  rejected for int inputs and `depends_on`). 06/11 accepted risks
  (documented), 02/05/08 partial with documented limits, 09 open by
  design (protocol_v5 stays unwired). Report:
  `.agents/reviews/redteam-v6-replay.md`.
- API suite: 778 passed / 2 honest skips on pristine `git archive`
  extract of `06651ab` (workspace `.venv`, 105 s) — 771 RC7 + 7 new
  `test_redteam_v6_fixes.py`.
- No schema migration (create_all unchanged; no new columns).

## RC7 — V5 redteam fixes + A/B prompt decision (0.2.0-rc.7)

- Commit: `5dac22a`, 2026-11-06 (joint API+web bump; tag `v0.2.0-rc.7` after CI + prod verification).
- V5 wave2 (`418adff`) + V5 redteam fixes (`084b4d2`): atomic chaos cap, token
  revocation + revoke-historic CLI, protocol_v5 (experimental, not wired),
  eval_v5 harness, safe evidence JSON parse, SSE ticket no-burn, input bounds,
  planner extras strip, short-desc 224 chars (LabLab 255 limit).
- API suite: 771 passed / 2 honest skips on pristine `git archive` extract of
  `084b4d2` (workspace `.venv`, 105 s); `5dac22a` touches version strings only
  (no test references them; CI re-runs the suite on the merged tree).
- Live prompt A/B (2026-11-06, `deepseek-v4.1-flash-1017`, 12 balanced cases,
  33,578 tokens, no early stop): A 10/12 = 0.833 kept in prod, B protocol_v5
  11/12 = 0.917 stays experimental (+19% tokens, simple-legit regression,
  flagship step deviation). Details: `docs/jury/05-ai-integration.md`.

## RC6 — Guest chaos for the jury Recovery Moment (0.2.0-rc.6)

- Commit: `db99170`, tag `v0.2.0-rc.6`, 2026-11-05.
- API suite: **689 passed, 2 skipped, 0 failed** — observed locally on
  the merged tree (Python 3.14.4, pytest 9.2.0, 103s).
- CI: success on the RC commit (run 42115552403, 1m43s).
- Prod (217.69.7.155): healthz `0.2.0-rc.6`, readyz ready; guest chaos
  inject observed **201** live; browser smoke **10/10 ALL PASS,
  0 console errors** (settings, agentic clarify, plan, execute wf83,
  workflow graph, chaos scenario wf84, recovery list, evidence VALID,
  connectors).
- Change: the guest-actor middleware no longer denies chaos. Rules are
  org-scoped (saga matches `ChaosRule.org_id`), `times <= 10`, capped
  at 50 active rules per org (429 beyond), and swept at guest-session
  expiry — a guest can only fault its own ephemeral demo tenant.
  Tests: 3 rewritten to the allow-contract, 1 CORS test retargeted to
  the quota-410 path, 1 new cap test, plus A/B cross-guest isolation.
- Smoke script `reversa/tests/e2e/smoke_browser.py` is now agentic:
  asserts NEEDS CLARIFICATION on the vague default intent, then runs
  the deterministic plan/approve/execute path; env-independent
  settings check; no crash when the workflow link is absent.

## RC5 — Agentic Cycle 2 live (0.2.0-rc.5)

- Commit: `0cecb98` (version bump; feature merge `ab0e66b`),
  tag `v0.2.0-rc.5`, 2026-11-05.
- API suite: **688 passed, 2 skipped, 0 failed** on the merged tree;
  node 27/27, `tsc --noEmit` clean, `next build` green.
- CI: success on the RC commit (run 42111933000, 1m30s).
- Content: intent gate (clarify max 3 / refuse REFUSAL_CODES),
  offboarding (3 steps) + escalation (7 steps) templates, eval matrix
  30 → 100 cases, cost-guarded live runner, provenance UI
  (contracts + header), bench + live-eval docs, CORSMiddleware
  outermost (middleware 403/429 carry ACAO).
- Live campaign (2026-11-05, `deepseek-v4.1-flash-1017`, key from local
  DPAPI store): 2 runs × 10 adversarial-heavy cases, 15387 + 16588 =
  **31975 tokens**, JSON 100%, DAG 100%, schema-valid 20% / 10%
  (raw model output; every invalid row rejected by the deterministic
  validator, never executed). Aggregates in
  `docs/benchmarks/ai-eval-live-RESULTS.md`; per-row JSON local only.
- Prod proofs on RC5: E2E IA wf80 + wf81 (mint 201 → intent 201
  `vultr-inference` → approve → execute COMPLETED 9/9 VERIFIED,
  evidence chain VALID, 54 events). Bundles local + mirrored.

## RC4 — Cycle 1 merge + P0 hardening (0.2.0-rc.4)

- Commit: `3680cca` ("V3 Cycle 1 merge + P0 fixes (0.2.0-rc.4)"),
  tag `v0.2.0-rc.4`, 2026-11-05.
- API suite: **363 passed, 2 skipped, 0 failed** — 365 collected.
  Delta +105 vs RC3 (Cycle 1 agent suites + P0 repro tests, all observed
  on the merged tree before commit).
- CI: 4/4 jobs green on the RC commit (run 42084171882: api 1m26s,
  web 40s, docker 1m07s, secrets-scan 6s).
- Web: `tsc --noEmit` clean, `next build` 13/13 pages.

### Added (V3 Cycle 1, merged)

- Structured agentic refusals: Vultr provider may emit `meta.refusal`
  → typed `OUT_OF_SCOPE` / `NEEDS_CLARIFICATION` carried by the
  existing 422 PLAN_REJECTED path, no route change
  (`tests/test_agentic_refusal.py`, 9 tests).
- AI eval matrix 30 → 100 offline cases + capped live runner
  (`REVERSA_EVAL_LIVE` gate, 25 cases / 60k tokens caps, anonymized)
  and `docs/benchmarks/ai-eval-live-PROTOCOL.md`.
- Live eval report `docs/benchmarks/ai-eval-live-RESULTS.md`:
  deepseek-v4.1-flash-1017, n=30, 29/30 accepted (7 via
  validator-feedback retry, 1 honest EMPTY_PLAN rejection), P50 6.8 s,
  87k tokens; baseline 100%/0% (template, never refuses).
- Typed nested-shape guards across all 14 actions + engine
  (`tests/test_nested_shapes.py`, 42 tests, red→green).
- Recovery verdict hardening F1–F9 + `tests/test_recovery_verdicts.py`
  (13 tests); +21 GitHub contract tests; +2 chaos-on-AI-path tests.
- `docs/benchmarks/load-protocol.md` (concurrency campaigns, isolated
  env required); jury docs synced to rc.3 state; LabLab text + V3
  storyboard (re-render pending supervised session).
- Recovery UX: truncation notice on the 500-event feed; workflow
  detail loading/error/retry states.

### Fixed (P0, reproduced first)

- P1-1 (was crash): compensation starting while a retry was scheduled
  raised `InvalidTransition RETRY_SCHEDULED -> SKIPPED` (HTTP 500 on
  resume). `RETRY_SCHEDULED` may now transition to `SKIPPED`
  (scheduled retry dropped, never executed), with a natural-sequence
  repro test (crash → verifier-down → FAILED sibling → resume →
  COMPENSATED, chain valid).
- R1 investigated, NOT reproduced: `RETRYING -> VERIFYING` cannot fire
  through any natural pump sequence (step 3 restores RUNNING on the
  retried action's own ready-path; proof in code review). Pinned by a
  last-action-retry → COMPLETED regression test instead of an
  untestable transition. No code change.
- P0-3: `users: []` passed validation but failed at execution
  (PreconditionFailed). Validator now rejects empty `users` at plan
  time (422, validator/executor parity).
- P0-2: public guest-mint bucket was global behind Caddy (one 5/hour
  bucket for all visitors). Buckets are now per visitor IP via the
  last X-Forwarded-For entry when the peer is a trusted proxy
  (`REVERSA_TRUSTED_PROXIES`, default loopback + private ranges);
  forged headers from untrusted peers are ignored (5 tests, incl.
  route-level per-visitor independence). JuryLaunch shows an honest
  rate-limit message on 429 instead of the owner-token fallback.

## RC3 — AI planning reliable live (0.2.0-rc.3)

- Commit: `25a6142` ("AI reliability: users-shape prompt rule + 8k
  token budget (0.2.0-rc.3)"), tag `v0.2.0-rc.3`, 2026-11-05.
- API suite: **258 passed, 2 skipped, 0 failed** — 260 collected.
  Delta +1 vs RC2 (offline retry-loop test for the live failure shape).
- CI: 4/4 jobs green on the RC commit (api, web, docker, secrets-scan).

### Fixed

- Model emitted `"users": 6` (headcount, not objects) → repeated
  `PLAN_REJECTED`: system prompt now pins the nested `users` shape
  with an expansion rule + example (verified 2/2 valid full plans
  live before commit).
- `max_tokens` 2000 → 8000: reasoning models spend ~700–1800
  tokens thinking; 2000 truncated plans mid-JSON (measured live).

## RC2 — Vultr Inference live + AI-shape hardening (0.2.0-rc.2)

- Commit: `2804f15` ("AI-shape hardening: nested users validation +
  typed executor guard (0.2.0-rc.2)"), tag `v0.2.0-rc.2`, 2026-11-05.
- API suite: **257 passed, 2 skipped, 0 failed** — 259 collected.
  Delta +2 vs RC1 (nested-users regression tests).
- CI: 4/4 jobs green on the RC commit (api, web, docker, secrets-scan).

### Added

- Vultr Serverless Inference operational in prod: subscription key
  retrieved via Cloud API, `deepseek-v4.1-flash-1017` configured,
  live `POST /api/v1/intents` returns `provider: vultr-inference`
  (10-step plan, accepted after 2 attempts, ~7.7 s wall).

### Fixed

- `identity.provision_users` with AI-shaped `users` (strings instead
  of `{email}` objects) crashed the executor with an untyped
  `TypeError` (HTTP 500 in prod): `validate_plan` now rejects
  non-object users at plan time (`BAD_INPUT_TYPE`, feeds the planner
  retry loop), and the executor raises typed `PreconditionFailed`
  (clean action FAILED, saga COMPENSATED) if one ever slips through.

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
