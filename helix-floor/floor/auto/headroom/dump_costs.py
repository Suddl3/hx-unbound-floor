"""Dump the Floor's Table 1 (model -> preset id, DSP cost) joined with Table 2 short names.
usage: dump_costs.py <floor repo helix-floor/floor dir> <stock Entry 0 (sw4)> <out.csv>"""


def main():
    import csv
    import struct
    import sys

    sys.path.insert(0, sys.argv[1])
    import stage_main as sm  # noqa: E402

    e0 = open(sys.argv[2], "rb").read()
    im = sm.Image(e0)
    pa = sm.pa
    tab1 = im.u32(sm.TAB1_BASE_PTRS[0])
    n1 = pa._decode_thumb_movw(im.rd(sm.TAB1_CNT_INSN, 4))[1]
    rows = [struct.unpack_from('<IHHI', im.rd(tab1 + 12 * i, 12)) for i in range(n1)]
    tab2 = im.u32(sm.TAB2_BASE_PTR)
    n2 = pa._decode_thumb_movw(im.rd(sm.TAB2_CNT_INSN, 4))[1]
    names = {}
    for i in range(n2):
        r = im.rd(tab2 + 44 * i, 44)
        names[struct.unpack_from('<I', r, 0)[0]] = r[4:20].split(b'\0')[0].decode('latin1')
    with open(sys.argv[3], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ni", "preset_id", "cost", "name"])
        for ni, pid, _, cost in sorted(rows, key=lambda r: -r[3]):
            w.writerow([hex(ni), pid, cost, names.get(ni, "")])
    print(n1, "rows")


if __name__ == "__main__":
    main()
