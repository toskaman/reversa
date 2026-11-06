# REVERSA — jury video V3 source

Built with the `/brag` skill (https://github.com/latent-spaces/brag) on
HyperFrames 0.9.19, rendered locally with the bundled FFmpeg 9.0.2.

## Files

- `composition-index.html` — HyperFrames composition (copy of the
  `index.html` used for the render; assets are referenced by relative
  path but not committed).
- `hyperframes.json`, `meta.json` — HyperFrames project descriptors.

## Assets used at render time (not committed here)

| Asset | Source in repo |
|---|---|
| Screen clips `s2-plan` … `s6-evidence` | `docs/jury/v2-clips/*.mp4` |
| Stills (reveal background, gallery) | `docs/jury/gallery/*.png` |
| Music bed | `skills/brag/assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (CC BY 4.0, Sascha Ende) |
| SFX | `skills/brag/assets/sfx/*` (CC0, Kenney.nl) |
| GSAP 3.15.0 | `cdn.jsdelivr.net` (vendored next to the composition at render) |
| Voiceover | ElevenLabs `eleven_multilingual_v2`, voice `XrExE9yKIg1WjnnlVkGX` (Matilda) |

## Rebuild

```powershell
# 1. project dir must contain index.html + assets/{clips,img,music,sfx,vo,gsap.min.js}
# 2. checks
npx -y hyperframes@0.9.19 check --json
# 3. render 1920x1080 / 30 fps
npx -y hyperframes@0.9.19 render --fps=30 --quality=delivery -o ..\master.mp4
# 4. loudness master (-16 LUFS, -1.5 dBTP, video stream copied)
ffmpeg -i ..\master.mp4 -c:v copy -af "volume=3.14dB,alimiter=limit=0.841:attack=5:release=80:level=false" -c:a aac -b:a 192k -ar 48000 -movflags +faststart ..\demo-v3.mp4
```

Mix levels baked into the composition: voiceover 1.0, music bed 0.08,
SFX 0.35-0.49.

Requires Node.js 22+ and FFmpeg on `PATH`.

## Voiceover script (English)

1. Your AI just onboarded half a customer. Then billing died. Who undoes the other five?
2. REVERSA is the recovery control plane for enterprise AI operations.
3. It plans across five systems, shows every effect before execution, and waits for your approval.
4. Every action is executed, verified, and sealed in a hash-chained evidence passport.
5. When step six fails, dependents are blocked, and seven effects are compensated in reverse order.
6. No orphaned state. No hand-wavy logs. Just a verifiable proof you can check offline.
7. One command verifies the chain offline. Eighty-one events. Valid.
8. REVERSA. Built on Vultr. Reversible where possible. Accountable everywhere.

Every on-screen figure is taken from the captured local runs in
`docs/jury/v2-clips/` (10 steps / 5 systems / 1 approval gate / 59
events on the happy path / 81 events, 6 failed, 7 compensated, 2
skipped on the chaos path). The offline CLI line was reproduced with
`python -m reversa_api.cli verify docs/jury/v2-clips/s6-evidence-chaos.json`
→ `VALID: offline chain valid (81 events recomputed)`.
