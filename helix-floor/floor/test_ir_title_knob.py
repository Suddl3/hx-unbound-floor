"""The knob-K title path (ir_title.build knob_pids) run in unicorn (Cortex-M Thumb), with the two stock
calls stubbed: CTX_FN returns a context in r0, PARAM_FN checks its arguments and writes the knob's
value record (a type byte, then the 4 value bytes) at r3. Also: the stock IR Single name branch still
has the instruction pattern the cave copies (Floor Entry 0), and caveB's knob redraw.
usage: test_ir_title_knob.py <entry0.bin>   (needs: pip install unicorn)"""
import struct
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upstream import TOOLS  # noqa: E402
sys.path.insert(0, TOOLS)
import capstone  # noqa: E402
import unicorn as U  # noqa: E402
from unicorn import arm_const as A  # noqa: E402
import ir_title as t  # noqa: E402

BASE, BLK, STK = 0x1001F000, 0x20300000, 0x20400000
PID, CTX = 555, 0xC0C0C0C0


def run(cave, pid, value=None, cat=12, knob_changed=6, raw_bits=None):
    code, ca, cb = t.build(BASE, [], [PID], 6)
    mu = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_THUMB | U.UC_MODE_MCLASS)
    for m in (BASE & ~0xFFF, BLK, STK, 0x28000000):
        mu.mem_map(m, 0x200000 if m == 0x28000000 else 0x10000)
    mu.mem_write(BASE, code)
    mu.mem_write(BLK + 1, struct.pack("<I", pid))
    mu.mem_write(BLK + 12, bytes([cat, 0]))
    sp = STK + 0x8000
    mu.reg_write(A.UC_ARM_REG_SP, sp)
    mu.mem_write(sp + t.B_KNOB_SP, struct.pack("<I", knob_changed))
    for r in (A.UC_ARM_REG_R4, A.UC_ARM_REG_R0, A.UC_ARM_REG_R1):
        mu.reg_write(r, 0x55)
    mu.reg_write(A.UC_ARM_REG_R6 if cave == "A" else A.UC_ARM_REG_R5, BLK)
    if cave == "A":
        mu.reg_write(A.UC_ARM_REG_R5, 7)                    # the block slot
    calls, exits = [], set()
    targets = {t.IR_PATH, t.NON_IR, t.IR_NAME, t.B_RET, t.B_IR, t.AFTER_READ, t.EMPTY, t.B_REDRAW}
    for v in targets | {t.CTX_FN, t.PARAM_FN}:
        mu.mem_write(v, b"\x70\x47")                        # bx lr (stubs; exits are caught first)

    def hook(uc, addr, size, _):
        if addr == t.CTX_FN:
            calls.append(("ctx", uc.reg_read(A.UC_ARM_REG_R0), uc.reg_read(A.UC_ARM_REG_R1)))
            uc.reg_write(A.UC_ARM_REG_R0, CTX)
        elif addr == t.PARAM_FN:
            r = [uc.reg_read(x) for x in (A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3)]
            q = struct.unpack("<iiB", bytes(uc.mem_read(r[2], 9)))
            calls.append(("param", r[0], r[1], r[2] - sp, r[3] - sp, q))
            bits = raw_bits if raw_bits is not None else struct.unpack("<I", struct.pack("<f", value))[0]
            uc.mem_write(r[3], b"\x03" + struct.pack("<I", bits))
        elif addr in targets:
            exits.add(addr)
            uc.emu_stop()
    mu.hook_add(U.UC_HOOK_CODE, hook)
    mu.emu_start((ca if cave == "A" else cb) | 1, 0, count=500)
    out = struct.unpack("<I", bytes(mu.mem_read(sp + 0x19, 4)))[0]
    return exits.pop() if len(exits) == 1 else exits, calls, out, mu.reg_read(A.UC_ARM_REG_R4), \
        mu.reg_read(A.UC_ARM_REG_SP) - sp


