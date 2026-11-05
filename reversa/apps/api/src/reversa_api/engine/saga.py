"""Durable saga orchestrator: claims, execution, verification, compensation.

Single-threaded synchronous runner (`execute_workflow_sync`) plus
compare-and-swap claims so parallel workers cannot double-execute.
Every state change is allow-listed (states.py) and journaled (evidence.py).
"""

from __future__ import annotations

import datetime as dt
import json
import random
import time
from enum import Enum

from sqlalchemy import or_, select, update

from ..config import settings
from ..connectors.sdk import (
    ChaosTriggered,
    ConnectorError,
    PreconditionFailed,
    chaos_error,
    get_connector,
)
from ..evidence import append_event, redact
from ..models import ActionRun, ChaosRule, Organization, Workflow, utcnow
from .states import check_action_transition, check_workflow_transition

COMPENSATABLE_CAPS = {
    "FULLY_REVERSIBLE",
    "CONDITIONALLY_REVERSIBLE",
    "COMPENSATABLE",
}
MANUAL_CAPS = {"IRREVERSIBLE", "MANUAL_ONLY", "UNKNOWN"}

WF_TERMINAL = {
    "COMPLETED",
    "COMPENSATED",
    "PARTIALLY_COMPENSATED",
    "MANUAL_REQUIRED",
    "FAILED",
    "CANCELLED",
}
ACT_FORWARD_DONE = {"VERIFIED", "SKIPPED", "COMPENSATED"}


class VerificationOutcome(str, Enum):
    """Typed verification verdict (P0-REC-01).

    Maps to docs/product/recovery-proof-engine.md section 2 effect states:
    PRESENT -> PRESENT, ABSENT_CONFIRMED -> ABSENT, INDETERMINATE -> UNKNOWN.
    """

    PRESENT = "PRESENT"
    ABSENT_CONFIRMED = "ABSENT_CONFIRMED"
    INDETERMINATE = "INDETERMINATE"


def _lease_is_stale(action: ActionRun, now: dt.datetime) -> bool:
    """True when no live worker can own this action.

    A missing lease carries no ownership claim, so it counts as stale.
    """
    return action.lease_expires_at is None or action.lease_expires_at < now


def _verify_effect(
    org: Organization, wf: Workflow, action: ActionRun
) -> tuple[VerificationOutcome, str]:
    """Verify one action's effect. Never raises, never guesses.

    TRUE from a clean verify call -> PRESENT; FALSE from a clean call ->
    ABSENT_CONFIRMED; anything else (verifier raised or crashed, unknown
    connector/contract, unreadable stored state, non-boolean answer) ->
    INDETERMINATE. A verifier error is never absence proof.
    """
    try:
        inputs = json.loads(action.input_json or "{}")
    except (ValueError, TypeError) as exc:
        return VerificationOutcome.INDETERMINATE, f"unreadable inputs: {exc}"
    if not isinstance(inputs, dict):
        return VerificationOutcome.INDETERMINATE, "stored inputs have no verifiable shape"
    try:
        prior = json.loads(action.output_json or "{}")
    except (ValueError, TypeError) as exc:
        return VerificationOutcome.INDETERMINATE, f"unreadable stored output: {exc}"
    probe = prior.get("output", prior) if isinstance(prior, dict) else prior
    if not isinstance(probe, dict):
        return VerificationOutcome.INDETERMINATE, "stored output has no verifiable shape"
    try:
        connector = get_connector(action.connector_id)
        contract = connector.contract_for(action.action_type)
        present = connector.verify(_ctx(org, wf, action), contract, inputs, probe)
    except ConnectorError as exc:
        return VerificationOutcome.INDETERMINATE, f"verifier error {exc.code}: {exc}"
    except Exception as exc:  # noqa: BLE001 - a verifier crash proves nothing
        return VerificationOutcome.INDETERMINATE, (
            f"verifier crashed ({type(exc).__name__}): {exc}"
        )
    if present is True:
        return VerificationOutcome.PRESENT, "effect confirmed present"
    if present is False:
        return VerificationOutcome.ABSENT_CONFIRMED, "effect confirmed absent"
    return VerificationOutcome.INDETERMINATE, (
        f"verifier returned non-boolean {type(present).__name__}"
    )


def _transition_wf(session, wf: Workflow, new: str, actor: str, note: str = "") -> None:
    check_workflow_transition(wf.state, new)
    old = wf.state
    wf.state = new
    wf.updated_at = utcnow()
    append_event(
        session, wf.id, wf.org_id, "workflow.state",
        {"from": old, "to": new, "note": note}, actor=actor,
    )


def transition_action(session, wf: Workflow, action: ActionRun, new: str, actor: str,
                      note: str = "") -> None:
    """Allow-listed, journaled action-state transition (raises InvalidTransition)."""
    check_action_transition(action.state, new)
    old = action.state
    action.state = new
    action.updated_at = utcnow()
    append_event(
        session, wf.id, wf.org_id, "action.state",
        {"seq": action.seq, "action_type": action.action_type,
         "from": old, "to": new, "note": note},
        actor=actor,
    )


