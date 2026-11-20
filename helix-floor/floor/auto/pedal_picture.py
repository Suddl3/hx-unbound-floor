#!/usr/bin/env python3
"""The NAM Pedal block's pictures in the eMMC stores (NAM_PEDAL=1 builds; docs/PICTURE_STORE.md for the layouts).

Appends ONE big picture (Focus View) to the picture store and ONE icon (signal-flow view) to the icon store, and points the
pedal's preset id at them, instead of rewriting the stores (the full write is ~16 min): about 130 KB written in all.
The artwork is drawn here (an original stompbox, no Line 6 or HX Edit art). The big picture is composited on the stored
background the pedal's slot uses (read back from the unit, so the dither around the box matches the scene exactly).

  pedal_picture.py [--pid 768] [--dry-run] [--preview DIR]

  --preview DIR   write the two pictures as PNGs and stop (nothing is read from the unit)
  --dry-run       read the stores, say what would be written, write nothing

Safety: only sectors 0x400000..0x760000 (past every partition, the stores' own area) are touched; the new pictures go into
the area of its own stores past their live pictures (or the pedal's own previous pictures when it already has them); each header is written
last and read back. HX Edit must be closed. Power cycle afterwards: the firmware reads both headers at start-up.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

PIC_STORE, ICON_STORE = 0x400000, 0x440000
PIC_HDR, ICON_HDR = 12, 10
CARD = 0x760000
NONE = 0xFFFF


def draw(size):
    """The pedal's picture, RGBA size x size: NAM_PEDAL_ART=<png> (e.g. a gen_pedal_N.png from HX Edit Unbound's
    src/nam_capture_icons) scaled to fit, else the stompbox drawn below."""
    art = os.environ.get("NAM_PEDAL_ART")
    if not art:
        return draw_own(size)
    from PIL import Image
    im = Image.open(art).convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return out


def draw_own(size):
    """The stompbox, RGBA size x size, transparent around it (drawn at 4x and reduced)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    k = 4
    S = size * k
    u = S / 256.0

    def r(*v):
        return [round(x * u) for x in v]
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(r(62, 34, 202, 238), radius=round(14 * u), fill=(0, 0, 0, 150))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(round(7 * u))))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(r(56, 22, 200, 230), radius=round(14 * u), fill=(20, 22, 26, 255), outline=(150, 154, 160, 255),
                        width=round(2 * u))
    d.rounded_rectangle(r(62, 28, 194, 224), radius=round(10 * u), fill=(34, 37, 43, 255))
    d.rounded_rectangle(r(62, 28, 194, 74), radius=round(10 * u), fill=(46, 50, 58, 255))
    for cx in (92, 128, 164):                                  # three knobs
        x, y, rad = cx * u, 52 * u, 15 * u
        d.ellipse([x - rad - 2 * u, y - rad - 2 * u, x + rad + 2 * u, y + rad + 2 * u], fill=(12, 13, 15, 255))
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(196, 200, 206, 255))
        d.ellipse([x - rad * 0.72, y - rad * 0.72, x + rad * 0.72, y + rad * 0.72], fill=(150, 154, 160, 255))
        d.line([x, y, x + (rad * 0.1 if cx == 128 else (-rad * 0.55 if cx == 92 else rad * 0.55)), y - rad * 0.8],
               fill=(235, 90, 40, 255), width=round(2.4 * u))
    d.rounded_rectangle(r(72, 88, 184, 146), radius=round(6 * u), fill=(236, 92, 38, 255))   # label plate
    try:
        big = ImageFont.truetype("arialbd.ttf", round(26 * u))
        small = ImageFont.truetype("arialbd.ttf", round(17 * u))
    except OSError:
        big = small = ImageFont.load_default()
    for text, font, y in (("NAM", big, 94), ("PEDAL", small, 122)):
        w = d.textlength(text, font=font)
        d.text(((256 * u - w) / 2, y * u), text, font=font, fill=(20, 22, 26, 255))
    d.ellipse(r(120, 156, 136, 172), fill=(255, 70, 50, 255), outline=(250, 200, 190, 255), width=round(1.5 * u))   # LED
    x, y, rad = 128 * u, 198 * u, 19 * u                       # footswitch
    d.ellipse([x - rad - 3 * u, y - rad - 3 * u, x + rad + 3 * u, y + rad + 3 * u], fill=(12, 13, 15, 255))
    d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(184, 188, 194, 255))
    d.ellipse([x - rad * 0.62, y - rad * 0.62, x + rad * 0.62, y + rad * 0.62], fill=(226, 229, 233, 255))
    for yy in (100, 118):                                      # jacks on the sides
        d.rounded_rectangle(r(50, yy, 58, yy + 10), radius=round(2 * u), fill=(120, 124, 130, 255))
        d.rounded_rectangle(r(198, yy, 206, yy + 10), radius=round(2 * u), fill=(120, 124, 130, 255))
    return im.resize((size, size), Image.LANCZOS)


def sector_bytes(p, floor_emmc, sector, n):
    assert PIC_STORE <= sector and sector + n <= CARD, f"sector {sector:#x}+{n} is outside the stores' area"
    return floor_emmc.read(p, sector, n)


