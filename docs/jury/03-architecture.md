# 03 — Architecture

```text
browser ──HTTPS──> Caddy :443 ──┬──> web:3000 (Next.js standalone, TS strict)
                                 ├──> api:8000 (FastAPI + in-process saga worker)
                                 │         ├─ Postgres 16 (workflows, actions, events, approvals)
                                 │         ├─ 5 SQLite stores (demo-crm/identity/support/billing/notify)
                                 │         └─ Vultr Inference (optional) / deterministic planner
                                 └──> /healthz /readyz probes
```

Key decisions (see `.agents/decisions/ADR-001-stack.md`):

- One VM + Compose over K8s: shippable in 3 days, ~$2 for the event.
- In-process worker with DB leases + startup reconciliation over Redis/Celery:
  fewer moving parts, crash-safe by construction, honestly documented.
- Demo services as isolated-state sub-apps: genuinely distributed state
  (separate files), independently queryable, extractable later.
- Strict contracts everywhere: Pydantic `extra=forbid` plans, allowlisted
  saga transitions (15 workflow / 14 action states), 16-field action
  contracts, typed errors, idempotency keys, optimistic versions.
