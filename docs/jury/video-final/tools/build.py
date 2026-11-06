import json, os, re, shutil
W = '/root/film/work'; T = json.load(open(f'{W}/audio/narration/timing.json'))
SEG = {s['id']: s for s in T['segments']}
PROD = json.load(open(f'{W}/footage2/prod-capture.json'))
LAT = PROD['aiCreatedEvent']['payload']['latency_ms'] / 1000
AIWF = PROD['aiWorkflow']
LEAD = 0.5
# scene durations (s)
DUR = dict(s01=9.0, s02=18.6, s03=10.0, s04=18.5, s05=23.0, s06=16.0, s07=18.0, s08=27.0, s09=21.5, s10=20.0, s11=24.0, s12=15.5, s13=7.5)
for k, s in SEG.items(): DUR[k] = max(DUR[k], round(LEAD + s['dur'] + 1.0, 2))

def wt(sid, word, nth=1, end=False):
    """film-time (within scene) of the nth token matching word."""
    n = 0
    for w in SEG[sid]['words']:
        if re.sub(r'\W', '', w['w']).lower() == re.sub(r'\W', '', word).lower():
            n += 1
            if n == nth: return round(LEAD + (w['e'] if end else w['s']), 2)
    raise KeyError((sid, word, nth))

CSS = open('/root/film/tools/style.css').read()

def page(sid, body, js):
    d = DUR[sid]
    return f'''<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=1920, height=1080">
<title>REVERSA {sid}</title><script src="assets/gsap.min.js"></script><style>{CSS}</style></head><body>
<div id="root" data-composition-id="{sid}" data-start="0" data-duration="{d}" data-width="1920" data-height="1080">
<div class="bg" data-layout-ignore></div>
{body}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
const IN = (s, t, o={{}}) => tl.fromTo(s, {{opacity:0, y: o.y ?? 18, filter: o.blur ? 'blur(8px)' : 'blur(0px)'}}, {{opacity:1, y:0, filter:'blur(0px)', duration: o.d ?? .6, ease: o.e ?? 'power3.out'}}, t);
const OUT = (s, t, d=.45) => tl.to(s, {{opacity:0, duration:d, ease:'power2.in'}}, t);
{js}
tl.fromTo('#root', {{opacity:0}}, {{opacity:1, duration:.35, ease:'power1.out'}}, 0);
tl.to('#root', {{opacity:0, duration:.35, ease:'power1.in'}}, {d - 0.35});
window.__timelines = window.__timelines || {{}}; window.__timelines["{sid}"] = tl; tl.seek(0);
</script></body></html>'''

def plate(sid, push=1.035):
    d = DUR[sid]
    return (f'<video id="plate" class="clip media" data-start="0" data-duration="{d}" data-track-index="1" muted playsinline src="assets/plates/{sid}.mp4"></video>',
            f"tl.fromTo('#plate', {{scale:1}}, {{scale:{push}, duration:{d}, ease:'none'}}, 0);")

def chip(text, live=False):
    return f'<div class="chip{" live" if live else ""}">{"<i></i>" if live else ""}{text}</div>'

def label(n, t): return f'<div class="label"><span>{n:02d}</span>{t}</div>'

S = {}
# 01 HOOK
v, j = plate('s01', 1.06)
S['s01'] = (f'''{v}<div class="clip shade-left red" data-start="0" data-duration="{DUR['s01']}" data-track-index="2"></div>
<div class="clip layer" data-start="0" data-duration="{DUR['s01']}" data-track-index="3">
 <div class="hook"><div class="eyebrow bad" id="h0">Step 6 of 10 · Billing · Failed</div>
 <h1 id="h1">Half the job is done.</h1><h1 id="h2" class="muted2">Who puts the rest back?</h1></div>
 {chip('Real recording · REVERSA demo tenant')}</div>''',
 j + f"IN('#h0',{wt('s01','billing')-0.2}); IN('#h1',0.5,{{blur:1,d:.8}}); IN('#h2',{wt('s01','who')-0.1},{{blur:1,d:.8}}); IN('.chip',0.3);")

