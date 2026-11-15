"""Focus View's pictures from the eMMC picture store, and the model pictures inside the path blocks, built in
(env NAM_EMMC_ART=1; needs NAM_DSP_METER=1).

m4/focus_emmc.s goes after segment 1's bytes (local SRAM 0x10088a30 + 0x3008 = 0x1008ba38: up to the bank's end at
0x10092000 the run-time contents were only the boot memory test's pattern: unproven; FINDINGS has the correction and a way to
prove it, a watch on that range over a session). Two patches in the DSP meter module point at
it: Focus View's focus_img jumps to fe_img (the big picture), and the end of dm_paint calls fe_hook (Focus View's own
fill as before, else the small model picture inside each path block). fe_img first draws the model's background (fe_bg:
bg_store.py's section in the store header) when there is one. The pictures themselves are written once with
auto/floor_emmc_art.py (write: the big ones, icons: the small ones) and are never part of the firmware.
Emulator tests: test_focus_emmc.py, test_block_icons.py.
"""
import os
import struct

ENABLED = os.environ.get("NAM_EMMC_ART") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "m4", "focus_emmc.bin")
SEG1 = (0x10088A30, 0x3008)                 # segment 1: destination, stock length
VA = SEG1[0] + SEG1[1]
FOCUS_IMG = bytes.fromhex("e0b58ab0")       # focus_img's first two instructions: push {r5-r7, lr}; sub sp, #0x28
SITE = bytes.fromhex("9b780bb1")            # ldrb r3, [r3, #2]; cbz r3, +6: Focus View's test at the end of dm_paint
END = 0x10092000
HOOK, IMG, LIT = 0x000, 0x540, 0x500        # fe_hook, fe_img and the literals in the module (m4/focus_emmc.s .org's)


def load():
    code = open(BIN, "rb").read()
    assert VA + len(code) <= END
    return code + bytes(-len(code) % 4)


def jump(at):
    """Bytes for `at` that go to fe_img: ldr.w pc, [pc] with its word aligned (a nop first at 2 mod 4)."""
    body = b"\xdf\xf8\x00\xf0" + struct.pack("<I", (VA + IMG) | 1)
    return body if at % 4 == 0 else b"\x00\xbf" + body


def encode_bl(src, dst):
    """Thumb-2 BL at src to dst."""
    off = dst - (src + 4)
    assert off % 2 == 0 and -(1 << 24) <= off < (1 << 24)
    s, i1, i2 = (off >> 24) & 1, (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    hw1 = 0xF000 | s << 10 | (off >> 12) & 0x3FF
    hw2 = 0xD000 | j1 << 13 | j2 << 11 | (off >> 1) & 0x7FF
    return struct.pack("<2H", hw1, hw2)


def decode_bl(src, b):
    hw1, hw2 = struct.unpack("<2H", b)
    assert hw1 >> 11 == 0x1E and hw2 >> 14 == 3 and hw2 >> 12 & 1, (hex(hw1), hex(hw2))
    s, j1, j2 = hw1 >> 10 & 1, hw2 >> 13 & 1, hw2 >> 11 & 1
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    off = s << 24 | i1 << 23 | i2 << 22 | (hw1 & 0x3FF) << 12 | (hw2 & 0x7FF) << 1
    if s:
        off -= 1 << 25
    return src + 4 + off


def hook_site(meter_code):
    """Offset of the 12 bytes `adr.w r3, dm_cfg; ldrb; cbz; bl focus_fill` that the call of fe_hook replaces."""
    k = meter_code.find(SITE)
    assert k >= 4 and meter_code.find(SITE, k + 1) < 0, "Focus View lines not found once in the meter module"
    return k - 4


def patches(meter_va, meter_code):
    """({offset in the meter module: bytes}, the meter's focus_fill): the jump over focus_img to fe_img, and at the end of
    dm_paint `mov r0, r5; mov r1, r4; bl fe_hook; nop; nop` over the Focus View lines."""
    site = hook_site(meter_code)
    focus_fill = decode_bl(meter_va + site + 8, meter_code[site + 8:site + 12])
    img = meter_code.find(FOCUS_IMG)
    assert img > 0 and meter_code.find(FOCUS_IMG, img + 1) < 0, "focus_img not found once in the meter module"
    hook = b"\x28\x46\x21\x46" + encode_bl(meter_va + site + 4, VA + HOOK) + b"\x00\xbf\x00\xbf"
    assert len(hook) == 12
    return {img: jump(meter_va + img), site: hook}, focus_fill


def with_literals(code, dm_cfg, focus_fill):
    """The module with the meter's dm_cfg and focus_fill (Thumb bit set) in its literals."""
    out = bytearray(code)
    struct.pack_into("<3I", out, LIT, dm_cfg, focus_fill | 1, 0)
    return bytes(out)


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


SRC = os.path.join(HERE, "m4", "focus_emmc.s")


def assemble(check=False):
    """Assemble m4/focus_emmc.s with zig's clang (pip install ziglang), as dsp_meter.py does; check=True only compares
    with the committed m4/focus_emmc.bin, otherwise it rewrites it."""
    import subprocess
    import sys
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        obj, binary = os.path.join(d, "m.o"), os.path.join(d, "m.bin")
        env = dict(os.environ, ZIG_LOCAL_CACHE_DIR=os.path.join(d, "lc"), ZIG_GLOBAL_CACHE_DIR=os.path.join(d, "gc"))
        zig = [sys.executable, "-m", "ziglang"]
        subprocess.run(zig + ["cc", "-target", "thumb-freestanding-eabi", "-mcpu=cortex_m4", "-c", SRC, "-o", obj],
                       check=True, timeout=60, env=env)
        subprocess.run(zig + ["objcopy", "-O", "binary", "-j", ".text", obj, binary], check=True, timeout=60, env=env)
        code = open(binary, "rb").read()
    if check:
        if open(BIN, "rb").read() != code:
            raise ValueError("Assembled focus_emmc bytes differ from the committed binary.")
    else:
        open(BIN, "wb").write(code)
    return code


if __name__ == "__main__":
    import sys
    if "--assemble" in sys.argv or "--check" in sys.argv:
        print(len(assemble(check="--check" in sys.argv)), "bytes")
