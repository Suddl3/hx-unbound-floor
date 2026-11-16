"""Dev mode (RAM only, a restart undoes it): fixes for the Focus View double-Home bug, as patches over the DSP meter module that is
running on the unit. Each patch checks the unit's bytes against the build's module first and restores them on `off`.

  floor_homefix.py pre on|off     paint-task exit fix (m4/fe_pre.bin): when Focus View goes off the next two paints blank the paths'
                                  area and force the stock full repaint; an 8-byte jump at module + 512
  floor_homefix.py rt on|off      the gear-menu repaint round trip at Home's release (module + 1440, a `beq de_go` made `b de_go`
                                  when "off" = no round trip)
  floor_homefix.py delay on|off   the earlier experiment (m4/rt_delay.bin: the round trip with a pause), jump at module + 1444
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_evlog as ev  # noqa: E402
import floor_poke  # noqa: E402


def module():
    return open(os.path.join(ev.M4, "floor_dsp_meter.bin"), "rb").read()


def base():
    return int(floor_poke.live()["meter"])


def read16(p, addr):
    code = bytearray(open(os.path.join(ev.M4, "copy16.bin"), "rb").read())
    struct.pack_into("<2I", code, len(code) - 8, addr, ev.COPY_DST)
    p.write_bulk(ev.COPY, bytes(code))
    p.call(ev.COPY)
    pk = ev.floor_peek.Peek(p.ctl)
    try:
        return pk.read(ev.COPY_DST, 16)
    finally:
        pk.close()


def upload(p, name, at):
    code = open(os.path.join(ev.M4, name), "rb").read()
    p.write_bulk(at, code)
    pk = ev.floor_peek.Peek(p.ctl)
    try:
        assert pk.read(at, len(code)) == code, f"{name} did not arrive intact: nothing patched"
    finally:
        pk.close()


def patch(p, off, new16, stub=None):
    """Replace the 16 bytes at module + off (word aligned on the unit) by new16, after checking the unit has the build's bytes
    there (or already new16)."""
    addr = base() + off
    assert addr % 4 == 0, hex(addr)
    orig = module()[off:off + 16]
    have = read16(p, addr)
    if have == new16:
        print("already in that state")
        return
    assert have == orig or stub is None, "unexpected bytes"
    if have != orig:
        raise SystemExit(f"the module on the unit is not the expected one at +{off}: {have.hex()} vs {orig.hex()}")
    if stub:
        upload(p, *stub)
    p.patch_atomic(addr, new16)


def main():
    a = sys.argv[1:]
    if len(a) != 2 or a[0] not in ("pre", "rt", "delay") or a[1] not in ("on", "off"):
        sys.exit(__doc__)
    m = module()
    on = a[1] == "on"
    with floor_poke.Poke() as p:
        p.enable_bulk()
        if a[0] == "pre":
            off = 512                   # ldr.w r3, [pc, #0x400]; blx r3; str r0, [sp, #0x80]  (8 bytes), then movs r6, #0 stays
            stub = 0x29F08000
            jump = b"\xdf\xf8\x00\xf0" + struct.pack("<I", stub | 1) + m[off + 8:off + 16]
            if on:
                patch(p, off, jump, ("fe_pre.bin", stub))
            else:
                p.patch_atomic(base() + off, m[off:off + 16])
        elif a[0] == "delay":
            off = 1444
            stub = 0x29F07400
            jump = b"\xdf\xf8\x00\xf0" + struct.pack("<I", stub | 1) + m[off + 8:off + 16]
            if on:
                patch(p, off, jump, ("rt_delay.bin", stub))
            else:
                p.patch_atomic(base() + off, m[off:off + 16])
        else:                           # rt: "on" = the stock behaviour (round trip), "off" = no round trip
            off = 1440
            new = m[off:off + 2] + b"\x1c\xe0" + m[off + 4:off + 16]   # 1442: `beq de_go` -> `b de_go` (1502)
            assert m[1442:1444] != b"\x1c\xe0"
            if on:
                p.patch_atomic(base() + off, m[off:off + 16])
            else:
                patch(p, off, new)
        print(f"{a[0]} {a[1]}: done")


if __name__ == "__main__":
    main()
