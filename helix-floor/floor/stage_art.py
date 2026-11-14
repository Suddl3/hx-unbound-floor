#!/usr/bin/env python3
"""Add pictures to the Floor's image store (personal builds only: the pictures are never shipped).

Entry 8 is the store's index (names, then 48-byte image records), Entry 9 its pixels (items of (length, offset) pairs). Each
PNG of the folder becomes one 128 x 128 image: composited over black, resized, RGB555 (R << 10 | G << 5 | B), row by row from
the top as the stock images are. Nothing already in the entries moves: the new items go after Entry 9's end with a copy of its
item table, the new records after Entry 8's end with a copy of its record table, and the headers point at the copies.
The new image indexes follow the stock 723; {PNG name: index} goes to <out>.art.json.

With NAM_ART_INPLACE=<index> no record is added: the records of the stock images from that index on (a few unused ones, as
HelixDNA_01..12 at 358) are repointed at the new items, so Entry 8 keeps its size.

usage: stage_art.py <in.l6ia> <out.l6ia> <folder of PNGs> [size]
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upstream import TOOLS  # noqa: E402
sys.path.insert(0, TOOLS)
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

E8_MAGIC, E9_MAGIC = 0x5b21255e, 0x2a5f3b5e
RECORD = 48
LIKE = 374                      # a stock image whose record the new ones copy (Icon_AmpCab)


def rgb555(im, size):
    from PIL import Image
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
    bg.alpha_composite(im)
    px = bg.convert("RGB").resize((size, size), Image.LANCZOS).tobytes()
    out = bytearray()
    for i in range(0, len(px), 3):
        v = (px[i] >> 3) << 10 | (px[i + 1] >> 3) << 5 | (px[i + 2] >> 3)
        out += struct.pack("<H", v)
    return bytes(out)


def add_items(e9, items):
    magic, ver, count, table, doff, _ = struct.unpack_from("<6I", e9, 0)
    assert magic == E9_MAGIC, "Entry 9 is not the image pixels"
    recs = [struct.unpack_from("<2I", e9, table + 8 * i) for i in range(count)]
    out = bytearray(e9)
    first = len(recs)
    for data in items:
        out += b"\0" * (-len(out) % 4)
        recs.append((len(data), len(out)))
        out += data
    out += b"\0" * (-len(out) % 4)
    new_table = len(out)
    out += b"".join(struct.pack("<2I", ln, off) for ln, off in recs)
    struct.pack_into("<6I", out, 0, magic, ver, len(recs), new_table, doff, len(out))
    return bytes(out), first


def add_records(e8, records):
    assert struct.unpack_from("<I", e8, 0)[0] == E8_MAGIC, "Entry 8 is not the image index"
    table, count = struct.unpack_from("<2I", e8, 0x14)
    out = bytearray(e8) + b"\0" * (-len(e8) % 4)
    new_table = len(out)
    out += e8[table:table + RECORD * count] + b"".join(records)
    struct.pack_into("<I", out, 8, len(out))
    struct.pack_into("<2I", out, 0x14, new_table, count + len(records))
    return bytes(out), count


def main():
    src, out, folder = sys.argv[1], sys.argv[2], sys.argv[3]
    size = int(sys.argv[4]) if len(sys.argv) > 4 else 128
    from PIL import Image
    names = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
    assert names, f"no PNGs in {folder}"
    data, _ = pa.load_l6ia_from_any(src)
    e8, e9 = pa.get_entry_swapped(data, 8), pa.get_entry_swapped(data, 9)
    pixels = [rgb555(Image.open(os.path.join(folder, n)), size) for n in names]
    new9, first_item = add_items(e9, pixels)
    table, count = struct.unpack_from("<2I", e8, 0x14)
    like = bytearray(e8[table + RECORD * LIKE: table + RECORD * (LIKE + 1)])
    recs = []
    for i in range(len(names)):
        r = bytearray(like)
        item = first_item + i
        for word, value in ((2, item), (3, item), (5, size), (6, size), (9, item)):
            struct.pack_into("<I", r, 4 * word, value)
        recs.append(bytes(r))
    inplace = os.environ.get("NAM_ART_INPLACE")
    if inplace:
        first_image = int(inplace)
        assert first_image + len(recs) <= count, "more pictures than records to reuse"
        new8 = bytearray(e8)
        for i, r in enumerate(recs):
            new8[table + RECORD * (first_image + i): table + RECORD * (first_image + i + 1)] = r
        new8 = bytes(new8)
    else:
        new8, first_image = add_records(e8, recs)
    img, _, _ = l6ia.rebuild_archive(data, {8: new8, 9: new9})
    open(out, "wb").write(img)
    manifest = {n[:-4]: first_image + i for i, n in enumerate(names)}
    with open(out + ".art.json", "w") as f:
        json.dump({"size": size, "first_image": first_image, "images": manifest}, f, indent=1)
    print(f"art: {len(names)} images {size}x{size} (+{(len(new9) - len(e9)) / 1e6:.1f} MB), image indexes {first_image}.."
          f"{first_image + len(names) - 1}; wrote {out}")


if __name__ == "__main__":
    main()
