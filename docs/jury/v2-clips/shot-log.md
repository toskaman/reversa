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
