# 05 — AI integration (honest)

The planner pipeline: intent → capability discovery (allowlist) → structured
generation → strict schema validation → policy (AUTO/APPROVAL/FORBIDDEN) →
DAG/cycle check → compensation compatibility → Shadow Preview.

Two providers behind one interface:

- **DeterministicPlanner (default, no key):** template matcher for onboarding.
  Powers the entire demo. No network, no cost, reproducible.
- **VultrInferenceProvider (optional):** OpenAI-compatible chat completions,
  JSON mode, one correction retry with structured errors, timeouts, usage
  metering. Falls back to deterministic with an explicit warning.

Verified live on 2026-11-05: `/v1/models` lists 35 models (public endpoint).
A cloud API key returns 401 on `chat/completions` (both `Bearer` and
`api-key` headers tested) — inference needs its own subscription key.
We retrieved it legitimately via the Cloud API
(`GET /v2/inference/{id}` → `api_key`) and configured prod with
`deepseek-v4.1-flash-1017`: direct `chat/completions` call returned
HTTP 200 in 761 ms with usage metering.

Live prod intents (`POST /api/v1/intents`, guest session, RC2):
Globex-6-users → 201 `provider: vultr-inference`, 10 steps, "accepted
after 2 attempt(s)", 7.7 s wall; one malformed AI draft was honestly
rejected with 422 `PLAN_REJECTED`/`BAD_INPUT_TYPE` and never executed.
The engine, not the model, stays the authority: invalid plans are
rejected with typed errors, and since RC2 nested `users` shapes are
validated both at plan time and in the executor
(`PreconditionFailed`, clean FAILED — no 500).

RC3 hardened live reliability: the model sometimes emitted `"users": 6`
(a headcount, not objects) and `max_tokens: 2000` truncated reasoning
models mid-JSON (measured: ~700–1800 reasoning tokens). The system
prompt now pins the nested `users` shape with an expansion rule, and
the budget is 8000 tokens — verified with 2/2 valid full plans live
before release. The retry loop (invalid → typed errors → corrected
plan) is also pinned offline in `test_ai_eval.py`.

Eval set (100 offline cases: 20 legit, 15 ambiguous, 12 contradictory,
12 impossible, 18 injection, 23 dangerous; `tests/test_ai_eval.py`,
baseline 100% schema-valid, 0% refusal) is green; the capped live
LLM-vs-baseline runner (`REVERSA_EVAL_LIVE=1`, max 25 cases / 60k tokens,
anonymized — see `docs/benchmarks/ai-eval-live-PROTOCOL.md`) measures
only, and only measured numbers are published.

## Cycle 2 — agentic planning (spec'd, not yet measured)

Design: `docs/superpowers/specs/2026-11-05-cycle2-agentic-design.md`.
AI proposes, deterministic disposes — `validate.py` stays the authority.
Binding non-goals: no multi-turn dialogue state, no LLM-generated
questions, no new connectors, no new infra, no prompt-chain agents,
no UI redesign. Nothing below is measured yet: no new numbers are
claimed until the eval campaign re-runs.

- **Intent gate (planned, `planner/intent.py`):** deterministic
  classifier — `onboarding | offboarding | escalation | ambiguous |
  offscope` — via keyword rules + capability match. Pure function,
  fully unit-tested. Today there is no gate: the baseline emits the
  onboarding template with a warning for non-matching intents
  (measured: 100% schema-valid, 0% refusal over the 100-case
  offline set).
- **Clarification contract (planned):** `ambiguous` → HTTP 200
  `{status: "needs_clarification", questions: [...]}` (max 3
  deterministic questions from missing slots; LLM-generated
  questions explicitly out of scope). No workflow created.
  Rate-limited as intents. Today ambiguity surfaces as
  `NEEDS_CLARIFICATION` inside the 422 `PLAN_REJECTED` path (AI
  provider only; pinned offline in `test_agentic_refusal.py`, never
  measured live).
- **Refusal contract (planned):** `offscope` → `{status: "refused",
  code, reason}` reusing `REFUSAL_CODES` in `validate.py` (today:
  `OUT_OF_SCOPE`, `NEEDS_CLARIFICATION`). No workflow. Today
  refusal is the same 422 `PLAN_REJECTED` path with `OUT_OF_SCOPE`
  (offline-pinned; the n=30 live campaign ran before structured
  refusal existed, so its 0% refusal rate must not be quoted as
  current behavior).
- **New templates (planned):** deterministic `offboarding` and
  `escalation` builders beside `templates/onboarding.py`, real
  registered capabilities only, each with steps, deps,
  preconditions, compensations, approval policy. Today only the
  10-step onboarding graph exists.
- **Eval (planned):** the live campaign (n=30 to date) re-runs
  capped (max N calls, fixed model) over the new contracts, and the
  deterministic-vs-Vultr comparison is appended to
  `docs/benchmarks/ai-eval-live-RESULTS.md` — never rewritten.
  Until then the only live AI numbers are the n=30 campaign above.
