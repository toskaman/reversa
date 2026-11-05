"""Recovery Proof Engine v1: read-only Recovery Manifest evaluator.

Implements docs/product/recovery-proof-engine.md sections 0-6: tri-state
effect claims (PRESENT/ABSENT/UNKNOWN), verdict truth table, confidence
C0-C7, and refusal codes R4_NOT_TERMINAL / R5_CANCELLED_RUN plus
in-manifest R_CAPABILITY_REFUSAL / R_EXTERNAL_MODIFICATION.

Read-only by construction: this module only SELECTs (workflows, actions,
events, demo-store rows). It never appends events, never retries, never
compensates, and never calls connector execute/verify/compensate. Every
claim derives from observed DB state: recorded evidence transitions plus
current demo-store rows.

Verdict honesty: recorded transitions establish a claim; current rows only
re-verify (a mismatch downgrades to a divergence); nothing is inferred —
a missing record stays UNKNOWN/INDETERMINATE however favourable the store.

Endpoint: GET /api/v1/workflows/{wf_id}/recovery-manifest
"""

from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from ..auth import OrgCtx, get_current_org, get_session
from ..connectors.services import SERVICE_STORES, DemoStore
from ..engine.saga import WF_TERMINAL
from ..evidence import verify_chain
from ..models import ActionRun, Event, Workflow, utcnow

router = APIRouter(prefix="/api/v1", tags=["recovery"])

MANIFEST_VERSION = "1.0"
GENERATOR = "reversa-rpe/1.0"

MANUAL_CAPS = frozenset({"IRREVERSIBLE", "MANUAL_ONLY", "UNKNOWN"})
COMP_STATES = frozenset({
    "COMPENSATION_PENDING", "COMPENSATING", "COMPENSATED", "COMPENSATION_FAILED",
})
# Terminal states the RPE can evaluate. CANCELLED is terminal in the engine
# but the spec authorises no confidence level for it, so v1 refuses it (R5)
# rather than mislabelling a cancelled run.
EVALUATABLE_TERMINAL = frozenset({
    "COMPLETED", "COMPENSATED", "PARTIALLY_COMPENSATED", "MANUAL_REQUIRED", "FAILED",
})

# Trail states proving an effect may exist (spec section 2.3, FAILED bullet).
_MAY_HAVE_EFFECT = frozenset({"SUCCEEDED", "VERIFYING", "UNKNOWN_OUTCOME"})
# Error-text markers of an inconclusive failure (partial/uncertain effect).
_UNCERTAIN_MARKERS = (
    "uncertain", "unknown", "verify error", "timeout", "timed out",
    "reconcile deferred", "resume deferred", "indeterminate",
)

ReadResource = Callable[[str, int], dict | None]


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except (ValueError, TypeError):
        return {}


def _forward_output(output: Any) -> dict:
    """Strip evaluator-internal keys; unwrap verify-failure originals."""
    if not isinstance(output, dict):
        return {}
    failure = output.get("_failure")
    if isinstance(failure, dict) and isinstance(failure.get("output"), dict):
        return failure["output"]
    return {k: v for k, v in output.items() if not str(k).startswith("_")}


def _extract_refs(forward: dict, connector_id: str) -> list[dict]:
    """Resource refs from a forward output. Shapes observed in demo stores:
    {"resource": ref} for single creates, {"users": [ref, ...]} for
    provision_users. Anything else (validate/core outputs) carries no refs."""
    refs: list[dict] = []
    default_store = connector_id[5:] if connector_id.startswith("demo-") else ""
    resource = forward.get("resource")
    if isinstance(resource, dict):
        refs.append({"store": default_store, **resource})
    users = forward.get("users")
    if isinstance(users, list):
        for ref in users:
            if isinstance(ref, dict):
                refs.append({"store": default_store, **ref})
    return refs


def _ref_id(ref: dict) -> int | None:
    rid = ref.get("id")
    return rid if isinstance(rid, int) and not isinstance(rid, bool) else None


def _comp_attempts_stored(output: Any) -> int:
    if isinstance(output, dict):
        try:
            return int(output.get("_comp_attempts", 0))
        except (TypeError, ValueError):
            return 0
    return 0


def _event_ref(seq: int | None) -> str | None:
    return f"event seq {seq}" if seq else None


