#!/usr/bin/env python3
"""DMA / CORE CONTENTION CALIBRATION image (test only, 2026-11-09; NOMASK kernel, 1 slot): what does an
EP DMA word moving to or from an on-chip block cost the core that is using that block, and how long do
the kernel's real DMA jobs take with the core doing nothing? At each call's exit (channel 0 idle), one
experiment, the next of 32 each call (cfg = 8 d + c): one of the kernel's own job chains replayed (its
data is dead there; all the block's jobs must have run, else no DMA) while the core runs a fixed loop.

  d  0 none
     1 a far layer's taps: RCH0, 15 TCBs x 16 + the sentinel, SDRAM -> SB (Block 3)
     2 a layer's row + weights: FCH0, 17 + LB_N words + the sentinel, SDRAM -> LB (Block 0)
     3 a write-back: WCH0, 12 TCBs x 16 + the sequence, OUTBUF (Block 0) -> SDRAM (the same data again)
  c  NLOOP x 4 instructions (fetched from Block 3), each:
     0 register add   1 PM read LB (Block 0)   2 DM read LB (Block 0)
     3 PM read SB+300 (Block 3)   4 DM read SB+300 (Block 3)   5, 6, 7 no loop (the DMA's own duration)

then the channel is polled (DMAC0) until the DMA is done. The NAM output is replaced by eight 2-sample
fields (meter v4 framing, field 0 = +16384):
  1 -(cfg + 1)   2 +loop cycles (DMA start -> loop end)   3 -(DMA start -> done seen, cycles, max 32767)
  4 +polls after the loop (0: the DMA ended inside the loop)   5 0
  6 +1: the chain's sentinel arrived (d 1, 2)   7 0
NAM_CAL_AUDIO=1 keeps the audio (KernelCheck then proves the replayed jobs leave the model alone).
usage: NAM_KERNEL=nam_floor5c (build_floor2.py --cal); nam_floor5c.py --sim | --check
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nam_floor5 as n5  # noqa: E402
from nam_floor5 import *  # noqa: E402,F401,F403

assert n5.P9_MODE == "nomask" and not n5.GATHER and not n5.GATHER_W and n5.WB != "sb"
NLOOP = int(os.environ.get("NAM_CAL_NLOOP", "1000"))
AUDIO = os.environ.get("NAM_CAL_AUDIO") == "1"
BODY = {"r": "R1 = R1 + R2;", "p": "R4 = PM(0, I9);", "d": "R4 = DM(0, I0);"}   # PRB: 0 cfg, 1 CP, 2 DMAC0, 3 loop, 4 done, 5 polls
LOOPS = "".join(f"""cl_{k}: CALL cl_go;
    LCNTR = {NLOOP}, DO cl_l{k} UNTIL LCE;
      {ins}
      {ins}
      {ins}
cl_l{k}: {ins}
    JUMP cl_e;
""" for k, ins in BODY.items())

CAL = ("""x_idle:
    R0 = DM(SAVE + 1);""", """x_idle:
    R0 = DM(PRB + 0);                   // (cal) the next experiment: cfg = 8 d + c
    R0 = R0 + 1;
    R1 = 31;
    R0 = R0 AND R1;
    DM(PRB + 0) = R0;
    R6 = LSHIFT R0 BY -3;               // d
    R1 = 7;
    R0 = R0 AND R1;                     // c
    R4 = (CAL_RCH + TCB_II) & 0x7FFFF;  // d 1: the taps chain
    R5 = DEN_CHEN;
    I5 = CAL_FL0;
    R1 = 2;
    COMP(R6, R1);
    IF LT JUMP cl_s;
    IF GT JUMP cl_w;
    R4 = (CAL_FCH + TCB_II) & 0x7FFFF;  // d 2: row + weights (the first LB_N of the model)
    I5 = CAL_LB;
    R1 = DM(G_SDR);
    R3 = W_OFF;
    R1 = R1 + R3;
    DM(CAL_FCH + TCB_EI + 6) = R1;
    R1 = CAL_LBN;
    DM(CAL_FCH + TCB_IC + 6) = R1;
    JUMP cl_s;
cl_w: R4 = (CAL_WCH + TCB_II) & 0x7FFFF;  // d 3: the last write-back again
    R5 = DEN_CHEN | TRAN;
cl_s: DM(PRB + 1) = R4;
    DM(PRB + 2) = R5;
    R1 = 0;
    DM(0, I5) = R1;                     // the sentinel flag
    R1 = DM(J_DONE);                    // no DMA unless this block's jobs all ran (the chains are filled)
    R3 = NJOBS;
    COMP(R1, R3);
    IF NE R6 = R6 - R6;
    R1 = CAL_LB;                        // the loop operand: LB (c 1, 2) or SB + 300 (c 3, 4)
    R3 = CAL_SB + 300;
    R4 = 3;
    COMP(R0, R4);
    IF GE R1 = PASS R3;
    I0 = R1;
    I9 = R1;
    L0 = 0;
    L9 = 0;
    R0 = PASS R0;
    IF EQ JUMP cl_r;
    R4 = 5;
    COMP(R0, R4);
    IF GE JUMP cl_n;
    R4 = 1;
    R4 = R0 AND R4;
    IF NE JUMP cl_p;
    JUMP cl_d;
cl_n: CALL cl_go;                         // c 5..7: no loop
    JUMP cl_e;