def _lease_until() -> dt.datetime:
    return utcnow() + dt.timedelta(seconds=settings.lease_ttl_seconds)


def claim_action(session, wf: Workflow, action_id: int, worker_id: str) -> ActionRun | None:
    """Compare-and-swap claim. Returns the action iff this worker won it."""
    now = utcnow()
    res = session.execute(
        update(ActionRun)
        .where(ActionRun.id == action_id, ActionRun.state == "PENDING")
        .values(state="CLAIMED", lease_owner=worker_id,
                lease_expires_at=_lease_until(), updated_at=now)
    )
    session.commit()
    if res.rowcount != 1:
        return None
    action = session.get(ActionRun, action_id)
    append_event(
        session, wf.id, wf.org_id, "action.claimed",
        {"seq": action.seq, "worker": worker_id}, actor=worker_id,
    )
    session.commit()
    return action


def reclaim_expired_leases(session, wf: Workflow, worker_id: str) -> int:
    now = utcnow()
    rows = session.scalars(
        select(ActionRun).where(
            ActionRun.workflow_id == wf.id,
            ActionRun.state == "CLAIMED",
            ActionRun.lease_expires_at < now,
        )
    ).all()
    for action in rows:
        transition_action(session, wf, action, "PENDING", worker_id, "lease expired")
        action.lease_owner = ""
        action.lease_expires_at = None
    return len(rows)


def _consume_chaos(session, wf: Workflow, org: Organization, action: ActionRun,
                   worker_id: str) -> None:
    """Fire at most one matching chaos rule. Demo tenant only. Raises on fault.

    Deterministic precedence (F3): among live rules for this org+connector,
    only action-matching rules compete (exact target_action or wildcard ""),
    and the lowest-id match fires. Filtering before the pick (not after)
    keeps an earlier non-matching rule from shadowing a later match, while
    a mismatch still consumes no budget.
    """
    if not settings.chaos_enabled or not org.is_demo:
        return
    rule = session.scalars(
        select(ChaosRule)
        .where(
            ChaosRule.org_id == org.id,
            ChaosRule.enabled == 1,
            ChaosRule.times_remaining > 0,
            ChaosRule.target_connector == action.connector_id,
            or_(
                ChaosRule.target_action == "",
                ChaosRule.target_action.is_(None),
                ChaosRule.target_action == action.action_type,
            ),
        )
        .order_by(ChaosRule.id)
    ).first()
    if rule is None:
        return
    rule.times_remaining -= 1
    append_event(
        session, wf.id, wf.org_id, "chaos.injected",
        {"seq": action.seq, "connector": action.connector_id,
         "action_type": action.action_type, "fault": rule.fault},
        actor=worker_id,
    )
    if rule.fault == "latency":
        time.sleep(2)
        return
    raise chaos_error(action.connector_id, action.action_type, rule.fault)


def _ctx(org: Organization, wf: Workflow, action: ActionRun) -> dict:
    return {
        "org_id": org.id,
        "is_demo": bool(org.is_demo),
        "workflow_id": wf.id,
        "idempotency_key": action.idempotency_key,
    }


def _fail(session, wf, org, action, worker_id, code, message, retryable) -> None:
    """Record a failure; schedule a bounded retry or leave FAILED for the pump."""
    action.error = f"{code}: {message}"
    action.output_json = json.dumps(
        {"_failure": {"code": code, "retryable": retryable, "error": message}}
    )
    transition_action(session, wf, action, "FAILED", worker_id, action.error)
    if retryable and action.attempt < action.max_attempts:
        transition_action(session, wf, action, "RETRY_SCHEDULED", worker_id,
                        f"attempt {action.attempt}/{action.max_attempts}")
        if wf.state == "RUNNING":
            _transition_wf(session, wf, "RETRYING", worker_id, "retry scheduled")
    session.commit()


