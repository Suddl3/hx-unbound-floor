"""Emulator test of m4/focus_emmc.bin (Focus View's picture from the eMMC store, built in: NAM_EMMC_ART=1)."""
import os
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_LR, UC_ARM_REG_SP

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = open(os.path.join(HERE, "m4", "focus_emmc.bin"), "rb").read()
BASE, FB, STORE = 0x1008ba38, 0x285a3f50, 0x400000
STUBS = {0x281043e8: "sel", 0x28155f34: "memset", 0x28114a1c: "obj", 0x28148ccc: "desc", 0x1000504c: "read", 0x2813aab8: "param"}
S, N = 20, 10
SPP = (S * S * 2 + 511) // 512
FIRST = STORE + 12


BGFIRST, Y0, ROWS, BGN = 0x460000, 52, 8, 2          # backgrounds: 2 of 8 rows of 800 pixels, from row 52
BGSPB = (ROWS * 1600 + 511) // 512


def bg_section(count=BGN, spb=BGSPB, y0=Y0, rows=ROWS, magic=b"HXBG", slots=None, mode=0):
    slots = slots if slots is not None else {5: 1, 9: 0, 7: 0xFF}
    sec = magic + struct.pack("<HHIHHHH", count, spb, BGFIRST, y0, rows, mode, 0) + bytes(4)
    return sec + bytes(slots.get(i, 0xFF) for i in range(N))


STORED_SEC, STB, STORED_WORD = 0x45fffe, 0x29902000, 0x281ee64c


def stored_table(entries, n=640, magic=b"HXSB"):
    t = magic + struct.pack("<HH", n, 0) + bytes(0xFF if i not in entries else entries[i] for i in range(min(n, 1016)))
    return t + bytes(1024 - len(t))


