# AGENT-20 — Final Hostile Audit, REVERSA V2 cycle 4 (FINAL ASCENT)

Hostile verification of all 11 ascent claims. Every citation was read with
tools before being written; every repro ran LOCAL (TestClient + temp DBs);
prod never touched, no SSH. Nothing below invents a result.

## Verdict up front

8 of 11 claims HOLD (guest isolation, safe recovery, verifiable externals,
coherent evidence, reproducibility-of-suite, authentic video, compliant
submission, green CI **on the committed base**). Three do NOT survive intact:

- **V4-5 [HIGH, NEW]: the "public app" is half-broken.** Zero-token JuryLaunch
  runs, but every result-inspection surface (workflow detail, evidence,
  timeline, recovery views) is owner-token-only: a public guest clicking
  "Open result" gets 401 (no token) or 404 (owner token, cross-org).
  Reproduced live (H2/H3 below) + proven by code search (only 2 files use
  the guest token).
- **V4-1 [HIGH, CONFIRMED LIVE]: quota race.** 8 threads vs
  `max_workflows=5` minted 8/8 (G1 below). Agent-08's finding reproduces
  on the current tree.
- **Suite RED on the dirty tree [HIGH, process-blocking]:** 3 failed /
  251 passed / 2 skipped — the 3 failures are the known stale assertions
  (F1/F2/F3), but CI would fail if this tree were pushed as-is.

"Real AI value" is THIN BUT HONEST (no live LLM anywhere; deterministic
planner + validation + 30-case eval are real; no fake-AI claim survives
inspection). "Faithful deploy" is UNVERIFIED (localhost-only mandate; no
in-cycle prod probe exists; stray `:8000` runs a pre-V2-02 build).

## Claim-by-claim (refutation attempts)

1. **Public app — PARTIALLY REFUTED (V4-5).** Public mint itself holds
   (A1: 201, fixed 2/2 quotas, `guest-` slug; A2: body override 422; B1:
   5x201 then 429 + `Retry-After: 3600`). But the post-run UI path is
   broken: `workflows/[id]/page.tsx:22` uses `api()` (owner token only),
   as do `evidence/[id]/page.tsx:14`, `EventTimeline.tsx:16,35` and every
   other page — a repo-wide search finds `reversa_guest_token` in exactly
   2 files (`JuryLaunch.tsx`, `app/page.tsx`). Live: owner-token GET of a
   guest workflow → 404 (H2); anonymous GET → 401 (H3). The Overview list
   was fixed (`page.tsx:18-24`, guest fallback) but nothing else was.
   Demo Lab chaos correctly needs the owner token (by design, `09:9-10`).
2. **Guest isolation — HOLDS except V4-1.** E1/E2: cross-session + owner
   reads 404; C1/C2: guest chaos/mint 403; D1: `?token=` dead (401; only
   comments remain, `workflows.py:315,369`); K1: expiry → 403 + sweep
   deletes org (sessions=1, swept=1, errors=[]); `test_guest_isolation.py`
   17/17 green. Race G1 is the single hole (see Issues).
3. **Safe recovery — HOLDS.** RPE is read-only by construction
   (`routes/recovery.py`: imports contain no transitions/append; endpoint
   SELECTs + pure `evaluate_recovery`); R4/R5 reproduced live (I1/I2:
   409 `R4_NOT_TERMINAL` / `R5_CANCELLED_RUN`); `test_recovery_manifest.py`
   18/18 + `test_crash_recovery.py` 13/13 green.
4. **Verifiable externals — HOLDS.** `GET /v1/models` → 200, 35 models
   (re-verified today; matches `05-ai-integration.md:15`). GitHub stays
   conditional (boot imports demo services only, `main.py:12`,
   `connectors/__init__` per agent-05 read; `registration_decision`
   requires token+allowlist, `github.py:151-188`); full suite green for
   `test_github_contract.py` (no failures outside the 3 known).
