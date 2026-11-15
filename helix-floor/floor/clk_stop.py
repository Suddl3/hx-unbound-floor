#!/usr/bin/env python3
"""Tap Tempo Pitch = Transparent also when the MIDI clock stops (env NAM_CLK_STOP=1).

Stock: when an incoming MIDI clock stops, the Floor goes back to the preset (or global) tempo. The two clock-state
listeners (0x28090970 and 0x28090b08; they run on the clock events the MIDI clock task posts) send that tempo to the DSP
with a bare `bl 0x2813ae68` (the DSP message sender: r0 ctx, r1 setting id 0x10 or 0xf, r2 -> {type 3, float}). The tap
tempo handler (0x280dd8c0) and the clock-update listener (0x28090ca0) wrap the same send as

    0x28148154(ctx, 1);  lock(ctx);  send;  unlock(ctx);  0x28148154(ctx, 0)

0x28148154 reads Tap Tempo Pitch (setting 65, the only reader) and, in Transparent, tells the DSP a tempo change is under
way. The revert had no such bracket, so after a stop the delay and reverb trails pitch-shifted even in Transparent
(found on the unit: preset BPM 120, clock at 80, clock stopped: the 440 Hz tail went +125 cents; with the bracket it
stays within a few cents). Without the lock around the send the editor's USB channel stopped answering after the stop
(audio unaffected), so the lock is part of the fix.

Six sends (3 in each listener: preset tempo, global tempo, a third one with its id in a literal) become a jump to a
wrapper in the seg0 cave that does the bracket, the send, and then the replaced `ldrb r3,[r4]; cmp r3,#4; bne` of the
site. Each site is 10 bytes (a `bl` and the three instructions after it) inside a 12-byte window:

  "mid" sites (the bl is 2 mod 4, `movs r1,#imm` just before it):  [movs r1][ldr.w pc,[pc,#4]][nop][literal]
  "aligned" sites (the bl is word aligned):                         [ldr.w pc,[pc,#4]][nop][nop][literal]

The jump instruction reads Align(site + 4, 4) + 4, which is the literal in both layouts. Cave code is in local SRAM, out
of BL range, so every call goes through a register; the wrapper keeps SP 8-aligned (push of 4 registers) and returns
the registers the site expects (r4 untouched). Live-tested through floor/auto/clk_fix.py (the same wrapper in RAM).
"""
import os
import struct
import sys

ENABLED = os.environ.get("NAM_CLK_STOP") == "1"
H = lambda *v: b"".join(struct.pack("<H", x) for x in v)

BRACKET, SEND, LOCK, UNLOCK = 0x28148154, 0x2813AE68, 0x2813E63C, 0x2813E654

# (window start, kind, listener); the listener picks the wrapper (where the replaced bne goes)
SITES = [
    (0x28090A78, "mid", "A"), (0x28090A90, "aligned", "A"), (0x28090AA4, "mid", "A"),
    (0x28090C10, "mid", "B"), (0x28090C28, "aligned", "B"), (0x28090C3C, "mid", "B"),
]
# where the replaced `bne` and the fall-through `b` of each listener go: (else, equal)
TAILS = {"A": (0x280909AE, 0x280909F8), "B": (0x28090B46, 0x28090B90)}
# the stock 12-byte windows (read from the unit's firmware 3.80.0 image): [movs r1][bl 0x2813ae68][ldrb][cmp][bne ..]
STOCK = {
    0x28090A78: bytes.fromhex("1021aaf0f5f92378042b94d1"),
    0x28090A90: bytes.fromhex("aaf0eaf92378042b89d1ade7"),
    0x28090AA4: bytes.fromhex("1021aaf0dff92378042b7ff4"),
    0x28090C10: bytes.fromhex("1021aaf029f92378042b94d1"),
    0x28090C28: bytes.fromhex("aaf01ef92378042b89d1ade7"),
    0x28090C3C: bytes.fromhex("1021aaf013f92378042b7ff4"),
}


