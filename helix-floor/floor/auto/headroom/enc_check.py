"""Is encode_preset(decode_preset(x)) without like= byte-identical? And the source block as stored.
usage: enc_check.py <hx dir> <blob> [<source blob> <path> <slot>]"""
import sys

sys.path.insert(0, sys.argv[1])
import hx_ctl as hc  # noqa: E402

b = open(sys.argv[2], "rb").read()
m, s = hc.decode_preset(b)
print("plain re-encode identical:", hc.encode_preset(m, s) == b, "| with like:", hc.encode_preset(m, s, like=b) == b)
print("2NAM slot 0 block keys:", sorted(hc.blocks(s)[hc.slot_index(0, 0)][20].keys()))
print("2NAM empty slot 2:", hc.blocks(s)[hc.slot_index(0, 2)])
if len(sys.argv) > 3:
    m2, s2 = hc.decode_preset(open(sys.argv[3], "rb").read())
    blk = hc.blocks(s2)[hc.slot_index(int(sys.argv[4]), int(sys.argv[5]))]
    print("source block:", {k: (v if k != 20 else {kk: vv for kk, vv in v.items() if kk != 11}) for k, v in blk.items()})
print("top-level sec[0] keys:", sorted(s[0].keys()))
