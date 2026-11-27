#!/usr/bin/env python3
"""stage_splash on made-up entries (no firmware needed): only the boot picture's bytes change, and a used space is refused."""
import hashlib
import struct

import stage_splash as s

OFF, LEN = 64, s.W * s.H * 2
stock = bytes(range(256)) * (LEN // 256) + bytes(LEN % 256)
e8 = bytearray(32 + s.RECORD * (s.IMAGE + 1))
struct.pack_into("<I", e8, 0x14, 32)
struct.pack_into("<12I", e8, 32 + s.RECORD * s.IMAGE, 0, 0, 0, 0, 0, s.W, s.H, 0, 0, 0, 0, 0)
e9 = bytearray(OFF + LEN + 16)
struct.pack_into("<4I", e9, 0, 0, 0, 1, OFF + LEN + 8)
struct.pack_into("<2I", e9, OFF + LEN + 8, LEN, OFF)
e9[OFF:OFF + LEN] = stock
e8, e9 = bytes(e8), bytes(e9)
s.STOCK_MD5 = hashlib.md5(stock).hexdigest()

new = b"\x55\x2a" * (LEN // 2)
out = s.apply(e8, e9, new)
assert len(out) == len(e9)
assert out[:OFF] == e9[:OFF] and out[OFF + LEN:] == e9[OFF + LEN:] and out[OFF:OFF + LEN] == new

used = e9[:OFF] + b"\1" + e9[OFF + 1:]
try:
    s.apply(e8, used, new)
except SystemExit as err:
    assert "not stock" in str(err)
else:
    raise AssertionError("a used picture space was overwritten")
print("stage_splash: ok")
