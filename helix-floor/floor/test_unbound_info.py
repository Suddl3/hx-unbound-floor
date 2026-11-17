"""Unicorn (Cortex-M4) test of m4/unbound_info.bin (unbound_info.py): the registrations through the trampoline (alone and
with the screen mirror's fm_regall), command 0x53's reply, the table's MessagePack and the build placing. Firmware
functions are Python stubs at their Floor addresses. Needs unicorn. usage: python test_unbound_info.py"""
import os
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_R7, UC_ARM_REG_R10, UC_ARM_REG_R11)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screen_mirror  # noqa: E402
import unbound_info  # noqa: E402

BASE = 0x1008c544                       # after segment 1 (any 4-aligned local SRAM address)
MIRROR = 0x1001f208
STUB = dict(REGISTER=0x280ee19c, NO_PARAMS=0x280f77fc, WRITER=0x280ed570, PREFIX_LEN=0x280ed594, PREFIX=0x280ed5b8,
            PREFIX_RESET=0x280ed5dc, REPLY_HEAD=0x280ed620, LOCK=0x10089148, UNLOCK=0x10089168,
            REGALL_A=0x280f0528, REGALL_B=0x280f01a4, REGALL_REST=0x280ee59e,
            S_WRITE=0x20001000, S_DONE=0x20001010, W_WRITE=0x20001020, CALLER=0x20001030)
ADDR = {v: k for k, v in STUB.items()}
STREAM, VTAB, WRITER_OBJ, PFX, PFX_LEN = 0x20002000, 0x20002100, 0x20002200, 0x20002300, 0x20002400
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R10, UC_ARM_REG_R11)
pfx = b"HEAD-MAP"
ENV = {"NAM_PAIR": "1", "NAM_SCREEN_MIRROR": "1", "NAM_DSP_METER": "1"}


def machine(module, mirror=False):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for base, size in ((0x10000000, 0x100000), (0x20000000, 0x100000), (0x28000000, 0x2000000)):
        mu.mem_map(base, size)
    mu.mem_write(BASE, module)
    if mirror:
        mu.mem_write(MIRROR, screen_mirror.load()[0])
    for a in STUB.values():
        mu.mem_write(a, b"\x70\x47")
    mu.mem_write(STREAM, struct.pack("<I", VTAB))
    mu.mem_write(VTAB, struct.pack("<4I", 0, STUB["S_WRITE"] | 1, 0, STUB["S_DONE"] | 1))
    mu.mem_write(WRITER_OBJ, struct.pack("<2I", 0xC0FFEE, STUB["W_WRITE"] | 1))
    st = {"log": [], "out": bytearray()}

    def r(reg):
        return mu.reg_read(reg)

    def ret(val=None):
        if val is not None:
            mu.reg_write(UC_ARM_REG_R0, val)
        mu.reg_write(UC_ARM_REG_PC, r(UC_ARM_REG_LR))

    def hook(uc, addr, size, _):
        name = ADDR.get(addr & ~1)
        if not name:
            return
        assert r(UC_ARM_REG_SP) % 8 == 0, f"stack is not 8-byte aligned at {name}"
        a0, a1, a2 = r(UC_ARM_REG_R0), r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)
        log = st["log"]
        log.append(name)
        if name == "REGISTER":
            log.append(("reg", a0, struct.unpack("<3I", bytes(uc.mem_read(a1, 12)))))
            ret(0)
        elif name == "WRITER":
            assert a0 == 6
            ret(WRITER_OBJ)
        elif name == "PREFIX_LEN":
            uc.mem_write(PFX_LEN, struct.pack("<I", len(pfx)))
            ret(PFX_LEN)
        elif name == "PREFIX":
            uc.mem_write(PFX, pfx)
            ret(PFX)
        elif name in ("PREFIX_RESET", "UNLOCK", "REGALL_A", "REGALL_B"):
            ret(0)
        elif name == "LOCK":
            assert a0 == STREAM - 8
            ret(0)
        elif name == "REPLY_HEAD":
            log.append(("head", a0, a1, a2))
            ret(0)
        elif name == "W_WRITE":
            log.append(("wwrite", bytes(uc.mem_read(a1, a2))))
            ret(0)
        elif name == "S_WRITE":
            assert a0 == STREAM
            st["out"].extend(uc.mem_read(a1, a2))
            ret(0)
        elif name == "S_DONE":
            log.append("done")
            ret(0x55)
        elif name == "REGALL_REST":         # the rest of the registrations: ...; movs r0, #0; pop {r3, pc}
            sp = r(UC_ARM_REG_SP)
            r3, pc = struct.unpack("<2I", bytes(uc.mem_read(sp, 8)))
            uc.reg_write(UC_ARM_REG_SP, sp + 8)
            uc.reg_write(UC_ARM_REG_R3, r3)
            uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, pc)
        elif name == "CALLER":
            uc.emu_stop()

    mu.hook_add(UC_HOOK_CODE, hook)

    def call(va, *args):
        for i, a in enumerate(args):
            mu.reg_write([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2][i], a)
        mu.reg_write(UC_ARM_REG_SP, 0x200F0000)
        mu.reg_write(UC_ARM_REG_LR, STUB["CALLER"] | 1)
        for reg in SAVED:
            mu.reg_write(reg, 0xA5A5A5A5)
        st["log"].clear()
        st["out"].clear()
        mu.emu_start(va | 1, 0, count=1_000_000)
        assert r(UC_ARM_REG_PC) & ~1 == STUB["CALLER"], hex(r(UC_ARM_REG_PC))
        assert r(UC_ARM_REG_SP) == 0x200F0000, "stack not balanced"
        assert all(r(reg) == 0xA5A5A5A5 for reg in SAVED), "callee-saved register clobbered"
        return r(UC_ARM_REG_R0)
    return mu, call, st


