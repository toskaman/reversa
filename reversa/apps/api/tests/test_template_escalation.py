"""Escalation template: contract + validation + happy-path/chaos e2e (Cycle 2).

The template is exercised the way the engine consumes it: raw steps go
through validate_plan, normalized steps seed a READY workflow, and the
workflow executes (happy path -> COMPLETED, injected fault -> COMPENSATED).
"""

import json
import uuid

from reversa_api.db import session_for
from reversa_api.engine.saga import execute_workflow_sync
from reversa_api.models import ActionRun, Workflow
from reversa_api.planner import available_capabilities, validate_plan
from reversa_api.templates.escalation import DEMO_ESCALATION, build_escalation_plan


EXPECTED_COMPENSATIONS = {
    "crm.validate_customer": "COMPENSATABLE",  # read-only: compensates to noop
    "crm.create_organization": "COMPENSATABLE",
    "identity.create_workspace": "FULLY_REVERSIBLE",
    "support.create_queue": "COMPENSATABLE",
    "identity.assign_manager": "FULLY_REVERSIBLE",
    "support.create_checklist": "COMPENSATABLE",
    "notify.send_summary": "IRREVERSIBLE",  # last step: never needs undoing
}


def _seed_ready_workflow(org_id: int, actor: str = "test") -> tuple[int, list[dict]]:
    """Validate the template and seed a READY workflow from it (route parity).

    Mirrors POST /intents row creation (plan_json + ActionRuns) minus the
    approval gate, which the template never raises (all steps AUTO_ALLOWED).
    """
    steps = build_escalation_plan()
    normalized, approval_required, issues = validate_plan({"steps": steps})
    assert issues == [], issues
    assert approval_required is False
    session = session_for("main")()
    try:
        wf = Workflow(org_id=org_id, name="Escalate Acme", intent="escalate",
                      state="READY", plan_version=1,
                      plan_json=json.dumps({"goal": "escalate", "steps": normalized}),
                      created_by=actor)
        session.add(wf)
        session.flush()
        for step in normalized:
            session.add(ActionRun(
                workflow_id=wf.id, seq=step["seq"],
                action_type=step["action_type"],
                connector_id=step["connector_id"], state="PENDING",
                input_json=json.dumps(step["inputs"]),
                idempotency_key=uuid.uuid4().hex,
                max_attempts=step["max_attempts"],
                compensation_capability=step["compensation_capability"],
                depends_on=json.dumps(step["depends_on"])))
        session.commit()
        return wf.id, normalized
    finally:
        session.close()


def test_escalation_shape_and_dag():
    steps = build_escalation_plan()
    assert len(steps) == 7
    assert steps == build_escalation_plan()  # deterministic
    for i, step in enumerate(steps, start=1):
        assert set(step) == {"action_type", "connector_id", "inputs", "depends_on"}
        assert isinstance(step["inputs"], dict)
        assert all(isinstance(d, int) and 1 <= d < i for d in step["depends_on"]), step
    assert steps[0]["depends_on"] == []
    assert steps[-1]["action_type"] == "notify.send_summary"


def test_escalation_customer_overrides():
    steps = build_escalation_plan({
        "company_name": "Globex", "org_slug": "globex", "tier": "urgent",
        "manager_email": "boss@globex.example", "channel": "slack",
    })
    by_action = {s["action_type"]: s for s in steps}
    assert by_action["crm.validate_customer"]["inputs"] == {"customer_name": "Globex"}
    assert by_action["crm.create_organization"]["inputs"] == {
        "org_slug": "globex", "company_name": "Globex"}
    assert by_action["support.create_queue"]["inputs"]["tier"] == "urgent"
    assert by_action["identity.assign_manager"]["inputs"] == {
        "workspace": "globex", "manager_email": "boss@globex.example"}
    assert by_action["notify.send_summary"]["inputs"]["channel"] == "slack"
    assert "Globex" in by_action["notify.send_summary"]["inputs"]["message"]
    # Defaults apply when no overrides are given.
    default = {s["action_type"]: s for s in build_escalation_plan()}
    assert default["crm.validate_customer"]["inputs"]["customer_name"] == (
        DEMO_ESCALATION["company_name"])
    # No secret-looking material anywhere in the template.
    blob = json.dumps(steps).lower()
    assert "token" not in blob and "secret" not in blob and "password" not in blob


def test_escalation_uses_registered_caps_only():
    from reversa_api.connectors.sdk import get_connector

    registered = {(c["action_type"], c["connector_id"])
                  for c in available_capabilities()}
    for step in build_escalation_plan():
        key = (step["action_type"], step["connector_id"])
        assert key in registered, f"{key} is not a registered capability"
        contract = get_connector(step["connector_id"]).contract_for(step["action_type"])
        assert contract.connector_id == step["connector_id"]
        assert contract.approval_policy == "AUTO_ALLOWED", key


