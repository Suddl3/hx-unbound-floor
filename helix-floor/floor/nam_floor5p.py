#!/usr/bin/env python3
"""PROFILE variant of nam_floor5 (a test image only, 2026-11-08: where does a NAM call's time go on
the unit?). Like the meter (nam_floor5m), every NAM block plays numbers instead of its output: eight
fields of two samples, signs + - + - + - + -, each n / 32768 (meter v4 framing, field 0 = +16384):

  0  +16384                  calibration (`meter_read.py --v4` divides every field by field 0 / 16384)
  1  -(total cycles / 8)     EMUCLK, the call's start to its exit (as meter v4's field 1)
  2  +(lwait / 8)            in lwait: a layer waits for its row + weights (pump calls inside)
  3  -(fwait / 8)            in fwait: a far layer waits for its taps (pump calls inside)
  4  +(head wait / 8)        n_hw0..n_hw1: the head's weights
  5  -(end wait / 8)         n_ew..n_ewd: the block's last DMA jobs (write-backs)
  6  +(pump / 8)             every pump call (also the ones inside the waits above)
  7  -polls                  REP R_POLLS (lwait/fwait/end wait loop turns)

compute ~= total - lwait - fwait - head - end - (pump outside the waits). Each timed routine gets a
wrapper (EMUCLK before and after a CALL to the original body; R0, R1 only, which every one of them
clobbers anyway), so the image runs a little slower than the release (~12 cycles a wrapped call).
One NAM slot per DSP (SLOTS = 1, as the meter). No KernelCheck (the output is the profile).

usage: NAM_KERNEL=nam_floor5p (build_floor2.py --profile);  nam_floor5p.py --sim: the fields in the
simulator (two instances, steady calls)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nam_floor5 as n5  # noqa: E402
from nam_floor5 import *  # noqa: E402,F401,F403
import nam_floor5m as n5m  # noqa: E402

assert n5.P9_MODE == "nomask"
n5.PRB_WORDS = 16                  # PRB + 2k: section k's start stamp, PRB + 2k + 1: its sum this call
SECTIONS = ["lwait", "fwait", "head", "end", "pump"]


def acc(k):
    """The section's time since its stamp, added to its sum (R0, R1)."""
    return f"""    R0 = EMUCLK;                        // (profile) {SECTIONS[k]}
    R1 = DM(PRB + {2 * k});
    R0 = R0 - R1;
    R1 = DM(PRB + {2 * k + 1});
    R1 = R1 + R0;
    DM(PRB + {2 * k + 1}) = R1;
"""


def stamp(k):
    return f"""    R0 = EMUCLK;                        // (profile) {SECTIONS[k]} starts
    DM(PRB + {2 * k}) = R0;
"""


def wrap(src, label, k):
    """`label:` becomes a timing wrapper around a CALL to the original body (`label`_i)."""
    a = f"\n{label}:\n"
    assert src.count(a) == 1, label
    return src.replace(a, f"\n{label}:\n" + stamp(k) + f"    CALL {label}_i;\n" + acc(k) + f"    RTS;\n{label}_i:\n")


FIELDS = """    R0 = 16384;                         // (profile) 0: calibration
    R2 = DM(PRB + 1);                   // 2: lwait
    R2 = LSHIFT R2 BY -3;
    R3 = DM(PRB + 3);                   // 3: -fwait
    R3 = LSHIFT R3 BY -3;
    R3 = -R3;
    R4 = DM(PRB + 5);                   // 4: head wait
    R4 = LSHIFT R4 BY -3;
    R5 = DM(PRB + 7);                   // 5: -end wait
    R5 = LSHIFT R5 BY -3;
    R5 = -R5;
    R6 = DM(PRB + 9);                   // 6: pump
    R6 = LSHIFT R6 BY -3;
    R7 = DM(REP + R_POLLS);             // 7: -polls
    R7 = -R7;
"""


def kernel_src():
    src = n5m.kernel_src()                # the meter: its entry stamp (DCNT) and its eight-field output
    a = src.index("    R0 = 16384;                         // 0: calibration")
    b = src.index("    F8 = 3.0517578125e-05;", a)
    src = src[:a] + FIELDS + src[b:]
    # fields 2..7 replaced; field 1 (total) stays meter v4's: R1 = -(EMUCLK - DCNT) / 8
    assert "R1 = -R1;                           // 1: -cycles / 8" in src
    zero = "".join(f"    DM(PRB + {2 * k + 1}) = R0;\n" for k in range(len(SECTIONS)))
    e = "    DM(DCNT) = R0;\n"
    assert src.count(e) == 1
    src = src.replace(e, e + "    R0 = 0;                             // (profile) this call's sums\n" + zero)
    for k, label in ((0, "lwait"), (1, "fwait"), (4, "pump")):
        src = wrap(src, label, k)
    h0 = "    R9 = POLLMAX;                       // the head's weights (into LB1 after layer 21): wait,\n"
    assert src.count(h0) == 1 and src.count("n_hw1:\n") == 1
    src = src.replace(h0, stamp(2) + h0).replace("n_hw1:\n", "n_hw1:\n" + acc(2))
    e0 = "    R9 = POLLMAX;\nn_ew: CALL pump;\n"
    assert src.count(e0) == 1 and src.count("n_ewd:\n") == 1
    src = src.replace(e0, stamp(3) + e0).replace("n_ewd:\n", "n_ewd:\n" + acc(3))
    return src


n5.kernel_src = kernel_src
_names = n5.names
n5.names = lambda: _names() + ([] if "PRB" in _names() else ["PRB"])
build, check, Layout, REGIONS3, RIG_BOUNDS, nf = n5.build, n5.check, n5.Layout, n5.REGIONS3, n5.RIG_BOUNDS, n5.nf


def _sim_emuclk():
    """ssim keeps EMUCLK at 0; for the profile in the simulator it reads the sim's cycle count."""
    import ssim
    code = ssim.U_TCOUNT - 6                    # EMUCLK = UREG 0x69 (sasm's table: ... LCNTR 0x68, EMUCLK)
    import sasm
    assert sasm.UREG_CODE["EMUCLK"] == code
    get0 = ssim.Sim.get if hasattr(ssim, "Sim") else None
    cls = next(c for c in vars(ssim).values() if isinstance(c, type) and hasattr(c, "get") and hasattr(c, "set")
               and "cycles" in getattr(c.__init__, "__code__", type("x", (), {"co_names": ()})).co_names)
    g0 = cls.get
    cls.get = lambda self, c: self.cycles & 0xFFFFFFFF if c == code else g0(self, c)


def sim(n=24):
    """Run the profile image in the simulator; return the last call's sums and the sim's cycle count."""
    import simclk
    simclk.enable()
    asm, lay = build(inst_bounds=RIG_BOUNDS)
    nm = n5.nm
    nm.REP = lay.rep
    r = Rig(asm, lay)
    w = n5.nam_lite.placeholder()
    nm.set_ir(r.sim, 1, n5.nam_lite.ir_samples(w, None))
    inst = r.inst("A", 0)
    inst.knobs(model=1)
    sig = [nf.ssim_f2b(0.2 * ((k * 7) % 11 - 5) / 5) for k in range(16)]
    for b in range(n):
        inst.call(sig, f"A {b}")
    prb = lay.v["PRB"]
    sums = {s: r.sim.rd(prb + 2 * k + 1) for k, s in enumerate(SECTIONS)}
    return sums, r.cycles[-1][1], r.rep()[nm.REPW["R_POLLS"]] if "R_POLLS" in nm.REPW else None


if __name__ == "__main__":
    if "--sim" in sys.argv:
        print(sim())