# 02 PROBLEM
systems = [("CRM", [(1,"Validate customer"),(2,"Create organization")]),("Identity",[(3,"Create workspace"),(4,"Provision users"),(7,"Assign manager")]),
           ("Support",[(5,"Create queue"),(8,"Onboarding checklist")]),("Billing",[(6,"Create billing profile")]),("Notify",[(10,"Send summary")])]
cards = ''
for i,(n,steps) in enumerate(systems):
    rows = ''.join(f'<div class="st" data-step="{k}"><b>{k}</b><span>{t}</span><em></em></div>' for k,t in steps)
    cards += f'<div class="sys" id="sys{i}"><div class="sysn">{n}</div>{rows}</div>'
w2 = ['crm','identity','support','billing','notifications']
js2 = f"IN('#p-title',0.4,{{blur:1}});" + ''.join(f"IN('#sys{i}',{wt('s02',w)-0.15},{{y:26}});" for i,w in enumerate(w2))
t6 = wt('s02','fails'); t15 = wt('s02','every')
js2 += ''.join(f"tl.call(()=>document.querySelector('[data-step=\"{k}\"]').classList.add('ok'),null,{round(t15+0.2*i,2)});" for i,k in enumerate([1,2,3,4,5,7,8]))
js2 += f"tl.call(()=>document.querySelector('[data-step=\"6\"]').classList.add('bad'),null,{t6});"
js2 += ''.join(f"tl.call(()=>document.querySelector('[data-step=\"{k}\"]').classList.add('unk'),null,{t6+0.9+0.12*i});" for i,k in enumerate([10]))
js2 += f"IN('#q1',{wt('s02','changed',2)-0.3}); IN('#q2',{wt('s02','undo')-0.3}); IN('#q3',{wt('s02','prove')-0.1});"
S['s02'] = (f'''<div class="clip layer" data-start="0" data-duration="{DUR['s02']}" data-track-index="2">{label(1,'The problem')}
<h2 class="ptitle" id="p-title">Partial failure. Real consequences.</h2><div class="systems">{cards}</div>
<div class="qs"><div id="q1">What actually changed?</div><div id="q2">What is safe to undo?</div><div id="q3">Where did it end?</div></div>
<div class="foot">The real failed run (#2): steps 7 and 8 had already run in parallel when billing failed. Step 9 is a REVERSA consistency check.</div></div>''', js2)

# 03 REVEAL
S['s03'] = (f'''<img id="still" class="clip media still" data-start="0" data-duration="{DUR['s03']}" data-track-index="1" src="assets/plates/overview-still.jpg">
<div class="clip layer center" data-start="0" data-duration="{DUR['s03']}" data-track-index="2">
<div class="mark" id="mk"><svg viewBox="0 0 20 20" width="84" height="84"><rect x=".5" y=".5" width="19" height="19" rx="5" fill="#191c21" stroke="rgba(255,255,255,.16)"/><path d="M6 13.5V6.5h4.2a2.3 2.3 0 0 1 0 4.6H6m4 0 3.5 2.4" fill="none" stroke="#7c9cff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
<div class="wordmark" id="wm">REVERSA</div><div class="rule" id="rl"></div>
<div class="tag" id="tg">The recovery control plane for enterprise AI operations</div>
<div class="tag2" id="t2">Reversible where possible. Accountable everywhere.</div></div>''',
 f"tl.fromTo('#still',{{opacity:0,scale:1.08}},{{opacity:.14,scale:1,duration:{DUR['s03']},ease:'none'}},0);IN('#mk',0.3,{{d:.8}});IN('#wm',{wt('s03','reversa')-0.1},{{blur:1,d:.9}});tl.fromTo('#rl',{{width:0}},{{width:120,duration:.6,ease:'power3.out'}},{wt('s03','reversa')+0.5});IN('#tg',{wt('s03','recovery')-0.1});IN('#t2',{wt('s03','reversible')-0.1});")

def footage_scene(sid, n, lab, chiptxt, live, caption_html, js_extra, push=1.03):
    v, j = plate(sid, push)
    return (f'''{v}<div class="clip shade-bottom" data-start="0" data-duration="{DUR[sid]}" data-track-index="2"></div>
<div class="clip layer" data-start="0" data-duration="{DUR[sid]}" data-track-index="3">{label(n, lab)}{chip(chiptxt, live)}{caption_html}</div>''',
            j + "IN('.label',0.25);IN('.chip',0.35);" + js_extra)

