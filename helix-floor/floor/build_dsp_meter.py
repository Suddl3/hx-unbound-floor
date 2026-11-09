#!/usr/bin/env python3
"""EXPERIMENT (TODO "Free DSP by making always-on items switchable", step 1): the idle-meter image.
build_floor2.py --meter with the kernel nam_floor5i (meter v4, field 4 = the DSP's idle % x 100).
Everything, intermediates included, stays in build/EXPERIMENT-DSP. A test image: the NAM block plays
number frames, not sound. Read with floor/auto/idle48.py.

usage: build_dsp_meter.py <stock Helix_Floor_v3.80.0_0x7d01f5efb.hxf> [--burn]
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from upstream import TOOLS  # noqa: E402
import build_floor as bf  # noqa: E402


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    stock = os.path.abspath(argv[0])
    assert hashlib.md5(open(stock, "rb").read()).hexdigest() == bf.STOCK_MD5, "not the stock Floor 3.80.0 file"
    b = os.path.join(bf.ROOT, "build", "EXPERIMENT-DSP")
    burn = "--burn" in argv                         # the burner variant (nam_floor5b)
    out = os.path.join(b, "Helix_Floor_v3.80.0_NAM2_BURNER.hxf" if burn else "Helix_Floor_v3.80.0_NAM2_IDLEMETER.hxf")
    os.makedirs(b, exist_ok=True)
    s0, s1, s2, s3, s4 = (os.path.join(b, f"dsp_{n}.l6ia") for n in ("stock", "s1", "s2", "s3", "s4"))
    bf.run(os.path.join(TOOLS, "hxf.py"), "unpack", stock, s0)
    os.environ["NAM_DIAG"] = "1"                     # (no KernelCheck: the output is the meter)
    os.environ["NAM_KERNEL"], os.environ["NAM_MAX_BLOCKS"] = ("nam_floor5b" if burn else "nam_floor5i"), "16"
    os.environ["NAM_MAX_STEADY"] = "60000"
    bf.run(os.path.join(HERE, "stage_slots2.py"), s0, s1)
    bf.run(os.path.join(HERE, "stage_model.py"), s1, s2)
    bf.run(os.path.join(HERE, "stage_kernel.py"), s2, s3)
    bf.run(os.path.join(HERE, "stage_main.py"), s3, s4)
    del os.environ["NAM_KERNEL"], os.environ["NAM_MAX_BLOCKS"], os.environ["NAM_DIAG"]
    v = bf.run(os.path.join(TOOLS, "l6ia_verify.py"), s4)
    assert "ALL OK" in v
    bf.slots(s4)
    bf.run(os.path.join(HERE, "test_arm_guards.py"))
    bf.run(os.path.join(HERE, "test_ir_title.py"))
    rep = bf.report(s0, s4)
    print(rep)
    open(os.path.join(b, "CHANGES_IDLEMETER.txt"), "w").write(rep + "\n")
    bf.run(os.path.join(HERE, "floor_hxf.py"), "pack", s4, out, "--donor", stock)
    for f in (s1, s2, s3):
        os.remove(f)
    print(f"\nDone: {out}\nTest image. MD5 {hashlib.md5(open(out, 'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()
