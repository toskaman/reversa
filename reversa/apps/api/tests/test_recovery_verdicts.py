"""Mandat 06-RECOVERY (Cycle 1 V3): verdicts tri-state, chaine, coherence.

Epingle les correctifs fail-closed de l'evaluateur :
- UNKNOWN != ABSENT : un FAILED dont la trace montre un effet possible mais
  dont les refs sont perdues (ecrasees par un retry) reste UNKNOWN sauf
  preuve d'absence enregistree dans la note chainee (verify-False,
  reconcile/resume-absent).
- La note de transition chainee est authoritative : un ActionRun.error
  adouci ne peut ni effacer l'incertitude ni supprimer un refus externe.
- Les tentatives de compensation derivent de la trace chainee (une
  transition COMPENSATING par essai), pas du compteur stocke falsifiable.
- Un effet disparu sans undo enregistre (VERIFIED dans un run compense)
  emet une divergence, comme le cas forward.
- comp_started survit a la perte du marqueur compensation.started (etats
  et traces de compensation) ; la troncature de queue (marqueur terminal
  manquant sur un prefixe valide) force C0.
- verification.method reflete la preuve : connector_verify quand un
  controle live decide, none quand le record seul prouve (SKIPPED,
  FAILED certain / absence enregistree).

Fichier NOUVEAU, sans append dans les fichiers de test existants.
"""

from reversa_api.db import session_for
from reversa_api.evidence import verify_chain
from reversa_api.models import Event
from reversa_api.routes.recovery import evaluate_recovery

from .conftest import make_ready


def _base_kwargs(**overrides):
    kw = dict(workflow_id=7, org_id=1, workflow_state="FAILED",
              actions=[], events=[], chain={"valid": True, "events": 0,
                                            "head_hash": "abc", "detail": "ok"},
              read_resource=lambda store, rid: None, final_resources=[],
              generated_at="2026-11-05T12:00:00Z")
    kw.update(overrides)
    return kw


def _ev(seq, type, payload=None, note_to=None, note=None):
    body = dict(payload or {})
    if note_to is not None:
        body["to"] = note_to
    if note is not None:
        body["note"] = note
    return {"seq": seq, "ts": "2026-11-05T12:00:00Z", "type": type,
            "payload": body}


def _ref(store="crm", rid=1):
    return {"store": store, "kind": "organization", "name": "acme",
            "id": rid, "version": 1}


def _row(status="active", version=1):
    return {"id": 1, "kind": "organization", "name": "acme",
            "status": status, "version": version, "data": {}}


def _action(seq=6, state="FAILED", output=None, error="", **over):
    base = {"seq": seq, "action_type": "billing.create_profile",
            "connector_id": "demo-billing", "state": state,
            "output": {} if output is None else output,
            "error": error, "attempt": 2,
            "compensation_capability": "COMPENSATABLE"}
    base.update(over)
    return base


# ---- UNKNOWN != ABSENT : refs perdues apres une trace SUCCEEDED ----

def test_failed_succeeded_trail_with_lost_refs_stays_unknown():
    # Tentative 1 SUCCEEDED (effet possible), tentative 2 en echec execute :
    # _fail() ecrase l'output et detruit les refs d'origine. Erreur
    # certaine mais sans preuve d'absence -> UNKNOWN, pas ABSENT.
    err = "CHAOS_HTTP500: chaos (retryable=True)"
    action = _action(output={"_failure": {"code": "CHAOS_HTTP500",
                                         "retryable": True, "error": err}},
                     error=err)
    events = [
        _ev(1, "action.state", {"seq": 6}, note_to="SUCCEEDED"),
        _ev(2, "action.state", {"seq": 6}, note_to="VERIFYING"),
        _ev(3, "action.state", {"seq": 6}, note_to="FAILED", note=err),
    ]
    m = evaluate_recovery(**_base_kwargs(actions=[action], events=events))
    assert m["actions"][0]["effect_state"] == "UNKNOWN"
    assert m["actions"][0]["verdict"] == "INDETERMINATE"
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C1"


def test_failed_verify_false_record_stays_absent_without_refs():
    # Verify a retourne False (enregistre) : absence prouvee meme sans refs.
    note = "effect NOT confirmed"
    action = _action(output={"_failure": {"code": "VERIFY_FAILED",
                                         "retryable": True, "error": note}},
                     error=note)
    events = [
        _ev(1, "action.state", {"seq": 6}, note_to="SUCCEEDED"),
        _ev(2, "action.state", {"seq": 6}, note_to="VERIFYING"),
        _ev(3, "action.state", {"seq": 6}, note_to="FAILED", note=note),
    ]
    m = evaluate_recovery(**_base_kwargs(actions=[action], events=events))
    assert m["actions"][0]["effect_state"] == "ABSENT"
    assert m["actions"][0]["verdict"] == "RESTORED"


