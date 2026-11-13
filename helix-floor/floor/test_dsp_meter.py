"""Unicorn (Cortex-M4) test of m4/floor_dsp_meter.bin (dsp_meter.py): a home view with two paths (path 2 split), the
labels read back from the frame by their glyphs, a removed block wiped, the second framebuffer kept apart, no DSP model,
lock order, stack and callee-saved registers. Firmware functions are Python stubs at their Floor addresses.
Needs unicorn (pip install unicorn). usage: python test_dsp_meter.py [out.png]  (the png needs Pillow)"""
import os
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                               UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp_meter  # noqa: E402

CODE, SYMS = dsp_meter.load()
CAVE = 0x1001f8bc & ~3
W, H = 800, 480
FB0, FB1 = 0x285a3f50, 0x285a3f50 + 0xbb800
VIEW, DSP, NODES, NODE0 = 0x28300000, 0x28400000, 0x28410000, 0x28420000
STUB = dict(STOCK_PAINT=0x280d6be8, DSP_LOCK=0x2813e63c, DSP_UNLOCK=0x2813e654, WLOCK=0x2808ee38, WUNLOCK=0x2808ee44,
            GET_VALUE=0x28150828, TEXT_REST=0x280941c8, CALLER=0x20001030)
ADDR = {v: k for k, v in STUB.items()}
FONT = [0b111101101101111, 0b010110010010111, 0b111001111100111, 0b111001111001111, 0b101101111001001,
        0b111100111001111, 0b111100111101111, 0b111001001001001, 0b111101111101111, 0b111101111001111,
        0b001001010100100, 0b111101111100100]
CHARS = "0123456789/P"
GREY, WHITE = 0x6318, 0x7fff

mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
for base, size in ((0x10000000, 0x100000), (0x20000000, 0x100000), (0x28000000, 0x2000000)):
    mu.mem_map(base, size)
mu.mem_write(CAVE, CODE)
for a in STUB.values():
    mu.mem_write(a, b"\x70\x47")
log = []
stock_line = None
settings = {74: 1, 122: 1}              # Preferences: DSP Meter Blocks (0/1), Paths (0 off, 1 numbers, 2 meters)


def r(reg):
    return mu.reg_read(reg)


def hook(uc, addr, size, _):
    name = ADDR.get(addr & ~1)
    if not name:
        return
    if name != "TEXT_REST":             # (the value-text trampoline's continuation is mid-function, not a call)
        assert r(UC_ARM_REG_SP) % 8 == 0, f"stack is not 8-byte aligned at {name}"
    a0, a1 = r(UC_ARM_REG_R0), r(UC_ARM_REG_R1)
    if name == "STOCK_PAINT":
        assert a1 == VIEW and a0 in (FB0, FB1)
        if stock_line:                  # the stock paint draws a path line through where a label was
            x0, x1, y = stock_line
            uc.mem_write(a0 + 2 * (y * W + x0), struct.pack("<H", 0x4210) * (x1 - x0))
    if name in ("DSP_LOCK", "DSP_UNLOCK"):
        assert a0 == 0
    if name == "GET_VALUE":             # (id, out): {type, value at +4}; -3 for an ID it doesn't know
        if a0 in settings and settings[a0] is not None:
            uc.mem_write(a1, struct.pack("<Bxxxi", 2, settings[a0]))
            uc.reg_write(UC_ARM_REG_R0, 0)
        else:
            uc.reg_write(UC_ARM_REG_R0, 0xfffffffd)
    if name == "TEXT_REST":
        uc.emu_stop()
        return
    if name == "CALLER":
        uc.emu_stop()
        return
    log.append(name)


mu.hook_add(UC_HOOK_CODE, hook)


def widget(p, k, x, y, visible=1):
    """An image widget: +4 image, +8 tint, +0xc x, +0x10 y, +0x14 w, +0x18 h, +0x1c anchor (4: centred), +0x1d visible."""
    w = VIEW + 0x64 + 0x4c0 * p + 0x4c * k
    mu.mem_write(w, bytes(0x4c))
    mu.mem_write(w + 4, struct.pack("<5i", 0x20, -1, x, y, 48) + struct.pack("<iBB", 48, 4, visible))


