"""clk_stop: the six sites and the wrapper, run in a small Thumb interpreter with the firmware's calls recorded."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clk_stop as c  # noqa: E402
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB  # noqa: E402

BASE = 0x1001F000
CTX, MSG = 0x20001234, 0x20005678


def run(code, entry, r4_byte, r1=0x10):
    """Run the wrapper from `entry` with r0 = CTX, r1, r2 = MSG, r4 pointing at a byte; calls through blx are recorded and
    return 0. Returns (calls, jump target, registers)."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    mem = {BASE + i: b for i, b in enumerate(code)}
    mem[0x20003000] = r4_byte
    r = [0] * 16
    r[0], r[1], r[2], r[4], r[13] = CTX, r1, MSG, 0x20003000, 0x20008000
    calls = []
    saved = list(r)

    def r32(a): return sum(mem.get(a + k, 0) << 8 * k for k in range(4))

    def w32(a, v):
        for k in range(4): mem[a + k] = (v >> 8 * k) & 0xFF

    pc = entry & ~1
    z = False
    for _ in range(300):
        ins = next(md.disasm(bytes(mem.get(pc + k, 0) for k in range(4)), pc, 1))
        nxt, m, op = pc + ins.size, ins.mnemonic, ins.op_str
        if pc < BASE or pc >= BASE + len(code):
            return calls, pc, r, saved
        if m == "push":
            regs = [int(x[1:]) for x in op.strip("{}").split(", ")]
            for x in reversed(regs):
                r[13] -= 4; w32(r[13], r[x])
        elif m == "pop":
            for x in [int(y[1:]) for y in op.strip("{}").split(", ")]:
                r[x] = r32(r[13]); r[13] += 4
        elif m == "movs" and op.split(", ")[1].startswith("r"):
            d, s = [int(x[1:]) for x in op.split(", ")]; r[d] = r[s]
        elif m == "movs":
            d, i = op.split(", "); r[int(d[1:])] = int(i[1:], 0)
        elif m == "ldr" and "[pc" in op:
            d, rest = op.split(", [pc, #")
            r[int(d[1:])] = r32(((pc + 4) & ~3) + int(rest.rstrip("]"), 0))
        elif m == "ldrb":
            d, rest = op.split(", [")
            r[int(d[1:])] = mem.get(r[int(rest.strip("]")[1:])], 0)
        elif m == "cmp":
            a, i = op.split(", "); z = r[int(a[1:])] == int(i[1:], 0)
        elif m == "beq":
            if z: nxt = int(op[1:], 0)
        elif m == "blx":
            tgt = r[int(op[1:])] & ~1
            calls.append((tgt, r[0], r[1], r[2]))
            r[0] = 0
        elif m == "ldr.w" and op.startswith("pc, [pc"):
            return calls, r32(((pc + 4) & ~3) + int(op.split("#")[1].rstrip("]"), 0)) & ~1, r, saved
        elif m == "nop":
            pass
        else:
            raise AssertionError(f"unhandled {m} {op} at {pc:#x}")
        pc = nxt
    raise AssertionError("no end")


def main():
    code, at = c.build(BASE)
    bad = []
    seq = [(c.BRACKET, 1), (c.LOCK, None), (c.SEND, None), (c.UNLOCK, None), (c.BRACKET, 0)]
    for ln in ("A", "B"):
        for byte, tail in ((4, 1), (0, 0)):
            calls, to, r, saved = run(code, at[ln], byte)
            want = c.TAILS[ln][tail]
            if [x[0] for x in calls] != [s[0] for s in seq]:
                bad.append((ln, "call order", [hex(x[0]) for x in calls]))
            if calls[0][1:3] != (CTX, 1) or calls[4][1:3] != (CTX, 0):
                bad.append((ln, "bracket args", calls))
            if calls[2][1:] != (CTX, 0x10, MSG) or calls[1][1] != CTX or calls[3][1] != CTX:
                bad.append((ln, "send args", calls))
            if to != want:
                bad.append((ln, byte, "tail", hex(to), hex(want)))
            if r[4] != saved[4] or r[5:8] != saved[5:8] or r[13] != saved[13]:
                bad.append((ln, "registers not kept", r[4:8], r[13]))
    # sites: stock windows are the 12 bytes the wrapper replaces; each patched window decodes to a jump to its wrapper
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    patches = c.site_patches(at)
    for va, kind, ln in c.SITES:
        stock, new = c.STOCK[va], patches[va]
        if len(new) != 12 or len(stock) != 12:
            bad.append((hex(va), "size"))
        ins = list(md.disasm(stock, va))
        bl = [i for i in ins if i.mnemonic == "bl"]
        if len(bl) != 1 or bl[0].op_str != "#0x%x" % c.SEND:
            bad.append((hex(va), "stock window has no bl to the sender", [i.mnemonic for i in ins]))
        jump_at = va + (2 if kind == "mid" else 0)
        j = next(md.disasm(new[jump_at - va:], jump_at, 1))
        lit_at = ((jump_at + 4) & ~3) + 4
        if (j.mnemonic, j.op_str) != ("ldr.w", "pc, [pc, #4]") or struct.unpack_from("<I", new, lit_at - va)[0] != at[ln] | 1:
            bad.append((hex(va), "jump", j.mnemonic, j.op_str))
        if kind == "mid" and new[:2] != stock[:2]:
            bad.append((hex(va), "movs r1 changed"))
        if lit_at - va + 4 != 12:
            bad.append((hex(va), "literal outside the window"))
    print(f"wrappers {len(code)} B; sites: {len(c.SITES)}; " + ("ALL OK" if not bad else "FAIL"))
    for b in bad:
        print("  ", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
