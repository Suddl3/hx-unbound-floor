"""Focus View's pictures stored in the eMMC (past every partition), drawn by m4/emmc_art.bin.

  floor_emmc_art.py write [SIZE]   once: HX Edit's model pictures (art_map.py, the user's own install) at SIZE x SIZE
                                   (default 128) written to the eMMC from sector 0x400000, then read back to check
  floor_emmc_art.py load           after each restart (~2 s): the store's header to RAM, emmc_art.bin uploaded and
                                   Focus View switched to it (Focus View must be off)
  floor_emmc_art.py erase          zeroes the store's header sectors (the pictures stay but are never read)

Store at 0x400000: sector 0 = "HXPC" + 12 bytes, then the header emmc_art.s reads ({u16 S, u16 preset ids, u32 first
picture sector, u16 map[preset id]}); pictures from 0x400000 + HDR_SECTORS, each on its own sectors. The card has
0x760000 sectors; the last partition ends at 0x3b7607; everything sampled past it read as zeros before the first write.
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FLOOR = os.environ.get("NAM_FLOOR_DIR", os.path.dirname(HERE))
sys.path.insert(0, FLOOR)
import floor_emmc  # noqa: E402
import floor_peek  # noqa: E402
import floor_poke  # noqa: E402

STORE = 0x400000
HDR_SECTORS = 8
MAGIC = b"HXPC"
CODE = 0x29F01000
FOCUS_IMG = 1082                # focus_img's offset in the DSP meter module
CENTRE_Y = 196


def build(size):
    import art_map
    from PIL import Image
    from stage_art import rgb555
    m = art_map.build()
    n = len(m["symbols"])
    mp = [m["ids"].get(pid, 0xFFFF) for pid in range(n)]
    spp = (size * size * 2 + 511) // 512
    hdr = MAGIC + struct.pack("<HH", 1, len(m["pictures"])) + bytes(8)
    hdr += struct.pack("<HHI", size, n, STORE + HDR_SECTORS) + struct.pack(f"<{n}H", *mp)
    assert len(hdr) <= HDR_SECTORS * 512
    hdr += bytes(HDR_SECTORS * 512 - len(hdr))
    pics = []
    for p in m["pictures"]:
        px = rgb555(art_map.open_picture(p), size)
        pics.append(px + bytes(spp * 512 - len(px)))
    return hdr, pics, spp


def write(size):
    hdr, pics, spp = build(size)
    data = b"".join(pics)
    total = len(data) // 512
    print(f"{len(pics)} pictures {size}x{size}: {total} sectors ({len(data) / 1e6:.1f} MB) from {STORE + HDR_SECTORS:#x}")
    t = time.time()
    with floor_poke.Poke() as p:
        p.enable_bulk()
        step = floor_emmc.MAX // spp * spp * 512
        for off in range(0, len(data), step):
            floor_emmc.write(p, STORE + HDR_SECTORS + off // 512, data[off:off + step])
            print(f"  {off + min(step, len(data) - off):>10} / {len(data)} bytes", flush=True)
        floor_emmc.write(p, STORE, hdr)                  # the header last: a store without one is never read
        back = floor_emmc.read(p, STORE, HDR_SECTORS)
        assert back == hdr, "header read back differs"
        for k in (0, len(pics) // 2, len(pics) - 1):
            got = floor_emmc.read(p, STORE + HDR_SECTORS + k * spp, spp)
            assert got == pics[k], f"picture {k} read back differs"
    print(f"written and checked in {time.time() - t:.0f} s")


def load():
    lv = floor_poke.live()
    code = bytearray(open(os.path.join(FLOOR, "m4", "emmc_art.bin"), "rb").read())
    struct.pack_into("<I", code, len(code) - 12, lv["dm_imgs"])
    hdr_ram = struct.unpack_from("<I", code, len(code) - 8)[0]
    fi = lv["meter"] + FOCUS_IMG
    assert fi % 4 == 2
    jump = b"\x00\xbf" + b"\xdf\xf8\x00\xf0" + struct.pack("<I", CODE | 1)    # nop; ldr.w pc, [pc]; .word emmc_img
    with floor_poke.Poke() as p:
        p.enable_bulk()
        hdr = floor_emmc.read(p, STORE, HDR_SECTORS)
        if hdr[:4] != MAGIC:
            raise SystemExit("no picture store on the eMMC (floor_emmc_art.py write first)")
        size = struct.unpack_from("<H", hdr, 16)[0]
        p.write_bulk(hdr_ram, hdr[16:])
        p.write_bulk(CODE, bytes(code))
        p.write(lv["dm_imgs"] + 2, struct.pack("<4H", 400, CENTRE_Y - size // 2, size, size))
        p.write(fi, jump)
    print(f"Focus View draws {size}x{size} pictures from the eMMC store")


def erase():
    with floor_poke.Poke() as p:
        p.enable_bulk()
        floor_emmc.write(p, STORE, bytes(HDR_SECTORS * 512))
    print("store header zeroed")


def main():
    a = sys.argv[1:]
    if a and a[0] == "write":
        write(int(a[1]) if len(a) > 1 else 128)
    elif a and a[0] == "load":
        load()
    elif a and a[0] == "erase":
        erase()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
