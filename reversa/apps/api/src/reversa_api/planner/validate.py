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


@dataclass
class ValidationIssue:
    code: str
    step: int
    field: str
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "step": self.step, "field": self.field,
                "message": self.message}


def validate_plan(plan: dict) -> tuple[list[dict], bool, list[ValidationIssue]]:
    """Returns (normalized_steps, approval_required, issues). Issues empty == valid."""
    issues: list[ValidationIssue] = []
    raw_steps = plan.get("steps", []) if isinstance(plan, dict) else []
    if not isinstance(raw_steps, list) or not raw_steps:
        return [], False, [ValidationIssue("EMPTY_PLAN", 0, "steps", "plan has no steps")]
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
            not isinstance(d, int) or d < 1 or d >= i for d in depends_on
        ):
            issues.append(ValidationIssue(
                "BAD_DEPS", i, "depends_on",
                "depends_on must list earlier step numbers (strictly increasing DAG)"))
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
            elif expected is not None and not isinstance(inputs[key], expected):
                issues.append(ValidationIssue(
                    "BAD_INPUT_TYPE", i, f"inputs.{key}",
                    f"'{key}' must be {typename}"))
        if (action_type == "identity.provision_users"
                and isinstance(inputs.get("users"), list)):
            for j, user in enumerate(inputs["users"]):
                if (not isinstance(user, dict)
                        or not isinstance(user.get("email"), str)
                        or not user["email"].strip()):
                    issues.append(ValidationIssue(
                        "BAD_INPUT_TYPE", i, f"inputs.users[{j}]",
                        "'users' elements must be objects with a non-empty 'email'"))
                    break
        normalized.append({
            "seq": i,
            "action_type": action_type,
            "connector_id": connector_id,
            "inputs": inputs,
            "depends_on": depends_on,
            "compensation_capability": contract.compensation_capability,
            "max_attempts": contract.retry_policy.max_attempts,
            "approval_policy": contract.approval_policy,
            "risk_level": contract.risk_level,
        })
    return normalized, approval_required, issues


def plan_hash(normalized_steps: list[dict]) -> str:
    return hashlib.sha256(canonical_bytes({"steps": normalized_steps})).hexdigest()