def wrapper(else_t, eq_t):
    """Thumb code (position independent: literals follow it): bracket(1); lock; send; unlock; bracket(0); pop; then the
    site's ldrb r3,[r4]; cmp r3,#4; beq eq_t (else else_t)."""
    items = [0xB4F0, 0x0004, 0x000D, 0x0016,                  # push {r4-r7} (16 bytes); r4, r5, r6 = r0, r1, r2
             0x0020, 0x2101, ("ldr3", "br"), 0x4798,           # r0 = ctx; r1 = 1; blx bracket (begin)
             0x0020, ("ldr3", "lock"), 0x4798,                 # lock(ctx)
             0x0020, 0x0029, 0x0032, ("ldr3", "send"), 0x4798,   # send(ctx, id, msg)
             0x0020, ("ldr3", "unlock"), 0x4798,               # unlock(ctx)
             0x0020, 0x2100, ("ldr3", "br"), 0x4798,           # r1 = 0; bracket (end)
             0xBCF0, 0x7823, 0x2B04, 0xD001,                   # pop {r4-r7}; ldrb r3,[r4]; cmp r3,#4; beq over the next jump
             ("ldrpc", "else"), ("ldrpc", "eq")]
    lits = {"else": else_t | 1, "eq": eq_t | 1, "br": BRACKET | 1, "send": SEND | 1,
            "lock": LOCK | 1, "unlock": UNLOCK | 1}
    size = sum(4 if isinstance(i, tuple) and i[0] == "ldrpc" else 2 for i in items)
    pool = (size + 3) & ~3
    addr = {k: pool + 4 * n for n, k in enumerate(lits)}
    out, pc = b"", 0
    for i in items:
        if isinstance(i, int):
            out += H(i)
            pc += 2
        elif i[0] == "ldr3":
            off = addr[i[1]] - ((pc + 4) & ~3)
            assert 0 <= off < 1024 and off % 4 == 0
            out += H(0x4B00 | off // 4)
            pc += 2
        else:
            off = addr[i[1]] - ((pc + 4) & ~3)
            assert 0 <= off < 4096
            out += H(0xF8DF, 0xF000 | off)
            pc += 4
    out += bytes(pool - len(out)) + b"".join(struct.pack("<I", v) for v in lits.values())
    return out


def build(base):
    """(code, {listener: wrapper address}) with the two wrappers laid out from `base` (word aligned)."""
    assert base % 4 == 0
    code, at = b"", {}
    for ln in ("A", "B"):
        at[ln] = base + len(code)
        code += wrapper(*TAILS[ln])
        code += bytes((-len(code)) & 3)
    return code, at


def site_patch(va, kind, wrap):
    """The 12 replacement bytes for the window at va (it keeps its leading `movs r1,#imm` on a mid site)."""
    stock = STOCK[va]
    lit = struct.pack("<I", wrap | 1)
    if kind == "mid":
        return stock[:2] + H(0xF8DF, 0xF004, 0xBF00) + lit
    return H(0xF8DF, 0xF004, 0xBF00, 0xBF00) + lit


def site_patches(at):
    """{address: bytes} for the six windows, given the wrapper addresses from build()."""
    return {va: site_patch(va, kind, at[ln]) for va, kind, ln in SITES}


def main():
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    code, at = build(0x1001F000)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for ln in ("A", "B"):
        print("wrapper", ln, hex(at[ln]))
        n = (at["B"] if ln == "A" else 0x1001F000 + len(code)) - at[ln]
        for i in md.disasm(code[at[ln] - 0x1001F000:at[ln] - 0x1001F000 + n - 28], at[ln]):
            print("  %#x %s %s" % (i.address, i.mnemonic, i.op_str))
    print(len(code), "bytes")


if __name__ == "__main__":
    sys.exit(main())
