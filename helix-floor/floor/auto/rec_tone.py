"""One test tone (440 Hz, 0.4 s) into an edit-buffer preset, MIDI clock stepping tempo every STEP s; record USB 1/2 and
track the tail's pitch (cents vs 440 Hz) and level.
  rec_tone.py BLOB OUT.wav [secs=26] [step_s=3] [bpm list e.g. 100,140,80,120,...]"""
import os, sys, time, threading, wave
os.environ["SD_ENABLE_ASIO"] = "1"
A = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, A); sys.path.insert(0, os.path.join(A, "hx"))
import numpy as np, sounddevice as sd
import probe, midi, hx_ctl as hc
blob, out_path = sys.argv[1:3]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 26
step = float(sys.argv[4]) if len(sys.argv) > 4 else 3
bpms = [float(v) for v in sys.argv[5].split(",")] if len(sys.argv) > 5 else [100, 140, 80, 120, 90, 150, 100, 130]
FS = 44100
TONE = float(os.environ.get('TONE_S', 0.4)); tt = np.arange(int(FS * TONE)) / FS
x = np.zeros(int(FS * secs), np.float32); s0 = int(FS * float(os.environ.get('TONE_AT', 3)))
x[s0:s0 + len(tt)] = (0.3 * np.sin(2 * np.pi * 440 * tt) * np.minimum(1, np.minimum(tt, TONE - tt) / 0.05)).astype(np.float32)
if blob != "-":
  with hc.HxCtl(pid=0x4248) as h:
    h.select(1, setlist=0); time.sleep(2)
    h.set_preset_blob(open(blob, "rb").read()); time.sleep(2)
stop = [False]; T0 = [0.0]
def bpm_at(t): return bpms[min(int(max(0, t) // step), len(bpms) - 1)]
def taps():                                   # TAP=1: tempo by MIDI CC64 taps (the tap-tempo path) instead of clock
    m = midi.Midi(); T0[0] = t = time.perf_counter()
    for k, b in enumerate(bpms):
        at = T0[0] + k * step
        while time.perf_counter() < at and not stop[0]: time.sleep(0.001)
        m.cc(64, 127); time.sleep(60 / b); m.cc(64, 127)
        if stop[0]: break
def clock():
    if os.environ.get("TAP"): return taps()
    m = midi.Midi(); t = time.perf_counter(); T0[0] = t
    STOP = float(os.environ.get('STOP_AT', 1e9)) + 2.5       # playback seconds -> clock seconds
    while not stop[0]:
        if time.perf_counter() - T0[0] > STOP: break            # clock just stops, nothing else sent
        m.short(0xF8); t += 2.5 / bpm_at(time.perf_counter() - T0[0])
        while time.perf_counter() < t and not stop[0]: time.sleep(0.0005)
th = threading.Thread(target=clock, daemon=True); th.start(); time.sleep(2.5)
out = np.zeros((len(x) + FS, 8), np.float32); out[:len(x), 0] = out[:len(x), 1] = out[:len(x), 2] = out[:len(x), 3] = x
got = np.zeros_like(out); p = 0; tstart = time.perf_counter()
with sd.Stream(device=probe.dev(), channels=8, samplerate=FS, dtype="float32") as st:
    while p < len(out):
        n = min(512, len(out) - p); st.write(np.ascontiguousarray(out[p:p + n])); got[p:p + n], _ = st.read(n); p += n
stop[0] = True
y = got[:, 0].astype(np.float64)
pk = np.abs(got[:, :2]).max(); z = got[:, :2] / max(pk, 1e-6) * 0.7
with wave.open(out_path, "wb") as o:
    o.setnchannels(2); o.setsampwidth(2); o.setframerate(FS); o.writeframes((z * 32767).astype("<i2").tobytes())
print("saved", out_path, "peak %.1f dBFS" % (20 * np.log10(pk + 1e-12)))
# clock started ~ (2.5 s) before playback began; tempo index at playback time t: bpm_at(t + 2.5)
print(" t(s)  bpm  level(dB)  tail pitch (cents vs 440)")
for k in range(0, int(secs * 2) - 2):
    a = int(FS * 0.5 * k); seg = y[a:a + int(FS * 0.5)]
    lv = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12)
    if lv < -75: continue
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 17)); fr = np.fft.rfftfreq(1 << 17, 1 / FS)
    m = (fr > 150) & (fr < 1500); f = fr[m][np.argmax(sp[m])]
    print("%5.1f %4.0f  %6.1f   %+6.0f  (%.1f Hz)" % (k * 0.5, bpm_at(k * 0.5 + 2.5), lv, 1200 * np.log2(f / 440), f))
