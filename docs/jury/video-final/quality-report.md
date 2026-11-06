# Quality report — REVERSA jury film (V14)

## Deliverable
| | final-jury-clean.mp4 (**upload this**) | final-jury.mp4 (burnt-in subtitles) |
|---|---|---|
| Duration | 3:54.6 (234.58 s) | 3:54.6 |
| Video | H.264 High, 1920×1080, 30 fps CFR, yuv420p | same, re-encoded once for subtitles |
| Audio | AAC 256 kb/s, 48 kHz stereo | same |
| Size | 60.5 MB | 43.4 MB |
| Loudness | −16.0 LUFS integrated, −1.5 dBTP true peak, LRA 2.7 LU | same audio |

LabLab (checked 6 Nov 2026): no hard duration limit, "under 5 minutes" recommended, MP4/MOV, ≤ 300 MB → compliant. Challenge 2 (Vultr VM backend + public web app) is what the film shows.

## Gates
- HyperFrames `check`: 13/13 scenes ok, 0 errors (one layout overlap found and fixed in s05).
- Concat: 13 scene files with identical encoder settings, stream-copied (no re-encode).
- `blackdetect`: no black segments. `freezedetect`: only intentional reading holds on graphic slides (≤ 7 s).
- Narration intelligibility: faster-whisper transcription of the **finished mix** matches the script word for word (differences are only number/acronym formatting) → music never masks the voice.
- Pronunciation: REVERSA, Vultr ("vulture"), FastAPI, Postgres, TLS checked by ASR; "Fast A P I" spelling rejected, plain "FastAPI" kept.
- Subtitles: 61 cues from the synthesized-speech token timestamps, ≤ 2 lines × 42 chars, no orphan cues; burnt version places them at the bottom over graphics and at the top over product footage (no collision with on-screen titles).
- Facts: every on-screen number traced in `claim-evidence-ledger.md`. One real inconsistency was caught and fixed during review: the terminal first showed the verifier output of a different run than the passport on screen; it now shows the run whose head hash (98060aea…) is visible in the footage.

## Independent review (separate agent, frames + script + ledger only, could not hear audio)
First-pass scores: Technology 8, Presentation 6, Business 5, Originality 7. Fixes applied after it:
1. "Everything … running live on Vultr" → "First, live on our Vultr deployment"; later shots carry "same build as production".
2. Problem graphic now matches the real run (steps 1–5, 7, 8 ran; 6 failed; 10 not run).
3. Orphan/punctuation subtitle cues merged; caption placement per scene.
4. Business: spoken revenue hypothesis and the differentiation vs. workflow engines (retry/rollback ≠ proving the final state).
5. "Restored = effect verified absent" added under the recovery verdict.
Not applied (would require inventing data or new captures): quantified cost of a failed automation (no measured figure exists), executing the AI-drafted plan on screen (guest quota), showing the Vultr console.

## Known limitations
- Production footage covers the guided demo and the Vultr Inference plan; preview/approval, execution, failure/recovery and evidence were filmed on a local run of the same commit (labelled on screen).
- The model name is redacted for guest sessions, so the film shows provider/latency/attempts, not the model id.
- The music is two existing CC BY tracks plus original drones; credit "Music: Sascha Ende, ende.app (CC BY 4.0)" must appear in the submission text.
- Visible UI copy typo in the plan review: "1 step require explicit approval" (fixed in code later, not in the filmed build).
