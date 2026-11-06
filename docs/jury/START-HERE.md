# REVERSA — START HERE (jury, 5 minutes)

**What:** the verified recovery control plane for enterprise AI operations.
AI proposes a multi-system workflow, a deterministic policy gate decides,
the saga engine executes with verification after every effect, failures
trigger typed reverse-order compensation, and every run exports a
hash-chained Evidence Passport you can verify offline.

**Why:** AI automation is powerful — until it fails halfway through and
leaves five systems inconsistent. REVERSA handles the part that normally
requires an engineer at 2 AM: it restores what it can, refuses to touch
what it cannot verify, and proves the final state.

**Live:** https://217.69.7.155.nip.io — zero token needed. Overview →
Launch Interactive Demo mints its own guest session (60-min TTL, fixed
2-workflow/2-execute quotas, own ephemeral demo org).

## 1. The Recovery Moment (click steps, ~90 s)

1. Command Center → keep the Acme onboarding intent → Generate plan →
   Shadow Preview (effects per system, billing approval flagged,
   `notify.send_summary` IRREVERSIBLE) → Approve.
2. Execute → watch graph + SSE timeline go green; Connector Hub shows
   rows in 5 isolated **demo** states (SQLite demo stores, labeled).
3. Demo Lab → INJECT FAILURE (billing http500) + RUN as guest
   (org-scoped, cap 50/org, swept at expiry). Watch detection →
   dependent blocking → reverse-order compensation (6 true undos +
   1 read-only noop in the reference run).
4. Resources view: workspace gone (hard-deleted), users/org/queue
   archived; workflow COMPENSATED; incident report + recovery manifest
   complete.
5. Agentic bonus (60 s): "Do the thing" → 200 needs_clarification
   (≤3 deterministic questions, no workflow); "Delete all workspaces" →
   refused with code; "Offboard leavers from Acme" → valid 3-step plan →
   approve → execute → evidence.

## 2. Export + verify (don't trust the demo — run the verifier)

- In-app: Evidence Passport → VALID chain → Download JSON (canonical).
  `?view=shared` omits user-controlled top fields but is
  **internal/do-not-post**: events stay byte-identical, so actor/org/error
  strings still escape (V8 finding; commitment-based format planned RC10).
  Share only synthetic demo-run bundles.
- CLI: `python -m reversa_api.cli verify export.json` →
  `VALID: offline chain valid (59 events recomputed)` exit 0. Strict:
  `python -m reversa_api.cli verify --strict --expect-count 59
  --expect-head <hash> export.json` (either anchor suffices; without
  anchors strict fails closed "completeness unverifiable"). RC9 prod:
  smoke wf90 VALID 59 (RT-04 approver-identity guest-label check OK —
  RT-04 defined in `12-final-verification-rc8.md:23`), chaos wf91
  VALID 81 (`15-final-verification-rc9.md:26-31`).
- Honest semantics: VALID = prefix-consistency (events 1..N link to
  GENESIS, no gaps/mismatches); does NOT rule out trailing truncation
  without `--strict` anchors; exported `ts` not hash-covered.

## 3. Model + gate (AI proposes, policy decides)

- Default: DeterministicPlanner (no key, reproducible) runs the whole
  demo. Optional: VultrInferenceProvider (`deepseek-v4.1-flash-1017`
  pinned, JSON mode, 8000-token budget, 1 correction retry, usage
  metering) with explicit fallback labeling.
- Authority is deterministic `validate.py`: allowlisted capabilities
  only, DAG/cycle check, compensation compatibility, policy
  AUTO/APPROVAL/FORBIDDEN, MAX_PLAN_STEPS=32, MAX_PROVISION_USERS=100.
  Malformed AI drafts → 422 PLAN_REJECTED, never executed
  (live-observed, `05-ai-integration.md:23-26`). Ambiguous → 200
  needs_clarification; off-scope → 200 refused
  (OUT_OF_SCOPE/UNSAFE/IMPOSSIBLE). Live A/B n=12: prod prompt A 10/12
  kept; protocol_v5 B 11/12 stays experimental (+19% tokens,
  simple-legit regression).

## 4. Architecture (one diagram)

```text
Browser (Next.js) ──HTTPS──▶ Caddy ──▶ FastAPI + worker ──▶ Postgres 16
        │                          │            │                 │
   opaque bearer              SSE stream   Vultr Inference   5 demo SQLite
   (60-min TTL)               (bounded)    (deepseek flash)  stores (labeled)
```

One Vultr VM (Paris, `vc2-2c-4gb`): API, worker, web, Postgres, Caddy.
Observed spend $0.28 on 2026-11-05 ($200 credit).

## 5. Tests (re-run everything)

- `PYTHONPATH=reversa/apps/api/src python -m pytest
  reversa/apps/api/tests/ -q` → 792 passed, 2 honest skips
  (RC10 v0.2.0-rc.10).
- `python reversa/tests/e2e/smoke_browser.py --token <tok>` → 10/10
  real Chromium.
- `python reversa/tests/performance/bench.py --base <url> --token <tok>`
  → P50s (505 ms happy / 1.78 s chaos).
- Fresh-clone keyless: README quickstart → public mint → intent →
  approve → execute → COMPLETED 59 events → CLI VALID.

## 6. Commercial value (30 s)

Buyer: Head of IT / RevOps / Business Systems at 200–2000-person SaaS
and MSPs. Wedge: teams that already automate but eat the recovery cost.
Model sketch (to validate): platform fee + execution volume. Pilot:
30-day Recovery Audit, sandbox-only, pre-registered success bar
(`docs/product/pilot-offer.md`, `pilot-kit.md`). Zero LOIs / revenue —
stated openly; the pilot is the instrument that earns them.

## 7. Limitations (what we do NOT claim)

Single-model planner; A/B n=12 only; concurrency N=1/5/10 loopback only
(N≥25/50 + soak not done); single worker + sync SSE bounded
(idle 30 s, heartbeat, 32-stream cap with idempotent leases, resume via
`since_seq`); one VM = SPOF (pre-deploy backup taken; restore TESTED on
RC7, RC10 restore test not run; snapshot taken); no exactly-once on external
systems; hash chain detects tampering, not absolute immutability; demo
systems labeled; `?view=shared` internal-only (8 redactions); V2 video ships
(V3 storyboard only); wf41 read-only classified, left in place by design.

Full dossier: `docs/jury/` (01–18). Numbers: RC10, 2026-11-06.