def _run_claimed(session, wf: Workflow, org: Organization, action: ActionRun,
                 worker_id: str, actor: str) -> None:
    """CLAIMED -> EXECUTING -> SUCCEEDED -> VERIFYING -> VERIFIED (or FAILED paths)."""
    action.attempt += 1
    action.lease_expires_at = _lease_until()
    transition_action(session, wf, action, "EXECUTING", worker_id,
                    f"attempt {action.attempt}")
    session.commit()  # persist attempt before any external effect
    inputs = json.loads(action.input_json or "{}")
    ctx = _ctx(org, wf, action)
    try:
        connector = get_connector(action.connector_id)
        contract = connector.contract_for(action.action_type)
        _consume_chaos(session, wf, org, action, worker_id)
        output = connector.execute(ctx, contract, inputs)
    except ChaosTriggered as exc:
        action.error = f"{exc.code}: {exc}"
        if exc.uncertain:
            transition_action(session, wf, action, "UNKNOWN_OUTCOME", worker_id, action.error)
        else:
            _fail(session, wf, org, action, worker_id, exc.code, str(exc), exc.retryable)
            return
        session.commit()
        return
    except PreconditionFailed as exc:
        _fail(session, wf, org, action, worker_id, "PRECONDITION_FAILED", str(exc), False)
        return
    except ConnectorError as exc:
        _fail(session, wf, org, action, worker_id, exc.code, str(exc), exc.retryable)
        return
    action.output_json = json.dumps(output)
    action.error = ""
    transition_action(session, wf, action, "SUCCEEDED", worker_id, "effect applied")
    session.commit()  # persist result before verification
    transition_action(session, wf, action, "VERIFYING", worker_id, "checking effect")
    session.commit()
    try:
        ok = connector.verify(ctx, contract, inputs, output)
        verify_note = "effect confirmed" if ok else "effect NOT confirmed"
    except ConnectorError as exc:
        ok, verify_note = False, f"verify error {exc.code}: {exc}"
    if ok:
        action.error = ""
        transition_action(session, wf, action, "VERIFIED", worker_id, verify_note)
        session.commit()
    else:
        action.error = verify_note
        action.output_json = json.dumps(
            {"_failure": {"code": "VERIFY_FAILED", "retryable": True,
                          "error": verify_note, "output": output}}
        )
        transition_action(session, wf, action, "FAILED", worker_id, verify_note)
        if action.attempt < action.max_attempts:
            transition_action(session, wf, action, "RETRY_SCHEDULED", worker_id,
                            f"attempt {action.attempt}/{action.max_attempts}")
            if wf.state == "RUNNING":
                _transition_wf(session, wf, "RETRYING", worker_id, "retry scheduled")
        session.commit()


def _reconcile_unknown(session, wf: Workflow, org: Organization, action: ActionRun,
                       worker_id: str) -> VerificationOutcome:
    """Reconcile an UNKNOWN_OUTCOME with typed tri-state verification (P0-REC-01).

    PRESENT -> VERIFIED (confirmed, no re-execution); ABSENT_CONFIRMED ->
    FAILED (+ retry when attempts remain); INDETERMINATE -> stays
    UNKNOWN_OUTCOME (deferred; a verifier error must never count as absence
    proof, so the action is never failed or retried on that basis).
    """
    outcome, detail = _verify_effect(org, wf, action)
    if outcome is VerificationOutcome.PRESENT:
        action.error = ""
        transition_action(session, wf, action, "VERIFYING", worker_id, "reconciling outcome")
        transition_action(session, wf, action, "VERIFIED", worker_id,
                        "effect confirmed; no re-execution")
    elif outcome is VerificationOutcome.ABSENT_CONFIRMED:
        action.error = "effect absent; idempotent re-execution allowed"
        transition_action(session, wf, action, "FAILED", worker_id, action.error)
        if action.attempt < action.max_attempts:
            transition_action(session, wf, action, "RETRY_SCHEDULED", worker_id,
                            "reconciled absent; safe idempotent retry")
            if wf.state == "RUNNING":
                _transition_wf(session, wf, "RETRYING", worker_id, "retry scheduled")
    else:
        action.error = f"reconcile deferred: {detail}; awaiting verifier"
        append_event(
            session, wf.id, wf.org_id, "action.reconcile_indeterminate",
            {"seq": action.seq, "action_type": action.action_type, "detail": detail},
            actor=worker_id,
        )
    session.commit()
    return outcome


def _resume_interrupted_verification(session, wf: Workflow, org: Organization,
                                     action: ActionRun,
                                     worker_id: str) -> VerificationOutcome:
    """Resume a SUCCEEDED/VERIFYING action left by a crash (P0-REC-02).

    Verifies in place; never re-executes. PRESENT -> VERIFIED,
    ABSENT_CONFIRMED -> FAILED (+ retry when attempts remain),
    INDETERMINATE -> stays VERIFYING (deferred until the verifier answers).
    """
    if action.state == "SUCCEEDED":
        transition_action(session, wf, action, "VERIFYING", worker_id,
                        "resume: success was durable, confirmation was not")
    outcome, detail = _verify_effect(org, wf, action)
    if outcome is VerificationOutcome.PRESENT:
        action.error = ""
        transition_action(session, wf, action, "VERIFIED", worker_id,
                        f"resume: {detail}; no re-execution")
    elif outcome is VerificationOutcome.ABSENT_CONFIRMED:
        action.error = f"resume: {detail}; idempotent re-execution allowed"
        transition_action(session, wf, action, "FAILED", worker_id, action.error)
        if action.attempt < action.max_attempts:
            transition_action(session, wf, action, "RETRY_SCHEDULED", worker_id,
                            f"attempt {action.attempt}/{action.max_attempts}")
            if wf.state == "RUNNING":
                _transition_wf(session, wf, "RETRYING", worker_id, "retry scheduled")
    else:
        action.error = f"resume deferred: {detail}"
        append_event(
            session, wf.id, wf.org_id, "action.verify_indeterminate",
            {"seq": action.seq, "action_type": action.action_type, "detail": detail},
            actor=worker_id,
        )
    session.commit()
    return outcome


