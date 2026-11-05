"""Planner orchestration: Vultr when asked+configured, else deterministic."""

from .base import LLMProvider, PlanError, PlanResult  # noqa: F401
from .deterministic import DeterministicPlanner  # noqa: F401
from .validate import ValidationIssue, plan_hash, validate_plan  # noqa: F401
from .vultr import VultrInferenceProvider  # noqa: F401

from ..config import settings
from ..connectors.sdk import REGISTRY


def available_capabilities() -> list[dict]:
    caps = []
    for connector in REGISTRY.values():
        assert connector.capabilities is not None
        for contract in connector.capabilities.values():
            caps.append({
                "action_type": contract.action_type,
                "connector_id": contract.connector_id,
                "description": contract.description,
                "approval_policy": contract.approval_policy,
                "compensation_capability": contract.compensation_capability,
                "inputs": sorted(contract.input_schema.keys()),
            })
    return caps


def plan_from_intent(intent: str, customer: dict, use_ai: bool) -> PlanResult:
    """Plan with Vultr when requested and configured, else deterministic.

    Never raises for model issues: Vultr failures degrade to deterministic
    with an explicit warning (the demo must not depend on a key).
    """
    warnings: list[str] = []
    if use_ai and settings.vultr_api_key and settings.vultr_model:
        try:
            provider = VultrInferenceProvider(
                settings.vultr_api_key, settings.vultr_model, settings.vultr_base_url
            )
            return provider.generate(intent, customer, available_capabilities())
        except PlanError as exc:
            warnings.append(f"vultr planner failed, deterministic fallback: {exc}")
    elif use_ai:
        warnings.append("vultr inference not configured; deterministic planner used")
    result = DeterministicPlanner().generate(intent, customer, available_capabilities())
    result.warnings = warnings + result.warnings
    return result
