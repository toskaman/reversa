# Original underscore pad (generated, no third-party material). 48 kHz stereo.
import numpy as np, soundfile as sf, sys
sr = 48000
def pad(dur, freqs, detune=0.15, pulse_bpm=None, seed=1):
    t = np.arange(int(sr*dur))/sr; rng = np.random.default_rng(seed)
    L = np.zeros_like(t); R = np.zeros_like(t)
    for f, a in freqs:
        for d, pan in ((-detune, .35), (detune, .65)):
            ph = rng.uniform(0, 2*np.pi)
            s = np.sin(2*np.pi*(f+d)*t + ph) + 0.18*np.sin(2*np.pi*2*(f+d)*t + ph)
            L += a*s*(1-pan); R += a*s*pan
    lfo = 0.75 + 0.25*np.sin(2*np.pi*t/9.0)
    L *= lfo; R *= lfo
    if pulse_bpm:
        per = 60/pulse_bpm; k = (t % per)/per
        env = np.exp(-k*9) * (k < 0.5)
        thump = np.sin(2*np.pi*48*t) * env * 0.55
        L += thump; R += thump
    # gentle air (lowpassed noise)
    n = rng.normal(0, 1, (2, len(t)));
    for ch in n:
        for _ in range(3): ch[1:] = ch[1:]*0.04 + ch[:-1]*0.96
    L += n[0]*0.08; R += n[1]*0.08
    x = np.stack([L, R], 1); x /= np.max(np.abs(x)) + 1e-9
    fade = int(sr*1.5); ramp = np.linspace(0, 1, fade)[:, None]
    x[:fade] *= ramp; x[-fade:] *= ramp[::-1]
    return x * 0.5
A1, E2, A2, C3, Bb2 = 55.0, 82.41, 110.0, 130.81, 116.54
sf.write('/root/film/work/audio/music/drone-open.wav', pad(38.5, [(A1,1),(E2,.6),(A2,.35),(C3,.18)], pulse_bpm=58), sr)
sf.write('/root/film/work/audio/music/drone-tension.wav', pad(30.0, [(A1,1),(E2,.5),(Bb2,.22),(A2,.25)], pulse_bpm=64, seed=3), sr)
print('ok')
