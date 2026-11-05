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
baseline 100% schema-valid, 0% refusal) is green (22 passed, 1 honest
live-gated skip); the capped live LLM-vs-baseline runner
(`REVERSA_EVAL_LIVE=1`, max 25 cases / 60k tokens, anonymized — see
`docs/benchmarks/ai-eval-live-PROTOCOL.md`) has run twice, and only
measured numbers are published — see
`docs/benchmarks/ai-eval-live-RESULTS.md` (n=30 campaign: 29/30
accepted, 87k tokens; Cycle 2 subset: 2×10 cases, 31,975 tokens).

## Cycle 2 — agentic planning (delivered in RC5, 2026-11-05)

Design: `docs/superpowers/specs/2026-11-05-cycle2-agentic-design.md`.
Shipped in `0.2.0-rc.5` (commit `0cecb98`, feature merge `ab0e66b`).
AI proposes, deterministic disposes — `validate.py` stays the authority.
Binding non-goals held: no multi-turn dialogue state, no LLM-generated
questions (all questions deterministic), no new connectors, no new
infra, no prompt-chain agents, no UI redesign.

- **Intent gate (live, `planner/intent.py`):** deterministic
  classifier — `onboarding | offboarding | escalation | ambiguous |
  offscope` — via keyword rules + capability match. Pure function,
  unit-tested (`test_intent_gate.py`, `test_intent_route_wiring.py`).
  Before RC5 there was no gate: the baseline emitted the onboarding
  template with a warning for non-matching intents (measured: 100%
  schema-valid, 0% refusal over the 100-case offline set).
- **Clarification contract (live):** `ambiguous` → HTTP 200
  `{status: "needs_clarification", questions: [...]}` (1–3
  deterministic questions from gate evidence; LLM-generated
  questions out of scope). No workflow created. Rate-limited as
  intents. The older `NEEDS_CLARIFICATION` inside the 422
  `PLAN_REJECTED` path remains for AI-provider sentinel refusals
  (pinned offline in `test_agentic_refusal.py`).
- **Refusal contract (live):** `offscope` → HTTP 200
  `{status: "refused", code, reason}` with codes `OUT_OF_SCOPE` /
  `UNSAFE_REQUEST` / `IMPOSSIBLE_REQUEST` (route contract;
  `REFUSAL_CODES` in `validate.py` additionally carries
  `NEEDS_CLARIFICATION` for the sentinel path). No workflow.
  Note: the n=30 live campaign ran before structured refusal
  existed, so its 0% refusal rate must not be quoted as current
  behavior.
- **New templates (live):** deterministic `offboarding` (3 steps:
  validate → checklist → notify) and `escalation` (7 steps)
  builders beside `templates/onboarding.py`, real registered
  capabilities only, each with steps, deps, preconditions,
  compensations, approval policy.
- **Eval (measured):** the capped Cycle 2 live subset ran 2026-11-05
  (model pinned `deepseek-v4.1-flash-1017`, 2 runs × 10
  adversarial-heavy cases, 15387 + 16588 = 31,975 tokens, no early
  stop): JSON 100%, DAG 100%, raw schema-valid 20% / 10% — every
  invalid row rejected by the deterministic validator after up to
  2 attempts, never executed. Appended to
  `docs/benchmarks/ai-eval-live-RESULTS.md`, never rewritten.
