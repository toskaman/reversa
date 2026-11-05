"""Structured AI Protocol v5 + enriched capability registry (offline).

Covers the discriminant PLAN / CLARIFY / REFUSE envelope
(``planner/protocol_v5.py``) — in particular REFUSE (or CLARIFY) plus
action steps is always rejected — and the contract-derived capability
enrichment (``planner/capabilities_v5.py``): arg schemas, required,
enums, constraints.

Fully offline: pure parsing/enrichment, synthetic contracts, and the local
demo registry (lazy SQLite stores, no I/O at registration). No key, no
network.
"""

import pytest

from reversa_api.connectors.sdk import (
    ActionContract,
    REGISTRY,
    RetryPolicy,
)
from reversa_api.planner.capabilities_v5 import (
    available_capabilities_v5,
    capability_index,
    enrich_contract,
    enrich_contracts,
    parse_type_declaration,
    render_capabilities_block,
)
from reversa_api.planner.protocol_v5 import (
    ProtocolError,
    StructuredDecision,
    build_messages,
    expected_decision_for_gate_label,
    parse_model_response,
    parse_model_text,
)
from reversa_api.planner.validate import (
    REFUSAL_ACTION,
    REFUSAL_CODES,
    validate_plan,
)


def _contract(**overrides):
    base = {
        "action_type": "demo.test_action",
        "schema_version": "v1",
        "connector_id": "demo-test",
        "input_schema": {"org_slug": "string"},
        "output_schema": {"resource": "ref"},
        "preconditions": ("input_has:org_slug",),
        "effects": ("+test resource",),
        "compensation_capability": "COMPENSATABLE",
    }
    base.update(overrides)
    return ActionContract(**base)


def _plan_step(**overrides):
    step = {
        "action_type": "crm.validate_customer",
        "connector_id": "demo-crm",
        "inputs": {"customer_name": "Acme"},
        "depends_on": [],
    }
    step.update(overrides)
    return step


# --- PLAN branch ---

def test_plan_minimal_ok():
    decision = parse_model_response(
        {"goal": "validate", "steps": [_plan_step()]})
    assert decision.decision == "PLAN"
    assert decision.goal == "validate"
    assert len(decision.steps) == 1
    assert decision.to_steps() == [_plan_step()]


def test_plan_goal_defaults_to_empty_string():
    decision = parse_model_response({"steps": [_plan_step()]})
    assert decision.decision == "PLAN"
    assert decision.goal == ""


def test_plan_rejects_empty_steps():
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({"goal": "x", "steps": []})
    assert exc.value.code == "BAD_PLAN"


def test_plan_rejects_malformed_steps():
    for bad in (
        {"action_type": "", "connector_id": "c", "inputs": {}, "depends_on": []},
        {"action_type": "a", "connector_id": "", "inputs": {}, "depends_on": []},
        {"action_type": "a", "connector_id": "c", "inputs": [], "depends_on": []},
        {"action_type": "a", "connector_id": "c", "inputs": {}, "depends_on": [1]},
        "not-a-step",
    ):
        with pytest.raises(ProtocolError) as exc:
            parse_model_response({"steps": [bad]})
        assert exc.value.code == "BAD_PLAN"


def test_plan_allows_forward_dag_reference():
    steps = [_plan_step(),
             _plan_step(action_type="crm.create_organization",
                        inputs={"org_slug": "acme", "company_name": "Acme"},
                        depends_on=[1])]
    decision = parse_model_response({"goal": "g", "steps": steps})
    assert len(decision.to_steps()) == 2


# --- CLARIFY branch ---

def test_clarify_ok():
    decision = parse_model_response(
        {"clarify": {"message": "Which customer?",
                     "questions": ["What is the company name?"]}})
    assert decision.decision == "CLARIFY"
    assert decision.questions == ("What is the company name?",)


def test_clarify_rejects_missing_or_bad_questions():
    for questions in (None, [], ["", "  "], ["q1", "q2", "q3", "q4"], "q?"):
        with pytest.raises(ProtocolError):
            parse_model_response(
                {"clarify": {"message": "m", "questions": questions}})


def test_clarify_rejects_blank_message():
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({"clarify": {"message": "  ", "questions": ["q?"]}})
    assert exc.value.code == "BAD_CLARIFY"


# --- REFUSE branch ---

@pytest.mark.parametrize("code", sorted(REFUSAL_CODES))
def test_refuse_each_code_ok(code):
    decision = parse_model_response(
        {"refusal": {"code": code, "message": f"nope: {code}"}})
    assert decision.decision == "REFUSE"
    assert decision.code == code


def test_refuse_allows_questions_on_clarification_code_only():
    decision = parse_model_response({"refusal": {
        "code": "NEEDS_CLARIFICATION", "message": "m",
        "questions": ["Who?", "When?"]}})
    assert decision.questions == ("Who?", "When?")


