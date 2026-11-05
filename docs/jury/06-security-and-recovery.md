# 06 — Security and recovery

**Threat model (top controls, all implemented):** per-org bearer tokens with
DB-stored hashes; tenant check on every query (cross-tenant reads 404);
plan approvals bound to the exact plan hash + 30-min TTL (stale/wrong hash
409); chaos locked to the demo org + env flag; no model-generated shell or
URLs — allowlisted capabilities only; secrets redacted at event-append and
on export; bounded retries with backoff+jitter; timeouts; CORS allowlist.

**Recovery semantics:**

- Failures are explicit states, never silent. Dependents block.
- Compensation runs in reverse completion order per action, each verified
  (forward effect re-checked absent; read-only steps are provable noops).
- State-equivalence preconditions: our own earlier compensations may advance
  versions; genuinely incompatible external changes refuse → MANUAL_REQUIRED.
- IRREVERSIBLE / MANUAL_ONLY / UNKNOWN capabilities are never auto-undone;
  they surface as manual items with reasons.
- PARTIALLY_COMPENSATED (compensation failed after retries) vs
  MANUAL_REQUIRED (human needed) vs COMPENSATED are distinct terminal states.

**Refused by design (code-enforced):** real payments (`no_real_payment`
precondition), canceling a mid-flight compensation. Mass sends and
third-party accounts are refused by connector policy (no such capability is
registered), but no dedicated bulk-send guard exists in code yet.
