"""Planner provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PlanResult:
    steps: list[dict]
    provider: str
    model: str = ""
    latency_ms: int = 0
    usage: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class PlanError(Exception):
    pass


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(self, intent: str, customer: dict, capabilities: list[dict]) -> PlanResult:
        """Turn a natural-language intent into plan steps (unvalidated)."""
