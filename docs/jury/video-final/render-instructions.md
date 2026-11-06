# Rebuild the REVERSA jury film

Everything is local and free: Node 22, FFmpeg, Chromium (Playwright), Python 3.12.

1. **Capture real footage** (1440×810 CSS viewport at deviceScaleFactor 4/3 → native 1920×1080 frames, CDP screencast, JPEG q92):
   - production: `OUT=footage node tools/cap-prod.js` (one guest session: guided demo + one Vultr Inference plan)
   - local build of the same commit (API `uvicorn reversa_api.main:app`, web `next start`): `OUT=footage TOK=<demo token> node tools/cap-local.js`
   - offline verifier: `python -m reversa_api.cli verify [--strict --expect-count N --expect-head H] reversa-evidence-<id>.json` → `cli-verify.txt`
2. **Narration** (Kokoro-82M, voice `af_heart`, speed 1.0): `python tools/tts.py full af_heart 1.0` → `audio/narration/sNN.wav` + `timing.json` (token timestamps). Pronunciation dictionary in `tools/tts.py` (`LEX`).
   Intelligibility check: `python tools/asr.py audio/narration/s*.wav` (faster-whisper small.en).
3. **Plates**: trim/retime product footage per `plates.json` (0.90–1.14× real time) → `composition/assets/plates/`.
4. **Compositions**: `python tools/build.py` writes 13 HyperFrames projects in `composition/scenes/sNN/` (shared `tools/style.css`; every overlay is timed from the narration token timestamps).
   Gate: `npx hyperframes@0.9.19 check` in each scene (all 13 pass, 0 errors).
5. **Render**: in each scene dir `npx hyperframes@0.9.19 render --fps=30 --quality=delivery -o render/sNN.mp4`.
6. **Assemble**: `python tools/assemble.py --captions` → concat (stream copy), narration/music/SFX stems, sidechain ducking, two-pass loudnorm (-16 LUFS, -1.5 dBTP), SRT/VTT/ASS from token timings, `final-jury-clean.mp4` (no subtitles) and `final-jury.mp4` (burnt-in subtitles).

To change one scene: edit `tools/build.py` (or the text in `script.json` → re-run step 2 for that scene), re-render that scene only, re-run step 6.
To fix a subtitle: edit `final-jury.srt`/`.ass` and re-run only the captioned encode (step 6, last command).