5. **Coherent evidence — HOLDS, limits honest.** H4: 59 events,
   chain valid. CLI semantics attacked directly: ts-tampered bundle →
   still VALID (F1), 10-of-59 truncation → still VALID (F2), strict mode
   with count anchor → INVALID (F3) — exactly what `cli.py:1-10`,
   `04:21-27` and README:47-49 document.
6. **Real AI value — THIN BUT HONEST.** No inference credential exists
   (agent-02's three-signal finding; suite's honest Vultr skip
   corroborates). Live path is deterministic-only with explicit warnings
   (`planner/__init__.py:28-47`). What IS real: strict validation
   pipeline, 30-case eval (`CASES==30` asserted `test_ai_eval.py:194`,
   green), offline metering tests. No run-scoped surface mislabels the
   provider (probes + `command/page.tsx`, `DecisionInspector.tsx` reads).
   Taglines ("AI that doesn't just act…") are aspirational, not run claims.
7. **Reproducibility — HOLDS for suite+web; bench/E2E not reproduced
   here.** Full API suite re-ran (counts below); web `lint` clean +
   `build` 13/13 green; README quickstart matches the executed shape
   (venv + pytest + npm build). `bench.py`/browser E2E need a prod token
   (+ Chrome) and were NOT re-run — `smoke_browser.py:1-7` requires
   servers + token; playwright imports but no E2E was executed.
8. **Green CI — HOLDS on base, RED on dirty tree.** Committed `f2a6152`
   is 204/2 green (agent-01/agent-14, re-verified runs). Current tree:
   3 stale failures → the `api` job would fail on push. `web` job inputs
   (lint+build) green on the dirty tree. Secrets-scan replicated
   tree-wide → zero hits. Docker job NOT verifiable here (no docker).
9. **Faithful deploy — UNVERIFIED.** Localhost-only mandate: no prod
   probe. Compose/Caddy/deploy/healthcheck scripts read and coherent
   (single VM, TLS via Caddy, idempotent deploy + verify). No in-cycle
   prod re-probe exists anywhere; last prod evidence is `results.md`
   (2026-11-05) + `jury/10` checkboxes. Stray `:8000` serves a STALE
   pre-V2-02 build (20 routes, no stream-ticket/public-mint/manifest —
   read-only route dump, process untouched).
10. **Authentic video — HOLDS.** `demo-v2.mp4`: 2,849,106 B, ftyp + h264
    (avc1) + AAC (mp4a) verified by my byte read — size matches
    `media-checklist.md` (read in full: 85.19 s container, 6 scene clips
    sum 81.107 s + 4 s tail, SRT 7 entries contiguous, 3 frames viewed
    with no secrets, all on-screen claims TRUE). TTS disclosed in shot
    log; v1 kept as fallback. Sibling's lablab-Video-pointer fix has
    since LANDED (diff read: now points at `demo-v2.mp4`).
11. **Compliant submission — MOSTLY HOLDS.** Rules fit verified
    (`00`: Challenge 2, HR onboarding, optional inference, MIT,
    deadline Nov 9 00:00 Paris — time remains). Artifacts present:
    gallery 8/8 PNGs, covers, slides.pdf (290,995 B), demo-v2.mp4+srt,
    lablab texts (Video pointer now correct). Submission itself pending
    the human's account (`10:15-16` honestly unchecked). Gaps: max video
    duration still unverified (`00:53`); `jury/10:9` counts stale
    (see Issues).

## Issues (severity-assigned)

- **V4-5 [HIGH, NEW]: guest-blind detail views.** Only
  `JuryLaunch.tsx` + `app/page.tsx` send the guest credential; workflow
  detail, evidence, timeline, recovery, command, connectors pages are
  owner-token-only. Public jury path: run works, "Open result" 401/404s.
  Fix: guest-token fallback (à la `page.tsx:18-24`) or carry the guest
  credential into detail routes; re-test zero-token end to end.
- **V4-1 [HIGH, CONFIRMED]: quota race.** `G1: 8x201 vs max_workflows=5`
  (single run, 8 threads). Root cause unchanged: check-then-act in
  `GuestSessionMiddleware` (`auth.py:517-571`, no lock). Fix:
  per-session serialization + threaded regression test.
