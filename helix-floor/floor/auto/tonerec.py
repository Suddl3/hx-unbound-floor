"""Record the Floor's USB 1 for a fixed 220 Hz + 523 Hz tone into USB 3/4 (6 s); save .npy; with a
reference file, align by cross-correlation and report the residual (dB below the signal)."""
import sys
import probe
import numpy as np, sounddevice as sd
FS = 44100; secs = 6
t = np.arange(FS * secs) / FS
x = (0.2 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 523 * t)).astype(np.float32)
out = np.zeros((len(t), 8), np.float32); out[:, 2] = out[:, 3] = x
got = np.zeros_like(out); p = 0
with sd.Stream(device=probe.dev(), channels=8, samplerate=FS, dtype="float32") as st:
    while p < len(t):
        n = min(512, len(t) - p); st.write(np.ascontiguousarray(out[p:p + n])); got[p:p + n], _ = st.read(n); p += n
y = got[FS:, 0].astype(np.float64)
np.save(sys.argv[1], y)
print("saved", sys.argv[1], "level %.1f dBFS" % (20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-12)))
if len(sys.argv) > 2:
    r = np.load(sys.argv[2]); n = min(len(r), len(y)) - 4410
    a = r[2205:2205 + n]
    best = None
    for lag in range(-2205, 2205):
        b = y[2205 + lag:2205 + lag + n]
        if len(b) < n: continue
        e = np.sum((a - b) ** 2)
        if best is None or e < best[0]: best = (e, lag)
    e, lag = best
    print("lag %d samples, residual %.1f dB below signal" % (lag, 10 * np.log10(e / np.sum(a ** 2) + 1e-30)))
