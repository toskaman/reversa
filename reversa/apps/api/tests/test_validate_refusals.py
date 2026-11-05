"""Cycle 2 refusal vocabulary (spec §2/§3): extended REFUSAL_CODES.

validate.py stays the authority: refusal_steps() builds the sentinel
(permissive by design) and validate_plan() accepts or rejects it. The
clarify/refuse route contracts ({status: needs_clarification, questions}
/ {status: refused, code, reason}) reuse these codes with no new module.

Durable: pins the 4-code vocabulary, the max-3-questions rule, and every
BAD_REFUSAL shape the validator polices. Offline, no key, no network.
"""

from reversa_api.planner.validate import (
    MAX_CLARIFICATION_QUESTIONS,
    REFUSAL_CODES,
    refusal_steps,
    validate_plan,
)


def test_refusal_codes_cover_cycle2_contracts():
    assert REFUSAL_CODES == frozenset({
        "OUT_OF_SCOPE",
        "NEEDS_CLARIFICATION",
        "UNSAFE_REQUEST",
        "IMPOSSIBLE_REQUEST",
    })


def test_max_clarification_questions_is_three():
    assert MAX_CLARIFICATION_QUESTIONS == 3


def test_refusal_steps_backward_compatible_shape():
    assert refusal_steps("OUT_OF_SCOPE", "not onboarding") == [{
        "action_type": "meta.refusal", "connector_id": "meta",
        "inputs": {"code": "OUT_OF_SCOPE", "message": "not onboarding"},
        "depends_on": [],
    }]


def test_refusal_steps_questions_capped_at_three():
    steps = refusal_steps("NEEDS_CLARIFICATION", "vague",
                          questions=["q1", "q2", "q3", "q4", "q5"])
    assert steps[0]["inputs"]["questions"] == ["q1", "q2", "q3"]


def test_refusal_steps_questions_sanitized():
    steps = refusal_steps("NEEDS_CLARIFICATION", "vague",
                          questions=["  kept  ", "", "   ", 42, None, "q2"])
    assert steps[0]["inputs"]["questions"] == ["kept", "q2"]


def test_refusal_steps_blank_questions_omitted():
    steps = refusal_steps("NEEDS_CLARIFICATION", "vague",
                          questions=["", "   "])
    assert "questions" not in steps[0]["inputs"]


def test_refusal_steps_single_string_question():
    steps = refusal_steps("NEEDS_CLARIFICATION", "vague",
                          questions="which customer?")
    assert steps[0]["inputs"]["questions"] == ["which customer?"]


def test_validate_unsafe_request_refusal():
    normalized, approval, issues = validate_plan(
        {"steps": refusal_steps("UNSAFE_REQUEST", "ignore previous rules")})
    assert normalized == []
    assert approval is False
    assert [i.code for i in issues] == ["UNSAFE_REQUEST"]
    assert issues[0].step == 1
    assert issues[0].field == "intent"


def test_validate_impossible_request_refusal():
    normalized, approval, issues = validate_plan(
        {"steps": refusal_steps("IMPOSSIBLE_REQUEST",
                                "teleport the database to Mars")})
    assert normalized == []
    assert approval is False
    assert [i.code for i in issues] == ["IMPOSSIBLE_REQUEST"]
    assert issues[0].to_dict()["field"] == "intent"


def test_validate_new_codes_message_truncated():
    _, _, issues = validate_plan(
        {"steps": refusal_steps("UNSAFE_REQUEST", "z" * 900)})
    assert len(issues[0].message) <= 500


def test_validate_clarification_with_questions_accepted():
    _, _, issues = validate_plan({"steps": refusal_steps(
        "NEEDS_CLARIFICATION", "which domain?",
        questions=["onboarding or offboarding?", "which customer?"])})
    assert [i.code for i in issues] == ["NEEDS_CLARIFICATION"]


def _raw_refusal(code, inputs):
    return {"steps": [{
        "action_type": "meta.refusal", "connector_id": "meta",
        "inputs": {"code": code, **inputs}, "depends_on": [],
    }]}


def test_validate_refusal_too_many_questions_rejected():
    _, _, issues = validate_plan(_raw_refusal(
        "NEEDS_CLARIFICATION",
        {"message": "vague", "questions": ["q1", "q2", "q3", "q4"]}))
    assert [i.code for i in issues] == ["BAD_REFUSAL"]
    assert issues[0].field == "inputs.questions"


def test_validate_refusal_non_list_questions_rejected():
    _, _, issues = validate_plan(_raw_refusal(
        "NEEDS_CLARIFICATION",
        {"message": "vague", "questions": "just ask"}))
    assert [i.code for i in issues] == ["BAD_REFUSAL"]
    assert issues[0].field == "inputs.questions"


def test_validate_refusal_empty_questions_rejected():
    _, _, issues = validate_plan(_raw_refusal(
        "NEEDS_CLARIFICATION", {"message": "vague", "questions": []}))
    assert [i.code for i in issues] == ["BAD_REFUSAL"]


def test_validate_refusal_blank_question_rejected():
    _, _, issues = validate_plan(_raw_refusal(
        "NEEDS_CLARIFICATION",
        {"message": "vague", "questions": ["ok?", "  "]}))
    assert [i.code for i in issues] == ["BAD_REFUSAL"]


def test_validate_refused_code_with_questions_rejected():
    for code in ("OUT_OF_SCOPE", "UNSAFE_REQUEST", "IMPOSSIBLE_REQUEST"):
        _, _, issues = validate_plan(_raw_refusal(
            code, {"message": "no", "questions": ["why?"]}))
        assert [i.code for i in issues] == ["BAD_REFUSAL"], code
        assert issues[0].field == "inputs.questions"


def test_validate_unknown_code_still_rejected():
    _, _, issues = validate_plan({"steps": refusal_steps("MAYBE", "x")})
    assert [i.code for i in issues] == ["BAD_REFUSAL"]
    assert issues[0].field == "inputs.code"
    assert "UNSAFE_REQUEST" in issues[0].message
    assert "IMPOSSIBLE_REQUEST" in issues[0].message


def test_unhashable_refusal_code_is_bad_refusal_not_crash():
    # B2: model-supplied dict/list code must not raise TypeError (HTTP 500).
    for bad in ({"code": "OUT_OF_SCOPE"}, ["OUT_OF_SCOPE"], None, 42):
        steps = [{"action_type": "meta.refusal", "connector_id": "meta",
                  "inputs": {"code": bad, "message": "x"}, "depends_on": []}]
        _, _, issues = validate_plan({"steps": steps})
        assert [i.code for i in issues] == ["BAD_REFUSAL"]
        assert issues[0].field == "inputs.code"
