#!/usr/bin/env python3
"""Map the Floor's model preset ids to HX Edit's model pictures (personal builds only: the pictures are never shipped).

A block's descriptor holds its preset id (+1, a word; ids <= 832). HX Edit's res/Helix.sym is a list whose index is that
preset id (833 entries; 147/148 the DSP flow inputs, 555 Xenomorph Fuzz Mono, as the firmware's tables). Its
res/HX_ModelCatalog.json names each model's picture ("image", in res/icons_models). A model without its own picture
(fixed blocks, fillers, models the catalog leaves out) gets its catalog category's picture (res/icons_category) when the
symbol is in the catalog, else none. The catalog names an effect once where the firmware has a Mono and a Stereo model:
both get its picture. Picture paths are relative to the res folder.

usage: art_map.py [out.json]      (default: art_map.json beside this file; HX_EDIT_RES overrides the res folder)
writes {"pictures": [png, ...], "ids": {preset id: picture index}, "missing": [preset ids with no picture]}
"""
import json
import os
import sys

RES = os.environ.get("HX_EDIT_RES", r"C:\Program Files (x86)\Line6\HX Edit\res")


def walk(node, cat_img, out):
    """Every model ({"id": symbol, "image": png}) under a category, with that category's picture."""
    if isinstance(node.get("id"), str):
        out.setdefault(node["id"], (node.get("image"), cat_img))
    for k in ("subcategories", "models"):
        for c in node.get(k, ()):
            walk(c, cat_img, out)


def build(res=RES):
    syms = [e.get("symbol") for e in json.load(open(os.path.join(res, "Helix.sym")))]
    cat = json.load(open(os.path.join(res, "HX_ModelCatalog.json")))
    models = {}
    for c in cat["categories"]:
        walk(c, c.get("image"), models)
    have = {n: "icons_models/" + n for n in os.listdir(os.path.join(res, "icons_models"))}
    cats = {n: "icons_category/" + n for n in os.listdir(os.path.join(res, "icons_category"))}
    pictures, ids, missing, kinds = [], {}, [], {"model": 0, "category": 0}
    for pid, sym in enumerate(syms):
        img = None
        key = sym
        if sym and sym not in models:                    # the catalog names an effect once, the firmware Mono and Stereo
            for sfx in ("Mono", "Stereo"):
                if sym.endswith(sfx) and sym[:-len(sfx)] in models:
                    key = sym[:-len(sfx)]
        if key in models:
            own, cimg = models[key]
            if own in have:
                img, kind = have[own], "model"
            elif cimg in cats:
                img, kind = cats[cimg], "category"
        if img is None:
            missing.append(pid)
            continue
        kinds[kind] += 1
        if img not in pictures:
            pictures.append(img)
        ids[pid] = pictures.index(img)
    return {"pictures": pictures, "ids": ids, "missing": missing, "symbols": syms, "kinds": kinds}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "art_map.json")
    m = build()
    with open(out, "w") as f:
        json.dump({k: m[k] for k in ("pictures", "ids", "missing")}, f, indent=1)
    print(f"art map: {len(m['ids'])} of {len(m['symbols'])} preset ids have a picture "
          f"({m['kinds']['model']} own, {m['kinds']['category']} category), {len(m['pictures'])} distinct PNGs, "
          f"{len(m['missing'])} without; wrote {out}")


if __name__ == "__main__":
    main()
