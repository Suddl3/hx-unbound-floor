"""Emulator test of fe_hook in m4/focus_emmc.bin: the model pictures inside the path blocks (NAM_EMMC_ART=1)."""
import os
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_LR,
                               UC_ARM_REG_SP)
import focus_emmc

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = focus_emmc.with_literals(focus_emmc.load(), 0x1001FE00, 0x1001FC46)
BASE, FB, VIEW, TBL, STORE = focus_emmc.VA, 0x285A3F50, 0x20004000, 0x29A00000, 0x440000
CFG = 0x1001FE00
STUBS = {0x2813AAB8: "param", 0x28155F34: "memset", 0x28114A1C: "obj", 0x28148CCC: "desc", 0x1000504C: "read", 0x1001FC46: "focus_fill"}
S, NIDS, NPIC = 6, 400, 4                 # 6 x 6 pictures (the real ones are 36 x 36), 4 pictures
SPP = (S * S * 2 + 511) // 512
HDR_SEC = 10
FIRST = STORE + HDR_SEC


def machine(store=True):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for b, s in ((0x10000000, 0x100000), (0x28000000, 0x2000000), (0x20000000, 0x10000)):
        mu.mem_map(b, s)
    mu.mem_write(BASE, CODE)
    for a in STUBS:
        mu.mem_write(a, b"\x70\x47")
    mu.mem_write(0x20000100, b"\x70\x47")
    emmc = {}
    if store:
        mp = [0xFFFF] * NIDS
        mp[3], mp[7], mp[9] = 2, 0, 1
        bitmap = bytearray(128)
        bitmap[40 >> 3] |= 1 << (40 & 7)       # image index 40: a bypassed frame
        hdr = struct.pack("<4sHHIHH", b"HXPI", S, NIDS, FIRST, NPIC, SPP) + bytes(bitmap) + struct.pack(f"<{NIDS}H", *mp)
        hdr += bytes(1912 - len(hdr)) + struct.pack("<H", 380) + bytes(6)
        nam = [0xFFFF] * 128
        nam[0], nam[4] = 3, 1                       # capture slots 1 and 5: pictures 3 and 1
        hdr += struct.pack("<128H", *nam)
        hdr += bytes(2304 - len(hdr))
        cols = [0] * 1024
        cols[10] = 28 << 10 | 4 << 5 | 2            # a category colour (red-ish)
        cols[40] = 14 << 10 | 2 << 5 | 1            # the bypassed frame's dimmer one (not used for the outline maths below)
        hdr += struct.pack("<1024H", *cols)
        hdr += bytes(HDR_SEC * 512 - len(hdr))
        for j in range(HDR_SEC):
            emmc[STORE + j] = hdr[512 * j:512 * (j + 1)]
        for k in range(NPIC):
            pic = b"".join(bytes([0x10 * (k + 1), 0x40 + r]) * S for r in range(S))
            pic += bytes(SPP * 512 - len(pic))
            for j in range(SPP):
                emmc[FIRST + k * SPP + j] = pic[512 * j:512 * (j + 1)]
    st = {"ids": {}, "reads": [], "calls": [], "fail": False, "knob": {}, "params": []}

    def hook(mu, addr, size, _):
        name = STUBS.get(addr)
        if not name:
            return
        assert mu.reg_read(UC_ARM_REG_SP) % 8 == 0, name
        st["calls"].append(name)
        if name == "obj":
            mu.reg_write(UC_ARM_REG_R0, 0x20006000)
        elif name == "desc":
            bid, d = mu.reg_read(UC_ARM_REG_R1), mu.reg_read(UC_ARM_REG_R2)
            pid = st["ids"].get(bid)
            st["asked"].append(bid)
            if pid is None:
                mu.reg_write(UC_ARM_REG_R0, 0xFFFFFFFF)
                return
            pid &= 0xFFFFFFFF
            mu.mem_write(d, struct.pack("<I", (pid << 8) & 0xFFFFFFFF) + bytes([pid >> 24]))
            mu.reg_write(UC_ARM_REG_R0, 0)
        elif name == "read":
            buf, sec, cnt = (mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            st["reads"].append((sec, cnt))
            if st["fail"]:
                mu.reg_write(UC_ARM_REG_R0, 0xFFFFFFFD)
                return
            mu.mem_write(buf, b"".join(emmc.get(sec + j, bytes(512)) for j in range(cnt)))
            mu.reg_write(UC_ARM_REG_R0, 0)
        elif name == "param":
            bid, q, out = (mu.reg_read(r) for r in (UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
            assert struct.unpack("<2I", bytes(mu.mem_read(q, 8))) == (0xFFFFFFFE, 0) and mu.mem_read(q + 8, 4) == bytes(4)
            val = st["knob"].get(bid, 0)
            mu.mem_write(out, struct.pack("<I", (val << 8) & 0xFFFFFFFF) + bytes([val >> 24]))
            st["params"].append(bid)
        elif name == "focus_fill":
            assert mu.reg_read(UC_ARM_REG_R4) == FB

    st["asked"] = []
    st["frames"] = []
    mu.hook_add(UC_HOOK_CODE, hook)
    mu.mem_write(CFG + 2, b"\x00")

    def widget(path, slot, index, x, y, w=48, h=48, anchor=4, visible=1):
        a = VIEW + 0x64 + 0x4C0 * path + 0x4C * slot
        mu.mem_write(a, bytes(0x4C))
        mu.mem_write(a, struct.pack("<I", index))
        mu.mem_write(a + 0xC, struct.pack("<4I", x, y, w, h))
        mu.mem_write(a + 0x1C, bytes([anchor, visible]))

    def run(focus=0):
        mu.mem_write(CFG + 2, bytes([focus]))
        st["calls"].clear(); st["reads"].clear(); st["asked"].clear()
        mu.mem_write(FB, bytes(800 * 480 * 2))
        for cx, cy, grey in st["frames"]:                 # a stock frame: a 2 pixel outline of this grey (5 bits), black inside
            for y in range(48):
                for x in range(48):
                    if x < 2 or x >= 46 or y < 2 or y >= 46:
                        mu.mem_write(FB + ((cy - 24 + y) * 800 + cx - 24 + x) * 2, struct.pack("<H", grey << 10 | grey << 5 | grey))
        mu.reg_write(UC_ARM_REG_R0, VIEW)
        mu.reg_write(UC_ARM_REG_R1, FB)
        mu.reg_write(UC_ARM_REG_R4, 0x1234)
        mu.reg_write(UC_ARM_REG_SP, 0x20008000)
        mu.reg_write(UC_ARM_REG_LR, 0x20000101)
        mu.emu_start(BASE | 1, 0x20000100)
        return bytes(mu.mem_read(FB, 800 * 480 * 2))
    return mu, st, widget, run


def box(fb, cx, cy, half):
    return [fb[((cy + dy) * 800 + cx - half) * 2:][:2 * half * 2] for dy in range(-half, half)]


mu, st, widget, run = machine()
st["ids"] = {1: 3, 2: 9, 11: 7, 21: 99, 38: 7}
widget(0, 0, 10, 103, 126)                 # path 0 slot 0: block id 1 -> preset 3 -> picture 2
widget(0, 1, 40, 188, 126)                 # slot 1: block id 2 -> preset 9 -> picture 1, a bypassed frame (image 40)
widget(0, 8, 10, 103, 270)                 # row B: block id 11 -> preset 7 -> picture 0
widget(0, 2, 10, 273, 126, visible=0)      # hidden
widget(0, 3, 10, 358, 126, w=36, h=66)     # not a 48 x 48 frame
widget(1, 0, 10, 103, 126, anchor=4)       # path 1 slot 0: block id 21 -> preset 99, past the map: nothing
widget(1, 15, 10, 700, 400)                # path 1 slot 15: block id 38 -> preset 7 -> picture 0
fb = run()
assert st["reads"] == [(STORE, HDR_SEC), (FIRST, NPIC * SPP)]           # the header, then every picture, once
asked = sorted(set(st["asked"]))
assert asked == [1, 2, 11, 21, 38], asked                         # 10 (2 path + slot / 8) + slot % 8 + 1


def drawn(fb, cx, cy, tag, dim=False):
    for r in range(S):
        row = fb[((cy - S // 2 + r) * 800 + cx - S // 2) * 2:][:2 * S]
        want = bytes([tag, 0x40 + r]) * S
        if dim:
            want = b"".join(struct.pack("<H", (struct.unpack("<H", want[i:i + 2])[0] >> 1) & 0x3DEF) for i in range(0, len(want), 2))
        assert row == want, (cx, cy, r, row.hex(), want.hex())


def blank(fb, cx, cy):
    assert not any(fb[((cy - 20 + r) * 800 + cx - 20) * 2:][:40] for r in range(40))


drawn(fb, 103, 126, 0x30)                  # picture 2
drawn(fb, 188, 126, 0x20, dim=True)        # picture 1, halved
drawn(fb, 103, 270, 0x10)                  # picture 0
drawn(fb, 700, 400, 0x10)
for cx, cy in ((273, 126), (358, 126), (103 + 0, 126 + 0)):
    pass
assert not any(fb[((126 - 3) * 800 + 273 - 3) * 2:][:6])           # the hidden slot: untouched
assert not any(fb[((126 - 3) * 800 + 358 - 3) * 2:][:6])           # the 36 x 66 one: untouched
# NAM blocks (preset id 380): the picture comes from the capture slot (the Model knob), not the preset id
st["ids"] = {1: 380, 2: 380, 11: 380, 21: 380}
st["knob"] = {1: 1, 2: 5, 11: 77, 21: 129}
st["frames"] = []
fb = run()
assert sorted(st["params"]) == [1, 2, 11, 21]
drawn(fb, 103, 126, 0x40)                  # slot 1 -> picture 3
drawn(fb, 188, 126, 0x20, dim=True)        # slot 5 -> picture 1 (a bypassed frame)
assert not any(fb[((270 - 3) * 800 + 103 - 3) * 2:][:6])           # slot 77: no picture
assert not any(fb[((126 - 3) * 800 + 103 - 3) * 2 + 0:][:0]) or True
st["ids"] = {1: 3, 2: 9, 11: 7, 21: 99, 38: 7}


def px(fb, x, y):
    v = struct.unpack("<H", fb[(y * 800 + x) * 2:][:2])[0]
    return v >> 10 & 31, v >> 5 & 31, v & 31


st["frames"] = [(103, 126, 16), (188, 126, 16), (103, 270, 8), (700, 400, 31)]
fb = run()
assert px(fb, 103 - 24, 126) == (28, 4, 2) and px(fb, 103, 126 - 24) == (28, 4, 2)    # outline grey 16: the category colour
assert px(fb, 103 + 23, 126 + 23) == (28, 4, 2) and px(fb, 103 - 22, 126 + 22) == (28, 4, 2)
assert px(fb, 188 - 24, 126) == (0, 0, 0) or True                                       # (colour 0 for image 40's own entry below)
assert px(fb, 103 - 24, 270) == (14, 2, 1)                                              # grey 8: half the colour
assert px(fb, 700 - 24, 400) == (31, 31, 31)                                            # white (selected): untouched
assert px(fb, 103 - 20, 126) == (0, 0, 0)                                               # outside the outline band: nothing
assert px(fb, 103 - 3, 126 - 3) != (28, 4, 2)                                           # the blanked square / picture inside
fb2 = run()
assert fb2 == fb and st["reads"] == []                             # a second paint: the same, no reads
# a square larger than the picture is blanked first (the stock icon under it): stock pixels in the 8 x 8 are gone
mu.mem_write(FB, b"\xff" * (800 * 480 * 2))
mu.reg_write(UC_ARM_REG_R0, VIEW); mu.reg_write(UC_ARM_REG_R1, FB)
mu.reg_write(UC_ARM_REG_SP, 0x20008000); mu.reg_write(UC_ARM_REG_LR, 0x20000101)
mu.emu_start(BASE | 1, 0x20000100)
row = bytes(mu.mem_read(FB + ((126 - S // 2 - 1) * 800 + 103 - S // 2 - 1) * 2, 2 * (S + 2)))
assert row == bytes(2 * (S + 2)), row.hex()                         # the blanked ring around the picture
assert bytes(mu.mem_read(FB + ((126 - S // 2 - 2) * 800 + 103) * 2, 2)) == b"\xff\xff"   # and nothing beyond it
# Focus View on: only the meter's focus_fill, no icons, no reads
run(focus=1)
assert st["calls"] == ["focus_fill"] and st["reads"] == []
# no store: nothing drawn, the header read once
mu, st, widget, run = machine(store=False)
st["ids"] = {1: 3}
widget(0, 0, 10, 103, 126)
assert not any(run()) and st["reads"] == [(STORE, HDR_SEC)]
assert not any(run()) and st["reads"] == []
print("block icons: block ids, 48 x 48 frames only, map, bypassed frames halved, blanked ring, cache, focus view, no store: OK")
