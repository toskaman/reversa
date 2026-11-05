# AGENT-20 — Independent Red-Team Audit (REVERSA V2 cycle 1)

Hostile audit of V1 claims. Every citation was read with tools before being
written. Live reproductions ran against a LOCAL API (same code, SQLite);
production was probed only on its unauthenticated surface plus auth
enforcement, because the demo token is server-log-only by design and no
credential was available. Nothing below invents a deployment or test result.

## Verdict up front

Core engine claims SURVIVE reproduction: happy COMPLETED with a 59-event
valid chain, chaos COMPENSATED with 7 reverse-order undos, CLI offline VALID,
tamper INVALID, auth error codes correct. But the dossier contains one wrong
state name, one wrong field count, one phantom artifact ("incident report"),
one vacuous "SSRF verified", a stored-XSS bug in the HTML export, and
cross-run resource aliasing that a hostile jury member can demonstrate live.
Bench/cost/reboot/history numbers have no committed raw evidence.

## Live reproduction (local API, port 8123, fresh SQLite data dir)

Happy path — intent → approve → execute:

- `COMPLETED`, 10/10 `VERIFIED`, 59 events, `chain valid (59 events)`,
  execute 438 ms, 4 active users afterwards.
- Matches: README "10 real actions" flow, jury `04` claim 7 (59-event
  chain), matrix "59 events valide API + CLI offline" (API half here).

Chaos path — `demo-billing`/`http500`/`times=5` → intent → approve → execute:

- `COMPENSATED`, billing `FAILED` after 2 attempts, seqs 1,2,3,4,5,7,8
  `COMPENSATED` in reverse order `[8,7,5,4,3,2,1]`, seqs 9,10 `SKIPPED`,
  81 events, chain valid, execute 1.69 s.
- Matches: jury `04` claim 3 (7 undone reverse, 2 skipped), matrix
  "COMPENSATED (7 inversées)", progress "wf3 COMPENSATED 81 events".
- Resources after: 0 workspaces, 4 archived users, 1 archived org,
  1 archived queue. Matches `04` claim 3 and `09` step 5 — AND proves
  finding F2 (see below): these were the happy run's rows too.

Evidence CLI (clean UTF-8 export, no BOM):

- `VALID: offline chain valid (59 events recomputed)` on the happy bundle.
- Tampered copy (1 payload byte changed) → `INVALID: hash mismatch at
  seq 11`. Detection is not vacuous.

Edge probes (all live): double-execute → `replay:true`, still `COMPLETED`;
wrong plan_hash → 409; execute before approval → 409; chaos with unknown
connector → 422. Executing an already-terminal workflow returns its
idempotent replay (execute_key checked first,
`reversa/apps/api/src/reversa_api/routes/workflows.py:181-184`) — by design.

Production probes (unauthenticated surface only):

- `GET /healthz` → 200 `{"status":"ok","version":"0.1.0","db":true}`.
- `GET /api/v1/health` → same. `GET /` → 200, HTML served.
- `GET /api/v1/me` without token → 401; with garbage token → 403;
  `GET /api/v1/demo/chaos` without token → 401.
- Authenticated happy/chaos repro on PROD was NOT possible: no demo
  token in env, and the repo correctly contains no live token (only the
  generator `reversa/apps/api/src/reversa_api/auth.py:96`, a docs example,
  and a UI placeholder). This is good security and a hard blocker for
  the "reproduce against PROD" mandate item — recorded, not faked.

Test suite: `pytest reversa/apps/api/tests/ -q` on the current (V2) tree →
**47 passed, 2 skipped** (22 s). Zero failures. The 2 skips are the honest
Vultr-not-configured skip plus one more conditional skip.

## Bugs found (all with file:line, two proven live)

F1 — Stored XSS in evidence HTML export (proven live). `_render_html`
interpolates workflow name, actor, and payload JSON with no escaping
(`reversa/apps/api/src/reversa_api/routes/evidence.py:78-102`). A workflow
named `<script>alert(1)</script>` produced an export containing the raw
tag (probe returned `True`). Fix: `html.escape` every interpolated value.
Severity: low-moderate (self-downloaded file), but a jury "security" claim
sits right next to it.

