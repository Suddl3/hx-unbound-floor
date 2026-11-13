"""List every model in a stock Helix Floor firmware: internal name, category, display names.

usage: dump_models.py FIRMWARE.hxf [-o models_stock.csv]
Reads your own firmware file; writes the input draft_names.py takes as --stock:
  internal,category,subcategory,db_display,table2_short,browser,browser_cats
db_display = model database display name; table2_short = main program's 16-byte short name; browser = the
add-block list name(s), '|'-joined when a model is listed more than once; browser_cats = their category numbers."""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FLOOR = os.path.join(HERE, "..", "floor")
sys.path.insert(0, FLOOR)
from upstream import TOOLS  # noqa: E402

sys.path.insert(0, TOOLS)
import patch_amp as pa  # noqa: E402
import stage_main as sm  # noqa: E402


def cstr(b):
    return b.split(b"\0")[0].decode("latin1")


def dump(path):
    data, _ = pa.load_l6ia_from_any(path)
    db = pa.parse_entry3_full(pa.get_entry_swapped(data, sm.E_DB))
    im = sm.Image(pa.get_entry_swapped(data, sm.E_MAIN))
    tab2 = im.u32(sm.TAB2_BASE_PTR)
    n2 = pa._decode_thumb_movw(im.rd(sm.TAB2_CNT_INSN, 4))[1]
    short = {im.u32(tab2 + 44 * i): cstr(im.rd(tab2 + 44 * i + 4, 16)) for i in range(n2)}
    listed = {}
    for idx in range(pa.E0_BLIST_SLOTS):
        lp, lc = im.u32(sm.BLIST_PTR_TAB + 4 * idx), im.u32(sm.BLIST_CNT_TAB + 4 * idx)
        for k in range(lc if lp else 0):
            listed.setdefault(im.u32(lp + 48 * k + 4), []).append((cstr(im.rd(lp + 48 * k + 14, 26)), idx // 4))
    rows = []
    for m in db["models"]:
        ni = m["words"][2]
        items = listed.get(ni, [])
        rows.append([m["name"], m["meta"].get("category", ""), m["meta"].get("subcategory", ""), m["displayName"],
                     short.get(ni, ""), "|".join(dict.fromkeys(n for n, _ in items)),
                     "|".join(dict.fromkeys(str(c) for _, c in items))])
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("firmware")
    ap.add_argument("-o", "--out", default="models_stock.csv")
    a = ap.parse_args(argv)
    rows = dump(a.firmware)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["internal", "category", "subcategory", "db_display", "table2_short", "browser", "browser_cats"])
        w.writerows(rows)
    print(f"{len(rows)} models -> {a.out}")


if __name__ == "__main__":
    main()