@pytest.mark.parametrize("code", ["OUT_OF_SCOPE", "UNSAFE_REQUEST",
                                  "IMPOSSIBLE_REQUEST"])
def test_refuse_rejects_misplaced_questions(code):
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({"refusal": {
            "code": code, "message": "m", "questions": ["Why?"]}})
    assert exc.value.code == "BAD_REFUSAL"


def test_refuse_rejects_unknown_code():
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({"refusal": {"code": "MAYBE", "message": "m"}})
    assert exc.value.code == "UNKNOWN_REFUSAL_CODE"


def test_refuse_rejects_blank_message():
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({"refusal": {"code": "OUT_OF_SCOPE", "message": ""}})
    assert exc.value.code == "BAD_REFUSAL"


# --- discriminant: never mixed ---

def test_refuse_plus_steps_rejected():
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({
            "steps": [_plan_step()],
            "refusal": {"code": "OUT_OF_SCOPE", "message": "no"}})
    assert exc.value.code == "MIXED_DECISION"


def test_clarify_plus_steps_rejected():
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({
            "steps": [_plan_step()],
            "clarify": {"message": "m", "questions": ["q?"]}})
    assert exc.value.code == "MIXED_DECISION"


def test_refusal_plus_clarify_rejected():
    with pytest.raises(ProtocolError) as exc:
        parse_model_response({
            "refusal": {"code": "OUT_OF_SCOPE", "message": "no"},
            "clarify": {"message": "m", "questions": ["q?"]}})
    assert exc.value.code == "MIXED_DECISION"


def test_empty_and_nonenvelope_rejected():
    for bad in ({}, {"goal": "no steps"}, {"unknown": 1}):
        with pytest.raises(ProtocolError) as exc:
            parse_model_response(bad)
        assert exc.value.code == "EMPTY_DECISION"
    for bad in (None, [], "plan", 42):
        with pytest.raises(ProtocolError) as exc:
            parse_model_response(bad)
        assert exc.value.code == "BAD_ENVELOPE"


def test_parse_model_text_rejects_bad_json():
    with pytest.raises(ProtocolError) as exc:
        parse_model_text("{not json")
    assert exc.value.code == "BAD_JSON"
    decision = parse_model_text('{"refusal": {"code": "OUT_OF_SCOPE",'
                                ' "message": "off-domain"}}')
    assert decision.decision == "REFUSE"


# --- decision outputs: sentinel-only, validator-compatible ---

def test_refuse_to_steps_is_sentinel_only():
    decision = parse_model_response(
        {"refusal": {"code": "UNSAFE_REQUEST", "message": "harmful"}})
    steps = decision.to_steps()
    assert len(steps) == 1
    assert steps[0]["action_type"] == REFUSAL_ACTION
    _, _, issues = validate_plan({"steps": steps})
    assert [i.code for i in issues] == ["UNSAFE_REQUEST"]


def test_clarify_to_steps_carries_typed_code():
    decision = parse_model_response(
        {"clarify": {"message": "ambiguous", "questions": ["Which org?"]}})
    steps = decision.to_steps()
    assert steps[0]["action_type"] == REFUSAL_ACTION
    assert steps[0]["inputs"]["questions"] == ["Which org?"]
    _, _, issues = validate_plan({"steps": steps})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def test_plan_to_steps_passes_validator():
    decision = parse_model_response(
        {"goal": "g", "steps": [_plan_step()]})
    normalized, _, issues = validate_plan(
        {"steps": decision.to_steps()})
    assert issues == []
    assert normalized[0]["action_type"] == "crm.validate_customer"


def test_round_trip_payloads_stay_discriminant():
    decisions = [
        parse_model_response({"goal": "g", "steps": [_plan_step()]}),
        parse_model_response(
            {"clarify": {"message": "m", "questions": ["q?"]}}),
        parse_model_response(
            {"refusal": {"code": "OUT_OF_SCOPE", "message": "m"}}),
    ]
    for decision in decisions:
        clone = parse_model_response(decision.to_plan_payload())
        assert clone.to_dict() == decision.to_dict()


# --- gate mapping + prompt building ---

@pytest.mark.parametrize(("label", "expected"), [
    ("onboarding", "PLAN"), ("offboarding", "PLAN"), ("escalation", "PLAN"),
    ("ambiguous", "CLARIFY"), ("offscope", "REFUSE"),
])
def test_gate_label_mapping(label, expected):
    assert expected_decision_for_gate_label(label) == expected


def test_gate_label_unknown_rejected():
    with pytest.raises(ProtocolError) as exc:
        expected_decision_for_gate_label("nope")
    assert exc.value.code == "BAD_GATE_LABEL"


def test_build_messages_embeds_enriched_caps():
    caps = enrich_contracts([_contract()])
    messages = build_messages("Do the thing", {"org_slug": "acme"}, caps)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "exactly ONE decision envelope" in messages[0]["content"]
    assert "demo.test_action" in messages[1]["content"]
    assert "org_slug: string!" in messages[1]["content"]


