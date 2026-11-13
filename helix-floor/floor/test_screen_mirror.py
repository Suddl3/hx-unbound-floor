"""Unicorn (Cortex-M4) test of m4/floor_mirror.bin (screen_mirror.py): registration through the trampoline flow, a
full frame, changed rows only, resync on a seq gap, the frame address from the LCD register. Firmware functions are
Python stubs at their Floor addresses. Needs unicorn (pip install unicorn). usage: python test_screen_mirror.py"""
import os
import random
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R4, UC_ARM_REG_R11)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screen_mirror  # noqa: E402

CODE, SYMS = screen_mirror.load()
CAVE = 0x10012000
W, H, ROW = 800, 480, 1600
FB0, FB1 = 0x285a3f50, 0x285a3f50 + W * H * 2
LCD = 0x40008000
STUB = dict(REGISTER=0x280ee19c, NO_PARAMS=0x280f77fc, WRITER=0x280ed570, PREFIX_LEN=0x280ed594, PREFIX=0x280ed5b8,
            PREFIX_RESET=0x280ed5dc, REPLY_HEAD=0x280ed620, LOCK=0x10089148, UNLOCK=0x10089168, CLOCK=0x10009bcc,
            SLEEP=0x1008971c, REGALL_A=0x280f0528, REGALL_B=0x280f01a4, REGALL_REST=0x280ee59e,
            S_WRITE=0x20001000, S_DONE=0x20001010, W_WRITE=0x20001020, CALLER=0x20001030, POST=0x2808b668)
ADDR = {v: k for k, v in STUB.items()}


def sym(name):
    return SYMS[name]


mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
for base, size in ((0x10000000, 0x100000), (0x20000000, 0x100000), (0x28000000, 0x2000000), (LCD, 0x1000)):
    mu.mem_map(base, size)
mu.mem_write(CAVE, CODE)
for a in STUB.values():                     # each stub: a bx lr, so a stub missing its hook still returns
    mu.mem_write(a, b"\x70\x47")
STREAM, VTAB, WRITER_OBJ, PFX, PFX_LEN = 0x20002000, 0x20002100, 0x20002200, 0x20002300, 0x20002400
mu.mem_write(STREAM, struct.pack("<I", VTAB))
mu.mem_write(VTAB, struct.pack("<4I", 0, STUB["S_WRITE"] | 1, 0, STUB["S_DONE"] | 1))
mu.mem_write(WRITER_OBJ, struct.pack("<2I", 0xC0FFEE, STUB["W_WRITE"] | 1))
log, out, clock = [], bytearray(), [1000]
pfx = b"PREFIX!!"


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
    elif name in ("PREFIX_RESET", "UNLOCK", "SLEEP"):
        ret(0)
    elif name == "LOCK":
        assert a0 == STREAM - 8
        ret(0)
    elif name == "REPLY_HEAD":
        log.append(("head", a0, a1, a2))
        ret(0)
    elif name == "CLOCK":
        clock[0] += 7
        ret(clock[0])
    elif name == "W_WRITE":
        log.append(("wwrite", bytes(uc.mem_read(a1, a2))))
        ret(0)
    elif name == "S_WRITE":
        assert a0 == STREAM
        out.extend(uc.mem_read(a1, a2))
        ret(0)
    elif name == "S_DONE":
        log.append("done")
        ret(0x55)
    elif name in ("REGALL_A", "REGALL_B"):
        ret(0)
    elif name == "REGALL_REST":             # the rest of the registrations: ...; movs r0, #0; pop {r3, pc}
        sp = r(UC_ARM_REG_SP)
        r3, pc = struct.unpack("<2I", bytes(uc.mem_read(sp, 8)))
        uc.reg_write(UC_ARM_REG_SP, sp + 8)
        uc.reg_write(UC_ARM_REG_R3, r3)
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, pc)
    elif name == "POST":
        log.append(("post", bytes(uc.mem_read(a0, 8))))
        ret(0)
    elif name == "CALLER":
        uc.emu_stop()


mu.hook_add(UC_HOOK_CODE, hook)


