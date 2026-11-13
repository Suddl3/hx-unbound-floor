"""Screen mirror for the Helix Floor (env NAM_SCREEN_MIRROR=1), ported from HXtra's screen_mirror
(wisemandenny/hxtra, GPL-3.0).

HX Edit's editor service gets two more commands (free on the Floor as on the Stomp): 0x52, whose reply holds the LCD
rows that changed since the last reply, and 0x51, which posts a key press or knob turn packed in its seq to the UI, as
the front panel would (m4/floor_mirror.s fm_input). auto/floor_mirror.py shows or saves the screen on a PC,
auto/floor_input.py presses and turns. Nothing changes on the unit's own screen or sound until a 0x51 comes.

The code goes in the local-SRAM cave (stage_main). The editor's command registrations (0x280ee594, called once at
boot) get an 8-byte trampoline to fm_regall, which runs them and then registers 0x52.

m4/floor_mirror.s is assembled with zig's clang (pip install ziglang): `python screen_mirror.py --assemble` writes
m4/floor_mirror.bin after checking m4/floor_mirror.json (symbol offsets). Both are committed so a build needs no
assembler. `--check` verifies a fresh assembly against both files without changing them; `--assemble --update-symbols`
explicitly accepts a reviewed source change that moves the symbol offsets.
"""
import json
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "m4", "floor_mirror.s")
BIN = os.path.join(HERE, "m4", "floor_mirror.bin")
SYMS = os.path.join(HERE, "m4", "floor_mirror.json")
ENABLED = os.environ.get("NAM_SCREEN_MIRROR") == "1"
REGALL = 0x280ee594                 # the editor's command registrations: the trampoline's site (4-byte aligned)

# Every firmware address floor_mirror.s uses, with its stock first bytes (found from HXtra's Stomp addresses by
# masked byte matching and the call graph; see docs/FINDINGS.md "Screen mirror")
STOCK = (
    (0x280ee594, "08b501f0c7ff01f003fe", "the editor's command registrations (push {r3, lr}; both replayed bl calls)"),
    (0x280ee19c, "7b280dd8", "the editor's command table setter (cmp r0, #0x7b; bhi)"),
    (0x280f77fc, "00207047", "the no-parameter check"),
    (0x280ed570, "022807d0054ba3f1", "the reply writer getter"),
    (0x280ed594, "022807d0054ba3f1", "the reply prefix length getter"),
    (0x280ed5b8, "022807d0054ba3f1", "the reply prefix getter"),
    (0x280ed5dc, "02280c4b4ff0", "the reply prefix reset"),
    (0x280ed620, "70b582b08323", "the reply map's head"),
    (0x10089148, "08b500f04df800b9", "the stream lock"),
    (0x10089168, "08b500f097f80020", "the stream unlock"),
    (0x10009bcc, "0120fff77fbf", "the microsecond clock (movs r0, #1; b.w the timer read)"),
    (0x1008971c, "09300928", "the task sleep"),
    (0x280f0528, "034b044a", "the registrations' first call"),
    (0x280f01a4, "10b584b0", "the registrations' second call"),
    (0x280ee59e, "01f013fe", "where the registrations go on after the trampoline (bl 0x280f01c8)"),
    (0x2808b668, "f8b505461148124e", "the UI's event post (push {r3-r7, lr}; mov r5, r0; ldr r0, =mutex; ldr r6, =lists)"),
)


def assemble(*, check=False, update_symbols=False):
    """Assemble in temporary files; validate symbol layout before publishing."""
    with tempfile.TemporaryDirectory() as d:
        source = os.path.join(d, "m.s")
        obj = os.path.join(d, "m.o")
        binary = os.path.join(d, "m.bin")
        with open(SRC, "rb") as f:
            source_bytes = f.read()
        with open(source, "wb") as f:
            f.write(source_bytes)
        zig = [sys.executable, "-m", "ziglang"]
        env = dict(os.environ, ZIG_LOCAL_CACHE_DIR=os.path.join(d, "local-cache"),
                   ZIG_GLOBAL_CACHE_DIR=os.path.join(d, "global-cache"))
        subprocess.run(zig + ["cc", "-target", "thumb-freestanding-eabi", "-mcpu=cortex_m4", "-c", source, "-o", obj],
                       check=True, timeout=60, env=env)
        subprocess.run(zig + ["objcopy", "-O", "binary", "-j", ".text", obj, binary], check=True, timeout=60, env=env)
        with open(obj, "rb") as f:
            b = f.read()
        with open(binary, "rb") as f:
            code = f.read()
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
                if name.startswith("fm_"):
                    syms[name] = val
    syms = dict(sorted(syms.items()))
    with open(SYMS) as f:
        expected = json.load(f)
    if syms != expected and (check or not update_symbols):
        raise ValueError("Assembled screen-mirror symbols differ from the committed map; review before --update-symbols.")
    if check:
        with open(BIN, "rb") as f:
            if f.read() != code:
                raise ValueError("Assembled screen-mirror bytes differ from the committed binary.")
    else:
        with open(BIN, "wb") as f:
            f.write(code)
        if syms != expected:
            with open(SYMS, "w") as f:
                json.dump(syms, f, indent=1)
    return code, syms


def load():
    return open(BIN, "rb").read(), json.load(open(SYMS))


def tramp(target):
    """ldr.w pc, [pc, #-0] ; .word target | 1"""
    return bytes.fromhex("5ff800f0") + struct.pack("<I", target | 1)


def check_stock(im):
    for va, want, what in STOCK:
        got = im.rd(va, len(want) // 2).hex()
        assert got == want, f"{va:#x} ({what}) is not stock: {got}"


def apply(im, code_va, syms):
    """Write the trampoline; the code itself is already in the cave at code_va."""
    check_stock(im)
    assert REGALL % 4 == 0 and code_va % 4 == 0
    im.wr(REGALL, tramp(code_va + syms["fm_regall"]))
    return (f"screen mirror: {len(load()[0])} B at {code_va:#x}; {REGALL:#x} -> ldr.w pc, [pc] ; "
            f".word {(code_va + syms['fm_regall']) | 1:#x}; editor command 0x52")


if __name__ == "__main__":
    if "--assemble" in sys.argv or "--check" in sys.argv:
        code, syms = assemble(check="--check" in sys.argv, update_symbols="--update-symbols" in sys.argv)
        print(len(code), "bytes;", syms)
