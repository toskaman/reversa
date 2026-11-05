# Competition matrix V2 — observed LabLab submissions (AGENT-17, REVERSA V2 cycle 1)

Date: 2026-11-05. Sources: public LabLab pages only, no login.
Live board at check time: 2,529 participants, 706 teams, 44 submissions,
21 drafts. Only ~10 submissions were visible on the public live page; 6 were
read in full (descriptions below). All competitor claims are **as described
on their public pages, unverified by us** — no code was copied, no test or
deployment results are asserted about them.

Rule note: prior cycle's `competition.md` recorded the event page as 404.
The board is reachable now; this file supersedes nothing — read both.

## Observed submissions (inspected)

### 1. YAI Guard — Prove-It Code Runner (team YAI Guard, 2026-11-05, 1 vote)
Closest competitor to REVERSA's evidence story.
- Control plane: task → Vultr Serverless Inference plan → deterministic
  policy → each command in a fresh Docker/gVisor (runsc) sandbox
  (read-only root, writable workspace, no network, CPU/mem/PID/timeout
  caps); sandbox destroyed + cleanup confirmed per task.
- Evidence: hash-chained trace per step (plan, tool call, policy decision,
  argv, exit code, output hashes, file changes, approval, cleanup); anchor
  seals event count + final hash; optional HMAC/Ed25519. Offline verify
  with levels VERIFIED / CONTENT_VERIFIED / PENDING / INCOMPLETE.
- "Never treats completed as proof unless cleanup confirmed and chain
  intact." App and controller on separate Vultr VMs; durable SQLite task
  queue with leases.
- Recovery/orchestration observed: retry/queue-based; **no typed
  compensation, no undo semantics, no refusal-to-claim-recovery concept**
  described.

### 2. VOIDLOCK (team TECH FORGE, 2026-11-03, 0 votes)
- AI code analysis over submitted GitHub repos/tasks; deterministic Policy
  Gate validates every proposed action before execution; approved actions
  run in isolated Docker sandbox; code mods verified by running tests;
  SHA-256 hash-chained receipt system; live dashboard with diff view,
  stop, and **rollback**.
- Recovery/orchestration observed: rollback of code changes (git-level
  undo). **No multi-system saga, no typed reversibility levels, no
  verify-after-undo of business effects** described.

### 3. Detonation Chamber (team Builders Nepal, 2026-11-04, 2 votes, top-voted)
- Behavioral malware analysis: submit npm/PyPI package, repo, or URL;
  executed once in a deleted-afterwards Docker+gVisor container
  (--network none, read-only fs, no caps, pid/mem/CPU caps); decoy
  credentials planted (AWS keys, SSH, .env, wallet); strace-traced into
  typed events; decoy reads / egress attempts marked critical.
- Deterministic scorer computes risk from observed events only; the
  Vultr-Inference agent writes plan + summary but **cannot overturn the
  score**. JSON export with SHA-256 over evidence.
- Recovery/orchestration observed: none — single-shot analysis runs, no
  failure healing, no orchestration across systems.

### 4. SRE Incident Agent — Blast Radius Zero (team SRE Incident Agent, 2026-11-03)
- Log triage: paste log → LLM plans diagnostic step → step runs as real
  Python in one-shot container (--network none, 256MB, 1 CPU, 64 pids,
  read-only rootfs, nobody, no-new-privs, 20s kill, destroyed per run) →
  stdout/exit feed back, ≤5 steps → triage report (executed-numbers
  findings, 3 ranked hypotheses, ordered runbook).
- Static guard refuses subprocess/sockets/fetches/file-writes/eval/host
  paths pre-run. "Nothing the LLM claims is trusted unless an executed
  snippet printed it."
- Recovery/orchestration observed: bounded retry loop with error feedback.
  **Diagnoses incidents; does not heal business operations.**

### 5. Containment-First Agent Runtime on Vultr (team Arber Arifim, 2026-11-03)
- NL task → planned steps → short-lived Docker sandbox per step (no net,
  read-only root, dropped caps, mem/CPU quotas) + headless-browser
  executor via Playwright in-sandbox. Every API response returns the
  **actually applied isolation flags** for reviewer verification.
  Vultr Inference planning with explicit local-fallback reporting.
- Recovery/orchestration observed: none described beyond step dispatch.

