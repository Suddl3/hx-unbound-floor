"""Live MIDI-clock tempo test (no install, RAM only). HX Edit closed.
  clk_test.py ramp LO HI SECS   send MIDI clock, tempo sweeping LO..HI..LO every SECS s each way, Ctrl-C to stop
  clk_test.py steady BPM SECS   send a steady clock
  clk_test.py src3              patch the clock handler's SET_VALUE source 0xe -> 3 (what the tap path uses), live
  clk_test.py src14             put it back (0xe)
Patched words: 0x28090db0 and 0x28090e08 (movs r3,#0xe in the clock-tempo handler at 0x28090ca0)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import struct

def clock(bpm_fn, secs):
    import midi
    m = midi.Midi(); t0 = t = time.perf_counter()
    try:
        while time.perf_counter() - t0 < secs:
            m.short(0xF8)
            t += 2.5 / bpm_fn(time.perf_counter() - t0)
            while time.perf_counter() < t: time.sleep(0.0005)
    except KeyboardInterrupt:
        pass

a = sys.argv[1:]
if a[0] == "ramp":
    lo, hi, s = float(a[1]), float(a[2]), float(a[3])
    def f(t):
        x = (t % (2 * s)) / s
        x = x if x <= 1 else 2 - x
        return lo + (hi - lo) * x
    clock(f, 3600)
elif a[0] == "steady":
    clock(lambda t: float(a[1]), float(a[2]))
elif a[0] in ("src3", "src14"):
    import floor_poke
    v = 3 if a[0] == "src3" else 0xE
    with floor_poke.Poke() as p:
        for addr in (0x28090DB0, 0x28090E08):
            w = struct.unpack("<I", p.at(addr, 4))[0] if hasattr(p, "at") and False else None
        p.patch_atomic(0x28090DB0, struct.pack("<I", 0x2300F8F3 | v << 16))
        p.patch_atomic(0x28090E08, struct.pack("<I", 0x2300F8C7 | v << 16))
    print("patched, source =", v)
