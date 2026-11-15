"""Read the Helix Floor's eMMC live (read only), through the poke: a small stub calls the firmware's own sector read
(0x1000504c(buffer, sector, count): bounds-checked against the card, under the card's mutex) into free SDRAM, then
the peek reads it back. Nothing is written to the eMMC.

  floor_emmc.py read SECTOR COUNT FILE     COUNT sectors (512 B; up to 1280 a call) from SECTOR into FILE
  floor_emmc.py scan SECTOR [SECTOR ...]   for each, 64 sectors: blank (all 0x00 / all 0xff) or not
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_peek  # noqa: E402
import floor_poke  # noqa: E402

READ = 0x1000504D               # (buffer, sector, count) -> 0 or < 0
STUB = 0x29F02000
BUF = 0x29F40000                # a peek window (128 KB aligned) in free SDRAM
RESULT = STUB + 0x40
MAX = 1280                      # one peek window's useful part (655,360 bytes)


def stub(sector, count):
    """push {r4, lr}; ldr r0-r3 (buffer, sector, count, READ); blx r3; ldr r1, =RESULT; str r0, [r1]; pop {r4, pc}"""
    code = struct.pack("<12H", 0xB510, 0x4805, 0x4905, 0x4A06, 0x4B06, 0x4798, 0x4906, 0x6008, 0xBD10, 0xBF00, 0xBF00, 0)
    return code + struct.pack("<5I", BUF, sector, count, READ, RESULT)


WRITE = 0x10005195              # (buffer, sector, count) -> 0 or < 0
WRITE_LO = 0x400000             # writes only here and above: past every partition (the last ends at 0x3b7607)


def write(p, sector, data):
    """Write data (a whole number of sectors, up to MAX) at sector: only at WRITE_LO or above, below the card's end."""
    assert len(data) % 512 == 0 and 0 < len(data) // 512 <= MAX
    count = len(data) // 512
    assert WRITE_LO <= sector and sector + count <= 0x760000, hex(sector)
    p.write_bulk(BUF, data)
    code = bytearray(stub(sector, count))
    struct.pack_into("<I", code, 24 + 12, WRITE)
    p.write_bulk(STUB, bytes(code))
    p.call(STUB)
    pk = floor_peek.Peek(p.ctl)
    try:
        res = struct.unpack_from("<i", pk.window(0x29F00000), RESULT - 0x29F00000)[0]
    finally:
        pk.close()
    if res < 0:
        raise SystemExit(f"write {sector:#x} x {count}: error {res}")


def read(p, sector, count):
    """p: a floor_poke.Poke with the bulk write enabled."""
    assert 0 < count <= MAX
    p.write_bulk(STUB, stub(sector, count))
    p.call(STUB)
    pk = floor_peek.Peek(p.ctl)         # one USB session for both (many in a row once left the unit deaf to the PC)
    try:
        res = struct.unpack_from("<i", pk.window(0x29F00000), RESULT - 0x29F00000)[0]
        data = pk.window(BUF)[:count * 512]
    finally:
        pk.close()
    if res < 0:
        raise SystemExit(f"read {sector:#x} x {count}: error {res}")
    return data


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] not in ("read", "scan"):
        sys.exit(__doc__)
    with floor_poke.Poke() as p:
        p.enable_bulk()
        if a[0] == "read":
            data = read(p, int(a[1], 0), int(a[2], 0))
            open(a[3], "wb").write(data)
            print(f"{len(data)} bytes")
        else:
            for s in a[1:]:
                d = read(p, int(s, 0), 64)
                kind = "blank 00" if not any(d) else "blank ff" if d == b"\xff" * len(d) else "DATA"
                print(f"{int(s, 0):#9x}: {kind}  first bytes {d[:16].hex()}", flush=True)


if __name__ == "__main__":
    main()
