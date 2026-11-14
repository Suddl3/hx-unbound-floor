"""Set Focus View's pictures live (a build whose DSP meter module has dm_imgs and the mirror passes classes 5 and 6).

  floor_art.py IDX,X,Y,W,H [IDX,X,Y,W,H ...]   replace the table (up to 8 pictures), then repaint (Home twice is not needed:
                                              a joystick nudge right then left redraws the home view)

Class 5 sets the write index, class 6 writes a 12-bit halfword and steps on (fm_input posts them, dm_event takes them).
The payload rides in the event's code (high 6 bits) and value (low 6 bits, sent as a signed 6-bit number).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_input  # noqa: E402


def signed6(v):
    return v - 64 if v >= 32 else v


def poke(inp, words):
    inp.event(5, 0, 0)
    for w in words:
        assert 0 <= w < 4096, w
        inp.event(6, w >> 6, signed6(w & 63))


def main():
    pics = [tuple(int(x) for x in a.split(",")) for a in sys.argv[1:]]
    assert pics and all(len(p) == 5 for p in pics) and len(pics) <= 8
    pics += [(4095, 0, 0, 0, 0)] * (8 - len(pics))         # unused slots: an index past the item table, which the lookup skips
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
