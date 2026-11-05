# AGENT-02 — AI / inference state audit (cycle V2-04, FINAL ASCENT)

- identity: AGENT-02, AI Auditor, REVERSA V2 cycle 4
- date (UTC): 2026-11-05
- repo root: D:/Hackatons/Vultr
- mandate: audit REAL inference state — providers configured, Vultr models
  endpoint (public GET only), whether any legitimate inference credential
  exists in env (names only, never values), mode honesty in UI/API.
  No key guessing, no brute force. No commits, no push, no prod touch
  (localhost probes only).

## Verdict (one line)

No legitimate inference credential exists anywhere audited (process env
empty, `reversa/infrastructure/.env` key+model both present-but-empty);
the only live path is the deterministic planner, and the API/UI label it
honestly everywhere the planner result is shown.

## Files read (before citing)

API / planner:

- `reversa/apps/api/src/reversa_api/config.py` — env wiring
- `reversa/apps/api/src/reversa_api/planner/__init__.py` — orchestration
- `reversa/apps/api/src/reversa_api/planner/base.py` — interface
- `reversa/apps/api/src/reversa_api/planner/vultr.py` — Vultr provider
- `reversa/apps/api/src/reversa_api/planner/deterministic.py` — baseline
- `reversa/apps/api/src/reversa_api/routes/workflows.py` — intent endpoint
- `reversa/apps/api/src/reversa_api/routes/health.py` — health endpoints
- `reversa/apps/api/src/reversa_api/schemas.py` — `IntentIn.use_ai`
- `reversa/apps/api/src/reversa_api/main.py` — app wiring
- `reversa/apps/api/tests/conftest.py` — test auth/DB fixtures
- `reversa/apps/api/tests/test_ai_eval.py` — 30-case eval + offline fakes
- `reversa/apps/api/tests/test_planner_evidence.py` — planner/evidence units
- `reversa/infrastructure/docker-compose.yml` — prod env wiring

UI:

- `reversa/apps/web/app/command/page.tsx` — planner toggle + provider display
- `reversa/apps/web/components/Recovery/DecisionInspector.tsx` — provenance
- `reversa/apps/web/app/page.tsx`, `layout.tsx`, `demo-lab/page.tsx`,
  `settings/page.tsx`, `components/Nav.tsx`, `components/JuryLaunch.tsx`
  (via targeted search)

Docs / prior cycles:

- `docs/jury/05-ai-integration.md` (full read)
- `docs/benchmarks/results.md`, `docs/jury/01-project-overview.md`,
  `docs/jury/lablab-submission.md`, `docs/jury/v2-clips/shot-log.md`,
  `docs/jury/v2-clips/s2-plan.json` (via targeted search hits)
- `.agents/cycles/cycle-V2-03/agent-*.md` (search hits only, auth context)
- `.env` files: variable NAMES extracted only, values never read or printed:
  `reversa/infrastructure/.env`, `reversa/infrastructure/.env.example`

## Files modified

- `.agents/cycles/cycle-V2-04/agent-02-ai-state.md` (this file) — created.
- No other file created, edited, or deleted. No commit. No push.

## Commands run (all read-only except the report above)

1. `Get-ChildItem` listings of repo root, `reversa/apps/*`,
   `.agents/cycles/*` (one listing accidentally recursed into
   `reversa/apps/api/.venv`; terminated, no writes).
2. Env presence check (names + SET/EMPTY boolean only, values never
   printed): `VULTR_INFERENCE_API_KEY`, `VULTR_INFERENCE_MODEL`,
   `VULTR_INFERENCE_BASE_URL`, `VULTR_API_KEY`, `OPENAI_API_KEY`,
   `ANTHROPIC_API_KEY`, `REVERSA_*`, `DATABASE_URL`; plus all env names
   matching `KEY|TOKEN|SECRET|PASSWORD`.
3. `git status --short`, `git log --oneline -8`, `git diff --stat`,
   `git diff` (hunk headers) and `git ls-files | Select-String '\.env'`.
4. `.env` / `.env.example` variable-NAME extraction (keys left of `=`
   only; values never printed, stored, or committed).
