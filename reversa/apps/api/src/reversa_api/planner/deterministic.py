"""Deterministic baseline planner: template matcher, no network, no key."""

from __future__ import annotations

import importlib
import re
import time

from ..templates.onboarding import DEMO_CUSTOMER, build_onboarding_plan
from .base import LLMProvider, PlanResult


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "acme"


# Cycle 2 template wiring (spec §4): gate domain label -> (module, builder).
# Soft imports: offboarding/escalation land from sibling branches; while a
# module is absent the planner falls back to onboarding with an explicit
# warning instead of failing (same pattern as the route's gate soft import).
_TEMPLATE_BUILDERS = {
    "offboarding": ("reversa_api.templates.offboarding", "build_offboarding_plan"),
    "escalation": ("reversa_api.templates.escalation", "build_escalation_plan"),
}


def _cycle2_domain(intent: str, capabilities: list[dict] | None) -> str | None:
    """Gate domain label for ``intent``, or None when unavailable.

    Returns only routable domain labels (onboarding/offboarding/
    escalation). None covers both a missing gate module (sibling branch
    not merged) and non-domain labels (ambiguous/offscope/unknown): the
    caller keeps the legacy onboarding behavior and the route owns
    clarify/refuse, so direct planner callers never see a contract shape.
    """
    try:
        module = importlib.import_module("reversa_api.planner.intent")
    except ImportError:
        return None
    label = module.classify_intent(intent, capabilities).label
    if label in _TEMPLATE_BUILDERS or label == "onboarding":
        return label
    return None


def _template_builder(label: str | None):
    """Builder for a domain label; None when its module has not landed."""
    if not label or label not in _TEMPLATE_BUILDERS:
        return build_onboarding_plan
    mod_name, attr = _TEMPLATE_BUILDERS[label]
    try:
        return getattr(importlib.import_module(mod_name), attr)
    except (ImportError, AttributeError):
        return None


class DeterministicPlanner(LLMProvider):
    name = "deterministic"

    def generate(self, intent: str, customer: dict, capabilities: list[dict]) -> PlanResult:
        started = time.perf_counter()
        merged = {**DEMO_CUSTOMER, **(customer or {})}
        quoted = re.search(r'"([^"]{2,60})"', intent)
        m = re.search(r"\bfor\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})", intent)
        company = None
        if quoted:
            company = quoted.group(1)
        elif m:
            company = m.group(1)
        if company and "customer" not in (customer or {}) and customer.get("company_name") in (None, ""):
            merged["company_name"] = company
            merged["org_slug"] = _slugify(company)
        domain = _cycle2_domain(intent, capabilities)
        builder = _template_builder(domain)
        warnings: list[str] = []
        if builder is None:
            # Sibling template not merged yet: stay executable, say so.
            builder = build_onboarding_plan
            warnings.append(f"{domain} template unavailable; default template used")
        elif domain is None and not self._looks_onboarding(intent):
            warnings.append(
                "intent does not clearly match onboarding; default template used"
            )
        steps = builder(merged)
        return PlanResult(
            steps=steps,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            warnings=warnings,
        )

    @staticmethod
    def _looks_onboarding(intent: str) -> bool:
        low = intent.lower()
        return any(w in low for w in ("onboard", "customer", "workspace", "provision",
                                      "enterprise", "acme", "recruit", "hire", "employee"))
