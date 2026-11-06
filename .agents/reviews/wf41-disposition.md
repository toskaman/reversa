# wf41 disposition — V7 B3 (read-only investigation, 2026-11-06)

## Observed state (prod Postgres + identity store, read-only)

- Workflow 41: RUNNING, org 7 (`guest-678c1de02e60285a`, demo), created and
  last touched 2026-11-05 17:22–17:31 UTC (~9 h stuck, zero writes since).
- Actions: 3 VERIFIED (crm.validate_customer, crm.create_organization,
  identity.create_workspace), 1 UNKNOWN_OUTCOME (id 404,
  identity.provision_users, attempt 1/3, COMPENSATABLE), 6 PENDING dependents.
- Action 404: input users user1/2/3@initech.example + workspace initech-llc,
  output `{}`, no error, lease worker-1 expired 2026-11-05 17:23:19 (stale).
- Last event seq 25: EXECUTING → UNKNOWN_OUTCOME, note "startup: owner
  crashed mid-effect". No reconcile/indeterminate/deferred markers since.
- Chaos rules for org 7: 0 rows (no active fault).
- External store (`identity.db`, read-only): org 7 owns exactly 1 row — the
  `initech-llc` workspace (active). Zero `user` rows → the provision effect
  is ABSENT (crash before the write; empty output corroborates).
- Guest session: record lost at the RC8 container recreate; TTL long passed.
  Expired + forgotten.

## Classification: 4 — manual intervention (leave in place)

A resume through the engine would be safe *and* correct here: stale lease +
UNKNOWN → `_reconcile_unknown` → verify reads store → ABSENT_CONFIRMED →
FAILED + idempotent retry (attempt 1 < 3, idempotency key present). Nothing
would be force-resolved; code paths audited in `saga.py:319-350,943-967`.

But no API principal can trigger it: the guest credential died with the
container, and the owner gets 404 by tenant-isolation design. Raw-SQL deletes
would destroy honest uncertainty evidence for zero user benefit — the rows
are invisible to every API principal (org-scoped listings + `_get_owned`).

## Disposition

- LEAVE IN PLACE. State stays RUNNING/UNKNOWN_OUTCOME as the honest record
  of a crash-mid-effect in an expired demo org. No retry, no delete, no
  compensate, no forced state.
- Honest product gap (post-hackathon, not pre-submission): container restart
  orphans expired guest orgs because the expiry sweep iterates in-memory
  sessions (`auth.py:321-339`). A DB-backed sweep would close it; too risky
  to migrate now for a user-invisible row.