# --- capability enrichment ---

def test_parse_type_declaration_shapes():
    assert parse_type_declaration("string")["type"] == "string"
    assert parse_type_declaration("string")["required"] is True
    optional = parse_type_declaration("string?")
    assert optional["required"] is False
    assert optional["type"] == "string"
    enum = parse_type_declaration("string? (completed|not_planned)")
    assert enum["enum"] == ["completed", "not_planned"]
    assert enum["required"] is False
    constrained = parse_type_declaration(
        "string (owner/name, must be allowlisted)")
    assert constrained["constraints"] == ["owner/name", "must be allowlisted"]
    assert constrained["required"] is True
    assert parse_type_declaration("integer")["type"] == "int"


def test_enrich_contract_required_optional_and_args():
    contract = _contract(
        input_schema={"org_slug": "string", "tier": "string", "note": "string?"},
        preconditions=("input_has:org_slug",),
    )
    enriched = enrich_contract(contract)
    assert enriched["required"] == ["org_slug"]
    assert enriched["optional"] == ["note", "tier"]
    assert enriched["args"]["org_slug"] == {"type": "string", "required": True}
    assert enriched["args"]["note"]["required"] is False


def test_enrich_contract_derives_constraints():
    enriched = enrich_contract(_contract(
        approval_policy="APPROVAL_REQUIRED",
        risk_level="high",
        compensation_capability="IRREVERSIBLE",
        preconditions=("input_has:org_slug", "tenant_is_demo",
                       "no_real_payment"),
    ))
    constraints = enriched["constraints"]
    for expected in ("demo tenant only", "no real payment, ever",
                     "requires human approval",
                     "irreversible: effect cannot be undone", "risk: high"):
        assert expected in constraints


def test_enrich_contract_github_enum_shape():
    contract = _contract(
        action_type="github.close_issue",
        connector_id="github",
        input_schema={"repo": "string (owner/name, must be allowlisted)",
                      "issue_number": "int",
                      "reason": "string? (completed|not_planned)"},
        preconditions=("input_has:repo", "input_has:issue_number"),
    )
    enriched = enrich_contract(contract)
    assert enriched["required"] == ["issue_number", "repo"]
    assert enriched["args"]["reason"]["enum"] == ["completed", "not_planned"]
    assert enriched["args"]["repo"]["constraints"] == [
        "owner/name", "must be allowlisted"]


def test_enrich_contract_provision_users_shape_hint():
    enriched = enrich_contract(_contract(
        action_type="identity.provision_users",
        connector_id="demo-identity",
        input_schema={"workspace": "string", "users": "list"},
        preconditions=("input_has:workspace", "input_has:users"),
    ))
    users = enriched["args"]["users"]
    assert "email" in users["items"]
    assert "non-empty list" in users["constraints"]


def test_enrich_contracts_sorted_and_indexed():
    contracts = [_contract(action_type="b.action"), _contract(action_type="a.action")]
    enriched = enrich_contracts(contracts)
    assert [c["action_type"] for c in enriched] == ["a.action", "b.action"]
    assert set(capability_index(enriched)) == {"a.action", "b.action"}


def test_available_capabilities_v5_uses_real_registry():
    caps = available_capabilities_v5()
    assert caps  # demo connectors registered via conftest import
    assert REGISTRY  # sanity: never empty in the test app
    by_action = capability_index(caps)
    crm = by_action["crm.create_organization"]
    assert crm["required"] == ["company_name", "org_slug"]
    assert crm["connector_id"] == "demo-crm"
    billing = by_action["billing.create_profile"]
    assert "no real payment, ever" in billing["constraints"]
    assert "requires human approval" in billing["constraints"]
    assert billing["max_attempts"] == RetryPolicy(max_attempts=2).max_attempts
    # deterministic order
    assert [c["action_type"] for c in caps] == sorted(by_action)


def test_render_capabilities_block_compact():
    caps = enrich_contracts([_contract(), _contract(
        action_type="github.close_issue",
        input_schema={"reason": "string? (completed|not_planned)"},
        preconditions=(),
        approval_policy="APPROVAL_REQUIRED",
    )])
    block = render_capabilities_block(caps)
    lines = block.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("- demo.test_action (demo-test):")
    assert "org_slug: string!" in lines[0]
    assert "reason: string=completed|not_planned?" in lines[1]
    assert "requires human approval" in lines[1]


def test_structured_decision_is_immutable_value():
    decision = StructuredDecision(decision="REFUSE", code="OUT_OF_SCOPE",
                                  message="m")
    assert decision.to_dict()["code"] == "OUT_OF_SCOPE"
    with pytest.raises(Exception):
        decision.code = "OTHER"  # frozen dataclass