def _resume_interrupted_compensation(session, wf: Workflow, org: Organization,
                                     action: ActionRun,
                                     worker_id: str) -> VerificationOutcome:
    """Resume a COMPENSATING action left by a crash (P0-REC-02).

    Re-reads the forward effect; never assumes the undo happened.
    ABSENT_CONFIRMED -> COMPENSATED (the undo demonstrably took effect
    before the crash), PRESENT -> COMPENSATION_FAILED (effect still there;
    needs (re-)compensation), INDETERMINATE -> stays COMPENSATING.
    """
    outcome, detail = _verify_effect(org, wf, action)
    if outcome is VerificationOutcome.ABSENT_CONFIRMED:
        try:
            output = json.loads(action.output_json or "{}")
        except ValueError:
            output = {}
        if isinstance(output, dict):
            output["_comp_proof"] = {"resumed_after_crash": True, "verify_detail": detail}
            action.output_json = json.dumps(output)
        action.error = ""
        transition_action(session, wf, action, "COMPENSATED", worker_id,
                        f"resume: {detail}; undo took effect before the crash")
    elif outcome is VerificationOutcome.PRESENT:
        action.error = (f"resume: {detail}; effect still present,"
                        " re-compensation required")
        transition_action(session, wf, action, "COMPENSATION_FAILED", worker_id, action.error)
    else:
        action.error = f"resume deferred: {detail}"
        append_event(
            session, wf.id, wf.org_id, "action.compensation_indeterminate",
            {"seq": action.seq, "action_type": action.action_type, "detail": detail},
            actor=worker_id,
        )
    session.commit()
    return outcome


def _deps_status(session, wf: Workflow, action: ActionRun,
                 states: dict[int, str] | None = None) -> str:
    deps = json.loads(action.depends_on or "[]")
    if not deps:
        return "ready"
    # Pump callers pass the precomputed {seq: state} map (built from the
    # already-loaded actions, so identical to a re-SELECT via the identity
    # map); direct callers without a map keep the one-shot load.
    if states is None:
        states = {
            row.seq: row.state
            for row in session.scalars(
                select(ActionRun).where(ActionRun.workflow_id == wf.id)
            ).all()
        }
    for dep in deps:
        if states.get(dep) != "VERIFIED":
            if states.get(dep) in (None, "SKIPPED", "FAILED", "COMPENSATED",
                                   "COMPENSATION_FAILED", "COMPENSATION_PENDING",
                                   "COMPENSATING"):
                return "blocked"
            return "waiting"
    return "ready"


def _backoff_delay(action: ActionRun) -> float:
    delay = min(1.0 * (2 ** max(action.attempt - 1, 0)), 30.0)
    return delay + random.uniform(0, min(delay * 0.25, 5.0))


def _comp_attempts(action: ActionRun) -> int:
    try:
        return int(json.loads(action.output_json or "{}").get("_comp_attempts", 0))
    except (ValueError, AttributeError):
        return 0


def _start_compensation(session, wf: Workflow, org: Organization,
                        worker_id: str, reason: str) -> None:
    """Enter COMPENSATING: block dependents, queue compensations, flag manual items."""
    _transition_wf(session, wf, "COMPENSATING", worker_id, reason)
    actions = session.scalars(
        select(ActionRun).where(ActionRun.workflow_id == wf.id).order_by(ActionRun.seq)
    ).all()
    queued, manual = 0, 0
    for action in actions:
        if action.state in ("PENDING", "RETRY_SCHEDULED"):
            transition_action(session, wf, action, "SKIPPED", worker_id,
                            "dependent blocked by failure")
        elif action.state == "VERIFIED":
            if action.compensation_capability in COMPENSATABLE_CAPS:
                transition_action(session, wf, action, "COMPENSATION_PENDING", worker_id,
                                "queued for compensation")
                queued += 1
            else:
                manual += 1
                append_event(
                    session, wf.id, wf.org_id, "compensation.manual_required",
                    {"seq": action.seq, "action_type": action.action_type,
                     "capability": action.compensation_capability,
                     "reason": "not automatically reversible"},
                    actor=worker_id,
                )
        elif action.state in ("SUCCEEDED", "VERIFYING"):
            # Effect may exist: verify once, then compensate or drop.
            # A verifier error is never absence proof: when the world cannot
            # be read, the effect is assumed present (fail closed) so it is
            # either compensated or escalated to a human, never dropped.
            outcome, detail = _verify_effect(org, wf, action)
            if action.state == "SUCCEEDED":
                transition_action(session, wf, action, "VERIFYING", worker_id,
                                "late verification before compensation")
            assume_present = outcome is not VerificationOutcome.ABSENT_CONFIRMED
            if assume_present and action.compensation_capability in COMPENSATABLE_CAPS:
                if outcome is VerificationOutcome.PRESENT:
                    note = "late verification before compensation"
                else:
                    note = f"effect unprovable ({detail}); assuming present for safety"
                transition_action(session, wf, action, "VERIFIED", worker_id, note)
                transition_action(session, wf, action, "COMPENSATION_PENDING", worker_id,
                                "queued for compensation")
                queued += 1
            elif assume_present:
                manual += 1
                transition_action(session, wf, action, "VERIFIED", worker_id,
                                f"effect may exist ({detail}); needs a human")
                append_event(
                    session, wf.id, wf.org_id, "compensation.manual_required",
                    {"seq": action.seq, "action_type": action.action_type,
                     "capability": action.compensation_capability,
                     "reason": "effect present or unprovable; not automatically reversible"},
                    actor=worker_id,
                )
            else:
                transition_action(session, wf, action, "FAILED", worker_id,
                                f"effect confirmed absent ({detail}); nothing to undo")
                transition_action(session, wf, action, "SKIPPED", worker_id,
                                "no confirmed effect to undo")
    append_event(
        session, wf.id, wf.org_id, "compensation.started",
        {"reason": reason, "queued": queued, "manual_items": manual}, actor=worker_id,
    )
    session.commit()


