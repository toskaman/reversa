# AGENT-16 — Evidence Integrity Verification (REVERSA V2 cycle 1)

Date: 2026-11-05. Role: Evidence Engineer.
Mandate: verify Evidence integrity end-to-end (PROD export read-only GET + CLI verifier
with REAL output), audit hash-chain code for gaps. Read-only except this file.
No commits, no pushes, no secrets touched.

## 1. Files read (full, before citing)

- `reversa/apps/api/src/reversa_api/evidence.py` (chain, redact, verify)
- `reversa/apps/api/src/reversa_api/cli.py` (offline verifier)
- `reversa/apps/api/src/reversa_api/routes/evidence.py` (export JSON/HTML)
- `reversa/apps/api/src/reversa_api/routes/workflows.py` (event journal call sites)
- `reversa/apps/api/src/reversa_api/engine/saga.py` (transition journaling)
- `reversa/apps/api/src/reversa_api/models.py` (Event schema, unique ix)
- `reversa/apps/api/src/reversa_api/auth.py`, `config.py`, `main.py`, `routes/health.py`
- `reversa/apps/api/tests/conftest.py`, `tests/test_planner_evidence.py`
- `.agents/verification-matrix.md`, `.agents/progress.md`, `.agents/tasks.json`
- `reversa/infrastructure/docker-compose.yml`, `.env.example`, `Caddyfile`,
  `scripts/deploy.sh`, `scripts/healthcheck.sh`, `scripts/add_token.py`
- `reversa/tests/e2e/smoke_browser.py`
- `.agents/cycles/cycle-V2-01/agent-02-inference-path.md` (prior V2 result, context only)
- `reversa/apps/api/src/reversa_api/schemas.py` (IntentIn.name, via targeted grep)

## 2. Commands run (all observed, nothing invented)

PROD (public, unauthenticated):
- `curl https://217.69.3.211.nip.io/healthz`
  → `{"status":"ok","version":"0.1.0","db":true}` HTTP 200 (~0.05 s)
- `curl https://217.69.3.211.nip.io/api/v1/workflows/2/evidence`
  → `{"detail":"missing Bearer [REDACTED]"}` HTTP 401 (expected: evidence needs auth)

PROD evidence export with auth: NOT performed — no legitimate token available to this
agent (demo token is server-log only, no SSH/key mandate, no brute force attempted).
This is the one mandate item that could not be completed; everything below is REAL
output from the local production-code path instead (same `_bundle` + `verify_chain` +
CLI code that serves PROD).

Local (venv python 3.14.4, `REVERSA_DATA_DIR=reversa/apps/api/data`, SELECT-only):
- Listed real local store: org `acme-demo`, WF1 `Onboard Acme Corporation` COMPLETED
  59 events, WF2 `Onboard customer` COMPENSATED 81 events.
- Exported both bundles via the exact route function `routes.evidence._bundle`
  (the same function the GET route calls) to `%TEMP%\reversa_evidence_wf{1,2}.json`:
  - wf1: `chain={'valid': True, 'bad_seq': 0, 'message': 'chain valid (59 events)'}`
  - wf2: `chain={'valid': True, 'bad_seq': 0, 'message': 'chain valid (81 events)'}`

CLI verifier (REAL subprocess output, `python -m reversa_api.cli verify <file>`):
- wf1 (59 events): `VALID: offline chain valid (59 events recomputed)` exit 0
- wf2 (81 events): `VALID: offline chain valid (81 events recomputed)` exit 0
- tampered copy (1 payload byte flipped at seq 1):
  `INVALID: hash mismatch at seq 1` exit 1 — tamper detection PROVEN
- no args: `usage: python -m reversa_api.cli verify <export.json>` exit 2

Edge probes (`verify_bundle` direct + HTML smoke):
- HTML render of real wf1 bundle: 17603 bytes, contains VALID badge + tables — OK
- ts-only rewrite of all 59 timestamps: still `(True, 'offline chain valid (59...)')`
- truncation to first 49 of 59 events: `(True, 'offline chain valid (49...)')`
- empty events list: `(True, 'offline chain valid (0 events recomputed)')`
- event missing keys: clean `(False, 'prev_hash mismatch at seq 1')`
- events present but `workflow` key missing: unhandled `KeyError: 'workflow'`

