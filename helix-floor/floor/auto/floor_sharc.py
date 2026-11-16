"""SHARC dev mode: boot both DSPs live from an LDR image held in RAM (m4/sharc_ramboot.s, test_sharc_ramboot.py). Nothing is
written to the eMMC and no clock, power or thermal register is touched by this tool; the stub only calls the firmware's own
DSP boot (0x100059e0) with RAM-backed streams. A restart brings back the installed firmware. While the DSPs boot, audio stops
and the unit's editor task is busy for a few seconds; afterwards the host side still believes the old graph is loaded, so a
power cycle may be needed (Fan plug, plug.py). HX Edit must be closed.

  floor_sharc.py stage [FILE]    read-only: put the image in RAM (default: the installed Entry 2, read from the eMMC at
                                 sector 0x8007, 2051 sectors) and upload the stub; verify both by readback. Boots nothing.
  floor_sharc.py boot            call the stub: reboots BOTH DSPs from the staged image. Needs --yes-reboot-dsps.
  floor_sharc.py relink          experiment: call the ARM link driver's per-DSP start for DSP 0 and 1 after a boot
  floor_sharc.py full [--limit N]            experiment: link driver teardown, DSP boot from RAM, driver bring-up. Needs --yes-reboot-dsps.
  floor_sharc.py spawn           same as full, in its own task: the host keeps answering and status shows where it stands.
  floor_sharc.py status          the control block's result word
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor_emmc  # noqa: E402
import floor_peek  # noqa: E402
import floor_poke  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STUB_BIN = os.path.join(HERE, "..", "m4", "sharc_ramboot.bin")
STUB, RUN_OFF, RELINK_OFF, FULL_OFF = 0x29F03000, 0x34, 0x94, 0xB0
SPAWN_OFF = 0x1FC                      # sr_spawn: sr_full in its own task   # sr_run's and sr_relink's offsets in the stub
CTL = 0x29F05000
IMG = 0x29A00000                       # up to 1.06 MiB, clear of the picture cache (0x29910000..) and the live stubs (0x29f0....)
ENTRY2_SECTOR, ENTRY2_SECTORS = 0x8007, 0x803     # partition 2's data sector, up to partition 3's header (0x880a)
PENDING = 0x7FFFFFFF


def read_entry2(p):
    out = b""
    for s in range(0, ENTRY2_SECTORS, 1024):
        n = min(1024, ENTRY2_SECTORS - s)
        out += floor_emmc.read(p, ENTRY2_SECTOR + s, n)
    return out


def stage(p, image):
    assert 0 < len(image) <= 0x110000 and len(image) % 4 == 0
    stub = open(STUB_BIN, "rb").read()
    p.write_bulk(IMG, image)
    p.write_bulk(STUB, stub)
    p.write_bulk(CTL, struct.pack("<3I", PENDING, IMG, len(image)))
    pk = floor_peek.Peek(p.ctl)
    try:
        got = pk.read(IMG, len(image))
        w = pk.window(0x29F00000)
        ok_stub = w[STUB - 0x29F00000:][:len(stub)] == stub
        ok_ctl = struct.unpack_from("<3I", w, CTL - 0x29F00000) == (PENDING, IMG, len(image))
    finally:
        pk.close()
    assert got == image, "the image did not arrive intact"
    assert ok_stub and ok_ctl, "the stub or its control block did not arrive intact"


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("stage", "boot", "relink", "full", "spawn", "status"):
        sys.exit(__doc__)
    with floor_poke.Poke() as p:
        p.enable_bulk()
        if a[0] == "stage":
            image = open(a[1], "rb").read() if len(a) > 1 else read_entry2(p)
            image += bytes(-len(image) % 4)
            stage(p, image)
            print(f"staged {len(image)} bytes at {IMG:#x}; stub at {STUB:#x}; nothing booted")
        elif a[0] == "boot":
            if "--yes-reboot-dsps" not in a:
                sys.exit("refused: this reboots both DSPs (audio stops). Add --yes-reboot-dsps")
            p.call(STUB + RUN_OFF)
            print("called; read the result with: floor_sharc.py status")
        elif a[0] == "full":
            if "--yes-reboot-dsps" not in a:
                sys.exit("refused: this tears the link driver down and reboots both DSPs. Add --yes-reboot-dsps")
            limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 99
            p.write(CTL + 0x14, struct.pack("<I", limit))     # a step above this is not run (result 0x7e): bisects a hang
            p.call(STUB + FULL_OFF)
            print(f"called (steps up to {limit}); floor_sharc.py status shows the step reached (99 = done)")
        elif a[0] == "spawn":
            if "--yes-reboot-dsps" not in a:
                sys.exit("refused: this tears the link driver down and reboots both DSPs. Add --yes-reboot-dsps")
            p.call(STUB + SPAWN_OFF)
            print("task created; poll floor_sharc.py status (step 99 = done)")
        elif a[0] == "relink":
            p.call(STUB + RELINK_OFF)
            print("called; results at CTL+0x10/0x14: floor_sharc.py status")
        else:
            pk = floor_peek.Peek(p.ctl)
            try:
                w = pk.window(0x29F00000)
                res = struct.unpack_from("<i", w, CTL - 0x29F00000)[0]
                link = struct.unpack_from("<2i", w, CTL - 0x29F00000 + 0x10)
                step = struct.unpack_from("<2i", w, CTL - 0x29F00000 + 0x18)
            finally:
                pk.close()
            print("pending (stub not finished or not run)" if res == PENDING else f"boot result {res}", f"relink results {link}", f"full: step {step[0]}, failing result {step[1]}")


if __name__ == "__main__":
    main()
