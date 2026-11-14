"""Emulator test of m4/live_bulk.bin (the live poke's bulk write, uploaded at run time by auto/floor_poke.py)."""
import os
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP

HERE = os.path.dirname(os.path.abspath(__file__))
SET, UNSET, PTR = 68, 82, 92                  # set_check, unset_check, bulk_ptr in the blob
code = bytearray(open(os.path.join(HERE, "m4", "live_bulk.bin"), "rb").read())
FM_PTR, BASE, TBL, NO_PARAMS = 0x1001f5ec, 0x29f00800, 0x281c98c4, 0x280f77fd
assert struct.unpack_from("<2I", code, PTR + 4) == (TBL, NO_PARAMS)
struct.pack_into("<I", code, PTR, FM_PTR)
mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
for b, s in ((0x10000000, 0x100000), (0x28000000, 0x2000000), (0x20000000, 0x10000)):
    mu.mem_map(b, s)
mu.mem_write(BASE, bytes(code))
RET = 0x20000100
mu.mem_write(RET, b"\x70\x47")


def call(addr, r1=0):
    mu.reg_write(UC_ARM_REG_R1, r1)
    mu.reg_write(UC_ARM_REG_LR, RET | 1)
    mu.reg_write(UC_ARM_REG_SP, 0x20008000)
    mu.emu_start(addr | 1, RET)
    return mu.reg_read(UC_ARM_REG_R0)


def word(a):
    return struct.unpack("<I", mu.mem_read(a, 4))[0]


def check(param):
    req = b"\x83\x66\x00\x64\x50\x65" + param
    mu.mem_write(0x20001000, req)
    mu.mem_write(0x20000200, struct.pack("<3I", 0x20001000, len(req), 6))
    assert call(BASE, 0x20000200) == 0


mu.mem_write(TBL, struct.pack("<I", NO_PARAMS))
call(BASE + SET)
assert word(TBL) == BASE | 1
dst = 0x29f10000
mu.mem_write(FM_PTR, struct.pack("<I", dst))
for n, hdr in ((300, lambda n: b"\xda" + struct.pack(">H", n)), (200, lambda n: b"\xc4" + bytes([n])),
               (4000, lambda n: b"\xc5" + struct.pack(">H", n)), (40, lambda n: b"\xd9" + bytes([n]))):
    payload = os.urandom(n)
    check(hdr(n) + payload)
    assert bytes(mu.mem_read(dst, n)) == payload
    dst += n
    assert word(FM_PTR) == dst
check(b"\xc0")                                 # nil: nothing written
assert word(FM_PTR) == dst
call(BASE + UNSET)
assert word(TBL) == NO_PARAMS
print("live_bulk: str8/16, bin8/16, nil, set/unset check: OK")