class _TrailIndex:
    """Per-action transition trails + typed-event lookups over one timeline."""

    def __init__(self, events: list[dict]):
        self.seqs = {e["seq"] for e in events}
        self.by_seq: dict[int, list[dict]] = {}
        for e in events:
            if e["type"] == "action.state" and isinstance(e["payload"], dict):
                seq = e["payload"].get("seq")
                if isinstance(seq, int):
                    self.by_seq.setdefault(seq, []).append(e)
        self.by_seq = {k: sorted(v, key=lambda e: e["seq"])
                       for k, v in self.by_seq.items()}
        self.events = events

    def trail(self, seq: int) -> list[str]:
        return [str(e["payload"].get("to", "")) for e in self.by_seq.get(seq, [])]

    def last_to(self, seq: int, to_state: str) -> dict | None:
        cands = [e for e in self.by_seq.get(seq, [])
                 if e["payload"].get("to") == to_state]
        return cands[-1] if cands else None

    def last_for(self, seq: int) -> dict | None:
        rows = self.by_seq.get(seq, [])
        return rows[-1] if rows else None

    def manual_required_event(self, seq: int) -> dict | None:
        for e in self.events:
            if (e["type"] == "compensation.manual_required"
                    and isinstance(e["payload"], dict)
                    and e["payload"].get("seq") == seq):
                return e
        for e in self.events:
            if e["type"] == "workflow.manual_required":
                return e
        return None

    @property
    def compensation_started(self) -> bool:
        return any(e["type"] == "compensation.started" for e in self.events)


def _check_refs_absent(refs: list[dict], read: ReadResource,
                       forward: dict) -> tuple[str, dict | None]:
    """Return ("absent"|"present"|"unidentifiable", witness_row).

    Absent = every identifiable ref is row-gone or inactive. The
    assign_manager effect ("workspace.manager set") is undone while its row
    stays active, so an active row whose manager equals the recorded
    pre-state also counts as absent.
    """
    identifiable = [r for r in refs if r.get("store") and _ref_id(r) is not None]
    if not identifiable:
        return "unidentifiable", None
    for ref in identifiable:
        row = read(ref["store"], _ref_id(ref))  # type: ignore[arg-type]
        if row is None or row.get("status") != "active":
            continue
        if ("previous_manager" in forward
                and row.get("data", {}).get("manager") == forward["previous_manager"]):
            continue
        return "present", row
    return "absent", None


def _check_refs_present(refs: list[dict], read: ReadResource) -> tuple[str, dict | None]:
    """Return ("present"|"absent"|"unidentifiable", witness_or_missing_ref)."""
    identifiable = [r for r in refs if r.get("store") and _ref_id(r) is not None]
    if not identifiable:
        return "unidentifiable", None
    for ref in identifiable:
        row = read(ref["store"], _ref_id(ref))  # type: ignore[arg-type]
        if row is None or row.get("status") != "active":
            return "absent", ref
    return "present", None