def _compensate_one(session, wf: Workflow, org: Organization, action: ActionRun,
                    worker_id: str) -> None:
    """COMPENSATION_PENDING -> COMPENSATING -> COMPENSATED (verified) or FAILED."""
    transition_action(session, wf, action, "COMPENSATING", worker_id, "compensating")
    session.commit()
    inputs = json.loads(action.input_json or "{}")
    original_output = json.loads(action.output_json or "{}")
    ctx = _ctx(org, wf, action)
    try:
        connector = get_connector(action.connector_id)
        contract = connector.contract_for(action.action_type)
        proof = connector.compensate(ctx, contract, inputs, original_output)
    except PreconditionFailed as exc:
        _comp_failed(session, wf, action, worker_id, "PRECONDITION_FAILED", str(exc))
        return
    except ConnectorError as exc:
        _comp_failed(session, wf, action, worker_id, exc.code,
                     f"{exc} (retryable={exc.retryable})", exc.retryable)
        return
    if isinstance(proof, dict) and proof.get("noop"):
        transition_action(session, wf, action, "COMPENSATED", worker_id, "noop (read-only)")
        session.commit()
        return
    # Verify the compensation: the forward effect must now be gone.
    try:
        still_present = connector.verify(ctx, contract, inputs, original_output)
    except ConnectorError as exc:
        _comp_failed(session, wf, action, worker_id, exc.code, str(exc), True)
        return
    if still_present:
        _comp_failed(session, wf, action, worker_id, "COMPENSATION_NOT_CONFIRMED",
                     "effect still present after compensation", True)
        return
    action.output_json = json.dumps({**original_output, "_comp_proof": redact(proof)})
    transition_action(session, wf, action, "COMPENSATED", worker_id, "effect undone+verified")
    session.commit()


def _comp_failed(session, wf, action, worker_id, code, message, retryable=True) -> None:
    attempts = _comp_attempts(action) + 1
    try:
        output = json.loads(action.output_json or "{}")
    except ValueError:
        output = {}
    output["_comp_attempts"] = attempts
    action.output_json = json.dumps(output)
    action.error = f"{code}: {message}"
    transition_action(session, wf, action, "COMPENSATION_FAILED", worker_id,
                    f"{action.error} (comp attempt {attempts}/3)")
    session.commit()


def _pump_forward(session, wf: Workflow, org: Organization, worker_id: str,
                  actor: str) -> bool:
    reclaim_expired_leases(session, wf, worker_id)
    # Crash leftovers: EXECUTING with an expired lease has an uncertain outcome.
    now = utcnow()
    for action in session.scalars(
        select(ActionRun).where(
            ActionRun.workflow_id == wf.id,
            ActionRun.state == "EXECUTING",
            ActionRun.lease_expires_at < now,
        )
    ).all():
        transition_action(session, wf, action, "UNKNOWN_OUTCOME", worker_id,
                        "owner gone; outcome uncertain")
    session.commit()
    # Crash leftovers: SUCCEEDED/VERIFYING with a stale lease never confirmed
    # their effect (P0-REC-02). Resume each with verification; indeterminate
    # ones defer without blocking independent work.
    for action in session.scalars(
        select(ActionRun).where(
            ActionRun.workflow_id == wf.id,
            ActionRun.state.in_(["SUCCEEDED", "VERIFYING"]),
        )
    ).all():
        if not _lease_is_stale(action, utcnow()):
            continue  # a live worker may still own it
        if _resume_interrupted_verification(session, wf, org, action, worker_id) is not (
            VerificationOutcome.INDETERMINATE
        ):
            return True
    actions = session.scalars(
        select(ActionRun).where(ActionRun.workflow_id == wf.id).order_by(ActionRun.seq)
    ).all()
    # 1. Reconcile unknown outcomes before re-executing any external effect.
    # Indeterminate unknowns stay UNKNOWN (P0-REC-01): they defer without
    # blocking independent work, but compensation waits for them (step 2).
    saw_indeterminate = False
    for action in actions:
        if action.state == "UNKNOWN_OUTCOME":
            outcome = _reconcile_unknown(session, wf, org, action, worker_id)
            if outcome is VerificationOutcome.INDETERMINATE:
                saw_indeterminate = True
                continue
            return True
    # 2. Exhausted failure -> start compensation (deferred while any outcome is
    # still unknown: never compensate around an unverified effect, or the
    # uncertain action would be orphaned by the compensation run).
    if not saw_indeterminate:
        for action in actions:
            if action.state == "FAILED":
                _start_compensation(session, wf, org, worker_id,
                                    f"seq {action.seq} {action.action_type}: {action.error}")
                return True
    # 3. Execute the next ready action.
    dep_states = {a.seq: a.state for a in actions}
    for action in actions:
        if action.state != "PENDING":
            continue
        status = _deps_status(session, wf, action, dep_states)
        if status == "blocked":
            transition_action(session, wf, action, "SKIPPED", worker_id,
                            "dependency failed or skipped")
            session.commit()
            return True
        if status == "ready":
            if wf.state == "RETRYING":
                _transition_wf(session, wf, "RUNNING", worker_id, "forward progress")
                session.commit()
            claimed = claim_action(session, wf, action.id, worker_id)
            if claimed is None:
                return False  # lost the race; another worker owns it
            _run_claimed(session, wf, org, claimed, worker_id, actor)
            return True
    # 4. Retries: bounded backoff, then back to PENDING.
    for action in actions:
        if action.state == "RETRY_SCHEDULED":
            delay = _backoff_delay(action)
            append_event(session, wf.id, wf.org_id, "action.retry_wait",
                         {"seq": action.seq, "wait_s": round(delay, 2)}, actor=worker_id)
            session.commit()
            time.sleep(delay)
            fresh = session.get(ActionRun, action.id)
            if fresh is not None and fresh.state == "RETRY_SCHEDULED":
                transition_action(session, wf, fresh, "PENDING", worker_id, "retry due")
                session.commit()
            return True
    # 5. All done -> final verification + complete.
    if actions and all(a.state in ACT_FORWARD_DONE for a in actions):
        _transition_wf(session, wf, "VERIFYING", worker_id, "final check")
        session.commit()
        verified = sum(1 for a in actions if a.state == "VERIFIED")
        _transition_wf(session, wf, "COMPLETED", worker_id,
                       f"{verified}/{len(actions)} actions verified")
        session.commit()
        return True
    return False


