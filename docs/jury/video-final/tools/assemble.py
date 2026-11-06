import json, subprocess, os, re, sys
W = '/root/film/work'; R = f'{W}/render'; A = f'{W}/audio'; OUT = f'{W}/out'; os.makedirs(OUT, exist_ok=True)
SFXD = '/root/film/brag/skills/brag/assets/sfx'; MUS = '/root/film/brag/skills/brag/assets/music'
tl = json.load(open(f'{W}/composition/timeline.json')); T = json.load(open(f'{A}/narration/timing.json'))
seg = {s['id']: s for s in T['segments']}
start = {}; t = 0.0
for s in tl: start[s['id']] = round(t, 3); t += s['duration']
TOTAL = round(t, 3)
def run(*a): subprocess.run(['ffmpeg', '-v', 'error', '-y', *a], check=True)
def wt(sid, word, nth=1):
    n = 0
    for w in seg[sid]['words']:
        if re.sub(r'\W', '', w['w']).lower() == word:
            n += 1
            if n == nth: return start[sid] + 0.5 + w['s']
    raise KeyError(word)

# 1) video: concat scene renders (identical encoder settings) -> copy
with open(f'{R}/concat.txt', 'w') as f:
    for s in tl: f.write(f"file '{R}/{s['id']}.mp4'\n")
run('-f', 'concat', '-safe', '0', '-i', f'{R}/concat.txt', '-c', 'copy', '-an', f'{OUT}/video.mp4')

# 2) narration stem
ins, fl = [], []
for i, s in enumerate(tl):
    ins += ['-i', f"{A}/narration/{s['id']}.wav"]; d = int((start[s['id']] + 0.5) * 1000)
    fl.append(f"[{i}:a]aresample=48000,highpass=f=70,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120,adelay={d}|{d},apad[n{i}]")
fl.append(''.join(f'[n{i}]' for i in range(len(tl))) + f"amix=inputs={len(tl)}:normalize=0,pan=stereo|c0=c0|c1=c0,atrim=0:{TOTAL}[v]")
run(*ins, '-filter_complex', ';'.join(fl), '-map', '[v]', '-c:a', 'pcm_s24le', f'{A}/master/narration-stem.wav')

# 3) music stem (arc: drone -> Vol.1 -> tension drone at failure -> Vol.9 resolution)
s04, s08 = start['s04'], start['s08']; t_fail = wt('s08', 'fails'); t_res = wt('s08', 'compensates')
mus = [
 (f'{A}/music/drone-open.wav', 0, 0, s04 + 1.5, 1.0, 0.8, 2.0),
 (f'{MUS}/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3', s04 - 0.3, 0, t_fail - (s04 - 0.3), 0.30, 1.5, 1.2),
 (f'{A}/music/drone-tension.wav', t_fail - 1.5, 0, (t_res + 4) - (t_fail - 1.5), 1.0, 1.0, 3.0),
 (f'{MUS}/happy-beats-business-moves-vol-9-by-ende-dot-app.mp3', t_res + 1.0, 0, TOTAL - (t_res + 1.0), 0.30, 3.0, 4.0),
]
ins, fl = [], []
for i, (f, at, ss, dur, vol, fi, fo) in enumerate(mus):
    ins += ['-i', f]; d = int(at * 1000)
    fl.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atrim={ss}:{ss+dur},asetpts=PTS-STARTPTS,volume={vol},afade=t=in:d={fi},afade=t=out:st={dur-fo}:d={fo},adelay={d}|{d},apad[m{i}]")
fl.append(''.join(f'[m{i}]' for i in range(len(mus))) + f"amix=inputs={len(mus)}:normalize=0,atrim=0:{TOTAL}[m]")
run(*ins, '-filter_complex', ';'.join(fl), '-map', '[m]', '-c:a', 'pcm_s24le', f'{A}/master/music-stem.wav')