def put(p, floor_emmc, sector, data):
    assert len(data) % 512 == 0 and PIC_STORE <= sector and sector + len(data) // 512 <= CARD, "write outside the stores' area"
    step = floor_emmc.MAX * 512
    for off in range(0, len(data), step):
        floor_emmc.write(p, sector + off // 512, data[off:off + step])
    assert floor_emmc.read(p, sector, len(data) // 512) == data, f"read back differs at {sector:#x}"


def main():
    args = sys.argv[1:]
    pid = int(args[args.index("--pid") + 1]) if "--pid" in args else 768
    from PIL import Image
    big_art = None
    if "--preview" in args:
        out = args[args.index("--preview") + 1]
        os.makedirs(out, exist_ok=True)
        draw(256).save(os.path.join(out, "pedal_256.png"))
        draw(36).save(os.path.join(out, "pedal_36.png"))
        print("wrote", out)
        return
    import bg_store
    import floor_emmc
    import floor_poke
    from stage_art import rgb555 as plain555
    with floor_poke.Poke() as p:
        p.enable_bulk()
        ph = bytearray(floor_emmc.read(p, PIC_STORE, PIC_HDR))
        ih = bytearray(floor_emmc.read(p, ICON_STORE, ICON_HDR))
        assert ph[:4] == b"HXPC" and ih[:4] == b"HXPI", "no picture / icon store on this unit (write them first)"
        size, n, first = struct.unpack_from("<HHI", ph, 16)
        count = struct.unpack_from("<H", ph, 6)[0]
        assert pid < n, f"preset id {pid} is outside the store's {n} ids"
        spp = (size * size * 2 + 511) // 512
        cur = struct.unpack_from("<H", ph, 24 + 2 * pid)[0]
        isize, in_, ifirst, icount, ispp = struct.unpack_from("<HHIHH", ih, 4)
        icur = struct.unpack_from("<H", ih, 144 + 2 * pid)[0]
        assert in_ == n and ispp == (isize * isize * 2 + 511) // 512
        # the background under the picture: the stored one of this id's slot
        slot = None
        if ph[bg_store.BG_HDR:bg_store.BG_HDR + 4] == b"HXBG":
            bcount, bspp, bfirst, y0, rows, mode = struct.unpack_from("<HHIHHH", ph, bg_store.BG_HDR + 4)
            slot = ph[bg_store.BG_HDR + 24 + pid]
            slot = None if slot == 0xFF or slot >= bcount or mode != 0 else slot
        idx = cur if cur != NONE else count
        iidx = icur if icur != NONE else icount
        print(f"picture store: {count} pictures of {size} px, preset id {pid} -> "
              f"{'picture %d (replace)' % cur if cur != NONE else 'new picture %d' % idx}; background slot {slot}")
        print(f"icon store: {icount} icons of {isize} px, preset id {pid} -> "
              f"{'icon %d (replace)' % icur if icur != NONE else 'new icon %d' % iidx}")
        # --- the big picture, solid on its background
        art = draw(size)
        if slot is None:
            px = plain555(art, size)
        else:
            raw = floor_emmc.read(p, bfirst + slot * bspp, bspp)
            left, top = bg_store.CENTRE_X - size // 2, bg_store.CENTRE_Y - size // 2
            assert y0 <= top and top + size <= y0 + rows
            crop = bytearray()
            for y in range(size):
                o = ((top - y0 + y) * bg_store.W + left) * 2
                crop += raw[o:o + size * 2]
            stored = struct.unpack(f"<{size * size}H", bytes(crop))
            bgrgb = Image.new("RGB", (size, size))
            bgrgb.putdata([((v >> 10 & 31) << 3 | (v >> 12 & 7), (v >> 5 & 31) << 3 | (v >> 7 & 7), (v & 31) << 3 | (v >> 2 & 7))
                           for v in stored])
            comp = bgrgb.convert("RGBA")
            comp.alpha_composite(art)
            dith = struct.unpack(f"<{size * size}H", bg_store.rgb555(comp.convert("RGB"), left, top))
            alpha = art.getchannel("A").tobytes()
            out = [dith[i] if alpha[i] else stored[i] for i in range(size * size)]      # clear pixels keep the stored scene exactly
            px = struct.pack(f"<{size * size}H", *out)
        px += bytes(spp * 512 - len(px))
        # --- the icon: the plain picture (as the icon store's other pictures)
        ipx = plain555(draw(isize), isize)
        ipx += bytes(ispp * 512 - len(ipx))
        if "--dry-run" in args:
            print("dry run: nothing written")
            return
        psec, isec = first + idx * spp, ifirst + iidx * ispp
        # the sectors past the live pictures belong to our store (its header is ours: checked above), up to the next store;
        # they may hold leftovers of an earlier, larger store, which nothing references (the same rule as floor_emmc_art.py write)
        if cur == NONE:
            assert psec >= first + count * spp and psec + spp <= ICON_STORE, "the new picture would leave the picture store's area"
        if icur == NONE:
            assert isec >= ifirst + icount * ispp and isec + ispp <= ICON_STORE + ICON_HDR + 10230 and isec + ispp <= 0x460000,                 "the new icon would leave the icon store's area (the firmware loads at most 10230 sectors of icons)"
        put(p, floor_emmc, psec, px)
        put(p, floor_emmc, isec, ipx)
        if cur == NONE:
            struct.pack_into("<H", ph, 6, count + 1)
            struct.pack_into("<H", ph, 24 + 2 * pid, idx)
            put(p, floor_emmc, PIC_STORE, bytes(ph))                                    # headers last
        if icur == NONE:
            struct.pack_into("<H", ih, 12, icount + 1)
            struct.pack_into("<H", ih, 144 + 2 * pid, iidx)
            put(p, floor_emmc, ICON_STORE, bytes(ih))
    print("written and read back; power cycle the Floor (it reads both headers at start-up)")


if __name__ == "__main__":
    main()
