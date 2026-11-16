"""Dev mode: log the key events the Floor's own buttons post, to see how a real press differs from the mirror's input
(auto/floor_input.py). A 10-byte jump over dm_event's first instructions (module + 1362) sends every UI event post to
m4/event_log.bin in free SDRAM, which records the key events (class 1) in a ring; this tool reads the ring back.
RAM only: a restart undoes it. Needs the build whose live.json is HX_LIVE_JSON (the DSP meter module, dm_event at +1362).

  floor_evlog.py install     check the module bytes first (refuses if they differ), upload the logger, patch the jump
  floor_evlog.py read        print the logged key events, oldest first (press / release / 3 = release before a hold / 5 hold)
  floor_evlog.py clear       empty the ring
  floor_evlog.py uninstall   put the original 16 bytes back
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_peek  # noqa: E402
import floor_poke  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
M4 = os.path.join(HERE, "..", "m4")
RING, STUB, COPY, COPY_DST = 0x29F06000, 0x29F07000, 0x29F06C00, 0x29F06800
DM_EVENT_OFF = 1362                    # dm_event in the DSP meter module (m4/floor_dsp_meter.json)
PATCH_OFF = DM_EVENT_OFF - 2           # word aligned: the 16 bytes from the `bx lr` before dm_event


def module_bytes():
    b = open(os.path.join(M4, "floor_dsp_meter.bin"), "rb").read()
    return b[PATCH_OFF:PATCH_OFF + 16]


def patch_addr():
    return int(floor_poke.live()["meter"]) + PATCH_OFF


def read_unit(p):
    """The 16 bytes at the patch address, copied to SDRAM by a stub and peeked."""
    code = bytearray(open(os.path.join(M4, "copy16.bin"), "rb").read())
    pool = len(code) - 8
    struct.pack_into("<2I", code, pool, patch_addr(), COPY_DST)
    p.write_bulk(COPY, bytes(code))
    p.call(COPY)
    pk = floor_peek.Peek(p.ctl)
    try:
        return pk.read(COPY_DST, 16)
    finally:
        pk.close()


def jump():
    orig = module_bytes()
    return orig[:2] + b"\x00\xbf" + b"\xdf\xf8\x00\xf0" + struct.pack("<I", STUB | 1) + orig[12:16]


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("install", "read", "clear", "uninstall"):
        sys.exit(__doc__)
    with floor_poke.Poke() as p:
        p.enable_bulk()
        if a[0] == "install":
            have = read_unit(p)
            if have == jump():
                sys.exit("already installed")
            assert have == module_bytes(), f"the module on the unit is not the one this tool expects: {have.hex()} vs {module_bytes().hex()}"
            code = open(os.path.join(M4, "event_log.bin"), "rb").read()
            p.write_bulk(RING, bytes(16 + 64 * 16))
            p.write_bulk(STUB, code)
            pk = floor_peek.Peek(p.ctl)
            try:
                assert pk.read(STUB, len(code)) == code, "the logger did not arrive intact: nothing patched"
            finally:
                pk.close()
            p.patch_atomic(patch_addr(), jump())
            print("installed: key events are logged; press buttons on the Floor, then: floor_evlog.py read")
        elif a[0] == "uninstall":
            p.patch_atomic(patch_addr(), module_bytes())
            print("original bytes restored")
        elif a[0] == "clear":
            p.write_bulk(RING, bytes(16 + 64 * 16))
            print("cleared")
        else:
            pk = floor_peek.Peek(p.ctl)
            try:
                d = pk.read(RING, 16 + 64 * 16)
            finally:
                pk.close()
            head = struct.unpack_from("<I", d, 0)[0]
            names = {1: "press", 2: "release", 3: "release-before-hold", 5: "hold"}
            first = max(0, head - 64)
            print(f"{head} key events logged")
            for n in range(first, head):
                cls, code, _, val, cfg, hv = struct.unpack_from("<BBHiII", d, 16 + 16 * (n % 64))
                print(f"{n:4d}: key {code:3d}  value {val} ({names.get(val, '?'):19s})  focus {cfg >> 16 & 255} flags {cfg >> 24:#x}  home view {hv}")


if __name__ == "__main__":
    main()