- **V4-4 [HIGH, process]: 3 stale tests keep the suite red.**
  `test_guest_sessions.py:50` (`guest-*` vs demo slug),
  `:134` (guest reads owner wf, now 404 by design),
  `test_negative_matrix.py:305` (`?format=xml` now 422 by design —
  `routes/evidence.py:74-77`). All intentional behavior changes; update
  the 3 assertions, then re-run FULL suite at tag time.
- **V4-6 [MEDIUM]: no V2-04 deploy evidence; prod state unknown.**
  Nothing in-cycle proves what build serves the public URL. Deploy the
  tagged tree, then re-run the agent-11/agent-08 probe sets against it.
- **V4-7 [MEDIUM, process]: stray servers.** `:8000` (stale pre-V2-02),
  `:3000`, `:3100`, `:8123`, `:18223` all LISTEN (other owners — probed
  read-only, left alone). Risk: testing/demoing against the wrong build.
  Owner(s) should confirm or stop them.
- **V3-2 [LOW, still open]: `_KeywordRefusalFake`** (`test_ai_eval.py:199`)
  still resolves category by exact intent-string lookup (`:211-216`) —
  no keyword matching; name + "discriminates" framing overstate an
  answer-key harness self-test. Rename + soften docstring.
- **N6 [LOW, still open]: `.agents/verification-matrix.md:8,17`** still
  says "pytest 19/19", "7 tests sécu", "SSRF". Internal doc, but cheap
  to fix.
- **J10 [LOW]: `jury/10:9`** "Backend suite 19/19; browser E2E 9/9" is
  V1-era stale (committed base is 204/2; E2E not re-run this cycle).
  Update or drop the line before jury lock.
- **J05 [LOW]: `jury/05:21`** "Eval set (10 cases…)" — now 30 cases
  (`test_ai_eval.py:194` asserts 30, green). One-line fix.
- **U3 [LOW]: "incident report" wording** (`jury/01:14`, `09:22`,
  `lablab-submission.md:31`) — no such artifact exists in code or API.
  Reword to "recovery manifest / evidence passport".
- **U1 [LOW]: `sdk.py:1`** "16-field action contracts" — `ActionContract`
  has 13 fields (`sdk.py:18-32`). Fix the count.
- **V4-3/R4 [LOW, still live]: pop-before-bind** (`workflows.py:336-340`,
  read) — wrong-workflow redeem burns the ticket. Attacker self-DoS
  only; peek-then-pop when convenient.
- **F1 [LOW, cosmetic]: `cli.py:196-200`** prints `VALID:` then
  `INVALID: server-side chain verdict is false` when the server verdict
  is false (exit code correct). Could confuse naive parsers.
- **INFO (accepted, no action):** V4-2 bearer SSE tickets (30 s TTL,
  single-use); single-process in-memory stores (guests/tickets/rate
  windows — documented); public-mint rows accumulate until lazy sweep
  (5/hour/IP cap verified); `slides.md:3` stale images-path comment;
  storyboard §4 not updated for the cycle-3 assembly; 85 s video vs
  90-120 s storyboard target (immaterial); 422-before-401 ordering.

## Structured report

- identity: AGENT-20, Hostile Auditor, REVERSA V2 cycle 4 (FINAL ASCENT).
- mandate: refute the 11 ascent claims with local repros; READ-ONLY
  except this file; cite file:line with severity; venv pytest with real
  counts; localhost only, no prod SSH, no push, no secrets committed.
