"""Focus View's pictures stored in the eMMC (past every partition), drawn by the reader built into the firmware (NAM_EMMC_ART=1, m4/focus_emmc.s).

  floor_emmc_art.py write [SIZE] [--scenes DIR --assign FILE [--theme FILE]]
                                   once: HX Edit's model pictures (art_map.py, the user's own install) at SIZE x SIZE
                                   (default 128) written to the eMMC from sector 0x400000, then read back to check. With
                                   --scenes (a folder of <name>.png, 800 x 480) and --assign (bg_store.py's JSON) every
                                   picture is stored on the background of its model, and the backgrounds go to sector
                                   0x460000 (bg_store.py: the layout)
  floor_emmc_art.py write [SIZE] --scenes DIR --assign FILE --cutout
                                   the gear stored alone, bit 15 set on its see-through pixels (hard edge): one picture for every
                                   background, which the per-preset scenes need
  floor_emmc_art.py stored --assign FILE [--theme FILE] | --clear
                                   the per-preset scene table (the assignment's "stored" map: "<setlist * 128 + preset>": scene)
                                   to sector 0x45fffe; a power cycle applies it (2 sectors, past the partitions)
  floor_emmc_art.py bg-live        dev mode (RAM only): run the module with backgrounds from free SDRAM (a restart undoes it)
  floor_emmc_art.py bg-mode 0|1 [installed]   switch the store between scene per category (0) and the theme pack (1)
  floor_emmc_art.py bg-test SCENES ASSIGN   dev mode: add the background section to the EXISTING store header, backgrounds
                                   to 0x460000 (eMMC past the partitions); bg-off removes the section
  floor_emmc_art.py erase          zeroes the store's header sectors (the pictures stay but are never read)

  floor_emmc_art.py write [SIZE] --input store.json     the editor's file (store_input.py; HX Edit Unbound's "Floor look" page):
  floor_emmc_art.py icons [SIZE] --input store.json     picture size, models folder, scenes and assignment, each NAM capture
                                                        slot's picture and icon, the NAM block's preset id. What the file leaves
                                                        out is done as without it; --scenes / --assign / --theme / SIZE on the
                                                        command line win over the file.

Store at 0x400000: sector 0 = "HXPC" + 12 bytes, then the header emmc_art.s reads ({u16 S, u16 preset ids, u32 first
picture sector, u16 map[preset id]}); pictures from 0x400000 + HDR_SECTORS, each on its own sectors. The card has
0x760000 sectors; the last partition ends at 0x3b7607; everything sampled past it read as zeros before the first write.
"""
import json
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
import store_input  # noqa: E402

STORE_INPUT = None              # the editor's file, loaded by main (--input), else None

STORE = 0x400000
HDR_SECTORS = 12                # header sectors (m4/focus_emmc.s HDR_SECS, bg_store.HDR_SECTORS): pictures start after them
MAGIC = b"HXPC"


