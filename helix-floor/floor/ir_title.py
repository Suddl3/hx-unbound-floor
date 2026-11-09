#!/usr/bin/env python3
"""The block title shows the selected User IR's name for NAM blocks (the Floor's version of
upstream's ir-title; the Floor's title code differs from the Stomp's).

Floor title code (Entry 0):
- site A `0x280ac164`: `ldrb r3,[r6,#12]; cmp r3,#15; beq.w 0x280ac374` (category 15 = IR ->
  the IR path, which takes r4 = subcategory and, for 0, the IR Single name branch
  `0x280ac8ee`); otherwise `0x280ac16c`.
- site B `0x280ad37c` (a knob changed): `ldrb r3,[r5,#12]; cmp r3,#15; beq 0x280ad38e` (IR:
  knob 0 redraws the title) else `0x280ad382` (return).
- r6 / r5 point at the block's descriptor: +1 its preset id (word), +12 category, +13 subcategory.

Patch: for an Amp-category (12) block whose preset id is one of PIDS, site A goes to the IR
Single name branch with r4 = 0 (as an IR Single block; the Model knob is knob 0, an IR
index like the IR block's), and site B treats it as an IR block (knob 0 redraws). Amp+Cab
(11) blocks keep the stock title (no cab-half confusion). The IR path's `[...+0x9c]` test
before the name branch is skipped for NAM blocks.

Both caves live in the seg0 cave (local SRAM, out of B.W range of seg2): site A becomes
`ldr.w pc,[pc,#0]; .word caveA|1` (its 8 bytes); site B (6 bytes) a `b.w` to a relay
`ldr.w pc,[pc,#0]; .word caveB|1` in the 8 bytes the guard trampoline left free at
0x28135078 (the old budget check's tail; nothing branches into it). The caves return
through `ldr.w pc` literals. Only r3 (and r4 = 0 on the NAM path, as the IR path sets it)
change, as at the stock sites.
"""
import struct
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arm_guards import Asm, COND, cmpi, movs  # noqa: E402

SITE_A, SITE_A_STOCK = 0x280AC164, bytes.fromhex("337b0f2b00f00481")
SITE_B, SITE_B_STOCK = 0x280AD37C, bytes.fromhex("2b7b0f2b05d0")
IR_PATH, NON_IR, IR_NAME = 0x280AC374, 0x280AC16C, 0x280AC8EE
B_IR, B_RET = 0x280AD38E, 0x280AD382
RELAY = 0x28135078
CAT_IR, CAT_AMP = 15, 12
# The knob-K title (the 555 build: Model is knob 6, a float 0..1000), upstream's ir-title --knob for the
# Floor. The IR Single name branch IR_NAME does: q = {-2, knob 0} (sp+0x38), half byte r4 (sp+0x40),
# CTX_FN(), PARAM_FN(ctx, r1 = r5 the slot, &q, sp+0x18); the value is the 4 bytes at sp+0x19, read
# back by AFTER_READ (subs r0,#1: the IR slot test, then the name). For a knob-K block the cave does
# the same with knob K, truncates the float to an int (integer code, as upstream), writes it back as
# bytes and goes on at AFTER_READ; a value outside 1..128 takes EMPTY (the stock not-found title).
# Calls go through a register (the cave in local SRAM is out of BL range); r0 (CTX_FN's result, the
# context PARAM_FN takes) and r1 are left alone before the calls, as at the stock site.
# Site B: the IR branch B_IR redraws on knob 0 (or 6 for an IR subcategory 1); a knob-K block
# redraws (B_REDRAW) when the changed knob [sp+0xa4] is K.
CTX_FN, PARAM_FN, AFTER_READ, EMPTY = 0x28114A1C, 0x2813AAB8, 0x280AC90A, 0x280ACA80
B_REDRAW, B_KNOB_SP = 0x280AD39C, 0xA4
COND["gt"] = 12


def ldrb_r3(rn):
    return 0x7800 | 12 << 6 | rn << 3 | 3


def ldrw_r3_1(rn):
    """ldr.w r3, [rn, #1] (T3)."""
    return [0xF8D0 | rn, 0x3001]


