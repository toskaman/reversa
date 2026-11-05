# AGENT-01 — Architecture Audit (REVERSA V2 cycle 1)

Date: 2026-11-05. Auditor: AGENT-01 (Principal Architect).
Scope: repo architecture vs headline claims (15 workflow states, 14 action
states, 6 connectors, 10 actions), plus tech debt and complexity risks.
Method: read-only source inspection. No tests were executed and no
deployment was performed in this audit; all verdicts below come from reading
the files cited. (Mandate: write only this file.)

Baseline note: the tree is moving under parallel V2 agents. At audit time
`git status` showed 1 modified file (`auth.py`, P1-AUTH-01 hardening, keeps
all behavior contracts) and 4 untracked additions: `connectors/github.py`,
`tests/test_github_contract.py`, `docs/benchmarks/chaos-matrix-v2.md`,
`docs/product/github-connector.md`. Committed-tree verdicts below exclude
that in-flight work; its impact is assessed separately in §4.

## 1. Claim verification (committed tree)

| Claim | Verdict | Evidence (file:line) |
|---|---|---|
| 15 workflow states | CONFIRMED | `reversa/apps/api/src/reversa_api/engine/states.py:10-26` — tuple holds exactly 15 entries; `WF_TRANSITIONS` covers all 15 |
| 14 action states | CONFIRMED | `states.py:28-43` — tuple holds exactly 14 entries; `ACT_TRANSITIONS` covers all 14 |
| 6 connectors | CONFIRMED | `connectors/services.py:588-597` — `register_all()` registers demo-crm, demo-identity, demo-support, demo-billing, demo-notify, reversa-core |
| 10 actions | CONFIRMED | capabilities per connector: 2 + 3 + 2 + 1 + 1 + 1 = 10 (`services.py:214-526`) |
| 10-step onboarding template | CONFIRMED | `templates/onboarding.py:20-48` returns 10 ordered steps; DAG fan-out after step 2, join at step 9 |
| 6 compensation capabilities | CONFIRMED (declared) | `states.py:45-52`; but only 4 of 6 are ever assigned — see D7 |
| 9 frontend routes | CONFIRMED | 9 `page.tsx` files under `reversa/apps/web/app` (home, command, connectors, demo-lab, evidence/[id], recovery, roi, settings, workflows/[id]) |
| 20 tests + 1 honest skip | CONFIRMED | 21 committed `test_*` defs across 6 files; `test_vultr_provider_if_configured` skips without a key (`test_ai_eval.py:100-102`). Matches `.agents/verification-matrix.md` |
| Postgres main + 5 isolated SQLite stores | CONFIRMED | `db.py:22-65` — `main` uses `DATABASE_URL` when set, else SQLite; one file per demo store |
| Token auth + tenant isolation + plan-hash approvals | CONFIRMED | `auth.py`, `routes/workflows.py:146-172` (hash match + 30-min TTL), org checks on every owned route |

## 2. Claim mismatches (doc drift, no code fix needed)

- M1 — "16-field action contracts" is wrong. `ActionContract` in
  `connectors/sdk.py:18-32` has 13 fields. A third number (12) appears in
  `.agents/tasks.json` (AGENT-05 mandate). Three sources, three counts;
  the docstring in `sdk.py:1` and `docs/jury/03-architecture.md:20-21`
  should say 13.
- M2 — README "19 passed" is stale. Committed suite is 21 defs / 1 skip
  (i.e. 20 passed when Vultr is unconfigured). The verification matrix is
  the accurate source.
- M3 — ADR-001 says "boucle asyncio in-process". The implementation is a
  synchronous pump (`execute_workflow_sync`, `engine/saga.py:528-540`)
  executed inside the `POST /execute` request handler
  (`routes/workflows.py:175-194`). No background worker, no asyncio loop.
  Either the ADR or a future worker extraction should close this gap.

## 3. Tech debt and complexity risks (ranked)

- D1 — Cancel bypasses the transition allowlist. `cancel_workflow`
  (`routes/workflows.py:207-218`) assigns `action.state = "SKIPPED"`
  directly instead of going through `check_action_transition`, breaking
  the "every state change is allow-listed" invariant the saga module
  advertises (`saga.py:1-6`). Same file also hops `RETRY_SCHEDULED`
  through an unjournaled intermediate. Fix: route through `_transition_act`
  (needs `PENDING -> SKIPPED`, which already exists, and an explicit
  `RETRY_SCHEDULED -> SKIPPED` edge or the legal two-hop with events).
- D2 — Evidence `seq` race under true parallelism. `append_event`
  (`evidence.py:68-103`) computes `max(seq)+1` in a read-then-insert
  without retry; two workers appending for one workflow concurrently can
  collide on the `ix_events_wf_seq` unique index (`models.py:90`) and
  500. The CAS claim logic (`saga.py:76-94`) is race-safe, but the
  journal is not. Low probability today (single in-process worker), but
  it contradicts the multi-worker story. Fix: retry-on-IntegrityError or
  a serialized appender.
- D3 — Blocking sleeps inside the request path. Retry backoff
  (`saga.py:449-460`, up to ~35 s per retry) and chaos latency
  (`saga.py:139-141`, 2 s) run as `time.sleep` inside `POST /execute`.
  A workflow with several retries can exceed proxy/client timeouts while
  holding a server worker. Acceptable for the demo; a real worker needs
  scheduled retries outside the request.
- D4 — Claim journal inconsistency. `claim_action` performs the CAS via a
  raw `UPDATE` (correct for atomicity) but journals `action.claimed`
  instead of an `action.state` PENDING -> CLAIMED event, so the
  `action.state` event stream skips that edge while `states.py` declares
  it. Consumers reconstructing state purely from `action.state` events
  will disagree with the DB. Fix: emit both, or document `action.claimed`
  as the canonical claim record.
