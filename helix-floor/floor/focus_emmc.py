"""Focus View's pictures from the eMMC picture store, built in (env NAM_EMMC_ART=1; needs NAM_DSP_METER=1).

m4/focus_emmc.s goes after segment 1's bytes (local SRAM 0x10088a30 + 0x3008 = 0x1008ba38: up to the bank's end at
0x10092000 the run-time contents were only the boot memory test's pattern), and a jump to it replaces the start of the
DSP meter module's focus_img. The pictures themselves are written once with auto/floor_emmc_art.py write (they are
never part of the firmware). Emulator test: test_focus_emmc.py.
"""
import os
import struct

ENABLED = os.environ.get("NAM_EMMC_ART") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "m4", "focus_emmc.bin")
SEG1 = (0x10088A30, 0x3008)                 # segment 1: destination, stock length
VA = SEG1[0] + SEG1[1]
FOCUS_IMG = bytes.fromhex("e0b58ab0")       # focus_img's first two instructions: push {r5-r7, lr}; sub sp, #0x28
END = 0x10092000


def load():
    code = open(BIN, "rb").read()
    assert VA + len(code) <= END
    return code + bytes(-len(code) % 4)


def jump(at):
    """Bytes for `at` that go to fe_img: ldr.w pc, [pc] with its word aligned (a nop first at 2 mod 4)."""
    body = b"\xdf\xf8\x00\xf0" + struct.pack("<I", VA | 1)
    return body if at % 4 == 0 else b"\x00\xbf" + body


def meter_patch(meter_va, meter_code):
    """(offset in the meter module, bytes): the jump over focus_img."""
    off = meter_code.find(FOCUS_IMG)
    assert off > 0 and meter_code.find(FOCUS_IMG, off + 1) < 0, "focus_img not found once in the meter module"
    return off, jump(meter_va + off)


def append_to_seg1(e0, segments, code):
    """Entry 0 with code after segment 1's bytes; later segments move in the file."""
    out = bytearray(e0)
    segs = segments(out)
    h1, p1, l1, d1, n1 = segs[1]
    assert (d1, l1) == SEG1, f"segment 1 is not stock: {d1:#x} + {l1:#x}"
    out = out[:n1] + code + out[n1:]
    delta = len(code)
    struct.pack_into("<3I", out, h1, l1 + delta, d1, n1 + delta)
    for h, p, l, d, n in segs[2:]:
        struct.pack_into("<3I", out, h + delta, l, d, n + delta)
    struct.pack_into("<I", out, 4, len(out))
    return bytes(out)