# 4) sfx stem (sparse, warm, low-HF picks from the bundled Kenney CC0 set)
sfx = [('impact/impactSoft_heavy_000.ogg', 0.05, .45), ('interface/error_005.ogg', wt('s01', 'billing') + 0.1, .32),
       ('impact/impactSoft_medium_001.ogg', start['s03'] + 0.3, .5), ('interface/bong_001.ogg', wt('s03', 'reversa'), .4),
       ('interface/error_006.ogg', t_fail, .3), ('impact/impactSoft_medium_004.ogg', wt('s08', 'blocks'), .35),
       ('interface/bong_001.ogg', wt('s08', 'verdict'), .4), ('interface/drop_001.ogg', wt('s09', 'export'), .3),
       ('interface/select_008.ogg', wt('s09', 'valid'), .35), ('impact/impactSoft_medium_001.ogg', start['s13'] + 0.3, .45)]
ins, fl = [], []
for i, (f, at, v) in enumerate(sfx):
    p = f'{SFXD}/{f}'
    if not os.path.exists(p): print('missing sfx', f); continue
    ins += ['-i', p]; d = int(at * 1000); k = len(fl)
    fl.append(f"[{len(fl)}:a]aresample=48000,aformat=channel_layouts=stereo,volume={v},adelay={d}|{d},apad[x{k}]")
fl.append(''.join(f'[x{i}]' for i in range(len(fl))) + f"amix=inputs={len(fl)}:normalize=0,atrim=0:{TOTAL}[x]")
run(*ins, '-filter_complex', ';'.join(fl), '-map', '[x]', '-c:a', 'pcm_s24le', f'{A}/master/sfx-stem.wav')

# 5) mix: music ducked by narration (sidechain), then 2-pass loudnorm to -16 LUFS / -1.5 dBTP
mixf = ("[0:a]asplit=2[vo][vk];[1:a][vk]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=450:makeup=1[md];"
        "[vo][md][2:a]amix=inputs=3:normalize=0:weights=1 0.9 1[mx]")
