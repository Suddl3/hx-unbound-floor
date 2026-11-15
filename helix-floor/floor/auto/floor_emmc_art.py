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



ICON_STORE = 0x440000
ICON_SIZE = 36
STOCK_L6IA = os.environ.get("NAM_STOCK_L6IA", os.path.join(FLOOR, "..", "build", "floor2_stock.l6ia"))


def stock_blocks():
    """(bypassed-frame bitmap, category colours): for the stock 48 x 48 block frame images (Block_...), by image index (< 1024).
    Bitmap: the images whose name ends in Off. Colour: the most saturated pixel of the image (the icon's line colour: the
    category colour, dimmer on the bypassed frames), RGB555; 0 for none."""
    from upstream import TOOLS
    sys.path.insert(0, TOOLS)
    import patch_amp as pa
    data, _ = pa.load_l6ia_from_any(STOCK_L6IA)
    e8, e9 = pa.get_entry_swapped(data, 8), pa.get_entry_swapped(data, 9)
    rtable, count = struct.unpack_from("<2I", e8, 0x14)
    itable = struct.unpack_from("<I", e9, 12)[0]
    bm, cols = bytearray(128), [0] * 1024
    for i in range(min(count, 1024)):
        off, ln = struct.unpack_from("<2I", e8, 0x24 + 8 * i)
        name = e8[off:off + ln].split(b"\0")[0].decode("latin1")
        rec = struct.unpack_from("<12I", e8, rtable + 48 * i)
        if not name.startswith("Block_") or (rec[5], rec[6]) != (48, 48):
            continue
        if name.endswith("Off"):
            bm[i >> 3] |= 1 << (i & 7)
        n, o = struct.unpack_from("<2I", e9, itable + 8 * rec[2])
        best = (0, 0, 0)
        for k in range(0, n, 2):
            v = struct.unpack_from("<H", e9, o + k)[0]
            r, g, b = v >> 10 & 31, v >> 5 & 31, v & 31
            sat = max(r, g, b) - min(r, g, b)
            if (sat, max(r, g, b)) > best[:2]:
                best = (sat, max(r, g, b), v)
        cols[i] = best[2] if best[0] >= 3 else 0
    return bytes(bm), cols


ICON_HDR = 10                   # header sectors of the icon store (m4/focus_emmc.s HDR_SEC)
NAM_PID = 380                   # the NAM A2 Lite block's preset id on this firmware
NAM_ICONS = os.environ.get("NAM_CAPTURE_ICONS", "")   # a clone of Suddl3/hx-edit-nam (capture_icons.py, nam_capture_icons/)


def nam_slot_icons():
    """{capture slot 1..128: icon id}: each capture's icon as HX Edit NAM picks it (capture_icons.pick on the capture's name;
    the slot names are the ones HX Edit remembered from the Floor), and the folder of those pictures."""
    import json
    if not NAM_ICONS:
        raise SystemExit("set NAM_CAPTURE_ICONS to your clone of Suddl3/hx-edit-nam")
    sys.path.insert(0, NAM_ICONS)
    import capture_icons
    mem = os.path.join(os.environ["LOCALAPPDATA"], "HX Edit NAM", "NAM Library", "floor-memory.json")
    slots = json.load(open(mem, encoding="utf-8")).get("slots", {})
    return {int(k): capture_icons.pick(v.get("name", "")) for k, v in slots.items() if 1 <= int(k) <= 128},         os.path.join(NAM_ICONS, "nam_capture_icons")


