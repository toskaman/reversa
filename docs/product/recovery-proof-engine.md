# Recovery Proof Engine — Product Spec (REVERSA V2, cycle 1)

- Status: v1 SHIPPED (cycle V2-02, AGENT-04): GET /api/v1/workflows/{id}/recovery-manifest
  (`routes/recovery.py`, 10 tests in `tests/test_recovery_manifest.py`), confidence levels
  VERIFIED / VERIFIED_WITH_COMPENSATION / PARTIAL / INDETERMINATE / MANUAL_REQUIRED
  with C0–C7 criteria; codes R4_NOT_TERMINAL / R5_CANCELLED_RUN.
- Scope: defines what "recovered" means, what evidence proves it, and when the
  engine must refuse to claim recovery.
- Non-goals: no new states, no API changes, no UI changes in this cycle.
  Implementers map this spec onto the existing engine; any mapping gap is a
  spec bug, not an engine bug, until reviewed.
- Status (cycle 3, AGENT-04): sections 4.4–6 restored (the V2-02 file copy was
  truncated mid-4.3); refusal codes and capability codes aligned with shipped
  `routes/recovery.py`; §3.4 example code corrected to shipped
  `R_EXTERNAL_MODIFICATION`.

## 0. Grounding (read, not assumed)

This spec builds strictly on behavior that exists in the repo today:

- `reversa/apps/api/src/reversa_api/engine/states.py` — 15 workflow states,
  14 action states, allowlisted `WF_TRANSITIONS` / `ACT_TRANSITIONS`, 6
  compensation capabilities (`FULLY_REVERSIBLE`, `CONDITIONALLY_REVERSIBLE`,
  `COMPENSATABLE`, `IRREVERSIBLE`, `MANUAL_ONLY`, `UNKNOWN`).
- `reversa/apps/api/src/reversa_api/engine/saga.py` — forward pump, reverse-order
  compensation pump (`seq` descending), verify-after-compensate (forward effect
  must be absent), read-only noop path, 3 bounded compensation attempts,
  terminal distinction `COMPENSATED` vs `PARTIALLY_COMPENSATED` vs
  `MANUAL_REQUIRED`; `UNKNOWN_OUTCOME` reconciliation before any re-execution;
  startup reconciliation that never blindly retries.
- `reversa/apps/api/src/reversa_api/evidence.py` — append-only SHA-256
  hash-chained timeline (`GENESIS` head, canonical JSON), `verify_chain`
  returning `(ok, bad_seq, message)`; secrets redacted at append.
- `reversa/apps/api/src/reversa_api/models.py` — `ActionRun` fields the manifest
  reads (`state`, `input_json`, `output_json`, `attempt`, `max_attempts`,
  `compensation_capability`, `error`, `_comp_attempts`, `_comp_proof`).
- `reversa/apps/api/src/reversa_api/connectors/sdk.py` — typed errors
  (`ConnectorError` with `retryable`/`uncertain`, `PreconditionFailed`,
  `ChaosTriggered`); generic preconditions (`input_has:*`, `tenant_is_demo`,
  `no_real_payment`).
- `docs/jury/06-security-and-recovery.md` — recovery semantics prose:
  explicit failures, dependents blocked, state-equivalence preconditions,
  refused-by-design list (real payments, mass sends, third-party accounts,
  canceling mid-flight compensation).
- `reversa/apps/api/tests/test_chaos.py` — billing-500 run ends `COMPENSATED`
  with reverse-order proof (`[8,7,5,4,3,2,1]`), resources verified restored;
  version-conflict test asserting `PreconditionFailed` on stale
  `expected_version`.

No test or deployment results are claimed in this spec beyond citing the above
sources. All examples below are illustrative inputs/outputs for implementers,
not measured runs.

## 1. Problem statement

Today the engine reaches a terminal workflow state (`COMPENSATED`,
`PARTIALLY_COMPENSATED`, `MANUAL_REQUIRED`, `COMPLETED`, `FAILED`) and the
evidence chain records how it got there. What is missing is a single,
machine-checkable answer to the question a buyer, auditor, or on-call engineer
asks after an incident:

> "Is the world back to normal — and how do you know?"

Raw terminal states do not answer this. `COMPENSATED` means every queued
compensation ran and verified, but it does not distinguish "nothing ever broke"
from "seven effects were undone and re-checked". `MANUAL_REQUIRED` does not say
whether the remaining work is fully enumerated. And no state today says "we
cannot tell what happened" as a first-class, honest verdict instead of a
silent gap.

The Recovery Proof Engine (RPE) is a read-only evaluator over durable state +
evidence. It never mutates workflows, never retries, never compensates. It
computes one **Recovery Manifest** per workflow: per-action verdicts plus one
workflow-level **Recovery Confidence**.

