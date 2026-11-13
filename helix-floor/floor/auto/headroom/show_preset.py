"""Print a preset blob's blocks with DSP prices. usage: show_preset.py <hx dir> <costs.csv> <blob>"""


def main():
    import csv
    import sys

    sys.path.insert(0, sys.argv[1])
    import hx_ctl as hc  # noqa: E402

    costs = {int(r["preset_id"]): (int(r["cost"]), r["name"]) for r in csv.DictReader(open(sys.argv[2]))}
    costs[380] = (0, "NAM A2 Lite")
    magic, sec = hc.decode_preset(open(sys.argv[3], "rb").read())
    tot = {0: 0, 1: 0}
    for b in hc.summarize(sec):
        c, n = costs.get(b["model_id"], (0, "?"))
        tot[b["path"]] += c
        print(f"path {b['path']} slot {b['slot']}: type {b['type']} model {b['model_id']} {n} ({c}) "
              f"kind {b['kind']} {'on' if b['enabled'] else 'off'}")
    print("non-NAM block price per path:", tot)


if __name__ == "__main__":
    main()