def icons_build(size=ICON_SIZE):
    import art_map
    from PIL import Image
    from stage_art import rgb555
    m = art_map.build()
    n = len(m["symbols"])
    mp = [m["ids"].get(pid, 0xFFFF) for pid in range(n)]
    spp = (size * size * 2 + 511) // 512
    first = ICON_STORE + ICON_HDR
    pics = []
    for pth in m["pictures"]:
        pics.append(rgb555(art_map.open_picture(pth), size))
    by_slot, folder = nam_slot_icons()
    ids = sorted(set(by_slot.values()))
    nam_table = [0xFFFF] * 128
    for k, ident in enumerate(ids):
        pics.append(rgb555(Image.open(os.path.join(folder, ident + ".png")), size))
        for slot, i in by_slot.items():
            if i == ident:
                nam_table[slot - 1] = len(m["pictures"]) + k
    bitmap, cols = stock_blocks()
    hdr = struct.pack("<4sHHIHH", b"HXPI", size, n, first, len(pics), spp) + bitmap
    hdr += struct.pack(f"<{n}H", *mp)
    assert len(hdr) <= 1912
    hdr += bytes(1912 - len(hdr)) + struct.pack("<H", NAM_PID) + bytes(6) + struct.pack("<128H", *nam_table)
    hdr += bytes(2304 - len(hdr)) + struct.pack("<1024H", *cols)
    assert len(hdr) <= ICON_HDR * 512
    hdr += bytes(ICON_HDR * 512 - len(hdr))
    data = b"".join(px + bytes(spp * 512 - len(px)) for px in pics)
    print(f"{len(m['pictures'])} model pictures + {len(ids)} NAM capture icons for {len(by_slot)} capture slots")
    return hdr, data, spp


def icons_write(size=ICON_SIZE):
    hdr, data, spp = icons_build(size)
    total = len(data) // 512
    print(f"icon store: {total} sectors ({len(data) / 1e6:.2f} MB) of {size} x {size} pictures at {ICON_STORE + ICON_HDR:#x}")
    with floor_poke.Poke() as p:
        p.enable_bulk()
        probe = floor_emmc.read(p, ICON_STORE, 8) + floor_emmc.read(p, ICON_STORE + total + ICON_HDR, 8)
        if any(probe) and probe[:4] != b"HXPI":
            raise SystemExit("the icon store's sectors are not blank: refusing to write over them")
        step = floor_emmc.MAX // spp * spp * 512
        for off in range(0, len(data), step):
            floor_emmc.write(p, ICON_STORE + ICON_HDR + off // 512, data[off:off + step])
        floor_emmc.write(p, ICON_STORE, hdr)
        assert floor_emmc.read(p, ICON_STORE, ICON_HDR) == hdr
        for k in (0, len(data) // (spp * 512) - 1):
            assert floor_emmc.read(p, ICON_STORE + ICON_HDR + k * spp, spp) == data[k * spp * 512:(k + 1) * spp * 512]
    print("written and checked")


def icons_live():
    """Block icons without an install: the new module over the old one at 0x1008ba38, then the meter's two patches."""
    import focus_emmc
    lv = floor_poke.live()
    meter = lv["meter"]
    mcode = open(os.path.join(FLOOR, "m4", "floor_dsp_meter.bin"), "rb").read()
    mpatch, focus_fill = focus_emmc.patches(meter, mcode)
    code = focus_emmc.with_literals(focus_emmc.load(), meter + json_sym("dm_cfg"), focus_fill)
    with floor_poke.Poke() as p:
        p.enable_bulk()
        site = focus_emmc.hook_site(mcode)                       # the module may be running: take the call out of dm_paint first
        p.patch_atomic(meter + site, mcode[site:site + 12])
        time.sleep(1.0)
        p.write_bulk(focus_emmc.VA, code)                       # (Focus View must be off: fe_img moved to +0x400)
        for off, b in sorted(mpatch.items()):
            at = meter + off
            head = (4 - at % 4) % 4                              # the 2-mod-4 jump starts with a nop, then a word-aligned ldr.w
            a = at - (at % 4)
            cur = bytearray(mcode[off - (at % 4):off - (at % 4) + ((len(b) + (at % 4) + 3) // 4) * 4])
            cur[at % 4:at % 4 + len(b)] = b
            for i in range(0, len(cur), 12):
                p.patch_atomic(a + i, bytes(cur[i:i + 12]))
    print("block icons live: module uploaded, focus_img -> fe_img, dm_paint -> fe_hook (a Floor restart undoes it)")


def json_sym(name):
    import json
    return json.load(open(os.path.join(FLOOR, "m4", "floor_dsp_meter.json")))[name]


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
    elif a and a[0] == "icons":
        icons_write(int(a[1]) if len(a) > 1 else ICON_SIZE)
    elif a and a[0] == "icons-live":
        icons_live()
    elif a and a[0] == "erase":
        erase()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