def cmp_r3(v):
    import patch_amp
    b = patch_amp._cmp_r3(v)
    return list(struct.unpack('<%dH' % (len(b) // 2), b))


def subw_r3(imm):
    """subw r3, r3, #imm (T4): preset ids such as 555 are no Thumb-2 modified immediates."""
    assert 0 <= imm < 4096
    return [0xF2A3 | (imm >> 11) << 10, ((imm >> 8) & 7) << 12 | 3 << 8 | (imm & 0xFF)]


def build(base, pids, knob_pids=(), knob=6):
    """pids: Model on knob 0 (an int IR index); knob_pids: Model on knob `knob` (a float)."""
    a = Asm(base)

    def hs(lst):
        for h in lst:
            a.h(h)

    def raw(hexs):
        hs(struct.unpack("<%dH" % (len(hexs) // 4), bytes.fromhex(hexs)))

    # caveA (site A: r6 = the block)
    a.label("caveA")
    a.h(ldrb_r3(6))
    a.h(cmpi(3, CAT_IR))
    a.b("ne", "a1")
    a.ldrpc("w_ir_path")
    a.label("a1")
    a.h(cmpi(3, CAT_AMP))
    a.b("ne", "a3")
    hs(ldrw_r3_1(6))
    for p in pids:
        hs(cmp_r3(p))
        a.b("eq", "a2")
    for p in knob_pids:
        hs(ldrw_r3_1(6))
        hs(subw_r3(p))
        a.h(cmpi(3, 0))
        a.b("eq", "k")
    a.label("a3")
    a.ldrpc("w_non_ir")
    a.label("a2")
    a.h(movs(4, 0))
    a.ldrpc("w_ir_name")
    if knob_pids:
        a.label("k")
        a.h(movs(4, 0))
        raw("6ff00102")                   # mvn r2, #1
        a.h(movs(3, knob))
        raw("cde90e23")                   # strd r2, r3, [sp, #0x38]
        raw("8df84040")                   # strb.w r4, [sp, #0x40]
        a.lit(3, "w_ctx")
        a.h(0x4798)                       # blx r3
        a.lit(3, "w_param")
        a.h(0x469C)                       # mov ip, r3
        a.h(0xAB06)                       # add r3, sp, #0x18
        a.h(0x4629)                       # mov r1, r5
        a.h(0xAA0E)                       # add r2, sp, #0x38
        a.h(0x47E0)                       # blx ip
        raw("9df81c00")                   # ldrb.w r0, [sp, #0x1c]
        a.h(0x9B06)                       # ldr r3, [sp, #0x18]
        a.h(0x0600)                       # lsls r0, r0, #24
        raw("40ea1320")                   # orr.w r0, r0, r3, lsr #8: the float's bits (sp+0x19)
        a.h(0x0DC2)                       # lsrs r2, r0, #23
        a.b("eq", "chk")
        a.h(0x3A7F)                       # subs r2, #127
        a.b("mi", "zero")
        a.h(cmpi(2, 23))
        a.b("gt", "chk")
        raw("c0f3160141f40001c2f1170221fa02f0")   # ubfx; orr #0x800000; rsb r2, #23; lsr.w r0, r1, r2
        a.b("al", "chk")
        a.label("zero")
        a.h(movs(0, 0))
        a.label("chk")
        a.h(0x1E41)                       # subs r1, r0, #1
        a.h(cmpi(1, 127))
        a.b("hi", "empty")
        raw("8df81900")                   # strb.w r0, [sp, #0x19]
        a.h(movs(2, 0))
        raw("8df81a20" "8df81b20" "8df81c20")    # strb.w r2, [sp, #0x1a / 0x1b / 0x1c]
        a.ldrpc("w_after_read")
        a.label("empty")
        a.ldrpc("w_empty")
    # caveB (site B: r5 = the block)
    a.label("caveB")
    a.h(ldrb_r3(5))
    a.h(cmpi(3, CAT_IR))
    a.b("eq", "b4")
    a.h(cmpi(3, CAT_AMP))
    a.b("ne", "b5")
    hs(ldrw_r3_1(5))
    for p in pids:
        hs(cmp_r3(p))
        a.b("eq", "b4")
    for p in knob_pids:
        hs(ldrw_r3_1(5))
        hs(subw_r3(p))
        a.h(cmpi(3, 0))
        a.b("eq", "bk")
    a.label("b5")
    a.ldrpc("w_b_ret")
    a.label("b4")
    a.ldrpc("w_b_ir")
    if knob_pids:
        a.label("bk")
        a.h(0x9B00 | B_KNOB_SP // 4)      # ldr r3, [sp, #0xa4]: the knob that changed
        a.h(cmpi(3, knob))
        a.b("ne", "b5")
        a.ldrpc("w_b_redraw")
    a.align4()
    words = [("w_ir_path", IR_PATH), ("w_non_ir", NON_IR), ("w_ir_name", IR_NAME),
             ("w_b_ret", B_RET), ("w_b_ir", B_IR)]
    if knob_pids:
        words += [("w_ctx", CTX_FN), ("w_param", PARAM_FN), ("w_after_read", AFTER_READ),
                  ("w_empty", EMPTY), ("w_b_redraw", B_REDRAW)]
    for name, v in words:
        a.word(name, v | 1)
    code = a.assemble()
    return code, a.labels["caveA"], a.labels["caveB"]


def site_patches(ca, cb):
    """{address: bytes} for the two sites and the relay."""
    import patch_amp
    # ldr.w pc, [pc, #0] reads Align(site + 4, 4): the literal right after it only when the site is 0 mod 4
    # (the Helix LT port's boot blue screen: its site A is 2 mod 4)
    assert SITE_A % 4 == 0 and RELAY % 4 == 0, "a literal-jump site is not word aligned"
    return {SITE_A: struct.pack("<HHI", 0xF8DF, 0xF000, ca | 1),
            SITE_B: patch_amp.thumb_bw(SITE_B, RELAY) + b"\x00\xbf",
            RELAY: struct.pack("<HHI", 0xF8DF, 0xF000, cb | 1)}


STOCK = {SITE_A: SITE_A_STOCK, SITE_B: SITE_B_STOCK}
RELAY_BEFORE = bytes.fromhex("00200120704700bf")     # movhi r0,#0; movls r0,#1; bx lr; nop: the
#                                                      old budget check's tail, dead once its head jumps