def stock_pattern(e0_path):
    """The stock branch at IR_NAME: q = {-2, 0} at sp+0x38, r4 at sp+0x40, CTX_FN, r3 = sp+0x18,
    r1 = r5, r2 = sp+0x38, PARAM_FN, then AFTER_READ reads sp+0x1c / sp+0x18."""
    e0 = open(e0_path, "rb").read()
    segs, off = [], 0x34
    for _ in range(struct.unpack_from("<I", e0, 16)[0]):
        slen, dst, nxt = struct.unpack_from("<3I", e0, off)
        segs.append((off + 12, slen, dst)); off = nxt
    fo = next(p + t.IR_NAME - d for p, l, d in segs if d <= t.IR_NAME < d + l)
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    got = [(i.address, i.mnemonic, i.op_str) for i in md.disasm(e0[fo:fo + 0x30], t.IR_NAME)][:12]
    want = [(0x280AC8EE, "mvn", "r2, #1"), (0x280AC8F2, "movs", "r3, #0"), (0x280AC8F4, "strd", "r2, r3, [sp, #0x38]"),
            (0x280AC8F8, "strb.w", "r4, [sp, #0x40]"), (0x280AC8FC, "bl", "#0x%x" % t.CTX_FN),
            (0x280AC900, "add", "r3, sp, #0x18"), (0x280AC902, "mov", "r1, r5"), (0x280AC904, "add", "r2, sp, #0x38"),
            (0x280AC906, "bl", "#0x%x" % t.PARAM_FN), (0x280AC90A, "ldrb.w", "r0, [sp, #0x1c]"),
            (0x280AC90E, "ldr", "r3, [sp, #0x18]"), (0x280AC910, "lsls", "r0, r0, #0x18")]
    return got == want, got


def main():
    ok, got = stock_pattern(sys.argv[1])
    cases = [("stock IR Single name branch as the cave assumes", ok, True)]
    for v, want_to, want_int in ((50.0, t.AFTER_READ, 50), (1.0, t.AFTER_READ, 1), (128.0, t.AFTER_READ, 128),
                                 (127.9, t.AFTER_READ, 127), (0.0, t.EMPTY, None), (0.5, t.EMPTY, None),
                                 (129.0, t.EMPTY, None), (1000.0, t.EMPTY, None), (-3.0, t.EMPTY, None)):
        to, calls, out, r4, dsp = run("A", PID, v)
        good = to == want_to and r4 == 0 and dsp == 0 and calls == [
            ("ctx", 0x55, 0x55), ("param", CTX, 7, 0x38, 0x18, (-2, 6, 0))] and (want_int is None or out == want_int)
        cases.append((f"A: 555, Model {v} -> {'name ' + str(want_int) if want_int else 'EMPTY'}", good, True))
    cases.append(("A: 555, NaN bits -> EMPTY", run("A", PID, raw_bits=0x7FC00000)[0], t.EMPTY))
    cases.append(("A: other amp -> stock", run("A", 77, 50.0)[0], t.NON_IR))
    cases.append(("A: 555 in Amp+Cab -> stock", run("A", PID, 50.0, cat=11)[0], t.NON_IR))
    cases.append(("A: IR block -> IR path", run("A", 5, 50.0, cat=15)[0], t.IR_PATH))
    cases.append(("B: 555, knob 6 changed -> redraw", run("B", PID, knob_changed=6)[0], t.B_REDRAW))
    cases.append(("B: 555, knob 0 changed -> return", run("B", PID, knob_changed=0)[0], t.B_RET))
    cases.append(("B: other amp -> return", run("B", 77)[0], t.B_RET))
    cases.append(("B: IR block -> IR redraw", run("B", 5, cat=15)[0], t.B_IR))
    bad = [c for c in cases if c[1] != c[2]]
    for name, g, w in cases:
        print(f"{'ok ' if g == w else 'BAD'} {name}" + ("" if g == w else f": {g} != {w}"))
    if not ok:
        print(got)
    print("PASS" if not bad else "FAIL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