def build(size, scenes=None, assign=None, theme=None, cutout=False):
    """(header, pictures, sectors a picture, backgrounds). assign = set A (scene per category, the default); theme = an optional
    set B (a theme pack) in the same assignment format: its own composited pictures, map and slots; the header's mode word
    (0 = A) picks the set (bg-mode switches it without rewriting anything else). cutout: the gear is stored alone, with bit 15
    set on its see-through pixels (bg_store.cutout), so one picture serves every background and the per-preset scenes."""
    import art_map
    from stage_art import rgb555
    m = art_map.build()
    n = len(m["symbols"])
    base = [m["ids"].get(pid, 0xFFFF) for pid in range(n)]
    pics, bgs, slots_a, map_b, slots_b = [], [], [None] * n, None, None
    if scenes:
        import bg_store
        assert n <= bg_store.MAX_IDS, f"{n} preset ids: the header holds {bg_store.MAX_IDS}"
        cats, syms = bg_store.categories()
        names = list(assign["scenes"]) + [x for x in (theme or {}).get("scenes", []) if x not in assign["scenes"]]
        scn = [bg_store.scene_rgb(os.path.join(scenes, nm + ".png")) for nm in names]
        bgs = [bg_store.background_bytes(sc) for sc in scn]

        def compose(asg):
            _, slots = bg_store.resolve(dict(asg, scenes=names), n, cats, syms)
            mp, done = [0xFFFF] * n, {}
            for pid in range(n):                          # one stored picture per (picture, background)
                if base[pid] == 0xFFFF:
                    continue
                key = (base[pid], None if cutout else slots[pid])
                if key not in done:
                    img = art_map.open_picture(m["pictures"][base[pid]])
                    done[key] = len(pics)
                    pics.append(bg_store.cutout(img, size) if cutout else
                                rgb555(img, size) if slots[pid] is None else bg_store.composite(scn[slots[pid]], img, size))
                mp[pid] = done[key]
            return mp, slots
        mp, slots_a = compose(assign)
        if theme:
            map_b, slots_b = compose(theme)
    else:
        mp = base
        if cutout:
            import bg_store
        pics = [bg_store.cutout(art_map.open_picture(p), size) if cutout else rgb555(art_map.open_picture(p), size)
                for p in m["pictures"]]
    spp = (size * size * 2 + 511) // 512
    nam = b""
    by_slot = nam_images("picture")                      # each NAM capture's own big picture (m4/focus_emmc.s fe_img, FNAM_*)
    if by_slot:
        from PIL import Image
        nam_pid = nam_preset_id()
        slot = slots_a[nam_pid] if scenes and nam_pid < n else None
        if cutout:
            import bg_store
        at = {}
        for ident in sorted(set(by_slot.values())):
            img = Image.open(ident)
            at[ident] = len(pics)
            pics.append(bg_store.cutout(img, size) if cutout else
                        rgb555(img, size) if slot is None else bg_store.composite(scn[slot], img, size))
        tab = [0xFFFF] * 128
        for sl, ident in by_slot.items():
            tab[sl - 1] = at[ident]
        nam = struct.pack("<H", nam_pid + 1) + bytes(6) + struct.pack("<128H", *tab)    # at 1784 (u16 pid + 1) and 1792 (table)
        print(f"{len(at)} NAM capture pictures for {len(by_slot)} capture slots")
    hdr = MAGIC + struct.pack("<HH", 1, len(pics)) + bytes(8)
    hdr += struct.pack("<HHI", size, n, STORE + HDR_SECTORS) + struct.pack(f"<{n}H", *mp)
    if nam:
        assert len(hdr) <= 1784
        hdr += bytes(1784 - len(hdr)) + nam
    assert len(hdr) <= (bg_store.BG_HDR if bgs else HDR_SECTORS * 512)
    if bgs:
        hdr += bytes(bg_store.BG_HDR - len(hdr)) + bg_store.section(slots_a, len(bgs), bg_store.BG_STORE, 0, map_b, slots_b)
    assert len(hdr) <= HDR_SECTORS * 512
    hdr += bytes(HDR_SECTORS * 512 - len(hdr))
    pics = [px + bytes(spp * 512 - len(px)) for px in pics]
    return hdr, pics, spp, bgs


