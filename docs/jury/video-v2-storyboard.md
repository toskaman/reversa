# REVERSA V2 — Narrated jury video storyboard (AGENT-19, cycle 1)

Status: STORYBOARD ONLY. No media rebuilt this cycle (per mandate).
Target: one narrated MP4, 90–120 s, 1280×800, replacing `demo.mp4` next cycle.
Voice: human-recorded preferred; neural TTS acceptable if disclosed nowhere on-screen (no claim depends on the voice).
Rule: every visual is a real capture or real screen recording. No staged UI, no mockups presented as product.

## 1. Media audit (2026-11-05, read in-repo)

Sources read: `docs/jury/demo.srt`, `build_video.py`, `build_slides.py`,
`slides.md`, `lablab-submission.md`, `09-demo-script.md`, `01/02/04/05/06/07/08/10`,
`README.md`, `docs/benchmarks/results.md`, `docs/product/{competition,github-connector,recovery-proof-engine,ux-v2-wireframes}.md`.
Media stat-checked: `demo.mp4` (509,791 B, 15:13), `slides.pdf` (290,995 B, 15:39),
`cover.png` (176,313 B = byte-identical to `gallery/workflow.png`),
`cover-16x9.png` (202,981 B, 15:39), `gallery/` 8 PNGs byte-identical to `.agents/smoke/` captures.

### 1.1 Accuracy — no false claims found

| Asset | Claim checked | Verdict |
|---|---|---|
| demo.mp4/srt | 10 actions, 5 systems | TRUE (README, 04) |
| demo.mp4/srt | 7 compensations, reverse order, verified | TRUE (04, test_chaos cited in RPE spec) |
| demo.mp4/srt | 59 events, verifiable offline | TRUE (04, 10, CLI in README) |
| demo.mp4/srt | one Vultr VM + automatic TLS | TRUE (benchmarks/results.md, README) |
| slides.pdf | happy P50 505 ms, chaos 1.78 s, recovery 100% | TRUE (matches results.md exactly) |
| slides.pdf | 1 VM 2vCPU/4GB Paris, under $3 | TRUE (vc2-2c-4gb cdg, $0.027/h in 10) |
| lablab-submission.md | stack, deterministic + optional inference, 8 gallery captures | TRUE (05, gallery count = 8) |
| lablab-submission.md | demo URL https://217.69.3.211.nip.io | STATED in README/01; liveness NOT re-verified this cycle |

### 1.2 Outdated / drift (minor, fix next cycle)

1. `slides.md` line 3 says images come from `.agents/smoke/*.png`, but
   `build_slides.py` reads `gallery/`. Stale path comment — fix the comment, not the build.
2. V2 specs exist but are UNIMPLEMENTED — media correctly claims none of them
   (good): Recovery Proof Engine = spec only; Recovery Race / Time Machine /
   Decision Inspector = wireframes only; GitHub connector = skeleton, offline
   tests only, NOT registered, live run pending. The V2 video MUST NOT show
   these as shipped. If teased, label "roadmap".
3. AI posture stays honest (05: inference 401 without key, deterministic default).
   V2 narration must keep "validated plans, honest fallback" framing — never "powered by LLM".

### 1.3 Missing WOW (the gap this storyboard closes)

Current `demo.mp4` is a SILENT 66 s slideshow: static screenshots + title cards,
no voice, no motion, no cursor, no live SSE timeline, no sound design.
`competition.md` self-flags exactly this ("Voiceover, timing" remaining).
Specific gaps: cold 5 s title card with no hook; no before/during/after resource
proof on screen; no incident-report close-up; measured numbers (505 ms / 1.78 s /
100% / 15 valid chains) never appear; no human voice or face; no real-connector
proof (blocked on GitHub live token — honest gap, keep out of video until green).

## 2. V2 storyboard — "Who fixes the mess?" (target 100 s)

Format per scene: TIME | VISUAL (real source) | VO (narration) | ON-SCREEN TEXT.
Total VO ≈ 230 words ≈ 95 s at 150 wpm + 5 s tail card.

### S1 — Hook (0:00–0:08, 8 s)
- VISUAL: cold open on `chaos.png`-style live screen recording: billing row
  flips red mid-run, timeline flags FAILURE. Motion, no title card.
  (New asset next cycle: 8 s screen recording of Demo Lab chaos run.)
- VO: "Your AI agent just onboarded half a customer. Six steps done — then
  billing died. Who undoes the other five?"
- TEXT: "Step 6 of 10 failed. Now what?"

### S2 — Plan (0:08–0:24, 16 s)
- VISUAL: screen recording: Command Center, Acme intent → Generate plan →
  Shadow Preview (effects, risks, billing approval flag, irreversible marker)
  → Approve. (New asset; fallback: `command-plan.png` + `command-done.png` pans.)
- VO: "REVERSA turns plain words into a strict plan — only over systems you
  authorized. Every effect previewed. Every risk flagged. Billing touches money,
  so it needs your approval."
