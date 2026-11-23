"""Focus View backgrounds in the eMMC picture store: the PC side (Pillow only; no hardware, no firmware build).

Layout (m4/focus_emmc.s fe_bg reads it): the picture store's header (8 sectors at 0x400000, floor_emmc_art.py) gets a
background section at byte BG_HDR = 2048:

    +0  "HXBG"
    +4  u16 count of backgrounds (<= 250)
    +6  u16 sectors a background takes (>= ROWS * 1600 / 512, <= 1024)
    +8  u32 sector of background 0
    +12 u16 y0 (the first frame row drawn), +14 u16 rows
    +16 u16 mode: 0 = set A (the header's own picture map + the slots below), 1 = set B (a theme pack)
    +24 u8 slot[preset id] of set A: the background of that model's Focus View (0xff: none, plain black as before)
  and, for set B, absolute header offsets SETB_MAP: u16 picture map[preset id], SETB_SLOT: u8 slot[preset id]. The header is
  HDR_SECTORS (12) sectors, up to MAX_IDS (1000) preset ids. Switching sets = rewriting the mode word (floor_emmc_art.py
  bg-mode); the store holds the pictures of both sets, each composited on its own backgrounds.

A background is ROWS rows of 800 RGB555 pixels (little-endian, from the top; the rows from y0 of the 800 x 480 frame) on
whole sectors, from BG_STORE up (its own eMMC area, past the picture store at 0x400000 and the icon store at 0x440000).
Each gear picture is stored already composited on the crop of the background it is shown on (the firmware copies pixels,
no blending): the picture's slot is its model's, and a picture shared by models with different backgrounds is stored once
per background (floor_emmc_art.py maps every preset id to its own copy).

Assignment (a JSON file, what HX Edit or the owner edits):
    {"scenes": ["synthwave", "neon_rain"],           background names, in slot order; <name>.png in the scenes folder
     "default": "synthwave",                          every model without a rule below (null: none)
     "category": {"Amp": "neon_rain"},                by HX Edit's category: amp, cab, preamp, distortion, dynamics, eq,
                                                      modulation, delay, reverb, pitch (pitchsynth), filter, wah, looper...
                                                      (case-insensitive; `python bg_store.py categories` lists them)
     "preset": {"HD2_AmpEssexA30": "synthwave"},      by model symbol (Helix.sym); wins over the category
     "stored": {"0": "synthwave", "129": "neon_rain"}} by the stored preset the Floor is on: setlist * 128 + preset, both from 0,
                                                      as a decimal string; wins over everything above (see stored_table)
The scene PNGs are Suddl3/hx-edit-unbound src/focus_backgrounds/backgrounds (800 x 480; rows above FRAME_Y0 and below
FRAME_Y0 + ROWS are black there anyway).
"""
import json
import os
import struct

W, H = 800, 480
Y0, ROWS = 52, 288                  # Focus View's area: m4/floor_dsp_meter.s FOCUS_Y / FOCUS_H
CENTRE_X, CENTRE_Y = 400, 196       # where fe_img puts a picture's centre (m4/focus_emmc.s)
BG_HDR = 2048
SETB_MAP, SETB_SLOT = 3072, 5072        # set B's picture map (u16 per preset id) and slots (u8), absolute header offsets
MAX_IDS = 1000
HDR_SECTORS = 12                        # header sectors the firmware reads (m4/focus_emmc.s HDR_SECS)
HDR_BYTES = HDR_SECTORS * 512
BG_STORE = 0x460000
MAGIC = b"HXBG"
MAX_COUNT = 250
BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def sectors_per_bg(rows=ROWS):
    return (rows * W * 2 + 511) // 512


