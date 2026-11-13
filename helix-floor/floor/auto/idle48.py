"""Idle-meter reader (build/EXPERIMENT-DSP NAM2_IDLEMETER image, kernel nam_floor5i) over ASIO at 48 kHz.
Meter v4 frames; field 4 = the DSP's idle % x 100 (stock idle word), field 1 = -cycles/8 of the meter call.
Prints the DSP load % (100 - idle) of the DSP running the meter block, and the meter block's own cycles.

usage: idle48.py [label] [seconds]   (appends a line to idle_log.txt next to this script)"""
import os
import sys
import time

import numpy as np
import sounddevice as sd

import probe

FS = 48000
label = sys.argv[1] if len(sys.argv) > 1 else ""
N = FS * (float(sys.argv[2]) if len(sys.argv) > 2 else 1.0)
N = int(N)
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
if best is None:
    sys.exit("no meter frame on USB 1 (is the meter block in the preset, panned so USB 1 gets it?)")
f = best[1]
g = np.median(f[:, 0, 0]) / 16384
idle = f[:, 4, 0] / g / 100
cyc = -f[:, 1, 0] / g * 8
load = 100 - idle
line = (f"{time.strftime('%H:%M:%S')} {label!r}: DSP load {np.median(load):.2f}% (min {load.min():.2f}, max {load.max():.2f}, "
        f"{len(load)} frames) | meter block {np.median(cyc):.0f} cycles | gain {g:.4f}")
print(line)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "idle_log.txt"), "a").write(line + "\n")