- TEXT: "Intent → strict plan → your approval"

### S3 — Verified execution (0:24–0:42, 18 s)
- VISUAL: screen recording: workflow graph + SSE timeline going green live;
  cut to Connector Hub real rows (`connectors.png` / `workflow.png`).
- VO: "Ten real actions across five systems. And REVERSA never assumes — it
  re-checks every effect. Green means verified, not attempted."
- TEXT: "10 actions · 10 verified · P50 505 ms"

### S4 — Chaos (0:42–0:58, 16 s)
- VISUAL: Demo Lab INJECT FAILURE click → billing 500s → detection banner →
  dependents blocked (`chaos.png` + recording).
- VO: "Now watch it break. One click kills billing mid-run. REVERSA detects it
  instantly, blocks everything downstream — nothing half-built escapes."
- TEXT: "Billing 500 · detected · dependents blocked"

### S5 — Self-healing (0:58–1:16, 18 s)
- VISUAL: recovery view: reverse-order compensation list animating to done;
  resources before/during/after (`recovery.png`).
- VO: "Then it heals itself. Seven completed steps, undone in reverse order —
  each one verified gone. The workspace is deleted. The users are archived.
  Nothing left to clean up."
- TEXT: "7/7 compensated · verified absent · P50 1.78 s"

### S6 — Evidence + close (1:16–1:40, 24 s)
- VISUAL: Evidence Passport VALID badge → download JSON → offline CLI "VALID"
  (`evidence.png` + terminal recording); tail card: architecture line + tagline.
- VO: "Every run seals a hash-chained Evidence Passport — fifty-nine events
  you can verify offline. All of it on one Vultr VM. REVERSA: reversible
  where possible, accountable everywhere."
- TEXT: "59 events · VALID offline · 100% on Vultr"

## 3. Build notes for next cycle (not this cycle)

1. Record S1–S6 screen captures against the live demo URL (Chromium, 1280×800);
   keep raw recordings under `.agents/v2-captures/` for provenance.
2. Record VO (human) or TTS to WAV; assemble with ffmpeg (extend `build_video.py`
   pattern: segments + concat + SRT; add `-i vo.wav -shortest`).
3. Burn key TEXT lines as lower-thirds (existing drawtext style); regenerate SRT
   from §2 VO with real timestamps.
4. Numbers allowed on screen ONLY: 505 ms / 1.78 s / 100% / 59 events / 15 valid
   chains (all from `docs/benchmarks/results.md` + 04/10). No new figures
   without a measured run.
5. Forbidden: V2 wireframe mockups as product, "AI-powered" claims beyond 05,
   GitHub footage until its live test is green, any invented deployment result.
6. Jury package update: swap `demo.mp4` + `demo.srt`, refresh `slides.pdf` S9
   only if numbers change, keep covers/gallery (authentic, current).

---
*AGENT-19 · REVERSA V2 cycle 1 · Media Director · 2026-11-05. Read-only audit + this file.*

---

## 4. Cycle 2 capture status (AGENT-19, 2026-11-05, LOCAL stack only)

Clips: `docs/jury/v2-clips/` (10 files + `shot-log.md`). Source: in-process
TestClient, fresh temp DB. No prod contact. No secrets in any clip (scanned).

| Scene | Status | Evidence |
|---|---|---|
| S1 Hook | CAPTURED (data) | `s1-hook.json`: wf 2 seq 6 `billing.create_profile` FAILED, `chaos.injected` seq 35+ |
| S2 Plan | CAPTURED (data) | `s2-plan.json`: 10 steps, deterministic, AWAITING_APPROVAL, approvals_required=true |
| S3 Execution | CAPTURED (data) | `s3-execution.json`: COMPLETED 10/10 VERIFIED, 59 events, real resources |
| S4 Chaos | CAPTURED (data) | `s4-chaos.json`: COMPENSATED, seq 6 FAILED, seqs 9+10 SKIPPED |
| S5 Recovery | CAPTURED (data) | `s5-recovery.json`: order [8,7,5,4,3,2,1], workspace 0, 4 users archived, 81 events |
| S6 Evidence | CAPTURED (data) | `s6-evidence-*.json` + `s6-passport-*.html` + `s6-cli-verify.txt` (rc 0/0/0, strict anchors match) |
| S1–S6 screen recordings | PENDING | needs Chromium 1280×800 motion captures (see shot log P1) |
| Voiceover + SRT | PENDING | shot log P2 |
| ffmpeg assembly + demo.mp4 swap | PENDING | shot log P3 |

"CAPTURED (data)" = real local scenario outputs backing each scene's
on-screen claims; pixel-level screen recordings remain pending. Published
jury numbers unchanged (505 ms / 1.78 s / 100% / 59 events / 15 chains).

*AGENT-19 · REVERSA V2 cycle 2 · Media Director · 2026-11-05. Local captures + shot log; no media rebuilt.*
