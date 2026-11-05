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

---

# Cycle 2 re-check (AGENT-17, REVERSA V2 cycle 2, 2026-11-05 later same day)

Sources: public LabLab pages only, no login. 7 pages read in full this
cycle: live board + the 4 titles left unopened in cycle 1 + 2 newly
surfaced submissions. All competitor claims are **as described on their
public pages, unverified by us**.

## Board counters (2026-11-05, cycle 2)

2,529 participants (+95 today), 707 teams (+45 today; was 706 in cycle
1), 44 submissions (+25 today), 21 drafts (+10 today). The public live
page still surfaces the same ~10 top-voted titles; the +25 submissions
are not individually visible, so most of the field remains unobservable
from public pages.

## Previously unopened titles — now inspected (all dated 2026-11-03/05)

### 7. Blast Radius Zero: sandboxed agent runtime (team Blast Radius Zero Solo, 2026-11-03, 0 votes)
Containment-first agent runtime, deployed on Vultr. Planner (Vultr
Serverless Inference, glm-5.3) proposes exactly one action per turn as a
complete Python program; each runs in a fresh container (no network,
read-only root, unprivileged, caps dropped, 256MB, 0.5 CPU, 64 pids,
20s watchdog). /out snapshots served as artefacts; a second model call
audits the final answer against recorded evidence (stdout, exit codes,
artefact list) — unsupported claims are not marked verified. SQLite
ledger; UI shows program/output/verdict side by side. "Containment Lab"
runs 7 real attacks (fs tamper, fork bomb, infinite loop, egress,
credential hunt, memory bomb, disk fill) through the same sandbox path,
reporting kernel evidence (EROFS, OOM-kill, no route, watchdog kill).
Stack: FastAPI+SSE, Docker+gVisor/runsc, Caddy, systemd, SQLite; VM
provisioned by repo scripts.
- Recovery/orchestration observed: **none** — no retry, compensation,
  undo, or healing described. Verification is a post-hoc audit verdict,
  not recovery.

### 8. Trifecta Checker - Blast Radius Zero (team Trifecta Checker, 2026-11-03, 0 votes)
Pre-execution AI Safety Gate: blocks "Lethal Trifecta"
(Private+Untrusted+External = 403 BLOCKED, else 200 CLEAN); blocks Vultr
VM spawn if malicious. Trust scores by domain (.gov=100 … unknown=10);
identity/agent-responsibility framing (DID, agent cards, CIS-8).
Deployed on Vercel (badge shown); Vultr VM described as pending ($5
deposit awaited). Built mobile-first after author's PC died.
- Recovery/orchestration observed: **none** — pure pre-exec block,
  no healing, no undo, no orchestration across systems.

### 9. QuantGate (team WataruAkis, 2026-11-03, 1 vote)
ML release gate: decides whether a smaller activation format is safe to
ship. Vultr Serverless Inference plans evaluation + generates a
constrained Python scoring kernel; disposable Docker worker on Vultr
Cloud Compute compiles to native C++, verifies calibration against an
independent Python reference. Checks sample overlap across partitions,
freezes candidate on dev data before holdout slices. Demo: INT8 blocked
(low-margin holdout accuracy 59.38%). Report shows code, fingerprints,
per-slice measurements, execution trace. Sandbox: no network, non-root,
read-only root, CPU/RAM/time caps; timeout probe demo. Honest limits
stated (rounding simulated at layer boundaries; byte counts cover
encoded activations only).
- Recovery/orchestration observed: **none** — a release *gate*, not
  healing. No compensation, retry, or undo semantics.

### 10. SAAS Fashion Garment Marketing - Batik to Global (team SuperInfra Trinity V32-2 SOLO, 2026-11-05, 2 votes)
Off-theme: Indonesian Batik SME supply-chain/finance SaaS (Google
Sheets-backed SAK EMKM accounting, demand planner, GPS transport,
Streamlit demo). Uses Vultr Serverless Inference (DeepSeek/Llama) for
Batik motif generation; claims Vultr Cloud Compute Jakarta + AMD MI300X
analytics. No safety, orchestration, or recovery content.
- Recovery/orchestration observed: **none**.

## Newly surfaced submissions (found via "Explore more" links, 2026-11-05, 0 votes each)

### 11. Fathom: AI Database Copilot on Vultr (team Fathom, 2026-11-05, 0 votes)
Autonomous DB copilot: upload .sql/.sqlite (≤25MB), ask in plain
English; DeepSeek-on-Vultr-Inference agent explores schema, writes SQL,
runs it, checks results (empty sets, truncation, null-heavy columns,
join fanout) and **rewrites the query when the evidence says it is
wrong**. Live timeline; answer as table/chart/explanation/refreshable
dashboard. Model treated as untrusted: SQLGlot guard — reads run,
single writes need explicit confirmation, DROP/ALTER/CREATE/ATTACH/
PRAGMA/load_extension are **refused**. Fresh Docker container per step
(no net, read-only root, caps dropped, pid/mem/CPU caps, removed after
each step); secrets never enter sandbox. "Containment drill" button;
DROP TABLE visibly marked Blocked. One Vultr VM (Caddy+Next.js+FastAPI),
all LLM calls to Vultr Serverless Inference.
- Recovery/orchestration observed: **query-rewrite loop only**
  (retry-like, single-system). The *refusal* concept is the closest
  parallel to REVERSA's refused-by-design seen so far — but it is a
  **pre-execution guard on SQL DDL**, not refusal of unsafe *undo* and
  not verified compensation. No multi-system saga, no tri-state
  recovery verdict.

