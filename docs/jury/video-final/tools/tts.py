import json, sys, re, soundfile as sf, numpy as np
from kokoro import KPipeline
# Pronunciation dictionary (misaki inline phonemes). Subtitles keep the original spelling.
LEX = {
  "REVERSA": "[Reversa](/ɹəvˈɜɹsə/)",
  "Vultr": "[Vultr](/vˈʌltʃəɹ/)",
  "Next.js": "Next J S", "no op": "[no-op](/nˈoʊ ˈɑp/)",
}
def tts_text(t):
    for k, v in LEX.items(): t = t.replace(k, v)
    return t
def gen(pipe, voice, text, out, speed=1.0):
    chunks, words = [], []; off = 0.0
    for r in pipe(tts_text(text), voice=voice, speed=speed, split_pattern=r'\n+'):
        a = r.audio.numpy() if hasattr(r.audio, 'numpy') else np.asarray(r.audio)
        for tk in (r.tokens or []):
            if tk.start_ts is not None and tk.text.strip():
                words.append({"w": tk.text, "s": round(off + tk.start_ts, 3), "e": round(off + (tk.end_ts or tk.start_ts), 3)})
        chunks.append(a); off += len(a) / 24000
    audio = np.concatenate(chunks); sf.write(out, audio, 24000)
    return len(audio) / 24000, words
if __name__ == "__main__":
    mode = sys.argv[1]; pipe = KPipeline(lang_code='a' if mode != 'b' else 'b')
    if mode == "cast":
        line = "Your automation just finished half of a customer onboarding. Then billing failed. This is REVERSA, running live on Vultr, with a Fast A P I engine and Postgres."
        for v in sys.argv[2].split(","):
            d, _ = gen(pipe, v, line, f"/root/film/work/audio/cast_{v}.wav"); print(v, round(d, 2))
    else:
        voice = sys.argv[2]; speed = float(sys.argv[3]); script = json.load(open('/root/film/work/script.json')); meta = []
        only = sys.argv[4].split(',') if len(sys.argv) > 4 else None
        old = {x['id']: x for x in json.load(open('/root/film/work/audio/narration/timing.json'))['segments']} if only else {}
        for s in script:
            if only and s['id'] not in only: meta.append(old[s['id']]); continue
            d, words = gen(pipe, voice, s["text"], f"/root/film/work/audio/narration/{s['id']}.wav", speed)
            meta.append({"id": s["id"], "dur": round(d, 3), "words": words}); print(s["id"], round(d, 2))
        json.dump({"voice": voice, "speed": speed, "engine": "kokoro 0.9.4 / Kokoro-82M", "segments": meta}, open('/root/film/work/audio/narration/timing.json', 'w'), indent=1)
