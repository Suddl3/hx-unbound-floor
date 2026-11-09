#!/usr/bin/env python3
"""IDLE METER variant of nam_floor5m (a test image only, build/EXPERIMENT-DSP): meter v4's frame,
but field 4 plays the DSP's own load word instead of DM(3, I0):

  4  +FIX(idle % x 100)    the stock idle word of the DSP running this block (Floor DM 0xC3B9B)

Upstream's Stomp word is DM 0xC2FD5 (a float, idle % of the block: 100% = ~150.9K cycles,
docs/research/KIT_UNIT_MEASUREMENTS.md). The Floor's address was found by matching both Stomp
code sites that touch 0xC2FD5 (Entry 2 bytes 0x1ed44, 0x267f6) to Floor code with the same
neighbours (Floor bytes 0x1f322, 0x27fda): both name 0xC3B9B, no other reference.

Read with `floor/auto/idle48.py` (ASIO 48 kHz): load % = 100 - field 4 / 100.
Load includes the meter block itself (one NAM, ~35%): compare settings by the difference.

usage: NAM_KERNEL=nam_floor5i (floor/build_dsp_meter.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nam_floor5 as n5  # noqa: E402
import nam_floor5m as m  # noqa: E402,F401  (installs the meter patches into n5.kernel_src)
from nam_floor5m import *  # noqa: E402,F401,F403

IDLE_WORD = 0xC3B9B                      # Floor (Stomp: 0xC2FD5)

OLD4 = """    R4 = DM(3, I4);                     // 4: DM(3, I0), low 15 bits (stock blocks: 1)
    R4 = R4 AND R8;
"""
NEW4 = f"""    F4 = DM({IDLE_WORD:#X});                   // 4: the DSP's idle % x 100 (stock idle word)
    F9 = 100.0;
    F4 = F4 * F9;
    R4 = FIX F4;
    R4 = R4 AND R8;
"""

_meter_src = n5.kernel_src


def kernel_src():
    src = _meter_src()
    assert src.count(OLD4) == 1, "meter field 4 not found"
    return src.replace(OLD4, NEW4)


n5.kernel_src = kernel_src
build, check, Layout, REGIONS3, RIG_BOUNDS, nf = n5.build, n5.check, n5.Layout, n5.REGIONS3, n5.RIG_BOUNDS, n5.nf
