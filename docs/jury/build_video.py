"""Build docs/jury/demo.mp4 from REAL screenshots + title cards.

Only authentic captures (.agents/smoke/*.png) + text cards. No staged UI.
Usage: python build_video.py   (needs ffmpeg on PATH)
Outputs: docs/jury/demo.mp4 (720p-ish), docs/jury/demo.srt
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "..", "..", ".agents", "smoke")
OUT = os.path.join(HERE, "demo.mp4")
SRT = os.path.join(HERE, "demo.srt")
W, H = 1280, 800

SCENES = [
    ("card", "REVERSA|Self-Healing AI Operations", "AI that does not just act. It makes things right.", 5),
    ("shot", "command-plan.png", "Describe the outcome. REVERSA drafts a strict, approved plan.", 8),
    ("shot", "command-done.png", "Ten real actions across five systems. Every effect verified.", 8),
    ("shot", "workflow.png", "Live graph, timeline, and shadow preview. Nothing is faked.", 9),
    ("shot", "chaos.png", "Chaos: billing fails mid-run. Detection is instant.", 9),
    ("shot", "recovery.png", "Dependents block. Completed work compensates in reverse.", 9),
    ("shot", "evidence.png", "Every run seals a hash-chained Evidence Passport.", 8),
    ("card", "Vultr native|One VM. Verified execution.", "API, worker, web and data run on Vultr.", 5),
    ("card", "Reversible where possible.|Accountable everywhere.", "REVERSA", 5),
]

SUBS = [
    "AI agents do real work now. But when step six of ten fails, who fixes the mess?",
    "REVERSA turns intent into a strict plan over authorized capabilities only.",
    "It executes across isolated systems and verifies every single effect.",
    "Watch it live: graph, timeline, preview. All state is real.",
    "Now chaos: billing goes down mid-run. Detection is instant.",
    "Dependents block. Seven actions compensate in reverse order. Verified.",
    "The Evidence Passport seals all 59 events. Verifiable offline.",
    "Everything runs on one Vultr VM with automatic TLS.",
    "REVERSA. Reversible where possible. Accountable everywhere.",
]


FONT_PATHS = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font() -> str:
    for path in FONT_PATHS:
        if os.path.exists(path):
            # Quoted + escaped for ffmpeg filter parsing (Windows drive colon).
            return "'" + path.replace(":", "\\:") + "'"
    raise SystemExit("no TTF font found for title cards")


def esc(text: str) -> str:
    return text.replace(":", "\\:")


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd[:4]) + " ...")
    subprocess.run(cmd, check=True)


def main() -> None:
    for kind, src, _cap, _dur in SCENES:
        if kind == "shot" and not os.path.exists(os.path.join(SHOTS, src)):
            raise SystemExit(f"screenshot missing (run the E2E smoke first): {src}")
    tmp = os.path.join(HERE, "_scenes")
    os.makedirs(tmp, exist_ok=True)
    parts = []
    t = 0.0
    srt_lines = []
    for i, (kind, src, cap, dur) in enumerate(SCENES):
        seg = os.path.join(tmp, f"s{i:02d}.mp4")
        if kind == "card":
            title, sub = src.split("|", 1)
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=0A0E14:s={W}x{H}:d={dur}",
                 "-vf", f"drawtext=fontfile={font()}:text='{esc(title)}':fontsize=54:"
                        f"fontcolor=E6EBF2:x=(w-text_w)/2:y=(h-text_h)/2-40,"
                        f"drawtext=fontfile={font()}:text='{esc(sub)}':fontsize=30:"
                        f"fontcolor=22D3EE:x=(w-text_w)/2:y=(h-text_h)/2+40",
                 "-r", "30", seg])
        else:
            run(["ffmpeg", "-y", "-loop", "1", "-i", os.path.join(SHOTS, src),
                 "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0A0E14,"
                        f"drawtext=fontfile={font()}:text='{esc(cap)}':fontsize=24:"
                        "fontcolor=E6EBF2:x=24:y=H-56:box=1:boxcolor=0A0E14@0.85:boxborderw=12",
                 "-t", str(dur), "-r", "30", seg])

        def stamp(sec: float) -> str:
            h, rem = divmod(sec, 3600)
            m, s = divmod(rem, 60)
            return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"

        srt_lines.append(f"{i + 1}\n{stamp(t)} --> {stamp(t + dur)}\n{SUBS[i]}\n")
        t += dur
        parts.append(f"file '{seg}'")
    with open(os.path.join(tmp, "list.txt"), "w") as fh:
        fh.write("\n".join(parts) + "\n")
    with open(SRT, "w") as fh:
        fh.write("\n".join(srt_lines))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i",
         os.path.join(tmp, "list.txt"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", OUT])
    print(f"wrote {OUT} ({t:.0f}s) + {SRT}")


if __name__ == "__main__":
    main()
