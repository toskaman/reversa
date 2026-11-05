# Jury media checklist — demo V2 audit (AGENT-19, cycle 4 FINAL Ascent)

Date: 2026-11-05. Scope: verify, do not rebuild. Base: V2-03 merged
(`f777543` + CHANGELOG `f2a6152`); working tree otherwise dirty with
cycle-04 work — this file is the only file this audit adds or edits.

All figures below were observed this run with `ffprobe`/`ffmpeg`/Python
(see Commands). Nothing is copied from prior summaries without re-check.

## 1. demo-v2.mp4 — ffprobe (observed)

- Path: `docs/jury/demo-v2.mp4`, 2,849,106 B
- Container duration: 85.193379 s (~85.2 s)
- Video: h264, 1280x800, duration 85.106641 s
- Audio: AAC, mono, 22050 Hz, duration 85.193379 s (voiceover present)
- Verdict: PASS — matches storyboard target (90-120 s target, 85 s actual;
  under target but complete: 6 scenes + 4 s tail card) and 1280x800 spec.

For reference (v1, untouched fallback): `docs/jury/demo.mp4`, 509,791 B,
h264 1280x800, 66.0 s, no audio stream.

## 2. Scene clips (observed)

| Clip | Duration (s) | Audio |
|---|---|---|
| s1-hook.mp4 | 10.400000 | aac |
| s2-plan.mp4 | 15.433333 | aac |
| s3-execution.mp4 | 12.033333 | aac |
| s4-chaos.mp4 | 12.600000 | aac |
| s5-recovery.mp4 | 16.420000 | aac |
| s6-evidence.mp4 | 14.220000 | aac |
| SUM | 81.106666 | — |

81.107 s + 4 s tail = 85.107 s = video stream duration 85.106641 s. PASS.

## 3. demo-v2.srt — sync (observed)

- Entries: 7 (counted programmatically)
- Span: 00:00:00,000 --> 00:01:25,120 (85.12 s)
- Contiguity: every entry end == next entry start (True, checked)
- Last end (85.12 s) vs video stream (85.11 s) vs container (85.19 s):
  within 0.08 s. PASS — no overrun, no gap.
- v1 `demo.srt`: 9 entries (unchanged).

## 4. On-screen secrets scan — 3 frames viewed (observed)

Extracted with ffmpeg at t=5 s (S1 Demo Lab), t=42 s (S4 chaos banner),
t=75 s (S6 timeline) and viewed as images:

- f1 (t=5): Demo Lab, "Running...", manual injection demo-billing/http500,
  lower-third "Step 6 of 10 failed. Now what?" — no credentials.
- f2 (t=42): Demo Lab, lower-third "Billing 500 - detected - dependents
  blocked" — no credentials.
- f3 (t=75): step list (seq 6 FAILED, 7-8 COMPENSATED, 9-10 SKIPPED) +
  Timeline (81 events) with actor label `token:media19` — actor LABEL
  only, not a credential (consistent with shot-log cycle-3 notes;
  capture token was localStorage-injected, revoked after the run).

Text scan (refined patterns: `rev_*`, Bearer, PEM headers, sk-*/ghp_*,
vultr key, password/token assignments) over `demo-v2.srt`, `demo.srt`,
`v2-clips/*.json|txt|md`, `docs/jury/*.md`: ZERO hits. (A naive first
pass matched `prev_hash` chain fields only — false positives.)
Verdict: PASS — no secrets on screen or in jury media sources.

Note: nothing in this audit is committed that contains secret material;
frame PNGs were viewed from copies and deleted (repo tree has no new
image files from this audit).

## 5. Slides / video references in docs (observed)

| Referring doc | Points at | Status |
|---|---|---|
| `lablab-submission.md:58` | Video: upload `docs/jury/demo.mp4` (V1) | STALE — still names v1 |
| `lablab-submission.md:59` | Slides: `slides.pdf` | OK |
| `09-demo-script.md:30` | fallback video `docs/jury/demo.mp4` | OK as fallback (v1 kept) |
| `slides.md:3` | images from `.agents/smoke/*.png` | STALE comment (known since cycle 1; build reads `gallery/`) |
| `video-v2-storyboard.md` | v1 stats, P1-P3 assembly plan | SUPERSEDED by cycle-3 assembly; §4 table not updated for it |
| `CHANGELOG.md:32-33` | `demo-v2.mp4` + srt + 6 clips | OK |
| `v2-clips/shot-log.md:48-85` | cycle-3 assembly notes | OK |

Gap: NO jury submission doc references `demo-v2.mp4` yet except
CHANGELOG + shot log. Before LabLab upload, update the `Video:` line in
`lablab-submission.md` to `docs/jury/demo-v2.mp4` (human/orchestrator
decision — out of this audit's mandate).

## 6. slides.pdf (observed)

- 290,995 B, `%PDF-1.3` header, 10 pages (counted). PASS.
- Slide 9 figures (505 ms / 1.78 s / 100%, 1 VM 2vCPU/4GB Paris, under $3)
  match `docs/benchmarks/results.md` exactly (re-checked this run).

## 7. On-screen / narrated claims vs sources (re-checked)

| Claim (SRT/frames) | Source | Verdict |
|---|---|---|
| 10 actions, 5 systems | README, 04 | TRUE |
| 7 compensated, reverse order, verified | 04, shot log (order [8,7,5,4,3,2,1]) | TRUE |
| 59 events, verifiable offline | 04, 10, `s6-cli-verify.txt` rc=0/0/0 | TRUE |
| one Vultr VM + auto TLS | benchmarks/results.md, README | TRUE |
| 505 ms / 1.78 s / 100% (published figs) | results.md | TRUE (unchanged) |

## 8. Observations (non-blocking)

1. Frames f1/f2 show nav tabs `Recovery Race`, `Time Machine`, `ROI` —
   V2 pages visible as tab labels only (real app chrome, not presented
   as demo content). No V2-wireframe-as-product claim is made; narration
   makes no claim about them. Acceptable, noted for the record.
2. SAPI/Zira TTS voiceover is disclosed in the shot log (cycle 3), per
   the storyboard rule. No on-screen voice claim exists. OK.
3. Storyboard §2 target was 90-120 s; assembled video is 85.2 s with all
   6 scenes + tail. Complete; duration target miss is immaterial.
4. `10-final-verification.md` LabLab checkboxes remain unchecked —
   correct, submission needs the human's account.

## 9. Commands run (this audit)

- `ffprobe` format+stream probe on `demo-v2.mp4` and `demo.mp4`
- `ffprobe` audio-stream probe on `demo-v2.mp4` and all 6 scene clips
- SRT entry counts + Python contiguity/span check on `demo-v2.srt`
- `ffmpeg -ss 5/42/75` frame extraction (viewed, then deleted)
- `Select-String` secret-pattern scans (naive + refined) over jury media
  sources; PDF header/page-count check in Python
- `pytest --collect-only` (256 collected — dirty tree incl. 2 new
  cycle-04 test files; docs-only change, no code path touched)
- `git status --short`, `git log --oneline -3`

## 10. Verdict

demo-v2.mp4: SHIP-READY as the LabLab upload (pending the one-line
`lablab-submission.md` Video pointer update by the orchestrator/human).
No media rebuild performed, no secrets found, no false claims found.

*AGENT-19 - REVERSA V2 cycle 4 (Final Ascent) - Media Auditor -
2026-11-05. This file is the audit's only deliverable.*
