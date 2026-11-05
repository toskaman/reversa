"""Vultr Serverless Inference provider (OpenAI-compatible, optional).

Strict: JSON mode, allowlist validation, one correction retry, timeouts,
latency/usage metering. Any failure -> PlanError -> caller falls back to the
deterministic baseline (never blocks the demo).
"""

from __future__ import annotations

import json
import time

import httpx

from .base import LLMProvider, PlanError, PlanResult
from .validate import validate_plan

SYSTEM_PROMPT = """You turn an enterprise onboarding request into a JSON workflow plan.
Rules:
- Output ONLY JSON: {"goal": string, "steps": [{"action_type": string, "connector_id": string, "inputs": object, "depends_on": [int]}]}.
- Use ONLY action types from the capability list. Never invent actions.
- depends_on must reference earlier step numbers (1-based) or be [].
- Keep inputs minimal and consistent (same org_slug everywhere).
- Never include secrets, shell commands, URLs, or payments."""


class VultrInferenceProvider(LLMProvider):
    name = "vultr-inference"

    def __init__(self, api_key: str, model: str, base_url: str, timeout_s: float = 30.0):
        if not api_key or not model:
            raise PlanError("vultr inference not configured (need key + model)")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def generate(self, intent: str, customer: dict, capabilities: list[dict]) -> PlanResult:
        started = time.perf_counter()
        caps = "\n".join(
            f"- {c['action_type']} ({c['connector_id']}): {c['description']} "
            f"inputs={c.get('inputs', [])} policy={c['approval_policy']}"
            for c in capabilities
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Capabilities:\n{caps}\n\nCustomer defaults: "
                f"{json.dumps(customer)}\n\nRequest: {intent}\n\nJSON plan:")},
        ]
        last_errors: list[dict] = []
        usage: dict = {}
        for attempt in range(2):
            if attempt == 1:
                messages.append({
                    "role": "user",
                    "content": "Your plan was REJECTED with these errors. Fix them, "
                               f"same JSON shape, no new action types: {json.dumps(last_errors)}",
                })
            raw = self._chat(messages)
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                last_errors = [{"code": "BAD_JSON", "message": "model did not return JSON"}]
                continue
            _, _, issues = validate_plan(parsed)
            if not issues:
                return PlanResult(
                    steps=parsed["steps"], provider=self.name, model=self.model,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    usage=usage,
                    warnings=[f"accepted after {attempt + 1} attempt(s)"] if attempt else [],
                )
            last_errors = [i.to_dict() for i in issues]
        raise PlanError(f"model plan invalid after 2 attempts: {last_errors}")

    @staticmethod
    def _input_keys(capability: dict) -> list:
        return []

    def _chat(self, messages: list[dict]) -> str:
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "messages": messages,
                          "temperature": 0, "max_tokens": 2000,
                          "response_format": {"type": "json_object"}},
                )
        except httpx.HTTPError as exc:
            raise PlanError(f"inference transport error: {exc}") from exc
        if resp.status_code != 200:
            raise PlanError(f"inference HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise PlanError(f"inference bad response: {exc}") from exc