### 12. Upgrade Proof (team Upgrade Proof, 2026-11-05, 0 votes)
Proves npm upgrades in disposable Vultr sandboxes for dependency-PR
reviewers. Vultr Inference (qwen3.8-27b) plans from package.json; agent
runs baseline tests → upgrade → tests again, each step in a new Docker
container (no host env, no caps, read-only root, non-root, npm-registry-
only proxy). **If tests fail, the model proposes a fix; applied and
retested, up to 3 times.** Demo: chalk 4→5.4.1 (ESM break fixed, tests
pass); hostile postinstall's 2 exfil calls proxy-blocked, 0 tokens seen;
26 s run. Output bundle: summary.json, upgrade.diff, step logs,
egress-blocked.jsonl, manifest.json with per-file SHA-256. Honest
limits: npm only, one run at a time, Docker not microVMs.
- Recovery/orchestration observed: **bounded fix-and-retest loop
  (≤3, code-level)**. No compensation/undo semantics, no refusal to
  claim recovery, no cross-system orchestration. Evidence-bundle story
  (hashed manifest) joins YAI Guard/VOIDLOCK/Detonation in making
  hash-chained evidence table stakes (now 4+ rivals).

## Spotted but not opened (titles only, no claims)

- CiteScreen — evidence-based resume screening (team resync).
- Theseus — "keep only what's load-bearing" (team Theseus).
- Both surfaced only as "Explore more" links; neither title suggests a
  recovery/orchestration approach, but open before the final pitch.

## Cycle 2 matrix delta (append-only; cycle 1 table above unchanged)

| Capability | REVERSA | BR-Zero solo | Trifecta | QuantGate | SAAS Fashion | Fathom | Upgrade Proof |
|---|---|---|---|---|---|---|---|
| Sandboxed execution | Demo-tenant isolation (no code sandbox) | YES (gVisor) | — (API gate) | YES (Docker) | — | YES (Docker) | YES (Docker+proxy) |
| Verify every effect | YES (connector verify) | YES (audit vs evidence) | — (block only) | YES (reference check) | — | YES (result checks) | YES (tests before/after) |
| Typed compensation / undo | YES (6 levels, verified) | — | — | — | — | — | — |
| Refuse unsafe undo | YES (refused-by-design) | — | — (pre-exec block) | — (release gate) | — | — (pre-exec DDL refusal) | — |
| Tri-state recovery verdict | YES (PRESENT/ABSENT/UNKNOWN) | Audit verdict ≠ recovery | — | Gate verdict ≠ recovery | — | — | — |
| Human approval gate | YES (plan-hash-bound, 30-min TTL) | — | — | — | — | YES (writes need confirm) | — |
| Hash-chained evidence | YES (SHA-256 + offline CLI) | SQLite ledger (hash unclaimed) | SHA-256 (agent cards) | Fingerprints+trace | — | Timeline (hash unclaimed) | YES (SHA-256 manifest) |
| Live Vultr deployment (claimed) | YES (1 VM, measured) | Claimed (script-deployed) | NO (Vercel; Vultr pending) | Claimed (demo URL) | Claimed | Claimed (1 VM) | Claimed (demo URL) |

## Cycle 2 conclusions (2026-11-05)

1. **Still nobody observed does typed, verified compensation across
   multi-system business effects.** 12/12 inspected submissions now:
   the nearest recovery-adjacent patterns remain retry loops
   (Fathom query-rewrite, Upgrade Proof ≤3 fix-retries) and pre-exec
   gates (Trifecta, QuantGate, Fathom DDL refusal). None describes
   undo semantics, verify-after-undo, or refusal-to-claim-recovery.
   Differentiation statement from cycle 1 holds verbatim.
2. **Evidence pressure keeps rising**: Upgrade Proof is the 4th rival
   with hashed evidence bundles. Keep the live offline-CLI verify +
   RPE tri-state story as the counter.
3. **Fathom is the closest new rival to watch**: one-VM Vultr deploy,
   visible timeline, and a *refusal* concept (pre-exec DDL). Pitch line
   stays: "they refuse dangerous *commands*; we refuse unsafe *undo*
   — and prove absence after it."
4. **Coverage is still partial**: only 12 of 44 submissions (+21
   drafts) observable from public pages. Re-check Nov 7–8; open
   CiteScreen and Theseus first, then any newly top-voted titles.

No copied code. No rival test/deployment results asserted. No secrets.