def test_escalation_validates_with_compensations():
    normalized, approval_required, issues = validate_plan(
        {"steps": build_escalation_plan()})
    assert issues == [], issues
    assert approval_required is False
    assert [s["seq"] for s in normalized] == [1, 2, 3, 4, 5, 6, 7]
    for step in normalized:
        assert step["compensation_capability"] == (
            EXPECTED_COMPENSATIONS[step["action_type"]]), step["action_type"]
        assert step["approval_policy"] == "AUTO_ALLOWED"
        assert step["risk_level"] in ("low", "medium", "high", "critical")
        assert step["max_attempts"] >= 1


def test_escalation_preconditions_satisfied():
    from reversa_api.connectors.sdk import get_connector

    for step in build_escalation_plan():
        contract = get_connector(step["connector_id"]).contract_for(step["action_type"])
        for pre in contract.preconditions:
            assert pre.startswith("input_has:"), (step["action_type"], pre)
            key = pre.split(":", 1)[1]
            assert step["inputs"].get(key) not in (None, ""), (step, pre)


def test_escalation_happy_path_e2e(client, demo_auth):
    wf_id, _ = _seed_ready_workflow(demo_auth["org_id"])
    h = demo_auth["headers"]
    r = client.post(f"/api/v1/workflows/{wf_id}/execute", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workflow"]["state"] == "COMPLETED", body
    assert all(a["state"] == "VERIFIED" for a in body["actions"]), body["actions"]

    # Real resources in independent service states.
    r = client.get("/api/v1/demo/support/resources",
                   params={"kind": "queue", "status": "active",
                           "workflow_id": wf_id}, headers=h)
    queues = r.json()["resources"]
    assert len(queues) == 1 and queues[0]["data"]["tier"] == "priority", r.text
    r = client.get("/api/v1/demo/support/resources",
                   params={"kind": "checklist", "status": "active",
                           "workflow_id": wf_id}, headers=h)
    assert len(r.json()["resources"]) == 1, r.text
    r = client.get("/api/v1/demo/identity/resources",
                   params={"kind": "workspace", "status": "active",
                           "workflow_id": wf_id}, headers=h)
    workspaces = r.json()["resources"]
    assert len(workspaces) == 1, r.text
    assert workspaces[0]["data"]["manager"] == DEMO_ESCALATION["manager_email"]
    r = client.get("/api/v1/demo/notify/resources",
                   params={"status": "active", "workflow_id": wf_id}, headers=h)
    assert len(r.json()["resources"]) == 1, r.text

    r = client.get(f"/api/v1/workflows/{wf_id}/evidence", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["chain"]["valid"] is True


def test_escalation_chaos_compensates_in_reverse(client, demo_auth):
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-support", "fault": "http500",
                          "times": 10},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id, _ = _seed_ready_workflow(demo_auth["org_id"])
    r = client.post(f"/api/v1/workflows/{wf_id}/execute",
                    headers=demo_auth["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["state"] == "COMPENSATED", r.text
    by_seq = {a["seq"]: a["state"] for a in r.json()["actions"]}
    assert by_seq[4] == "FAILED", by_seq  # support.create_queue
    assert all(by_seq[s] == "COMPENSATED" for s in (1, 2, 3, 5)), by_seq
    assert all(by_seq[s] == "SKIPPED" for s in (6, 7)), by_seq

    r = client.get(f"/api/v1/workflows/{wf_id}/events",
                   params={"limit": 500}, headers=demo_auth["headers"])
    comp_order = [e["payload"]["seq"] for e in r.json()["data"]
                  if e["type"] == "action.state"
                  and e["payload"].get("to") == "COMPENSATED"]
    assert comp_order == sorted(comp_order, reverse=True), comp_order
    assert comp_order == [5, 3, 2, 1], comp_order

    # Resources actually restored.
    h = demo_auth["headers"]
    r = client.get("/api/v1/demo/identity/resources",
                   params={"kind": "workspace", "workflow_id": wf_id}, headers=h)
    assert r.json()["resources"] == [], r.text  # hard-deleted
    r = client.get("/api/v1/demo/crm/resources",
                   params={"kind": "organization", "status": "archived",
                           "workflow_id": wf_id}, headers=h)
    assert len(r.json()["resources"]) == 1, r.text


def test_escalation_lost_response_retries_idempotently(client, demo_auth):
    """Chaos crash (uncertain) on step 1 -> reconcile -> one retry -> COMPLETED."""
    r = client.post("/api/v1/demo/chaos",
                    json={"target_connector": "demo-crm",
                          "target_action": "crm.validate_customer",
                          "fault": "crash", "times": 1},
                    headers=demo_auth["headers"])
    assert r.status_code == 201, r.text
    wf_id, _ = _seed_ready_workflow(demo_auth["org_id"])
    assert execute_workflow_sync(session_for("main"), wf_id,
                                 worker_id="worker-1") == "COMPLETED"
    r = client.get(f"/api/v1/workflows/{wf_id}/events",
                   params={"limit": 500}, headers=demo_auth["headers"])
    events = r.json()["data"]
    trail = [e["payload"].get("to") for e in events
             if e["type"] == "action.state"
             and e["payload"].get("action_type") == "crm.validate_customer"]
    assert "UNKNOWN_OUTCOME" in trail, trail
    assert trail.count("EXECUTING") == 2, trail
    assert trail[-1] == "VERIFIED", trail
