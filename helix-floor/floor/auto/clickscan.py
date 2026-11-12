"""Scan a clicktest recording: each second against the one before it (the tone repeats every second);
an event = 16-sample blocks above the floor + 25 dB. usage: clickscan.py FILE.npy"""
import sys
import numpy as np
FS = 44100
y = np.load(sys.argv[1])
secs = len(y) // FS
s = y[:secs * FS].reshape(secs, FS, -1)
sig = np.sqrt((np.median(s, axis=0) ** 2).mean())
d = (s[1:] - s[:-1]).reshape(-1, s.shape[2])
blk = np.sqrt((d[:len(d) // 16 * 16].reshape(-1, 16, d.shape[1]) ** 2).mean(axis=(1, 2)))
db = 20 * np.log10(blk / sig + 1e-12)
fl = np.median(db)
hits = np.nonzero(db > fl + 25)[0]
ev = []
for h in hits:
    if ev and h - ev[-1][1] <= 20:
        ev[-1][1] = h
    else:
        ev.append([h, h])
# an event at second k shows in diffs k-1->k and k->k+1: keep the first of each pair (same offset in the second)
out, seen = [], set()
for a, b in ev:
    t = a * 16 / FS + 1
    key = (round(t % 1, 3), int(t))
    if (round(t % 1, 3), int(t) - 1) in seen:
        continue
    seen.add(key)
    out.append((t, (b - a + 1) * 16, float(db[a:b + 1].max())))
print(f"{sys.argv[1]}: {secs} s, floor {fl:.1f} dB, {len(out)} event(s)")
for t, n, p in out:
    print(f"  t={t:7.2f} s  {n:5d} samples  peak {p:6.1f} dB")
