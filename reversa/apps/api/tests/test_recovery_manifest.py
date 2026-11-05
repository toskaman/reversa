"""Recovery Proof Engine v1: manifest endpoint + evaluator units.

Endpoint tests pin clean C5/C6 runs, R4 refusal, the C0 tamper cap, and C7
divergence. Unit tests pin C1 (missing/uncertain/partial records), C2
(dangling refs), C3 (capability/external manual work, UNKNOWN fail-closed,
C1>C3 and C3>C4 dominance), C4 exhaustion, and verdict honesty (recorded
vs re-verified vs never-inferred).
"""

from reversa_api.db import session_for
from reversa_api.models import DemoResource, Event

from .conftest import make_ready


def _manifest(client, auth, wf_id):
    r = client.get(f"/api/v1/workflows/{wf_id}/recovery-manifest",
                   headers=auth["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def _event_seqs(client, auth, wf_id):
    r = client.get(f"/api/v1/workflows/{wf_id}/events", params={"limit": 500},
                   headers=auth["headers"])
    assert r.status_code == 200, r.text
    return {e["seq"] for e in r.json()["data"]}


def _assert_refs_resolve(manifest, seqs):
    def check(ref):
        assert isinstance(ref, str) and ref.startswith("event seq "), ref
        assert int(ref.removeprefix("event seq ")) in seqs, ref

    for entry in manifest["actions"]:
        check(entry["verification"]["event_ref"])
        if "compensation" in entry:
            check(entry["compensation"]["proof_ref"])
    for item in manifest["manual_items"]:
        check(item["event_ref"])


def test_completed_run_is_verified(client, demo_auth):
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text

    m = _manifest(client, demo_auth, wf_id)
    assert m["manifest_version"] == "1.0"
    assert m["workflow_id"] == wf_id
    assert m["recovery_confidence"] == "VERIFIED"
    assert m["confidence_criteria"]["rule"] == "C6"
    assert m["chain"]["valid"] is True
    assert m["summary"] == {"actions_total": 10, "restored": 10,
                            "not_restored": 0, "indeterminate": 0,
                            "compensations_run": 0, "manual_items": 0,
                            "refusals": 0}, m["summary"]
    assert all(e["verdict"] == "RESTORED" for e in m["actions"])
    assert all(e["required"] == "forward_success" for e in m["actions"])
    assert m["divergences"] == []
    assert m["indeterminate"] == []
    assert m["manual_items"] == []
    assert m["refusals"] == []
    # Resources: 8 actions carry refs (validate + core check carry none).
    assert len(m["created_resources"]) == 8
    assert len(m["final_resources"]) == 10  # org+workspace+4 users+queue+checklist+profile+msg
    assert all(r["status"] == "active" for r in m["final_resources"])
    assert m["initial_resources"] == []  # fresh org: everything created by the run
    _assert_refs_resolve(m, _event_seqs(client, demo_auth, wf_id))


def test_compensated_run_is_verified_with_compensation(client, demo_auth):
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-billing", "fault": "http500",
                          "times": 5},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text

    m = _manifest(client, demo_auth, wf_id)
    assert m["recovery_confidence"] == "VERIFIED_WITH_COMPENSATION"
    assert m["confidence_criteria"]["rule"] == "C5"
    assert m["chain"]["valid"] is True
    assert m["summary"]["compensations_run"] == 7, m["summary"]
    assert m["summary"]["restored"] == 10, m["summary"]
    by_seq = {e["seq"]: e for e in m["actions"]}
    assert by_seq[6]["action_state"] == "FAILED"
    assert by_seq[6]["verdict"] == "RESTORED"  # certain failure: nothing to undo
    assert by_seq[9]["verdict"] == "RESTORED"
    assert by_seq[10]["verdict"] == "RESTORED"
    assert by_seq[1]["compensation"]["absence_method"] == "noop_proof"
    assert m["divergences"] == []
    assert m["indeterminate"] == []
    # Workspace hard-deleted; users/org/queue/checklist archived; no profile, no msg.
    final = {(r["kind"], r["status"]) for r in m["final_resources"]}
    assert ("workspace", "active") not in final
    assert ("user", "archived") in final
    assert ("organization", "archived") in final
    assert len(m["compensations"]) == 7
    assert {c["result"] for c in m["compensations"]} <= {"compensated", "noop"}
    _assert_refs_resolve(m, _event_seqs(client, demo_auth, wf_id))


def test_non_terminal_workflow_is_refused(client, demo_auth):
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.get(f"/api/v1/workflows/{wf_id}/recovery-manifest",
                   headers=demo_auth["headers"])
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "R4_NOT_TERMINAL"


def test_unknown_workflow_is_404(client, demo_auth):
    r = client.get("/api/v1/workflows/999999/recovery-manifest",
                   headers=demo_auth["headers"])
    assert r.status_code == 404


def test_tampered_chain_is_indeterminate(client, demo_auth):
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    session = session_for("main")()
    try:
        row = session.query(Event).filter_by(workflow_id=wf_id, seq=2).one()
        row.payload_json = '{"tampered": true}'
        session.commit()
    finally:
        session.close()
    m = _manifest(client, demo_auth, wf_id)
    assert m["chain"]["valid"] is False
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C0"


def test_external_delete_after_success_is_divergence(client, demo_auth):
    made = make_ready(client, demo_auth)
    wf_id = made["workflow"]["id"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.json()["workflow"]["state"] == "COMPLETED", r.text
    session = session_for("identity")()
    try:
        row = session.query(DemoResource).filter_by(
            org_id=demo_auth["org_id"], kind="workspace").one()
        session.delete(row)
        session.commit()
    finally:
        session.close()
    m = _manifest(client, demo_auth, wf_id)
    by_seq = {e["seq"]: e for e in m["actions"]}
    assert by_seq[3]["effect_state"] == "ABSENT"
    assert by_seq[3]["verdict"] == "NOT_RESTORED"
    assert any(d["seq"] == 3 and d["expected"] == "PRESENT"
               for d in m["divergences"]), m["divergences"]
    # Lost forward effect: no manual/exhausted cause -> C7 fallthrough.
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C7"


def _base_kwargs(**overrides):
    kw = dict(workflow_id=7, org_id=1, workflow_state="MANUAL_REQUIRED",
              actions=[], events=[], chain={"valid": True, "events": 0,
                                            "head_hash": "abc", "detail": "ok"},
              read_resource=lambda store, rid: None, final_resources=[],
              generated_at="2026-11-05T12:00:00Z")
    kw.update(overrides)
    return kw


def _ev(seq, type, payload=None, note_to=None):
    body = dict(payload or {})
    if note_to is not None:
        body["to"] = note_to
    return {"seq": seq, "ts": "2026-11-05T12:00:00Z", "type": type,
            "payload": body}


def test_unit_manual_refusal_needs_human():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 10, "action_type": "notify.send_summary",
              "connector_id": "demo-notify", "state": "VERIFIED",
              "output": {"resource": {"store": "notify", "kind": "message",
                                      "name": "7:email", "id": 1, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "IRREVERSIBLE"}
    events = [
        _ev(1, "workflow.created"),
        _ev(2, "action.state", {"seq": 10}, note_to="VERIFIED"),
        _ev(3, "compensation.started", {"queued": 0, "manual_items": 1}),
        _ev(4, "compensation.manual_required", {"seq": 10}),
    ]
    row = {"id": 1, "kind": "message", "name": "7:email", "status": "active",
           "version": 1, "data": {"sent": True}}
    m = evaluate_recovery(
        **_base_kwargs(actions=[action], events=events,
                       read_resource=lambda store, rid: dict(row)))
    assert m["recovery_confidence"] == "MANUAL_REQUIRED"
    assert m["confidence_criteria"]["rule"] == "C3"
    assert m["actions"][0]["verdict"] == "NOT_RESTORED"
    assert m["manual_items"][0]["cause"] == "capability_refusal"
    assert m["refusals"][0]["code"] == "R_CAPABILITY_REFUSAL"


def test_unit_exhausted_compensation_is_partial():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 2, "action_type": "crm.create_organization",
              "connector_id": "demo-crm", "state": "COMPENSATION_FAILED",
              "output": {"resource": {"store": "crm", "kind": "organization",
                                      "name": "acme", "id": 1, "version": 1},
                         "_comp_attempts": 3},
              "error": "CHAOS_HTTP500: chaos (retryable=True)", "attempt": 1,
              "compensation_capability": "COMPENSATABLE"}
    events = [
        _ev(1, "action.state", {"seq": 2}, note_to="VERIFIED"),
        _ev(2, "compensation.started", {"queued": 1, "manual_items": 0}),
        _ev(3, "action.state", {"seq": 2}, note_to="COMPENSATION_FAILED"),
    ]
    row = {"id": 1, "kind": "organization", "name": "acme",
           "status": "active", "version": 1, "data": {}}
    m = evaluate_recovery(
        **_base_kwargs(workflow_state="PARTIALLY_COMPENSATED", actions=[action],
                       events=events,
                       read_resource=lambda store, rid: dict(row)))
    assert m["recovery_confidence"] == "PARTIAL"
    assert m["confidence_criteria"]["rule"] == "C4"
    assert m["manual_items"] == []
    assert m["compensations"][0]["result"] == "failed"
    assert m["compensations"][0]["attempts"] == 3


def test_unit_missing_record_is_indeterminate():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 2, "action_type": "crm.create_organization",
              "connector_id": "demo-crm", "state": "COMPENSATED",
              "output": {"resource": {"store": "crm", "kind": "organization",
                                      "name": "acme", "id": 1, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "COMPENSATABLE"}
    m = evaluate_recovery(**_base_kwargs(workflow_state="COMPENSATED",
                                         actions=[action], events=[]))
    assert m["actions"][0]["effect_state"] == "UNKNOWN"
    assert m["actions"][0]["verdict"] == "INDETERMINATE"
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C1"
    assert len(m["indeterminate"]) == 1


def test_unit_external_modification_orders_manual_work():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 2, "action_type": "crm.create_organization",
              "connector_id": "demo-crm", "state": "COMPENSATION_FAILED",
              "output": {"resource": {"store": "crm", "kind": "organization",
                                      "name": "acme", "id": 1, "version": 1},
                         "_comp_attempts": 3},
              "error": ("PRECONDITION_FAILED: resource 1 changed (expected v1, "
                        "found v5); refusing to overwrite a newer state"),
              "attempt": 1, "compensation_capability": "COMPENSATABLE"}
    events = [
        _ev(1, "action.state", {"seq": 2}, note_to="VERIFIED"),
        _ev(2, "compensation.started", {"queued": 1, "manual_items": 0}),
        _ev(3, "action.state", {"seq": 2}, note_to="COMPENSATION_FAILED"),
    ]
    row = {"id": 1, "kind": "organization", "name": "acme",
           "status": "active", "version": 5, "data": {}}
    m = evaluate_recovery(
        **_base_kwargs(actions=[action], events=events,
                       read_resource=lambda store, rid: dict(row)))
    assert m["recovery_confidence"] == "MANUAL_REQUIRED"
    assert m["confidence_criteria"]["rule"] == "C3"
    assert m["manual_items"][0]["cause"] == "external_modification"
    assert m["refusals"][0]["code"] == "R_EXTERNAL_MODIFICATION"


def test_unit_uncertain_failure_is_indeterminate():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 5, "action_type": "billing.create_profile",
              "connector_id": "demo-billing", "state": "FAILED",
              "output": {}, "error": "timeout waiting for connector verify",
              "attempt": 1, "compensation_capability": "COMPENSATABLE"}
    events = [_ev(1, "action.state", {"seq": 5}, note_to="FAILED")]
    m = evaluate_recovery(**_base_kwargs(workflow_state="FAILED",
                                         actions=[action], events=events))
    assert m["actions"][0]["effect_state"] == "UNKNOWN"
    assert m["actions"][0]["verdict"] == "INDETERMINATE"
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C1"
    assert m["confidence_criteria"]["evaluated"]["refs_resolve"] is True
    assert len(m["indeterminate"]) == 1


def test_unit_failed_partial_effect_is_indeterminate():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 6, "action_type": "billing.create_profile",
              "connector_id": "demo-billing", "state": "FAILED",
              "output": {"partial": True},
              "error": "verify error: reconcile deferred",
              "attempt": 2, "compensation_capability": "COMPENSATABLE"}
    events = [
        _ev(1, "action.state", {"seq": 6}, note_to="SUCCEEDED"),
        _ev(2, "action.state", {"seq": 6}, note_to="VERIFYING"),
        _ev(3, "action.state", {"seq": 6}, note_to="FAILED"),
    ]
    m = evaluate_recovery(**_base_kwargs(workflow_state="FAILED",
                                         actions=[action], events=events))
    assert m["actions"][0]["effect_state"] == "UNKNOWN"
    assert m["actions"][0]["verdict"] == "INDETERMINATE"
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C1"


