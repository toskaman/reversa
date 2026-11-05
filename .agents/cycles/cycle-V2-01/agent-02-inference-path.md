# AGENT-02 — Vultr Inference Activation Path (REVERSA V2 cycle 1)

Date: 2026-11-05. Role: AI Integration Engineer.
Mandate: research LEGITIMATE activation only. No brute-force attempted, no secrets committed, no pushes.

## 1. Sources actually read

- https://api.vultrinference.com/docs/get-started/authentication (fetched, HTTP 200)
- https://api.vultrinference.com/docs/get-started/quickstart (fetched, HTTP 200)
- Live probe: unauthenticated `GET https://api.vultrinference.com/v1/models` → HTTP 200 (public endpoint, needs no key)
- Repo files read in full:
  - `reversa/apps/api/src/reversa_api/planner/base.py`
  - `reversa/apps/api/src/reversa_api/planner/vultr.py`
  - `reversa/apps/api/src/reversa_api/planner/deterministic.py`
  - `reversa/apps/api/src/reversa_api/planner/validate.py`
  - `reversa/apps/api/src/reversa_api/planner/__init__.py`
  - `reversa/apps/api/src/reversa_api/config.py`
  - `reversa/apps/api/tests/test_ai_eval.py`
- Call-site search (regex) for `plan_from_intent|VULTR_INFERENCE_API_KEY|VultrInferenceProvider` across the repo.

## 2. Vultr Inference auth — documented facts

From the authentication doc:

- One API key per request, sent as either `Authorization: Bearer <key>` (capital B) or `x-api-key: <key>`.
  Both work on every route; if both present, `Authorization` wins.
- Keys are matched exactly (case-sensitive). Create and revoke them in the Vultr console:
  **https://console.vultr.com/inference/**
- Failure shapes: no key → `401 "No API key provided"`; bad key → `401 "Invalid API key"`.
  A 401 is never worth retrying with the same key. (`/v1/messages` returns Anthropic-shaped `authentication_error`.)
- Usage, files, vector stores, rate limits, and webhook secret belong to the **subscription**: every key of that
  subscription sees the same ones. Webhook receivers need no API key (signed with a separate webhook secret).

From the quickstart doc:

- Setup is: create a key in the console, `export VULTR_INFERENCE_API_KEY=...`, call
  `POST https://api.vultrinference.com/v1/chat/completions` (OpenAI-compatible; `choices[0].message.content` holds text,
  `usage` counts billed tokens).
- **The model list is public and needs no key.** Each entry carries prices, context window, input modalities,
  and supported parameters.
- Default-model behavior (important for §5): on `/v1/chat/completions` and `/v1/responses`, omitting `model`
  routes to **`deepseek-v4.1-flash-1017`**; an **unknown model id is NOT an error** — the request silently routes to
  that same default and the response's `model` field says what actually ran. Check the returned `model` field.

## 3. GET /v1/models — observed result (public, no key)

Unauthenticated `GET /v1/models` returned **HTTP 200** with 36 models (id → name):

| id | name |
|---|---|
| ace-step-1.5 | ACE-Step 1.5 |
| auk / auk-flash | AuK / AuK-Flash (evaluation) |
| bge-reranker-v2-m3 | BGE M3 |
| chatterbox | Chatterbox |
| clef / clef-flash | Clef / Clef Flash |
| d3 | d3 |
| **deepseek-v4.1-flash-1017** | **DeepSeek V4.1 Flash 1017** (documented chat default) |
| glm-5.2 / glm-5.3 / glm-5.3-flash | GLM 5.2 / 5.3 / 5.3 Flash |
| granite-speech-5.0-2b | Granite Speech 5.0 2B |
| mimo-v2.6-flash / mimo-v2.6-pro | MiMo V2.6 Flash / Pro |
| minimax-h3 | MiniMax H3 |
| minimax-m3.1-flash | MiniMax M3.1 Flash |
| minimax-music3 | MiniMax Music 3 |
| moss-image | MOSS-Image |
| muse-glimmer-30b | Muse Glimmer 30B |
| nemotron-3-nano-omni-30b-a3b-reasoning | Nemotron 3 Nano Omni |
| nemotron-3.5-content-safety | Nemotron 3.5 Content Safety |
| pplx-decider-v1.2 | pplx-decider v1.2 |
| qwen-image-2.1 | Qwen-Image 2.1 (evaluation) |
| qwen3-asr-1.7b | Qwen3-ASR 1.7B |
| qwen3-embedding-4b | Qwen 3 Embedding 4B |
| qwen3-tts-12hz-1.7b | Qwen 3 TTS 12Hz 1.7B |
| qwen3.8-27b / qwen3.8-flash-next | Qwen 3.8 27B / 3.8 Flash Next |
| raon-1-mini-preview | Raon-1 mini (preview) |
| voxtral-mini-4b-realtime | Voxtral Mini 4B Realtime |
| vultron-retriever-core-qwen3.5-4.5b | Vultron Retriever Core 4.5B |
| vultron-retriever-flash-qwen3.5-0.8b | Vultron Retriever Flash 0.8B |
| whisper-large-v3-turbo | Whisper Large V3 Turbo |
| z-image-turbo | Z-Image Turbo |