## 2. Tri-state semantics (normative)

### 2.1 The core rule

Every claim the RPE makes about a side effect MUST resolve to exactly one of
three values. There is no fourth value, no `null`, no omitted field, no
"assumed absent":

| Value | Meaning | Burden of proof |
|---|---|---|
| `PRESENT` | The effect exists in the target system now. | A successful `verify()` returning true, recorded in evidence, after the last mutation attempt on that effect. |
| `ABSENT` | The effect does not exist in the target system now. | A successful `verify()` returning false (for presence checks), or a store-level absence proof (e.g. row gone), recorded in evidence, after the last mutation attempt on that effect. |
| `UNKNOWN` | We cannot say whether the effect exists. | Default. Any verify error, timeout, crash mid-effect, unverifiable capability, or missing verification record resolves here. |

Rationale: distributed effects are not boolean. A crashed worker, a timed-out
verify call, or a connector that cannot re-check an effect leaves genuine
uncertainty. Collapsing that uncertainty into "probably fine" is how
automation silently corrupts customer data. The tri-state forces the engine to
either prove its claim or confess ignorance.

### 2.2 Two tri-states, not one

The RPE tracks two independent tri-states per action:

1. **Forward-effect state** — does the action's intended effect exist now?
   Values: `PRESENT` / `ABSENT` / `UNKNOWN`.
2. **Recovery verdict** — given what the run needed, is this action resolved?
   Values: `RESTORED` / `NOT_RESTORED` / `INDETERMINATE`.

The verdict is derived from the effect state plus what the run required:

| Run needed | Effect state | Verdict | Notes |
|---|---|---|---|
| Forward success (no compensation) | `PRESENT` | `RESTORED` | "Restored" here means "in its required end state"; see §4 `VERIFIED`. |
| Forward success (no compensation) | `ABSENT` | `NOT_RESTORED` | Effect lost after success; data-loss signal. |
| Forward success (no compensation) | `UNKNOWN` | `INDETERMINATE` | Verify never conclusively passed. |
| Compensation (effect must be gone) | `ABSENT` | `RESTORED` | Standard compensated case. |
| Compensation (effect must be gone) | `PRESENT` | `NOT_RESTORED` | Compensation did not take; engine must already have recorded `COMPENSATION_FAILED` / `COMPENSATION_NOT_CONFIRMED`. |
| Compensation (effect must be gone) | `UNKNOWN` | `INDETERMINATE` | Compensation ran but confirmation failed (verify error during the absence check). |
| No effect required (`SKIPPED` dependents, noop read-only) | `ABSENT` | `RESTORED` | Provable noop: read-only steps with `noop` proof, or never-executed dependents. |
| No effect required | `PRESENT` | `NOT_RESTORED` | Must not happen; indicates a skipped action that still took effect. Escalate as engine bug. |
| No effect required | `UNKNOWN` | `INDETERMINATE` | E.g. dependent skipped while its dependency's outcome was still `UNKNOWN`. |

### 2.3 Derivation rules (engine-state mapping)

The RPE derives the required inputs from existing states only:

- "Run needed compensation" ⟺ workflow entered `COMPENSATING` (evidence event
  `compensation.started` exists) OR any action left `COMPENSATION_PENDING`.
- Per-action "run needed":
  - `COMPENSATED` → compensation was needed; effect MUST now be `ABSENT`
    (or the action carries a `noop` proof for read-only steps, which counts as
    `ABSENT`-equivalent — see §2.4).
  - `VERIFIED` in a compensated run with a manual capability (`IRREVERSIBLE` /
    `MANUAL_ONLY` / `UNKNOWN`) → compensation was needed but refused; effect
    is `PRESENT` (it was verified and never undone) → `NOT_RESTORED` with a
    manual item (§3.4).
  - `COMPENSATION_FAILED` → compensation needed; effect state re-read from the
    last verify record: `PRESENT` if the absence check returned still-present,
    `UNKNOWN` if the absence check itself errored.
  - `VERIFIED` in a non-compensated run → forward success needed; effect
    `PRESENT` by the verify record that produced `VERIFIED`.
  - `SKIPPED` → no effect required; `ABSENT` unless evidence shows an effect
    (engine-bug path).
  - `FAILED` (terminal, workflow `FAILED` — compensation never started, e.g.
    validation failures) → forward effect `ABSENT` (never confirmed) → verdict
    `RESTORED` **only if** no effect was ever observed; if the failure record
    shows a partial effect, `INDETERMINATE`.
  - Any action in a non-terminal workflow state, or workflow not terminal →
    RPE MUST refuse to emit a manifest (see §5, refusal R4).
