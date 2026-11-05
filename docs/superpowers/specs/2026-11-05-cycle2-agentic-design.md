# Cycle 2 — Agentic Planning Engine (spec)

Date: 2026-11-05. Scope: ONE cycle. YAGNI: no tool-calling loop, no new
connectors, no new infra. All new plans must use registered capabilities only.

## Problem

`DeterministicPlanner` always emits the onboarding template (with a warning
when the intent does not match). Off-domain, ambiguous, or impossible intents
get a misleading plan instead of clarification or refusal.

## Design (approved direction: V3 §4, AI proposes / deterministic disposes)

1. **Intent gate (deterministic, NEW `planner/intent.py`)**: classify intent as
   `onboarding | offboarding | escalation | ambiguous | offscope` via
   keyword rules + capability match. Pure function, fully unit-tested.
2. **Clarification contract**: `ambiguous` → HTTP 200 with
   `{status: "needs_clarification", questions: [...]}` (max 3 targeted
   questions, generated deterministically from missing slots; LLM-generated
   questions explicitly OUT of scope). No workflow created. Rate-limited
   same as intents.
3. **Refusal contract**: `offscope` → `{status: "refused", code, reason}` reusing
   `REFUSAL_CODES` in `validate.py` (extend list, no new module). No workflow.
4. **New templates (deterministic, real caps only)**: `offboarding` and
   `escalation` builders next to `templates/onboarding.py`, each with:
   steps, deps, preconditions, compensations, approval policy; happy-path +
   chaos e2e reuse.
5. **Vultr prompt update**: system prompt lists the 3 domains + refusal rules;
   provider maps model `clarify`/`refuse` outputs to contracts §2/§3.
   Validation unchanged in authority (validate.py stays the decider).
6. **Provenance (minimal UI)**: intent response + workflow header already carry
   provider/model/latency/warnings; frontend shows them (badge + tooltip).
   Full AI Decision Inspector stays Cycle 4.
7. **Eval**: extend `tests/test_ai_eval.py` matrix 30 → 100 cases covering the
   new contracts; live campaign script with cost guard (max N calls, model
   fixed); comparison report deterministic-vs-vultr in
   `docs/benchmarks/ai-eval-live-RESULTS.md` (append, no rewrite).

## Non-goals

Multi-turn dialogue state, LLM-generated questions, new connectors,
new infra, prompt-chain agents, UI redesign.

## Acceptance

- Ambiguous intent → questions, no workflow, no template leak.
- Off-scope intent → explicit refusal code, no workflow.
- Offboarding/escalation intents → valid executable plans (AI + deterministic).
- 100-case matrix green offline; live campaign run once, results appended.
- Full suite + CI green; RC4 prod untouched until merge + deploy.
