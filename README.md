# REVERSA — Self-Healing AI Operations Platform

**AI that doesn't just act. It makes things right.**
**Every action accounted for. Every failure handled.**
**Reversible where possible. Accountable everywhere.**

Vultr Agent Rush Hackathon 2026 — Challenge 2: Powering the Future of Work.

## Problem

AI agents can execute business operations across systems. But when an
operation fails halfway through, nobody fixes the mess: half-created
accounts, orphaned resources, inconsistent systems, manual cleanup.

## Solution

REVERSA is an enterprise AI operations platform with a recovery engine:

- **AI Planning** — natural-language intent becomes a strict, validated plan
  over allowlisted capabilities (never arbitrary commands).
- **Verified Execution** — every action runs through authorized connectors and
  its effect is re-checked, not assumed.
- **Typed Compensation** — FULLY / CONDITIONALLY / COMPENSATABLE /
  IRREVERSIBLE / MANUAL_ONLY / UNKNOWN. Unsafe undo is refused, never forced.
- **State Reconciliation** — unknown outcomes are investigated before any
  retry; crashes resume without blind re-execution.
- **Evidence** — every run produces a hash-chained, exportable, offline-
  verifiable Evidence Passport.

Live demo: `https://217.69.3.211.nip.io` (ask the team for a demo token,
or run locally below).

## The 30-second demo

1. Open **Command**, keep the Acme onboarding intent, Generate plan.
2. Review the **Shadow Preview** (effects, risks, approvals), Approve.
3. Execute: 10 real actions across CRM, Identity, Support, Billing, Notify.
4. Open **Demo Lab**, **INJECT FAILURE + RUN**: billing fails, REVERSA blocks
   dependents, compensates 7 actions in reverse order, and reports.
5. Open **Evidence**: hash-chained timeline, JSON/HTML export, CLI verify.

## Architecture

```text
Next.js web ──HTTPS──> Caddy ──┬──> FastAPI + saga worker ──> Postgres (main)
                                │         │  ├─ demo CRM/Identity/Support/Billing/Notify (SQLite, isolated)
                                │         │  └─ Vultr Inference (optional) / deterministic planner
                                └──> Next.js standalone
```

- Backend: Python 3.12, FastAPI, Pydantic v2 (strict), SQLAlchemy 2.
- Frontend: Next.js 15, TypeScript strict, SSE live timeline, custom SVG graph.
- Infra: 1 Vultr VM (vc2-2c-4gb, Paris), Docker Compose, Caddy TLS.
- 19 backend tests + 9 browser E2E checks, all green (see below).

## How REVERSA Uses Vultr

- **Cloud Compute** (`vc2-2c-4gb`, `cdg`): API, worker, web, Postgres, Caddy —
  the entire product runs on the VM. Nothing executes elsewhere.
- **Serverless Inference**: optional `VultrInferenceProvider`
  (OpenAI-compatible). Model list verified live (35 models); chat completions
  currently return 401 with a cloud key, so the deterministic planner is the
  default and Vultr activates when an inference key is configured.
- **Credits**: $200 granted; VM costs ~$0.027/h (~$2 for the event).

## Quickstart (local, no key needed)

```bash
# API
cd reversa/apps/api && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q            # 19 passed
REVERSA_DATA_DIR=data .venv/bin/python -m uvicorn reversa_api.main:app  # :8000
# Web (new shell)
cd reversa/apps/web && npm install && npm run build && npm run start   # :3000
```

Open `http://localhost:3000/settings`, paste the demo token printed by the
API server log, Test connection, then run the 30-second demo above.

Verify an export offline:

```bash
python -m reversa_api.cli verify reversa-evidence-<id>.json
```

## Tests

- Backend: `pytest reversa/apps/api/tests -q` — 19 tests: saga transitions,
  claim races, idempotent double-execute, UNKNOWN reconciliation, chaos
  compensation (order + restored resources), tenant isolation, approvals.
- Browser E2E: `reversa/tests/e2e/smoke_browser.py` — 9 checks in real
  Chromium (plan→approve→execute→COMPLETED, chaos→COMPENSATED, evidence VALID).
- Benchmarks: `reversa/tests/performance/bench.py` (see `docs/benchmarks/`).

## Security & limits (honest)

- Per-org bearer tokens, tenant isolation enforced per query, approvals bound
  to the exact plan hash with 30-min TTL, chaos locked to the demo tenant,
  secrets redacted at event-append time and on export.
- No exactly-once claim on external systems; idempotency keys + verification
  instead. The hash chain detects tampering; it is not absolute immutability
  without an external anchor. Demo connectors are labeled as such.

## Docs for the jury

`docs/jury/` (01 overview → 10 final verification), `docs/architecture/`,
`docs/benchmarks/`, `docs/security/`. Storyboard + LabLab texts included.

## License

MIT. Built originally for this hackathon; no copied code.
