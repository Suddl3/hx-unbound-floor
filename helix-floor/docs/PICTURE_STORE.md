# The Floor's picture, icon and background stores

What the Focus View firmware (`NAM_EMMC_ART=1`, `m4/focus_emmc.s`) reads from the Floor's eMMC, and what
`auto/floor_emmc_art.py` + `bg_store.py` write. Everything sits **past the last partition**, in sectors of 512 bytes. All
numbers are little-endian. Nothing here is shared with Line 6's own data: never write below `0x400000`.

This page is the reference for both sides (firmware tools and the editor). If code and page disagree, the code is right: fix
the page. The test vectors at the bottom are checked by `test_picture_store_doc.py`.

## Areas

| Area | First sector | Written by | What |
|---|---|---|---|
| Picture store | `0x400000` | `floor_emmc_art.py write SIZE [--scenes DIR --assign JSON [--theme JSON]]` | gear pictures for Focus View, composited on their backgrounds, plus the header that maps models to pictures and backgrounds to models |
| Icon store | `0x440000` | `floor_emmc_art.py icons` | 36 px (up to 44 px) pictures for the block frames in the signal-flow view, one per NAM capture slot |
| Scene table | `0x45fffe` (2 sectors) | `floor_emmc_art.py stored` | which scene each stored preset (setlist x 128 + preset) shows behind its gear |
| Background store | `0x460000` | `floor_emmc_art.py write --scenes` | the scenes: 288 rows of 800 pixels each, 900 sectors a scene |

The picture store may grow up to the icon store; `write` refuses when it would. The backgrounds must end before sector
`0x760000` (the card).

## Picture store header (12 sectors = 6144 bytes at `0x400000`)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `"HXPC"` |
| 4 | u16 | format, 1 |
| 6 | u16 | number of pictures |
| 8 | 8 | zero |
| 16 | u16 | S: the pictures' side in pixels (at most 256) |
| 18 | u16 | N: number of preset ids covered (at most 1000) |
| 20 | u32 | sector of picture 0 (`0x400000 + 12`) |
| 24 | u16 x N | `map[preset id]` = picture index, `0xffff` none |
| 1784 | u16 | the NAM block's preset id + 1 (0: this store has no per-capture pictures) |
| 1792 | u16 x 128 | `nam[capture slot - 1]` = picture index, `0xffff` none: the NAM block's own picture per capture |
| 2048 | | background section, below |
| 3072 | u16 x N | set B: `map[preset id]` (theme pack) |
| 5072 | u8 x N | set B: `slot[preset id]` |

A picture is S x S RGB555 pixels (red in bits 14-10, green 9-5, blue 4-0; **bit 15 set = see-through**: the firmware leaves the pixel as it is, which is the scene behind the gear), rows from the top, each picture
starting on a whole sector: `ceil(S * S * 2 / 512)` sectors. Picture k is at `first + k * sectors`.

The pictures are stored **already composited** on the crop of the background they are shown on (the firmware copies
pixels, no blending), so a picture used by two models with different backgrounds is stored twice. A model without an entry
(`0xffff`) shows nothing; a store without a background section is drawn on plain black, as before.

## Background section (from byte 2048 of the same header)

| Offset | Size | Field |
|---|---|---|
| 2048 | 4 | `"HXBG"` |
| 2052 | u16 | number of backgrounds (at most 250) |
| 2054 | u16 | sectors a background takes (900 for 288 rows) |
| 2056 | u32 | sector of background 0 (`0x460000`) |
| 2060 | u16 | y0: first frame row drawn (52) |
| 2062 | u16 | rows (288) |
| 2064 | u16 | mode: 0 = set A, 1 = set B (anything else counts as set A) |
| 2072 | u8 x N | `slot[preset id]` of set A = background index, `0xff` none |

A background is `rows` rows of 800 RGB555 pixels, ordered dither anchored at absolute frame coordinates (see
`bg_store.rgb555`), from row `y0` of the 800 x 480 frame. Everything the header says is range checked by the firmware
before it reads (magic, count, slot, rows, sectors); a bad header draws no background and the picture still shows.