- files read (45+): `main/auth/config/db/evidence/cli/ratelimit/\n  schemas.py`, `planner/{__init__,vultr,deterministic}.py`,
  `connectors/{sdk,github}.py`, `engine/saga.py` (head), all 7 route
  modules, `conftest.py`, `test_{guest_isolation,crash_recovery}.py`
  (heads), `test_ai_eval.py:190-270`, `docker-compose.yml`, Caddyfile,
  both Dockerfiles, `deploy.sh`, `healthcheck.sh`, RUNBOOK, `ci.yml`,
  `CHANGELOG.md`, README, `prompt.txt` (head), jury
  `00/01/02/04/05/06/07/09/10/lablab-submission/storyboard/shot-log/\n  media-checklist`, `benchmarks/{results,concurrency-results}.md`,
  web `lib/api.ts`, `page.tsx`, `workflows/[id]`, `evidence/[id]`,
  `demo-lab`, `JuryLaunch`, `EventTimeline`, `next.config.ts`,
  cycle reports `V2-03/agent-{11,20}`, `V2-04/agent-{01,02,05,08,09,14}`.
- files modified: `.agents/cycles/cycle-V2-04/agent-20-final-audit.md`
  (this file) ONLY. Scratch probe `%TEMP%/a20_audit.py` kept outside
  the repo; temp DBs auto-scoped. No credentials printed or committed.
- commands run: full suite → **3 failed, 251 passed, 2 skipped in
  70.90 s**; stale-pin rerun (exact assert lines captured); new/changed
  files (`guest_isolation+crash+chaos_matrix+recovery_manifest+\n  security+engine_units`) → **109 passed in 46.73 s**; web `lint`
  clean + `build` 13/13 green; CI secrets-scan replication → zero hits;
  `GET /v1/models` → 200, 35 models; 19-probe hostile script (A1–G1,
  all matched expectations except G1 race 8/8); read-only `:8000`
  route dump (20 routes, pre-V2-02); MP4 container check
  (2,849,106 B, ftyp+avc1+mp4a); gallery count 8; git log/status/diffs.
- observed results: public mint + isolation + sweep + R4/R5 + 422 gate
  + rate limits + CLI limits all hold live; quota race reproduces;
  guest-blind detail views proven (code search + H2/H3); stray `:8000`
  stale; V3-2/N6/U1/U3/F1/R4 carryovers re-confirmed live; lablab Video
  pointer fixed mid-audit by a sibling (diff read); media19 PNGs deleted
  mid-audit; 2 new untracked docs appeared (`release-v0.2.0-rc.1.md`,
  `media-checklist.md`) — racing tree throughout.
- tests: quoted above; zero failures except the 3 known stale
  assertions. Skips are the 2 standing honest ones (Vultr
  unconfigured, no GitHub token).
- issues: V4-5 (guest-blind UI), V4-1 (quota race), V4-4 (3 stale
  tests), V4-6 (no deploy evidence), V4-7 (stray servers), V3-2, N6,
  J10, J05, U3, U1, V4-3/R4, F1 — see Issues with severities.
- risks: (1) NOTHING may be tagged/deployed until V4-4 is fixed and a
  settled-tree full run is green — the tree churned under this audit
  (docs edited, files added/deleted mid-run); (2) V4-5 breaks the
  public-jury story as shipped — fix before any "public app" claim or
  demo; (3) V4-1 overshoot scales with burst size; (4) prod is a blind
  spot — deploy + re-probe post-tag; (5) stray `:8000` risks wrong-build
  demos; (6) browser E2E 9/9 and bench figures are unreproduced here.
- confidence: HIGH on isolation/recovery/evidence/CLI verdicts (live
  bytes + green tests); HIGH on V4-1/V4-5 (reproduced + code-proven);
  HIGH on counts (executed, quoted verbatim); HIGH on video container +
  media provenance (own bytes + full sibling-audit read); MEDIUM on
  docs completeness (targeted greps + full reads of cited docs, not
  every jury line); LOW on prod (never touched by mandate).
- next task: (1) fix V4-5 (guest-aware detail views) + V4-1 (quota
  serialization + threaded test); (2) update the 3 stale assertions;
  (3) settle tree, re-run FULL suite + lint + build at tag time;
  (4) deploy tagged tree to prod, re-probe (agent-11 + agent-08 sets);
  (5) one-line doc fixes (J10/J05/U3/U1/N6/slides.md:3); (6) human:
  LabLab upload (demo-v2.mp4) + deadline re-check before Nov 9 00:00 Paris.
