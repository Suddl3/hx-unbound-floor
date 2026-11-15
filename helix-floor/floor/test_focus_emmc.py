"""Emulator test of m4/focus_emmc.bin (Focus View's picture from the eMMC store, built in: NAM_EMMC_ART=1)."""
import os
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_LR, UC_ARM_REG_SP

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = open(os.path.join(HERE, "m4", "focus_emmc.bin"), "rb").read()
BASE, FB, STORE = 0x1008ba38, 0x285a3f50, 0x400000
STUBS = {0x281043e8: "sel", 0x28155f34: "memset", 0x28114a1c: "obj", 0x28148ccc: "desc", 0x1000504c: "read"}
S, N = 20, 10
SPP = (S * S * 2 + 511) // 512
FIRST = STORE + 8


def machine(with_store=True):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for b, s in ((0x10000000, 0x100000), (0x28000000, 0x2000000), (0x20000000, 0x10000)):
        mu.mem_map(b, s)
    mu.mem_write(BASE, CODE)
    for a in STUBS:
        mu.mem_write(a, b"\x70\x47")
    mu.mem_write(0x20000100, b"\x70\x47")
    emmc = {}
    if with_store:
        mp = [0xffff] * N
        mp[5], mp[9] = 2, 0
        hdr = b"HXPC" + bytes(12) + struct.pack("<HHI", S, N, FIRST) + struct.pack(f"<{N}H", *mp)
        hdr += bytes(8 * 512 - len(hdr))
        for j in range(8):
            emmc[STORE + j] = hdr[512 * j:512 * (j + 1)]
        for k in range(3):
            pic = b"".join(bytes([k + 1, 0x40 + r]) * S for r in range(S))
            pic += bytes(SPP * 512 - len(pic))
            for j in range(SPP):
                emmc[FIRST + k * SPP + j] = pic[512 * j:512 * (j + 1)]
    st = {"pid": 0, "ok": 0, "reads": [], "fail": False}

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
            pid = st["pid"] & 0xffffffff
            mu.mem_write(d, struct.pack("<I", (pid << 8) & 0xffffffff) + bytes([pid >> 24]))
            mu.reg_write(UC_ARM_REG_R0, st["ok"])
        elif name == "read":
            buf, sec, cnt = (mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            st["reads"].append((sec, cnt))
            if st["fail"]:
                mu.reg_write(UC_ARM_REG_R0, 0xfffffffd)
                return
            mu.mem_write(buf, b"".join(emmc.get(sec + j, bytes(512)) for j in range(cnt)))
            mu.reg_write(UC_ARM_REG_R0, 0)

    mu.hook_add(UC_HOOK_CODE, hook)

    def run(pid, ok=0, fail=False):
        st.update(pid=pid, ok=ok, fail=fail)
        st["reads"].clear()
        mu.mem_write(FB, bytes(800 * 480 * 2))
        mu.reg_write(UC_ARM_REG_R4, FB)
        mu.reg_write(UC_ARM_REG_SP, 0x20008000)
        mu.reg_write(UC_ARM_REG_LR, 0x20000101)
        mu.emu_start((BASE + 0x400) | 1, 0x20000100)
        assert mu.reg_read(UC_ARM_REG_R4) == FB
        return bytes(mu.mem_read(FB, 800 * 480 * 2))
    return run, st


def drawn(fb, k):
    top = 196 - S // 2
    return all(fb[((top + r) * 800 + 400 - S // 2) * 2:][:2 * S] == bytes([k + 1, 0x40 + r]) * S for r in range(S))


run, st = machine()
fb = run(5)
assert st["reads"] == [(STORE, 8), (FIRST + 2 * SPP, SPP)] and drawn(fb, 2)     # header on the first call, then the picture
assert sum(fb) == sum(sum(bytes([3, 0x40 + r]) * S) for r in range(S))
assert drawn(run(5), 2) and st["reads"] == []                                  # header kept, picture cached
assert drawn(run(9), 0) and st["reads"] == [(FIRST, SPP)]
assert not any(run(3)) and not any(run(10)) and not any(run(-1)) and not any(run(5, ok=-1))
assert not any(run(5, fail=True)) and drawn(run(5), 2)                         # a failed read is retried
run, st = machine(with_store=False)
assert not any(run(5)) and st["reads"] == [(STORE, 8)]                         # no store: the header read once...
assert not any(run(5)) and st["reads"] == []                                   # ...and never again
print("focus_emmc: header read once, picture by preset id, cache, retry, none / empty / no block, no store: OK")