def block(index, cost, handle=None):
    """Record index -> a handle -> a block node (kind 1) with cost."""
    h = index + 3 if handle is None else handle
    mu.mem_write(DSP + 0x14 + 0x54 * index, struct.pack("<i", h))
    if 0 <= h <= 0x4b:
        node = NODE0 + 0x100 * h
        mu.mem_write(NODES + 0x24 + 4 * h, struct.pack("<I", node))
        mu.mem_write(node, bytes(0x100))
        mu.mem_write(node + 5, b"\x01")
        mu.mem_write(node + 0x44, struct.pack("<i", cost))


def call(fb):
    mu.reg_write(UC_ARM_REG_R0, fb)
    mu.reg_write(UC_ARM_REG_R1, VIEW)
    mu.reg_write(UC_ARM_REG_SP, 0x200F0000)
    mu.reg_write(UC_ARM_REG_LR, STUB["CALLER"] | 1)
    regs = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10,
            UC_ARM_REG_R11)
    for i, reg in enumerate(regs):
        mu.reg_write(reg, 0xA5A5A500 + i)
    del log[:]
    mu.emu_start((CAVE + SYMS["dm_paint"]) | 1, 0, count=50_000_000)
    assert r(UC_ARM_REG_PC) & ~1 == STUB["CALLER"], hex(r(UC_ARM_REG_PC))
    assert r(UC_ARM_REG_SP) == 0x200F0000, "stack not balanced"
    assert all(r(reg) == 0xA5A5A500 + i for i, reg in enumerate(regs)), "callee-saved register clobbered"
    # the settings read first; the DSP model's lock never held with the widget lock; the stock paint after the wipes,
    # before the labels
    assert log[:2] == ["GET_VALUE", "GET_VALUE"], log
    del log[:2]
    if "DSP_LOCK" in log:
        assert log == ["DSP_LOCK", "DSP_UNLOCK", "WLOCK", "WUNLOCK", "STOCK_PAINT"], log
    else:
        assert log == ["WLOCK", "WUNLOCK", "STOCK_PAINT"], log


def frame(fb):
    return struct.unpack(f"<{W * H}H", bytes(mu.mem_read(fb, W * H * 2)))


