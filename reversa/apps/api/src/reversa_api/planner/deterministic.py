"""Deterministic baseline planner: template matcher, no network, no key."""

from __future__ import annotations

import re
import time

from ..templates.onboarding import DEMO_CUSTOMER, build_onboarding_plan
from .base import LLMProvider, PlanResult


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "acme"


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
        steps = build_onboarding_plan(merged)
        return PlanResult(
            steps=steps,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            warnings=[] if self._looks_onboarding(intent) else [
                "intent does not clearly match onboarding; default template used"
            ],
        )

    @staticmethod
    def _looks_onboarding(intent: str) -> bool:
        low = intent.lower()
        return any(w in low for w in ("onboard", "customer", "workspace", "provision",
                                      "enterprise", "acme", "recruit", "hire", "employee"))
