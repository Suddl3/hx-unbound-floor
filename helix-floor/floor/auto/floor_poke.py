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
RAM = ((0x10000000, 0x10020000), (0x10080000, 0x10092000), (0x20000000, 0x20010000), (0x28000000, 0x2A000000))
BULK_CHUNK = 496                # an editor request is 512 bytes at most (longer ones are cut): 9 bytes of map + str16 header
LIVE = os.environ.get("HX_LIVE_JSON") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "live.json")


def live():
    """The addresses of the image on the unit: build_floor2.py writes <out.hxf>.live.json (copy it to live.json here, or set
    HX_LIVE_JSON to it). Every address is checked against the RAM ranges, so a stale or hand-edited file cannot aim a write
    outside RAM. (Host-side only: the firmware's fm_peekset itself takes any address, there is no room left in the cave
    for a check there.)"""
    with open(LIVE) as f:
        out = {k: int(v, 0) if isinstance(v, str) and v.startswith("0x") else v for k, v in json.load(f).items()}
    for k, v in out.items():
        if isinstance(v, int):
            assert any(lo <= v < hi for lo, hi in RAM), f"{LIVE}: {k} = {v:#x} is not RAM"
    return out


class Poke:
    def __init__(self, ctl=None):
        self.own = ctl is None
        self.bulk = False
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

    @staticmethod
    def check(addr, n):
        """The whole write addr .. addr + n must lie in one RAM range (the pointer steps on after every byte)."""
        assert n > 0 and any(lo <= addr and addr + n <= hi for lo, hi in RAM), f"{addr:#x} + {n}: not inside one RAM range: refused"

    def at(self, addr):
        # RAM only: local SRAM, AHB SRAM, SDRAM. Never the peripherals or the system space (clocks, power, thermal:
        # the hardware must not be reconfigured or overheated by an experiment)
        assert any(lo <= addr < hi for lo, hi in RAM), f"{addr:#x} is not RAM: refused"
        for sh in (28, 14, 0):
            self._send(0xC000 | (addr >> sh) & 0x3FFF)

    def write(self, addr, data):
        self.check(addr, len(data))
        self.at(addr)
        for b in data:
            self._send(0x8000 | b)

    def call(self, addr, arg=0):
        assert 0 <= arg < 256
        self.at(addr)
        self._send(0xA000 | arg)

    def patch_atomic(self, addr, data, stub=0x29F02100):
        """Write data (a multiple of 4 bytes, up to 16, addr word aligned) in running code in one go: a stub masks the CPU's
        interrupts (PRIMASK: no task switch) for the few stores, so the paint task never sees half an instruction. Only a
        mask of the processor's interrupts for about a microsecond; no clock, power or thermal setting is touched."""
        assert addr % 4 == 0 and len(data) % 4 == 0 and 0 < len(data) <= 16
        words = struct.unpack(f"<{len(data) // 4}I", data)
        n = len(words)
        code = [0xB672, 0x4800 | 0]                      # cpsid i; ldr r0, [pc, #imm] (filled below)
        body = []
        for i in range(n):
            body += [0x4900, 0x6001 | (i << 6) & 0x07C0]  # ldr r1, [pc, #imm]; str r1, [r0, #4 i]
        tail = [0xB662, 0x4770]                          # cpsie i; bx lr
        total = 2 + len(body) + len(tail)
        pool = (total * 2 + 3) & ~3                      # the literals start here (word aligned)
        ins = [code[0], 0x4800 | ((pool - ((2 * 1 + 4) & ~3)) // 4)]
        pc = 2
        for i in range(n):
            off = pool + 4 * (i + 1) - (((2 * (pc)) + 4) & ~3)
            ins += [0x4900 | (off // 4), 0x6001 | (i << 6)]
            pc += 2
        ins += tail
        blob = struct.pack(f"<{len(ins)}H", *ins)
        blob += bytes(pool - len(blob)) + struct.pack(f"<{n + 1}I", addr, *words)
        self.write_bulk(stub, blob) if self.bulk else self.write(stub, blob)
        self.call(stub)

    def enable_bulk(self, base=BULK_AT):
        """Upload m4/live_bulk.bin (byte by byte, ~3 s) and make it command 0x50's params check, so write_bulk works.
        Gone at the next restart."""
        code = bytearray(BULK_BIN)
        struct.pack_into("<I", code, BULK_PTR, live()["fm_ptr"])
        self.write(base, code)
        self.call(base + BULK_SET)
        self.bulk = True

    def write_bulk(self, addr, data, chunk=BULK_CHUNK):
        """Write data at addr, chunk bytes a request (enable_bulk first)."""
        assert 32 <= chunk <= BULK_CHUNK, chunk     # under 32 msgpack makes a fixstr (not copied); a request is 512 B at most
        self.check(addr, len(data))
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