def registered(log):
    return [(x[1], x[2]) for x in log if isinstance(x, tuple) and x[0] == "reg"]


code, syms = unbound_info.load()
blocks = [(380, 3250)]
tab = unbound_info.table(blocks, ENV)

# the table: a MessagePack map the editor reads (checked against msgpack when it is installed)
assert tab == bytes.fromhex("83a3666d7401a6626c6f636b739192cd017ccd0cb2a46665617493a470616972a66d6972726f72a56d65746572"), tab.hex()
try:
    import msgpack
    assert msgpack.unpackb(tab) == {"fmt": 1, "blocks": [[380, 3250]], "feat": ["pair", "mirror", "meter"]}
except ImportError:
    pass
assert unbound_info.pack({"feat": ["focus", "art"]})[-14:] in unbound_info.table(blocks, {"NAM_EMMC_ART": "1"})   # implied focus
assert unbound_info.table([(380, 3600)], {}) == unbound_info.pack({"fmt": 1, "blocks": [[380, 3600]], "feat": []})

# alone: the stock registrations run (A, B, then the rest), then 0x53 with {ui_cmd, NO_PARAMS, 0}
module = unbound_info.build(BASE, blocks, None, ENV)
assert len(module) % 4 == 0 and module[:len(code)] != code          # ui_impl and ui_len are filled in
assert struct.unpack_from("<2I", module, syms["ui_impl"]) == ((BASE + syms["ui_stock"]) | 1, len(tab))
assert module[syms["ui_table"]:syms["ui_table"] + len(tab)] == tab
mu, call, st = machine(module)
assert call(BASE + syms["ui_regall"]) == 0
names = [x for x in st["log"] if isinstance(x, str)]
assert names[:3] == ["REGALL_A", "REGALL_B", "REGALL_REST"], names
assert registered(st["log"]) == [(0x53, ((BASE + syms["ui_cmd"]) | 1, STUB["NO_PARAMS"] | 1, 0))], registered(st["log"])

# the reply: {0x66: seq, 0x67: 0} head, then one message {u16 0, u16 6, u32 n} + the head's bytes + the table
req = 0x20003000
mu.mem_write(req, bytes(12) + struct.pack("<H", 0x1234))
assert call(BASE + syms["ui_cmd"], STREAM, req) == 0x55
log = st["log"]
assert ("head", WRITER_OBJ, 0x1234, 0) in log
assert log.index("LOCK") < log.index("done") < log.index("UNLOCK")
assert not [x for x in log if isinstance(x, tuple) and x[0] == "wwrite"]
m = bytes(st["out"])
assert m == struct.pack("<HHI", 0, 6, len(pfx) + len(tab)) + pfx + tab, m.hex()

# with the screen mirror: its fm_regall runs the registrations and registers 0x52, 0x51, 0x50; then 0x53
msyms = screen_mirror.load()[1]
module = unbound_info.build(BASE, blocks, MIRROR + msyms["fm_regall"], ENV)
assert struct.unpack_from("<I", module, syms["ui_impl"])[0] == (MIRROR + msyms["fm_regall"]) | 1
mu, call, st = machine(module, mirror=True)
assert call(BASE + syms["ui_regall"]) == 0
cmds = [c for c, _ in registered(st["log"])]
assert cmds == [0x52, 0x51, 0x50, 0x53], cmds
assert [x for x in st["log"] if isinstance(x, str)][:3] == ["REGALL_A", "REGALL_B", "REGALL_REST"]


# build placing: the trampoline replaces the mirror's, the stock bytes checked either way
class Im:
    def __init__(self, mem):
        self.mem = dict(mem)

    def rd(self, va, n):
        return bytes(self.mem.get(va + i, 0) for i in range(n))

    def wr(self, va, b):
        for i, x in enumerate(b):
            self.mem[va + i] = x


stock = {}
for va, want, _ in unbound_info.STOCK:
    for i, x in enumerate(bytes.fromhex(want)):
        stock[va + i] = x
im = Im(stock)
unbound_info.apply(im, BASE, blocks, None)
assert im.rd(unbound_info.REGALL, 8) == unbound_info.tramp(BASE + syms["ui_regall"])
im = Im(stock)
im.wr(screen_mirror.REGALL, screen_mirror.tramp(MIRROR + msyms["fm_regall"]))
unbound_info.apply(im, BASE, blocks, (MIRROR, b"", msyms))
assert im.rd(unbound_info.REGALL, 8) == unbound_info.tramp(BASE + syms["ui_regall"])
try:
    unbound_info.apply(Im(stock), BASE, blocks, (MIRROR, b"", msyms))
    raise AssertionError("applied over a missing mirror trampoline")
except AssertionError as e:
    assert "mirror's trampoline" in str(e)

unbound_info.assemble(check=True) if "--assemble-check" in sys.argv else None
print("unbound_info: registration alone and after the mirror, 0x53 reply and table, trampoline placing: OK")
