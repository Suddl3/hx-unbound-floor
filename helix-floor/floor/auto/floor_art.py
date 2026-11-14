"""Set Focus View's pictures live, through the mirror's poke (auto/floor_poke.py; the address of the picture table comes
from live.json, "dm_imgs").

  floor_art.py PIC,X,Y,W,H [PIC,X,Y,W,H ...]  replace the table (up to 4 pictures), then repaint (a joystick nudge right
                                              then left redraws the home view)
  PIC is an image index, or "sel": the selected block's own picture (a NAM_ART=map build: item 1093 + its preset id)
  floor_art.py                                back to the default: sel,400,174,44,44
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_input  # noqa: E402
import floor_poke  # noqa: E402

SEL = 4094          # SEL_PIC in floor_dsp_meter.s
SLOTS = 4


def main():
    args = sys.argv[1:] or ["sel,400,174,44,44"]
    pics = [tuple(SEL if i == 0 and x == "sel" else int(x) for i, x in enumerate(a.split(","))) for a in args]
    assert pics and all(len(p) == 5 for p in pics) and len(pics) <= SLOTS
    words = [v for p in pics for v in p] + [0xFFFF] * (5 * SLOTS - 5 * len(pics))
    with floor_poke.Poke() as p:
        p.write(floor_poke.live()["dm_imgs"], b"".join(struct.pack("<H", w) for w in words))
    inp = floor_input.Input()
    try:
        inp.tap(11)
        time.sleep(0.3)
        inp.tap(10)
    finally:
        inp.close()


if __name__ == "__main__":
    main()