def call(fn, *args):
    for i, a in enumerate(args):
        mu.reg_write([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2][i], a)
    mu.reg_write(UC_ARM_REG_SP, 0x200F0000)
    mu.reg_write(UC_ARM_REG_LR, STUB["CALLER"] | 1)
    for reg in (UC_ARM_REG_R4, UC_ARM_REG_R11):
        mu.reg_write(reg, 0xA5A5A5A5)
    mu.emu_start((CAVE + sym(fn)) | 1, 0, count=20_000_000)
    assert r(UC_ARM_REG_PC) & ~1 == STUB["CALLER"], hex(r(UC_ARM_REG_PC))
    assert r(UC_ARM_REG_SP) == 0x200F0000, "stack not balanced"
    assert r(UC_ARM_REG_R4) == 0xA5A5A5A5 and r(UC_ARM_REG_R11) == 0xA5A5A5A5, "callee-saved register clobbered"
    return r(UC_ARM_REG_R0)


def request(seq):
    req = 0x20003000
    mu.mem_write(req, bytes(12) + struct.pack("<H", seq))
    out.clear()
    del log[:]
    res = call("fm_cmd", STREAM, req)
    assert res == 0x55 and "done" in log and log.index("LOCK") < log.index("done") < log.index("UNLOCK")
    head = [x for x in log if isinstance(x, tuple) and x[0] == "head"][0]
    assert head == ("head", WRITER_OBJ, seq, 0), head
    ww = [x[1] for x in log if isinstance(x, tuple) and x[0] == "wwrite"][0]
    n = struct.unpack(">I", ww[1:5])[0]
    assert ww[0] == 0xC6
    m = bytes(out)
    z, svc, total = struct.unpack_from("<HHI", m, 0)
    assert (z, svc) == (0, 6) and total == len(pfx) + n and m[8:8 + len(pfx)] == pfx and len(m) == 8 + total, (total, len(m))
    body = m[8 + len(pfx):]
    fmt, w, h, nrows, fb, ctrl = struct.unpack_from("<4H2I", body, 0)
    assert (fmt, w, h) == (0xF100, W, H) and n == 76 + nrows * ROW + 12
    bits = struct.unpack_from("<30H", body, 16)
    rows = [i for i in range(H) if bits[i // 16] >> (i % 16) & 1]
    assert len(rows) == nrows
    data = body[76:76 + nrows * ROW]
    return fb, ctrl, rows, {row: data[k * ROW:(k + 1) * ROW] for k, row in enumerate(rows)}


random.seed(5)
frame = bytearray(random.randbytes(W * H * 2))
mu.mem_write(FB0, bytes(frame))
mu.mem_write(LCD + 0x10, struct.pack("<I", FB0))
mu.mem_write(LCD + 0x18, struct.pack("<I", 0x0001082D))

# 1. registration through the trampoline flow: A, B, the rest, then CMD; returns 0 to the caller
del log[:]
assert call("fm_regall") == 0
names = [x for x in log if isinstance(x, str)]
assert names[:4] == ["REGALL_A", "REGALL_B", "REGALL_REST", "REGISTER"], names
regs = [x for x in log if isinstance(x, tuple) and x[0] == "reg"]
assert regs[0][1] == 0x52 and regs[0][2] == ((CAVE + sym("fm_cmd")) | 1, 0x280f77fd, 0), regs
assert regs[1][1] == 0x51 and regs[1][2] == ((CAVE + sym("fm_input")) | 1, 0x280f77fd, 0), regs
assert regs[2][1] == 0x53 and regs[2][2] == ((CAVE + sym("fm_peekset")) | 1, 0x280f77fd, 0), regs
assert len(regs) == 3
print("registration: OK")

# 2. first request: every row, equal to the frame
fb, ctrl, rows, got = request(1)
assert fb == FB0 and ctrl == 0x0001082D and rows == list(range(H))
assert all(got[i] == frame[i * ROW:(i + 1) * ROW] for i in rows)
print("full frame: OK (480 rows)")

# 3. next seq: nothing changed -> no rows; then three rows change -> just those
assert request(2)[2] == []
for row in (0, 100, 479):
    frame[row * ROW + 7] ^= 0xFF
mu.mem_write(FB0, bytes(frame))
fb, ctrl, rows, got = request(3)
assert rows == [0, 100, 479] and all(got[i] == frame[i * ROW:(i + 1) * ROW] for i in rows), rows
print("changed rows only: OK", rows)

# 4. a seq that does not follow -> every row again
assert request(9)[2] == list(range(H))
print("resync on a seq gap: OK")

# 5. the LCD shows the second buffer; an address outside SDRAM falls back to FB0
frame2 = bytearray(random.randbytes(W * H * 2))
mu.mem_write(FB1, bytes(frame2))
mu.mem_write(LCD + 0x10, struct.pack("<I", FB1))
fb, _, rows, got = request(10)
assert fb == FB1 and all(got[i] == frame2[i * ROW:(i + 1) * ROW] for i in rows) and len(rows) == H
mu.mem_write(LCD + 0x10, struct.pack("<I", 0))
assert request(1)[0] == FB0
print("frame address: OK")

# 2b. CMD 0x53 (fm_peekset): the next frames read memory from seq << 17; 0 goes back to the screen
def peekset(seq):
    req = 0x20003000
    mu.mem_write(req, bytes(12) + struct.pack("<H", seq))
    out.clear()
    del log[:]
    assert call("fm_peekset", STREAM, req) == 0x55 and "done" in log

peekset(0x1400)                                   # 0x1400 << 17 = 0x28000000
assert request(1)[0] == 0x28000000 and request(2)[0] == 0x28000000
peekset(0)
assert request(1)[0] == FB0
print("peek window: OK")


def press(seq):
    """CMD 0x51 (fm_input): -> the events it posted; its reply checked: {seq, 0, 0} as one fixint after the head."""
    req = 0x20003000
    mu.mem_write(req, bytes(12) + struct.pack("<H", seq))
    out.clear()
    del log[:]
    res = call("fm_input", STREAM, req)
    assert res == 0x55 and "done" in log and log.index("LOCK") < log.index("done") < log.index("UNLOCK")
    posts = [x[1] for x in log if isinstance(x, tuple) and x[0] == "post"]
    if posts:
        assert log.index(("post", posts[0])) < log.index("LOCK"), "posted under the stream lock"
    assert [x for x in log if isinstance(x, tuple) and x[0] == "head"] == [("head", WRITER_OBJ, seq, 0)]
    assert [x[1] for x in log if isinstance(x, tuple) and x[0] == "wwrite"] == [b"\x00"]
    m = bytes(out)
    z, svc, total = struct.unpack_from("<HHI", m, 0)
    assert (z, svc) == (0, 6) and total == len(pfx) and m[8:] == pfx, m
    return posts


def ev(cls, code, value):
    return 0x8000 | cls << 12 | code << 6 | (value & 0x3f)


assert press(ev(1, 0x11, 1)) == [struct.pack("<BBxxi", 1, 0x11, 1)]          # a key press
assert press(ev(1, 0x11, 2)) == [struct.pack("<BBxxi", 1, 0x11, 2)]          # its release
assert press(ev(1, 63, 5)) == [struct.pack("<BBxxi", 1, 63, 5)]              # a hold
assert press(ev(2, 3, -4)) == [struct.pack("<BBxxi", 2, 3, -4)]              # knob 4 back a step
assert press(ev(2, 0, 31)) == [struct.pack("<BBxxi", 2, 0, 31)]
assert press(ev(0, 1, 1)) == [struct.pack("<BBxxi", 1, 65, 1)]                # class 0: key 64 + code
assert press(ev(3, 5, 2)) == [struct.pack("<BBxxi", 1, 133, 2)]                # class 3: key 128 + code
assert press(ev(4, 63, 1)) == [struct.pack("<BBxxi", 1, 255, 1)]               # class 4: key 192 + code
assert press(ev(5, 1, 1)) == [] and press(ev(6, 1, -1)) == [] and press(ev(7, 0, 1)) == []   # 5..7 refused
assert press(0x1234) == []                                                   # no bit 15: a reply only
# the mirror's own seq is untouched: the next frame request (seq 2 after request(1)) still gets only changed rows
assert request(2)[2] == []
print("remote input: keys 0..255, knobs, classes 5..7 refused, reply, mirror seq kept: OK")
print("sleeps per full hash pass:", log.count("SLEEP"))
print("ALL PASS")
