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

Eval set (30 offline cases: legit, ambiguous, contradictory, impossible,
injection, dangerous; per-category summary in `tests/test_ai_eval.py`)
is implemented and green; full live LLM-vs-baseline scoring runs against
RC3 and will be reported with measured numbers only.
