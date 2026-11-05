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
`chat/completions` returns 401 with a cloud API key (both `Bearer` and
`api-key` headers tested) — an inference-scoped key is required, which we
don't have. We report this instead of faking AI output: the engine, not the
model, is the authority (invalid plans are rejected with typed errors).

Eval set (30 offline cases: legit, ambiguous, contradictory, impossible,
injection, dangerous; per-category summary in `tests/test_ai_eval.py`)
is implemented and green; full LLM-vs-baseline scoring awaits a working key.
