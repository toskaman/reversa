# Recovery Proof Engine — Product Spec (REVERSA V2, cycle 1)

- Status: DRAFT spec (AGENT-04, Recovery Researcher). No implementation in this cycle.
- Scope: defines what "recovered" means, what evidence proves it, and when the
  engine must refuse to claim recovery.
- Non-goals: no new states, no API changes, no UI changes in this cycle.
  Implementers map this spec onto the existing engine; any mapping gap is a
  spec bug, not an engine bug, until reviewed.

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
  "code": "R2_EXTERNAL_MODIFICATION",
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
...[truncated 6268 chars]