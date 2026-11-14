"""Set Focus View's pictures live (a build whose DSP meter module has dm_imgs and the mirror passes classes 5 and 6).

  floor_art.py PIC,X,Y,W,H [PIC,X,Y,W,H ...]  replace the table (up to 4 pictures), then repaint (a joystick nudge right
                                              then left redraws the home view)
  PIC is an image index, or "sel": the selected block's own picture (a NAM_ART=map build: item 1093 + its preset id)
  floor_art.py                                back to the default: sel,400,110,128,128

Class 5 sets the write index, class 6 writes a 12-bit halfword and steps on (fm_input posts them, dm_event takes them).
The payload rides in the event's code (high 6 bits) and value (low 6 bits, sent as a signed 6-bit number).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_input  # noqa: E402

SEL = 4094          # SEL_PIC in floor_dsp_meter.s
SLOTS = 4


def signed6(v):
    return v - 64 if v >= 32 else v


def poke(inp, words):
    inp.event(5, 0, 0)
    for w in words:
        assert 0 <= w < 4096, w
        inp.event(6, w >> 6, signed6(w & 63))


def main():
    args = sys.argv[1:] or ["sel,400,110,128,128"]
    pics = [tuple(SEL if i == 0 and x == "sel" else int(x) for i, x in enumerate(a.split(","))) for a in args]
    assert pics and all(len(p) == 5 for p in pics) and len(pics) <= SLOTS
    pics += [(4095, 0, 0, 0, 0)] * (SLOTS - len(pics))     # unused slots: an index past the item table, which the lookup skips
    words = [v for p in pics for v in p]                   # (0xffff, the table's end, cannot be sent in 12 bits)
    inp = floor_input.Input()
    try:
        poke(inp, words)
        inp.tap(11)
        time.sleep(0.3)
        inp.tap(10)
    finally:
        inp.close()


if __name__ == "__main__":
    main()
