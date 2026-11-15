"""Emulator test of m4/emmc_art.bin (Focus View's picture read from the eMMC store, auto/floor_emmc_art.py)."""
import os
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_LR,
                               UC_ARM_REG_SP)

HERE = os.path.dirname(os.path.abspath(__file__))
code = bytearray(open(os.path.join(HERE, "m4", "emmc_art.bin"), "rb").read())
CACHED, IMGS_P, HDR_P, CACHE_P = (len(code) - 16 + 4 * i for i in range(4))
BASE, IMGS, FB = 0x29f01000, 0x1001fe64, 0x285a3f50
HDR, CACHE = struct.unpack_from("<2I", code, HDR_P)
struct.pack_into("<I", code, IMGS_P, IMGS)
mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
for b, s in ((0x10000000, 0x100000), (0x28000000, 0x2000000), (0x20000000, 0x10000)):
    mu.mem_map(b, s)
mu.mem_write(BASE, bytes(code))
STUBS = {0x281043e8: "sel", 0x28155f34: "memset", 0x28114a1c: "obj", 0x28148ccc: "desc", 0x1000504c: "read"}
for a in STUBS:
    mu.mem_write(a, b"\x70\x47")
S, N, FIRST = 20, 10, 0x400008                 # 20 x 20 = 800 B: 2 sectors a picture
SPP = (S * S * 2 + 511) // 512
emmc = {}
for k in range(3):
    pic = b"".join(bytes([k + 1, 0x40 + r]) * S for r in range(S))
    pic += bytes(SPP * 512 - len(pic))
    for j in range(SPP):
        emmc[FIRST + k * SPP + j] = pic[512 * j:512 * (j + 1)]
state = {"pid": 0, "ok": 0, "reads": [], "fail": False}


def hook(mu, addr, size, _):
    name = STUBS.get(addr)
    if not name:
        return
    assert mu.reg_read(UC_ARM_REG_SP) % 8 == 0, name
    if name == "sel":
        mu.reg_write(UC_ARM_REG_R0, 7)
    elif name == "obj":
        mu.reg_write(UC_ARM_REG_R0, 0x20004000)
    elif name == "desc":
        d = mu.reg_read(UC_ARM_REG_R2)
        pid = state["pid"] & 0xffffffff
        mu.mem_write(d, struct.pack("<I", (pid << 8) & 0xffffffff) + bytes([pid >> 24]))
        mu.reg_write(UC_ARM_REG_R0, state["ok"])
    elif name == "read":
        buf, sec, cnt = (mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        state["reads"].append((sec, cnt))
        if state["fail"]:
            mu.reg_write(UC_ARM_REG_R0, 0xfffffffd)
            return
        mu.mem_write(buf, b"".join(emmc.get(sec + j, bytes(512)) for j in range(cnt)))
        mu.reg_write(UC_ARM_REG_R0, 0)


mu.hook_add(UC_HOOK_CODE, hook)
RET = 0x20000100
mu.mem_write(RET, b"\x70\x47")
mp = [0xffff] * N
mp[5], mp[9] = 2, 0
mu.mem_write(HDR, struct.pack("<HHI", S, N, FIRST) + struct.pack(f"<{N}H", *mp))
mu.mem_write(IMGS, struct.pack("<5H", 4094, 400, 100, S, S))


def run(pid, ok=0, fail=False):
    state.update(pid=pid, ok=ok, fail=fail)
    state["reads"].clear()
    mu.mem_write(FB, bytes(800 * 480 * 2))
    mu.reg_write(UC_ARM_REG_R4, FB)
    mu.reg_write(UC_ARM_REG_SP, 0x20008000)
    mu.reg_write(UC_ARM_REG_LR, RET | 1)
    mu.emu_start(BASE | 1, RET)
    assert mu.reg_read(UC_ARM_REG_R4) == FB
    return bytes(mu.mem_read(FB, 800 * 480 * 2))


def drawn(fb, k):
    return all(fb[((100 + r) * 800 + 400 - S // 2) * 2:][:2 * S] == bytes([k + 1, 0x40 + r]) * S for r in range(S))


fb = run(5)
assert drawn(fb, 2) and state["reads"] == [(FIRST + 2 * SPP, SPP)]
assert sum(fb) == sum(sum(bytes([3, 0x40 + r]) * S) for r in range(S))
assert drawn(run(5), 2) and state["reads"] == []                   # cached: no read
assert drawn(run(9), 0) and state["reads"] == [(FIRST, SPP)]       # another picture: read
assert not any(run(3)) and not any(run(10)) and not any(run(-1)) and not any(run(5, ok=-1))
assert not any(run(5, fail=True)) and state["reads"]               # a failed read draws nothing...
assert drawn(run(5), 2) and state["reads"]                         # ...and is retried next time
print("emmc_art: picture by preset id from the eMMC, cache, none / past the map / empty / no block / read error: OK")
