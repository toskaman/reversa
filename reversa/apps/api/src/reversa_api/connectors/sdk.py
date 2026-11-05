"""Connector SDK: 16-field action contracts (spec 5.2, conflict C1), registry,
typed errors, tenant isolation, chaos fault mapping (demo tenant only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_base_s: float = 1.0
    backoff_max_s: float = 30.0


@dataclass(frozen=True)
class ActionContract:
    action_type: str
    schema_version: str
    connector_id: str
    input_schema: dict
    output_schema: dict
    preconditions: tuple[str, ...]
    effects: tuple[str, ...]
    compensation_capability: str
    timeout_s: int = 30
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    risk_level: str = "low"  # low | medium | high | critical
    approval_policy: str = "AUTO_ALLOWED"  # AUTO_ALLOWED | APPROVAL_REQUIRED | FORBIDDEN
    description: str = ""


class ConnectorError(Exception):
    """Typed connector failure."""

    def __init__(self, code: str, message: str, retryable: bool = False,
                 uncertain: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.uncertain = uncertain
        # V3-1: structured HTTP status when the error wraps an HTTP
        # response; callers must use this, never substring-sniff the message.
        self.status_code = status_code


class PreconditionFailed(ConnectorError):
    def __init__(self, message: str):
        super().__init__("PRECONDITION_FAILED", message, retryable=False)


class ChaosTriggered(ConnectorError):
    """Raised when a demo-tenant chaos rule fires. Never raised for real tenants."""


class Connector:
    id: str = ""
    store: str = ""  # demo-service sqlite store name
    capabilities: dict[str, ActionContract] | None = None

    def contract_for(self, action_type: str) -> ActionContract:
        assert self.capabilities is not None
        try:
            return self.capabilities[action_type]
        except KeyError:
            raise ConnectorError("UNKNOWN_ACTION", f"unknown action {action_type}",
                                 retryable=False) from None

    def execute(self, ctx: dict, action: ActionContract, inputs: dict) -> dict:
        raise NotImplementedError

    def verify(self, ctx: dict, action: ActionContract, inputs: dict, output: dict) -> bool:
        raise NotImplementedError

    def compensate(self, ctx: dict, action: ActionContract, inputs: dict,
                   output: dict) -> dict:
        raise NotImplementedError


REGISTRY: dict[str, Connector] = {}


def register(connector: Connector) -> None:
    REGISTRY[connector.id] = connector


def get_connector(connector_id: str) -> Connector:
    try:
        return REGISTRY[connector_id]
    except KeyError:
        raise ConnectorError("UNKNOWN_CONNECTOR", f"unknown connector {connector_id}",
                             retryable=False) from None


def capabilities_snapshot() -> list[dict]:
    out = []
    for connector in REGISTRY.values():
        assert connector.capabilities is not None
        for contract in connector.capabilities.values():
            out.append(
                {
                    "action_type": contract.action_type,
                    "connector_id": contract.connector_id,
                    "schema_version": contract.schema_version,
                    "compensation_capability": contract.compensation_capability,
                    "risk_level": contract.risk_level,
                    "approval_policy": contract.approval_policy,
                    "description": contract.description,
                }
            )
    return out


CHAOS_FAULTS = ("http500", "http429", "timeout", "malformed", "latency", "crash")


def chaos_error(connector_id: str, action_type: str, fault: str) -> ChaosTriggered:
    if fault == "http500":
        return ChaosTriggered("CHAOS_HTTP500", f"chaos: {connector_id}/{action_type} 500",
                              retryable=True)
    if fault == "http429":
        return ChaosTriggered("CHAOS_HTTP429", f"chaos: {connector_id}/{action_type} 429",
                              retryable=True)
    if fault == "timeout":
        return ChaosTriggered("CHAOS_TIMEOUT", f"chaos: {connector_id}/{action_type} timeout",
                              retryable=True, uncertain=True)
    if fault == "malformed":
        return ChaosTriggered("CHAOS_MALFORMED",
                              f"chaos: {connector_id}/{action_type} malformed response",
                              retryable=False)
    if fault == "crash":
        return ChaosTriggered("CHAOS_CRASH",
                              f"chaos: {connector_id}/{action_type} worker crash simulated",
                              retryable=True, uncertain=True)
    return ChaosTriggered("CHAOS_UNKNOWN", f"chaos: unknown fault {fault}", retryable=False)


def require_inputs_dict(inputs: Any) -> dict:
    """Return inputs iff it is a dict, else fail typed (never TypeError)."""
    if not isinstance(inputs, dict):
        raise PreconditionFailed("inputs must be an object")
    return inputs


def require_str(inputs: dict, key: str) -> str:
    """Return inputs[key] iff it is a str, else fail typed (never 500).

    Call after check_preconditions(): presence is already established, this
    guards the nested-shape case (dict/list/int where a string belongs).
    """
    require_inputs_dict(inputs)
    value = inputs.get(key)
    if not isinstance(value, str):
        raise PreconditionFailed(f"'{key}' must be a string")
    return value


def require_str_list(inputs: dict, key: str) -> list:
    """Return inputs[key] iff it is a list of str, else fail typed."""
    require_inputs_dict(inputs)
    value = inputs.get(key)
    if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value):
        raise PreconditionFailed(f"'{key}' must be a list of strings")
    return value


def require_ref(output: Any, key: str = "resource") -> dict:
    """Return output[key] iff it is a dict ref, else refuse compensation."""
    ref = output.get(key, {}) if isinstance(output, dict) else None
    if not isinstance(ref, dict):
        raise ConnectorError("COMPENSATION_REFUSED",
                             f"cannot compensate: '{key}' has no usable ref shape",
                             retryable=False)
    return ref


def check_preconditions(ctx: dict, contract: ActionContract, inputs: dict) -> None:
    """Validate declared preconditions that the engine can check generically."""
    require_inputs_dict(inputs)
    for pre in contract.preconditions:
        if pre.startswith("input_has:"):
            key = pre.split(":", 1)[1]
            if key not in inputs or inputs[key] in (None, ""):
                raise PreconditionFailed(f"missing required input '{key}'")
        elif pre == "tenant_is_demo" and not ctx.get("is_demo"):
            raise PreconditionFailed("action restricted to the demo tenant")
        elif pre == "no_real_payment" and str(inputs.get("charge_real_money", "")).lower() in (
            "1", "true", "yes"):
            raise PreconditionFailed("real payments are forbidden")
