import sys, subprocess, numpy as np, json
from faster_whisper import WhisperModel
m = WhisperModel("small.en", device="cpu", compute_type="int8")
def load(f): return np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",f,"-ac","1","-ar","16000","-f","f32le","-"],capture_output=True).stdout, np.float32)
words_mode = sys.argv[1] == "--words"
for f in (sys.argv[2:] if words_mode else sys.argv[1:]):
    segs, _ = m.transcribe(load(f), beam_size=5, word_timestamps=words_mode)
    segs = list(segs)
    if words_mode: print(json.dumps([{"w":w.word.strip(),"s":round(w.start,3),"e":round(w.end,3)} for s in segs for w in s.words]))
    else: print(f.split('/')[-1], "|", " ".join(s.text.strip() for s in segs))
