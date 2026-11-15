"""Live RAM-only test fix for MIDI clock stop + Tap Tempo Pitch = Transparent.
When the MIDI clock stops, the tempo reverts to the preset/global tempo by calling the DSP tempo sender 0x2813ae68 directly,
without the begin/end bracket 0x28148154(ctx, 1/0) that the tap and clock-update paths use (that bracket is what makes
Transparent work). Each of those calls (7 sites in 0x28090a7a.. and 0x28090c12..) becomes a jump (ldr.w pc, literal) to a
wrapper in free RAM (0x29F03000 / 0x29F03080) that does bracket(1); send; bracket(0), then redoes the replaced
ldrb/cmp/bne and rejoins.
  clk_fix.py on | off | status        (a restart also undoes it). HX Edit closed."""
import os, struct, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import floor_poke, floor_peek

W1, W2 = 0x29F03000, 0x29F03080
H = lambda *v: b"".join(struct.pack("<H", x) for x in v)
BAK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clk_fix_orig.json")


def wrapper(else_t, eq_t, cnt):
    """bracket(1); lock; send; unlock; bracket(0) - the order the tap and clock-update paths use - then ldrb/cmp/bne again."""
    items = [0xB4F0, 0x0004, 0x000D, 0x0016,                  # push {r4-r7} (16 bytes: keeps SP 8-aligned); r4,r5,r6 = r0,r1,r2
             ("ldr3", "cnt"), 0x6818, 0x3001, 0x6018,          # counter++ (debug)
             0x0020, 0x2101, ("ldr3", "br"), 0x4798,           # r0=ctx; r1=1; begin
             0x0020, ("ldr3", "lock"), 0x4798,                 # lock(ctx)
             0x0020, 0x0029, 0x0032, ("ldr3", "send"), 0x4798,   # send(ctx, id, msg)
             0x0020, ("ldr3", "unlock"), 0x4798,               # unlock(ctx)
             0x0020, 0x2100, ("ldr3", "br"), 0x4798,           # r1=0; end
             0xBCF0, 0x7823, 0x2B04, ("beq", 2),               # pop; ldrb r3,[r4]; cmp r3,#4; beq over the next jump
             ("ldrpc", "else"), ("ldrpc", "eq")]
    lits = {"else": else_t | 1, "eq": eq_t | 1, "br": 0x28148154 | 1, "send": 0x2813AE68 | 1,
            "lock": 0x2813E63C | 1, "unlock": 0x2813E654 | 1, "cnt": cnt}
    size = sum(4 if isinstance(i, tuple) and i[0] == "ldrpc" else 2 for i in items)
    pool = (size + 3) & ~3
    addr = {k: pool + 4 * n for n, k in enumerate(lits)}
    out, pc = b"", 0
    for i in items:
        if isinstance(i, int):
            out += H(i); pc += 2
        elif i[0] == "ldr3":
            out += H(0x4B00 | ((addr[i[1]] - ((pc + 4) & ~3)) // 4)); pc += 2
        elif i[0] == "beq":
            out += H(0xD000 | i[1] - 1 if False else 0xD001); pc += 2
        else:
            out += H(0xF8DF, 0xF000 | (addr[i[1]] - ((pc + 4) & ~3))); pc += 4
    out += bytes(pool - len(out)) + b"".join(struct.pack("<I", v) for v in lits.values())
    assert len(out) <= 0x80, hex(len(out))
    return out


CNT1, CNT2 = 0x29F03200, 0x29F03204


# (base word address of the 12 bytes, wrapper, kind): kind "mid" = bl at base+2 (movs r1 before it); "aligned" = bl at base
SITES = [(0x28090A78, W1, "mid"), (0x28090A90, W1, "aligned"), (0x28090AA4, W1, "mid"), (0x28090C10, W2, "mid"), (0x28090C24 + 4, W2, "aligned"), (0x28090C3C, W2, "mid")]
# group A (0x28090970's tail): else 0x280909ae, equal 0x280909f8.  group B (0x28090b08's tail): else 0x28090b46, equal 0x28090b90


def new_words(orig, wr, kind):
    w = list(struct.unpack("<6H", orig[:12]))
    lit = struct.pack("<I", wr | 1)
    if kind == "mid":                # hw: [movs r1][bl a][bl b][ldrb][cmp][bne]  -> literal lands on [cmp][bne]
        w[1], w[2], w[3] = 0xF8DF, 0xF004, 0xBF00
        return struct.pack("<4H", *w[:4]) + lit
    w[0], w[1], w[2], w[3] = 0xF8DF, 0xF004, 0xBF00, 0xBF00      # aligned: [bl a][bl b][ldrb][cmp] -> ; literal on [bne][b]
    return struct.pack("<4H", *w[:4]) + lit


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("on", "off", "status"):
        sys.exit(__doc__)
    with floor_poke.Poke() as p:
        pk = floor_peek.Peek(p.ctl)
        if mode == "status":
            for base, wr, kind in SITES:
                print(hex(base), pk.read(base, 12).hex())
            return
        if mode == "on":
            bak = json.load(open(BAK)) if os.path.exists(BAK) else {}
            for b, _, _ in SITES:                       # unpatched sites only (a patched one holds our ldr.w pc)
                if hex(b) not in bak:
                    bak[hex(b)] = pk.read(b, 12).hex()
            json.dump(bak, open(BAK, "w"))
            p.enable_bulk()
            p.write(CNT1, bytes(8))
            p.write_bulk(W1, wrapper(0x280909AE, 0x280909F8, CNT1))
            p.write_bulk(W2, wrapper(0x28090B46, 0x28090B90, CNT2))
            for base, wr, kind in SITES:
                new = new_words(bytes.fromhex(json.load(open(BAK))[hex(base)]), wr, kind)
                for i in range(0, 12, 4):
                    p.patch_atomic(base + i, new[i:i + 4])
        else:
            bak = json.load(open(BAK))
            for base, wr, kind in SITES:
                orig = bytes.fromhex(bak[hex(base)])
                for i in range(0, 12, 4):
                    p.patch_atomic(base + i, orig[i:i + 4])
    print("clock-stop fix", mode)


if __name__ == "__main__":
    main()