5. Public, unauthenticated `GET https://api.vultrinference.com/v1/models`
   via the API `.venv` python + httpx (mandated public-GET check; no key
   sent, no Chat Completions call made).
6. In-process boolean comparison (no value output): dotenv
   `VULTR_INFERENCE_API_KEY` / `VULTR_INFERENCE_MODEL` empty-or-not and
   placeholder-like-or-not vs the 35 public model IDs.
7. Localhost probes: `GET http://localhost:8000/health`,
   `GET http://localhost:3000/`.
8. Live mode-honesty probe: throwaway `TestClient` run with a temp
   `REVERSA_DATA_DIR` (deleted afterwards), fresh demo org + token,
   `POST /api/v1/intents` with `use_ai=true`, `use_ai` omitted, and
   `use_ai=false`; recorded HTTP status, `provider`, `warnings`, and the
   `workflow.created` event payload.
9. `.\.venv\Scripts\python.exe -m pytest tests/test_ai_eval.py
   tests/test_planner_evidence.py -q`.

## Observed results

### 1. Providers configured (code truth)

- Exactly two planner providers exist; a repo search for
  `openai|anthropic|cohere|mistral|ollama|groq|together` under
  `reversa/apps/api/src` returns zero hits.
- `DeterministicPlanner` (`planner/deterministic.py`, name
  `"deterministic"`): template matcher, no network, no key.
- `VultrInferenceProvider` (`planner/vultr.py`, name
  `"vultr-inference"`): OpenAI-compatible `POST {base}/chat/completions`,
  JSON mode, one correction retry, 30 s timeout, full metering contract
  (`latency_ms`, token usage, attempts, requested-vs-returned model,
  substitution flag). Constructor refuses to run without key+model
  (`PlanError: vultr inference not configured (need key + model)`).
- Orchestration (`planner/__init__.py:28-47`): Vultr is attempted only
  when `use_ai` is true AND both `settings.vultr_api_key` and
  `settings.vultr_model` are non-empty. Any `PlanError` degrades to
  deterministic with an explicit warning; `use_ai` without config yields
  `"vultr inference not configured; deterministic planner used"`.
- Effective live state: **deterministic only**. No key+model pair is
  configured in any reachable env (see §2), so the Vultr branch is
  unreachable at runtime.

### 2. Inference credentials (names only, never values)

- Process environment: `VULTR_INFERENCE_API_KEY=EMPTY_OR_UNSET`,
  `VULTR_INFERENCE_MODEL=EMPTY_OR_UNSET`,
  `VULTR_INFERENCE_BASE_URL=EMPTY_OR_UNSET`, `VULTR_API_KEY`,
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` all `EMPTY_OR_UNSET`. Zero env
  names match `KEY|TOKEN|SECRET|PASSWORD`.
- `reversa/infrastructure/.env` (untracked, gitignored — correct):
  4 variable names: `DOMAIN`, `POSTGRES_PASSWORD`,
  `VULTR_INFERENCE_API_KEY`, `VULTR_INFERENCE_MODEL`.
  Boolean check: `VULTR_INFERENCE_API_KEY` present=True, nonempty=False;
  `VULTR_INFERENCE_MODEL` present=True, nonempty=False.
  `MODEL_IN_PUBLIC_LIST=False` (empty string matches nothing).
- `reversa/infrastructure/.env.example` (tracked): same 4 names, no
  values committed.
- `git ls-files` confirms only `.env.example` is tracked; the real
  `.env` is covered by `.gitignore` (`*.db`, `.env` entries verified).
- Conclusion: **no legitimate inference credential exists** in process
  env or in the repo's env files. Nothing was read beyond presence /
  empty / placeholder-like booleans; no value was printed, stored, or
  committed.

### 3. Vultr models endpoint (public GET only, no auth sent)

- `GET https://api.vultrinference.com/v1/models` → **HTTP 200**,
  `application/json`, 68,832 bytes, `{"data": [...]}` with **35 models**.
- Matches the prior verified claim in `docs/jury/05-ai-integration.md:15`
  ("`/v1/models` lists 35 models (public endpoint)").