# 04 LIVE DEMO
S['s04'] = footage_scene('s04', 2, 'Live on Vultr', '217.69.7.155.nip.io · recorded 6 Nov 2026', True,
 '<div class="cap"><div class="ct" id="c1">The real application, live on Vultr.</div><div class="cs" id="c2">Guided demo · isolated demo tenant · deterministic planner · 10 steps · 5 demo systems</div></div>',
 f"IN('#c1',{wt('s04','real')-0.2});IN('#c2',{wt('s04','isolated')});")

# 05 AI
t_plan = 14.0
S['s05'] = footage_scene('s05', 3, 'AI planning', 'Vultr Serverless Inference · live capture', True,
 f'''<div class="proof" id="pf"><div class="ph">Recorded provenance · workflow #{AIWF}</div>
<div><span>provider</span><b>vultr-inference</b></div><div><span>latency</span><b>{LAT:.1f} s</b></div><div><span>attempts</span><b>1</b></div><div><span>warnings</span><b>none</b></div></div>
<div class="flow3" id="f3"><div id="fa">AI proposes</div><i>→</i><div id="fb">Policy validates</div><i>→</i><div id="fc">REVERSA executes</div></div>''',
 f"IN('#pf',{t_plan},{{y:24}});OUT('#pf',{wt('s05','deterministic')-0.6});IN('#f3',{wt('s05','deterministic')-0.3});"
 f"tl.fromTo('#fa',{{color:'#959ba5'}},{{color:'#e9ebee',duration:.3}},{wt('s05','model',2)});tl.fromTo('#fb',{{color:'#959ba5'}},{{color:'#7c9cff',duration:.3}},{wt('s05','deterministic')});tl.fromTo('#fc',{{color:'#959ba5'}},{{color:'#57c78a',duration:.3}},{wt('s05','provenance')});")

# 06 PREVIEW
S['s06'] = footage_scene('s06', 4, 'Preview & approval', 'Real recording · same build as production', False,
 '<div class="cap"><div class="ct" id="c1">Every effect visible before execution.</div><div class="ct alt" id="c2">Human approval when required.</div><div class="cs" id="c3">notify.send_summary is flagged irreversible — it cannot be unsent.</div></div>',
 f"IN('#c1',0.6);OUT('#c1',{wt('s06','person')-0.4});IN('#c2',{wt('s06','person')});OUT('#c2',{wt('s06','notification')-0.4});IN('#c3',{wt('s06','notification')});")

# 07 EXECUTION
S['s07'] = footage_scene('s07', 5, 'Verified execution', 'Real recording · same build as production', False,
 '<div class="cap row"><div class="word" id="w1">Execute.</div><div class="word" id="w2">Verify.</div><div class="word" id="w3">Record.</div>'
 '<div class="stat" id="st"><b>10 / 10</b> steps verified<br><b>59</b> events recorded</div></div>',
 f"IN('#w1',{wt('s07','executes')-0.2});IN('#w2',{wt('s07','confirm')-0.2});IN('#w3',{wt('s07','recorded')-1.6});IN('#st',{wt('s07','ten')-0.2});")

# 08 FAILURE + RECOVERY
st = [("Failure detected", wt('s08','fails')-0.3), ("Dependents blocked", wt('s08','blocks')-0.2), ("Safe changes reversed", wt('s08','compensates')-0.2), ("Outcome verified", wt('s08','verdict')-0.2)]
items = ''.join(f'<div class="stage-i" id="g{i}"><span class="dot"></span>{t}</div>' for i,(t,_) in enumerate(st))
js8 = ''.join(f"IN('#g{i}',{t},{{y:10}});tl.call(()=>document.getElementById('g{i}').classList.add('on'),null,{t});" for i,(_,t) in enumerate(st))
S['s08'] = footage_scene('s08', 6, 'Failure & recovery', 'Real recording · injected fault, isolated demo tenant', False,
 f'<div class="cap"><div class="stages">{items}</div><div class="cs" id="fn">Step 6 failed after 2 attempts · 2 dependent steps skipped · 7 compensation steps in reverse order, 1 of them a read-only no-op · verdict VERIFIED_WITH_COMPENSATION (restored = effect verified absent)</div></div>',
 js8 + f"IN('#fn',{wt('s08','seven')-0.2});", 1.02)

