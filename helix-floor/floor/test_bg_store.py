"""Host-side test of bg_store.py (Focus View backgrounds): the dither is anchored at frame coordinates, so a picture
composited on a background crop is the same pixels as the background there; the header section and the assignment rules.
Needs Pillow. usage: python test_bg_store.py"""
import struct

from PIL import Image

import bg_store as bs


def gradient(seed):
    im = Image.new("RGB", (bs.W, bs.H))
    px = im.load()
    for y in range(bs.H):
        for x in range(bs.W):
            px[x, y] = ((x * 3 + seed) & 255, (y * 5 + seed * 2) & 255, ((x + y) * 2 + seed * 3) & 255)
    return im


# 1. a fully transparent gear changes nothing: the stored picture equals the background's pixels under it
scene = gradient(7).crop((0, bs.Y0, bs.W, bs.Y0 + bs.ROWS))
bg = bs.rgb555(scene, 0, bs.Y0)
assert len(bg) == bs.W * bs.ROWS * 2
size = 64
clear = Image.new("RGBA", (size, size), (255, 0, 0, 0))
pic = bs.composite(scene, clear, size)
left, top = bs.CENTRE_X - size // 2, bs.CENTRE_Y - size // 2
for y in range(size):
    want = bg[((top - bs.Y0 + y) * bs.W + left) * 2:][:size * 2]
    assert pic[y * size * 2:(y + 1) * size * 2] == want, f"row {y}: the picture's dither differs from the background's"
# an opaque gear replaces them, and what is inside the picture is the gear (not the scene)
red = Image.new("RGBA", (size, size), (255, 0, 0, 255))
pic = bs.composite(scene, red, size)
assert struct.unpack_from("<H", pic, 0)[0] >> 10 == 31 and struct.unpack_from("<H", pic, 0)[0] & 0x3FF == 0

# 2. a gear outside the area Focus View draws is refused by the geometry, not silently cut
try:
    bs.composite(scene, clear, 300)
    raise AssertionError("a 300 px picture does not fit the 288 rows")
except SystemExit:
    pass

# 3. the header section
slots = [None, 0, 1, 1]
sec = bs.section(slots, 2, bs.BG_STORE)
assert sec[:4] == b"HXBG" and struct.unpack_from("<HHIHH", sec, 4) == (2, bs.sectors_per_bg(), bs.BG_STORE, bs.Y0, bs.ROWS)
assert sec[16:] == bytes([0xFF, 0, 1, 1]) and bs.sectors_per_bg() == 900
assert len(bs.background_bytes(scene)) == 900 * 512

# 4. the assignment: a model's symbol wins over its category, the category over the default; unknown scenes are refused
a = {"scenes": ["a", "b", "c"], "default": "a", "category": {"Amp": "b"}, "preset": {"HD2_X": "c"}}
scenes, got = bs.resolve(a, 4, {1: "amp", 2: "amp", 3: "reverb"}, ["HD2_Y", "HD2_Y", "HD2_X", "HD2_Z"])
assert scenes == ["a", "b", "c"] and got == [0, 1, 2, 0], got          # id 0 no category: default; 1 Amp: b; 2 symbol: c; 3: default
_, got = bs.resolve({"scenes": ["a"], "default": None}, 2, {}, ["x", "y"])
assert got == [None, None]
try:
    bs.resolve({"scenes": ["a"], "default": "zzz"}, 1, {}, ["x"])
    raise AssertionError("an unknown scene must be refused")
except SystemExit:
    pass
print("bg_store: dither anchored at frame coordinates, header section, assignment rules: OK")
