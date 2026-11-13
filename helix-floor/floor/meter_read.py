#!/usr/bin/env python3
"""Read the nam_floor5m meter from the Floor's USB audio: records a few seconds of the
"Digital Audio Interface (Line 6 Helix)" input with ffmpeg (or reads a recorded .wav / raw f32),
and prints each channel's cycles per NAM call (|sample| x 2^18): median, 99th percentile, max,
as % of the 150,000-cycle block.

usage: meter_read.py [seconds | file.wav] [--device NAME] [--v2]
(The Floor's Windows capture endpoint is 1 channel: USB 1, main L, comes in duplicated.)
"""
import subprocess
import os
import sys

import numpy as np

DEVICE = os.environ.get("METER_DEVICE", "Digital Audio Interface (Line 6 Helix)")   # "ASIO": the ASIO Helix driver
RATE, BLOCK = 48000, 150000


def record(seconds, device):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "dshow", "-sample_rate", str(RATE),
           "-i", f"audio={device}", "-t", str(seconds), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return raw


def load(path):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-f", "f32le", "-"]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def record_asio(seconds):
    """USB 1/2 from the ASIO Helix driver (no Windows mixer, sample exact); 2 x N float."""
    os.environ["SD_ENABLE_ASIO"] = "1"
    import sounddevice as sd
    dev = [i for i, d in enumerate(sd.query_devices()) if d["name"] == "ASIO Helix"][0]
    x = sd.rec(int(seconds * 48000), samplerate=48000, channels=8, device=dev, dtype="float32", blocking=True)
    return x[:, :2].T


def channels(path_or_seconds, device):
    if device == "ASIO":
        return record_asio(float(path_or_seconds))
    if str(path_or_seconds).replace(".", "").isdigit():
        raw = record(float(path_or_seconds), device)
    else:
        raw = load(path_or_seconds)
    x = np.frombuffer(raw, dtype="<f4")
    nch = 2 if x.size % 2 == 0 else 1
    return x.reshape(-1, nch).T


def report(ch, name):
    c = np.abs(ch) * 2 ** 18
    c = c[c > 1000]                      # (silence or a sign change sample)
    if c.size < RATE // 10:
        print(f"{name}: no meter signal")
        return
    q = np.percentile(c, [50, 99, 100])
    print(f"{name}: cycles per call median {q[0]:,.0f} ({q[0] / BLOCK:.1%}), "
          f"99% {q[1]:,.0f} ({q[1] / BLOCK:.1%}), max {q[2]:,.0f} ({q[2] / BLOCK:.1%})")


def report_v2(ch):
    """nam_floor5m v2: 16-sample frames of four 4-sample fields (+cycles/8, -polls, +DM/16, -PM/16)."""
    n = np.round(ch * 32768).astype(np.int64)
    best = None
    for p in range(16):                  # the phase whose 4-sample groups are constant, signs + - + -
        m = (len(n) - p) // 16
        f = n[p:p + 16 * m].reshape(m, 4, 4)
        ok = (f == f[:, :, :1]).all(axis=2).mean()
        sg = (np.sign(f[:, :, 0]) == np.array([1, -1, 1, -1])).mean()
        score = ok + sg
        if best is None or score > best[0]:
            best = (score, f[:, :, 0])
    g = best[1]
    if np.var(g[:, 2]) > np.var(g[:, 0]):  # (cycles vary call to call; the addresses don't)
        g = g[:, [2, 3, 0, 1]]
    cyc, polls = g[:, 0] * 8, -g[:, 1]
    q = np.percentile(cyc, [50, 99, 100])
    print(f"frames {len(g)} (fit {best[0] / 2:.0%})")
    print(f"cycles per call: median {q[0]:,.0f} ({q[0] / BLOCK:.1%}), 99% {q[1]:,.0f}, max {q[2]:,.0f}")
    print(f"wait polls per call: median {np.median(polls):,.0f}, max {polls.max():,.0f}")
    dm = np.unique(g[:, 2] * 16 + 0x80000)
    pm = np.unique(-g[:, 3] * 16 + 0x80000)
    print("instance DM block (I0):", [hex(x) for x in dm[:4]], " PM block (I8):", [hex(x) for x in pm[:4]])


def report_v4(ch):
    """nam_floor5m v4: 16-sample frames of eight 2-sample fields, field 0 = +16384 (calibration)."""
    n = np.round(ch * 32768).astype(np.int64)
    best = None
    for p in range(16):                  # the phase whose field 0 is a steady positive pair
        m = (len(n) - p) // 16
        if m < 10:
            continue
        f = n[p:p + 16 * m].reshape(m, 8, 2)
        pair = (f[:, :, 0] == f[:, :, 1]).mean()
        c = f[:, 0, 0]
        steady = (c > 1000).mean() * (1.0 / (1.0 + np.std(c)))
        score = pair + steady
        if best is None or score > best[0]:
            best = (score, f[:, :, 0])
    if best is None:
        print("no meter signal")
        return
    g = best[1].astype(float)
    cal = np.median(g[:, 0])
    gain = cal / 16384
    print(f"frames {len(g)}; calibration field {cal:.0f} -> gain after the block x{gain:.4f} "
          f"({20 * np.log10(max(gain, 1e-9)):+.2f} dB)")
    v = np.round(g / gain).astype(np.int64)
    cyc = -v[:, 1] * 8
    q = np.percentile(cyc, [50, 99, 100])
    print(f"cycles per call (gain-corrected): median {q[0]:,.0f} ({q[0] / BLOCK:.1%}), 99% {q[1]:,.0f}, max {q[2]:,.0f}")
    print("I0 (DM block):", [hex(x * 16 + 0x80000) for x in np.unique(v[:, 2])[:4]],
          " I8 (PM block):", [hex(-x * 64) for x in np.unique(v[:, 3])[:4]])
    print("DM(3,I0) values seen:", np.unique(v[:, 4])[:6], " (1 = a knob write, cleared by the kernel)")
    print("DM(7,I0) top:", [hex(-x) for x in np.unique(v[:, 5])[:4]], " low:", np.unique(v[:, 6])[:4])
    for s in np.unique(-v[:, 7])[:4]:
        print(f"state {s}: P_SLOT {s >> 3}, DM guard {'ok' if s & 4 else 'FAIL'}, "
              f"PM guard {'ok' if s & 2 else 'FAIL'}, S_INIT {s & 1}")