def evaluate_recovery(
    *,
    workflow_id: int,
    org_id: int,
    workflow_state: str,
    actions: list[dict],
    events: list[dict],
    chain: dict,
    read_resource: ReadResource,
    final_resources: list[dict],
    generated_at: str,
) -> dict:
    """Pure manifest evaluator. All inputs are observed state; no I/O except
    the injected read_resource probe (DemoStore reads in production)."""
    idx = _TrailIndex(events)
    comp_started = idx.compensation_started
    entries: list[dict] = []
    manual_items: list[dict] = []
    refusals: list[dict] = []
    divergences: list[dict] = []
    indeterminates: list[dict] = []
    compensations: list[dict] = []
    created_resources: list[dict] = []

    for action in sorted(actions, key=lambda a: a["seq"]):
        seq = action["seq"]
        action_type = action["action_type"]
        connector_id = action["connector_id"]
        state = action["state"]
        capability = action.get("compensation_capability", "UNKNOWN")
        output = action.get("output", {})
        error = action.get("error", "") or ""
        forward = _forward_output(output)
        refs = _extract_refs(forward, connector_id)
        trail = idx.trail(seq)

        # ---- required (spec 2.3) ----
        if state in COMP_STATES:
            required = "compensation"
        elif state == "VERIFIED":
            required = "compensation" if comp_started else "forward_success"
        elif state in ("SKIPPED", "FAILED"):
            required = "none"
        else:
            required = "none"

        effect: str | None = None
        verdict: str | None = None
        verification: dict = {"method": "none", "event_ref": None,
                              "observed_at": None}
        compensation: dict | None = None
        note = ""

        def _observe(ts_event: dict | None, method: str) -> None:
            verification["method"] = method
            verification["event_ref"] = _event_ref(
                ts_event["seq"] if ts_event else None)
            verification["observed_at"] = ts_event["ts"] if ts_event else None

        # ---- effect state per action state ----
        if state == "COMPENSATED":
            comp_ev = idx.last_to(seq, "COMPENSATED")
            stored_attempts = _comp_attempts_stored(output)
            if comp_ev is None:
                effect = "UNKNOWN"
                note = "no compensation record in evidence"
            elif comp_ev["payload"].get("note") == "noop (read-only)":
                effect = "ABSENT"
                _observe(comp_ev, "noop_proof")
                compensation = {"capability": capability,
                                "attempts": stored_attempts + 1,
                                "proof_ref": _event_ref(comp_ev["seq"]),
                                "absence_method": "noop_proof"}
            else:
                absent, witness = _check_refs_absent(refs, read_resource, forward)
                _observe(comp_ev, "connector_verify")
                compensation = {"capability": capability,
                                "attempts": stored_attempts + 1,
                                "proof_ref": _event_ref(comp_ev["seq"]),
                                "absence_method": "verify_absent"}
                if absent == "present":
                    effect = "PRESENT"
                    assert witness is not None
                    divergences.append({
                        "seq": seq, "action_type": action_type,
                        "resource": {"store": witness.get("store", ""),
                                     "id": witness.get("id"),
                                     "kind": witness.get("kind"),
                                     "name": witness.get("name")},
                        "expected": "ABSENT",
                        "observed": f"PRESENT (status={witness.get('status')}, "
                                    f"version={witness.get('version')})",
                        "detail": "effect still present after recorded compensation",
                    })
                elif absent == "absent":
                    effect = "ABSENT"
                else:
                    # Recorded absence stands: the COMPENSATED transition is
                    # the verify-after-compensate proof (spec 2.1 burden).
                    effect = "ABSENT"
                    note = ("resource unidentifiable from stored output; "
                            f"absence per compensation record {_event_ref(comp_ev['seq'])}")
        elif state == "COMPENSATION_FAILED":
            fail_ev = idx.last_to(seq, "COMPENSATION_FAILED")
            attempts = _comp_attempts_stored(output)
            refused_external = error.startswith("PRECONDITION_FAILED")
            if fail_ev is None:
                effect = "UNKNOWN"
                note = "no compensation-failure record in evidence"
            else:
                absent, witness = _check_refs_absent(refs, read_resource, forward)
                _observe(fail_ev, "connector_verify")
                compensation = {"capability": capability, "attempts": attempts,
                                "proof_ref": _event_ref(fail_ev["seq"]),
                                "absence_method": "verify_absent"}
                if absent == "present":
                    effect = "PRESENT"
                    assert witness is not None
                    divergences.append({
                        "seq": seq, "action_type": action_type,
                        "resource": {"store": witness.get("store", ""),
                                     "id": witness.get("id"),
                                     "kind": witness.get("kind"),
                                     "name": witness.get("name")},
                        "expected": "ABSENT",
                        "observed": f"PRESENT (status={witness.get('status')}, "
                                    f"version={witness.get('version')})",
                        "detail": f"compensation failed ({error[:120]}); effect remains",
                    })
                elif absent == "absent":
                    effect = "ABSENT"
                    note = "effect absent despite recorded compensation failure"
                elif refused_external or error.startswith("COMPENSATION_NOT_CONFIRMED"):
                    effect = "PRESENT"  # refused/still-present: undo never took
                else:
                    effect = "UNKNOWN"  # verifier error proves nothing
                    note = f"absence check inconclusive ({error[:120]})"
            if refused_external:
                man_ev = idx.manual_required_event(seq) or fail_ev
                manual_items.append({
                    "seq": seq, "action_type": action_type,
                    "connector_id": connector_id, "capability": capability,
                    "cause": "external_modification",
                    "effect_state": effect or "UNKNOWN",
                    "reason": (f"{action_type} target changed incompatibly; "
                               f"auto-undo refused ({error[:160]})"),
                    "suggested_action": (
                        f"Review the external change on the {action_type} target "
                        f"(seq {seq}), reconcile it, then re-run evaluation."),
                    "event_ref": _event_ref(man_ev["seq"] if man_ev else None),
                })
        elif state == "VERIFIED" and comp_started:
            ver_ev = idx.last_to(seq, "VERIFIED")
            if ver_ev is None:
                effect = "UNKNOWN"
                note = "no verification record in evidence"
            else:
                present, _ = _check_refs_present(refs, read_resource)
                _observe(ver_ev, "connector_verify")
                man_ev = idx.manual_required_event(seq)
                compensation = {"capability": capability, "attempts": 0,
                                "proof_ref": _event_ref(
                                    man_ev["seq"] if man_ev else None),
                                "absence_method": "verify_absent"}
                if present == "absent":
                    effect = "ABSENT"
                else:
                    effect = "PRESENT"  # verified and never undone
                if capability in MANUAL_CAPS:
                    manual_items.append({
                        "seq": seq, "action_type": action_type,
                        "connector_id": connector_id, "capability": capability,
                        "cause": "capability_refusal",
                        "effect_state": effect,
                        "reason": (f"{action_type} is {capability}: auto-undo refused"),
                        "suggested_action": (
                            f"Manually reverse the {action_type} effect (seq {seq}), "
                            "then re-run evaluation."),
                        "event_ref": _event_ref(man_ev["seq"] if man_ev else None),
                    })
                elif effect == "PRESENT":
                    divergences.append({
                        "seq": seq, "action_type": action_type,
                        "resource": None, "expected": "ABSENT",
                        "observed": "PRESENT",
                        "detail": ("compensatable action left VERIFIED in a "
                                   "compensated run; engine did not queue it"),
                    })
        elif state == "VERIFIED":
            ver_ev = idx.last_to(seq, "VERIFIED")
            if ver_ev is None:
                effect = "UNKNOWN"
                note = "no verification record in evidence"
            else:
                present, missing = _check_refs_present(refs, read_resource)
                _observe(ver_ev, "connector_verify")
                if present == "absent":
                    effect = "ABSENT"
                    assert isinstance(missing, dict)
                    row = read_resource(missing.get("store", ""),
                                        _ref_id(missing) or -1)
                    divergences.append({
                        "seq": seq, "action_type": action_type,
                        "resource": {"store": missing.get("store", ""),
                                     "id": _ref_id(missing),
                                     "kind": missing.get("kind"),
                                     "name": missing.get("name")},
                        "expected": "PRESENT",
                        "observed": ("deleted" if row is None
                                     else f"status={row.get('status')}"),
                        "detail": "effect lost after recorded forward success",
                    })
                else:
                    # "present" by store check, or "unidentifiable" (read-only
                    # steps carry no refs): the VERIFIED record proves presence.
                    effect = "PRESENT"
        elif state == "SKIPPED":
            skip_ev = idx.last_to(seq, "SKIPPED")
            if skip_ev is None:
                effect = "UNKNOWN"
                note = "no skip record in evidence"
            else:
                _observe(skip_ev, "none")
                present, witness = _check_refs_present(refs, read_resource)
                if present == "present":
                    effect = "PRESENT"  # engine-bug path (spec 2.2)
                    divergences.append({
                        "seq": seq, "action_type": action_type,
                        "resource": None, "expected": "ABSENT",
                        "observed": "PRESENT",
                        "detail": "skipped action left an effect; engine bug",
                    })
                else:
                    effect = "ABSENT"
        elif state == "FAILED":
            fail_ev = idx.last_to(seq, "FAILED")
            _observe(fail_ev, "none")
            if any(t in _MAY_HAVE_EFFECT for t in trail):
                absent, witness = _check_refs_absent(refs, read_resource, forward)
                if absent == "present":
                    effect = "PRESENT"
                    assert witness is not None
                    divergences.append({
                        "seq": seq, "action_type": action_type,
                        "resource": {"store": witness.get("store", ""),
                                     "id": witness.get("id"),
                                     "kind": witness.get("kind"),
                                     "name": witness.get("name")},
                        "expected": "ABSENT",
                        "observed": f"PRESENT (status={witness.get('status')})",
                        "detail": "failed action left an effect behind",
                    })
                elif absent == "absent":
                    effect = "ABSENT"
                elif ("_failure" in forward or isinstance(output, dict)
                      and "_failure" in output) and not _is_uncertain(error):
                    effect = "ABSENT"  # certain failure, nothing observed
                elif not _is_uncertain(error) and not refs:
                    effect = "ABSENT"
                else:
                    effect = "UNKNOWN"
                    note = f"failure record shows a possible partial effect ({error[:120]})"
            elif fail_ev is None:
                effect = "UNKNOWN"
                note = "no failure record in evidence"
            elif _is_uncertain(error):
                effect = "UNKNOWN"
                note = f"failure is inconclusive ({error[:120]})"
            else:
                effect = "ABSENT"  # certain failure before any effect
        else:
            last = idx.last_for(seq)
            _observe(last, "none")
            effect = "UNKNOWN"
            note = (f"action left in non-terminal state {state} "
                    "in a terminal workflow")

        assert effect in ("PRESENT", "ABSENT", "UNKNOWN")
        # ---- verdict (spec 2.2 truth table) ----
        if effect == "UNKNOWN":
            verdict = "INDETERMINATE"
        elif required == "forward_success":
            verdict = "RESTORED" if effect == "PRESENT" else "NOT_RESTORED"
        elif required == "compensation":
            verdict = "RESTORED" if effect == "ABSENT" else "NOT_RESTORED"
        else:
            verdict = "RESTORED" if effect == "ABSENT" else "NOT_RESTORED"

        entry: dict = {
            "seq": seq, "action_type": action_type,
            "connector_id": connector_id, "action_state": state,
            "required": required, "effect_state": effect, "verdict": verdict,
            "verification": verification,
            "forward_attempts": action.get("attempt", 0),
        }
        if compensation is not None:
            entry["compensation"] = compensation
        if note:
            entry["note"] = note
        entries.append(entry)

        if effect == "UNKNOWN":
            indeterminates.append({
                "seq": seq, "action_type": action_type,
                "reason": note or "effect state unprovable from observed state",
                "event_ref": verification["event_ref"],
            })

        # ---- per-action resource + compensation records ----
        if refs:
            created_resources.append({
                "seq": seq, "action_type": action_type,
                "refs": [
                    {
                        "store": r.get("store", ""),
                        "kind": r.get("kind"), "name": r.get("name"),
                        "id": _ref_id(r), "version_at_creation": r.get("version"),
                        "current": _current_of(r, read_resource),
                    }
                    for r in refs
                ],
            })
        if required == "compensation" or "COMPENSATING" in trail:
            if state == "COMPENSATED" and compensation is not None and compensation.get(
                    "absence_method") == "noop_proof":
                result = "noop"
            elif state == "COMPENSATED":
                result = "compensated"
            elif state == "COMPENSATION_FAILED":
                result = "failed"
            elif state == "VERIFIED":
                result = "refused"
            else:
                result = "incomplete"
            compensations.append({
                "seq": seq, "action_type": action_type,
                "connector_id": connector_id, "capability": capability,
                "attempts": (compensation or {}).get("attempts", 0),
                "result": result,
                "proof_ref": (compensation or {}).get("proof_ref"),
                "detail": (note or error[:160] or result),
            })

    # ---- refusals (one per intelligent refusal behind a manual item) ----
    for item in manual_items:
        refusals.append({
            "code": ("R_EXTERNAL_MODIFICATION"
                     if item["cause"] == "external_modification"
                     else "R_CAPABILITY_REFUSAL"),
            "seq": item["seq"],
            "reason": item["reason"],
            "event_ref": item["event_ref"],
        })

    restored = sum(1 for e in entries if e["verdict"] == "RESTORED")
    not_restored = sum(1 for e in entries if e["verdict"] == "NOT_RESTORED")
    indet = sum(1 for e in entries if e["verdict"] == "INDETERMINATE")
    compensations_run = sum(
        1 for a in actions
        if a["state"] in ("COMPENSATED", "COMPENSATION_FAILED")
        or "COMPENSATING" in idx.trail(a["seq"]))
    summary = {
        "actions_total": len(entries), "restored": restored,
        "not_restored": not_restored, "indeterminate": indet,
        "compensations_run": compensations_run,
        "manual_items": len(manual_items), "refusals": len(refusals),
    }

    # ---- C2 self-check: refs resolve, table holds, counts match ----
    refs_ok = True
    for e in entries:
        candidates = [e["verification"].get("event_ref")]
        if "compensation" in e:
            candidates.append(e["compensation"].get("proof_ref"))
        for ref in candidates:
            if ref is None or not _ref_resolves(ref, idx.seqs):
                refs_ok = False
    for item in manual_items:
        if item["event_ref"] is None or not _ref_resolves(item["event_ref"], idx.seqs):
            refs_ok = False
    table_ok = all(_table_holds(e) for e in entries)
    counts_ok = (
        summary["actions_total"] == len(entries)
        and summary["restored"] + summary["not_restored"]
        + summary["indeterminate"] == len(entries)
        and summary["manual_items"] == len(manual_items)
        and summary["refusals"] == len(refusals))
    self_consistent = refs_ok and table_ok and counts_ok

    # ---- confidence (spec 4.2 decision procedure, first match wins) ----
    unknowns = sum(1 for e in entries if e["effect_state"] == "UNKNOWN")
    exhausted = [e for e in entries
                 if e["action_state"] == "COMPENSATION_FAILED"
                 and e["verdict"] == "NOT_RESTORED"
                 and (e.get("compensation") or {}).get("attempts", 0) >= 3]
    all_restored = bool(entries) and all(e["verdict"] == "RESTORED" for e in entries)
    evaluated = {
        "workflow_state": workflow_state,
        "chain_valid": bool(chain.get("valid")),
        "unknowns": unknowns,
        "refs_resolve": refs_ok,
        "table_holds": table_ok,
        "counts_match": counts_ok,
        "manual_items": len(manual_items),
        "exhausted_compensations": len(exhausted),
        "compensation_started": comp_started,
        "all_restored": all_restored,
    }
    if not chain.get("valid"):
        rule, confidence = "C0", "INDETERMINATE"
        decision = "evidence chain invalid; no record can be trusted"
    elif unknowns:
        rule, confidence = "C1", "INDETERMINATE"
        decision = f"{unknowns} effect(s) unproven; one unknown poisons the claim"
    elif not self_consistent:
        rule, confidence = "C2", "INDETERMINATE"
        decision = "manifest self-check failed (refs/table/counts)"
    elif manual_items:
        rule, confidence = "C3", "MANUAL_REQUIRED"
        decision = f"{len(manual_items)} known item(s) need a human"
    elif exhausted:
        rule, confidence = "C4", "PARTIAL"
        decision = f"{len(exhausted)} compensation(s) exhausted without human blockers"
    elif comp_started and all_restored:
        rule, confidence = "C5", "VERIFIED_WITH_COMPENSATION"
        decision = "every completed effect was undone and proven gone"
    elif not comp_started and all_restored:
        rule, confidence = "C6", "VERIFIED"
        decision = "nothing broke; every required effect is proven in place"
    elif all_restored and not comp_started:
        rule, confidence = "C7", "VERIFIED"  # unreachable; kept for spec parity
        decision = "fallthrough: all restored, no compensation ran"
    else:
        rule, confidence = "C7", "INDETERMINATE"
        decision = "fallthrough: non-restored effects without manual/exhausted cause"

    created_ids = {(r.get("store"), _ref_id(r))
                   for cr in created_resources for r in cr["refs"]}
    initial_resources = [r for r in final_resources
                         if (r.get("store"), r.get("id")) not in created_ids]

    return {
        "manifest_version": MANIFEST_VERSION,
        "workflow_id": workflow_id,
        "org_id": org_id,
        "generated_at": generated_at,
        "generator": GENERATOR,
        "recovery_confidence": confidence,
        "confidence_criteria": {"rule": rule, "decision": decision,
                                "evaluated": evaluated},
        "chain": chain,
        "summary": summary,
        "actions": entries,
        "manual_items": manual_items,
        "refusals": refusals,
        "initial_resources": initial_resources,
        "created_resources": created_resources,
        "final_resources": final_resources,
        "compensations": compensations,
        "divergences": divergences,
        "indeterminate": indeterminates,
    }


