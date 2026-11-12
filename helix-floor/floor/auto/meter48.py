"""Meter v4 reader over ASIO at 48 kHz: frames of 8 two-sample fields, signs + - + - + - + -, field 0 =
16384 x gain. Prints the gain-corrected fields and cycles a call (field 1 x -8)."""
import probe
import numpy as np, sounddevice as sd
FS = 48000; N = FS
out = np.zeros((N, 8), np.float32); got = np.zeros_like(out); p = 0
with sd.Stream(device=probe.dev(), channels=8, samplerate=FS, dtype="float32") as st:
    while p < N:
        k = min(512, N - p); st.write(out[p:p + k]); got[p:p + k], _ = st.read(k); p += k
n = got[FS // 4:, 0].astype(np.float64) * 32768
best = None
for ph in range(16):
    m = (len(n) - ph) // 16
    f = n[ph:ph + 16 * m].reshape(m, 8, 2)
    c = f[:, 0, 0]
    if (c <= 0).any():
        continue
    sc = -np.mean(c) + 1000 * (np.std(c) > 2)        # field 0: the largest steady positive value
    if best is None or sc < best[0]:
        best = (sc, f)
f = best[1]
g = np.median(f[:, 0, 0]) / 16384
vals = np.median(f[:, :, 0], axis=0) / g
cyc = -f[:, 1, 0] / g * 8
print("gain %.4f | fields %s" % (g, [int(round(v)) for v in vals]))
print("cycles a call: median %.0f, mean %.0f, max %.0f (%d calls)" % (np.median(cyc), cyc.mean(), cyc.max(), len(cyc)))
