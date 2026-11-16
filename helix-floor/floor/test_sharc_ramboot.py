"""Emulator test of m4/sharc_ramboot.bin (SHARC dev mode: the DSP boot fed from RAM). The firmware's boot is replaced by a
routine that does what the real one does with its two stream objects: reads them through class slot 0, as the stock stream
read is called (read(obj, buf, n) -> n or < 0)."""
import os
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_LR,
                               UC_ARM_REG_SP, UC_ARM_REG_PC)

HERE = os.path.dirname(os.path.abspath(__file__))
code = open(os.path.join(HERE, "m4", "sharc_ramboot.bin"), "rb").read()
RUN = 0x34                                      # sr_run's offset (m4/sharc_ramboot.s: first thumb_func after sr_ret0)
BASE, CTL, IMG, BOOT = 0x29f03000, 0x29f05000, 0x29a00000, 0x100059e0
ret = 0x29f0f001

mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
mu.mem_map(0x28000000, 0x2000000)
mu.mem_map(0x20000000, 0x10000)
mu.mem_map(0x10000000, 0x100000)
mu.mem_write(BASE, code)
image = bytes((i * 7 + (i >> 8)) & 0xff for i in range(5000))
mu.mem_write(IMG, image)
mu.mem_write(CTL, struct.pack("<3I", 0x7fffffff, IMG, len(image)))
mu.mem_write(BOOT, b"\x70\x47")                 # bx lr: the hook below does the work
log = {"calls": 0, "got": [b"", b""], "boot_r0": None, "over": None}


def u32(a):
    return struct.unpack("<I", bytes(mu.mem_read(a, 4)))[0]


def run_read(obj, buf, n):
    """Call the object's class slot 0 the way the boot does."""
    mu.reg_write(UC_ARM_REG_R0, obj)
    mu.reg_write(UC_ARM_REG_R1, buf)
    mu.reg_write(UC_ARM_REG_R2, n)
    mu.reg_write(UC_ARM_REG_LR, ret)
    mu.reg_write(UC_ARM_REG_SP, 0x20008000)
    fn = u32(u32(obj))
    assert fn & 1, "class slot 0 must be a Thumb address"
    mu.emu_start(fn, ret & ~1)
    return struct.unpack("<i", struct.pack("<I", mu.reg_read(UC_ARM_REG_R0)))[0]


def hook(mu_, addr, size, _):
    if addr == BOOT:
        log["boot_r0"] = mu_.reg_read(UC_ARM_REG_R0)
        sp, lr = mu_.reg_read(UC_ARM_REG_SP), mu_.reg_read(UC_ARM_REG_LR)
        assert sp % 8 == 0, "the boot must be entered 8-byte aligned"
        arr = log["boot_r0"]
        objs = [u32(arr), u32(arr + 4)]
        log["objs"] = objs


mu.hook_add(UC_HOOK_CODE, hook, begin=BOOT, end=BOOT + 2)
mu.reg_write(UC_ARM_REG_LR, ret)
mu.reg_write(UC_ARM_REG_SP, 0x20008000)
mu.emu_start((BASE + RUN) | 1, ret & ~1)

assert log["boot_r0"] == CTL + 0x60, hex(log["boot_r0"] or 0)
a, b = log["objs"]
assert (a, b) == (CTL + 0x20, CTL + 0x40)
for o in (a, b):
    assert u32(o) == CTL + 0x80 and u32(o + 4) == 0 and u32(o + 8) == IMG and u32(o + 12) == len(image)
assert u32(CTL) == CTL + 0x60, "the boot's return value (the emulated bx lr leaves r0 = the array) is stored at CTL"

# the boot's reads: 4 bytes at a time, then odd sizes, both streams independent, then past the end
BUF = 0x29f08000
for o in (a, b):
    got = bytearray()
    for n in (4, 4, 12, 1, 100, 4):
        assert run_read(o, BUF, n) == n
        got += bytes(mu.mem_read(BUF, n))
    assert bytes(got) == image[:len(got)], "stream read does not match the image"
    pos = u32(o + 4)
    assert pos == len(got)
    assert run_read(o, BUF, len(image)) < 0, "a read past the end must fail"
    assert u32(o + 4) == pos, "a failed read must not move the position"
# the unused class slots return 0
for k in range(1, 8):
    mu.reg_write(UC_ARM_REG_R0, a)
    mu.reg_write(UC_ARM_REG_LR, ret)
    mu.reg_write(UC_ARM_REG_SP, 0x20008000)
    fn = u32(CTL + 0x80 + 4 * k)
    assert fn & 1
    mu.emu_start(fn, ret & ~1)
    assert mu.reg_read(UC_ARM_REG_R0) == 0
print("test_sharc_ramboot: ok")

# sr_full (experiment 2): the call order of the teardown + boot + bring-up, every firmware routine replaced by "return 0"
FULL = 0xb0
order = [0x1000e2d0, BOOT, 0x28114c64, 0x28156c68, 0x28156c68, 0x28156b30, 0x28114cac, 0x28156a48, 0x281569e8, 0x281569e8,
         0x281568b8, 0x28156cb8, 0x28156cb8]
seen = []
for a in set(order):
    mu.mem_write(a, b"\x00\x20\x70\x47")         # movs r0, #0; bx lr
mu.ctl_flush_tb()
mu.mem_write(0x2811641c, struct.pack("<7I", *range(0x100, 0x107)))
mu.mem_write(0x28116438, struct.pack("<7I", *range(0x200, 0x207)))
args = []


def hook2(mu_, addr, size, _):
    if addr in order:
        seen.append(addr)
        if addr == 0x28156c68:
            args.append(tuple(mu_.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)))


for a in set(order):
    mu.hook_add(UC_HOOK_CODE, hook2, begin=a, end=a + 1)
mu.mem_write(CTL, struct.pack("<6I", 0x7fffffff, IMG, len(image), 0, 0, 99))
mu.reg_write(UC_ARM_REG_LR, ret)
mu.reg_write(UC_ARM_REG_SP, 0x20008000)
mu.emu_start((BASE + FULL) | 1, ret & ~1)
assert seen == order, [hex(x) for x in seen]
assert args == [(0x282c5780, 0x2971dbd4, 0xb, 0x890d), (0x282c57ec, 0x2981dbd4, 2, 0x9110)], args
assert u32(CTL + 0x18) == 99 and u32(CTL + 0x1c) == 0, (u32(CTL + 0x14), u32(CTL + 0x18), u32(CTL + 0x1c))
print("test_sharc_ramboot sr_full: ok")
