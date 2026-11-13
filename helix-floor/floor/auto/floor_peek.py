"""Read the Helix Floor's SDRAM from a build with NAM_SCREEN_MIRROR=1 (command 0x53, m4/floor_mirror.s fm_peekset).
The frame command then returns 480 rows of 1600 bytes from the chosen address instead of the screen: 768,000 bytes a
frame (about 2 s). The window starts at a multiple of 128 KB (the address rides in the request's seq, 15 bits << 17).
Only 0x28000000 .. 0x2a000000 is SDRAM; anything else may fault the unit, so this tool refuses it. HX Edit must be closed.

  floor_peek.py dump ADDR LEN FILE         LEN bytes from ADDR (any address) into FILE
  floor_peek.py find START END HEX         every address in START..END holding the byte pattern HEX (little-endian words:
                                           floor_peek.py find 0x28180000 0x28400000 75010000   finds the word 0x175)
  floor_peek.py words ADDR COUNT           COUNT 32-bit words from ADDR, printed
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl  # noqa: E402
import floor_mirror  # noqa: E402

CMD_PEEK = 0x53
LO, HI = 0x28000000, 0x2A000000
FRAME = 480 * 1600
STEP = 5 * (1 << 17)                    # the window's useful step: 5 x 128 KB = 655,360 of the 768,000


class Peek:
    def __init__(self):
        self.ctl = hx_ctl.HxCtl(pid=0x4248, timeout=10.0)
        self.m = floor_mirror.Mirror(self.ctl)

    def window(self, base):
        assert base % (1 << 17) == 0 and LO <= base and base + FRAME <= HI, hex(base)
        seq = base >> 17
        ed = self.ctl.ed
        keep = ed.seq
        ed.seq = (seq - 1) & 0xFFFF
        try:
            r = ed.request(CMD_PEEK, timeout=5)
        finally:
            ed.seq = keep
        if r != 0:
            raise hx_ctl.HxError(f"peek: unexpected reply {r!r} (a build without the 0x53 command?)")
        self.m.img = None
        self.m.frame()
        return self.m.img.tobytes()

    def read(self, addr, n):
        assert LO <= addr and addr + n <= HI, (hex(addr), n)
        out, a = bytearray(), addr
        while len(out) < n:
            base = a & ~((1 << 17) - 1)
            if base + FRAME > HI:
                base = HI - FRAME & ~((1 << 17) - 1)
            data = self.window(base)
            off = a - base
            take = min(n - len(out), len(data) - off)
            out += data[off: off + take]
            a += take
        return bytes(out)

    def screen(self):
        ed = self.ctl.ed
        keep = ed.seq
        ed.seq = (0 - 1) & 0xFFFF
        try:
            ed.request(CMD_PEEK, timeout=5)
        finally:
            ed.seq = keep
        self.m.img = None

    def close(self):
        try:
            self.screen()
        finally:
            self.ctl.close()


def num(s):
    return int(s, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dump"); p.add_argument("addr", type=num); p.add_argument("len", type=num); p.add_argument("file")
    p = sub.add_parser("find"); p.add_argument("start", type=num); p.add_argument("end", type=num); p.add_argument("hex")
    p = sub.add_parser("words"); p.add_argument("addr", type=num); p.add_argument("count", type=num)
    a = ap.parse_args()
    pk = Peek()
    try:
        if a.cmd == "dump":
            open(a.file, "wb").write(pk.read(a.addr, a.len))
            print(f"{a.len} bytes from {a.addr:#x} -> {a.file}")
        elif a.cmd == "words":
            d = pk.read(a.addr, 4 * a.count)
            for i in range(0, len(d), 16):
                print(f"{a.addr + i:#x}: " + " ".join(f"{w:08x}" for w in struct.unpack_from(f"<{len(d[i:i + 16]) // 4}I", d, i)))
        else:
            pat, hits, base = bytes.fromhex(a.hex), 0, a.start & ~3
            while base < a.end:
                n = min(STEP, a.end - base)
                d = pk.read(base, n)
                i = d.find(pat)
                while i >= 0:
                    print(f"{base + i:#x}")
                    hits += 1
                    i = d.find(pat, i + 1)
                base += n - len(pat) + 1 if n == STEP else n
            print(f"{hits} hits")
    finally:
        pk.close()


if __name__ == "__main__":
    main()
