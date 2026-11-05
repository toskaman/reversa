"""Nested-shape validation: every action must fail typed, never 500 (05-SAGA).

Classe de bug visee: inputs/outputs imbriques non valides (dict/list/int a la
place d'un str, refs malformees, JSON stocke illisible, payloads API
surprenants) qui levaient des exceptions brutes (AttributeError, TypeError,
ValueError, KeyError, AssertionError) -> HTTP 500. Attendu: ConnectorError /
PreconditionFailed types, ou etat FAILED/COMPENSATED propre via le moteur.
"""

import httpx
import pytest

from reversa_api.connectors.github import GithubConnector
from reversa_api.connectors.sdk import (
    REGISTRY,
    ConnectorError,
    PreconditionFailed,
    check_preconditions,
    get_connector,
)
from reversa_api.db import session_for
from reversa_api.engine.saga import execute_workflow_sync
from reversa_api.models import ActionRun, Workflow


def _ctx(org_id=1, wf_id=1):
    return {"org_id": org_id, "workflow_id": wf_id, "is_demo": True}


def _contract(connector_id, action_type):
    return get_connector(connector_id).contract_for(action_type)


def _seed(session, wf_id, seq, state, key, action_type, connector_id,
          inputs=None, raw_input=None, raw_output=None, output=None,
          attempt=0, max_attempts=1, capability="COMPENSATABLE",
          depends_on="[]", error=""):
    import json

    action = ActionRun(
        workflow_id=wf_id, seq=seq, action_type=action_type,
        connector_id=connector_id, state=state,
        input_json=(raw_input if raw_input is not None
                    else json.dumps(inputs if inputs is not None else {})),
        output_json=(raw_output if raw_output is not None
                     else json.dumps(output if output is not None else {})),
        idempotency_key=key, attempt=attempt, max_attempts=max_attempts,
        lease_owner="", lease_expires_at=None,
        compensation_capability=capability, depends_on=depends_on,
        error=error)
    session.add(action)
    session.flush()
    return action


def _seed_wf(session, org_id):
    wf = Workflow(org_id=org_id, name="t", intent="t", state="RUNNING",
                  plan_json="{}", created_by="test")
    session.add(wf)
    session.flush()
    return wf


def _action_state(key):
    session = session_for("main")()
    try:
        action = session.query(ActionRun).filter_by(
            idempotency_key=key).one()
        return action.state, action.error
    finally:
        session.close()


# -- sdk: preconditions ------------------------------------------------------

NESTED = [{"nested": "dict"}, ["list"], 42, True]


def test_check_preconditions_rejects_non_dict_inputs():
    contract = _contract("demo-crm", "crm.validate_customer")
    for bad in (None, 42, ["x"], "customer_name"):
        with pytest.raises(PreconditionFailed):
            check_preconditions(_ctx(), contract, bad)


# -- demo connectors: execute ------------------------------------------------

def test_crm_validate_customer_nested_shape_fails_typed(fresh_db):
    connector = get_connector("demo-crm")
    contract = connector.contract_for("crm.validate_customer")
    for bad in NESTED:
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract, {"customer_name": bad})


def test_create_organization_nested_slug_fails_typed(fresh_db):
    connector = get_connector("demo-crm")
    contract = connector.contract_for("crm.create_organization")
    for bad in NESTED:
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"org_slug": bad, "company_name": "Acme"})
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"org_slug": "acme", "company_name": bad})


def test_identity_create_workspace_nested_slug_fails_typed(fresh_db):
    connector = get_connector("demo-identity")
    contract = connector.contract_for("identity.create_workspace")
    for bad in NESTED:
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract, {"org_slug": bad})


def test_provision_users_nested_workspace_fails_typed(fresh_db):
    connector = get_connector("demo-identity")
    contract = connector.contract_for("identity.provision_users")
    users = [{"email": "a@example.com"}]
    for bad in NESTED:
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"workspace": bad, "users": users})


def test_assign_manager_nested_inputs_fail_typed(fresh_db):
    connector = get_connector("demo-identity")
    contract = connector.contract_for("identity.assign_manager")
    for bad in NESTED:
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"workspace": bad, "manager_email": "m@x.co"})
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"workspace": "w", "manager_email": bad})


