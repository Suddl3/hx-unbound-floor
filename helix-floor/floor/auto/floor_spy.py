"""Log the UI events the Floor's own controls post (a build with NAM_SCREEN_MIRROR=1 NAM_MIRROR_SPY=1).
Press a button or turn a knob on the unit and this prints the event: class, code, value. HX Edit must be closed.

  floor_spy.py [SECONDS]        poll (default 60 s), print each new event

The firmware keeps the last 16 events in a ring (m4/floor_mirror.s fm_spy). A request to command 0x51 whose seq has bit 15
clear reads it: bit 14 set = the head counter; else bits 5..2 the slot, bits 1..0 the 7-bit chunk of the slot's event
word (class << 16 | code << 8 | value & 0xff). The answer comes back as the reply's status byte.
Class 1 is a key (value 1 press, 2 release, 3 release before a hold, 5 hold), class 2 a knob; the key function adds 64
to the code for classes 0, 3, 4 events (the encoder and joystick presses).
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl  # noqa: E402

CMD = 0x51


class Spy:
    def __init__(self):
        self.ctl = hx_ctl.HxCtl(pid=0x4248, timeout=10.0)

    def ask(self, seq):
        ed = self.ctl.ed
        keep = ed.seq
        ed.seq = (seq - 1) & 0xFFFF
        try:
            try:
                r = ed.request(CMD, timeout=5)
                return r if isinstance(r, int) else 0
            except hx_ctl.HxError as e:             # a non-zero status is the answer; hx_ctl calls it a refusal
                m = re.search(r"status (\d+)", str(e))
                if not m:
                    raise
                return int(m.group(1))
        finally:
            ed.seq = keep

    def head(self):
        return self.ask(0x4000)                     # the counter's low 7 bits

    def slot(self, i):
        w = 0
        for c in range(3):
            w |= (self.ask((i & 15) << 2 | c) & 0x7F) << (7 * c)
        return w >> 16 & 0xFF, w >> 8 & 0xFF, ((w & 0xFF) ^ 0x80) - 0x80


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    s = Spy()
    try:
        run(s, secs)
    finally:
        s.ctl.close()


def run(s, secs):
    last = s.head()
    print("listening; head", last, flush=True)
    end = time.time() + secs
    while time.time() < end:
        h = s.head()
        n = (h - last) & 0x7F
        if n > 16:
            n = 16
        for k in range(n, 0, -1):
            cls, code, val = s.slot((h - k) & 15)
            print(f"class {cls} code {code} value {val}", flush=True)
        last = h
        time.sleep(0.25)


if __name__ == "__main__":
    main()