- D5 — Dead conditional branch: billing `invoice_issued` is read
  (`services.py:461`) but never written anywhere in src or tests, so the
  "cancel refused once invoiced" guard — the showcase for
  CONDITIONALLY_REVERSIBLE — cannot trigger today. Either wire a setter
  (demo route or chaos fault) or downgrade the doc claim.
- D6 — No migrations (acknowledged in ADR-001, still debt).
  `Base.metadata.create_all` (`db.py:56-65`) means any V2 schema change
  needs a manual prod procedure; the Postgres-vs-SQLite datetime fix
  mentioned in `.agents/progress.md` is exactly the class of bug this
  invites. Alembic (or a documented create_all + backup discipline)
  should land before the first schema change.
- D7 — Two compensation capabilities are unexercised. No connector
  declares `MANUAL_ONLY`; `UNKNOWN` appears only as the DB default
  (`models.py:78`). The `MANUAL_REQUIRED` path is therefore reachable
  only via `IRREVERSIBLE` (notify). The state machine handles all three
  identically (`saga.py:34`, `workflows.py:236`), so risk is low, but
  coverage claims should not imply all six were demonstrated.
- D8 — Credential shopping list (accepted tradeoffs, record explicitly):
  token in `localStorage` (XSS-readable), SSE `?token=` fallback
  (`routes/workflows.py:261-265`, URL-logged), unsalted SHA-256 token
  hashes (fine for random tokens, weak if a low-entropy token is ever
  added via `infrastructure/scripts/add_token.py`). The in-flight
  P1-AUTH-01 change (strict Bearer [REDACTED] length cap, constant-time
  compare) improves this without altering contracts.
- D9 — Dead code: `VultrInferenceProvider._input_keys`
  (`planner/vultr.py:77-79`) always returns `[]` and has no callers.
  Remove or wire it (the prompt at line 42 already inlines the same data
  via `c.get('inputs', [])`).
- D10 — `verify()` dual-use subtlety. The same method proves forward
  effects AND proves compensations (`saga.py:371-380` expects `False`
  after undo). Every demo connector satisfies both directions today, but
  any new connector author must preserve the inverted postcondition —
  worth one paragraph in the connector contract docs, since V2 adds a
  real connector (§4).
- D11 — Frontend has no tests and `lint` is only `tsc --noEmit`
  (`reversa/apps/web/package.json:9`). E2E browser coverage exists at
  repo level (`reversa/tests/e2e/smoke_browser.py`), but component
  regressions have no net. Fine for P0 scope; flag before UI-heavy V2
  work.
- D12 — DemoStore opens a fresh session per operation
  (`services.py:46-48`) and `list_connectors` fans out one full listing
  per store (`routes/connectors.py:14-28`). N+1-shaped but trivially
  small at demo scale; do not "optimize" prematurely — just don't copy
  the pattern into hot paths.

Secrets hygiene (checked, clean): `reversa/infrastructure/.env` exists on
disk but is git-ignored (`.gitignore:9`) and untracked — only
`.env.example` is committed. No secret material is committed. Redaction at
append time plus re-redaction on export (`evidence.py:35-59`,
`routes/evidence.py:45-53`) is correctly layered.

## 4. In-flight V2 work (uncommitted, reviewed for direction only)

- `connectors/github.py` (new, ~400 lines, NOT self-registered — honest
  skeleton): 4 actions (`create_issue`, `add_labels`, `update_issue`,
  `close_issue`), token from env only, no token in errors, client-side
  idempotency marker, explicit "close, never delete" compensation copy.
  Direction is sound and it follows the SDK interface correctly.
- Architectural consequences once wired: connector count becomes 7 and
  action count 14, so every "6 connectors / 10 actions" claim (README,
  arch doc, matrix) needs a refresh, and the planner capability list
  grows (eval-set impact: `tool_precision` denominator changes).
- Watch items for the wiring step: (a) `input_schema` values like
  `"string (owner/name)"` and `"string?"` are free-form strings the
  validator looks up in `TYPE_CHECKS` (`planner/validate.py:12-18`) —
  unknown type names silently skip type checking (line 81: `expected is
  None` passes), so optional/annotated inputs are currently unchecked;
  decide whether that leniency is policy or a validator gap. (b) The
  first-page-only idempotency scan (`github.py:337-350`) and network
  verify-per-call are honest best-effort; they inherit D2/D3 risks at
  higher latency. (c) `verify()` for `create_issue` requires
  `state == "open"`, which conflicts with close-as-compensation
  verification per D10 — the compensation path calls `verify` expecting
  `False` after close, which holds here, but the interaction deserves a
  test.
- `auth.py` P1-AUTH-01 diff (working tree): strict `Bearer` scheme parse,
  512-char cap, hash-once + `compare_digest`. Behavior-preserving for
  legitimate clients; slightly changes the status for malformed schemes
  (now 401 via the empty-token path). No architecture impact.

## 5. Verdict

The committed architecture substantiates its headline claims: the state
machines, connector registry, action inventory, template, evidence chain,
and approval gating are all exactly as documented, with M1–M3 the only
paperwork drift. The engine's core safety properties (CAS claims, lease
recovery, UNKNOWN-first reconciliation, optimistic compensation guards,
hash-chained evidence) are genuinely implemented, not aspirational. The
debt above is the normal residue of a 3-day hackathon build: D1, D2, and
D6 are the three items I would fix before any V2 scale or multi-worker
claim; the rest can ride.
