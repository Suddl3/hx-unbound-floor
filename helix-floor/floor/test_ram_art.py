"""Emulator test of m4/ram_art.bin (Focus View's picture from RAM, uploaded at run time by auto/floor_ram_art.py)."""
import os
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_SP)

HERE = os.path.dirname(os.path.abspath(__file__))
code = bytearray(open(os.path.join(HERE, "m4", "ram_art.bin"), "rb").read())
DM_IMGS_P, PIC_BASE_P = len(code) - 8, len(code) - 4
assert struct.unpack_from("<I", code, PIC_BASE_P)[0] == 0x29900000
BASE, IMGS, PICS, FB = 0x29f01000, 0x1001fe64, 0x29900000, 0x285a3f50
struct.pack_into("<I", code, DM_IMGS_P, IMGS)
mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
for b, s in ((0x10000000, 0x100000), (0x28000000, 0x2000000), (0x20000000, 0x10000)):
    mu.mem_map(b, s)
mu.mem_write(BASE, bytes(code))
STUBS = {0x281043e8: "sel", 0x28155f34: "memset", 0x28114a1c: "obj", 0x28148ccc: "desc"}
for a in STUBS:
    mu.mem_write(a, b"\x70\x47")
state = {"pid": 0, "desc_ok": 0}
calls = []


def hook(mu, addr, size, _):
    name = STUBS.get(addr)
    if not name:
        return
    sp = mu.reg_read(UC_ARM_REG_SP)
    calls.append((name, sp % 8))
    if name == "sel":
        mu.reg_write(UC_ARM_REG_R0, 7)
    elif name == "obj":
        mu.reg_write(UC_ARM_REG_R0, 0x20004000)
    elif name == "desc":
        d = mu.reg_read(UC_ARM_REG_R2)
        pid = state["pid"] & 0xffffffff
        mu.mem_write(d, struct.pack("<I", (pid << 8) & 0xffffffff) + bytes([pid >> 24]))
        mu.reg_write(UC_ARM_REG_R0, state["desc_ok"])


mu.hook_add(UC_HOOK_CODE, hook)
RET = 0x20000100
mu.mem_write(RET, b"\x70\x47")

S, N = 4, 10
pics = [bytes([k + 1, 0x40 + r]) * S for k in range(3) for r in range(S)]   # 3 pictures, rows tagged
pix = b"".join(pics)
mp = [0xffff] * N
mp[5], mp[9] = 2, 0
hdr = struct.pack("<HHI", S, N, 8 + 2 * N + 4) + struct.pack(f"<{N}H", *mp) + bytes(4)
mu.mem_write(PICS, hdr + pix)
mu.mem_write(IMGS, struct.pack("<5H", 4094, 400, 100, S, S))


def run(pid, ok=0):
    state.update(pid=pid, desc_ok=ok)
    mu.mem_write(FB, bytes(800 * 480 * 2))
    calls.clear()
    mu.reg_write(UC_ARM_REG_R4, FB)
    mu.reg_write(UC_ARM_REG_SP, 0x20008000)
    mu.reg_write(UC_ARM_REG_LR, RET | 1)
    mu.emu_start(BASE | 1, RET)
    assert mu.reg_read(UC_ARM_REG_R4) == FB
    assert all(al == 0 for _, al in calls), calls          # 8-byte aligned at every firmware call
    return bytes(mu.mem_read(FB, 800 * 480 * 2))


fb = run(5)
for r in range(S):
    off = ((100 + r) * 800 + 400 - S // 2) * 2
    assert fb[off:off + 2 * S] == bytes([3, 0x40 + r]) * S, (r, fb[off:off + 2 * S].hex())
    assert fb[off - 2:off] == bytes(2) and fb[off + 2 * S:off + 2 * S + 2] == bytes(2)
assert sum(fb) == sum(sum(bytes([3, 0x40 + r]) * S) for r in range(S))      # nothing else drawn
assert run(9)[((100) * 800 + 398) * 2] == 1                 # picture 0
assert not any(run(3)) and not any(run(10)) and not any(run(-1)) and not any(run(5, ok=-1))   # none, past the map, empty, no block
print("ram_art: picture by preset id, placement, none / past the map / empty / no block, alignment: OK")
