"""Live poke: write the Helix Floor's RAM and call code there, from a build with NAM_SCREEN_MIRROR=1 whose mirror has the
poke (m4/floor_mirror.s fm_peekset, command 0x50 with bit 15 set). Nothing is stored: a restart brings back the installed
firmware. A bad write can freeze the unit until a power cycle. HX Edit must be closed.

  floor_poke.py write ADDR HEX            write the bytes HEX at ADDR
  floor_poke.py load ADDR FILE            write a file's bytes at ADDR
  floor_poke.py call ADDR [ARG]           call the Thumb code at ADDR with r0 = ARG (0..255), in the editor's task
  floor_poke.py hword ADDR V [V ...]      write 16-bit values at ADDR

One request carries one byte (a few ms each), the pointer takes three. `bulk` first uploads m4/live_bulk.bin and makes
it command 0x50's params check: then a request carries 496 bytes (~157 KB/s measured; gone at the next restart).
  floor_poke.py bulk ADDR FILE            fast write of a file at ADDR Free RAM for uploaded code: SDRAM
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
# m4/live_bulk.s assembled (test_live_bulk.py): the bulk write, made command 0x50's params check at run time
BULK_BIN = bytes.fromhex(
    "0a688b681a4412f8013bc42b0cd0d92b0ad0c52b01d0da2b12d112f8013b12f8010b40ea032301e012f8013b0b480168013b04d412"
    "f801cb01f801cbf8e70160002070470648aff2480141f0010101607047034803490160704700bf00000000c4981c28fd770f28")
BULK_SET, BULK_UNSET, BULK_PTR = 68, 82, 92
BULK_AT = 0x29f00800
BULK_CHUNK = 496                # an editor request is 512 bytes at most (longer ones are cut): 9 bytes of map + str16 header
LIVE =os.path.join(os.path.dirname(os.path.abspath(__file__)), "live.json")


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

    def enable_bulk(self, base=BULK_AT):
        """Upload m4/live_bulk.bin (byte by byte, ~3 s) and make it command 0x50's params check, so write_bulk works.
        Gone at the next restart."""
        code = bytearray(BULK_BIN)
        struct.pack_into("<I", code, BULK_PTR, live()["fm_ptr"])
        self.write(base, code)
        self.call(base + BULK_SET)

    def write_bulk(self, addr, data, chunk=BULK_CHUNK):
        """Write data at addr, chunk bytes a request (enable_bulk first)."""
        assert 32 <= chunk <= BULK_CHUNK, chunk     # under 32 msgpack makes a fixstr (not copied); a request is 512 B at most
        self.at(addr)
        ed = self.ctl.ed
        keep = ed.seq
        try:
            for i in range(0, len(data), chunk):
                part = bytes(data[i:i + chunk])
                if len(part) < 32:
                    self.write(addr + i, part)       # the short tail byte by byte
                    break
                ed.seq = 0xFFFF                      # the request's seq 0: the peek window goes back to the screen
                ed.request(CMD_PEEK, part, timeout=5)
        finally:
            ed.seq = keep


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
        elif cmd == "bulk":                          # floor_poke.py bulk ADDR FILE: enable_bulk, then write the file
            p.enable_bulk()
            p.write_bulk(addr, open(a[2], "rb").read())
        elif cmd == "hword":
            p.write(addr, b"".join(struct.pack("<H", int(v, 0) & 0xFFFF) for v in a[2:]))
        elif cmd == "call":
            p.call(addr, int(a[2], 0) if len(a) > 2 else 0)
        else:
            sys.exit(__doc__)


if __name__ == "__main__":
    main()