def _is_uncertain(error: str) -> bool:
    low = (error or "").lower()
    return any(m in low for m in _UNCERTAIN_MARKERS)


def _ref_resolves(ref: str, seqs: set[int]) -> bool:
    try:
        return int(str(ref).removeprefix("event seq ")) in seqs
    except (ValueError, AttributeError):
        return False


def _table_holds(entry: dict) -> bool:
    required, effect, verdict = (entry["required"], entry["effect_state"],
                                 entry["verdict"])
    if effect == "UNKNOWN":
        return verdict == "INDETERMINATE"
    if required == "forward_success":
        return verdict == ("RESTORED" if effect == "PRESENT" else "NOT_RESTORED")
    if required == "compensation":
        return verdict == ("RESTORED" if effect == "ABSENT" else "NOT_RESTORED")
    return verdict == ("RESTORED" if effect == "ABSENT" else "NOT_RESTORED")


def _current_of(ref: dict, read: ReadResource) -> dict | None:
    if not ref.get("store") or _ref_id(ref) is None:
        return None
    row = read(ref["store"], _ref_id(ref))  # type: ignore[arg-type]
    if row is None:
        return None
    return {"status": row.get("status"), "version": row.get("version")}


def _store_reader(store: str, resource_id: int) -> dict | None:
    row = DemoStore(store).get(resource_id)
    if row is None:
        return None
    return {"store": store, **row}