def test_failed_reconciled_absent_stays_absent_without_refs():
    # UNKNOWN_OUTCOME reconcilie absent : la note chainee prouve l'absence.
    note = "effect absent; idempotent re-execution allowed"
    action = _action(output={}, error=note)
    events = [
        _ev(1, "action.state", {"seq": 6}, note_to="UNKNOWN_OUTCOME"),
        _ev(2, "action.state", {"seq": 6}, note_to="FAILED", note=note),
    ]
    m = evaluate_recovery(**_base_kwargs(actions=[action], events=events))
    assert m["actions"][0]["effect_state"] == "ABSENT"
    assert m["actions"][0]["verdict"] == "RESTORED"


# ---- La note chainee gagne sur ActionRun.error (fail-closed) ----

def test_failed_chained_note_uncertainty_survives_softened_error():
    # error adouci ("declined") mais note chainee "timeout" -> UNKNOWN.
    action = _action(output={}, error="declined by policy")
    events = [_ev(1, "action.state", {"seq": 6}, note_to="FAILED",
                  note="timeout waiting for connector verify")]
    m = evaluate_recovery(**_base_kwargs(actions=[action], events=events))
    assert m["actions"][0]["effect_state"] == "UNKNOWN"
    assert m["confidence_criteria"]["rule"] == "C1"


def test_compensation_failed_note_only_precondition_keeps_manual():
    # error reecrit en CHAOS banal mais note chainee PRECONDITION_FAILED :
    # le refus externe et l'item manuel survivent.
    note = ("PRECONDITION_FAILED: resource 1 changed (expected v1, found "
            "v5); refusing to overwrite a newer state (comp attempt 1/3)")
    action = _action(seq=2, state="COMPENSATION_FAILED",
                     output={"resource": _ref(), "_comp_attempts": 1},
                     error="CHAOS_HTTP500: chaos (retryable=True)")
    events = [
        _ev(1, "action.state", {"seq": 2}, note_to="VERIFIED"),
        _ev(2, "compensation.started", {"queued": 1, "manual_items": 0}),
        _ev(3, "action.state", {"seq": 2}, note_to="COMPENSATION_FAILED",
            note=note),
    ]
    m = evaluate_recovery(
        **_base_kwargs(workflow_state="MANUAL_REQUIRED", actions=[action],
                       events=events,
                       read_resource=lambda store, rid: dict(_row(version=5))))
    assert m["actions"][0]["effect_state"] == "PRESENT"
    assert m["manual_items"][0]["cause"] == "external_modification"
    assert m["refusals"][0]["code"] == "R_EXTERNAL_MODIFICATION"
    assert m["confidence_criteria"]["rule"] == "C3"


def test_compensation_attempts_derive_from_chained_trail():
    # Compteur stocke falsifie a 0 mais 3 transitions COMPENSATING
    # chainees + effet present -> epuise -> C4 PARTIAL, pas C7.
    action = _action(seq=2, state="COMPENSATION_FAILED",
                     output={"resource": _ref(), "_comp_attempts": 0},
                     error="CHAOS_HTTP500: chaos (retryable=True)")
    trail = ["VERIFIED", "COMPENSATING", "COMPENSATION_FAILED",
             "COMPENSATION_PENDING", "COMPENSATING", "COMPENSATION_FAILED",
             "COMPENSATION_PENDING", "COMPENSATING", "COMPENSATION_FAILED"]
    events = [_ev(1, "compensation.started",
                  {"queued": 1, "manual_items": 0})]
    events += [_ev(i + 2, "action.state", {"seq": 2}, note_to=t)
               for i, t in enumerate(trail)]
    m = evaluate_recovery(
        **_base_kwargs(workflow_state="PARTIALLY_COMPENSATED",
                       actions=[action], events=events,
                       read_resource=lambda store, rid: dict(_row())))
    assert m["actions"][0]["compensation"]["attempts"] == 3
    assert m["confidence_criteria"]["evaluated"]["exhausted_compensations"] == 1
    assert m["recovery_confidence"] == "PARTIAL"
    assert m["confidence_criteria"]["rule"] == "C4"


# ---- Divergence : effet disparu sans undo enregistre ----

def test_verified_in_compensated_run_absent_without_record_diverges():
    action = _action(seq=2, state="VERIFIED",
                     output={"resource": _ref()}, error="")
    events = [
        _ev(1, "action.state", {"seq": 2}, note_to="VERIFIED"),
        _ev(2, "compensation.started", {"queued": 1, "manual_items": 0}),
    ]
    m = evaluate_recovery(
        **_base_kwargs(workflow_state="COMPENSATED", actions=[action],
                       events=events,
                       read_resource=lambda store, rid: None))
    assert m["actions"][0]["effect_state"] == "ABSENT"
    assert len(m["divergences"]) == 1
    assert m["divergences"][0]["expected"] == "PRESENT"
    assert "without recorded compensation" in m["divergences"][0]["detail"]


# ---- comp_started robuste a la perte du marqueur ----

