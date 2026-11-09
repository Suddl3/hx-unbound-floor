#!/usr/bin/env python3
"""BURNER variant of nam_floor5i (a test image only, build/EXPERIMENT-DSP): the idle meter plus a
burn loop at the block's exit, so the true spare DSP time can be found by raising the burn until the
audio breaks (overrun), independent of the stock idle word.

  burn = max(0, DM(8, I0) - 0.5) x 300,000 loop passes (the knob at DM(8, I0); 0.5 and below = none)
  field 1 (-cycles / 8) is read after the burn, so it shows the block's cycles including it
  field 6 = FIX(DM(8, I0) x 10000): which preset knob lands in DM(8, I0), and its value

The loop body is 3 instructions (no short-loop penalty), ~3 cycles a pass; field 1 calibrates it.
usage: NAM_KERNEL=nam_floor5b (floor/build_dsp_meter.py --burn)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nam_floor5 as n5  # noqa: E402
import nam_floor5i as mi  # noqa: E402,F401  (installs the meter + idle patches into n5.kernel_src)
from nam_floor5i import *  # noqa: E402,F401,F403

BURN_KNOB = 8

OLD_START = "    R0 = EMUCLK;                        // (meter v4) eight 2-sample fields, signs + - + - ...\n"
NEW_START = f"""    R0 = DM(SAVE + 31);                 // (burner) the caller's I0
    I4 = R0;
    F0 = DM({BURN_KNOB}, I4);                    // burn = max(0, knob - 0.5) x 300,000 passes
    F1 = 0.5;
    F0 = F0 - F1;
    F1 = 300000.0;
    F0 = F0 * F1;
    R0 = FIX F0;
    R1 = 1;
    R0 = MAX(R0, R1);
    LCNTR = R0, DO b_burn UNTIL LCE;
      NOP;
      NOP;
b_burn: NOP;
""" + OLD_START

OLD6 = "    R6 = R5 AND R8;                     // 6: DM(7, I0), low 15 bits (the Model knob as an int)\n"
NEW6 = f"""    F6 = DM({BURN_KNOB}, I4);                    // 6: (burner) the burn knob x 10000
    F9 = 10000.0;
    F6 = F6 * F9;
    R6 = FIX F6;
    R6 = R6 AND R8;
"""

_idle_src = n5.kernel_src


def kernel_src():
    src = _idle_src()
    for a, b in ((OLD_START, NEW_START), (OLD6, NEW6)):
        assert src.count(a) == 1, a[:60]
        src = src.replace(a, b)
    return src


n5.kernel_src = kernel_src
build, check, Layout, REGIONS3, RIG_BOUNDS, nf = n5.build, n5.check, n5.Layout, n5.REGIONS3, n5.RIG_BOUNDS, n5.nf