Tests:
- `pytest tests/test_planner_evidence.py -q` → **4 passed** (0.46 s; 1 unrelated
  httpx/starlette deprecation warning). Covers chain-ok, tamper-invalid, redaction.

## 3. Observed results (verdicts)

- Hash chain algorithm is deterministic and shared: `canonical_bytes`
  (sort_keys, `separators=(",",":")`, ensure_ascii, UTF-8) + `SHA256(prev_hash +
  canonical_json)` is used identically by `append_event`, `verify_chain`, and the
  CLI. Server-side and offline verifiers AGREE on both real bundles (59 + 81).
- Journal coverage is complete: every workflow/action transition in `saga.py`
  funnels through `_transition_wf/_transition_act` → `append_event`; claim, chaos,
  retry-wait, compensation, manual-required, approval, cancel paths all emit events.
- Redaction is append-time + re-applied on export, and idempotent
  (`***REDACTED***` survives re-redaction; verified by reasoning over
  `_looks_like_secret` charset excluding `*`). Unique index
  `ix_events_wf_seq(workflow_id, seq)` makes concurrent-append races fail safe
  (constraint error, never silent fork).
- No-secrets discipline held: no token material read, printed, or committed.

## 4. Gaps found (audit, all confirmed by code or probe — NOT fixed, read-only mandate)

1. **Trailing truncation undetected (medium).** Forward-only chain commits to no
   total length: dropping the last N events (or all of them) still verifies VALID
   (probed: 49-of-59 → VALID; 0 events → VALID). Fix: include `event_count` +
   terminal head hash in the signed envelope, or have the CLI cross-check
   `chain.message` count / fail on 0 events when workflow is terminal.
2. **`ts` excluded from hash (low).** Body covers workflow/org/seq/type/actor/
   payload/prev_hash but not the timestamp; rewriting all timestamps stays VALID
   (probed). Fix: add `ts` to the hashed body (migration: recompute existing rows).
3. **Fully-recomputed forgery undetectable (known, documented).** No asymmetric
   signature or external anchor; anyone with DB write can rewrite history +
   recompute the chain. Code/docs state this honestly ("detects tampering; not
   absolute immutability"). Fix (later cycle): detached Ed25519 signature over the
   head hash published out-of-band, or periodic anchoring.
4. **Stored HTML injection in evidence HTML export (low-medium).** `_render_html`
   interpolates user-controlled `workflow.name` (`IntentIn.name`, ≤128 chars),
   actor, and payload JSON with zero escaping (grep: no `escape` in the module).
   Opening a malicious export in a browser executes injected markup/script.
   Fix: `html.escape` every interpolated value.
5. **CLI robustness nits (low).** Missing `bundle["workflow"]` with non-empty
   events → raw `KeyError` traceback instead of `INVALID` (probed); offline
   verifier also trusts the bundle's self-reported `chain.valid` flag, which a
   forger controls (defense-in-depth only — recomputation is the real check).
6. **DB-level mutability (informational).** Append-only is application-level; no
   SQL triggers/policies forbid UPDATE/DELETE on `events`. Acceptable for P0
   given (3) is already the trust boundary, but worth a hardening note.

## 5. Risks

- PROD end-to-end evidence export remains unverified from the outside for lack of
  a read-only token; local verification uses identical code paths, but a PROD
  cron/labelled check with a read-only token would close the loop.
- Gaps 1–2 mean "VALID" today attests *internal consistency of the presented
  prefix*, not completeness or timestamp truth — jury/demo claims should phrase it
  that way until fixed.

## 6. Confidence / next task

- Confidence: HIGH on chain-correctness and CLI behavior (real bundles, real CLI
  output, tamper proven, tests green); MEDIUM on PROD parity (same code, but PROD
  export not directly fetched — auth-blocked, reported honestly).
- Suggested next task (later cycle): fix gaps 1 (length commitment), 2 (hash `ts`),
  4 (`html.escape`), 5 (CLI `INVALID` on malformed); then re-run this agent's probe
  script against PROD with a read-only token.
- Probe scripts kept outside the repo at `%TEMP%\agent16_export.py`,
  `%TEMP%\agent16_tamper.py`, `%TEMP%\agent16_probe2.py`; exports at
  `%TEMP%\reversa_evidence_wf{1,2}.json` (+ `_tampered`).

## 7. Files modified

- ONLY `.agents/cycles/cycle-V2-01/agent-16-evidence-verify.md` (this report).