def write(size, scenes=None, assign=None, theme=None, cutout=False):
    hdr, pics, spp, bgs = build(size, scenes, assign, theme, cutout)
    data = b"".join(pics)
    total = len(data) // 512
    print(f"{len(pics)} pictures {size}x{size}: {total} sectors ({len(data) / 1e6:.1f} MB) from {STORE + HDR_SECTORS:#x}"
          + (f"; {len(bgs)} backgrounds" if bgs else ""))
    if STORE + HDR_SECTORS + total > ICON_STORE:
        raise SystemExit(f"the picture store would reach the icon store at {ICON_STORE:#x}: use a smaller SIZE")
    bg_data = b"".join(bgs)
    if bgs:
        import bg_store
        end = bg_store.BG_STORE + len(bg_data) // 512
        if end > 0x760000 or bg_store.BG_STORE < ICON_STORE + ICON_MAX_SECTORS + ICON_HDR:
            raise SystemExit(f"the backgrounds at {bg_store.BG_STORE:#x}..{end:#x} do not fit between the icon store and the card")
    t = time.time()
    with floor_poke.Poke() as p:
        p.enable_bulk()
        probe = floor_emmc.read(p, STORE, 1) + floor_emmc.read(p, STORE + HDR_SECTORS + total, 8)      # a store of ours, or blank
        if any(probe) and probe[:4] != MAGIC:
            raise SystemExit("the picture store's sectors are not blank and hold no picture store: refusing to write over them")
        step = floor_emmc.MAX // spp * spp * 512
        for off in range(0, len(data), step):
            floor_emmc.write(p, STORE + HDR_SECTORS + off // 512, data[off:off + step])
            print(f"  {off + min(step, len(data) - off):>10} / {len(data)} bytes", flush=True)
        if bgs:
            bstep = floor_emmc.MAX // bg_store.sectors_per_bg() * bg_store.sectors_per_bg() * 512 or bg_store.sectors_per_bg() * 512
            for off in range(0, len(bg_data), bstep):
                floor_emmc.write(p, bg_store.BG_STORE + off // 512, bg_data[off:off + bstep])
                print(f"  backgrounds {off + min(bstep, len(bg_data) - off):>10} / {len(bg_data)} bytes", flush=True)
            sp = bg_store.sectors_per_bg()
            for k in (0, len(bgs) - 1):
                assert floor_emmc.read(p, bg_store.BG_STORE + k * sp, sp) == bgs[k], f"background {k} read back differs"
        floor_emmc.write(p, STORE, hdr)                  # the header last: a store without one is never read
        back = floor_emmc.read(p, STORE, HDR_SECTORS)
        assert back == hdr, "header read back differs"
        for k in (0, len(pics) // 2, len(pics) - 1):
            got = floor_emmc.read(p, STORE + HDR_SECTORS + k * spp, spp)
            assert got == pics[k], f"picture {k} read back differs"
    print(f"written and checked in {time.time() - t:.0f} s")


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
    bm, cols, index = bytearray(128), [0] * 1024, {}
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
        index[name] = i
    for name, i in index.items():                    # a bypassed frame has its category's colour (its own icon is washed out)
        if name.endswith("Off") and index.get(name[:-3]) is not None and cols[index[name[:-3]]]:
            cols[i] = cols[index[name[:-3]]]
    return bytes(bm), cols


ICON_HDR = 10                   # header sectors of the icon store (m4/focus_emmc.s HDR_SEC)
NAM_PID = 380                   # the NAM A2 Lite block's preset id on this firmware
NAM_ICONS = os.environ.get("NAM_CAPTURE_ICONS", "")   # a clone of Suddl3/hx-edit-unbound (formerly hx-edit-nam)


# HX_ART_DIR: HX Edit Unbound's own 3D gear instead of HX Edit's pictures: auto/hxart_from_pack.py makes the folder from the release's helix-gear-art.zip.
# NAM_ICON_PIX: a folder of the pictures themselves instead of nam_capture_icons/ (e.g. the 256/ folder of Suddl3's nam-gear-art.zip,
# release gear-art-2026-11-22, the pictures without the floor shadow; same ids as the file names there). The picking rules still come from NAM_CAPTURE_ICONS.


def editor_code(folder):
    """Where capture_icons.py and nam_capture_icons/ are in a clone of HX Edit Unbound: src/ since 2026-11-16 (the root
    before), so a clone's root or its src/ both work."""
    src = os.path.join(folder, "src")
    return src if os.path.isfile(os.path.join(src, "capture_icons.py")) else folder


def nam_slot_icons():
    """{capture slot 1..128: icon id}: each capture's icon as HX Edit NAM picks it (capture_icons.pick on the capture's name;
    the slot names are the ones HX Edit remembered from the Floor), and the folder of those pictures."""
    import json
    if not NAM_ICONS:
        raise SystemExit("set NAM_CAPTURE_ICONS to your clone of Suddl3/hx-edit-unbound")
    code = editor_code(NAM_ICONS)
    sys.path.insert(0, code)
    import capture_icons
    mem = os.path.join(os.environ["LOCALAPPDATA"], "HX Edit NAM", "NAM Library", "floor-memory.json")
    slots = json.load(open(mem, encoding="utf-8")).get("slots", {})
    return {int(k): capture_icons.pick(v.get("name", "")) for k, v in slots.items() if 1 <= int(k) <= 128},         os.environ.get("NAM_ICON_PIX") or os.path.join(code, "nam_capture_icons")


def nam_preset_id():
    """The NAM block's preset id: the editor's file (the first of nam.preset_ids), else NAM_PID."""
    return (STORE_INPUT or {}).get("nam_pid") or NAM_PID


def nam_images(kind, always=False):
    """{capture slot: png path} of each NAM capture's `kind` ("picture": the big Focus View one, "icon": the chain-view one).
    With the editor's file, what it lists. Without it: the pictures only when NAM_ICON_PIX and NAM_CAPTURE_ICONS are set
    (as before), the icons (always=True) from the editor code's capture_icons, as before."""
    if STORE_INPUT is not None:
        return {s: e[kind] for s, e in STORE_INPUT["nam"].items() if e.get(kind)}
    if not always and not (os.environ.get("NAM_ICON_PIX") and NAM_ICONS):
        return {}
    by_slot, folder = nam_slot_icons()
    return {s: os.path.join(folder, ident + ".png") for s, ident in by_slot.items()}


ICON_MAX_SIZE = 44              # the frame's inside (m4/focus_emmc.s: the firmware refuses anything else)
ICON_MAX_SECTORS = 10230        # picture sectors that fit the RAM set aside, 0x29a00000 + header up to the live code at 0x29f00000


def icons_build(size=ICON_SIZE):
    if not 1 <= size <= ICON_MAX_SIZE:
        raise SystemExit(f"icon size {size}: must be 1..{ICON_MAX_SIZE} (it is drawn inside the 48 x 48 block frame)")
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
    by_slot = nam_images("icon", always=True)
    ids = sorted(set(by_slot.values()))
    nam_table = [0xFFFF] * 128
    for k, ident in enumerate(ids):
        pics.append(rgb555(Image.open(ident), size))
        for slot, i in by_slot.items():
            if i == ident:
                nam_table[slot - 1] = len(m["pictures"]) + k
    bitmap, cols = stock_blocks()
    hdr = struct.pack("<4sHHIHH", b"HXPI", size, n, first, len(pics), spp) + bitmap
    hdr += struct.pack(f"<{n}H", *mp)
    assert len(hdr) <= 1912
    hdr += bytes(1912 - len(hdr)) + struct.pack("<H", nam_preset_id()) + bytes(6) + struct.pack("<128H", *nam_table)
    hdr += bytes(2304 - len(hdr)) + struct.pack("<1024H", *cols)
    assert len(hdr) <= ICON_HDR * 512
    hdr += bytes(ICON_HDR * 512 - len(hdr))
    data = b"".join(px + bytes(spp * 512 - len(px)) for px in pics)
    if len(data) // 512 > ICON_MAX_SECTORS:
        raise SystemExit(f"{len(pics)} pictures of {spp} sectors = {len(data) // 512} sectors: the firmware loads them into "
                         f"{ICON_MAX_SECTORS} sectors of RAM at most; use a smaller size")
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
            assert len(cur) <= 16, "a patch must go in one patch_atomic (16 bytes), or a paint could see half of it"
            p.patch_atomic(a, bytes(cur))
    print("block icons live: module uploaded, focus_img -> fe_img, dm_paint -> fe_hook (a Floor restart undoes it)")


LIVE_VA = 0x29F20000            # dev mode: the focus module runs from free SDRAM (no write over the clock-stop wrappers)


def bg_live():
    """Dev mode, RAM only: run the current focus module (fe_bg included) from free SDRAM at LIVE_VA. The installed module's two
    entry points (fe_hook at +0, fe_img at +0x540, which dm_paint's call and the focus_img jump already reach) each get an
    8 byte jump to the new one; the meter, the clock-stop wrappers and the rest of the installed module are not touched.
    A Floor restart undoes it."""
    import focus_emmc
    lv = floor_poke.live()
    meter = lv["meter"]
    code = focus_emmc.with_literals(focus_emmc.load(), meter + json_sym("dm_cfg"), _focus_fill(meter))
    veneer = lambda target: bytes.fromhex("dff800f0") + struct.pack("<I", target | 1)      # ldr.w pc, [pc]; .word target
    with floor_poke.Poke() as p:
        p.enable_bulk()
        p.write_bulk(LIVE_VA, code)                              # not referenced yet: nothing can run it half written
        for entry in (focus_emmc.HOOK, focus_emmc.IMG):
            p.patch_atomic(focus_emmc.VA + entry, veneer(LIVE_VA + entry))
    print(f"focus module (with backgrounds) running from {LIVE_VA:#x}: fe_hook and fe_img of the installed module jump to it "
          f"(a restart undoes it)")


def _focus_fill(meter):
    import focus_emmc
    mcode = open(os.path.join(FLOOR, "m4", "floor_dsp_meter.bin"), "rb").read()
    return focus_emmc.patches(meter, mcode)[1]


def bg_test(scenes, assign):
    """Dev mode, eMMC past the partitions only: add a background section to the picture store's EXISTING header (the pictures
    stay as they are, so each sits on black over the scene) and write the backgrounds at sector 0x460000. bg-off removes it."""
    import bg_store
    names, _ = None, None
    with floor_poke.Poke() as p:
        p.enable_bulk()
        hdr = floor_emmc.read(p, STORE, HDR_SECTORS)
        if hdr[:4] != MAGIC:
            raise SystemExit("no picture store on the eMMC (floor_emmc_art.py write first)")
        n = struct.unpack_from("<H", hdr, 18)[0]
        size = struct.unpack_from("<H", hdr, 16)[0]
        if struct.unpack_from("<I", hdr, 20)[0] < STORE + HDR_SECTORS:
            raise SystemExit("this store's pictures start inside the 12 header sectors: rewrite it first (write)")
        print(f"existing store: {size} x {size} pictures, {n} preset ids")
        cats, syms = bg_store.categories()
        names, slots = bg_store.resolve(assign, n, cats, syms)
        bgs = [bg_store.background_bytes(bg_store.scene_rgb(os.path.join(scenes, nm + ".png"))) for nm in names]
        data = b"".join(bgs)
        probe = floor_emmc.read(p, bg_store.BG_STORE, 8)
        if any(probe) and hdr[bg_store.BG_HDR:bg_store.BG_HDR + 4] != bg_store.MAGIC:
            raise SystemExit("the background area is not blank and has no background section: refusing to write over it")
        step = floor_emmc.MAX // bg_store.sectors_per_bg() * bg_store.sectors_per_bg() * 512
        for off in range(0, len(data), step):
            floor_emmc.write(p, bg_store.BG_STORE + off // 512, data[off:off + step])
        sp = bg_store.sectors_per_bg()
        for k in range(len(bgs)):
            assert floor_emmc.read(p, bg_store.BG_STORE + k * sp, sp) == bgs[k], f"background {k} read back differs"
        sec = bg_store.section(slots, len(bgs), bg_store.BG_STORE)
        assert bg_store.BG_HDR + len(sec) <= HDR_SECTORS * 512
        new = hdr[:bg_store.BG_HDR] + bytes(HDR_SECTORS * 512 - bg_store.BG_HDR)
        new = new[:bg_store.BG_HDR] + sec + new[bg_store.BG_HDR + len(sec):]
        floor_emmc.write(p, STORE, new)                         # the header last
        assert floor_emmc.read(p, STORE, HDR_SECTORS) == new, "header read back differs"
    print(f"{len(bgs)} backgrounds written, header section added: {dict((nm, slots.count(i)) for i, nm in enumerate(names))}")


def stored_write(assign, theme=None, clear=False):
    """The per-preset scene table (bg_store.stored_table) at sector 0x45fffe, 2 sectors past the partitions and before the
    backgrounds: assign["stored"] = {"<setlist * 128 + preset>": scene name}. The firmware reads it once at the first Focus View
    paint, so a power cycle applies a change. clear: zeroes the table (the firmware then ignores it)."""
    import bg_store
    if clear:
        data = bytes(1024)
    else:
        names = list(assign["scenes"]) + [x for x in (theme or {}).get("scenes", []) if x not in assign["scenes"]]
        data = bg_store.stored_table(assign.get("stored"), names)
    with floor_poke.Poke() as p:
        p.enable_bulk()
        cur = floor_emmc.read(p, bg_store.STORED_SEC, 2)
        if any(cur) and cur[:4] != bg_store.STORED_MAGIC:
            raise SystemExit("the sectors before the backgrounds are not blank and hold no scene table: refusing to write over them")
        floor_emmc.write(p, bg_store.STORED_SEC, data)
        assert floor_emmc.read(p, bg_store.STORED_SEC, 2) == data, "scene table read back differs"
    n = struct.unpack_from("<H", data, 4)[0]
    print("scene table cleared" if clear else f"scene table written: {len([b for b in data[8:8 + n] if b != 0xFF])} presets, N = {n}")


def bg_mode(mode, installed=False):
    """Switch the picture store between set A (0: scene per category) and set B (1: the theme pack): the mode word in the
    eMMC header (one sector write; survives restarts) and, when the focus module is running, its RAM copy of the header and
    caches, so the screen follows at the next paint. Which module's caches: the dev-mode copy at LIVE_VA (bg-live, the default)
    or, with installed=True, the one built in after segment 1 (only for a build made from this source: the state words sit at
    its end, and an older build's module is shorter)."""
    import bg_store
    import focus_emmc
    with floor_poke.Poke() as p:
        p.enable_bulk()
        hdr = bytearray(floor_emmc.read(p, STORE, HDR_SECTORS))
        if hdr[bg_store.BG_HDR:bg_store.BG_HDR + 4] != bg_store.MAGIC:
            raise SystemExit("this store has no background section")
        if struct.unpack_from("<I", hdr, 20)[0] < STORE + HDR_SECTORS:
            raise SystemExit("this store's pictures start inside the 12 header sectors: rewrite it first (write)")
        struct.pack_into("<H", hdr, bg_store.BG_HDR + 16, mode)
        floor_emmc.write(p, STORE, bytes(hdr))
        assert floor_emmc.read(p, STORE, HDR_SECTORS) == bytes(hdr)
        p.write(0x29900000 + bg_store.BG_HDR + 16, struct.pack("<H", mode))     # the RAM copy (HDR in m4/focus_emmc.s)
        n = len(focus_emmc.load())
        base = focus_emmc.VA if installed else LIVE_VA         # fe_cached, fe_bgcached: the caches hold set-specific picture ids
        p.write(base + n - 8, struct.pack("<2I", 0xFFFFFFFF, 0xFFFFFFFF))
    print(f"store mode {mode} ({'theme pack' if mode else 'scene per category'})")


def bg_off():
    """Dev mode: remove the background section from the header (the backgrounds stay, never read)."""
    import bg_store
    with floor_poke.Poke() as p:
        p.enable_bulk()
        hdr = floor_emmc.read(p, STORE, HDR_SECTORS)
        if struct.unpack_from("<I", hdr, 20)[0] < STORE + HDR_SECTORS:
            raise SystemExit("this store's pictures start inside the 12 header sectors: refusing to rewrite them")
        new = hdr[:bg_store.BG_HDR] + bytes(HDR_SECTORS * 512 - bg_store.BG_HDR)
        floor_emmc.write(p, STORE, new)
        assert floor_emmc.read(p, STORE, HDR_SECTORS) == new
    print("background section removed")


def json_sym(name):
    import json
    return json.load(open(os.path.join(FLOOR, "m4", "floor_dsp_meter.json")))[name]


def erase():
    with floor_poke.Poke() as p:
        p.enable_bulk()
        floor_emmc.write(p, STORE, bytes(HDR_SECTORS * 512))
    print("store header zeroed")


def main():
    global STORE_INPUT
    a = sys.argv[1:]
    flag = lambda f: a[a.index(f) + 1] if f in a else None
    inp = flag("--input")
    if inp:                                       # the editor's file (store_input.py): write and icons only
        if not a or a[0] not in ("write", "icons", "stored"):
            sys.exit("--input goes with write, icons and stored")
        try:
            STORE_INPUT = store_input.load(inp)
        except store_input.StoreInputError as e:
            sys.exit(f"--input: {e}")
        if STORE_INPUT["models_dir"]:
            os.environ["HX_ART_DIR"] = STORE_INPUT["models_dir"]       # art_map.open_picture reads it at each picture
        a = [x for x in a if x not in ("--input", inp)]
    if a and a[0] == "write":
        rest = [x for x in a[1:] if x not in ("--scenes", "--assign", flag("--scenes"), flag("--assign"))]
        scenes, assign, theme = flag("--scenes"), flag("--assign"), flag("--theme")
        assign = json.load(open(assign)) if assign else None
        theme = json.load(open(theme)) if theme else None
        if STORE_INPUT and not (scenes or assign or theme):          # the file's scenes, assignment and theme pack
            scenes, assign, theme = STORE_INPUT["scenes_dir"], STORE_INPUT["assign"], STORE_INPUT["theme"]
        if bool(scenes) != bool(assign) or (theme and not scenes):
            sys.exit("--scenes and --assign go together; --theme (a second assignment, the theme pack) needs both")
        cutout = "--cutout" in a or bool((STORE_INPUT or {}).get("cutout"))
        rest = [x for x in rest if x not in ("--theme", flag("--theme"), "--cutout")]
        size = int(rest[0]) if rest else (STORE_INPUT or {}).get("size") or 128
        write(size, scenes, assign, theme, cutout)
    elif a and a[0] == "stored":
        if "--clear" in a:
            stored_write(None, clear=True)
        else:
            asg, thm = flag("--assign"), flag("--theme")
            asg = json.load(open(asg)) if asg else (STORE_INPUT or {}).get("assign")
            thm = json.load(open(thm)) if thm else (STORE_INPUT or {}).get("theme")
            if not asg:
                sys.exit("stored needs --assign FILE (or --input store.json): the file's \"stored\" map and its scenes' order")
            stored_write(asg, thm)
    elif a and a[0] == "icons":
        icons_write(int(a[1]) if len(a) > 1 else (STORE_INPUT or {}).get("icon_size") or ICON_SIZE)
    elif a and a[0] == "bg-live":
        bg_live()
    elif a and a[0] == "bg-test" and len(a) == 3:
        bg_test(a[1], json.load(open(a[2])))
    elif a and a[0] == "bg-mode" and len(a) in (2, 3) and a[1] in ("0", "1"):
        bg_mode(int(a[1]), installed=a[2:] == ["installed"])
    elif a and a[0] == "bg-off":
        bg_off()
    elif a and a[0] == "icons-live":
        icons_live()
    elif a and a[0] == "erase":
        erase()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
