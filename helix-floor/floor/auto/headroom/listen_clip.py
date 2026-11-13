"""Play a synthetic plucked-guitar riff into USB 3/4 through an edit-buffer blob, record USB 1/2, save WAV.
usage: listen_clip.py <auto dir> <blob> <out.wav>   (edit buffer only, nothing saved)"""


def main():
    import os
    import sys
    import time
    import wave

    AUTO = sys.argv[1]
    sys.path.insert(0, AUTO)
    sys.path.insert(0, os.path.join(AUTO, "hx"))
    import probe  # noqa: E402  (must come before sounddevice: enables ASIO)
    import hx_ctl as hc  # noqa: E402
    import numpy as np  # noqa: E402
    import sounddevice as sd  # noqa: E402

    FS = 44100
    rng = np.random.default_rng(1)


    def pluck(hz, secs, amp):
        """Karplus-Strong string."""
        n = int(FS * secs)
        p = int(round(FS / hz))
        buf = rng.uniform(-1, 1, p)
        out = np.zeros(n)
        for i in range(n):
            out[i] = buf[i % p]
            buf[i % p] = 0.4985 * (buf[i % p] + buf[(i + 1) % p])
        return amp * out


    def riff():
        E2, A2, B3, E4 = 82.41, 110.0, 246.94, 329.63
        x = np.zeros(int(FS * 14))
        t = 0.0
        for _ in range(2):                       # palm-ish chugs then power chord
            for _ in range(6):
                s = int(t * FS); x[s:s + int(FS * .25)] += pluck(E2, .25, .35); t += .25
            for hz in (E2, 98.0, A2):
                s = int(t * FS); x[s:s + int(FS * .5)] += pluck(hz, .5, .3); t += .5
            t += .25
        s = int(t * FS)                          # open E chord strum, let ring
        for k, hz in enumerate((E2, 123.47, 164.81, 207.65, B3, E4)):
            d = s + int(k * .012 * FS); x[d:d + int(FS * 4)] += pluck(hz, 4, .18)
        return np.clip(x, -0.9, 0.9).astype(np.float32)


    blob = open(sys.argv[2], "rb").read()
    with hc.HxCtl(pid=0x4248) as h:
        h.select(1, setlist=0)
        time.sleep(2)
        h.set_preset_blob(blob)
        time.sleep(2)
        _, sec = hc.decode_preset(h.get_preset_blob())
        kept = [b["model_id"] for b in hc.summarize(sec)]
    print("blocks kept:", kept)

    if len(sys.argv) > 4:                        # real DI take: channel 0, first N seconds, level untouched
        import wavio
        fs_in, di = wavio.read(sys.argv[4])
        assert fs_in == FS, f"take is {fs_in} Hz, need {FS}"
        secs = float(sys.argv[5]) if len(sys.argv) > 5 else 30
        x = di[: int(FS * secs), 0].astype(np.float32)
        print("DI take %.1f s, peak %.1f dBFS" % (len(x) / FS, 20 * np.log10(np.abs(x).max() + 1e-12)))
    else:
        x = riff()
    out = np.zeros((len(x) + FS, 8), np.float32)
    out[:len(x), 2] = out[:len(x), 3] = x
    got = np.zeros_like(out)
    p = 0
    with sd.Stream(device=probe.dev(), channels=8, samplerate=FS, dtype="float32") as st:
        while p < len(out):
            n = min(512, len(out) - p)
            st.write(np.ascontiguousarray(out[p:p + n]))
            got[p:p + n], _ = st.read(n)
            p += n
    y = got[:, :2]
    peak = np.abs(y).max()
    print("out peak %.1f dBFS" % (20 * np.log10(peak + 1e-12)))
    y = y / max(peak, 1e-6) * 0.7                # normalise for listening
    pcm = (y * 32767).astype("<i2")
    with wave.open(sys.argv[3], "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(pcm.tobytes())
    print("saved", sys.argv[3])


if __name__ == "__main__":
    main()
