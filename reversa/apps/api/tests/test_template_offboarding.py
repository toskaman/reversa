"""Offboarding template: registered caps only, valid DAG, engine-executable."""

import json
import uuid

from reversa_api.connectors.sdk import get_connector
from reversa_api.db import session_for
from reversa_api.engine.saga import execute_workflow_sync
from reversa_api.models import ActionRun, Workflow
from reversa_api.planner.validate import plan_hash, validate_plan
from reversa_api.templates.offboarding import DEMO_CUSTOMER, build_offboarding_plan


def _contracts(steps):
    return [get_connector(s["connector_id"]).contract_for(s["action_type"])
            for s in steps]


def test_steps_use_registered_capabilities_only():
    steps = build_offboarding_plan()
    assert len(steps) == 3
    for step in steps:
        assert set(step) == {"action_type", "connector_id", "inputs", "depends_on"}
        contract = get_connector(step["connector_id"]).contract_for(step["action_type"])
        assert contract.connector_id == step["connector_id"]
        for key in contract.input_schema:
            assert key in step["inputs"], f"{step['action_type']} missing {key}"
        for pre in contract.preconditions:
            if pre.startswith("input_has:"):
                key = pre.split(":", 1)[1]
                assert step["inputs"].get(key) not in (None, "")


def test_dag_is_strictly_increasing():
    steps = build_offboarding_plan()
    for i, step in enumerate(steps, start=1):
        assert all(isinstance(d, int) and 1 <= d < i for d in step["depends_on"])
    assert [s["depends_on"] for s in steps] == [[], [1], [2]]


def test_validate_plan_accepts_offboarding():
    normalized, approval_required, issues = validate_plan(
        {"steps": build_offboarding_plan()})
    assert issues == []
    assert len(normalized) == 3
    assert approval_required is False
    for step in normalized:
        assert step["compensation_capability"]
        assert step["approval_policy"] == "AUTO_ALLOWED"
        assert step["max_attempts"] >= 1


def test_compensation_posture_record_then_irreversible_notify():
    contracts = _contracts(build_offboarding_plan())
    assert [c.compensation_capability for c in contracts] == [
        "COMPENSATABLE", "COMPENSATABLE", "IRREVERSIBLE"]


def test_customer_override_propagates_without_onboarding_leak():
    steps = build_offboarding_plan({"company_name": "Hooli", "org_slug": "hooli"})
    assert steps[0]["inputs"] == {"customer_name": "Hooli"}
    assert steps[1]["inputs"] == {"org_slug": "hooli"}
    message = steps[2]["inputs"]["message"]
    assert message == "Offboarding complete for Hooli"
    assert "Onboarding" not in json.dumps(steps)


def test_default_customer_shape():
    assert DEMO_CUSTOMER["company_name"] and DEMO_CUSTOMER["org_slug"]
    steps = build_offboarding_plan()
    assert steps[0]["inputs"]["customer_name"] == DEMO_CUSTOMER["company_name"]


def test_plan_hash_deterministic():
    first = plan_hash(validate_plan({"steps": build_offboarding_plan()})[0])
    second = plan_hash(validate_plan({"steps": build_offboarding_plan()})[0])
    assert first == second


def test_engine_happy_path_completes(fresh_db, demo_auth):
    """Seed a READY workflow from the template; the saga must COMPLETE it."""
    normalized, approval_required, issues = validate_plan(
        {"steps": build_offboarding_plan()})
    assert issues == [] and approval_required is False
    session = session_for("main")()
    try:
        wf = Workflow(org_id=demo_auth["org_id"], name="Offboard test",
                      intent="offboard", state="READY",
                      plan_json=json.dumps({"steps": normalized}),
                      created_by="test")
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
        wf_id = wf.id
    finally:
        session.close()
    assert execute_workflow_sync(session_for("main"), wf_id, worker_id="test",
                                 actor="test") == "COMPLETED"
    session = session_for("main")()
    try:
        states = [a.state for a in session.query(ActionRun)
                  .filter_by(workflow_id=wf_id).order_by(ActionRun.seq).all()]
        assert states == ["VERIFIED"] * 3, states
    finally:
        session.close()
