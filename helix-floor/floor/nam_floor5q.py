#!/usr/bin/env python3
"""PROFILE 2 (a test image only, 2026-11-08): the call's compute split by section, after profile 1
(nam_floor5p) showed ~40K of the unit's 52K cycles are compute, not DMA waits. Meter v4 framing
(field 0 = +16384, signs + - + - ...), fields in cycles / 8:

  1  -total                      the call (meter v4's field 1)
  2  +entry -> jobs              setup: slot claim, guards, state, the block's DMA jobs queued... up to the jobs
  3  -jobs -> layers             the DMA jobs started, the input stage (to `F5 = 0.01; S5 = 0.01;`)
  4  +layers -> head             the 23 layers (incl. their waits, fcopy, n_put, pumps)
  5  -head -> mix                the head (16 taps)
  6  +mix -> end wait            the mix and output
  7  -pair loops                 the layers' 8-pair MAC loops together (the core math)

Stamps save R0 in PRB + 7, read EMUCLK through R0 and restore it (a direct `DM(x) = EMUCLK` store
misbehaved in the simulator, so it is not used); the pair-loop sum adds after each loop with R0/R1
(dead there). Profile 1's waits (lwait 9.2K, fwait 2.9K on the unit) sit inside field 4.
usage: NAM_KERNEL=nam_floor5q (build_floor2.py --profile2); nam_floor5q.py --sim
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nam_floor5 as n5  # noqa: E402
from nam_floor5 import *  # noqa: E402,F401,F403
import nam_floor5m as n5m  # noqa: E402

assert n5.P9_MODE == "nomask"
n5.PRB_WORDS = 8                   # PRB+0..4: stamps jobs, layers, head, mix, end; +5 pair start; +6 pair sum; +7 R0 save
ANCHORS = [("    // ---- the DMA jobs of this block, then the model\n", 0),
           ("    F5 = 0.01; S5 = 0.01;", 1),
           ("    // ---- the head: 16 taps", 2),
           ("    // ---- the mix: the model", 3),
           ("    // ---- the block's DMA jobs all done", 4)]
PAIR_START = "      I4 = IN;\n      BIT SET MODE1 PEYEN | BDCST9;\n      NOP;\n      LCNTR = 8, DO n_pair UNTIL LCE;\n"
PAIR_END = "n_pair: DM(I3, M6) = F13;\n      BIT CLR MODE1 PEYEN | BDCST9;\n      I4 = R15;\n      L0 = 0;\n      L1 = 0;\n      L2 = 0;\n"

FIELDS = """    R0 = 16384;                         // (profile 2) 0: calibration
    R9 = DM(DCNT);
    R2 = DM(PRB + 0);                   // 2: entry -> jobs
    R2 = R2 - R9;
    R2 = LSHIFT R2 BY -3;
    R9 = DM(PRB + 0);
    R3 = DM(PRB + 1);                   // 3: -(jobs -> layers)
    R3 = R3 - R9;
    R3 = LSHIFT R3 BY -3;
    R3 = -R3;
    R9 = DM(PRB + 1);
    R4 = DM(PRB + 2);                   // 4: layers -> head
    R4 = R4 - R9;
    R4 = LSHIFT R4 BY -3;
    R9 = DM(PRB + 2);
    R5 = DM(PRB + 3);                   // 5: -(head -> mix)
    R5 = R5 - R9;
    R5 = LSHIFT R5 BY -3;
    R5 = -R5;
    R9 = DM(PRB + 3);
    R6 = DM(PRB + 4);                   // 6: mix -> end wait
    R6 = R6 - R9;
    R6 = LSHIFT R6 BY -3;
    R7 = DM(PRB + 6);                   // 7: -(pair loops)
    R7 = LSHIFT R7 BY -3;
    R7 = -R7;
"""


def stamp(k, ind="    "):
    return (f"{ind}DM(PRB + 7) = R0;                 // (profile 2) stamp {k}\n{ind}R0 = EMUCLK;\n"
            f"{ind}DM(PRB + {k}) = R0;\n{ind}R0 = DM(PRB + 7);\n")


def kernel_src():
    src = n5m.kernel_src()
    a = src.index("    R0 = 16384;                         // 0: calibration")
    b = src.index("    F8 = 3.0517578125e-05;", a)
    src = src[:a] + FIELDS + src[b:]
    e = "    DM(DCNT) = R0;\n"
    assert src.count(e) == 1
    src = src.replace(e, e + "    R0 = 0;                             // (profile 2) this call's pair-loop sum\n"
                      "    DM(PRB + 6) = R0;\n")
    for text, k in ANCHORS:
        assert src.count(text) == 1, text
        src = src.replace(text, stamp(k) + text)
    assert src.count(PAIR_START) == 1 and src.count(PAIR_END) == 1
    src = src.replace(PAIR_START, stamp(5, "      ") + PAIR_START)
    src = src.replace(PAIR_END, PAIR_END + """      R0 = EMUCLK;                      // (profile 2) its time, summed
      R1 = DM(PRB + 5);
      R0 = R0 - R1;
      R1 = DM(PRB + 6);
      R1 = R1 + R0;
      DM(PRB + 6) = R1;
""")
    return src


n5.kernel_src = kernel_src
_names = n5.names
n5.names = lambda: _names() + ([] if "PRB" in _names() else ["PRB"])
build, check, Layout, REGIONS3, RIG_BOUNDS, nf = n5.build, n5.check, n5.Layout, n5.REGIONS3, n5.RIG_BOUNDS, n5.nf


def sim(n=24):
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
    rd = r.sim.rd
    p, d = lay.v["PRB"], lay.v["DCNT"]
    t = [rd(d)] + [rd(p + k) for k in range(5)]
    names = ["entry->jobs", "jobs->layers", "layers->head", "head->mix", "mix->end"]
    out = {nm_: t[i + 1] - t[i] for i, nm_ in enumerate(names)}
    out["pair loops"] = rd(p + 6)
    return out, r.cycles[-1][1]


if __name__ == "__main__":
    if "--sim" in sys.argv:
        print(sim())