def _profile_frames(ch):
    x = np.round(ch * 32768).astype(np.int64)
    st = [i for i in range(len(x) - 16) if x[i] == x[i + 1] == 16384 and x[i + 2] == x[i + 3] < 0]
    if len(st) < 10:
        return None
    return np.array([[x[i + 2 * k] for k in range(8)] for i in st]) * np.array([1, -1, 1, -1, 1, -1, 1, -1])


def report_profile2(ch):
    """nam_floor5q: fields 1..7 = total, entry->jobs, jobs->layers, layers->head, head->mix, mix->end, pair loops."""
    f = _profile_frames(ch)
    if f is None:
        print("no profile signal (gain after the block must be 1)")
        return
    tot = np.median(f[:, 1]) * 8
    print(f"frames {len(f)}")
    for k, name in enumerate(["total", "setup (entry->jobs)", "jobs->layers (input)", "23 layers", "head",
                              "mix + output", "pair loops (core math)"], 1):
        c = np.median(f[:, k]) * 8
        print(f"  {name:24s} median {c:8,.0f} cycles  {c / tot:6.1%} of the call  {c / BLOCK:6.1%} of the DSP")


def report_cal(ch):
    """nam_floor5c: fields 1..6 = cfg + 1 (8 d + c), loop cycles, start -> done, polls after the loop, 0, sentinel."""
    f = _profile_frames(ch)
    if f is None:
        print("no calibration signal (gain after the block must be 1)")
        return
    dn = ["none", "taps -> SB (B3)", "weights -> LB (B0)", "write-back <- OUTBUF (B0)"]
    cn = ["reg add", "PM read LB (B0)", "DM read LB (B0)", "PM read SB (B3)", "DM read SB (B3)", "no loop", "no loop", "no loop"]
    base = {}
    print(f"frames {len(f)}")
    for d in range(4):
        for c in range(8):
            g = f[f[:, 1] == 8 * d + c + 1]
            if not len(g):
                continue
            lp, dn_, po, se = (np.median(g[:, k]) for k in (2, 3, 4, 6))
            if d == 0:
                base[c] = lp
            print(f"  d{d} {dn[d]:26s} c{c} {cn[c]:16s} n {len(g):4d}  loop {lp:6.0f} (+{lp - base.get(c, lp):5.0f}, min {g[:, 2].min():5d})"
                  f"  done {dn_:6.0f}  polls {po:5.0f}  sentinel {se:.0f}")


def report_profile(ch):
    """nam_floor5p: v4 framing; fields 1..7 = -total, +lwait, -fwait, +head, -end, +pump (cycles/8), -polls.
    Frames are found by their marker (field 0 = 16384, 16384) followed by a negative pair (field 1)."""
    x = np.round(ch * 32768).astype(np.int64)
    st = [i for i in range(len(x) - 16) if x[i] == x[i + 1] == 16384 and x[i + 2] == x[i + 3] < 0]
    if len(st) < 10:
        print("no profile signal (gain after the block must be 1: use a preset with nothing after NAM)")
        return
    f = np.array([[x[i + 2 * k] for k in range(8)] for i in st]) * np.array([1, -1, 1, -1, 1, -1, 1, -1])
    tot = np.median(f[:, 1]) * 8
    print(f"frames {len(f)}")
    for k, name in ((1, "total"), (2, "lwait (layer weights)"), (3, "fwait (far taps)"), (4, "head wait"),
                    (5, "end wait"), (6, "pump (all calls)")):
        c = np.median(f[:, k]) * 8
        print(f"  {name:24s} median {c:8,.0f} cycles  {c / tot:6.1%} of the call  {c / BLOCK:6.1%} of the DSP")
    print(f"  polls                    median {np.median(f[:, 7]):8,.0f}")
    w = sum(np.median(f[:, k]) * 8 for k in (2, 3, 4, 5))
    print(f"  waits together           {w:8,.0f} cycles ({w / tot:.1%}); the rest (compute + pump outside waits) {tot - w:,.0f}")

def main():
    argv = sys.argv[1:]
    if "--profile2" in argv:
        argv.remove("--profile2")
        report_profile2(channels(argv[0] if argv else "5", "ASIO")[0])
        return
    if "--cal" in argv:
        argv.remove("--cal")
        report_cal(channels(argv[0] if argv else "5", "ASIO")[0])
        return
    if "--profile" in argv:
        argv.remove("--profile")
        report_profile(channels(argv[0] if argv else "5", DEVICE)[0])
        return
    if "--v4" in argv:
        argv.remove("--v4")
        report_v4(channels(argv[0] if argv else "5", DEVICE)[0])
        return
    if "--v2" in argv:
        argv.remove("--v2")
        report_v2(channels(argv[0] if argv else "5", DEVICE)[0])
        return
    device = DEVICE
    if "--device" in argv:
        i = argv.index("--device")
        device = argv[i + 1]
        del argv[i:i + 2]
    src = argv[0] if argv else "5"
    chs = channels(src, device)
    for k, ch in enumerate(chs):
        report(ch, "L" if k == 0 else "R")


if __name__ == "__main__":
    main()
