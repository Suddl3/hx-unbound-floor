"""List every block model used in a Floor backup, with its DSP price, heaviest first.
usage: scan_blocks.py <hx dir with hx_ctl.py> <backup dir> <costs.csv> [blob ...]"""
import csv
import glob
import os
import sys

sys.path.insert(0, sys.argv[1])
import hx_ctl as hc  # noqa: E402

costs = {int(r["preset_id"]): (int(r["cost"]), r["name"]) for r in csv.DictReader(open(sys.argv[3]))}
files = sorted(glob.glob(os.path.join(sys.argv[2], "setlist*", "*.bin"))) + sys.argv[4:]
seen = {}
for f in files:
    try:
        magic, sec = hc.decode_preset(open(f, "rb").read())
    except Exception as e:  # noqa: BLE001
        print("skip", f, e)
        continue
    for b in hc.summarize(sec):
        mid = b["model_id"]
        if b["type"] == hc.BLOCK_TYPE and mid is not None and mid not in seen:
            seen[mid] = (f, b["path"], b["slot"], b["kind"])
rows = sorted(seen.items(), key=lambda kv: -costs.get(kv[0], (0, ""))[0])
for mid, (f, p, s, k) in rows:
    c, n = costs.get(mid, (0, "?"))
    print(f"{c:5d}  {mid:4d}  {n:18s} kind {k}  {os.path.relpath(f, sys.argv[2])} path {p} slot {s}")