def _pump_compensation(session, wf: Workflow, org: Organization, worker_id: str) -> bool:
    # Crash leftovers: COMPENSATING with a stale lease never confirmed the
    # undo (P0-REC-02). Resume each by re-reading the forward effect.
    for action in session.scalars(
        select(ActionRun).where(
            ActionRun.workflow_id == wf.id,
            ActionRun.state == "COMPENSATING",
        )
    ).all():
        if not _lease_is_stale(action, utcnow()):
            continue  # a live worker may still own it
        if _resume_interrupted_compensation(session, wf, org, action, worker_id) is not (
            VerificationOutcome.INDETERMINATE
        ):
            return True
    actions = session.scalars(
        select(ActionRun).where(ActionRun.workflow_id == wf.id)
        .order_by(ActionRun.seq.desc())
    ).all()
    for action in actions:
        if action.state == "COMPENSATION_PENDING":
            _compensate_one(session, wf, org, action, worker_id)
            return True
    for action in actions:
        if action.state == "COMPENSATION_FAILED" and _comp_attempts(action) < 3:
            transition_action(session, wf, action, "COMPENSATION_PENDING", worker_id,
                            "compensation retry")
            session.commit()
            return True
    manual = [a for a in actions
              if a.state == "VERIFIED" and a.compensation_capability in MANUAL_CAPS]
    failed_comp = [a for a in actions if a.state == "COMPENSATION_FAILED"]
    if manual:
        _transition_wf(session, wf, "MANUAL_REQUIRED", worker_id,
                       f"{len(manual)} action(s) need a human")
        append_event(
            session, wf.id, wf.org_id, "workflow.manual_required",
            {"items": [{"seq": a.seq, "action_type": a.action_type,
                        "capability": a.compensation_capability} for a in manual]},
            actor=worker_id,
        )
    elif failed_comp:
        _transition_wf(session, wf, "PARTIALLY_COMPENSATED", worker_id,
                       f"{len(failed_comp)} compensation(s) failed")
    else:
        _transition_wf(session, wf, "COMPENSATED", worker_id, "all effects undone+verified")
    session.commit()
    return True


def _pump(session, workflow_id: int, worker_id: str, actor: str) -> tuple[bool, str]:
    wf = session.get(Workflow, workflow_id)
    if wf is None:
        raise ConnectorError("NOT_FOUND", f"workflow {workflow_id} not found")
    if wf.state in WF_TERMINAL or wf.state == "CANCELLED":
        return False, wf.state
    org = session.get(Organization, wf.org_id)
    if wf.state == "READY":
        _transition_wf(session, wf, "RUNNING", worker_id, "execution started")
        session.commit()
        return True, wf.state
    if wf.state in ("RUNNING", "RETRYING"):
        progressed = _pump_forward(session, wf, org, worker_id, actor)
        return progressed, wf.state
    if wf.state == "COMPENSATING":
        return _pump_compensation(session, wf, org, worker_id), wf.state
    return False, wf.state


def execute_workflow_sync(session_factory, workflow_id: int, worker_id: str = "worker-1",
                          actor: str = "system", max_iterations: int = 1000) -> str:
    """Run a workflow until it reaches a terminal state. Returns that state."""
    for _ in range(max_iterations):
        session = session_factory()
        try:
            progressed, state = _pump(session, workflow_id, worker_id, actor)
            session.commit()
        finally:
            session.close()
        if state in WF_TERMINAL or not progressed:
            return state
    return state


