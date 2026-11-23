#!/usr/bin/env python3
"""A folder of HX Edit Unbound's 3D gear pictures under HX Edit's own file names, for floor_emmc_art.py's HX_ART_DIR.

The release's helix-gear-art.zip (Suddl3/hx-edit-unbound, e.g. gear-art-2026-11-22) holds the renders by their own ids in
256/ (bass_agua51.png); HX Edit's models are named AMP_HX_BASS_Agua51.png. src/helix_model_icons/icons.json of the editor
clone maps one to the other. This copies each render to its HX Edit name, so

  python hxart_from_pack.py helix-gear-art/256 <clone>/src/helix_model_icons/icons.json OUT
  HX_ART_DIR=OUT NAM_ICON_PIX=nam-gear-art/256 NAM_CAPTURE_ICONS=<clone> python floor_emmc_art.py write 256 --scenes ... --cutout

draws every model from his art (no Line 6 pictures at all). Nothing is overwritten that is not already in OUT's own set."""
import json
import os
import shutil
import sys


def main(pack, icons, out):
    table = json.load(open(icons, encoding="utf-8"))["icons"]
    os.makedirs(out, exist_ok=True)
    copied, missing = 0, []
    for stock, v in table.items():
        src = os.path.join(pack, v["render"] + ".png")
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(out, stock))
            copied += 1
        else:
            missing.append(stock)
    print(f"{copied} pictures copied to {out}" + (f"; {len(missing)} missing: {missing[:5]}" if missing else ""))
    return 1 if missing else 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
