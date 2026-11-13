"""Play 220 Hz into USB 3/4 for N s, record USB 1; report level, harmonics and dropouts (100 ms windows)."""
import sys
import probe
import numpy as np, sounddevice as sd
FS = 44100; secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5
t = np.arange(int(FS * secs)) / FS
out = np.zeros((len(t), 8), np.float32); out[:, 2] = out[:, 3] = 0.25 * np.sin(2 * np.pi * 220 * t)
got = np.zeros_like(out); p = 0
with sd.Stream(device=probe.dev(), channels=8, samplerate=FS, dtype="float32") as st:
    while p < len(t):
        n = min(512, len(t) - p); st.write(np.ascontiguousarray(out[p:p + n])); got[p:p + n], _ = st.read(n); p += n
x = got[FS:, 0]
w = x[: len(x) // 4410 * 4410].reshape(-1, 4410); r = 20 * np.log10(np.sqrt((w ** 2).mean(1)) + 1e-9)
X = np.abs(np.fft.rfft(x * np.hanning(len(x)))); f = np.fft.rfftfreq(len(x), 1 / FS)
h = [X[np.argmin(abs(f - 220 * k))] for k in range(1, 6)]
d = np.abs(np.diff(x)); spikes = int((d > 8 * np.median(d) + 0.05).sum())
print("level %.1f dBFS, 100ms windows min %.1f max %.1f, H2..H5 %s dB, jumps %d" % (
    20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9), r.min(), r.max(), [round(20 * np.log10(v / h[0] + 1e-12), 1) for v in h[1:]], spikes))
