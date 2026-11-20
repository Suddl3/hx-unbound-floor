"""Editor command 0x4f for HX Edit Unbound: which firmware this is (on in every build; env NAM_UNBOUND_INFO=0 leaves it out).

HX Edit sums each block's DSP load from its own catalog, so the editor has to know the NAM blocks this image has and
their costs (3600 standard, 3250 with the PAIR kernel, and later the NAM Pedal block). The reply's result is a fixed
MessagePack map the build writes after the code:

    {"fmt": 1, "blocks": [[preset id, DSP cost], ...], "feat": ["mirror", "meter", ...]}

`fmt` changes only when a key changes meaning; the editor ignores keys it does not know. Stock firmware and older
builds answer 0x4f with an error status, and the editor then falls back to its own setting. auto/floor_info.py asks
from the PC (HX Edit closed).

m4/unbound_info.s goes after segment 1's bytes (local SRAM bank 2, behind the Focus View reader and the clock-stop
wrappers when they are built in). It owns the trampoline at the editor's command registrations (0x280ee594): it runs
the screen mirror's fm_regall when the mirror is built in, else its own copy of the stock registrations, then registers
0x4f. Assembled with zig's clang like the mirror: `python unbound_info.py --assemble` writes m4/unbound_info.bin and
checks m4/unbound_info.json (symbol offsets); `--check` verifies both without changing them.
"""
import json
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "m4", "unbound_info.s")
BIN = os.path.join(HERE, "m4", "unbound_info.bin")
SYMS = os.path.join(HERE, "m4", "unbound_info.json")
ENABLED = os.environ.get("NAM_UNBOUND_INFO") != "0"      # on by default; NAM_UNBOUND_INFO=0 leaves it out
CMD = 0x4f                              # stock uses 0x53; 0x50..0x52 are the mirror's
FORMAT = 1
REGALL = 0x280ee594
MAX_TABLE = 200                         # the reply stays far below an editor message's size

# Build flags reported as features (the editor shows them; only "blocks" changes what it offers)
FEATURES = (("pair", "NAM_PAIR"), ("mirror", "NAM_SCREEN_MIRROR"), ("meter", "NAM_DSP_METER"),
            ("focus", "NAM_FOCUS_VIEW"), ("art", "NAM_EMMC_ART"), ("clk", "NAM_CLK_STOP"))

# The addresses unbound_info.s uses, with their stock first bytes (the same ones the screen mirror checks)
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
    (0x280f0528, "034b044a", "the registrations' first call"),
    (0x280f01a4, "10b584b0", "the registrations' second call"),
    (0x280ee59e, "01f013fe", "where the registrations go on after the trampoline (bl 0x280f01c8)"),
)


def pack(value):
    """The MessagePack subset the table needs: small maps, arrays, short strings, non-negative ints, None, bools."""
    if value is None:
        return b"\xc0"
    if value is True or value is False:
        return b"\xc3" if value else b"\xc2"
    if isinstance(value, int):
        assert 0 <= value < 1 << 16, value
        return bytes([value]) if value < 0x80 else b"\xcd" + struct.pack(">H", value)
    if isinstance(value, str):
        raw = value.encode("ascii")
        assert len(raw) < 32
        return bytes([0xa0 | len(raw)]) + raw
    if isinstance(value, (list, tuple)):
        assert len(value) < 16
        return bytes([0x90 | len(value)]) + b"".join(pack(v) for v in value)
    if isinstance(value, dict):
        assert len(value) < 16
        return bytes([0x80 | len(value)]) + b"".join(pack(k) + pack(v) for k, v in value.items())
    raise TypeError(type(value))


def table(blocks, env=None):
    """The reply's map. blocks: [(preset id, DSP cost), ...] of the NAM blocks this image has."""
    env = os.environ if env is None else env
    data = {"fmt": FORMAT, "blocks": [[int(pid), int(cost)] for pid, cost in blocks],
            "feat": [name for name, flag in FEATURES if env.get(flag) == "1"
                     or (name == "focus" and env.get("NAM_EMMC_ART") == "1")]}     # the eMMC pictures imply Focus View
    raw = pack(data)
    assert len(raw) <= MAX_TABLE, f"the info table is {len(raw)} bytes"
    return raw


