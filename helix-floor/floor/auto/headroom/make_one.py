"""One test blob from soak_eb_2nam.bin: optionally drop the 2nd NAM, add blocks copied from backup presets.
usage: make_one.py <hx dir> <base blob> <backup dir> <out> [--one-nam] <src.bin:path:slot> ..."""
import copy
import os
import sys

sys.path.insert(0, sys.argv[1])
import hx_ctl as hc  # noqa: E402

base = open(sys.argv[2], "rb").read()
bk, out, args = sys.argv[3], sys.argv[4], sys.argv[5:]
magic, sec = hc.decode_preset(base)
bl = hc.blocks(sec)
empty = copy.deepcopy(bl[hc.slot_index(0, 2)])
assert empty.get(20) is None
if "--one-nam" in args:
    args.remove("--one-nam")
    bl[hc.slot_index(0, 1)] = copy.deepcopy(empty)
pos = 2
for a in args:
    f, p, s = a.split(":")
    _, s2 = hc.decode_preset(open(os.path.join(bk, f), "rb").read())
    blk = hc.blocks(s2)[hc.slot_index(int(p), int(s))]
    bl[hc.slot_index(0, pos)] = copy.deepcopy(blk)
    print(f"path 0 slot {pos} <- model {blk[20][24][25]} kind {blk[20][9]}")
    pos += 1
open(out, "wb").write(hc.encode_preset(magic, sec, like=base))
print("models:", [b["model_id"] for b in hc.summarize(hc.decode_preset(open(out, "rb").read())[1])])
