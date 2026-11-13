"""Click count: play 220 + 523 Hz into Floor USB 3/4 for SECS seconds, record USB out 1/2, find glitches.
The tone repeats exactly every second (gcd(220, 523) = 1), so once steady each second of output should
equal the median of all seconds; a 16-sample block more than THRESH dB above the residual floor counts.
Run it on the preset as it is (06D with or without `namtest.py load`).
usage: clicktest.py LABEL [secs=120]     -> saves ../../build/EXPERIMENT-KERNEL/click_LABEL.npy, prints events"""
import os
import sys
os.environ["SD_ENABLE_ASIO"] = "1"
import numpy as np
import sounddevice as sd
import probe

FS, THRESH = 44100, -40.0
label = sys.argv[1]
secs = int(sys.argv[2]) if len(sys.argv) > 2 else 120
t = np.arange(FS * (secs + 2)) / FS
x = (0.2 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 523 * t)).astype(np.float32)
out = np.zeros((len(t), 8), np.float32)
out[:, 2] = out[:, 3] = x
got = np.zeros_like(out)
p = 0
with sd.Stream(device=probe.dev(), channels=8, samplerate=FS, dtype="float32") as st:
    while p < len(t):
        n = min(512, len(t) - p)
        st.write(np.ascontiguousarray(out[p:p + n]))
        got[p:p + n], _ = st.read(n)
        p += n
y = got[FS:FS * (secs + 1), :2]                       # drop the first and last second
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "build", "EXPERIMENT-KERNEL",
                    f"click_{label}.npy")
np.save(path, y)
sec = y.reshape(secs, FS, 2)
med = np.median(sec, axis=0)
sig = np.sqrt((med ** 2).mean())
d = (sec - med).reshape(-1, 2)
blk = np.sqrt((d[: len(d) // 16 * 16].reshape(-1, 16, 2) ** 2).mean(axis=(1, 2)))
db = 20 * np.log10(blk / sig + 1e-12)
floor_db = np.median(db)
hits = np.nonzero(db > max(THRESH, floor_db + 15))[0]
events = []
for h in hits:                                         # merge blocks closer than 20 blocks into one event
    if events and h - events[-1][1] <= 20:
        events[-1][1] = h
    else:
        events.append([h, h])
print(f"{label}: {secs} s, level {20 * np.log10(sig):.1f} dBFS, residual floor {floor_db:.1f} dB, "
      f"{len(events)} glitch event(s)")
for a, b in events:
    print(f"  t={a * 16 / FS + 1:7.2f} s  {(b - a + 1) * 16:4d} samples  peak {db[a:b + 1].max():.1f} dB")
