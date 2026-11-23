"""PC side of the per-preset scenes and the see-through gear (bg_store.stored_table, bg_store.cutout, store_input's "stored" and
"cutout"). The firmware side is in test_focus_emmc.py."""
import struct

from PIL import Image

import bg_store
import store_input

names = ["synthwave", "neon_rain", "dusk"]

# the table: "HXSB", N = highest key + 1, scene indices by setlist * 128 + preset, 0xff none, 1024 bytes
t = bg_store.stored_table({"0": "neon_rain", "129": "dusk", "5": "synthwave"}, names)
assert len(t) == 1024 and t[:4] == b"HXSB" and struct.unpack_from("<HH", t, 4) == (130, 0)
assert t[8] == 1 and t[8 + 5] == 0 and t[8 + 129] == 2 and t[8 + 1] == 0xFF and t[8 + 130:] == bytes(1024 - 138)
assert bg_store.stored_table({}, names) == b"HXSB" + bytes(1020) and bg_store.stored_table(None, names)[4:6] == b"\x00\x00"
last = bg_store.STORED_MAX - 1
assert struct.unpack_from("<H", bg_store.stored_table({str(last): "dusk"}, names), 4)[0] == bg_store.STORED_MAX
for bad in ({"x": "dusk"}, {"-1": "dusk"}, {str(bg_store.STORED_MAX): "dusk"}, {"3": "nope"}):
    try:
        bg_store.stored_table(bad, names)
    except SystemExit:
        continue
    raise AssertionError(bad)

# the see-through gear: bit 15 on pixels with alpha below 128, the other pixels keep their colour (RGB555, no background)
im = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
im.putpixel((0, 0), (9, 9, 9, 0))
im.putpixel((1, 0), (9, 9, 9, 127))
im.putpixel((2, 0), (0, 255, 0, 128))
im.putpixel((3, 0), (0, 0, 255, 255))
w = struct.unpack("<16H", bg_store.cutout(im, 4))
assert w[0] == 0x8000 and w[1] == 0x8000 and w[2] == 0x03E0 and w[3] == 0x001F and w[4] == 0x7C00, [hex(x) for x in w]
assert all(x & 0x8000 == 0 for x in w[2:]), "opaque pixels never carry bit 15"

# the editor's file: "stored" rides in the assignment, "cutout" in backgrounds
obj = {"format": store_input.FORMAT, "backgrounds": {"scenes_dir": ".", "cutout": True,
       "assign": {"scenes": names, "default": "dusk", "stored": {"129": "dusk", 7: "neon_rain"}}}}
out = store_input.normalize(obj, check_files=False)
assert out["assign"]["stored"] == {"129": "dusk", "7": "neon_rain"} and out["cutout"] is True
obj["backgrounds"].pop("cutout")
assert store_input.normalize(obj, check_files=False)["cutout"] is False
obj["backgrounds"]["cutout"] = "yes"
try:
    store_input.normalize(obj, check_files=False)
    raise AssertionError("cutout must be a bool")
except store_input.StoreInputError:
    pass
print("stored scenes: table layout and bounds, see-through gear, the editor's file: OK")
