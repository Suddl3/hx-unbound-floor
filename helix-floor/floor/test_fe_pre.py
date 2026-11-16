"""Emulator test of fe_pre in m4/focus_emmc.bin (Focus View's exit cleanup in the paint task): with Focus View off and scene pixels
left in the frame the paths' area is blanked and the view's full-repaint flag set before the stock paint; otherwise nothing but the
stock paint; the stock paint's result is kept at [sp, #0x80] and the code goes on at fp_ret."""
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R12, UC_ARM_REG_LR, UC_ARM_REG_SP, UC_ARM_REG_PC)
import focus_emmc

BASE, FB, VIEW, DMCFG, RET = focus_emmc.VA, 0x285A3F50, 0x20004000, 0x1001FEDC, 0x1001FA35
STOCK, MEMSET, FINISH = 0x280D6BE8, 0x28155F34, 0x1001FA34
CODE = focus_emmc.with_literals(focus_emmc.load(), DMCFG, 0x1001FC46, RET)
ROW = 1600


def run(focus, lit_pixels, stale_flag=0):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for b, s in ((0x10000000, 0x100000), (0x28000000, 0x2000000), (0x20000000, 0x10000)):
        mu.mem_map(b, s)
    mu.mem_write(BASE, CODE)
    mu.mem_write(DMCFG, bytes([1, 1, focus, 0]))
    mu.mem_write(FB, b"\x55" * (480 * ROW))                                   # a frame full of something
    clean = bytearray(480 * ROW)                                              # black everywhere but where asked
    for (x, y) in lit_pixels:
        clean[y * ROW + 2 * x:y * ROW + 2 * x + 2] = b"\x34\x12"
    mu.mem_write(FB, bytes(clean))
    mu.mem_write(VIEW + 0x5F, bytes([stale_flag]))
    mu.mem_write(STOCK, b"\x70\x47")
    mu.mem_write(MEMSET, b"\x70\x47")
    mu.mem_write(FINISH, b"\x70\x47")
    log = []

    def hook(mu_, addr, size, _):
        sp = mu_.reg_read(UC_ARM_REG_SP)
        if addr == STOCK:
            assert sp % 8 == 0, "the stock paint must be called 8-byte aligned"
            log.append(("stock", mu_.reg_read(UC_ARM_REG_R0), mu_.reg_read(UC_ARM_REG_R1), mu_.mem_read(VIEW + 0x5F, 1)[0]))
            mu_.reg_write(UC_ARM_REG_R0, 0x77)                                # the stock paint's result
        elif addr == MEMSET:
            assert sp % 8 == 0, "memset must be called 8-byte aligned"
            log.append(("memset", mu_.reg_read(UC_ARM_REG_R0), mu_.reg_read(UC_ARM_REG_R1), mu_.reg_read(UC_ARM_REG_R2)))

    for a in (STOCK, MEMSET):
        mu.hook_add(UC_HOOK_CODE, hook, begin=a, end=a + 1)
    sp = 0x20008000
    mu.reg_write(UC_ARM_REG_SP, sp)
    mu.reg_write(UC_ARM_REG_R4, FB)
    mu.reg_write(UC_ARM_REG_R5, VIEW)
    mu.reg_write(UC_ARM_REG_R0, FB)
    mu.reg_write(UC_ARM_REG_R1, VIEW)
    mu.reg_write(UC_ARM_REG_R6, 0x1234)
    mu.reg_write(UC_ARM_REG_R7, 0x5678)
    mu.reg_write(UC_ARM_REG_R12, 0x9ABC)
    mu.emu_start((BASE + focus_emmc.PRE) | 1, FINISH, count=2000)
    assert mu.reg_read(UC_ARM_REG_PC) == FINISH, "fe_pre must end at fp_ret (the build's return address)"
    log.append(("ret", mu.reg_read(UC_ARM_REG_R6)))
    kept = struct.unpack("<I", mu.mem_read(sp + 0x80, 4))[0]
    return log, kept, mu.mem_read(VIEW + 0x5F, 1)[0], mu.reg_read(UC_ARM_REG_R6)


# focus on: just the stock paint
log, kept, flag, r6 = run(1, [(300, 180)])
assert [l[0] for l in log] == ["stock", "ret"], log
assert kept == 0x77 and flag == 0 and r6 == 0x1234, (kept, flag, r6)
# focus off, frame clean: just the stock paint
log, kept, flag, r6 = run(0, [])
assert [l[0] for l in log] == ["stock", "ret"] and flag == 0 and kept == 0x77, log
# focus off, a lit probe pixel (each of the twelve in turn): blank the paths' area, set the flag, then the stock paint
for x in range(150, 701, 50):
    log, kept, flag, r6 = run(0, [(x, 180)])
    assert [l[0] for l in log] == ["memset", "stock", "ret"], (x, log)
    assert log[0][1:] == (FB + 52 * ROW, 0, 288 * ROW), log[0]
    assert log[1][3] == 1, "the full-repaint flag must be set before the stock paint"
    assert kept == 0x77 and r6 == 0x1234, (kept, r6)
# a lit pixel outside the probes is not seen
log, kept, flag, r6 = run(0, [(155, 180), (300, 181)])
assert [l[0] for l in log] == ["stock", "ret"], log
print("fe_pre: focus on / clean frame untouched; twelve probes; blank + flag before the stock paint; result and return kept: OK")