def text_at(px, left, top, colour, n=None):
    """The glyphs drawn at (left, top) in colour, read cell by cell (scale 2, advance 8): n of them (a blank one is a
    space), or up to the first blank."""
    out = ""
    x = left
    while n is None or len(out) < n:
        bits = 0
        for cell in range(15):
            cx, cy = x + 2 * (cell % 3), top + 2 * (cell // 3)
            on = px[cy * W + cx]
            assert on in (0, colour), (x, top, hex(on))
            assert all(px[(cy + dy) * W + cx + dx] == on for dy in (0, 1) for dx in (0, 1))
            bits = (bits << 1) | (on == colour)
        if bits == 0 and n is None:
            return out
        if bits == 0:
            out += " "
            x += 8
            continue
        assert bits in FONT, (x, top, bin(bits))
        out += CHARS[FONT.index(bits)]
        x += 8
    return out


def label_left(cx, text):
    return cx - (8 * len(text) - 2) // 2


def under(px, x, y, text):
    """The grey label centred under the 48 x 48 icon centred at (x, y)."""
    return text_at(px, label_left(x, text), y + 24 + 6, GREY)


def total(px, path, text):
    """'Pn used/75' right-aligned in path n's slot of the title bar."""
    right = 736 - (path == 1) * (9 * 8 - 2 + 16)
    return text_at(px, right - (8 * len(text) - 2), 24, WHITE, len(text))


def black(px, left, top, w, h):
    return all(px[(top + j) * W + left + i] == 0 for j in range(h) for i in range(w))


# path 1: eight blocks on row A (y 126); path 2 split: two on row A (y 234), one on row B (y 306)
mu.mem_write(DSP_PTR := 0x284e5758, struct.pack("<I", DSP))
mu.mem_write(DSP + 0x5060, struct.pack("<I", NODES))
for i in range(32):
    block(i, 0, handle=-1)
costs0 = [750, 1249, 3250, 35, 0, 999, 4000, 2345]
for k, c in enumerate(costs0):
    widget(0, k, 103 + 85 * k, 126)
    block(k, c)
widget(1, 0, 103, 234)
block(16, 1500)
widget(1, 1, 188, 234)
block(17, 820)
widget(1, 8, 103, 306)
block(24, 3250)
widget(1, 2, 273, 234, visible=0)      # a hidden slot: no label, though its record has a block
block(18, 600)
widget(1, 3, 358, 234)                 # a shown slot with no block: no label
mu.mem_write(DSP + 0x14 + 0x54 * 19, struct.pack("<i", 0x4c))   # (a handle past the table: none)


def cfg(blocks, paths):
    """The two Preferences settings, as GET_VALUE gives them: block labels 0/1; path totals 0 off, 1 numbers, 2 meters."""
    settings[74], settings[122] = blocks, paths


cfg(1, 1)
call(FB0)
px = frame(FB0)
want0 = ["8", "12", "33", "0", "0", "10", "40", "23"]
for k, t in enumerate(want0):
    assert under(px, 103 + 85 * k, 126, t) == t, (k, under(px, 103 + 85 * k, 126, t))
assert under(px, 103, 234, "15") == "15" and under(px, 188, 234, "8") == "8" and under(px, 103, 306, "33") == "33"
assert black(px, 273 - 12, 234 + 30, 24, 10) and black(px, 358 - 12, 234 + 30, 24, 10)
assert total(px, 1, "P1 126/75") == "P1 126/75", total(px, 1, "P1 126/75")
assert total(px, 2, "P2 62/75") == "P2 62/75"     # 15 + 8 + 33 + the hidden slot's 6: the sum is the DSP's
print("FB0: block labels and totals read back")

# FB1 is drawn on its own; then path 1's third block goes and the paint of FB0 wipes its label, and only it
call(FB1)
assert frame(FB1) == px
widget(0, 2, 273, 126, visible=0)
block(2, 0, handle=-1)
stock_line = (240, 310, 160)            # through the removed label's middle row
call(FB0)
stock_line = None
px2 = frame(FB0)
assert all(px2[160 * W + x] == 0x4210 for x in range(240, 310)), "the wipe ran after the stock paint"
assert black(px2, 273 - 12, 126 + 30, 24, 4) and black(px2, 273 - 12, 126 + 35, 24, 5), "the removed label was not wiped"
assert under(px2, 103, 126, "8") == "8" and under(px2, 358, 126, "0") == "0"
assert total(px2, 1, "P1 93/75") == "P1 93/75"
assert black(px2, 650 - 70, 24, 6, 10)        # the old total's first glyph ("P" of P1 126/75) is gone
assert frame(FB1) == px, "FB1 changed by FB0's paint"
print("FB0 after a block went: its label wiped, the rest and FB1 unchanged")

# meters: "Pn" and a 50 x 10 bar filled to used/75 (P1's 93 stops at 75: red, full; P2's 62: yellow, 39 of 48)
cfg(1, 2)
call(FB0)
px3 = frame(FB0)
EDGE, RED, YELLOW, GREEN = 0x4210, 0x7c00, 0x7f00, 0x0300
for left, fill, colour in ((580, 48, RED), (666, 62 * 48 // 75, YELLOW)):
    assert text_at(px3, left, 24, WHITE, 2) in ("P1", "P2")
    bx = left + 20
    assert all(px3[24 * W + x] == EDGE and px3[33 * W + x] == EDGE for x in range(bx, bx + 50))
    assert all(px3[y * W + bx] == EDGE and px3[y * W + bx + 49] == EDGE for y in range(24, 34))
    for y in range(25, 33):
        row = [px3[y * W + x] for x in range(bx + 1, bx + 49)]
        assert row == [colour] * fill + [0] * (48 - fill), (left, y, row)
assert text_at(px3, 580, 24, WHITE, 2) == "P1" and text_at(px3, 666, 24, WHITE, 2) == "P2"
assert black(px3, 594, 24, 6, 10) and black(px3, 680, 24, 6, 10)     # the numbers' glyphs between "Pn" and the bar wiped
assert under(px3, 103, 126, "8") == "8"
print("meters: P1 full red, P2 yellow 39/48, numbers wiped")
pxm = px3

# block labels off: wiped; the meters stay
cfg(0, 2)
call(FB0)
px4 = frame(FB0)
for k in (0, 1, 3, 4, 5, 6, 7):
    assert black(px4, 103 + 85 * k - 12, 156, 24, 10), k
assert black(px4, 103 - 12, 264, 24, 10) and black(px4, 103 - 12, 336, 24, 10)
assert [px4[28 * W + x] for x in range(601, 649)] == [RED] * 48
# totals off too: nothing left
cfg(0, 0)
call(FB0)
left = [(i % W, i // W) for i, v in enumerate(frame(FB0)) if v and i // W != 160]   # (row 160: the mock stock line)
assert not left, ("labels left with both settings off", left[:5])
print("block labels off, then totals off: wiped")
cfg(1, 2)

# a failed settings read keeps the last values; out-of-range values clamp (a stored 5 on Paths reads as meters)
call(FB0)
settings[74] = settings[122] = None
call(FB0)
assert bytes(mu.mem_read(CAVE + SYMS["dm_cfg"], 2)) == bytes([1, 2])
cfg(7, 5)
call(FB0)
assert bytes(mu.mem_read(CAVE + SYMS["dm_cfg"], 2)) == bytes([1, 2])
print("settings: a failed read keeps the last, out of range clamps")


def text(sid, value, size=32):
    """dm_text (the value-text function's start) -> (result, the string) for our IDs."""
    val, out = 0x20002000, 0x20002100
    mu.mem_write(val, struct.pack("<Bxxxi", 2, value))
    mu.mem_write(out, b"\xee" * 40)
    mu.reg_write(UC_ARM_REG_R0, sid)
    mu.reg_write(UC_ARM_REG_R1, val)
    mu.reg_write(UC_ARM_REG_R2, out)
    mu.reg_write(UC_ARM_REG_R3, size)
    mu.reg_write(UC_ARM_REG_SP, 0x200F0000)
    mu.reg_write(UC_ARM_REG_LR, STUB["CALLER"] | 1)
    mu.emu_start((CAVE + SYMS["dm_text"]) | 1, 0, count=10_000)
    pc = r(UC_ARM_REG_PC) & ~1
    if pc == STUB["TEXT_REST"]:
        return "stock", r(UC_ARM_REG_SP)
    assert pc == STUB["CALLER"] and r(UC_ARM_REG_SP) == 0x200F0000
    b = bytes(mu.mem_read(out, 40))
    assert b"\0" in b[:size] and b[b.index(b"\0") + 1:] == b"\xee" * (39 - b.index(b"\0"))
    return r(UC_ARM_REG_R0), b[:b.index(b"\0")].decode()


assert [text(74, v) for v in (0, 1, 9)] == [(0, "Off"), (0, "On"), (0, "On")]
assert [text(122, v) for v in (0, 1, 2, 3)] == [(0, "Off"), (0, "Numbers"), (0, "Meters"), (0, "Meters")]
assert text(122, 1, size=4) == (0, "Num")
mu.reg_write(UC_ARM_REG_R4, 0x44444444)
res = text(73, 0)                       # another ID: the stock function, its first 8 bytes run (7 registers, d8)
assert res == ("stock", 0x200F0000 - 36), res
assert struct.unpack("<7I", bytes(mu.mem_read(0x200F0000 - 28, 28)))[0] == 0x44444444
assert r(UC_ARM_REG_R0) == 73 and r(UC_ARM_REG_R2) == 0x20002100 and r(UC_ARM_REG_R3) == 32
print("value text: Off/On, Off/Numbers/Meters, cut to size, other IDs go on to the stock function")

# no DSP model (as at boot): every label goes, no lock taken
mu.mem_write(DSP_PTR, struct.pack("<I", 0))
call(FB1)
assert "DSP_LOCK" not in log
assert all(v == 0 for v in frame(FB1)), "labels left without a DSP model"
print("no DSP model: FB1 wiped, no DSP lock")

if len(sys.argv) > 1:
    from PIL import Image
    img = Image.new("RGB", (W, H))
    img.putdata([(((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31) for v in pxm])
    img.save(sys.argv[1])
    print("saved", sys.argv[1])
print("ok:", len(CODE), "bytes")