### 6. Tripwire Sandbox (team Cubiczan, 2026-11-03)
- Finance reconciliation: agent code per task in fresh Docker (no net, no
  secrets, read-only fs + tmpfs, caps); error-feedback retry; outputs →
  proposed payments → deterministic policy gate → CFO approval; denied
  payments unapprovable; no payment rail connected (intent only).
- Honest status: submitted in MOCK mode; Vultr inference + deploy script
  implemented but **not run live, not deployed on Vultr**.
- Recovery/orchestration observed: retry-on-error + human approval gate.
  No compensation semantics.

## Observed but not opened (titles only, no claims)

- Blast Radius Zero: sandboxed agent runtime (solo) — title suggests direct
  containment competitor; not fetched to limit request volume.
- Trifecta Checker - Blast Radius Zero — not fetched.
- QuantGate (team WataruAkis, 1 vote) — name suggests finance; not fetched.
- SAAS Fashion Garment Marketing - Batik to Global (2 votes) — off-theme
  for recovery/orchestration/safety; not fetched.

## Competition matrix: recovery / orchestration / safety

Legend: YES = described on public page; — = not described; REVERSA column
grounded in repo (`README.md`, `docs/product/recovery-proof-engine.md`).

| Capability | REVERSA | YAI Guard | VOIDLOCK | Detonation | SRE Agent | Contain-First | Tripwire |
|---|---|---|---|---|---|---|---|
| Sandboxed execution | Demo-tenant isolation (no code sandbox) | YES (gVisor) | YES (Docker) | YES (gVisor+strace) | YES (one-shot) | YES (Docker+browser) | YES (Docker) |
| Verify every effect | YES (connector verify) | YES (tests/exit/outputs) | YES (run tests) | YES (observed events) | YES (stdout/exit) | — (flags only) | — |
| Typed compensation / undo | YES (6 levels, verified) | — | Rollback (code) | — | — | — | — |
| Refuse unsafe undo | YES (refused-by-design) | — | — (policy gate is pre-exec) | — | — | — | — (pre-exec gate) |
| Tri-state recovery verdict | YES (RPE spec: PRESENT/ABSENT/UNKNOWN) | Levels are evidence grades, not recovery | — | — | — | — | — |
| Human approval gate | YES (plan-hash-bound, 30-min TTL) | YES (approval in trace) | — (stop button) | — | — | — | YES (CFO) |
| Hash-chained evidence | YES (SHA-256 + offline CLI) | YES (+anchor/HMAC/Ed25519) | YES (receipts) | YES (JSON+SHA-256) | — | — | — |
| Deterministic scorer LLM can't override | Strict plan validation | Policy + anchor | Policy Gate | YES (scorer) | Static guard | — | Policy gate |
| Live Vultr deployment (claimed) | YES (1 VM, measured) | YES (2 VMs, claimed) | Unclear (Vercel badge shown) | Unclear | Unclear | Claimed (deploy script) | NO (self-declared mock) |

## Differentiation and recommended actions

1. **Nobody observed does typed, verified compensation across
   multi-system business effects.** YAI Guard and VOIDLOCK verify *code
   execution*; REVERSA heals *business operations* (CRM/Identity/Support/
   Billing/Notify) with 6 reversibility levels and verified absence after
   undo. Keep the demo on the billing-500 chaos run: detection → blocked
   dependents → reverse-order compensation → restored resources.
2. **Evidence is now table stakes, not a moat.** Three rivals describe
   hash-chained traces; YAI Guard adds anchors + optional signatures.
   Counter: live offline-CLI verification on stage (export → verify in a
   fresh shell) and the RPE tri-state story ("we prove ABSENT or confess
   UNKNOWN") — no rival describes refusal-to-claim-recovery.
3. **Containment gap is real.** Every inspected rival sandboxes *code*;
   REVERSA isolates *tenants/demo systems*. Do not claim code sandboxing.
   Frame honestly: "they contain code, we contain business blast radius" —
   and the refused-by-design list (real payments, mass sends) is the
   business equivalent of their seccomp/no-network flags.
4. **Deployment honesty wins points.** Tripwire self-declares mock mode;
   two rivals show Vercel badges. REVERSA's 100%-on-Vultr live demo with
   measured numbers (README) is a proven edge — keep the "runs on one VM,
   ~$2" line.
5. **Re-check before the final pitch.** Only 10/44 submissions were
   visible; 21 drafts pending. Re-run this check on Nov 7–8, prioritizing
   the unopened titles above.

No copied code. No rival test/deployment results asserted. No secrets.
