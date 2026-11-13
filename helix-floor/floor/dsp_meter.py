"""DSP meter for the Helix Floor (env NAM_DSP_METER=1), ported from HXtra's dsp_meter (wisemandenny/hxtra, GPL-3.0).

The home view shows each block's DSP cost (whole per cent, grey) under its icon, and each path's blocks' sum against
what blocks may use on that path's DSP as "P1 used/75" and "P2 used/75" (white) in the title bar. The costs are the
firmware's own declared ones (the ones it checks a preset against), not measured load.

The code goes in the local-SRAM cave (stage_main). The home view's paint function pointer, a literal the boot passes
to the view registrar (0x28093592), is pointed at dm_paint, which wipes the labels that changed, runs the stock paint
and then draws the labels.

m4/floor_dsp_meter.s is assembled with zig's clang (pip install ziglang): `python dsp_meter.py --assemble` writes
m4/floor_dsp_meter.bin and m4/floor_dsp_meter.json (symbol offsets). (*.bin is gitignored here, as the mirror's: a fresh
checkout runs --assemble once.)
"""
import json
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "m4", "floor_dsp_meter.s")
BIN = os.path.join(HERE, "m4", "floor_dsp_meter.bin")
SYMS = os.path.join(HERE, "m4", "floor_dsp_meter.json")
ENABLED = os.environ.get("NAM_DSP_METER") == "1"
PAINT_LIT, PAINT = 0x2809372c, 0x280d6be9    # the home view's paint, as the boot registers it (ldr r0 at 0x28093590)

# Every firmware address floor_dsp_meter.s uses, with its stock first bytes (from HXtra's Stomp addresses by masked
# byte matching and the call graph; see docs/FINDINGS.md "DSP meter")
STOCK = (
    (0x28093590, "6648", "the registration's ldr r0 of the home view's paint (literal 0x2809372c)"),
    (0x280d6be8, "2de9f04f01f5c858", "the home view's paint (push.w {r4-r11, lr}; add.w r8, r1, #0x1900)"),
    (0x2813e63c, "20b9044b", "the DSP model's lock (cbnz r0; ldr r3, =0x284e5758)"),
    (0x2813e654, "20b9044b", "the DSP model's unlock"),
    (0x2808ee38, "0148c7f0", "the widget lock (ldr r0, =0x28178e6c; b.w)"),
    (0x2808ee44, "0148c7f0", "the widget unlock"),
    (0x281404b8, "4ff0540c", "the block address map: records of 0x54 bytes (mov.w ip, #0x54)"),
    (0x2814048c, "00f5a040", "the node container at model + 0x505c (add.w r0, r0, #0x5000)"),
    (0x2811d63c, "5b6a", "the block-node lookup: [table + 0x24 + 4 handle]"),
)


def assemble():
    """m4/floor_dsp_meter.s -> .bin + .json, with zig's clang."""
    with tempfile.TemporaryDirectory() as d:
        obj = os.path.join(d, "m.o")
        zig = [sys.executable, "-m", "ziglang"]
        subprocess.run(zig + ["cc", "-target", "thumb-freestanding-eabi", "-mcpu=cortex_m4", "-c", SRC, "-o", obj],
                       check=True)
        subprocess.run(zig + ["objcopy", "-O", "binary", "-j", ".text", obj, BIN], check=True)
        b = open(obj, "rb").read()
    shoff, = struct.unpack_from("<I", b, 0x20)
    ent, num, _ = struct.unpack_from("<HHH", b, 0x2e)
    secs = [struct.unpack_from("<10I", b, shoff + i * ent) for i in range(num)]
    syms = {}
    for s in secs:
        if s[1] == 2:                                   # SHT_SYMTAB
            st = secs[s[6]]
            for i in range(s[5] // 16):
                nm, val, *_ = struct.unpack_from("<IIIBBH", b, s[4] + 16 * i)
                name = b[st[4] + nm:].split(b"\0")[0].decode()
                if name.startswith("dm_"):
                    syms[name] = val & ~1
    with open(SYMS, "w") as f:
        json.dump(dict(sorted(syms.items())), f, indent=1)
    return open(BIN, "rb").read(), syms


def load():
    return open(BIN, "rb").read(), json.load(open(SYMS))


def check_stock(im):
    for va, want, what in STOCK:
        got = im.rd(va, len(want) // 2).hex()
        assert got == want, f"{va:#x} ({what}) is not stock: {got}"
    assert im.u32(PAINT_LIT) == PAINT, f"the home view's paint literal {PAINT_LIT:#x} is not stock: {im.u32(PAINT_LIT):#x}"
    assert im.u32(0x2813e650) == 0x284e5758, "the DSP model lock's literal is not the model pointer 0x284e5758"


def apply(im, code_va, syms):
    """Point the home view's paint at dm_paint; the code itself is already in the cave at code_va."""
    check_stock(im)
    assert code_va % 4 == 0
    im.wr(PAINT_LIT, struct.pack("<I", (code_va + syms["dm_paint"]) | 1))
    return (f"DSP meter: {len(load()[0])} B at {code_va:#x}; home view paint {PAINT_LIT:#x} -> "
            f"{(code_va + syms['dm_paint']) | 1:#x} (then the stock {PAINT:#x})")


if __name__ == "__main__":
    if "--assemble" in sys.argv:
        code, syms = assemble()
        print(len(code), "bytes;", syms)