# 09 EVIDENCE
cli = open(f'{W}/footage2/cli-verify.txt').read().strip().splitlines()
def cl(l):
    l = l.replace('<','&lt;')
    if l.startswith('$'): return f'<div class="cmd">{l}</div>'
    if l.startswith('VALID'): return f'<div class="okl">{l}</div>'
    return f'<div class="dim">{l}</div>'
lines = ''.join(cl(l) for l in cli if not l.startswith('exit='))
tterm = wt('s09','export')-0.3
S['s09'] = footage_scene('s09', 7, 'Evidence Passport', 'Real recording + real offline verifier output', False,
 f'''<div class="cap"><div class="ct" id="c1">Don't trust a success message.</div><div class="ct alt" id="c2">Verify the evidence.</div></div>
<div class="term" id="tm"><div class="tbar"><i></i><i></i><i></i><span>offline · python -m reversa_api.cli</span></div><div class="tbody">{lines}</div></div>''',
 f"IN('#c1',0.5);OUT('#c1',{tterm-0.4});IN('#c2',{tterm});tl.to('#plate',{{opacity:.28,duration:.6}},{tterm});IN('#tm',{tterm},{{y:30,d:.7}});"
 f"tl.fromTo('#tm .tbody > div',{{opacity:0}},{{opacity:1,duration:.25,stagger:.9}},{tterm+0.5});")

# 10 VULTR
S['s10'] = (f'''<div class="clip layer" data-start="0" data-duration="{DUR['s10']}" data-track-index="2">{label(8,'Architecture')}
<h2 class="ptitle" id="vt">Built and running on Vultr.</h2>
<div class="arch">
 <div class="node n-br" id="a0"><b>Browser</b><span>Next.js console</span></div><div class="arr" id="ar0">HTTPS</div>
 <div class="vm" id="a1"><div class="vmh">Vultr Cloud Compute <span>vc2-2c-4gb · Paris · one instance</span></div>
  <div class="vmrow"><div class="node" id="b0"><b>Caddy</b><span>automatic TLS</span></div><div class="node" id="b1"><b>Next.js</b><span>web console</span></div><div class="node" id="b2"><b>FastAPI</b><span>API + saga worker</span></div></div>
  <div class="vmrow"><div class="node" id="b3"><b>PostgreSQL 16</b><span>workflows · actions · events</span></div><div class="node" id="b4"><b>5 isolated demo stores</b><span>CRM · Identity · Support · Billing · Notify</span></div></div></div>
 <div class="arr dashed" id="ar1">plans</div>
 <div class="node n-inf" id="a2"><b>Vultr Serverless Inference</b><span>optional AI planner</span></div></div></div>''',
 f"IN('#vt',0.4,{{blur:1}});IN('#a0',{wt('s10','platform')});IN('#ar0',{wt('s10','vultr')-0.2});IN('#a1',{wt('s10','cloud')-0.2});"
 f"IN('#b1',{wt('s10','next')-0.1});IN('#b2',{wt('s10','fastapi')-0.1});IN('#b3',{wt('s10','postgres')-0.1});IN('#b4',{wt('s10','five')-0.1});IN('#b0',{wt('s10','tls')-0.3});"
 f"IN('#ar1',{wt('s10','vultr',2)-0.2});IN('#a2',{wt('s10','vultr',2)});")

