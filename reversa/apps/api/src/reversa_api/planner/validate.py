"""Plan validation: allowlist, DAG, input types, policy. Engine-grade strictness."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ..connectors.sdk import ConnectorError, get_connector
from ..evidence import canonical_bytes

TYPE_CHECKS = {
    "string": str,
    "list": list,
    "dict": dict,
    "bool": bool,
    "int": int,
}


def _type_matches(value, typename: str, expected: type) -> bool:
    if not isinstance(value, expected):
        return False
    # RT-V5-10: bool subclasses int, but True/False are not valid ints.
    if typename == "int" and isinstance(value, bool):
        return False
    return True


@dataclass
class ValidationIssue:
    code: str
    step: int
    field: str
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "step": self.step, "field": self.field,
                "message": self.message}


# Structured refusal (agentic): a provider that cannot plan safely emits a
# sentinel step instead of inventing actions. validate_plan translates it
# into a typed ValidationIssue, so the existing 422 PLAN_REJECTED path
# carries OUT_OF_SCOPE / NEEDS_CLARIFICATION with no route change.
#
# Cycle 2 contracts (spec 2026-11-05-cycle2-agentic-design.md §2/§3):
# ambiguous intents answer HTTP 200 {status: needs_clarification,
# questions} and off-scope intents answer {status: refused, code, reason}
# with no workflow created. Both reuse this module: REFUSAL_CODES is the
# contract vocabulary, refusal_steps() builds the sentinel, and
# validate_plan() stays the authority that accepts or rejects it.
REFUSAL_ACTION = "meta.refusal"
REFUSAL_CONNECTOR = "meta"
# Code -> intent-gate offscope sub-reason / eval category:
# - OUT_OF_SCOPE: off-domain or no actionable signal.
# - UNSAFE_REQUEST: injection, policy violation, destructive or
#   exfiltration phrasing. Never plannable, never clarified.
# - IMPOSSIBLE_REQUEST: shaped like a request but unfulfillable with
#   real capabilities (teleport, time travel, negative users).
# - NEEDS_CLARIFICATION: ambiguous; may carry clarification questions.
REFUSAL_CODES = frozenset({
    "OUT_OF_SCOPE",
    "NEEDS_CLARIFICATION",
    "UNSAFE_REQUEST",
    "IMPOSSIBLE_REQUEST",
})

# Spec §2: a clarification answer carries at most 3 targeted questions.
MAX_CLARIFICATION_QUESTIONS = 3
# RT-V5-05: a single step must not seed thousands of resources (legit
# onboarding provisions a handful of users; templates use 2).
MAX_PROVISION_USERS = 100
MAX_USER_EMAIL_LEN = 254
# RT-V5-05b: bound the plan itself (flagship onboarding is 10 steps;
# 32 leaves wide headroom while capping executor fan-out).
MAX_PLAN_STEPS = 32


def refusal_steps(
    code: str,
    message: str,
    questions: list[str] | tuple[str, ...] | str | None = None,
) -> list[dict]:
    """Build the sentinel step list encoding a structured refusal.

    ``questions`` (NEEDS_CLARIFICATION only) is sanitized
    deterministically: non-string/blank entries dropped, stripped, capped
    at MAX_CLARIFICATION_QUESTIONS; omitted from inputs when empty.

    The constructor stays permissive by design (unknown codes, misplaced
    questions) — validate_plan() is the authority that rejects them.
    """
    inputs: dict = {"code": code, "message": message}
    if questions:
        if isinstance(questions, str):
            questions = [questions]
        kept = [q.strip() for q in questions
                if isinstance(q, str) and q.strip()]
        kept = kept[:MAX_CLARIFICATION_QUESTIONS]
        if kept:
            inputs["questions"] = kept
    return [{
        "action_type": REFUSAL_ACTION,
        "connector_id": REFUSAL_CONNECTOR,
        "inputs": inputs,
        "depends_on": [],
    }]


def validate_plan(plan: dict) -> tuple[list[dict], bool, list[ValidationIssue]]:
    """Returns (normalized_steps, approval_required, issues). Issues empty == valid."""
    issues: list[ValidationIssue] = []
    raw_steps = plan.get("steps", []) if isinstance(plan, dict) else []
    if not isinstance(raw_steps, list) or not raw_steps:
        return [], False, [ValidationIssue("EMPTY_PLAN", 0, "steps", "plan has no steps")]
    if len(raw_steps) > MAX_PLAN_STEPS:
        return [], False, [ValidationIssue(
            "TOO_MANY_STEPS", 0, "steps",
            f"plan has at most {MAX_PLAN_STEPS} steps")]
    normalized: list[dict] = []
    approval_required = False
    for i, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            issues.append(ValidationIssue("BAD_STEP", i, "", "step must be an object"))
            continue
        action_type = raw.get("action_type", "")
        connector_id = raw.get("connector_id", "")
        inputs = raw.get("inputs", {})
        depends_on = raw.get("depends_on", [])
        if not isinstance(inputs, dict):
            issues.append(ValidationIssue("BAD_INPUTS", i, "inputs", "inputs must be an object"))
            continue
        if not isinstance(depends_on, list) or any(
            type(d) is not int or d < 1 or d >= i for d in depends_on
        ):
            issues.append(ValidationIssue(
                "BAD_DEPS", i, "depends_on",
                "depends_on must list earlier step numbers (strictly increasing DAG)"))
            continue
        if action_type == REFUSAL_ACTION:
            code = inputs.get("code", "")
            message = inputs.get("message", "")
            questions = inputs.get("questions")
            if not isinstance(code, str) or code not in REFUSAL_CODES:
                issues.append(ValidationIssue(
                    "BAD_REFUSAL", i, "inputs.code",
                    f"refusal code must be one of {sorted(REFUSAL_CODES)}"))
            elif questions is not None and (
                    code != "NEEDS_CLARIFICATION"
                    or not isinstance(questions, list)
                    or not 1 <= len(questions) <= MAX_CLARIFICATION_QUESTIONS
                    or any(not isinstance(q, str) or not q.strip()
                           for q in questions)):
                issues.append(ValidationIssue(
                    "BAD_REFUSAL", i, "inputs.questions",
                    "refusal questions must be a list of 1.."
                    f"{MAX_CLARIFICATION_QUESTIONS} non-empty strings "
                    "on NEEDS_CLARIFICATION only"))
            else:
                issues.append(ValidationIssue(
                    code, i, "intent",
                    str(message)[:500] or f"planner refused: {code}"))
            continue
        try:
            connector = get_connector(connector_id)
            contract = connector.contract_for(action_type)
        except ConnectorError as exc:
            issues.append(ValidationIssue("UNKNOWN_CAPABILITY", i, "action_type",
                                          f"{exc.code}: {exc}"))
            continue
        if contract.connector_id != connector_id:
            issues.append(ValidationIssue("CONNECTOR_MISMATCH", i, "connector_id",
                                          f"{action_type} belongs to {contract.connector_id}"))
            continue
        if contract.approval_policy == "FORBIDDEN":
            issues.append(ValidationIssue("FORBIDDEN_ACTION", i, "action_type",
                                          f"{action_type} is forbidden by policy"))
            continue
        if contract.approval_policy == "APPROVAL_REQUIRED":
            approval_required = True
        for key, typename in contract.input_schema.items():
            expected = TYPE_CHECKS.get(typename)
            if key not in inputs:
                issues.append(ValidationIssue("MISSING_INPUT", i, f"inputs.{key}",
                                              f"missing required input '{key}'"))
            elif expected is not None and not _type_matches(
                    inputs[key], typename, expected):
                issues.append(ValidationIssue(
                    "BAD_INPUT_TYPE", i, f"inputs.{key}",
                    f"'{key}' must be {typename}"))
        if (action_type == "identity.provision_users"
                and isinstance(inputs.get("users"), list)):
            # P0-3 parity: the executor rejects an empty list
            # (PreconditionFailed); fail fast here with a 422 instead.
            if not inputs["users"]:
                issues.append(ValidationIssue(
                    "BAD_INPUT_TYPE", i, "inputs.users",
                    "'users' must be a non-empty list"))
            elif len(inputs["users"]) > MAX_PROVISION_USERS:
                issues.append(ValidationIssue(
                    "TOO_MANY_USERS", i, "inputs.users",
                    f"'users' must have at most {MAX_PROVISION_USERS} entries"))
                continue
            for j, user in enumerate(inputs["users"]):
                if (not isinstance(user, dict)
                        or not isinstance(user.get("email"), str)
                        or not user["email"].strip()
                        or len(user["email"]) > MAX_USER_EMAIL_LEN):
                    issues.append(ValidationIssue(
                        "BAD_INPUT_TYPE", i, f"inputs.users[{j}]",
                        "'users' elements must be objects with a non-empty 'email'"))
                    break
        normalized.append({
            "seq": i,
            "action_type": action_type,
            "connector_id": connector_id,
            "inputs": {k: v for k, v in inputs.items() if k in contract.input_schema},
            "depends_on": depends_on,
            "compensation_capability": contract.compensation_capability,
            "max_attempts": contract.retry_policy.max_attempts,
            "approval_policy": contract.approval_policy,
            "risk_level": contract.risk_level,
        })
    return normalized, approval_required, issues


def plan_hash(normalized_steps: list[dict]) -> str:
    return hashlib.sha256(canonical_bytes({"steps": normalized_steps})).hexdigest()