- The RPE MUST NOT infer effect state from action state alone when a verify
  record is missing: no verify record ⟹ `UNKNOWN`. State says what the engine
  did; only a verify record says what the world contains.

### 2.4 Noop equivalence

Read-only steps return a `noop` compensation proof (`saga.py`
`_compensate_one`) and transition directly to `COMPENSATED`. The manifest
records these as `effect_state: "ABSENT"`, `absence_method: "noop_proof"`,
with the proof reference. A noop proof is a positive claim ("this step is
read-only and took no effect"), not the absence of a claim.

### 2.5 State-equivalence preconditions

Per `docs/jury/06-security-and-recovery.md`, the engine's own earlier
compensations may advance resource versions; only genuinely incompatible
external changes refuse compensation. The RPE therefore distinguishes two
refusal causes in the manifest (§3.4 `cause`):

- `external_modification` — version advanced by another actor; auto-undo
  refused to avoid destroying чужой work (see §6 scenario).
- `capability_refusal` — action was never auto-reversible (`IRREVERSIBLE` /
  `MANUAL_ONLY` / `UNKNOWN`) regardless of versions.

## 3. Recovery Manifest schema (normative)

### 3.1 Envelope

JSON object, `application/json`, UTF-8. Field order insignificant; producers
MUST emit keys sorted for stable hashing. All fields REQUIRED unless marked
optional. Unknown fields MUST be ignored by readers (forward compatibility),
but the manifest hash covers only the declared fields (§3.5).

```json
{
  "manifest_version": "1.0",
  "workflow_id": 42,
  "org_id": 7,
  "generated_at": "2026-11-05T12:00:00Z",
  "generator": "reversa-rpe/1.0",
  "recovery_confidence": "VERIFIED_WITH_COMPENSATION",
  "chain": {
    "valid": true,
    "events": 73,
    "head_hash": "9f2c…",
    "detail": "chain valid (73 events)"
  },
  "summary": {
    "actions_total": 10,
    "restored": 9,
    "not_restored": 0,
    "indeterminate": 0,
    "compensations_run": 7,
    "manual_items": 1,
    "refusals": 1
  },
  "actions": [ { "…per-action entry…" } ],
  "manual_items": [ { "…manual item…" } ],
  "refusals": [ { "…refusal record…" } ]
}
```

Field notes:

- `generated_at` — RFC 3339 UTC. The manifest is a point-in-time evaluation;
  re-running the RPE later (e.g. after manual work completes) produces a new
  manifest; manifests are never mutated.
- `generator` — `name/version` of the evaluator build, for audit.
- `recovery_confidence` — one of the five levels in §4.
- `chain` — verbatim result of the existing `verify_chain` over the
  workflow's evidence timeline, plus the head hash. If the chain is invalid,
  confidence is capped (see §4.6).

### 3.2 Per-action entry

```json
{
  "seq": 3,
  "action_type": "identity.create_user",
  "connector_id": "demo-identity",
  "action_state": "COMPENSATED",
  "required": "compensation",
  "effect_state": "ABSENT",
  "verdict": "RESTORED",
  "compensation": {
    "capability": "FULLY_REVERSIBLE",
    "attempts": 1,
    "proof_ref": "event seq 61",
    "absence_method": "verify_absent"
  },
  "verification": {
    "method": "connector_verify",
    "event_ref": "event seq 60",
    "observed_at": "2026-11-05T11:59:41Z"
  },
  "forward_attempts": 1
}
```

Enumerations:

- `required`: `forward_success` | `compensation` | `none`.
- `effect_state`: `PRESENT` | `ABSENT` | `UNKNOWN`.
- `verdict`: `RESTORED` | `NOT_RESTORED` | `INDETERMINATE`, derived per the
  §2.2 truth table; any entry violating the table invalidates the manifest.
- `compensation.absence_method`: `verify_absent` | `noop_proof` |
  `not_applicable`. `not_applicable` only when `required != "compensation"`.
- `verification.method`: `connector_verify` | `noop_proof` | `none`.
  `none` ⟹ `effect_state` MUST be `UNKNOWN`.
- `verification.event_ref`, `compensation.proof_ref`: pointers into the
  workflow's evidence timeline (`event seq N`). They MUST resolve to real
  events or the manifest is invalid.
- `compensation` object is REQUIRED when `required == "compensation"`,
  optional otherwise. `attempts` counts compensation attempts
  (`_comp_attempts` + 1 for the successful run, i.e. total tries).
- `forward_attempts` mirrors `ActionRun.attempt` for context.

### 3.3 Minimal entry shapes (other cases)

Skipped dependent (no effect required):

```json
{
  "seq": 9,
  "action_type": "notify.send",
  "connector_id": "demo-notify",
  "action_state": "SKIPPED",
  "required": "none",
  "effect_state": "ABSENT",
  "verdict": "RESTORED",
  "verification": { "method": "none", "event_ref": "event seq 55", "observed_at": "2026-11-05T11:59:40Z" }
}
```

Note: `SKIPPED` entries use `verification.method: "none"` with an
`event_ref` pointing at the skip event (`action.state` → `SKIPPED`), which is
the positive record that no effect was taken. This is the sole exception to
"`none` ⟹ `UNKNOWN`", allowed only when `required == "none"` and
`action_state == "SKIPPED"`.

Failed compensation, effect still present:

```json
{
  "seq": 2,
  "action_type": "crm.create_org",
  "connector_id": "demo-crm",
  "action_state": "COMPENSATION_FAILED",
  "required": "compensation",
  "effect_state": "PRESENT",
  "verdict": "NOT_RESTORED",
  "compensation": { "capability": "COMPENSATABLE", "attempts": 3, "proof_ref": "event seq 70", "absence_method": "verify_absent" },
  "verification": { "method": "connector_verify", "event_ref": "event seq 70", "observed_at": "…" },
  "forward_attempts": 1
}
```

### 3.4 Manual items and refusals

`manual_items[]` — one per action a human must still handle:

```json
{
  "seq": 6,
  "action_type": "billing.create_profile",
  "connector_id": "demo-billing",
  "capability": "MANUAL_ONLY",
  "cause": "capability_refusal",
  "effect_state": "PRESENT",
  "reason": "billing profile is MANUAL_ONLY: auto-undo refused; cancel or credit manually",
  "suggested_action": "Void profile billing/acme-01 in the billing console, then re-run evaluation.",
  "event_ref": "event seq 58"
}
```

- `cause`: `capability_refusal` | `external_modification` |
  `compensation_exhausted` | `verification_inconclusive`.
- `suggested_action` is advisory text; it MUST NOT contain secrets or
  credentials (redaction rules from `evidence.py` apply to manifest text).

`refusals[]` — one per intelligent refusal (§5/§6), including refusals that
did not create manual items (e.g. whole-manifest refusal):

```json
{
  "code": "R_EXTERNAL_MODIFICATION",
  "seq": 4,
  "reason": "crm org version advanced by external actor (v3→v5); auto-undo refused",
  "event_ref": "event seq 64"
}
```

### 3.5 Manifest integrity

- The manifest MUST embed the evidence `head_hash` it was evaluated against.
  If the workflow's chain grows afterwards (manual follow-ups, re-evaluation),
  the old manifest stays valid history; it does not update.
- Readers MUST check: (a) chain head matches the workflow's chain at that
  height, (b) every `event_ref`/`proof_ref` resolves, (c) every verdict obeys
  the §2.2 truth table, (d) `summary` counts match the arrays. Any failure ⟹
  treat the manifest as `INDETERMINATE` regardless of its stated confidence.
- The manifest itself is not (in V2) hash-chained; it is derived data. If V2
  later seals manifests into the timeline, that changes only provenance, not
  these semantics.

## 4. Recovery Confidence levels (normative)

### 4.1 Level definitions

| Level | One-line meaning | Terminal workflow states that can carry it |
|---|---|---|
| `VERIFIED` | Nothing broke; every required effect is proven in place. | `COMPLETED` only |
| `VERIFIED_WITH_COMPENSATION` | Something broke; every completed effect was undone and proven gone; nothing left for humans. | `COMPENSATED` only |
| `PARTIAL` | The world is half-healed: some effects restored, at least one auto-compensation exhausted without human-blocked items pending. | `PARTIALLY_COMPENSATED` only |
| `INDETERMINATE` | We cannot say what the world contains. | Any terminal state (caps all others) |
| `MANUAL_REQUIRED` | We know exactly what remains, and a human must do it. | `MANUAL_REQUIRED` (and any terminal state with unenumerated-manual-item bugs — see §4.6) |

### 4.2 Objective criteria (decision procedure)

Evaluate in this exact order. First match wins. All predicates read only the
manifest's own fields plus `verify_chain`:

1. **C0 — Chain invalid.** If `chain.valid == false` ⟹ `INDETERMINATE`.
   (We cannot trust any record, including success records.)
2. **C1 — Any unknown.** If any action has `effect_state == "UNKNOWN"`
   ⟹ `INDETERMINATE`. (One unproven effect poisons the whole claim. This
   dominates manual items: "we don't know" is weaker knowledge than "we know
   what remains".)
3. **C2 — Unresolved evidence pointers.** If any `event_ref`/`proof_ref` does
   not resolve, any verdict violates the §2.2 table, or `summary` counts
   mismatch ⟹ `INDETERMINATE`. (A self-contradicting manifest proves nothing.)
4. **C3 — Manual items outstanding.** If `manual_items` is non-empty ⟹
   `MANUAL_REQUIRED`. (Includes `capability_refusal` and
   `external_modification` causes. Reached only when everything is known —
   that is what makes the handoff actionable.)
5. **C4 — Auto-recovery exhausted.** If any action has
   `verdict == "NOT_RESTORED"` with cause `compensation_exhausted` (action
   state `COMPENSATION_FAILED`, attempts ≥ 3) and C3 did not fire ⟹ `PARTIAL`.
6. **C5 — Clean compensation.** If the workflow entered `COMPENSATING`, all
   actions are `RESTORED`, no manual items, no unknowns ⟹
   `VERIFIED_WITH_COMPENSATION`.
7. **C6 — Clean forward run.** If the workflow never entered `COMPENSATING`,
   all actions are `RESTORED`, no manual items, no unknowns ⟹ `VERIFIED`.
8. **C7 — Fallthrough.** Anything else (e.g. workflow terminal `FAILED` with
   all-no-effect-required `RESTORED`) ⟹ `VERIFIED` if every verdict is
   `RESTORED` and no compensation ran; otherwise `INDETERMINATE`. The
   fallthrough MUST NOT produce `PARTIAL` or `MANUAL_REQUIRED` — those need
   their positive evidence above.

### 4.3 Worked classifications

- Happy-path onboarding (10 steps, all `VERIFIED`, chain valid, no
  `compensation.started`) → `VERIFIED`.
- Billing-500 chaos run from `test_chaos.py` (7 compensated with verified
  absence, 1 `FAILED` trigger, 2 `SKIPPED`, chain valid) → 
  `VERIFIED_WITH_COMPENSATION` (C5: 7 `COMPENSATED` in reverse order
  `[8,7,5,4,3,2,1]`, 1 certain-failure `FAILED`, 2 `SKIPPED`; pinned by
  `test_compensated_run_is_verified_with_compensation`: 10/10 `RESTORED`,
  `compensations_run == 7`).
- Tampered evidence chain (one payload rewritten) → `INDETERMINATE` via C0,
  whatever the states say (`test_tampered_chain_is_indeterminate`).
- External delete after a clean run (workspace row gone, seq 3 effect
  `ABSENT` where `PRESENT` was required) → `INDETERMINATE` via C7, with a
  `divergences[]` entry (`test_external_delete_after_success_is_divergence`).
- Manual capability left `VERIFIED` in a compensated run (`IRREVERSIBLE`
  notify send, effect still `PRESENT`) → `MANUAL_REQUIRED` via C3, with a
  `capability_refusal` manual item and `R_CAPABILITY_REFUSAL`
  (`test_unit_manual_refusal_needs_human`).
- External modification during compensation (`PRECONDITION_FAILED`, effect
  still `PRESENT`) → `MANUAL_REQUIRED` via C3, with an
  `external_modification` manual item and `R_EXTERNAL_MODIFICATION`
  (`test_unit_external_modification_orders_manual_work`).
- Exhausted auto-recovery (`COMPENSATION_FAILED` after 3 attempts, effect
  `PRESENT`, no manual items) → `PARTIAL` via C4
  (`test_unit_exhausted_compensation_is_partial`).
- Missing verify/compensation record (`COMPENSATED` with no `COMPENSATED`
  transition in evidence) → `INDETERMINATE` via C1
  (`test_unit_missing_record_is_indeterminate`).

### 4.4 Confidence versus workflow state (normative)

The §4.1 "can carry" column describes how the shipped engine and evaluator
behave together; it is a pairing table, not an evaluator cross-check:

| Workflow state | Confidence the v1 evaluator yields for it |
|---|---|
| `COMPLETED` | `VERIFIED`, or `INDETERMINATE` when capped (C0/C1/C2/C7) |
| `COMPENSATED` | `VERIFIED_WITH_COMPENSATION`, or `INDETERMINATE` when capped |
| `PARTIALLY_COMPENSATED` | `PARTIAL`, or `INDETERMINATE` when capped |
| `MANUAL_REQUIRED` | `MANUAL_REQUIRED`, or `INDETERMINATE` when capped |
| `FAILED` (compensation never started) | `VERIFIED` if every verdict is `RESTORED` and no compensation ran (C7), else `INDETERMINATE` |
| `CANCELLED` | No manifest: whole-manifest refusal R5 (§5.3) |

Shipped-evaluator fact: `evaluate_recovery` derives confidence from the
manifest's own fields plus `verify_chain` only. `workflow_state` is recorded
in `confidence_criteria.evaluated` for audit, but no C-rule branches on it
(`routes/recovery.py`), so v1 does not refuse state/confidence mismatches.
A mismatch (e.g. a `COMPENSATED` workflow whose manifest carries manual
items) therefore indicates an engine or evaluator bug; readers handle it per
§4.6, never by trusting the stated confidence. `INDETERMINATE` is portable
across all five evaluatable terminal states: it is a cap, not a state label.

### 4.5 Dominance and capping (normative)

Rule order is dominance order: C0 > C1 > C2 > C3 > C4 > C5/C6 > C7.

- **Ignorance dominates actionability.** Any `UNKNOWN` effect yields
  `INDETERMINATE` even when manual items are also outstanding (C1 runs
  before C3). "We don't know" is weaker knowledge than "we know what
  remains", so it must win.
- **Actionability dominates partial auto-recovery.** Any manual item yields
  `MANUAL_REQUIRED` even when compensations are also exhausted (C3 runs
  before C4). `PARTIAL` therefore requires zero manual items: it means "the
  machine did all it could and no known human work is pending".
- **Clean levels require everything.** C5/C6 fire only with all verdicts
  `RESTORED`, no manual items, no unknowns, and a valid chain — plus
  compensation ran (C5) or never ran (C6).
- **The fallthrough never upgrades.** C7 yields `VERIFIED` only for
  all-`RESTORED` with no compensation run; any other residue yields
  `INDETERMINATE`. C7 MUST NOT manufacture `PARTIAL` or `MANUAL_REQUIRED`:
  those need their positive evidence (exhausted attempts, manual items).

### 4.6 Self-contradiction and reader fallback (normative)

C2 is the manifest's self-check, evaluated by the shipper and re-checkable
by any reader from the manifest body alone:

1. Every `event_ref` / `proof_ref` resolves to a real event sequence in the
   workflow's timeline.
2. Every per-action verdict obeys the §2.2 truth table for its
   (`required`, `effect_state`) pair.
3. `summary` counts match the arrays (`actions_total`, restored /
   not-restored / indeterminate split, `manual_items`, `refusals`).

Any failure yields `INDETERMINATE`, whatever else the manifest claims.

**Unenumerated-manual-item bugs.** If a run needed a human but produced no
`manual_items` entry, the manifest MUST NOT claim a clean level. The gap
surfaces as a C2 failure (dangling or missing refs) or as a C7 residue
(`NOT_RESTORED` without manual or exhausted cause) — both read as
`INDETERMINATE`. Silence about required human work is never `VERIFIED`.

**Chain-invalid cap.** C0 fires before every other rule: a manifest with
`chain.valid == false` MUST be read as `INDETERMINATE` regardless of its
stated confidence (§3.5 reader rule). No record — including success
records — can be trusted once the chain breaks.

**Reader obligation.** Readers MUST recompute C0–C2 from the manifest body
and, on any failure, treat the manifest as `INDETERMINATE` regardless of
its stated `recovery_confidence`.

## 5. Refusal codes (normative)

### 5.1 Two tiers

| Tier | Shape | Codes | Manifest? |
|---|---|---|---|
| Whole-manifest refusal | HTTP 409, JSON `detail` with `code`, `workflow_state`, `reason`, `retryable: false` | R4, R5 | No manifest is emitted |
| In-manifest refusal | `refusals[]` entry with `code`, `seq`, `reason`, `event_ref` | `R_CAPABILITY_REFUSAL`, `R_EXTERNAL_MODIFICATION` | Yes; usually `MANUAL_REQUIRED` via C3 |

HTTP 404 `"workflow not found"` (unknown id, or a workflow owned by another
org) is not a refusal: it carries no R-code and says nothing about recovery.

### 5.2 R4_NOT_TERMINAL

- **Condition:** `wf.state` is not in engine `WF_TERMINAL`
  (`COMPLETED`, `COMPENSATED`, `PARTIALLY_COMPENSATED`, `MANUAL_REQUIRED`,
  `FAILED`, `CANCELLED` — `saga.py`). Any live state (`DRAFT` … `READY`,
  `RUNNING`, `VERIFYING`, `RETRYING`, `COMPENSATING`) refuses.
- **Shape:** HTTP 409, `detail.code == "R4_NOT_TERMINAL"`,
  `retryable: false`. The refusal is final for that workflow state; the
  caller may request a fresh evaluation after the run terminates.
- **Spec anchor:** the §2.3 rule — the RPE MUST refuse to emit a manifest
  for non-terminal workflows, because per-action `required` is still moving.
- Pinned by `test_non_terminal_workflow_is_refused`.

### 5.3 R5_CANCELLED_RUN

- **Condition:** the workflow is terminal but not evaluatable: `CANCELLED`.
  The v1 evaluatable set is `COMPLETED`, `COMPENSATED`,
  `PARTIALLY_COMPENSATED`, `MANUAL_REQUIRED`, `FAILED`
  (`EVALUATABLE_TERMINAL` in `routes/recovery.py`).
- **Shape:** HTTP 409, `detail.code == "R5_CANCELLED_RUN"`,
  `retryable: false`.
- **Rationale:** no confidence level is defined for cancelled runs. A
  cancelled run may hold partially present effects with no recorded
  compensation obligation, so any of the five levels would mislabel it.
  Refusing honestly beats a confident lie.

### 5.4 R_CAPABILITY_REFUSAL

- **Condition:** an action is `VERIFIED` in a compensated run with a manual
  capability — `IRREVERSIBLE`, `MANUAL_ONLY`, or `UNKNOWN` (`MANUAL_CAPS`,
  identical sets in `saga.py` and `routes/recovery.py`). The engine never
  queues these for auto-undo: `_start_compensation` emits
  `compensation.manual_required` (`"not automatically reversible"`) and the
  action keeps its verified, still-`PRESENT` effect.
- **Manifest records:** the action reads `effect_state: PRESENT`,
  `verdict: NOT_RESTORED`; one `manual_items[]` entry with
  `cause: capability_refusal`; one `refusals[]` entry with
  `code: R_CAPABILITY_REFUSAL`, mirroring the manual item's `reason`, with
  `event_ref` pointing at the `compensation.manual_required` (or
  `workflow.manual_required`) event.
- **Capability split (shipped):** `FULLY_REVERSIBLE`,
  `CONDITIONALLY_REVERSIBLE`, `COMPENSATABLE` are auto-compensated
  (`COMPENSATABLE_CAPS`); `IRREVERSIBLE`, `MANUAL_ONLY`, `UNKNOWN` always
  refuse and need a human. `ActionRun.compensation_capability` defaults to
  `UNKNOWN` (`models.py`), so an unclassified action fails closed to a
  human, never to silent auto-undo.
- Pinned by `test_unit_manual_refusal_needs_human`.

### 5.5 R_EXTERNAL_MODIFICATION

- **Condition:** compensation was queued but refused because the target
  changed incompatibly: action state `COMPENSATION_FAILED` with
  `action.error` starting `PRECONDITION_FAILED`, effect still `PRESENT`.
- **Manifest records:** one `manual_items[]` entry with
  `cause: external_modification`; one `refusals[]` entry with
  `code: R_EXTERNAL_MODIFICATION`, with `event_ref` pointing at the
  manual-required event or, failing that, the `COMPENSATION_FAILED`
  transition.
- **State-equivalence (§2.5):** the engine's own earlier compensations may
  advance resource versions without refusing; only genuinely incompatible
  external changes refuse (`docs/jury/06-security-and-recovery.md`). The
  refusal protects another actor's newer work from being destroyed by an
  undo — see the §6.2 scenario.
- **Naming:** the V2-02 draft example used `R2_EXTERNAL_MODIFICATION`; the
  shipped evaluator emits `R_EXTERNAL_MODIFICATION` (`routes/recovery.py`,
  pinned by `test_unit_external_modification_orders_manual_work`). The §3.4
  example is corrected to the shipped code.
- Cause-to-code mapping (shipped): `external_modification` →
  `R_EXTERNAL_MODIFICATION`; every other manual-item cause →
  `R_CAPABILITY_REFUSAL`.

### 5.6 Code inventory (v1, closed)

v1 defines exactly four refusal codes: `R4_NOT_TERMINAL`,
`R5_CANCELLED_RUN`, `R_CAPABILITY_REFUSAL`, `R_EXTERNAL_MODIFICATION`.
There are no R1–R3 codes in the shipped evaluator or its tests; numbers in
that range MUST NOT be assumed to exist by readers. Whole-manifest codes
(R4/R5) travel on the HTTP error because there is no manifest to carry
them; in-manifest codes travel in `refusals[]` with one entry per manual
item behind them, so `summary.refusals == len(refusals)` doubles as the
C2 count check.

## 6. Refusal scenarios (informative)

These traces show the engine-to-manifest path for each refusal. They are
illustrative inputs/outputs for implementers, not measured runs (per §0);
each names the test that pins the behavior it describes.

### 6.1 Design-time refusal: real-money payment

A connector contract carrying the `no_real_payment` precondition
(`connectors/sdk.py`) raises `PreconditionFailed("real payments are
forbidden")` when `charge_real_money` is truthy. The action fails
certainly before any effect exists (`FAILED`, no trail through
`SUCCEEDED`/`VERIFYING`/`UNKNOWN_OUTCOME`), so the manifest reads the
effect `ABSENT` and the verdict `RESTORED` — there was nothing to undo.
The same shape covers the refused-by-design list in
`docs/jury/06-security-and-recovery.md` (real payments, mass sends,
third-party accounts, canceling a mid-flight compensation): those are
engine refusals, and the manifest surfaces their outcome rather than
re-refusing them.

### 6.2 Runtime refusal: external modification mid-compensation

1. `crm.create_org` (seq 2, `COMPENSATABLE`) verifies, then billing fails
   and `_start_compensation` queues seq 2 (`VERIFIED` →
   `COMPENSATION_PENDING`, `compensation.started` recorded).
2. Before the undo runs, an external actor advances the org (v1 → v5).
   `_compensate_one` raises through the version guard and records
   `COMPENSATING` → `COMPENSATION_FAILED` with
   `error: "PRECONDITION_FAILED: resource 1 changed (expected v1, found
   v5); refusing to overwrite a newer state"`.
3. The evaluator re-reads the effect (`PRESENT`, v5 row still active),
   emits a manual item (`cause: external_modification`,
   `suggested_action` points at reconciling the external change) and a
   `refusals[]` entry with `code: R_EXTERNAL_MODIFICATION`.
4. One manual item outstanding, everything known → `MANUAL_REQUIRED`
   via C3.
5. After the human reconciles and re-runs evaluation, a later manifest
   reflects the new world; the old manifest stays valid history (§3.5).

Pinned by `test_unit_external_modification_orders_manual_work` (manifest
path) and `test_concurrent_modification_blocks_compensation` (store-level
`PreconditionFailed` guard).

### 6.3 Capability refusal: manual-only effect in a compensated run

1. `notify.send_summary` (seq 10, `IRREVERSIBLE`) verifies and sends;
   a later failure triggers compensation.
2. `_start_compensation` refuses to queue seq 10, emits
   `compensation.manual_required`, and records `compensation.started`
   with `manual_items: 1`. The action stays `VERIFIED`, effect `PRESENT`.
3. The evaluator emits a manual item (`cause: capability_refusal`) and a
   `refusals[]` entry with `code: R_CAPABILITY_REFUSAL`.
4. One manual item outstanding, everything known → `MANUAL_REQUIRED`
   via C3.

Pinned by `test_unit_manual_refusal_needs_human`.

### 6.4 Exhaustion without human blockers: PARTIAL

`crm.create_org` (seq 2, `COMPENSATABLE`) fails compensation 3 times
(the engine retries while `_comp_attempts < 3` and records
`"comp attempt {n}/3"`; `COMPENSATION_FAILED` with attempts ≥ 3 is
exhausted). The effect is still `PRESENT`, no manual item applies, and
C3 does not fire — so C4 yields `PARTIAL`: the machine did all it could,
nothing is unknown, and no known human work is pending. Pinned by
`test_unit_exhausted_compensation_is_partial`.

### 6.5 Whole-manifest refusals

- Probing a `RUNNING` workflow's manifest returns HTTP 409
  `R4_NOT_TERMINAL` with the current `workflow_state` echoed in the
  detail (pinned by `test_non_terminal_workflow_is_refused`). The caller
  retries the GET after the run reaches a terminal state.
- Probing a `CANCELLED` workflow returns HTTP 409 `R5_CANCELLED_RUN`:
  no manifest, no confidence level, no guess about half-present effects.

### 6.6 v1 implementation notes (shipped, informative)

Beyond the §3 schema, the v1 evaluator (`routes/recovery.py`,
`GET /api/v1/workflows/{id}/recovery-manifest`, registered in `main.py`)
ships these additional manifest sections; readers MUST ignore unknown
fields per §3.1, so they are safe extensions:

- `confidence_criteria`: `{rule, decision, evaluated}` — the winning
  C-rule, a one-line decision rationale, and the evaluated predicates
  (`workflow_state`, `chain_valid`, `unknowns`, `refs_resolve`,
  `table_holds`, `counts_match`, `manual_items`,
  `exhausted_compensations`, `compensation_started`, `all_restored`).
- `compensations[]`: one entry per action that needed compensation, with
  `result` in `compensated` | `noop` | `failed` | `refused` |
  `incomplete`.
- `divergences[]`: recorded-claim vs current-store-row mismatches
  (effect still present after recorded compensation, effect lost after
  recorded success, skipped action left an effect).
- `indeterminate[]`: one entry per `UNKNOWN` action with its reason.
- `initial_resources[]` / `created_resources[]` / `final_resources[]`:
  demo-store snapshots tracing what the run found, made, and left behind.

Producer guarantees (shipped): keys emitted sorted for stable hashing;
`generator: "reversa-rpe/1.0"`; read-only by construction — the evaluator
only SELECTs workflows, actions, events, and demo-store rows, never
appends events, never retries, never compensates, and never calls
connector execute/verify/compensate. Current store rows can only
*downgrade* a recorded claim (a divergence); they never upgrade a missing
record into a proven claim.