@pytest.mark.parametrize("connector_id,action_type,inputs", [
    ("demo-support", "support.create_queue",
     {"org_slug": {"nested": 1}, "tier": "enterprise"}),
    ("demo-support", "support.create_checklist", {"org_slug": ["l"]}),
    ("demo-billing", "billing.create_profile",
     {"org_slug": "acme", "plan": {"nested": 1}}),
    ("demo-notify", "notify.send_summary",
     {"channel": ["c"], "message": "hi"}),
    ("demo-notify", "notify.send_summary",
     {"channel": "email", "message": {"nested": 1}}),
    ("reversa-core", "core.consistency_check", {"org_slug": 42}),
])
def test_demo_string_inputs_nested_fail_typed(fresh_db, connector_id,
                                              action_type, inputs):
    connector = get_connector(connector_id)
    contract = connector.contract_for(action_type)
    with pytest.raises(PreconditionFailed):
        connector.execute(_ctx(), contract, inputs)


# -- demo connectors: verify / compensate ------------------------------------

MALFORMED_REFS = ["x", None, ["list"], 42]


@pytest.mark.parametrize("connector_id,action_type", [
    ("demo-crm", "crm.create_organization"),
    ("demo-identity", "identity.create_workspace"),
    ("demo-support", "support.create_queue"),
    ("demo-billing", "billing.create_profile"),
    ("demo-notify", "notify.send_summary"),
])
def test_verify_malformed_resource_raises_typed(fresh_db, connector_id,
                                                action_type):
    connector = get_connector(connector_id)
    contract = connector.contract_for(action_type)
    for bad in MALFORMED_REFS:
        with pytest.raises(ConnectorError):
            connector.verify(_ctx(), contract, {}, {"resource": bad})


@pytest.mark.parametrize("connector_id,action_type", [
    ("demo-crm", "crm.create_organization"),
    ("demo-identity", "identity.create_workspace"),
    ("demo-identity", "identity.assign_manager"),
    ("demo-support", "support.create_queue"),
    ("demo-billing", "billing.create_profile"),
])
def test_compensate_malformed_ref_refused_typed(fresh_db, connector_id,
                                                action_type):
    connector = get_connector(connector_id)
    contract = connector.contract_for(action_type)
    for bad in MALFORMED_REFS:
        with pytest.raises(ConnectorError) as excinfo:
            connector.compensate(_ctx(), contract, {}, {"resource": bad})
        assert excinfo.value.code == "COMPENSATION_REFUSED"


def test_provision_users_verify_malformed_users_raises_typed(fresh_db):
    connector = get_connector("demo-identity")
    contract = connector.contract_for("identity.provision_users")
    for bad in (None, "x", 42, ["not-a-ref"], [None]):
        with pytest.raises(ConnectorError):
            connector.verify(_ctx(), contract, {}, {"users": bad})
    # A well-formed dict ref pointing nowhere reads as absent, not an error.
    assert connector.verify(_ctx(), contract, {},
                            {"users": [{"no": "id"}]}) is False


def test_provision_users_compensate_malformed_users_refused(fresh_db):
    connector = get_connector("demo-identity")
    contract = connector.contract_for("identity.provision_users")
    for bad in (None, "x", 42, ["not-a-ref"]):
        with pytest.raises(ConnectorError) as excinfo:
            connector.compensate(_ctx(), contract, {}, {"users": bad})
        assert excinfo.value.code == "COMPENSATION_REFUSED"


# -- github connector --------------------------------------------------------

def _github(handler):
    return GithubConnector(transport=httpx.MockTransport(handler),
                           allowed_repos=("o/r",))


def test_github_update_bad_issue_number_fails_typed():
    connector = _github(lambda request: httpx.Response(200, json={}))
    contract = connector.contract_for("github.update_issue")
    for bad in ("abc", {"n": 1}, ["1"], None):
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"repo": "o/r", "issue_number": bad,
                               "title": "t"})


def test_github_close_bad_issue_number_fails_typed():
    connector = _github(lambda request: httpx.Response(200, json={}))
    contract = connector.contract_for("github.close_issue")
    with pytest.raises(PreconditionFailed):
        connector.execute(_ctx(), contract,
                          {"repo": "o/r", "issue_number": "abc"})


def test_github_compensate_bad_issue_number_refused():
    def handler(request):
        return httpx.Response(200, json={"number": 1, "title": "t"})
    connector = _github(handler)
    contract = connector.contract_for("github.close_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.compensate(_ctx(), contract, {"repo": "o/r"},
                             {"issue_number": "abc"})
    assert excinfo.value.code == "COMPENSATION_REFUSED"


