"""Virtual button presses and knob turns on the Helix Floor, from a build with NAM_SCREEN_MIRROR=1 (its command 0x51,
m4/floor_mirror.s fm_input). Pairs with floor_mirror.py: press, then look. HX Edit must be closed.

  floor_input.py tap CODE [CODE ...]            press and release keys (class 1), 0.1 s apart
  floor_input.py hold CODE                      press, hold event, release
  floor_input.py turn KNOB COUNTS               turn a knob (class 2; KNOB 0..6, COUNTS signed, 4 a step on an int)
  floor_input.py raw CLASS CODE VALUE           one event as is
  floor_input.py scan FIRST LAST DIR            tap each key code in turn and save DIR/key_NN.png after it
  floor_input.py do STEPS... --shot out.png     a sequence: tap:C, hold:C, turn:K:N, wait:S; then a screenshot

The event travels in the request's seq: bit 15 set, class bits 14..12, code bits 11..6, value bits 5..0 (signed).
Key codes 64..255 (the encoder and joystick presses) go as class 0, 3 or 4 (fm_input adds 64, 128 or 192); tap/hold take them as plain numbers.
The firmware posts {class, code, 0, 0, value} to the UI as its own producers do and replies 0. Key values: 1 press,
2 release, 3 release before a hold, 5 hold. Knob values: the turn, -32..31 counts an event (longer turns are split).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl  # noqa: E402

CMD = 0x51
KEY, KNOB = 1, 2
PRESS, RELEASE, RELEASE_HELD, HOLD = 1, 2, 3, 5


class Input:
    def __init__(self, ctl=None):
        self.ctl = ctl or hx_ctl.HxCtl(pid=0x4248, timeout=10.0)

    def event(self, cls, code, value):
        if cls == KEY and code >= 64:               # keys 64..255 ride in classes 0, 3, 4 (fm_input adds 64, 128, 192)
            assert code < 256, code
            cls, code = {1: 0, 2: 3, 3: 4}[code // 64], code % 64
        assert 0 <= cls < 7 and 0 <= code < 64 and -32 <= value < 32, (cls, code, value)
        seq = 0x8000 | cls << 12 | code << 6 | (value & 0x3F)
        ed = self.ctl.ed
        keep = ed.seq                               # the mirror's own seq sequence is left as it was
        ed.seq = (seq - 1) & 0xFFFF
        try:
            r = ed.request(CMD, timeout=5)
        finally:
            ed.seq = keep
        if r != 0:
            raise hx_ctl.HxError(f"input: unexpected reply {r!r} (a build without the 0x51 command?)")

    def tap(self, code, dwell=0.1):
        self.event(KEY, code, PRESS)
        time.sleep(dwell)
        self.event(KEY, code, RELEASE)

    def hold(self, code):
        self.event(KEY, code, PRESS)
        time.sleep(1.0)
        self.event(KEY, code, HOLD)
        self.event(KEY, code, RELEASE)

    def turn(self, knob, counts):
        while counts:
            n = max(-32, min(31, counts))
            self.event(KNOB, knob, n)
            counts -= n
            time.sleep(0.02)

    def close(self):
        self.ctl.close()


def shot(ctl, path):
    import floor_mirror
    m = floor_mirror.Mirror(ctl)
    a = m.frame()
    open(path, "wb").write(floor_mirror.png(a))
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("tap"); sp.add_argument("codes", type=lambda s: int(s, 0), nargs="+")
    sp = sub.add_parser("hold"); sp.add_argument("code", type=lambda s: int(s, 0))
    sp = sub.add_parser("turn"); sp.add_argument("knob", type=int); sp.add_argument("counts", type=int)
    sp = sub.add_parser("raw")
    for a in ("cls", "code", "value"):
        sp.add_argument(a, type=lambda s: int(s, 0))
    sp = sub.add_parser("scan")
    sp.add_argument("first", type=lambda s: int(s, 0)); sp.add_argument("last", type=lambda s: int(s, 0))
    sp.add_argument("dir")
    sp = sub.add_parser("do"); sp.add_argument("steps", nargs="+"); sp.add_argument("--shot")
    args = ap.parse_args()
    inp = Input()
    try:
        if args.cmd == "tap":
            for c in args.codes:
                inp.tap(c)
                time.sleep(0.1)
        elif args.cmd == "hold":
            inp.hold(args.code)
        elif args.cmd == "turn":
            inp.turn(args.knob, args.counts)
        elif args.cmd == "raw":
            inp.event(args.cls, args.code, args.value)
        elif args.cmd == "scan":
            os.makedirs(args.dir, exist_ok=True)
            for c in range(args.first, args.last + 1):
                inp.tap(c)
                time.sleep(0.6)
                print(c, shot(inp.ctl, os.path.join(args.dir, f"key_{c:02d}.png")), flush=True)
        elif args.cmd == "do":
            for st in args.steps:
                kind, *v = st.split(":")
                v = [int(x, 0) if kind != "wait" else float(x) for x in v]
                {"tap": lambda: inp.tap(v[0]), "hold": lambda: inp.hold(v[0]),
                 "turn": lambda: inp.turn(v[0], v[1]), "wait": lambda: time.sleep(v[0])}[kind]()
                time.sleep(0.15)
            if args.shot:
                time.sleep(0.4)
                print(shot(inp.ctl, args.shot))
    finally:
        inp.close()


if __name__ == "__main__":
    main()
