import numpy as np, wave
SR = 44100
def note(freq, dur, amp=1.0):
    t = np.arange(int(dur*SR))/SR
    y = sum(np.sin(2*np.pi*freq*k*t)/k for k in (1,2,3,4))
    env = np.minimum(1, t/0.01) * np.minimum(1, (dur - t)/0.02)
    return (y*env*amp).astype(np.float32)
def midi(n): return 440*2**((n-69)/12)
def make_track(bpm, tonic=9, minor=True, seconds=10, seed=0, drums=True, swing=0.0, halftime=False):
    rng = np.random.default_rng(seed)
    x = np.zeros(int(seconds*SR)+SR, dtype=np.float32)
    beat = 60/bpm*SR
    def add(sig, pos):
        pos = int(pos)
        if pos >= len(x): return
        L = min(len(sig), len(x)-pos); x[pos:pos+L] += sig[:L]
    if drums:
        t = np.arange(int(0.18*SR))/SR
        f = 50 + 90*np.exp(-t/0.03); kick = np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t/0.07)*0.9
        sn = rng.standard_normal(int(0.14*SR)).astype(np.float32)*np.exp(-np.arange(int(0.14*SR))/SR/0.04)*0.5
        hat = np.diff(rng.standard_normal(int(0.04*SR)+1)).astype(np.float32)*np.exp(-np.arange(int(0.04*SR))/SR/0.01)*0.25
        k = 0
        while k*beat < seconds*SR:
            if halftime:
                if k % 4 == 0: add(kick, k*beat)
                if k % 4 == 2: add(sn, k*beat)
            else:
                add(kick, k*beat)
                if k % 2 == 1: add(sn, k*beat)
            add(hat, k*beat + beat/2 + swing*beat/4)
            k += 1
    # harmony: tonic-heavy progression, root in bass + triad
    if minor: prog = [(0,(0,3,7)),(5,(0,3,7)),(0,(0,3,7)),(7,(0,3,7))]
    else:     prog = [(0,(0,4,7)),(5,(0,4,7)),(0,(0,4,7)),(7,(0,4,7))]
    bar = 4*beat; i = 0
    while i*bar < seconds*SR:
        root, tri = prog[i % 4]
        base = 48 + tonic + root           # C3 + tonic
        d = bar/SR
        add(note(midi(base-12), d, 0.5), i*bar)
        for iv in tri: add(note(midi(base+12+iv), d, 0.25), i*bar)
        i += 1
    x = x[:int(seconds*SR)]
    x = x/ max(1e-6, np.abs(x).max()) * 0.8
    return x
def write(path, x):
    with wave.open(path,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(x,-1,1)*32767).astype("<i2").tobytes())