# 11 BUSINESS
S['s11'] = (f'''<div class="clip layer" data-start="0" data-duration="{DUR['s11']}" data-track-index="2">{label(9,'Business value')}
<div class="biz"><div class="bcol"><div class="bh" id="bh">Who buys</div><div class="bb" id="bb">IT Operations and Business Systems teams running automation across many SaaS tools.</div></div>
<div class="bcol"><div class="bh" id="ch">Where the cost really is</div><div class="cost" id="k1">Investigation</div><div class="cost" id="k2">Manual repair</div><div class="cost" id="k3">Proving the final state</div><div class="vs" id="k4">Workflow engines retry and roll back. REVERSA proves the final state.</div></div>
<div class="bcol pilot" id="pl"><div class="bh">First offer</div><div class="pt">30-day Recovery Audit</div><div class="bb">Sandbox only · success criteria agreed up front · then platform fee + execution volume (hypothesis)</div><div class="honest" id="hn">0 customers today. The pilot is how we earn the first.</div></div></div></div>''',
 f"IN('#bh',0.5);IN('#bb',{wt('s11','operations')-0.3});IN('#ch',{wt('s11','expensive')-0.2});IN('#k1',{wt('s11','investigation')-0.1});IN('#k2',{wt('s11','manual')-0.1});IN('#k3',{wt('s11','proving')-0.1});IN('#k4',{wt('s11','workflow')-0.1});"
 f"IN('#pl',{wt('s11','offer')-0.3},{{y:24}});IN('#hn',{wt('s11','customers')-0.2});")

# 12 ORIGINALITY
pil = [("Typed compensation","typed"),("Verify after every effect","verification"),("Uncertainty stays explicit","uncertain"),("AI planning ≠ authorization","planning"),("Evidence anyone can check","evidence")]
pills = ''.join(f'<div class="pil" id="o{i}"><small>0{i+1}</small>{t}</div>' for i,(t,_) in enumerate(pil))
S['s12'] = (f'''<img id="still" class="clip media still" data-start="0" data-duration="{DUR['s12']}" data-track-index="1" src="assets/plates/recovery-still.jpg">
<div class="clip layer" data-start="0" data-duration="{DUR['s12']}" data-track-index="2">{label(10,'What is new')}<div class="pils">{pills}</div><div class="layerbar" id="lb">One control layer</div></div>''',
 f"tl.fromTo('#still',{{opacity:0}},{{opacity:.1,duration:1}},0);" + ''.join(f"IN('#o{i}',{wt('s12',w)-0.15},{{y:16}});" for i,(_,w) in enumerate(pil)) + f"IN('#lb',{wt('s12','control')-0.4},{{y:20,d:.8}});")

# 13 OUTRO
S['s13'] = (f'''<div class="clip layer center" data-start="0" data-duration="{DUR['s13']}" data-track-index="2">
<div class="wordmark big" id="wm">REVERSA</div><div class="rule" id="rl"></div><div class="tag2" id="t2">Reversible where possible. Accountable everywhere.</div>
<div class="url" id="u">217.69.7.155.nip.io</div><div class="foot2" id="f">Vultr Agent Rush 2026 · Challenge 2 — Powering the Future of Work · github.com/toskaman/reversa</div></div>''',
 f"IN('#wm',0.3,{{blur:1,d:1}});tl.fromTo('#rl',{{width:0}},{{width:120,duration:.6}},1.0);IN('#t2',{wt('s13','reversible')-0.1});IN('#u',{wt('s13','everywhere')+0.4});IN('#f',{wt('s13','everywhere')+0.8});")

out = f'{W}/composition/scenes'; os.makedirs(out, exist_ok=True)
manifest = []
for sid in sorted(S):
    d = f'{out}/{sid}'; os.makedirs(d, exist_ok=True)
    if not os.path.exists(f'{d}/assets'): os.symlink(f'{W}/composition/assets', f'{d}/assets')
    body, js = S[sid]; open(f'{d}/index.html', 'w').write(page(sid, body, js))
    json.dump({"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json", "paths": {"assets": "assets"}}, open(f'{d}/hyperframes.json', 'w'))
    json.dump({"id": f"reversa-{sid}", "name": f"REVERSA jury film {sid}"}, open(f'{d}/meta.json', 'w'))
    manifest.append({"id": sid, "duration": DUR[sid], "narration_start": LEAD, "narration_dur": SEG[sid]['dur']})
json.dump(manifest, open(f'{W}/composition/timeline.json', 'w'), indent=1)
print(sum(m['duration'] for m in manifest), [ (m['id'], m['duration']) for m in manifest])