Assignment JSON (the input of `write --assign`): `{"scenes": [names in slot order], "default": name or null, "category":
{HX Edit category: name}, "preset": {model symbol: name}}`; `preset` wins over `category`. `auto/assign_default.json` is
the default look.

## Per-preset scenes (the scene table)

Each preset can name its own scene, so a background follows the preset (and moves with it when presets are reordered). The
table is **2 sectors at `0x45fffe`**, read once into free SDRAM at the first Focus View paint (a power cycle applies a change):

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `"HXSB"` |
| 4 | u16 | N, the number of entries (at most 1016) |
| 6 | u16 | spare, 0 |
| 8 | u8 x N | `scene[stored preset]` = background index (a slot of the background section), `0xff` none |

The index is the 32-bit word at `0x281ee64c`, **setlist x 128 + preset** (both 0-based; setlist 1, preset 1 is 129). An entry
that is `0xff`, an index past N, a wrong magic, a failed read, or a scene index past the background count: that preset uses its
model's own scene as before. A store without a background section draws no background at all. The editor's assignment JSON
carries it as `"stored": {"<setlist x 128 + preset>": "<scene name>"}` beside `category` and `preset`; precedence: `stored`,
then `preset` (the model), then `category`, then `default`.

### See-through gear

A scene that differs from the model's own would show a box around a gear picture that was stored composited on its model's
scene. `floor_emmc_art.py write ... --cutout` (or `backgrounds.cutout: true` in the editor's file) stores each gear picture
alone, with bit 15 set on every pixel whose alpha is below 128; the firmware skips those pixels. Edges are hard (no
anti-aliasing against the scene). A store written without `--cutout` is drawn exactly as before.

## Icon store header (10 sectors at `0x440000`)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `"HXPI"` |
| 4 | u16 | S, the icons' side (at most 44) |
| 6 | u16 | N, preset ids |
| 8 | u32 | sector of picture 0 (`0x440000 + 10`) |
| 12 | u16 | number of pictures |
| 14 | u16 | sectors a picture |
| 16 | 128 | bitmap by stock frame image index: 1 = a bypassed ("Off") frame |
| 144 | u16 x N | `map[preset id]` = picture index, `0xffff` none |
| 1912 | u16 | the NAM block's preset id |
| 1920 | u16 x 128 | `nam[capture slot - 1]` = picture index |
| 2304 | u16 x 1024 | category colour (RGB555) by stock frame image index, 0 none |

## What the firmware does with it

- `fe_img` (Focus View): the selected block's preset id gives the picture, via `map` (set A, or set B when the mode word is
  1). For the NAM block (preset id at 1784, minus 1) it asks the block's knob 0 for the capture slot and takes `nam[slot-1]`
  when that is not `0xffff`. The background comes from `slot[preset id]`. The header is read once, at the first call.
- `fe_hook` (signal-flow view): each block's frame gets its picture from the icon store, dimmed 0 % on a bypassed frame,
  with a category-coloured outline.
- A store that is missing, has a wrong magic or fails a read: nothing is drawn, and nothing else changes.

## Test vectors

Header, N = 4, S = 256, 2 pictures, `map = [none, 0, 1, none]`:

```
48585043 0100 0200 0000000000000000 0001 0400 0c004000 ffff 0000 0100 ffff
```

Background section for `slot = [none, 0, 0, none]`, 2 backgrounds at `0x460000`:

```
48584247 0200 8403 00004600 3400 2001 0000 0000 00000000 ff 00 00 ff
```

(The first 40 bytes of `bg_store.section(...)`; 900 sectors = `0x0384`, y0 52 = `0x34`, rows 288 = `0x120`.)

NAM table for NAM preset id 380, capture slot 2 -> picture 1, others none:

```
7d01 000000000000 ffff 0100 ffff ffff
```

Scene table for `{"0": "neon_rain", "5": "synthwave", "129": "dusk"}` with scenes `[synthwave, neon_rain, dusk]` (first 16
bytes; N = 130, scene 1 at stored preset 0, scene 0 at 5):

```
48585342 8200 0000 01ffffffff00ffff
```