def test_unit_dangling_ref_is_indeterminate():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 10, "action_type": "notify.send_summary",
              "connector_id": "demo-notify", "state": "VERIFIED",
              "output": {"resource": {"store": "notify", "kind": "message",
                                      "name": "7:email", "id": 1, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "IRREVERSIBLE"}
    events = [
        _ev(1, "workflow.created"),
        _ev(2, "action.state", {"seq": 10}, note_to="VERIFIED"),
        _ev(3, "compensation.started", {"queued": 0, "manual_items": 1}),
    ]
    row = {"id": 1, "kind": "message", "name": "7:email", "status": "active",
           "version": 1, "data": {"sent": True}}
    m = evaluate_recovery(
        **_base_kwargs(actions=[action], events=events,
                       read_resource=lambda store, rid: dict(row)))
    assert m["confidence_criteria"]["evaluated"]["refs_resolve"] is False
    assert m["manual_items"][0]["event_ref"] is None
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C2"


def test_unit_unknown_capability_fails_closed_to_manual():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 9, "action_type": "crm.tag_vip",
              "connector_id": "demo-crm", "state": "VERIFIED",
              "output": {"resource": {"store": "crm", "kind": "tag",
                                      "name": "vip", "id": 2, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "UNKNOWN"}
    events = [
        _ev(1, "workflow.created"),
        _ev(2, "action.state", {"seq": 9}, note_to="VERIFIED"),
        _ev(3, "compensation.started", {"queued": 0, "manual_items": 1}),
        _ev(4, "compensation.manual_required", {"seq": 9}),
    ]
    row = {"id": 2, "kind": "tag", "name": "vip", "status": "active",
           "version": 1, "data": {}}
    m = evaluate_recovery(
        **_base_kwargs(actions=[action], events=events,
                       read_resource=lambda store, rid: dict(row)))
    assert m["recovery_confidence"] == "MANUAL_REQUIRED"
    assert m["confidence_criteria"]["rule"] == "C3"
    assert m["actions"][0]["effect_state"] == "PRESENT"
    assert m["actions"][0]["verdict"] == "NOT_RESTORED"
    assert m["manual_items"][0]["cause"] == "capability_refusal"
    assert m["refusals"][0]["code"] == "R_CAPABILITY_REFUSAL"


def test_unit_ignorance_dominates_actionability():
    from reversa_api.routes.recovery import evaluate_recovery
    unknown = {"seq": 5, "action_type": "billing.create_profile",
               "connector_id": "demo-billing", "state": "FAILED",
               "output": {}, "error": "timeout waiting for connector verify",
               "attempt": 1, "compensation_capability": "COMPENSATABLE"}
    manual = {"seq": 10, "action_type": "notify.send_summary",
              "connector_id": "demo-notify", "state": "VERIFIED",
              "output": {"resource": {"store": "notify", "kind": "message",
                                      "name": "7:email", "id": 1, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "IRREVERSIBLE"}
    events = [
        _ev(1, "action.state", {"seq": 5}, note_to="FAILED"),
        _ev(2, "action.state", {"seq": 10}, note_to="VERIFIED"),
        _ev(3, "compensation.started", {"queued": 0, "manual_items": 1}),
        _ev(4, "compensation.manual_required", {"seq": 10}),
    ]
    row = {"id": 1, "kind": "message", "name": "7:email", "status": "active",
           "version": 1, "data": {"sent": True}}
    m = evaluate_recovery(
        **_base_kwargs(actions=[unknown, manual], events=events,
                       read_resource=lambda store, rid: dict(row)))
    assert m["confidence_criteria"]["evaluated"]["refs_resolve"] is True
    assert len(m["manual_items"]) == 1  # still enumerated, but dominated
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C1"


def test_unit_actionability_dominates_exhaustion():
    from reversa_api.routes.recovery import evaluate_recovery
    exhausted = {"seq": 2, "action_type": "crm.create_organization",
                 "connector_id": "demo-crm", "state": "COMPENSATION_FAILED",
                 "output": {"resource": {"store": "crm", "kind": "organization",
                                         "name": "acme", "id": 1, "version": 1},
                            "_comp_attempts": 3},
                 "error": "CHAOS_HTTP500: chaos (retryable=True)", "attempt": 1,
                 "compensation_capability": "COMPENSATABLE"}
    manual = {"seq": 10, "action_type": "notify.send_summary",
              "connector_id": "demo-notify", "state": "VERIFIED",
              "output": {"resource": {"store": "notify", "kind": "message",
                                      "name": "7:email", "id": 1, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "IRREVERSIBLE"}
    events = [
        _ev(1, "action.state", {"seq": 2}, note_to="VERIFIED"),
        _ev(2, "action.state", {"seq": 10}, note_to="VERIFIED"),
        _ev(3, "compensation.started", {"queued": 1, "manual_items": 1}),
        _ev(4, "action.state", {"seq": 2}, note_to="COMPENSATION_FAILED"),
        _ev(5, "compensation.manual_required", {"seq": 10}),
    ]

    def _read(store, rid):
        if store == "notify":
            return {"id": 1, "kind": "message", "name": "7:email",
                    "status": "active", "version": 1, "data": {"sent": True}}
        return {"id": 1, "kind": "organization", "name": "acme",
                "status": "active", "version": 1, "data": {}}

    m = evaluate_recovery(**_base_kwargs(actions=[exhausted, manual],
                                         events=events, read_resource=_read))
    assert m["confidence_criteria"]["evaluated"]["exhausted_compensations"] == 1
    assert len(m["manual_items"]) == 1
    assert m["recovery_confidence"] == "MANUAL_REQUIRED"
    assert m["confidence_criteria"]["rule"] == "C3"


def test_unit_missing_verify_never_inferred_present():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 3, "action_type": "identity.create_workspace",
              "connector_id": "demo-identity", "state": "VERIFIED",
              "output": {"resource": {"store": "identity", "kind": "workspace",
                                      "name": "acme", "id": 9, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "FULLY_REVERSIBLE"}
    row = {"id": 9, "kind": "workspace", "name": "acme", "status": "active",
           "version": 1, "data": {}}
    m = evaluate_recovery(**_base_kwargs(workflow_state="COMPLETED",
                                         actions=[action], events=[],
                                         read_resource=lambda s, r: dict(row)))
    assert m["actions"][0]["effect_state"] == "UNKNOWN"
    assert m["actions"][0]["verdict"] == "INDETERMINATE"
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C1"


def test_unit_recorded_compensation_downgraded_by_present_row():
    from reversa_api.routes.recovery import evaluate_recovery
    action = {"seq": 2, "action_type": "crm.create_organization",
              "connector_id": "demo-crm", "state": "COMPENSATED",
              "output": {"resource": {"store": "crm", "kind": "organization",
                                      "name": "acme", "id": 1, "version": 1}},
              "error": "", "attempt": 1,
              "compensation_capability": "COMPENSATABLE"}
    events = [
        _ev(1, "action.state", {"seq": 2}, note_to="VERIFIED"),
        _ev(2, "compensation.started", {"queued": 1, "manual_items": 0}),
        _ev(3, "action.state", {"seq": 2}, note_to="COMPENSATING"),
        _ev(4, "action.state", {"seq": 2}, note_to="COMPENSATED"),
    ]
    row = {"id": 1, "kind": "organization", "name": "acme",
           "status": "active", "version": 1, "data": {}}
    m = evaluate_recovery(
        **_base_kwargs(workflow_state="COMPENSATED", actions=[action],
                       events=events,
                       read_resource=lambda store, rid: dict(row)))
    assert m["actions"][0]["effect_state"] == "PRESENT"
    assert m["actions"][0]["verdict"] == "NOT_RESTORED"
    assert len(m["divergences"]) == 1
    assert m["divergences"][0]["expected"] == "ABSENT"
    assert m["recovery_confidence"] == "INDETERMINATE"
    assert m["confidence_criteria"]["rule"] == "C7"