- That doc also records (lines 16-18): `chat/completions` returns 401
  with a cloud API key (both `Bearer` and `api-key` headers tested) —
  an inference-scoped key is required, which the project does not have.
  This audit did NOT re-test `chat/completions` (no credential exists to
  test with, and key probing is out of mandate); the 401 statement is
  cited from the read doc, not re-verified.
- Default base URL in code (`config.py:19-21`):
  `https://api.vultrinference.com/v1` — consistent with the probed host.

### 4. Mode honesty in the API (live probe, temp localhost stack)

`POST /api/v1/intents` with no inference credential configured:

| request | HTTP | provider | warnings |
|---|---|---|---|
| `use_ai=true` | 201 | `deterministic` | `vultr inference not configured; deterministic planner used` |
| `use_ai` omitted (schema default is `True`, `schemas.py:28`) | 201 | `deterministic` | same explicit warning |
| `use_ai=false` | 201 | `deterministic` | none (correct — AI not requested) |

- The `workflow.created` event payload records the identical literal
  values (`provider: deterministic`, `model: ""`, `latency_ms: 0`,
  `usage: {}`, plus the warning when applicable) — provenance is
  inspectable, not cosmetic.
- Response contract (`routes/workflows.py:120-122`) always returns the
  real `provider` + `warnings` — there is no code path that reports an
  AI provider while running deterministic.
- Localhost stack observed up during the audit: `:8000/health` → 200
  (43 bytes), `:3000/` → 200. No prod host touched (no SSH, no prod
  URL probed).

### 5. Mode honesty in the UI (source-read)

- Honest (planner surfaces):
  - `app/command/page.tsx:73-75`: checkbox reads "Try Vultr inference
    (falls back to deterministic planner)"; result panel prints
    `provider: {provider}` verbatim plus every warning (`:82-84`).
  - `DecisionInspector.tsx:12-16,56-63`: renders provider/model/latency/
    usage strictly from the `workflow.created` payload or "not recorded".
  - `demo-lab/page.tsx:59` and `JuryLaunch.tsx:114` hard-code
    `use_ai: false` — the jury path never implies live AI.
  - Captured jury clips (`docs/jury/v2-clips/s2-plan.json:11`,
    `s6-evidence-*.json`, `shot-log.md:15`) all record
    `"provider": "deterministic"` — shipped evidence matches reality.
- Aspirational-but-unqualified (flagged, not blocking):
  - `app/layout.tsx:6-7`: title "REVERSA — Self-Healing AI Operations",
    description "AI that doesn't just act. It makes things right."
  - `app/page.tsx:28`: same "AI that doesn't just act…" tagline.
  - `reversa_api/main.py:40-41`: API description
    "Self-Healing AI Operations Platform".
  - Submission copy (`lablab-submission.md:39-40`) says "AI planning
    ships with a deterministic baseline and an optional Vultr Inference
    provider" — accurate. The taglines above never claim live inference
    for a specific run, and every run-scoped surface reports the true
    provider; still, a jury member skimming only the tagline could infer
    more AI than is currently wired. Suggested one-line softening is
    left to the demo-copy owner (out of this mandate).

### 6. Working-tree note (not my change, do not attribute to base)

- Committed base: `f2a6152 CHANGELOG: V2-03 entry (204 verified)`.
- The tree was already dirty when audited and got dirtier during the
  audit (sibling V2-04 agents active): modified
  `auth.py`, `engine/saga.py`, `routes/recovery.py`,
  `routes/workflows.py`, `tests/test_engine_units.py`, `globals.css`,
  `layout.tsx`, `recovery-race/page.tsx`, `time-machine/page.tsx`,
  `RaceComparison.tsx → ExecutionComparison.tsx` rename; untracked
  `.agents/cycles/cycle-V2-04/`, `test_crash_recovery.py`,
  `ManifestPanel.tsx`.
- Relevance check: the sibling `workflows.py` diff touches imports /
  cancel / events / SSE-ticket hunks only — NOT the intent endpoint
  (lines 77-122) or the provider response. Core audit files
  (`config.py`, `planner/*`, `schemas.py`, `main.py`, `health.py`,
  `test_ai_eval.py`, `test_planner_evidence.py`) are byte-identical to
  the committed base. Conclusion: the "committed base is clean (V2-03
  merged)" premise holds for every file this audit depends on; the dirt
  is sibling V2-04 work in flight, untouched by me.