def rgb555(img, x0=0, y0=0):
    """RGB image -> little-endian RGB555 bytes, the ordered dither anchored at absolute frame coordinates (x0, y0) of its
    top left pixel, so a gear picture composited on a background crop dithers exactly like the background around it."""
    from PIL import Image, ImageChops
    img = img.convert("RGB")
    w, h = img.size
    tile = Image.new("L", (w, h))
    px = tile.load()
    for y in range(h):
        row = BAYER4[(y + y0) & 3]
        for x in range(w):
            px[x, y] = row[(x + x0) & 3] // 2           # 0..7: up to a 5-bit step (8.2) less one
    lut = [min(31, v // 8) for v in range(256)]         # v + a dither of 0..7: unbiased (white stays 31)
    r, g, b = (ImageChops.add(c, tile).point(lut).tobytes() for c in img.split())
    return b"".join(struct.pack("<H", (rr << 10) | (gg << 5) | bb) for rr, gg, bb in zip(r, g, b))


def scene_rgb(path):
    """The scene's rows Y0..Y0+ROWS as an RGB image (800 x ROWS)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.size != (W, H):
        raise SystemExit(f"{path}: {im.size[0]} x {im.size[1]}, a scene must be {W} x {H}")
    return im.crop((0, Y0, W, Y0 + ROWS))


def categories():
    """{preset id: HX Edit category (icons_category picture name, lower case)} and {preset id: symbol}."""
    import art_map
    syms = [e.get("symbol") for e in json.load(open(os.path.join(art_map.RES, "Helix.sym")))]
    cat = json.load(open(os.path.join(art_map.RES, "HX_ModelCatalog.json")))
    models = {}
    for c in cat["categories"]:
        art_map.walk(c, c.get("image"), models)
    out = {}
    for pid, sym in enumerate(syms):
        key = sym
        if sym and sym not in models:
            for sfx in ("Mono", "Stereo"):
                if sym.endswith(sfx) and sym[:-len(sfx)] in models:
                    key = sym[:-len(sfx)]
        if key in models and models[key][1]:
            out[pid] = category_name(models[key][1])
    return out, syms


ALIASES = {"pitch": "pitchsynth", "ir": "impulse response", "volume": "volumepan", "sendreturn": "sendreturn"}


def category_name(image):
    """HX Edit's category from its picture's name: icons_category/fx_hx_category_amp.png -> "amp" (sprite sheets lose their
    "_%N", the input / output pictures are "input" / "output")."""
    n = os.path.splitext(os.path.basename(image))[0].lower()
    n = n.split("_%")[0]
    for pre in ("fx_hx_category_", "icon-"):
        if n.startswith(pre):
            n = n[len(pre):]
    return n[:-len("-category")] if n.endswith("-category") else n


def resolve(assign, n, cats, syms):
    """(scene names in slot order, [slot or None] by preset id) for an assignment dict."""
    scenes = list(assign["scenes"])
    if len(scenes) > MAX_COUNT or len(set(scenes)) != len(scenes):
        raise SystemExit(f"scenes: at most {MAX_COUNT}, each once")
    by_cat = {ALIASES.get(k.lower(), k.lower()): v for k, v in assign.get("category", {}).items()}
    by_sym = assign.get("preset", {})
    for v in [assign.get("default"), *by_cat.values(), *by_sym.values()]:
        if v is not None and v not in scenes:
            raise SystemExit(f"assignment names {v!r}, which is not in scenes {scenes}")
    slots = []
    for pid in range(n):
        name = by_sym.get(syms[pid]) if pid < len(syms) else None
        if name is None:
            name = by_cat.get(cats.get(pid), assign.get("default"))
        slots.append(None if name is None else scenes.index(name))
    return scenes, slots


def section(slots, count, first_sector, mode=0, map_b=None, slots_b=None):
    """The header's background bytes from BG_HDR on (to at most HDR_BYTES): the section for set A (SPC: scene per category),
    its mode word, and set B (a theme pack) at SETB_MAP / SETB_SLOT when given. mode 0 = set A, 1 = set B."""
    assert len(slots) <= MAX_IDS
    out = MAGIC + struct.pack("<HHIHHHH", count, sectors_per_bg(), first_sector, Y0, ROWS, mode, 0) + bytes(4)
    out += bytes(0xFF if s is None else s for s in slots)
    if map_b is not None:
        assert len(map_b) == len(slots_b) == len(slots)
        out += bytes(SETB_MAP - BG_HDR - len(out)) + struct.pack(f"<{len(map_b)}H", *map_b)
        out += bytes(SETB_SLOT - BG_HDR - len(out)) + bytes(0xFF if s is None else s for s in slots_b)
    assert BG_HDR + len(out) <= HDR_BYTES
    return out


def background_bytes(scene):
    """One background's sectors (zero padded)."""
    data = rgb555(scene, 0, Y0)
    return data + bytes(sectors_per_bg() * 512 - len(data))


STORED_SEC = 0x45FFFE           # the per-preset scene table: 2 sectors just before the backgrounds (m4/focus_emmc.s fe_stored)
STORED_MAX = 1016               # entries it holds: "HXSB", u16 N, u16 spare, then u8 scene[N] (0xff: none), 1024 bytes in all
STORED_MAGIC = b"HXSB"


def stored_table(stored, names):
    """The 1024 bytes at STORED_SEC. stored = {"<setlist * 128 + preset>": scene name}; names = the scenes in slot order (the
    assignment's own, then a theme pack's extra ones, as floor_emmc_art.build orders them). N is the highest key + 1. A scene
    that is not in names, or a key that is not a number in 0..STORED_MAX - 1, is an error (never silently dropped)."""
    entries = {}
    for key, name in (stored or {}).items():
        if not str(key).isdigit() or not 0 <= int(key) < STORED_MAX:
            raise SystemExit(f"stored preset {key!r}: setlist * 128 + preset as a number in 0..{STORED_MAX - 1} is expected")
        if name not in names:
            raise SystemExit(f"stored preset {key}: scene {name!r} is not one of the scenes {list(names)}")
        entries[int(key)] = names.index(name)
    n = max(entries) + 1 if entries else 0
    body = bytes(entries.get(i, 0xFF) for i in range(n))
    out = STORED_MAGIC + struct.pack("<HH", n, 0) + body
    return out + bytes(1024 - len(out))


def cutout(gear, size):
    """The gear picture at size x size as RGB555 with bit 15 set on every see-through pixel (alpha below 128): the firmware
    leaves the background there (a hard edge) so one picture sits on any scene. Opaque pixels keep their own colour."""
    from PIL import Image
    g = gear.convert("RGBA").resize((size, size), Image.LANCZOS)
    px = g.load()
    out = bytearray()
    for y in range(size):
        for x in range(size):
            r, gg, b, a = px[x, y]
            if a < 128:
                out += struct.pack("<H", 0x8000)
            else:
                out += struct.pack("<H", (r >> 3) << 10 | (gg >> 3) << 5 | b >> 3)
    return bytes(out)


def composite(scene, gear, size):
    """The gear picture (PIL, any mode) at size x size on the scene's crop under it: RGB555 bytes of the picture, solid."""
    from PIL import Image
    g = gear.convert("RGBA").resize((size, size), Image.LANCZOS)
    left, top = CENTRE_X - size // 2, CENTRE_Y - size // 2
    if top < Y0 or top + size > Y0 + ROWS or left < 0 or left + size > W:
        raise SystemExit(f"a {size} px picture at the Focus View centre is outside the drawn area (rows {Y0}..{Y0 + ROWS})")
    crop = scene.crop((left, top - Y0, left + size, top - Y0 + size)).convert("RGBA")
    crop.alpha_composite(g)
    return rgb555(crop.convert("RGB"), left, top)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["categories"]:
        from collections import Counter
        cats, _ = categories()
        for name, n in sorted(Counter(cats.values()).items()):
            print(f"{name:20s} {n:4d} models")
    else:
        sys.exit(__doc__)