@router.get("/workflows/{wf_id}/recovery-manifest")
def get_recovery_manifest(wf_id: int, org: OrgCtx = Depends(get_current_org),
                          session=Depends(get_session)):
    """Evaluate and return the Recovery Manifest (read-only)."""
    wf = session.get(Workflow, wf_id)
    if wf is None or wf.org_id != org.org_id:
        raise HTTPException(status_code=404, detail="workflow not found")
    if wf.state not in WF_TERMINAL:
        # Spec 2.3 / refusal R4: no manifest for non-terminal workflows.
        raise HTTPException(status_code=409, detail={
            "code": "R4_NOT_TERMINAL", "workflow_state": wf.state,
            "reason": (f"workflow {wf_id} is {wf.state}; the Recovery Proof Engine "
                       "only evaluates terminal workflows"),
            "retryable": False})
    if wf.state not in EVALUATABLE_TERMINAL:
        raise HTTPException(status_code=409, detail={
            "code": "R5_CANCELLED_RUN", "workflow_state": wf.state,
            "reason": (f"workflow {wf_id} is {wf.state}; no confidence level "
                       "is defined for cancelled runs"),
            "retryable": False})

    actions = [
        {"seq": a.seq, "action_type": a.action_type,
         "connector_id": a.connector_id, "state": a.state,
         "output": _parse_json(a.output_json), "error": a.error or "",
         "attempt": a.attempt,
         "compensation_capability": a.compensation_capability}
        for a in session.scalars(
            select(ActionRun).where(ActionRun.workflow_id == wf.id)
            .order_by(ActionRun.seq)).all()
    ]
    events = [
        {"seq": e.seq, "ts": e.ts.isoformat(), "type": e.type,
         "payload": _parse_json(e.payload_json)}
        for e in session.scalars(
            select(Event).where(Event.workflow_id == wf.id)
            .order_by(Event.seq)).all()
    ]
    ok, _bad_seq, message = verify_chain(session, wf.id)
    chain = {
        "valid": ok,
        "events": len(events),
        "head_hash": (session.scalars(
            select(Event.hash).where(Event.workflow_id == wf.id)
            .order_by(Event.seq.desc())).first() or "GENESIS"),
        "detail": message,
    }
    final_resources: list[dict] = []
    for store in SERVICE_STORES:
        for row in DemoStore(store).list(org.org_id):
            final_resources.append({"store": store, **row})

    manifest = evaluate_recovery(
        workflow_id=wf.id, org_id=wf.org_id, workflow_state=wf.state,
        actions=actions, events=events, chain=chain,
        read_resource=_store_reader, final_resources=final_resources,
        generated_at=utcnow().isoformat() + "Z",
    )
    # Spec 3.1: producers emit keys sorted for stable hashing.
    return Response(
        content=json.dumps(manifest, sort_keys=True, ensure_ascii=True),
        media_type="application/json",
    )
