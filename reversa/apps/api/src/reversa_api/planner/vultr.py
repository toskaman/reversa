"""Vultr Serverless Inference provider (OpenAI-compatible, optional).

Strict: JSON mode, allowlist validation, one correction retry, timeouts,
latency/usage metering. Any failure -> PlanError -> caller falls back to the
deterministic baseline (never blocks the demo).

Metering contract (every call, success or failure):
- ``PlanResult.latency_ms`` is always set (int, >= 0).
- ``PlanResult.usage`` always carries ``prompt_tokens`` / ``completion_tokens``
  / ``total_tokens`` (summed across attempts), ``attempts`` (number of chat
  calls), ``model_requested`` vs ``model_returned``, and the
  ``model_substituted`` flag.
- ``PlanResult.model`` is the model that actually served the plan (the
  response ``model`` field), falling back to the requested model when the
  API omits it. A substitution adds an explicit warning.
- On failure the raised ``PlanError`` carries the same snapshot as
  ``exc.latency_ms`` / ``exc.usage`` attributes so callers can meter errors.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

import httpx

from .base import LLMProvider, PlanError, PlanResult
from .validate import validate_plan

SYSTEM_PROMPT = """You turn an enterprise onboarding request into a JSON workflow plan.
Rules:
- Output ONLY JSON: {"goal": string, "steps": [{"action_type": string, "connector_id": string, "inputs": object, "depends_on": [int]}]}.
- Use ONLY action types from the capability list. Never invent actions.
- depends_on must reference earlier step numbers (1-based) or be [].
- Keep inputs minimal and consistent (same org_slug everywhere).
- identity.provision_users inputs.users must be a LIST of {"email": string,
  "name": string} objects. Expand any headcount into explicit objects (e.g.
  6 users -> 6 objects with emails like user1@example.com). Never emit a
  bare number or bare strings for users.
- Never include secrets, shell commands, URLs, or payments."""


@dataclass
class _ChatCompletion:
    """One parsed chat-completions reply: content + metering metadata."""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class VultrInferenceProvider(LLMProvider):
    name = "vultr-inference"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout_s: float = 30.0,
        client_factory: Callable[[], AbstractContextManager] | None = None,
    ):
        if not api_key or not model:
            raise PlanError("vultr inference not configured (need key + model)")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        # Injectable for offline tests: a zero-arg factory returning a
        # context manager with a ``post(url, headers, json)`` method.
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=self.timeout_s)
        )

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
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        models_returned: list[str] = []
        attempts = 0

        def _elapsed_ms() -> int:
            return int((time.perf_counter() - started) * 1000)

        def _usage_snapshot() -> dict:
            returned = models_returned[-1] if models_returned else self.model
            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "attempts": attempts,
                "model_requested": self.model,
                "model_returned": returned,
                "model_substituted": returned != self.model,
            }

        def _metered_error(message: str) -> PlanError:
            err = PlanError(message)
            # Attributes, not ctor args: PlanError lives in base.py and stays
            # a plain Exception so other providers are unaffected.
            err.latency_ms = _elapsed_ms()  # type: ignore[attr-defined]
            err.usage = _usage_snapshot()  # type: ignore[attr-defined]
            return err

        for attempt in range(2):
            if attempt == 1:
                messages.append({
                    "role": "user",
                    "content": "Your plan was REJECTED with these errors. Fix them, "
                               f"same JSON shape, no new action types: {json.dumps(last_errors)}",
                })
            attempts += 1
            try:
                chat = self._chat(messages)
            except PlanError as exc:
                exc.latency_ms = _elapsed_ms()  # type: ignore[attr-defined]
                exc.usage = _usage_snapshot()  # type: ignore[attr-defined]
                raise
            prompt_tokens += chat.prompt_tokens
            completion_tokens += chat.completion_tokens
            total_tokens += chat.total_tokens
            models_returned.append(chat.model)
            try:
                parsed = json.loads(chat.content)
            except (json.JSONDecodeError, TypeError):
                last_errors = [{"code": "BAD_JSON", "message": "model did not return JSON"}]
                continue
            _, _, issues = validate_plan(parsed)
            if not issues:
                usage = _usage_snapshot()
                warnings = (
                    [f"accepted after {attempt + 1} attempt(s)"] if attempt else []
                )
                if usage["model_substituted"]:
                    warnings.append(
                        "model substitution: requested "
                        f"{usage['model_requested']}, served {usage['model_returned']}"
                    )
                return PlanResult(
                    steps=parsed["steps"], provider=self.name, model=usage["model_returned"],
                    latency_ms=_elapsed_ms(),
                    usage=usage,
                    warnings=warnings,
                )
            last_errors = [i.to_dict() for i in issues]
        raise _metered_error(f"model plan invalid after 2 attempts: {last_errors}")

    def _chat(self, messages: list[dict]) -> _ChatCompletion:
        try:
            with self._client_factory() as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "messages": messages,
                          # 8000: reasoning models spend most tokens thinking;
                          # 2000 truncated plans mid-JSON (measured live).
                          "temperature": 0, "max_tokens": 8000,
                          "response_format": {"type": "json_object"}},
                )
        except httpx.HTTPError as exc:
            raise PlanError(f"inference transport error: {exc}") from exc
        if resp.status_code != 200:
            raise PlanError(f"inference HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise PlanError(f"inference bad response: {exc}") from exc
        raw_usage = data.get("usage", {}) or {} if isinstance(data, dict) else {}
        prompt = _safe_int(raw_usage.get("prompt_tokens"))
        completion = _safe_int(raw_usage.get("completion_tokens"))
        total = raw_usage.get("total_tokens")
        total = _safe_int(total) if total is not None else prompt + completion
        model_returned = (
            data.get("model") or self.model if isinstance(data, dict) else self.model
        )
        return _ChatCompletion(
            content=content, model=model_returned,
            prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
        )
