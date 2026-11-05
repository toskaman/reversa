"""Offline behavioral fakes for the v5 decisional harness.

No key, no network, no clock: each fake maps the casebook intent to a
scripted provider output so the 4 stages can be scored deterministically.
Fakes take the case list in their constructor (never import the casebook
themselves) and expose ``provider_name`` for report labels.
"""

from __future__ import annotations

from reversa_api.planner.base import LLMProvider, PlanError, PlanResult
from reversa_api.planner.validate import refusal_steps
from reversa_api.templates.onboarding import build_onboarding_plan

from .decisions import CATEGORY_REFUSAL_CODE, EXPECTED_CONTRACT


class _CasedFake(LLMProvider):
    name = "cased-fake"

    def __init__(self, cases: list[tuple[str, str, str]]):
        self._categories = {intent: cat for _, intent, cat in cases}
        self.provider_name = self.name

    def _category_of(self, intent: str) -> str:
        try:
            return self._categories[intent]
        except KeyError:
            raise PlanError(f"fake has no script for intent {intent[:60]!r}") from None

    def _plan(self) -> PlanResult:
        return PlanResult(steps=build_onboarding_plan(), provider=self.name)

    def _contract(self, category: str) -> PlanResult:
        contract = EXPECTED_CONTRACT[category]
        if contract == "plan":
            return self._plan()
        code = CATEGORY_REFUSAL_CODE[category]
        return PlanResult(
            steps=refusal_steps(code, f"{contract}: {category}"),
            provider=self.name,
        )


class ContractFake(_CasedFake):
    """Ideal agentic planner: plans legit, clarifies, refuses with codes."""

    name = "contract-fake"

    def generate(self, intent, customer, capabilities) -> PlanResult:
        return self._contract(self._category_of(intent))


class NaiveFake(_CasedFake):
    """Follows injection intents with an invented tool (must be caught)."""

    name = "naive-fake"

    def generate(self, intent, customer, capabilities) -> PlanResult:
        if self._category_of(intent) == "injection":
            return PlanResult(
                steps=[{"action_type": "shell.exec",
                        "connector_id": "demo-crm",
                        "inputs": {"cmd": intent[:40]}, "depends_on": []}],
                provider=self.name,
            )
        return self._plan()


class FlakyFake(_CasedFake):
    """Raises on impossible (exception path: never correction-retried)."""

    name = "flaky-fake"

    def generate(self, intent, customer, capabilities) -> PlanResult:
        if self._category_of(intent) == "impossible":
            raise PlanError("simulated outage")
        return self._plan()


class LegitFlakyFake(_CasedFake):
    """Raises on legit (gate-routed) cases: proves the fallback rescues."""

    name = "legit-flaky-fake"

    def generate(self, intent, customer, capabilities) -> PlanResult:
        if self._category_of(intent) == "legit":
            raise PlanError("simulated outage on legit")
        return self._plan()


class EmptyRefusalFake(_CasedFake):
    """Legacy refusal-by-omission: [] on policy-violating categories."""

    name = "empty-refusal-fake"
    REFUSE_CATEGORIES = frozenset(
        {"dangerous", "injection", "impossible", "contradictory"})

    def generate(self, intent, customer, capabilities) -> PlanResult:
        if self._category_of(intent) in self.REFUSE_CATEGORIES:
            return PlanResult(steps=[], provider=self.name,
                              warnings=["refused by omission"])
        return self._plan()


class ScriptedCorrectionFake(_CasedFake):
    """Invalid first attempt, contract-correct on regenerate().

    Models the Vultr one-retry mechanics offline: ``generate`` always emits
    an invented tool (error at model_only), ``regenerate`` returns the
    contract-correct output (recovered at corrected+). ``regen_calls``
    records every correction call for assertions.
    """

    name = "scripted-correction-fake"

    def __init__(self, cases):
        super().__init__(cases)
        self.regen_calls: list[str] = []

    def generate(self, intent, customer, capabilities) -> PlanResult:
        self._category_of(intent)  # raise on unscripted, like the others
        return PlanResult(
            steps=[{"action_type": "shell.exec", "connector_id": "demo-crm",
                    "inputs": {"cmd": "first-attempt"}, "depends_on": []}],
            provider=self.name,
        )

    def regenerate(self, intent, customer, capabilities, issues) -> PlanResult:
        assert isinstance(issues, str) and issues, "typed issues required"
        self.regen_calls.append(intent)
        return self._contract(self._category_of(intent))
