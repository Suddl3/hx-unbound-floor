"""Live RAM-only trace of the DSP message sender 0x2813ae68 (r0 ctx, r1 id, r2 -> {type byte, 4 bytes}).
Every call appends a 16-byte record {lr, r1, *(r2), *(r2+4)} to a ring of 32 at 0x29F03410 (index word at 0x29F03400).
  trace_send.py on | off | dump | clear     (a restart also undoes it). HX Edit closed."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import floor_poke, floor_peek

ENTRY, BACK, W, LOG = 0x2813AE68, 0x2813AE70, 0x29F03300, 0x29F03400
H = lambda *v: b"".join(struct.pack("<H", x) for x in v)


def wrapper(orig):
    b = orig                                    # the 8 replaced bytes: push.w {r4-r8,lr}; mov r4,r0; mov r6,r1
    b += H(0x4B08, 0x681F, 0x3701, 0x601F,      # ldr r3,[LOG]; ldr r7,[r3]; adds r7,#1; str r7,[r3]
           0x06FF, 0x0EFF, 0x013F, 0x18FF, 0x3710,   # slot = LOG + 16 + 16 * (idx & 31) in r7
           0x4673, 0x603B, 0x6079,              # mov r3,lr; str r3,[r7]; str r1,[r7,#4]
           0x6813, 0x60BB, 0x6853, 0x60FB,      # *(r2) -> [r7,#8]; *(r2+4) -> [r7,#12]
           0xF8DF, 0xF004)                      # ldr.w pc,[pc,#4] -> BACK
    b += struct.pack("<2I", LOG, BACK | 1)
    assert len(b) == 0x34, hex(len(b))
    return b


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("on", "off", "dump", "clear"):
        sys.exit(__doc__)
    with floor_poke.Poke() as p:
        pk = floor_peek.Peek(p.ctl)
        if mode == "dump":
            raw = pk.read(LOG, 16 + 32 * 16)
            idx = struct.unpack_from("<I", raw, 0)[0]
            print("calls:", idx)
            n = min(idx, 32)
            for k in range(idx - n + 1, idx + 1):
                lr, r1, w0, w1 = struct.unpack_from("<4I", raw, 16 + 16 * (k & 31))
                print("#%d lr=%#x id=%#x msg type=%d val=%#x" % (k, lr, r1, w0 & 0xFF, w1))
            return
        if mode == "clear":
            p.write(LOG, bytes(16 + 32 * 16)); return
        if mode == "on":
            orig = pk.read(ENTRY, 8)
            assert orig == bytes.fromhex("2de9f0410446" "0e46"), orig.hex()
            p.write(LOG, bytes(16 + 32 * 16))
            p.enable_bulk(); p.write_bulk(W, wrapper(orig))
            new = H(0xF8DF, 0xF000) + struct.pack("<I", W | 1)
        else:
            new = bytes.fromhex("2de9f0410446" "0e46")
        for i in range(0, 8, 4):
            p.patch_atomic(ENTRY + i, new[i:i + 4])
    print("trace", mode)


if __name__ == "__main__":
    main()
