#!/usr/bin/env python3
"""Build stage (NAM_SPLASH=<png> in build_floor2.py): our own picture on the Helix Floor's boot screen.

usage: stage_splash.py IN.l6ia OUT.l6ia PICTURE.png      (800x350, e.g. splash/unbound_boot.png)

The app's boot view draws the image Helix_Splash (image 372: 800x350, RGB555, row by row from the top, in Entry 9). Its pixels are
overwritten in place: same size, no new item, no code change. The stock pixels are hashed first, so an image where something else
already uses that space is refused. (stage_art.py's NAM_ART_STORE=splash uses the LT and Rack splashes, images 370 and 371, not
this one.) The bootloader's own picture, shown before the app starts, is not changed.
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from upstream import TOOLS  # noqa: E402
sys.path.insert(0, TOOLS)
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

IMAGE, W, H, RECORD = 372, 800, 350, 48
STOCK_MD5 = "c5ce596343a3db02a5d52052b9042773"


def pixels(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.size != (W, H):
        raise SystemExit(f"splash: {path} is {im.size[0]}x{im.size[1]}, the Floor's boot picture is {W}x{H}")
    px = im.tobytes()
    return struct.pack(f"<{W * H}H", *((px[i] >> 3) << 10 | (px[i + 1] >> 3) << 5 | (px[i + 2] >> 3) for i in range(0, len(px), 3)))


def locate(e8, e9):
    """(offset, length) of the boot picture's pixels in Entry 9."""
    records = struct.unpack_from("<I", e8, 0x14)[0]
    rec = struct.unpack_from("<12I", e8, records + RECORD * IMAGE)
    if (rec[5], rec[6]) != (W, H):
        raise SystemExit(f"splash: image {IMAGE} is {rec[5]}x{rec[6]}, not {W}x{H}")
    table = struct.unpack_from("<I", e9, 12)[0]
    length, off = struct.unpack_from("<2I", e9, table + 8 * rec[2])
    if length != W * H * 2:
        raise SystemExit(f"splash: image {IMAGE} holds {length} bytes, not {W * H * 2}")
    return off, length


def apply(e8, e9, new):
    off, length = locate(e8, e9)
    got = hashlib.md5(e9[off:off + length]).hexdigest()
    if got != STOCK_MD5:
        raise SystemExit(f"splash: the boot picture's pixels are not stock (MD5 {got}): another step uses them; nothing written")
    assert len(new) == length
    return e9[:off] + new + e9[off + length:]


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src, out, png = sys.argv[1:]
    data, _ = pa.load_l6ia_from_any(src)
    e9 = pa.get_entry_swapped(data, 9)
    new9 = apply(pa.get_entry_swapped(data, 8), e9, pixels(png))
    assert len(new9) == len(e9), "Entry 9 changed length"
    img, _, _ = l6ia.rebuild_archive(data, {9: new9})
    open(out, "wb").write(img)
    back = pa.get_entry_swapped(pa.load_l6ia_from_any(out)[0], 9)
    assert back == new9, "Entry 9 read back differs"
    print(f"splash: {os.path.basename(png)} on the boot screen (image {IMAGE}, {W}x{H}, in place); wrote {out}")


if __name__ == "__main__":
    main()
