# V2 clips — shot log (AGENT-19, cycle 2)

Date: 2026-11-05. Source: LOCAL stack only — in-process FastAPI TestClient,
fresh temp SQLite DB per capture run. No prod contact, no network calls.
Capture script: ephemeral (`$env:TEMP\v2_capture.py`, not committed).
Secrets: capture tokens lived in process memory only; lifespan seed printed
no token (demo org pre-seeded); all files scanned — no `rev_*`, Bearer, or
key material present.

## Captured (data-level scenario outputs, real local runs)

| Scene | Clip file(s) | Observed result |
|---|---|---|
| S1 Hook | `s1-hook.json` | wf 2, seq 6 `billing.create_profile` FAILED (`CHAOS_HTTP500`), `chaos.injected` events at seq 35+ |
| S2 Plan | `s2-plan.json` | wf 1, 10 steps, provider `deterministic`, `AWAITING_APPROVAL`, plan hash `3061d315…ffd7a`, preview approvals_required=true |
| S3 Execution | `s3-execution.json` | wf 1 COMPLETED, 10/10 VERIFIED, resources 1 org + 1 workspace + 4 users + 1 queue + 1 billing profile, 59 events |
| S4 Chaos | `s4-chaos.json` | wf 2 COMPENSATED, seq 6 FAILED, seqs 9+10 SKIPPED (blocked), DRAFT→…→COMPENSATED transitions recorded |
| S5 Recovery | `s5-recovery.json` | comp order [8,7,5,4,3,2,1], 7/7 compensated, workspace 0, users 4 archived / 0 active, org 1 archived, 81 events, chain VALID |
| S6 Evidence | `s6-evidence-happy.json` (59 ev), `s6-evidence-chaos.json` (81 ev), `s6-passport-*.html`, `s6-cli-verify.txt` | API chain VALID both; CLI `verify` rc=0 both; strict `--expect-count 59 --expect-head …` rc=0 |

Local wall timings (in-process, NOT benchmark claims): plan 49 ms scale,
happy execute ~216 ms, chaos execute ~1373 ms. Jury numbers stay the
published ones: 505 ms / 1.78 s / 100% / 59 events / 15 valid chains.

## Pending (needs browser + voice, next cycle)

- P1: screen recordings (Chromium 1280×800): Demo Lab chaos run (S1/S4),
  Command Center plan→approve (S2), live graph + SSE timeline (S3),
  recovery view animation (S5), Passport + terminal CLI (S6).
- P2: voiceover WAV (human or disclosed TTS) + SRT from storyboard §2 VO.
- P3: ffmpeg assembly (`build_video.py` pattern + `-i vo.wav`), swap
  `demo.mp4` + `demo.srt`.
- Forbidden unchanged: V2 wireframe mockups as product, "AI-powered"
  claims, GitHub footage until live green, invented deployment results.

## Reproduce

```powershell
# from repo root; drives the LOCAL API only (fresh temp DB, no prod)
reversa/apps/api/.venv/Scripts/python.exe "$env:TEMP\v2_capture.py"
```

Re-run prints `happy wf=1 events=59 …` / `chaos wf=2 events=81 …` and
rewrites the JSON/HTML/TXT clips above (workflow ids restart at 1 per run).

## Cycle 3 capture + assembly (AGENT-19, 2026-11-05, LOCAL stack only)

Outputs (NEW, uncommitted): `docs/jury/demo-v2.mp4` (85.1 s, 1280×800,
h264 + AAC VO), `docs/jury/demo-v2.srt` (7 entries, real timestamps),
`v2-clips/s1-hook.mp4 … s6-evidence.mp4` (per-scene segments with VO).
`demo.mp4` / `demo.srt` (v1) left untouched. No prod contact. No secrets
in any clip: capture token passed via localStorage init script only,
never typed or shown; stills reviewed — only the `token:media19` actor
label (not the credential) appears. Capture token minted for this run
and revoked afterwards; leftover chaos rules deleted.

Source runs (real local stack, wf ids 4/6/7 — shared demo DB, no reset):
wf6 COMPLETED 10/10 VERIFIED, 59 events; wf7 COMPENSATED (seq 6
`billing.create_profile` FAILED, 7 compensated, seqs 9+10 SKIPPED),
81 events; CLI `verify` on the wf6 export: `VALID: offline chain valid
(59 events recomputed)`, rc=0 (verbatim on the S6 card).

| Scene | Video source (real captures) | VO (SAPI Zira, disclosed TTS) |
|---|---|---|
| S1 Hook 10.4 s | s4-chaos.webm 0–6 s (Demo Lab click + run start) + freeze-hold | 9.8 s |
| S2 Plan 15.4 s | s2-plan.webm (plan → approve) + freeze-hold | 14.8 s |
| S3 Execution 12.0 s | s3a-execute + s3b-workflow (COMPLETED + graph/timeline scroll) | 11.4 s |
| S4 Chaos 12.6 s | s4-chaos.webm full (INJECT + finished banner) + freeze-hold | 12.0 s |
| S5 Recovery 16.4 s | s5-recovery + s5b-comp (Recovery Center + wf7 comp list) + hold | 15.8 s |
| S6 Evidence 14.2 s | s6-evidence (VALID + timeline) + verbatim CLI card 6 s | 13.6 s |
| Tail 4 s | tagline card, silent | — |

On-screen numbers: 10 actions / 10 verified / 7 compensated / 59 events /
VALID rc=0 from the runs above; P50 505 ms / 1.78 s / 100% are the
published jury figures (unchanged, from `docs/benchmarks/results.md`).
Capture notes: `:3000` web was serving a stale build (statics 400, JS
dead — owner process left untouched); captures used own `next start`
on `:3100` from the on-disk build (read-only, stopped after) with
capture-browser `--disable-web-security` (demo API CORS allowlists
`:3000` only; prod is same-origin via Caddy). A stale enabled
billing-500 rule (times_remaining=1, no active owner) was deleted after
it demonstrably poisoned a happy-path take (wf5 COMPENSATED); the
scenario's own rule was deleted after the run. Raw `.webm` + `.wav`
kept ephemeral in `%TEMP%` (`v2-raw/`, `v2-vo/`); reproduce via the
scripts there (`v2capture*.py`, `v2voice.ps1`, `build_v2.py`).