def test_github_malformed_api_payload_raises_typed():
    connector = _github(lambda request: httpx.Response(200, json={}))
    create = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(_ctx(), create, {"repo": "o/r", "title": "t"})
    assert excinfo.value.code == "GITHUB_MALFORMED"

    connector = _github(
        lambda request: httpx.Response(200, json={"not": "a-list"}))
    add = connector.contract_for("github.add_labels")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(_ctx(), add,
                          {"repo": "o/r", "issue_number": 1,
                           "labels": ["bug"]})
    assert excinfo.value.code == "GITHUB_MALFORMED"

    connector = _github(
        lambda request: httpx.Response(200, json=[{"no_name": 1}]))
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(_ctx(), add,
                          {"repo": "o/r", "issue_number": 1,
                           "labels": ["bug"]})
    assert excinfo.value.code == "GITHUB_MALFORMED"

    connector = _github(
        lambda request: httpx.Response(200, json=[{"number": 1}]))
    get = connector.contract_for("github.update_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(_ctx(), get,
                          {"repo": "o/r", "issue_number": 1, "title": "t"})
    assert excinfo.value.code == "GITHUB_MALFORMED"


def test_github_malformed_json_body_raises_typed():
    connector = _github(
        lambda request: httpx.Response(200, content=b"not json"))
    contract = connector.contract_for("github.create_issue")
    with pytest.raises(ConnectorError) as excinfo:
        connector.execute(_ctx(), contract, {"repo": "o/r", "title": "t"})
    assert excinfo.value.code == "GITHUB_MALFORMED"


def test_github_verify_malformed_labels_raises_typed():
    for labels in (None, ["plain-string"], [{"no_name": 1}], "bug"):
        def handler(request, labels=labels):
            return httpx.Response(200, json={"number": 1, "labels": labels})
        connector = _github(handler)
        contract = connector.contract_for("github.add_labels")
        with pytest.raises(ConnectorError):
            connector.verify(_ctx(), contract, {"repo": "o/r"},
                             {"issue_number": 1, "labels": ["bug"]})


def test_github_verify_non_list_expected_labels_raises_typed():
    def handler(request):
        return httpx.Response(200, json={"number": 1, "labels": []})
    connector = _github(handler)
    contract = connector.contract_for("github.add_labels")
    with pytest.raises(ConnectorError):
        connector.verify(_ctx(), contract, {"repo": "o/r"},
                         {"issue_number": 1, "labels": 42})


def test_github_create_nested_labels_fails_typed():
    connector = _github(lambda request: httpx.Response(200, json={}))
    contract = connector.contract_for("github.create_issue")
    for bad in ({"a": 1}, "bug", [["nested"]]):
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"repo": "o/r", "title": "t", "labels": bad})


def test_github_add_labels_nested_elements_fail_typed():
    connector = _github(lambda request: httpx.Response(200, json=[]))
    contract = connector.contract_for("github.add_labels")
    for bad in ([{"x": 1}], [["nested"]], ["ok", 42]):
        with pytest.raises(PreconditionFailed):
            connector.execute(_ctx(), contract,
                              {"repo": "o/r", "issue_number": 1,
                               "labels": bad})


def test_github_compensate_non_list_labels_refused():
    def handler(request):
        return httpx.Response(204)
    connector = _github(handler)
    contract = connector.contract_for("github.add_labels")
    for bad in ("bug", 42, {"a": 1}):
        with pytest.raises(ConnectorError) as excinfo:
            connector.compensate(_ctx(), contract, {"repo": "o/r"},
                                 {"issue_number": 1, "labels": bad})
        assert excinfo.value.code == "COMPENSATION_REFUSED"


def test_github_update_non_string_fields_fail_typed():
    connector = _github(lambda request: httpx.Response(200, json={}))
    contract = connector.contract_for("github.update_issue")
    with pytest.raises(PreconditionFailed):
        connector.execute(_ctx(), contract,
                          {"repo": "o/r", "issue_number": 1,
                           "title": {"nested": 1}})


# -- engine: malformed stored state ------------------------------------------

def test_engine_invalid_input_json_fails_typed(fresh_db, demo_auth):
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed(session, wf.id, seq=1, state="PENDING", key="k-ns-badjson",
              action_type="crm.validate_customer", connector_id="demo-crm",
              raw_input="{invalid-json")
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="w")
    assert final == "COMPENSATED"
    state, error = _action_state("k-ns-badjson")
    assert state == "FAILED"
    assert "INVALID_INPUTS" in error or "PRECONDITION_FAILED" in error