def assemble(*, check=False, update_symbols=False):
    """Assemble in temporary files; validate symbol layout before publishing (as screen_mirror.assemble)."""
    with tempfile.TemporaryDirectory() as d:
        source, obj, binary = (os.path.join(d, n) for n in ("m.s", "m.o", "m.bin"))
        with open(SRC, "rb") as f, open(source, "wb") as g:
            g.write(f.read())
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
                if name.startswith("ui_"):
                    syms[name] = val
    syms = dict(sorted(syms.items()))
    expected = json.load(open(SYMS)) if os.path.isfile(SYMS) else None
    if syms != expected and (check or (expected is not None and not update_symbols)):
        raise ValueError("Assembled unbound-info symbols differ from the committed map; review before --update-symbols.")
    if check:
        with open(BIN, "rb") as f:
            if f.read() != code:
                raise ValueError("Assembled unbound-info bytes differ from the committed binary.")
    else:
        with open(BIN, "wb") as f:
            f.write(code)
        if syms != expected:
            with open(SYMS, "w") as f:
                json.dump(syms, f, indent=1)
    return code, syms


def load():
    return open(BIN, "rb").read(), json.load(open(SYMS))


def build(code_va, blocks, mirror_regall=None, env=None):
    """The module's bytes at code_va: the code, ui_impl (the mirror's fm_regall, or ui_stock), ui_len and the table."""
    code, syms = load()
    assert len(code) == syms["ui_table"], "the table must follow the code"
    assert code_va % 4 == 0
    raw = table(blocks, env)
    impl = (mirror_regall if mirror_regall is not None else code_va + syms["ui_stock"]) | 1
    out = bytearray(code)
    struct.pack_into("<II", out, syms["ui_impl"], impl, len(raw))
    assert syms["ui_len"] == syms["ui_impl"] + 4
    return bytes(out) + raw + bytes(-len(raw) % 4)


def tramp(target):
    """ldr.w pc, [pc, #-0] ; .word target | 1"""
    return bytes.fromhex("5ff800f0") + struct.pack("<I", target | 1)


def check_stock(im):
    for va, want, what in STOCK:
        got = im.rd(va, len(want) // 2).hex()
        assert got == want, f"{va:#x} ({what}) is not stock: {got}"


def apply(im, code_va, blocks, mirror):
    """Write the trampoline over the registrations (after the mirror's, which it replaces: the module calls fm_regall).
    The stock bytes are checked first, on the stock image or on the mirror's trampoline."""
    syms = load()[1]
    if mirror:
        import screen_mirror
        assert im.rd(REGALL, 8) == screen_mirror.tramp(mirror[0] + mirror[2]["fm_regall"]), "the mirror's trampoline is not in place"
        check_stock_after_mirror(im)
    else:
        check_stock(im)
    im.wr(REGALL, tramp(code_va + syms["ui_regall"]))
    return (f"unbound info: {code_va:#x}; {REGALL:#x} -> ldr.w pc, [pc] ; .word {(code_va + syms['ui_regall']) | 1:#x}; "
            f"editor command 0x4f, table " + table(blocks).hex())


def check_stock_after_mirror(im):
    for va, want, what in STOCK[1:]:                    # the registrations' first 8 bytes hold the mirror's trampoline
        got = im.rd(va, len(want) // 2).hex()
        assert got == want, f"{va:#x} ({what}) is not stock: {got}"


if __name__ == "__main__":
    if "--assemble" in sys.argv or "--check" in sys.argv:
        code, syms = assemble(check="--check" in sys.argv, update_symbols="--update-symbols" in sys.argv)
        print(f"{len(code)} bytes; {syms}")
    else:
        print(__doc__)