run('-i', f'{A}/master/narration-stem.wav', '-i', f'{A}/master/music-stem.wav', '-i', f'{A}/master/sfx-stem.wav', '-filter_complex', mixf, '-map', '[mx]', '-c:a', 'pcm_s24le', f'{A}/master/premix.wav')
m = subprocess.run(['ffmpeg', '-hide_banner', '-i', f'{A}/master/premix.wav', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
j = json.loads(m[m.rindex('{'):])
ln = f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true"
run('-i', f'{A}/master/premix.wav', '-af', ln + ',aresample=48000', '-c:a', 'pcm_s24le', f'{A}/master/master.wav')

# 6) subtitles from the synthesized-speech token timings
FIX = [(r'\bReversa\b', 'REVERSA'), (r'Next J S', 'Next.js'), (r'\bA\.I\.', 'AI'), (r'\bI\.T\.', 'IT'), (r'fifty nine', '59'),
       (r'eighty one', '81'), (r'\bten step\b', '10-step'), (r'thirty day', '30-day'), (r'read only', 'read-only'),
       (r'hash chained', 'hash-chained'), (r'\bTen steps, ten verified', '10 steps, 10 verified'), (r'\bsandbox only', 'sandbox-only')]
def fix(s):
    for a, b in FIX: s = re.sub(a, b, s)
    return s
cues = []
for s in tl:
    toks = seg[s['id']]['words']; cur = []; off = start[s['id']] + 0.5
    def flush():
        if cur: cues.append([off + cur[0]['s'], off + cur[-1]['e'], ' '.join(w['w'] for w in cur)])
    for w in toks:
        if re.fullmatch(r'[.,:;?!]', w['w']) and cur:
            cur[-1] = dict(cur[-1], w=cur[-1]['w'] + w['w'])
            if w['w'] in '.?!:' or len(' '.join(x['w'] for x in cur)) > 62:
                flush(); cur = []
            continue
        cur.append(w)
        if len(' '.join(x['w'] for x in cur)) > 78: flush(); cur = []
    flush()
# merge punctuation-only and orphan cues (<3 words) into a neighbour
merged = []
for c in cues:
    txt = c[2].strip()
    if merged and (re.fullmatch(r'[.,:;?!]+', txt) or len(txt.split()) < 3) and len(merged[-1][2]) + len(txt) < 92 and c[0] - merged[-1][1] < 0.8:
        merged[-1][1] = c[1]; merged[-1][2] = (merged[-1][2] + ' ' + txt).replace(' .', '.').replace(' ,', ','); continue
    merged.append(c)
cues = []
for c in merged:
    if cues and len(cues[-1][2].split()) < 3 and len(cues[-1][2]) + len(c[2]) < 92 and c[0] - cues[-1][1] < 0.8:
        cues[-1][1] = c[1]; cues[-1][2] += ' ' + c[2]; continue
    cues.append(c)
for i, c in enumerate(cues):
    c[2] = fix(re.sub(r'\s+([,.;:?!])', r'\1', c[2])).strip()
    nxt = cues[i + 1][0] if i + 1 < len(cues) else TOTAL
    c[1] = min(max(c[1] + 0.25, c[0] + 1.0), nxt - 0.04)
TOP = {'s04', 's05', 's06', 's07', 's08', 's09', 's13'}
def scene_of(x):
    k = None
    for s in tl:
        if start[s['id']] <= x: k = s['id']
    return k
def two(s, n=42):
    if len(s) <= n: return s
    w = s.split(); best = None
    for k in range(1, len(w)):
        a, b = ' '.join(w[:k]), ' '.join(w[k:]); sc = max(len(a), len(b))
        if best is None or sc < best[0]: best = (sc, a + '\n' + b)
    return best[1]
def ts(x, sep=','):
    h = int(x // 3600); m = int(x % 3600 // 60); s = x % 60
    return f'{h:02d}:{m:02d}:{int(s):02d}{sep}{int(round((s - int(s)) * 1000)):03d}'
with open(f'{OUT}/final-jury.srt', 'w') as f:
    for i, (a, b, s) in enumerate(cues, 1): f.write(f'{i}\n{ts(a)} --> {ts(b)}\n{two(s)}\n\n')
with open(f'{OUT}/final-jury.vtt', 'w') as f:
    f.write('WEBVTT\n\n')
    for a, b, s in cues: f.write(f"{ts(a, '.')} --> {ts(b, '.')}\n{two(s)}\n\n")
ass_head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\n\n[V4+ Styles]\n"
 "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
 "Style: Default,Inter,40,&H00EEEBE9,&H00FFFFFF,&H00000000,&H9A0E0C0B,0,0,0,0,100,100,0,0,3,14,0,2,200,200,34,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
def at(x): return f'{int(x//3600)}:{int(x%3600//60):02d}:{x%60:05.2f}'
with open(f'{OUT}/final-jury.ass', 'w') as f:
    f.write(ass_head)
    for a, b, s in cues: f.write(f"Dialogue: 0,{at(a)},{at(b)},Default,,0,0,{128 if scene_of(a) in TOP else 0},,{'{\\an8}' if scene_of(a) in TOP else ''}{two(s).replace(chr(10), '\\N')}\n")

# 7) masters: clean + captioned (subtitles burnt with libass; video re-encoded only for the captioned copy)
run('-i', f'{OUT}/video.mp4', '-i', f'{A}/master/master.wav', '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-movflags', '+faststart', '-shortest', f'{OUT}/final-jury-clean.mp4')
if '--captions' in sys.argv:
    run('-i', f'{OUT}/final-jury-clean.mp4', '-vf', f"ass={OUT}/final-jury.ass:fontsdir=/root/film/work/composition/assets/fonts", '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', f'{OUT}/final-jury.mp4')
json.dump({"total": TOTAL, "scene_starts": start, "music": [m[:2] for m in mus], "sfx": sfx, "cues": len(cues)}, open(f'{OUT}/edit-manifest.json', 'w'), indent=1)
print('TOTAL', TOTAL, 'cues', len(cues))