def reconcile_on_startup(session_factory, worker_id: str) -> dict:
    """Recover in-flight work after a crash. Returns stats. Never blindly retries.

    Per-state audit (P0-REC-02):
    - CLAIMED with an expired lease -> PENDING (no effect ever started).
    - EXECUTING with an expired lease -> UNKNOWN_OUTCOME (effect uncertain;
      the forward pump reconciles it with verification before any
      re-execution). Fresh leases are left alone in both cases.
    - SUCCEEDED / VERIFYING with a stale lease -> verified in place
      (PRESENT -> VERIFIED with no re-execution, ABSENT_CONFIRMED -> FAILED
      plus a retry when attempts remain, INDETERMINATE -> left VERIFYING
      for a later pass). A blind FAILED here would permit an unsafe retry
      of a possibly-present effect.
    - UNKNOWN_OUTCOME -> deliberately left for the pump, which reconciles
      every UNKNOWN with verification before any forward progress; counted
      as reconcile_pending. Never force-resolved.
    - COMPENSATING with a stale lease -> forward effect re-read
      (ABSENT_CONFIRMED -> COMPENSATED, PRESENT -> COMPENSATION_FAILED so
      the undo is retried, INDETERMINATE -> left COMPENSATING).
    """
    session = session_factory()
    stats = {"requeued": 0, "unknown": 0, "failed": 0, "comp_failed": 0,
             "verified": 0, "compensated": 0, "deferred": 0,
             "reconcile_pending": 0, "live": 0}
    try:
        now = utcnow()
        for action in session.scalars(
            select(ActionRun).where(ActionRun.state == "CLAIMED",
                                    ActionRun.lease_expires_at < now)
        ).all():
            wf = session.get(Workflow, action.workflow_id)
            transition_action(session, wf, action, "PENDING", worker_id,
                            "startup: lease expired")
            action.lease_owner = ""
            stats["requeued"] += 1
        for action in session.scalars(
            select(ActionRun).where(ActionRun.state == "EXECUTING",
                                    ActionRun.lease_expires_at < now)
        ).all():
            wf = session.get(Workflow, action.workflow_id)
            transition_action(session, wf, action, "UNKNOWN_OUTCOME", worker_id,
                            "startup: owner crashed mid-effect")
            stats["unknown"] += 1
        session.commit()
        for action in session.scalars(
            select(ActionRun).where(ActionRun.state.in_(["SUCCEEDED", "VERIFYING"]))
        ).all():
            if not _lease_is_stale(action, utcnow()):
                stats["live"] += 1
                continue
            wf = session.get(Workflow, action.workflow_id)
            org = session.get(Organization, wf.org_id) if wf is not None else None
            if wf is None or org is None:
                stats["deferred"] += 1
                continue
            outcome = _resume_interrupted_verification(session, wf, org, action, worker_id)
            if outcome is VerificationOutcome.PRESENT:
                stats["verified"] += 1
            elif outcome is VerificationOutcome.ABSENT_CONFIRMED:
                stats["failed"] += 1
            else:
                stats["deferred"] += 1
        stats["reconcile_pending"] = len(session.scalars(
            select(ActionRun).where(ActionRun.state == "UNKNOWN_OUTCOME")
        ).all())
        for action in session.scalars(
            select(ActionRun).where(ActionRun.state == "COMPENSATING")
        ).all():
            if not _lease_is_stale(action, utcnow()):
                stats["live"] += 1
                continue
            wf = session.get(Workflow, action.workflow_id)
            org = session.get(Organization, wf.org_id) if wf is not None else None
            if wf is None or org is None:
                stats["deferred"] += 1
                continue
            outcome = _resume_interrupted_compensation(session, wf, org, action, worker_id)
            if outcome is VerificationOutcome.ABSENT_CONFIRMED:
                stats["compensated"] += 1
            elif outcome is VerificationOutcome.PRESENT:
                stats["comp_failed"] += 1
            else:
                stats["deferred"] += 1
        session.commit()
        return stats
    finally:
        session.close()