def machine(with_store=True, bg=None, setb=False, nam=False, stored=None, holes=False):
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
        mp[5], mp[9], mp[7] = 2, 0, 1
        hdr = b"HXPC" + bytes(12) + struct.pack("<HHI", S, N, FIRST) + struct.pack(f"<{N}H", *mp)
        hdr += bytes(12 * 512 - len(hdr))
        if bg is not None:
            hdr = hdr[:2048] + bg + hdr[2048 + len(bg):]
            if setb:                                      # set B: pid 5 -> picture 0 on slot 0 (set A: picture 2, slot 1)
                mb = [0xFFFF] * N
                mb[5] = 0
                hdr = hdr[:3072] + struct.pack(f"<{N}H", *mb) + hdr[3072 + 2 * N:]
                sb = bytes([0xFF] * N)
                sb = sb[:5] + bytes([0]) + sb[6:]
                hdr = hdr[:5072] + sb + hdr[5072 + N:]
            for k in range(BGN):                          # background k: row r is bytes [0xA0 + k, r] x 800
                data = b"".join(bytes([0xA0 + k, r]) * 800 for r in range(ROWS)) 
                data += bytes(BGSPB * 512 - len(data))
                for j in range(BGSPB):
                    emmc[BGFIRST + k * BGSPB + j] = data[512 * j:512 * (j + 1)]
        if nam:                                           # pid 9 is the NAM block: capture slot 3 -> picture 1, slot 4 -> 0xffff
            tab = [0xFFFF] * 128
            tab[2] = 1
            hdr = hdr[:1784] + struct.pack("<H", 9 + 1) + bytes(6) + struct.pack("<128H", *tab) + hdr[1784 + 8 + 256:]
        for j in range(12):
            emmc[STORE + j] = hdr[512 * j:512 * (j + 1)]
        for k in range(3):
            pic = b"".join(bytes([k + 1, 0x40 + r]) * S for r in range(S))
            if holes and k == 2:                          # picture 2: bit 15 set on its first four columns (see-through)
                pic = b"".join((bytes([k + 1, 0xC0 + r]) * 4 + bytes([k + 1, 0x40 + r]) * (S - 4)) for r in range(S))
            pic += bytes(SPP * 512 - len(pic))
            for j in range(SPP):
                emmc[FIRST + k * SPP + j] = pic[512 * j:512 * (j + 1)]
    if stored is not None:
        for j in range(2):
            emmc[STORED_SEC + j] = stored[512 * j:512 * (j + 1)]
    st = {"pid": 0, "ok": 0, "reads": [], "fail": False, "slot": 0, "asked": 0, "sbreads": [], "preset": 0}

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
        elif name == "param":                            # the block title's reader: the capture slot as knob 0's value (<< 8)
            st["asked"] += 1
            assert mu.reg_read(UC_ARM_REG_R1) == 7                       # asked for the selected block
            mu.mem_write(mu.reg_read(UC_ARM_REG_R3), struct.pack("<I", st["slot"] << 8) + bytes(8))
        elif name == "read":
            buf, sec, cnt = (mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            (st["sbreads"] if sec == STORED_SEC else st["reads"]).append((sec, cnt))
            if st["fail"]:
                mu.reg_write(UC_ARM_REG_R0, 0xfffffffd)
                return
            mu.mem_write(buf, b"".join(emmc.get(sec + j, bytes(512)) for j in range(cnt)))
            mu.reg_write(UC_ARM_REG_R0, 0)

    mu.hook_add(UC_HOOK_CODE, hook)

    def run(pid, ok=0, fail=False, slot=0, preset=None):
        st.update(pid=pid, ok=ok, fail=fail, slot=slot)
        if preset is not None:
            st["preset"] = preset
        mu.mem_write(STORED_WORD, struct.pack("<I", st["preset"]))
        st["reads"].clear()
        mu.mem_write(FB, bytes(800 * 480 * 2))
        mu.reg_write(UC_ARM_REG_R4, FB)
        mu.reg_write(UC_ARM_REG_SP, 0x20008000)
        mu.reg_write(UC_ARM_REG_LR, 0x20000101)
        mu.emu_start((BASE + 0x540) | 1, 0x20000100)
        assert mu.reg_read(UC_ARM_REG_R4) == FB
        return bytes(mu.mem_read(FB, 800 * 480 * 2))
    return run, st


def drawn(fb, k):
    top = 196 - S // 2
    return all(fb[((top + r) * 800 + 400 - S // 2) * 2:][:2 * S] == bytes([k + 1, 0x40 + r]) * S for r in range(S))


run, st = machine()
fb = run(5)
assert st["reads"] == [(STORE, 12), (FIRST + 2 * SPP, SPP)] and drawn(fb, 2)     # header on the first call, then the picture
assert sum(fb) == sum(sum(bytes([3, 0x40 + r]) * S) for r in range(S))
assert drawn(run(5), 2) and st["reads"] == []                                  # header kept, picture cached
assert drawn(run(9), 0) and st["reads"] == [(FIRST, SPP)]
assert not any(run(3)) and not any(run(10)) and not any(run(-1)) and not any(run(5, ok=-1))
assert not any(run(5, fail=True)) and drawn(run(5), 2)                         # a failed read is retried
run, st = machine(with_store=False)
assert not any(run(5)) and st["reads"] == [(STORE, 12)]                         # no store: the header read once...
assert not any(run(5)) and st["reads"] == []                                   # ...and never again

def bgdrawn(fb, k):
    return all(fb[(Y0 + r) * 1600:][:1600] == bytes([0xA0 + k, r]) * 800 for r in range(ROWS))


def bgnone(fb):
    return not any(fb[Y0 * 1600:(Y0 + ROWS) * 1600])


# backgrounds: the model's slot is read once (cached), copied into rows y0.., the picture goes over it
run, st = machine(bg=bg_section())
fb = run(5)
assert st["reads"] == [(STORE, 12), (BGFIRST + BGSPB, BGSPB), (FIRST + 2 * SPP, SPP)], st["reads"]
assert bgdrawn(fb, 1) and drawn(fb, 2)
fb = run(5)
assert st["reads"] == [] and bgdrawn(fb, 1) and drawn(fb, 2)                   # background and picture cached
fb = run(9)
assert st["reads"] == [(BGFIRST, BGSPB), (FIRST, SPP)] and bgdrawn(fb, 0) and drawn(fb, 0)
fb = run(7)                                                                    # a picture, slot 0xff: no background
assert bgnone(fb) and drawn(fb, 1) and all(r[0] != BGFIRST for r in st["reads"])
assert not any(run(3)) and not any(run(10))                                    # no picture, no block: nothing, as before
run, st = machine(bg=bg_section())
run(5)
fb = run(9, fail=True)                                                                  # a failed background read: no background, and
assert bgnone(fb), "failed read"                                               # the next paint reads it again
fb = run(9)
assert bgdrawn(fb, 0) and drawn(fb, 0) and (BGFIRST, BGSPB) in st["reads"]
# a header outside the bounds draws no background (the picture still shows)
for bad in (dict(magic=b"HXBX"), dict(count=251), dict(rows=0), dict(rows=ROWS, y0=480), dict(spb=BGSPB - 1), dict(spb=2000),
            dict(slots={5: 2}), dict(rows=700, y0=0)):
    run, st = machine(bg=bg_section(**bad))
    fb = run(5)
    assert bgnone(fb) and drawn(fb, 2), bad
    assert all(not BGFIRST <= r[0] < BGFIRST + 4 * BGSPB for r in st["reads"]), (bad, st["reads"])
# an old store (no background section): exactly as before
run, st = machine(bg=None)
fb = run(5)
assert bgnone(fb) and drawn(fb, 2) and st["reads"] == [(STORE, 12), (FIRST + 2 * SPP, SPP)]
# set B (the theme pack): the mode word picks its map and slots; set A is untouched in the same header
run, st = machine(bg=bg_section(mode=1), setb=True)
fb = run(5)
assert bgdrawn(fb, 0) and drawn(fb, 0), "set B"
assert st["reads"] == [(STORE, 12), (BGFIRST, BGSPB), (FIRST, SPP)], st["reads"]
assert bgnone(run(9)) and not any(run(3))                                       # set B has no entry for pid 9: nothing drawn
run, st = machine(bg=bg_section(mode=0), setb=True)
assert bgdrawn(run(5), 1) and drawn(run(5), 2)                                 # mode 0: set A as before
run, st = machine(bg=bg_section(mode=7), setb=True)
assert bgdrawn(run(5), 1) and drawn(run(5), 2)                                 # anything but 1: set A
# NAM block (pid 9): the capture's own picture by slot; no entry / slot out of range: the model's picture; other blocks never ask
run, st = machine(nam=True)
assert drawn(run(9, slot=3), 1) and st["asked"] == 1      # slot 3 (1 based) -> table[2] = picture 1
assert drawn(run(9, slot=4), 0) and drawn(run(9, slot=0), 0) and drawn(run(9, slot=129), 0)
assert drawn(run(5), 2) and st["asked"] == 4                                    # another model: its own picture, no query
run, st = machine(nam=False)
assert drawn(run(9, slot=3), 0) and st["asked"] == 0                            # a store without NAM pictures: as before

# per-preset scenes: the table at STORED_SEC (read once) overrides the model's background; setlist * 128 + preset indexes it
run, st = machine(bg=bg_section(), stored=stored_table({3: 0, 129: 1, 4: 0xFF}))
fb = run(5, preset=3)                                                          # pid 5's own slot is 1; this preset says scene 0
assert bgdrawn(fb, 0) and drawn(fb, 2), "stored scene wins"
assert st["sbreads"] == [(STORED_SEC, 2)], st["sbreads"]
fb = run(5, preset=129)                                                        # setlist 1, preset 1 -> scene 1
assert bgdrawn(fb, 1) and st["sbreads"] == [(STORED_SEC, 2)]                   # (the table is read once)
fb = run(5, preset=4)                                                          # 0xff: the model's own slot (1)
assert bgdrawn(fb, 1)
fb = run(9, preset=3)                                                          # another model, same preset: scene 0 as well
assert bgdrawn(fb, 0)
fb = run(7, preset=3)                                                          # a model with no background of its own gets the preset's
assert bgdrawn(fb, 0) and drawn(fb, 1)
fb = run(5, preset=640)                                                        # past the table's N: the model's own
assert bgdrawn(fb, 1)
fb = run(5, preset=0)                                                          # no entry: the model's own
assert bgdrawn(fb, 1)
run, st = machine(bg=bg_section(), stored=stored_table({3: 7}))               # scene 7 does not exist: no background (the count check)
assert bgnone(run(5, preset=3)) and drawn(run(5, preset=3), 2)
run, st = machine(bg=bg_section(), stored=stored_table({3: 0}, magic=b"HXSX"))  # a wrong magic: ignored, read once
assert bgdrawn(run(5, preset=3), 1) and bgdrawn(run(5, preset=3), 1) and len(st["sbreads"]) == 1
run, st = machine(bg=bg_section(), stored=stored_table({3: 0}, n=1017))        # N too large: ignored
assert bgdrawn(run(5, preset=3), 1)
run, st = machine(bg=bg_section())                                             # no table at all: as before
assert bgdrawn(run(5, preset=3), 1) and drawn(run(5, preset=3), 2)
run, st = machine(bg=None, stored=stored_table({3: 0}))                        # a store without a background section: no background
assert bgnone(run(5, preset=3)) and drawn(run(5, preset=3), 2)
# see-through pixels: bit 15 set leaves the background there (hard edge); other pixels as before
run, st = machine(bg=bg_section(), holes=True)
fb = run(5)
top = 196 - S // 2
for r in range(S):
    row = fb[((top + r) * 800 + 400 - S // 2) * 2:][:2 * S]
    bgpx = bytes([0xA0 + 1, (top + r - Y0)]) if 0 <= top + r - Y0 < ROWS else bytes(2)
    assert row[:8] == bgpx * 4, (r, row[:8])                                   # the four holes show the background
    assert row[8:] == bytes([3, 0x40 + r]) * (S - 4), r                        # the rest is the picture
run, st = machine(holes=True)                                                  # no background at all: holes show the plain frame
fb = run(5)
assert fb[((top + 0) * 800 + 400 - S // 2) * 2:][:8] == bytes(8)
print("focus_emmc: per-preset scenes (table read once, bounds, wrong magic, no table) and see-through pixels: OK")
print("focus_emmc: NAM capture pictures by slot, fallbacks, old stores: OK")
print("focus_emmc: backgrounds by slot, cached, bounds, two sets: OK")
print("focus_emmc: header read once, picture by preset id, cache, retry, none / empty / no block, no store: OK")