F2 — Cross-run resource aliasing (proven live). `DemoStore.create` is
idempotent by `(org_id, kind, name)` across ALL workflows
(`reversa/apps/api/src/reversa_api/connectors/services.py:84-103`), and the
template reuses `org_slug: acme` every run. Consequences observed: the
chaos run reused the happy run's 4 users/org/workspace/queue, then its
compensation archived/deleted them — after chaos, workspaces = 0 and
archived users = 4 total, i.e. the earlier run's "VERIFIED" effects no
longer exist and its evidence is stale. The bench's 10 happy + 5 chaos
runs all mutate shared rows. "Before/during/after" resource views conflate
runs. Fix or honest-label: namespace demo resources per workflow (or per
run slug), or document that same-slug runs share state.

F3 — Chaos matcher stops at the first same-connector rule
(`reversa/apps/api/src/reversa_api/engine/saga.py:181-194`). If the
earliest rule for a connector has a non-matching `target_action`, the
function returns instead of scanning later rules — a second rule for a
different action on the same connector silently never fires.

F4 — Concurrent double-execute race
(`reversa/apps/api/src/reversa_api/routes/workflows.py:181-191`). Two
simultaneous `POST .../execute` can both pass the `execute_key` check;
the CAS claim prevents double effects, but the loser returns a
non-terminal snapshot with `replay:false, terminal:false`. Confusing
contract under double-click/load-balancer retry.

F5 — `/readyz` returns 200 even when degraded
(`reversa/apps/api/src/reversa_api/routes/health.py:30-33`). A readiness
probe must be 503 when `db:false`; orchestrators cannot distinguish.

F6 — SSE `?token=` fallback retained plus inconsistent scheme parsing
(`reversa/apps/api/src/reversa_api/routes/workflows.py:314-324` vs
`reversa/apps/api/src/reversa_api/auth.py:69-76`). Documented as
deprecated, but the token-in-URL leak and the case-sensitive
`removeprefix("Bearer ")` (strict parser is case-insensitive) remain live.

F7 — Unbounded worst-case execute duration. `execute_workflow_sync` pumps
up to 1000 iterations with backoff sleeps inside the request thread
(`reversa/apps/api/src/reversa_api/engine/saga.py:624-635,717-729`); a
permanently-indeterminate verifier returns 200/non-terminal (behavior is
tested, `reversa/apps/api/tests/test_chaos.py:127-131`) but holds the
single worker. Single-worker is disclosed; the duration bound is not.

N1 (nit, dead code) — `VultrInferenceProvider._input_keys` always returns
`[]` and is unused (`reversa/apps/api/src/reversa_api/planner/vultr.py:77-79`).
The live path passes `available_capabilities()` which DOES include inputs
(`reversa/apps/api/src/reversa_api/planner/__init__.py:23`), so prompts are
fine; only `/connectors` capability snapshots lack input lists
(`reversa/apps/api/src/reversa_api/connectors/sdk.py:93-109`).

N2 (nit) — token hashes are unsalted SHA-256
(`reversa/apps/api/src/reversa_api/auth.py:21-22`). Acceptable for 192-bit
random tokens; a salt would still be nicer.

## Claim-by-claim: overstated or unverified (hostile list)

U1 — "16-field action contracts" (`docs/jury/03-architecture.md:20-21`).
FALSE. `ActionContract` has 13 fields
(`reversa/apps/api/src/reversa_api/connectors/sdk.py:18-32`).

U2 — "Genuinely incompatible external changes refuse → MANUAL_REQUIRED"
(`docs/jury/06-security-and-recovery.md:15-16`). WRONG STATE. A
precondition refusal inside `compensate()` yields `COMPENSATION_FAILED`,
retried 3×, then `PARTIALLY_COMPENSATED`
(`reversa/apps/api/src/reversa_api/engine/saga.py:511-517,671-694`).
`MANUAL_REQUIRED` only covers `VERIFIED` actions with manual-only
capabilities (`saga.py:677-688`). Companion test
`test_concurrent_modification_blocks_compensation`
(`reversa/apps/api/tests/test_chaos.py:56-69`) asserts only a store-level
`PreconditionFailed` — it never drives any terminal state, so its name
and docstring overstate its coverage.