def resume_workflow_sync(session_factory, workflow_id: int,
                         worker_id: str = "worker-1", actor: str = "system",
                         max_iterations: int = 1000) -> dict:
    """Resume one interrupted workflow after a restart. Returns state+stats.

    Per-action recovery scoped to this workflow (mirrors reconcile_on_startup
    but for a single workflow, so POST /workflows/{id}/resume can recover
    without touching other tenants' work):
    - CLAIMED with an expired lease -> PENDING (no effect ever started).
    - EXECUTING with an expired lease -> UNKNOWN_OUTCOME (uncertain).
    - SUCCEEDED/VERIFYING with a stale lease -> verified in place via
      _resume_interrupted_verification (never re-executed).
    - UNKNOWN_OUTCOME with a stale lease -> _reconcile_unknown; PRESENT ->
      VERIFIED, ABSENT_CONFIRMED -> FAILED (+retry), INDETERMINATE -> stays
      UNKNOWN_OUTCOME with a backoff event (action.reconcile_deferred);
      never force-resolved to FAILED or VERIFIED.
    - COMPENSATING with a stale lease -> _resume_interrupted_compensation.
    Fresh leases are left alone (counted as live).
    After recovery the normal pump runs to completion (or honest deferral).
    """
    stats = {"requeued": 0, "unknown": 0, "failed": 0, "comp_failed": 0,
             "verified": 0, "compensated": 0, "deferred": 0,
             "reconcile_pending": 0, "live": 0}
    session = session_factory()
    try:
        wf = session.get(Workflow, workflow_id)
        if wf is None:
            raise ConnectorError("NOT_FOUND", f"workflow {workflow_id} not found")
        if wf.state in WF_TERMINAL or wf.state == "CANCELLED":
            return {"state": wf.state, "stats": stats, "resumed": False}
        org = session.get(Organization, wf.org_id)
        if org is None:
            return {"state": wf.state, "stats": stats, "resumed": False}
        now = utcnow()
        for action in session.scalars(
            select(ActionRun).where(
                ActionRun.workflow_id == wf.id, ActionRun.state == "CLAIMED",
                ActionRun.lease_expires_at < now)
        ).all():
            transition_action(session, wf, action, "PENDING", worker_id,
                            "resume: lease expired")
            action.lease_owner = ""
            action.lease_expires_at = None
            stats["requeued"] += 1
        for action in session.scalars(
            select(ActionRun).where(
                ActionRun.workflow_id == wf.id, ActionRun.state == "EXECUTING",
                ActionRun.lease_expires_at < now)
        ).all():
            transition_action(session, wf, action, "UNKNOWN_OUTCOME", worker_id,
                            "resume: owner crashed mid-effect")
            stats["unknown"] += 1
        session.commit()
        for action in session.scalars(
            select(ActionRun).where(
                ActionRun.workflow_id == wf.id,
                ActionRun.state.in_(["SUCCEEDED", "VERIFYING"]))
        ).all():
            if not _lease_is_stale(action, utcnow()):
                stats["live"] += 1
                continue
            outcome = _resume_interrupted_verification(
                session, wf, org, action, worker_id)
            if outcome is VerificationOutcome.PRESENT:
                stats["verified"] += 1
            elif outcome is VerificationOutcome.ABSENT_CONFIRMED:
                stats["failed"] += 1
            else:
                stats["deferred"] += 1
        for action in session.scalars(
            select(ActionRun).where(
                ActionRun.workflow_id == wf.id,
                ActionRun.state == "UNKNOWN_OUTCOME")
        ).all():
            if not _lease_is_stale(action, utcnow()):
                stats["live"] += 1
                continue
            outcome = _reconcile_unknown(session, wf, org, action, worker_id)
            if outcome is VerificationOutcome.PRESENT:
                stats["verified"] += 1
            elif outcome is VerificationOutcome.ABSENT_CONFIRMED:
                stats["failed"] += 1
            else:
                stats["deferred"] += 1
                delay = _backoff_delay(action)
                append_event(
                    session, wf.id, wf.org_id, "action.reconcile_deferred",
                    {"seq": action.seq, "action_type": action.action_type,
                     "wait_s": round(delay, 2),
                     "reason": "stale UNKNOWN deferred with backoff; "
                               "never force-resolved"},
                    actor=worker_id,
                )
                session.commit()
        for action in session.scalars(
            select(ActionRun).where(
                ActionRun.workflow_id == wf.id, ActionRun.state == "COMPENSATING")
        ).all():
            if not _lease_is_stale(action, utcnow()):
                stats["live"] += 1
                continue
            outcome = _resume_interrupted_compensation(
                session, wf, org, action, worker_id)
            if outcome is VerificationOutcome.ABSENT_CONFIRMED:
                stats["compensated"] += 1
            elif outcome is VerificationOutcome.PRESENT:
                stats["comp_failed"] += 1
            else:
                stats["deferred"] += 1
        stats["reconcile_pending"] = len(session.scalars(
            select(ActionRun).where(
                ActionRun.workflow_id == wf.id,
                ActionRun.state == "UNKNOWN_OUTCOME")
        ).all())
        # Crash between the two commits of the final check can persist a
        # workflow-level VERIFYING with all actions already done: complete it.
        wf_now = session.get(Workflow, workflow_id)
        if wf_now is not None and wf_now.state == "VERIFYING":
            acts = session.scalars(
                select(ActionRun).where(ActionRun.workflow_id == wf.id)
            ).all()
            if acts and all(a.state in ACT_FORWARD_DONE for a in acts):
                verified = sum(1 for a in acts if a.state == "VERIFIED")
                _transition_wf(session, wf_now, "COMPLETED", worker_id,
                               f"resume: final check recovered "
                               f"({verified}/{len(acts)} verified)")
                session.commit()
        session.commit()
    finally:
        session.close()
    final = execute_workflow_sync(
        session_factory, workflow_id, worker_id=worker_id, actor=actor,
        max_iterations=max_iterations)
    return {"state": final, "stats": stats, "resumed": True}