def test_compensation_started_derived_from_trail_without_marker():
    # Pas d'evenement compensation.started (perdu) mais transitions de
    # compensation chainees -> C5, pas C6.
    action = _action(seq=2, state="COMPENSATED",
                     output={"resource": _ref()}, error="")
    events = [
        _ev(1, "action.state", {"seq": 2}, note_to="VERIFIED"),
        _ev(2, "action.state", {"seq": 2}, note_to="COMPENSATING"),
        _ev(3, "action.state", {"seq": 2}, note_to="COMPENSATED",
            note="effect undone+verified"),
    ]
    m = evaluate_recovery(
        **_base_kwargs(workflow_state="COMPENSATED", actions=[action],
                       events=events,
                       read_resource=lambda store, rid: None))
    assert m["confidence_criteria"]["evaluated"]["compensation_started"] is True
    assert m["recovery_confidence"] == "VERIFIED_WITH_COMPENSATION"
    assert m["confidence_criteria"]["rule"] == "C5"


# ---- Garde-fous : pas de sur-correction ----

def test_failed_certain_before_effect_stays_absent_with_none_method():
    # Refus design-time avant tout effet (spec 6.1) : ABSENT prouve par le
    # record d'echec (exception documentee a "none => UNKNOWN"), et un run
    # FAILED propre atterrit en C6 (C6 subsume C7-VERIFIED en v1).
    note = "PRECONDITION_FAILED: real payments are forbidden"
    action = _action(output={"_failure": {"code": "PRECONDITION_FAILED",
                                         "retryable": False, "error": note}},
                     error=note)
    events = [_ev(1, "action.state", {"seq": 6}, note_to="FAILED", note=note)]
    m = evaluate_recovery(**_base_kwargs(actions=[action], events=events))
    entry = m["actions"][0]
    assert entry["effect_state"] == "ABSENT"
    assert entry["verdict"] == "RESTORED"
    assert entry["verification"]["method"] == "none"
    assert m["recovery_confidence"] == "VERIFIED"
    assert m["confidence_criteria"]["rule"] == "C6"


def test_skipped_engine_bug_reports_connector_verify_method():
    action = _action(seq=9, state="SKIPPED",
                     output={"resource": _ref()}, error="")
    events = [_ev(1, "action.state", {"seq": 9}, note_to="SKIPPED",
                  note="dependent blocked by failure")]
    m = evaluate_recovery(
        **_base_kwargs(actions=[action], events=events,
                       read_resource=lambda store, rid: dict(_row())))
    entry = m["actions"][0]
    assert entry["effect_state"] == "PRESENT"
    assert entry["verdict"] == "NOT_RESTORED"
    assert entry["verification"]["method"] == "connector_verify"
    assert len(m["divergences"]) == 1


def test_failed_live_checks_report_connector_verify_method():
    err = "CHAOS_HTTP500: chaos (retryable=True)"
    events = [
        _ev(1, "action.state", {"seq": 6}, note_to="SUCCEEDED"),
        _ev(2, "action.state", {"seq": 6}, note_to="FAILED", note=err),
    ]
    present = _action(output={"resource": _ref()}, error=err)
    m = evaluate_recovery(
        **_base_kwargs(actions=[present], events=events,
                       read_resource=lambda store, rid: dict(_row())))
    assert m["actions"][0]["effect_state"] == "PRESENT"
    assert m["actions"][0]["verification"]["method"] == "connector_verify"
    absent = _action(output={"resource": _ref()}, error=err)
    m = evaluate_recovery(
        **_base_kwargs(actions=[absent], events=events,
                       read_resource=lambda store, rid: None))
    assert m["actions"][0]["effect_state"] == "ABSENT"
    assert m["actions"][0]["verification"]["method"] == "connector_verify"


# ---- Chaine : troncature de queue vs trou au milieu (endpoint) ----

def _terminal_marker(session, wf_id, wf_state):
    rows = session.query(Event).filter_by(workflow_id=wf_id).order_by(
        Event.seq).all()
    for row in rows:
        import json
        payload = json.loads(row.payload_json or "{}")
        if (row.type == "workflow.state" and isinstance(payload, dict)
                and payload.get("to") == wf_state):
            return row, rows
    raise AssertionError("terminal marker not found")


def test_truncated_terminal_marker_forces_c0(client, demo_auth):
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    session = session_for("main")()
    try:
        marker, rows = _terminal_marker(session, wf_id, "COMPLETED")
        # Le marqueur terminal est le dernier evenement : sa suppression
        # laisse un prefixe valide (troncature pure, pas un trou).
        assert marker.seq == rows[-1].seq
        session.delete(marker)
        session.commit()
        ok, _, _ = verify_chain(session, wf_id)
        assert ok is True  # oracle independant : prefixe hash-valide
    finally:
        session.close()
    r = client.get(f"/api/v1/workflows/{wf_id}/recovery-manifest",
                   headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["chain"]["valid"] is False
    assert "truncation" in m["chain"]["detail"]
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C0"


def test_middle_event_deletion_forces_c0_with_gap(client, demo_auth):
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    session = session_for("main")()
    try:
        rows = session.query(Event).filter_by(workflow_id=wf_id).order_by(
            Event.seq).all()
        assert len(rows) > 5
        session.delete(rows[4])
        session.commit()
    finally:
        session.close()
    r = client.get(f"/api/v1/workflows/{wf_id}/recovery-manifest",
                   headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["chain"]["valid"] is False
    assert "sequence gap" in m["chain"]["detail"]
    assert m["confidence_criteria"]["rule"] == "C0"
