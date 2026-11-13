"""The Helix Floor's screen on this PC, from a build with NAM_SCREEN_MIRROR=1 (floor/screen_mirror.py).
Each frame is one request on HX Edit's editor service (command 0x52), so HX Edit must be closed.

  floor_mirror.py shot screen.png [--scale 1]    one frame as a PNG
  floor_mirror.py view [--scale 1]               a live window (tkinter)
  floor_mirror.py bench [--frames 20]            frames a second, rows a frame

Reply format (m4/floor_mirror.s): u16 0xF100, u16 width, u16 height, u16 rows sent, u32 frame address, u32 LCD CTRL,
u16[30] bitmap of the rows sent, the rows (width x u16 each), u32 x 3 timings (µs). The first request, and any
after a seq gap, gets every row; later ones only the rows whose hash changed.
"""
import argparse
import os
import struct
import sys
import time
import zlib

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl  # noqa: E402

CMD = 0x52


class Mirror:
    def __init__(self, ctl=None, swap=False):
        self.ctl = ctl or hx_ctl.HxCtl(pid=0x4248, timeout=10.0)
        self.img, self.swap, self.last = None, swap, None

    def frame(self):
        """The screen as an RGB array (h, w, 3)."""
        blob = self.ctl.ed.request(CMD, timeout=15)
        if not isinstance(blob, (bytes, bytearray)):
            raise hx_ctl.HxError(f"screen: no frame in the reply (a build without NAM_SCREEN_MIRROR=1?): {blob!r}")
        blob = bytes(blob)
        fmt, w, h, n, fb, ctrl = struct.unpack_from("<4H2I", blob, 0)
        if fmt != 0xF100:
            raise hx_ctl.HxError(f"screen: unknown format {fmt:#x}")
        bits = struct.unpack_from("<30H", blob, 16)
        rows = [r for r in range(h) if bits[r // 16] >> (r % 16) & 1]
        assert len(rows) == n and len(blob) == 76 + n * w * 2 + 12, (len(rows), n, len(blob))
        if self.img is None or self.img.shape != (h, w):
            if n != h:                              # no picture yet and only part of one sent: ask for all of it
                self.ctl.ed.seq = (self.ctl.ed.seq + 1) & 0xFFFF
                return self.frame()
            self.img = np.zeros((h, w), np.uint16)
        px = np.frombuffer(blob, "<u2", n * w, 76).reshape(n, w)
        self.img[rows] = px
        self.last = dict(rows=n, fb=fb, ctrl=ctrl, us=struct.unpack_from("<3I", blob, 76 + n * w * 2), bytes=len(blob))
        return rgb(self.img, ctrl, self.swap)

    def close(self):
        self.ctl.close()


def rgb(img, ctrl, swap=False):
    """16-bit pixels -> RGB, by the LCD's CTRL: BPP (bits 1-3) 6 = 5:6:5, else 1:5:5:5; BGR (bit 8) swaps R and B."""
    p = img.astype(np.uint32)
    if (ctrl >> 1) & 7 == 6:
        lo, mid, hi = p & 31, (p >> 5) & 63, (p >> 11) & 31
        g = (mid << 2) | (mid >> 4)
    else:
        lo, mid, hi = p & 31, (p >> 5) & 31, (p >> 10) & 31
        g = (mid << 3) | (mid >> 2)
    lo, hi = (lo << 3) | (lo >> 2), (hi << 3) | (hi >> 2)
    r, b = (hi, lo) if ((ctrl >> 8) & 1) ^ swap else (lo, hi)
    return np.stack([r, g, b], -1).astype(np.uint8)


def png(a, scale=1):
    if scale > 1:
        a = a.repeat(scale, 0).repeat(scale, 1)
    h, w, _ = a.shape
    raw = b"".join(b"\0" + a[y].tobytes() for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def view(m, scale):
    import tkinter as tk
    root = tk.Tk()
    root.title("Helix Floor")
    label = tk.Label(root)
    label.pack()

    def tick():
        try:
            a = m.frame()
        except Exception as e:  # noqa: BLE001
            root.title(f"Helix Floor: {e}")
            root.after(1000, tick)
            return
        if scale > 1:
            a = a.repeat(scale, 0).repeat(scale, 1)
        h, w, _ = a.shape
        photo = tk.PhotoImage(data=b"P6 %d %d 255\n" % (w, h) + a.tobytes(), format="PPM")
        label.configure(image=photo)
        label.image = photo
        root.title(f"Helix Floor ({m.last['rows']} rows)")
        root.after(30, tick)

    root.after(0, tick)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["shot", "view", "bench"])
    ap.add_argument("out", nargs="?", default="floor_screen.png")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--frames", type=int, default=20)
    ap.add_argument("--swap", action="store_true", help="swap red and blue if the colours look wrong")
    a = ap.parse_args()
    m = Mirror(swap=a.swap)
    try:
        if a.what == "shot":
            img = m.frame()
            open(a.out, "wb").write(png(img, a.scale))
            print(f"saved {a.out}: {img.shape[1]}x{img.shape[0]}, frame {m.last['fb']:#x}, CTRL {m.last['ctrl']:#x}, "
                  f"{m.last['bytes']} bytes, hash {m.last['us'][1] / 1000:.1f} ms, send {m.last['us'][2] / 1000:.1f} ms")
        elif a.what == "view":
            view(m, a.scale)
        else:
            m.frame()
            t0, rows = time.monotonic(), 0
            for _ in range(a.frames):
                m.frame()
                rows += m.last["rows"]
            dt = time.monotonic() - t0
            print(f"{a.frames / dt:.1f} frames/s, {rows / a.frames:.0f} rows a frame (still screen: ~0)")
    finally:
        m.close()


if __name__ == "__main__":
    main()
