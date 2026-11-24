#!/usr/bin/env python3
"""Build stage (NAM_DSP_OPT=1 in build_floor2.py): nocaseguy's bit-exact DSP rewrites at the Helix Floor's Entry 2 addresses.

usage: stage_dsp_opt.py IN.l6ia OUT.l6ia PORT.json [--only a,b] [--without a,b]

Runs after the NAM kernel is in Entry 2 (the rewrites touch other routines). Each group's stock bytes are hashed in the image first
(dsp_opt_port.apply), the new parcels are written in place, Entry 2 keeps its length. See dsp_opt_port.py and DSP_OPT.md.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from upstream import TOOLS  # noqa: E402
sys.path.insert(0, TOOLS)
import l6ia  # noqa: E402
import dsp_opt_port  # noqa: E402


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        sys.exit(__doc__)
    src, out, port_file = a[0], a[1], a[2]

    def opt(name):
        return set(a[a.index(name) + 1].split(",")) if name in a else None
    data = open(src, "rb").read()
    e = l6ia.parse(data)[2]
    e2 = data[e["payload_off"]: e["payload_off"] + e["payload_len"]]
    port = json.load(open(port_file, encoding="utf-8"))
    new, groups, parcels = dsp_opt_port.apply(e2, port, opt("--only"), opt("--without"))
    assert len(new) == len(e2), "Entry 2 changed length"
    img, _, _ = l6ia.rebuild_archive(data, {2: l6ia.swap32(new)})
    open(out, "wb").write(img)
    print(f"DSP rewrites (nocaseguy, bit-exact): {groups} groups, {parcels} parcels changed in place in Entry 2 ({len(e2):#x} bytes, unchanged length)")


if __name__ == "__main__":
    main()
