"""Freeze probe: play a tone into Floor USB 3/4, record USB out 1/2, measure level.
Floor answers a preset change -> alive. 06D FREEZE PROBE (USB 3/4 in) = PC 23; 06C NAM test = PC 22.
usage: probe.py level [pc]      -> tone level heard (dBFS) on the current or given preset
       probe.py check            -> PC 23, level (expect tone), PC 22 back; prints ALIVE/FROZEN"""
import os, sys, time
os.environ['SD_ENABLE_ASIO'] = '1'
import numpy as np, sounddevice as sd
import midi

FS = 44100


def dev():
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == "ASIO Helix":
            return i
    raise RuntimeError("no ASIO Helix")


def level(secs=1.5, freq=1000.0):
    t = np.arange(int(FS * secs)) / FS
    out = np.zeros((len(t), 8), np.float32)
    out[:, 2] = out[:, 3] = 0.25 * np.sin(2 * np.pi * freq * t)       # USB 3/4
    with sd.Stream(device=dev(), channels=8, samplerate=FS, dtype="float32") as st:   # ASIO full duplex
        got = np.zeros_like(out); pos = 0; blk = 512
        while pos < len(t):
            n = min(blk, len(t) - pos)
            st.write(np.ascontiguousarray(out[pos:pos + n]))
            got[pos:pos + n], _ = st.read(n)
            pos += n
    x = got[len(t) // 2:, :2]                                          # USB out 1/2, steady part
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def check(m, settle=3.0, home=22):
    m.pc(23); time.sleep(settle); on = level()
    m.pc(home); time.sleep(settle); off = level()
    alive = on > -40 and on - off > 15
    return alive, on, off


if __name__ == "__main__":
    m = midi.Midi()
    try:
        if sys.argv[1] == "level":
            if len(sys.argv) > 2: m.pc(int(sys.argv[2])); time.sleep(3)
            print(f"{level():.1f} dBFS")
        else:
            a, on, off = check(m)
            print(("ALIVE" if a else "FROZEN"), f"probe {on:.1f} dBFS, 06C {off:.1f} dBFS")
    finally:
        m.close()