U3 — "Incident report" (README "reports"; `docs/jury/01`:14 "files the
incident report"; `docs/jury/09`:15 "incident report complete"). PHANTOM.
The string "incident" appears zero times in API src and zero times in the
web app. The evidence timeline is the de-facto report — say that.

U4 — "SSRF" listed as verified (`.agents/verification-matrix.md` P0
security row). VACUOUS. Zero SSRF mentions in src/tests/jury; no
user-controlled URL is ever fetched (Vultr base URL is env-only,
`reversa/apps/api/src/reversa_api/planner/vultr.py:30-36`). Correct label
is "N/A", not "verified".

U5 — "Timeouts" as an implemented control
(`docs/jury/06-security-and-recovery.md:8`). PARTIALLY TRUE. Contract
`timeout_s` (`connectors/sdk.py:27`) is never enforced by the engine; the
only real timeout is the Vultr httpx client (`planner/vultr.py:83`).

U6 — "10 real actions across CRM, Identity, Support, Billing, Notify"
(README demo step 3; video captions). LOOSE. Step 9 runs on
`reversa-core`, not one of the five
(`reversa/apps/api/src/reversa_api/templates/onboarding.py:43`), and steps
1 and 9 are read-only noops
(`reversa/apps/api/src/reversa_api/connectors/services.py:259-260,562-563`).
Accurate: 8 mutating demo actions + 2 read-only checks.

U7 — "Refused by design: real payments, mass sends, third-party accounts"
(`docs/jury/06-security-and-recovery.md:22-23`). 1 OF 3 ENFORCED. Only
`no_real_payment` exists (`connectors/sdk.py:145-147`); no mass-send or
third-party-account guard is in code (notify has no rate limit).

U8 — "Every step also works via API+cURL (see README)"
(`docs/jury/09-demo-script.md:21`). FALSE POINTER. README contains zero
curl examples.

U9 — Test-count drift: README says "19 passed"
(`README.md:66`); matrix says "20 pytest + 1 skip"
(`.agents/verification-matrix.md:11`); actual is 47 passed + 2 skipped.
Both doc numbers are stale AND mutually inconsistent.

U10 — "Deps MIT/BSD (… Caddy images)"
(`docs/jury/10-final-verification.md:11-12`). INACCURATE. Caddy is
Apache-2.0 (still MIT-compatible — fix the wording, not the stack).

U11 — "Lint" in CI claims (matrix "Lint + unit + intégration + build";
README badge implies CI). OVERSTATED. There is no linter: `lint` is
`tsc --noEmit` (`reversa/apps/web/package.json:8`), no ruff/eslint
anywhere, and `ci.yml` runs pytest + tsc + build only. Also the cited run
number `42045740960` is not verifiable from the repo.

U12 — Bench figures (505 ms / 1.78 s / 100% / 15/15). NO RAW EVIDENCE
COMMITTED — `docs/benchmarks/` has only the summary. My local numbers
(438 ms happy, 1.69 s chaos, SQLite, no network) are consistent with the
prod claims, which is supportive but not a reproduction. (The bench metric
itself is honest: it asserts COMPENSATED-or-worse but only counts strict
COMPENSATED toward recovery rate, `reversa/tests/performance/bench.py:75,90`.)

U13 — "Reboot VM vérifié" (matrix; `.agents/progress.md:25`). NO
TIMESTAMPED EVIDENCE in repo. Unverifiable-from-repo.

U14 — "35 modèles listés / model list verified live". NO COMMITTED OUTPUT.
Unverifiable-from-repo (the 401-without-key story is at least honest).

U15 — Spend "~$0.15 constaté, ~$2 projetés" (matrix, progress, README).
NO INVOICE/USAGE EVIDENCE. Unverifiable-from-repo.

U16 — "Consumed as one-shot rules" (`docs/jury/04`:10). LOOSE. Schema
allows `times` 1–10 (`reversa/apps/api/src/reversa_api/schemas.py:40`)
and the bench uses `times=5` (default 1 is one-shot — the word "one-shot"
needs that qualifier).

U17 — "59-event chain per happy run" (`docs/jury/04`:19). VERIFIED for the
canonical path (reproduced exactly 59), but any retry path changes the
count (chaos = 81). The "happy run" qualifier saves it; keep the qualifier.

U18 — Jury `02` "9 routes" list omits `/roi`, which exists
(`reversa/apps/web/app/roi/page.tsx`) and is referenced by `08`. Minor.

U19 — "No copied code" (`docs/jury/10`:12). UNATTESTED. No license headers
or provenance audit; cannot be verified by reading the tree.

U20 — "Demo systems are labeled as such" (README). API-side verified
(`demo-*` connector ids, demo org); web-UI labeling not inspected this
session (no browser run). Partial.

U21 — "Timeout run passes through UNKNOWN_OUTCOME … ends COMPLETED"
(`docs/jury/04`:14). Verified via the `crash` fault
(`reversa/apps/api/tests/test_chaos.py:72-94`); the literal `timeout` fault
maps to the same uncertain path (`connectors/sdk.py:122-124`) but has no
dedicated test. Note, not a fail.

U22 — "Tested at unit + boot" for restart reconciliation (`docs/jury/04`:17-18).
PARTIAL. Unit coverage is real (`test_engine_units.py`, incl. resume-all-
inflight-states); "boot" is just the lifespan call
(`reversa/apps/api/src/reversa_api/main.py:32`) with no process-boot test.

U23 — "66 s from real captures" (README; build script). NEARLY VERIFIED:
scene durations sum to exactly 66 s
(`docs/jury/build_video.py:17-27`), screenshots are required inputs
(`build_video.py:66-68`), `demo.mp4` (510 KB) + `demo.srt` exist — but the
binary's real duration was not measured (no ffprobe on this host).

U24 — "Browser E2E 9/9". NOT REPRODUCED this session (needs running stack
+ token + Chrome). Script genuinely has 9 checks
(`reversa/tests/e2e/smoke_browser.py:28-124`); two are conditional on
finding workflow links, but the link check itself fails loudly, so a 9/9
claim remains meaningful.

U25 — "Genuinely distributed state (separate files)" for demo services
(`docs/jury/03`:17-18). LOOSE for `reversa-core`, which has NO store
(`connectors/services.py:511`) and reads the other stores directly
(`services.py:529-552`). True for the 5 demo stores.

U26 — "Usage metering" for the Vultr provider (`docs/jury/05`:12-13).
UNTRUE. `usage` stays `{}` — never populated from the inference response
(`reversa/apps/api/src/reversa_api/planner/vultr.py:52,71`).

## Confirmed-true claims (hostile spot-checks that held)

15 workflow / 14 action states and the 6 compensation capabilities match
`engine/states.py:10-52` exactly. Plan-hash-bound approvals with 30-min TTL
(`routes/workflows.py:102-107,160-167`). Demo-only chaos guard at both
layers (`routes/chaos.py:17-20`, `engine/saga.py:179`). Idempotency keys
(`models.py:71`), CAS lease claims (`engine/saga.py:139-157`), optimistic
version checks (`connectors/services.py:105-124,151-174`), startup
reconciliation (`engine/saga.py:732-818`). Redaction at append and export
(`evidence.py:35-45,68`, `routes/evidence.py:45-46,52`). Cancel-during-
compensation refused (`routes/workflows.py:203-205`). Billing approval gate
+ high risk, notify irreversible (`connectors/services.py:442,482`).
Preview with declared limits (`routes/workflows.py:225-247`). Strict
`extra=forbid` schemas (`schemas.py:8-9`), DAG validation rejecting
non-earlier deps (`planner/validate.py:52-58`). SSE single-use tickets
(`routes/workflows.py:262-311`). 9 web routes, Next.js 15, `strict:true`
tsconfig. `.env` git-ignored and untracked; remote is
`toskaman/reversa`. ROI default 100% is labeled "measured demo-benchmark
rate (5 chaos runs)" with editable inputs (`app/roi/page.tsx:10,36-37`);
prompt §15.3 exists (`prompt.txt:1649`). No exactly-once overclaim; hash
limits honestly stated. Eval documents 0% baseline refusal as a limitation
(`tests/test_ai_eval.py:94-97`) with an honest Vultr skip
(`test_ai_eval.py:100-102`).

## Risks for the jury

1. A juror re-running the demo twice on `acme` then opening Connector Hub
   sees aliased/mutated resources (F2) — the most demo-visible finding.
2. A juror asking "show me the incident report" gets silence (U3) — rename
   the evidence view's narrative before the pitch.
3. A security-minded juror grepping for SSRF/timeout/mass-send guards (U4,
   U5, U7) or opening the HTML export source (F1) finds gaps behind
   confident wording.
4. Bench/cost/reboot/model-list numbers (U12–U15) are all assert-without-
   artifact; one "prove it" question each. My local timings support the
   bench magnitudes but are not prod evidence.
5. State-name slip (U2) is exactly the kind of detail a saga-knowledgeable
   juror checks against the state diagram.

## Structured report

- identity: AGENT-20, Independent Red-Team Auditor, REVERSA V2 cycle 1.
- mandate: challenge V1 claims; reproduce one happy-path + one chaos run
  (read-only + demo tenant); verify states/resources; hunt silent bugs;
  list every unverified/overstated README/jury statement; write this file;
  no invented results; no secrets; no push; no out-of-mandate edits.
- files read: README.md, prompt.txt (§15.3), .agents/verification-matrix.md,
  progress.md, risks.md, docs/jury/00-10 (all), lablab-submission.md,
  slides (listed), build_video.py, docs/benchmarks/results.md,
  reversa/apps/api/src: main.py, config.py, auth.py, db.py, models.py,
  schemas.py, evidence.py, cli.py, engine/states.py, engine/saga.py (full),
  routes/workflows.py, chaos.py, evidence.py, health.py, connectors.py,
  connectors/sdk.py, services.py (full), github.py, __init__.py,
  planner/__init__.py, deterministic.py, validate.py, vultr.py,
  templates/onboarding.py; tests: conftest.py, test_chaos.py,
  test_ai_eval.py (+ test-name scans of security/engine/planner/happy
  suites); reversa/tests/e2e/smoke_browser.py,
  reversa/tests/performance/bench.py; reversa/infrastructure/
  docker-compose.yml; reversa/apps/web/package.json, tsconfig.json,
  app/roi/page.tsx; .github/workflows/ci.yml; .agents/decisions listing.
- files modified: `.agents/cycles/cycle-V2-01/agent-20-redteam.md` (this
  file) ONLY. Scratch (server data dir, logs, evidence exports incl. one
  local-only demo token) was created under `%TEMP%` and deleted after the
  run. No repo files otherwise touched; nothing committed; nothing pushed.
- commands run:
  - `pytest reversa/apps/api/tests/ -q` → 47 passed, 2 skipped.
  - Local uvicorn on :8123 (fresh data dir) + full happy/chaos/edge/CLI/
    tamper/XSS probe sequence (all results above).
  - PROD: `GET /healthz`, `/api/v1/health`, `/`, `/api/v1/me` (±token),
    `/api/v1/demo/chaos` (no token) → 200/200/200/401/403/401.
  - `git remote -v`, `git ls-files`/`check-ignore` (.env untracked+ignored),
    `rev_demo_` repo search (no live tokens), route/store/gallery listings.
- observed results: happy COMPLETED 10/10 VERIFIED 59 events chain-valid
  (438 ms local); chaos COMPENSATED reverse-order [8,7,5,4,3,2,1], 9+10
  SKIPPED, 81 events chain-valid (1.69 s local); CLI VALID 59 recomputed;
  tamper → INVALID seq 11; replay/409/422 edges correct; PROD healthy with
  auth enforced; suite green.
- tests: existing suite 47+2 green (covers happy, chaos reverse-order +
  resource restore, idempotent retry, UNKNOWN deferral/resume, claim race,
  startup resume, tamper, redaction, 17 security tests incl. stream
  tickets, AI-eval baseline + honest Vultr skip, github contract). NOT
  re-run: browser E2E (needs stack+token+Chrome), bench vs prod (needs
  token). Gaps: no end-to-end MANUAL_REQUIRED test, no literal-timeout-
  fault test, no process-boot test, no HTML-escape test.
- issues: F1 stored XSS (live-proven), F2 cross-run aliasing (live-proven),
  F3 chaos multi-rule shadowing, F4 double-execute race, F5 /readyz 200-
  when-degraded, F6 SSE token fallback + scheme inconsistency, F7 unbounded
  execute duration; U1–U26 overstatements/unverified items above, worst:
  U1 (13≠16), U2 (wrong terminal state), U3 (phantom incident report),
  U4 (vacuous SSRF), U26 (usage never metered).
- risks: jury-visible aliasing (F2), "show me the incident report" (U3),
  security-wording gaps (F1/U4/U5/U7), assert-without-artifact numbers
  (U12–U15), state-name slip (U2).
- confidence: HIGH on code findings (file:line cited, F1/F2/U-paths live-
  proven); HIGH on local behavioral reproduction; MEDIUM on prod behavior
  (unauth surface + auth enforcement only — authenticated PROD repro
  blocked by design, no token); LOW on historical prod numbers (bench,
  reboot, spend, model list — no committed artifacts either way).
- next task: (1) fix F1 with `html.escape` + regression test;
  (2) fix or honestly document F2 (per-run demo namespace; bench with
  unique slugs); (3) correct U1/U2/U3/U4/U5/U7/U8/U10/U26 wording;
  (4) commit raw bench JSON + reboot/model-list evidence or downgrade to
  "reported, artifact pending"; (5) add MANUAL_REQUIRED e2e,
  literal-timeout, and HTML-escape tests; (6) /readyz 503 + chaos
  multi-rule scan; (7) re-run E2E + bench against PROD with the demo token
  when the human provides it (server log only, never in repo).