cl_go: R6 = PASS R6;                    // the DMA started (d != 0), the start stamp in R8
    IF EQ JUMP cl_g0;
    R1 = DFLSH;
    DM(DMAC0) = R1;
    R1 = 0;
    DM(CPEP0) = R1;
    R1 = DM(PRB + 2);
    DM(DMAC0) = R1;
    R1 = DM(PRB + 1);
    DM(CPEP0) = R1;
cl_g0: R8 = EMUCLK;
    RTS;
""" + LOOPS + """cl_e: R9 = EMUCLK;
    R7 = 0;
cl_q: R1 = DM(DMAC0);
    R3 = 0x1300000;                     // DMAS | CHS | EXTS (DEN stays set)
    R3 = R1 AND R3;
    IF EQ JUMP cl_qd;
    R7 = R7 + 1;
    R3 = 4000;
    COMP(R7, R3);
    IF LT JUMP cl_q;
cl_qd: R10 = EMUCLK;
    R1 = 0;
    DM(DMAC0) = R1;
    R9 = R9 - R8;
    R10 = R10 - R8;
    R1 = 32767;
    R10 = MIN(R10, R1);
    DM(PRB + 3) = R9;
    DM(PRB + 4) = R10;
    DM(PRB + 5) = R7;
    R1 = 0;
    R11 = DM(0, I5);                    // the sentinel flag, then cleared (no stale MAGIC before LB)
    DM(0, I5) = R1;
""" + ("" if AUDIO else """    // ---- the fields
    F8 = 3.0517578125e-05;
    I11 = B11;
    R0 = 16384;                         // 0
    CALL cl_o;
    R0 = DM(PRB + 0);                   // 1: -(cfg + 1)
    R0 = R0 + 1;
    R0 = -R0;
    CALL cl_o;
    R0 = R9;                            // 2: loop cycles
    CALL cl_o;
    R0 = -R10;                          // 3: -(start -> done)
    CALL cl_o;
    R0 = R7;                            // 4: polls
    CALL cl_o;
    R0 = 0;                             // 5
    PM(I11, M9) = R0;
    PM(I11, M9) = R0;
    R1 = MAGIC;                         // 6: the sentinel
    COMP(R11, R1);
    IF EQ R0 = R0 + 1;
    CALL cl_o;
    R0 = 0;                             // 7
    PM(I11, M9) = R0;
    PM(I11, M9) = R0;
    JUMP cl_x;
cl_o: F0 = FLOAT R0;
    F0 = F0 * F8;
    PM(I11, M9) = R0;
    PM(I11, M9) = R0;
    RTS;
cl_x:
""") + """    R0 = DM(SAVE + 1);""")
_kernel_src = n5.kernel_src


def kernel_src():
    s = _kernel_src()
    assert s.count(CAL[0]) == 1, "x_idle anchor"
    return s.replace(*CAL)


n5.kernel_src = kernel_src
n5.SLOTS = 1
n5.PRB_WORDS = 6
for _k, _v in n5.PLACE.items():             # (1 slot leaves the blocks in other pieces: any block as a fallback)
    n5.PLACE[_k] = list(_v) + [r for r in ("R1", "R2", "R3") if r not in _v]
CAL_NAMES = ["PRB", "W_OFF", "CAL_SB", "CAL_LB", "CAL_LBN", "CAL_FL0", "CAL_RCH", "CAL_FCH", "CAL_WCH"]
_names = n5.names
n5.names = lambda: _names() + [n for n in CAL_NAMES if n not in _names()]
_init = n5.Layout.__init__


def _layout_init(self, *a, **kw):
    _init(self, *a, **kw)
    al = self.alloc
    self.v.update(CAL_SB=al["SB"], CAL_LB=al["LB"], CAL_LBN=n5.LB_N, CAL_FL0=self.flags[0],
                  CAL_RCH=al["RCH0"], CAL_FCH=al["FCH0"], CAL_WCH=al["WCH0"])


n5.Layout.__init__ = _layout_init
build, check, Layout, REGIONS3, RIG_BOUNDS, nf = n5.build, n5.check, n5.Layout, n5.REGIONS3, n5.RIG_BOUNDS, n5.nf


def sim(n=72):
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
    rd, p = r.sim.rd, lay.v["PRB"]
    rows = []
    for b in range(n):
        inst.call(sig, f"A {b}")
        rows.append((rd(p) >> 3, rd(p) & 7, rd(p + 3), rd(p + 4), rd(p + 5)))
    al = lay.alloc
    return rows, {k: hex(al[k]) for k in ("PRB", "SB", "LB", "OUTBUF", "RCH0", "FCH0", "WCH0")}, lay.rg.spare()


if __name__ == "__main__":
    if "--sim" in sys.argv:
        rows, where, spare = sim()
        print(where, spare)
        for x in rows[-32:]:
            print("d %d c %d  loop %5d  done %5d  polls %4d" % x)
    if "--check" in sys.argv:               # 1 slot: KernelCheck's own steps need 2; A alone, 79 blocks (every cfg twice)
        asm, lay = build(inst_bounds=RIG_BOUNDS)
        nm = n5.nm
        nm.Rig, nm.REP = Rig, lay.rep
        k = nm.KernelCheck(asm, lay, n5.nam_lite.placeholder())
        try:
            k.A = k.rig.inst("A", 0)
            k.A.knobs(model=1)
            k.start(k.A, k.w, k.sig("A", 80), "A")
            k.play(k.A, "A", 79)
            print("check: PASS (A alone, 79 blocks bit-exact)")
        except nm.CheckFailed as e:
            print("check: FAIL", e)
