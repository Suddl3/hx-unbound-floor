"""The test vectors of docs/PICTURE_STORE.md against the code that writes the stores (struct + bg_store, no hardware)."""
import os
import re
import struct

import bg_store

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = open(os.path.join(HERE, "..", "docs", "PICTURE_STORE.md"), encoding="utf-8").read()
VECTORS = [re.sub(r"\s+", "", v) for v in re.findall(r"```\n([0-9a-f ]+)\n```", DOC)]
assert len(VECTORS) == 4, VECTORS

S, N = 256, 4
hdr = b"HXPC" + struct.pack("<HH", 1, 2) + bytes(8) + struct.pack("<HHI", S, N, 0x40000C) + struct.pack(f"<{N}H", 0xFFFF, 0, 1, 0xFFFF)
assert hdr.hex() == VECTORS[0], (hdr.hex(), VECTORS[0])

sec = bg_store.section([None, 0, 0, None], 2, 0x460000)
assert sec[:40].hex() == VECTORS[1], (sec[:40].hex(), VECTORS[1])
assert bg_store.BG_HDR == 2048 and bg_store.SETB_MAP == 3072 and bg_store.SETB_SLOT == 5072
assert bg_store.sectors_per_bg() == 900 and (bg_store.Y0, bg_store.ROWS) == (52, 288) and bg_store.BG_STORE == 0x460000
assert sec[24] == 0xFF and sec[25] == 0 and sec[26] == 0 and sec[27] == 0xFF       # slot[preset id] from byte 2048 + 24

nam = struct.pack("<H", 380 + 1) + bytes(6) + struct.pack("<4H", 0xFFFF, 1, 0xFFFF, 0xFFFF)
assert nam.hex() == VECTORS[2], (nam.hex(), VECTORS[2])
tab = bg_store.stored_table({"0": "neon_rain", "5": "synthwave", "129": "dusk"}, ["synthwave", "neon_rain", "dusk"])
assert tab[:16].hex() == VECTORS[3], (tab[:16].hex(), VECTORS[3])
assert bg_store.STORED_SEC == 0x45FFFE and len(tab) == 1024 and tab[8 + 129] == 2
print("picture store doc: header, background section, NAM table and scene table vectors match the code: OK")