Each entry also exposes pricing/context/parameters in the full JSON (verified shape on first entry; full listing
not persisted). Per docs, the same list is browsable at `/docs/models`. Which non-default ids support
`response_format: json_object` on the chat route was NOT verified — confirm per-model before relying on JSON mode.

## 4. Exactly what is missing + legitimate activation procedure

Current shell environment (presence only, values never printed):

- `VULTR_INFERENCE_API_KEY`: **absent**
- `VULTR_INFERENCE_MODEL`: **absent**
- `VULTR_INFERENCE_BASE_URL`: absent → code default `https://api.vultrinference.com/v1` applies (correct per docs)

So the missing credential is a **Vultr Inference API key bound to a Vultr account subscription with Inference
enabled**, plus a chosen model id. Nothing else (no separate subscription token, no SDK install — plain HTTPS works).

Legitimate activation (human operator steps, no automation around key creation):

1. Sign in to the Vultr account at https://console.vultr.com/inference/ (the "Get an API key" target in the docs).
2. Create an API key there; ensure the account's Inference subscription is active / has credit.
3. On the machine running the API (and worker, if separate):
   `VULTR_INFERENCE_API_KEY=<key>`, `VULTR_INFERENCE_MODEL=deepseek-v4.1-flash-1017`
   (or another chat-capable id from §3 after verifying JSON-mode support).
4. Restart the API process (settings are read from env at import — see §5.4).
5. Verify: `pytest reversa/apps/api/tests/test_ai_eval.py -k vultr` should run instead of honest-skip,
   and `POST /workflows/from-intent` with `use_ai: true` should return `provider: "vultr-inference"`.
   Then eyeball the returned `model` field — per §2 it must equal the requested id, else the request
   silently fell back to the default.

No key material may be committed; `docker-compose.yml` already passes the key through as
`${VULTR_INFERENCE_API_KEY:-}` without a default, which is the correct shape.

## 5. Planner provider-abstraction review

### 5.1 Strengths (verified in code)

- Clean abstraction: `LLMProvider.generate(intent, customer, capabilities) -> PlanResult` (`base.py`);
  both `DeterministicPlanner` and `VultrInferenceProvider` honor it, and `test_ai_eval.py:evaluate(provider)`
  runs the same 10-case suite against either — genuine substitutability, not just inheritance.
- Fail-safe orchestration (`planner/__init__.py:plan_from_intent`): Vultr is used only when requested AND
  configured; any `PlanError` degrades to deterministic with an explicit warning. Single caller
  (`routes/workflows.py:69`), and the route re-validates with `validate_plan` regardless of provider.
- Defense in depth: system prompt constrains output shape and forbids secrets/commands/URLs/payments;
  `validate.py` enforces connector allowlist, DAG order, input types, and FORBIDDEN/APPROVAL policies;
  one correction retry feeds structured errors back. Timeouts (30 s), error truncation (300 chars), and
  latency metering are present.
- Honest test gating: `test_vultr_provider_if_configured` skips (not fakes) when unconfigured.

### 5.2 Gaps / bugs found (for a later cycle, NOT fixed here — read-only mandate)

1. **`usage` is never populated** (`vultr.py:52,71`): `usage` is initialized to `{}` and `_chat` returns only the
   content string, so `PlanResult.usage` is always empty despite the "usage metering" claim. Fix: return
   `(content, data.get("usage", {}))` from `_chat` and assign per attempt.
2. **Silent model substitution is undetected**: per §2, a mistyped `VULTR_INFERENCE_MODEL` still returns HTTP 200
   from the default model. The provider never compares the response's `model` field to the requested id.
   Recommend asserting/logging a warning on mismatch.
3. **Dead code**: `VultrInferenceProvider._input_keys` (`vultr.py:77-79`) always returns `[]` and is never called.
   Remove or wire to capability input schemas.
4. **Env read at import time** (`config.py:9-28` + `planner/__init__.py:8`): `settings` is a frozen dataclass built
   from `os.environ` at import; setting the key after process start has no effect. Activation runbook must include
   a restart (noted in §4.4). A lazy `get_settings()` would fix it.
5. **Assumed JSON mode**: `response_format: {"type": "json_object"}` is sent unconditionally; support varies by
   model and was not verified for the chosen id. The `BAD_JSON` retry path mitigates this, but a model that
   ignores the hint burns the retry budget routinely.
6. Minor: `DeterministicPlanner.generate` (`deterministic.py:30`) calls `customer.get` without guarding
   `customer=None` (the `or {}` merge on line 22 suggests None was anticipated); `temperature: 0` +
   `max_tokens: 2000` are hardcoded with no per-model tuning.

### 5.3 Verdict

Abstraction quality is **good for its purpose**: one interface, two swappable providers, honest fallback, and an
eval harness that measures both. The Vultr path is correctly unwired until a legitimate key exists. Items 1–2 in
§5.2 should be fixed before any billed usage is trusted for metering/attribution; items 3–6 are hygiene.