## Tests

- `pytest tests/test_ai_eval.py tests/test_planner_evidence.py -q`
  (via `reversa/apps/api/.venv`): **16 passed, 1 skipped in 0.32 s**.
- The single skip is `test_vultr_provider_if_configured` →
  "vultr inference not configured (honest skip)" — the suite itself
  corroborates §2 (no key present).
- The remaining 16 cover: 30-case eval shape, deterministic baseline
  measurement (100% schema/DAG valid, 0% refusal — documented
  limitation), 3 offline behavioral fakes (refusal/echo/flaky), 6
  offline Vultr metering/substitution tests (scripted HTTP, no network),
  planner validation (10 steps, approval required), evidence chain +
  tamper, redaction, HTML XSS escaping.
- Full-suite run was out of mandate (touched-area only); sibling test
  files were being edited concurrently, so a whole-repo count would not
  be attributable to this audit.

## Issues

1. (INFO, expected) No inference credential anywhere — Vultr path
   unreachable; demo runs 100% deterministic. Consistent with
   `docs/benchmarks/results.md:31` ("no inference key; deterministic
   used") and the V2-03 "204 green" claim, which never required live AI.
2. (MINOR, copy) Unqualified "AI" taglines in `layout.tsx`, `page.tsx`,
   and `main.py` (see §5). No run-scoped surface mislabels; jury clips
   are honest. Recommend a copy-owner decision, not an audit fix.
3. (NOTE) `IntentIn.use_ai` defaults to `True` (`schemas.py:28`).
   Harmless today (falls back with an explicit warning, verified live),
   but if a key is ever half-configured (key without model or vice
   versa), requests silently take the fallback path — by design, and
   loudly warned. No change proposed.

## Risks

- R1 — Secret hygiene if a key arrives: compose already wires
  `VULTR_INFERENCE_API_KEY: ${VULTR_INFERENCE_API_KEY:-}` with an empty
  default (safe); ensure any real key lands only in the gitignored
  `.env`, never in `.env.example`, docs, clips, or chat logs.
- R2 — Half-configuration: key XOR model set → silent deterministic
  fallback (with warning). Acceptable; the warning + `provider` field
  make it visible.
- R3 — Model drift: the empty dotenv model matches none of the 35
  public IDs (trivially). When a model is chosen, it must be validated
  against the live `/v1/models` list — several public IDs are
  non-obvious (`auk`, `clef`, `d3`, …); the provider already detects and
  warns on server-side substitution.
- R4 — Concurrent-edit contamination: sibling V2-04 edits landed
  mid-audit; I verified none touch the audited intent/planner path, but
  a final re-run of the AI-area suite at merge time is cheap insurance.

## Confidence

- HIGH that no legitimate inference credential exists (process env +
  dotenv booleans, suite's honest skip, live fallback warnings — three
  independent signals, zero values handled).
- HIGH that `/v1/models` is public and lists 35 models (live 200,
  re-confirmed today; matches the 2026-11-05 doc claim).
- HIGH that mode reporting is honest (live `provider`/`warnings` +
  event payload observed on a throwaway stack; UI renders verbatim API
  values; jury clips corroborate).
- MEDIUM on the historical `chat/completions` 401 claim (cited from
  `docs/jury/05-ai-integration.md:16-18`, not re-probed — correctly so,
  since no credential exists and probing is out of mandate).
- No result in this file is invented: every claim cites a file read or
  a command observed in this session.

## Next task (suggested, not started)

- If FINAL ASCENT wants live AI: obtain an inference-scoped Vultr key,
  set `VULTR_INFERENCE_API_KEY` + `VULTR_INFERENCE_MODEL` (model ID from
  the §3 public list) in the gitignored `reversa/infrastructure/.env`
  only, then re-run `test_ai_eval.py` (the live test will un-skip) and
  re-capture one jury clip showing `provider: vultr-inference`.
- Regardless: have the demo-copy owner accept or soften the two "AI"
  taglines (§5/Issue 2) before jury lock.
