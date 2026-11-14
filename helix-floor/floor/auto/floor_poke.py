"""Live poke: write the Helix Floor's RAM and call code there, from a build with NAM_SCREEN_MIRROR=1 whose mirror has the
poke (m4/floor_mirror.s fm_peekset, command 0x50 with bit 15 set). Nothing is stored: a restart brings back the installed
firmware. A bad write can freeze the unit until a power cycle. HX Edit must be closed.

  floor_poke.py write ADDR HEX            write the bytes HEX at ADDR
  floor_poke.py load ADDR FILE            write a file's bytes at ADDR
  floor_poke.py call ADDR [ARG]           call the Thumb code at ADDR with r0 = ARG (0..255), in the editor's task
  floor_poke.py hword ADDR V [V ...]      write 16-bit values at ADDR

One request carries one byte (about 6 ms each on the unit), the pointer takes three. Free RAM for uploaded code: SDRAM
0x29900000..0x2a000000 still holds the boot's memory test pattern (0xaaaaaaaa / 0x55555555) after start-up.
live.json beside this tool holds the addresses of the build on the unit ({"meter": the DSP meter module's base, ...}).
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl  # noqa: E402

CMD_PEEK = 0x50
LIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live.json")


def live():
    with open(LIVE) as f:
        return {k: int(v, 0) if isinstance(v, str) and v.startswith("0x") else v for k, v in json.load(f).items()}


class Poke:
    def __init__(self, ctl=None):
        self.own = ctl is None
        self.ctl = ctl or hx_ctl.HxCtl(pid=0x4248, timeout=10.0)

    def close(self):
        if self.own:
            self.ctl.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _send(self, seq):
        ed = self.ctl.ed
        keep = ed.seq
        ed.seq = (seq - 1) & 0xFFFF
        try:
            ed.request(CMD_PEEK, timeout=5)
        finally:
            ed.seq = keep

    def at(self, addr):
        for sh in (28, 14, 0):
            self._send(0xC000 | (addr >> sh) & 0x3FFF)

    def write(self, addr, data):
        self.at(addr)
        for b in data:
            self._send(0x8000 | b)

    def call(self, addr, arg=0):
        assert 0 <= arg < 256
        self.at(addr)
        self._send(0xA000 | arg)


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd, addr = a[0], int(a[1], 0)
    with Poke() as p:
        if cmd == "write":
            p.write(addr, bytes.fromhex(a[2]))
        elif cmd == "load":
            p.write(addr, open(a[2], "rb").read())
        elif cmd == "hword":
            p.write(addr, b"".join(struct.pack("<H", int(v, 0) & 0xFFFF) for v in a[2:]))
        elif cmd == "call":
            p.call(addr, int(a[2], 0) if len(a) > 2 else 0)
        else:
            sys.exit(__doc__)


if __name__ == "__main__":
    main()