def test_engine_non_dict_inputs_fail_typed(fresh_db, demo_auth):
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed(session, wf.id, seq=1, state="PENDING", key="k-ns-nondict",
              action_type="crm.validate_customer", connector_id="demo-crm",
              raw_input="42")
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="w")
    assert final == "COMPENSATED"
    state, error = _action_state("k-ns-nondict")
    assert state == "FAILED"
    assert "INVALID_INPUTS" in error or "PRECONDITION_FAILED" in error


def test_engine_invalid_output_json_compensation_no_crash(fresh_db,
                                                          demo_auth):
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed(session, wf.id, seq=1, state="VERIFIED", key="k-ns-badout",
              action_type="crm.create_organization", connector_id="demo-crm",
              inputs={"org_slug": "acme", "company_name": "Acme"},
              raw_output="{invalid-json", attempt=1)
        _seed(session, wf.id, seq=2, state="FAILED", key="k-ns-trigger",
              action_type="crm.validate_customer", connector_id="demo-crm",
              inputs={"customer_name": "x"}, attempt=1, error="boom")
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="w")
    assert final == "PARTIALLY_COMPENSATED"
    state, _ = _action_state("k-ns-badout")
    assert state == "COMPENSATION_FAILED"


def test_engine_invalid_depends_on_skips_never_crashes(fresh_db, demo_auth):
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed(session, wf.id, seq=1, state="PENDING", key="k-ns-dep1",
              action_type="crm.validate_customer", connector_id="demo-crm",
              inputs={"customer_name": "x"})
        _seed(session, wf.id, seq=2, state="PENDING", key="k-ns-dep2",
              action_type="crm.validate_customer", connector_id="demo-crm",
              inputs={"customer_name": "y"}, depends_on="{invalid")
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="w")
    assert final == "COMPLETED"
    state, _ = _action_state("k-ns-dep2")
    assert state == "SKIPPED"


def test_engine_crashing_verify_fails_typed(fresh_db, demo_auth,
                                            monkeypatch):
    def boom(ctx, contract, inputs, output):
        raise RuntimeError("verifier exploded")

    monkeypatch.setattr(REGISTRY["demo-crm"], "verify", boom)
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed(session, wf.id, seq=1, state="PENDING", key="k-ns-boomverify",
              action_type="crm.validate_customer", connector_id="demo-crm",
              inputs={"customer_name": "x"})
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="w")
    assert final == "COMPENSATED"
    state, error = _action_state("k-ns-boomverify")
    assert state == "FAILED"
    assert "verifier crashed" in error


def test_engine_crashing_compensation_verify_no_crash(fresh_db, demo_auth,
                                                      monkeypatch):
    def boom(ctx, contract, inputs, output):
        raise RuntimeError("post-comp verify exploded")

    monkeypatch.setattr(REGISTRY["demo-crm"], "verify", boom)
    connector = get_connector("demo-crm")
    contract = connector.contract_for("crm.create_organization")
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        created = connector.execute(
            {"org_id": demo_auth["org_id"], "workflow_id": wf.id,
             "is_demo": True}, contract,
            {"org_slug": "ns-acme", "company_name": "Acme"})
        _seed(session, wf.id, seq=1, state="VERIFIED", key="k-ns-compboom",
              action_type="crm.create_organization", connector_id="demo-crm",
              inputs={"org_slug": "ns-acme", "company_name": "Acme"},
              output=created, attempt=1)
        _seed(session, wf.id, seq=2, state="FAILED", key="k-ns-comptrig",
              action_type="crm.validate_customer", connector_id="demo-crm",
              inputs={"customer_name": "x"}, attempt=1, error="boom")
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="w")
    assert final == "PARTIALLY_COMPENSATED"
    state, _ = _action_state("k-ns-compboom")
    assert state == "COMPENSATION_FAILED"


def test_engine_non_serializable_output_fails_typed(fresh_db, demo_auth,
                                                    monkeypatch):
    def bad_execute(ctx, contract, inputs):
        return {"x": object()}

    monkeypatch.setattr(REGISTRY["demo-crm"], "execute", bad_execute)
    session = session_for("main")()
    try:
        wf = _seed_wf(session, demo_auth["org_id"])
        _seed(session, wf.id, seq=1, state="PENDING", key="k-ns-badout2",
              action_type="crm.validate_customer", connector_id="demo-crm",
              inputs={"customer_name": "x"})
        session.commit()
        wf_id = wf.id
    finally:
        session.close()
    final = execute_workflow_sync(session_for("main"), wf_id, worker_id="w")
    assert final == "COMPENSATED"
    state, error = _action_state("k-ns-badout2")
    assert state == "FAILED"
    assert "INVALID_OUTPUT" in error
