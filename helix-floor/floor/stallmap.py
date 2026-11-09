#!/usr/bin/env python3
"""Block-conflict stall estimate for the Floor kernel layout (2026-11-08). The sim counts instructions;
the unit adds a cycle when (a) one instruction's DM and PM data accesses hit the same memory block, or
(b) an instruction with no PM data access touches the code's block (Block 3 on the Floor) with DM: its
fetch comes from that block (upstream NAM_LITE_DSP_LOAD.md, "fetch conflict"). Cache misses, load-use
and DMA contention are not modelled. Calibration on the unit (profile 2): default 53,244 vs sim + model
54,649; NAM_LB_B0 51,616 vs 51,867.

Runs the kernel in ssim (as nam_floor5q.sim) and records, per executed instruction, which buffers
(Layout.alloc names, INSTDM / INSTPM for the instance's blocks) it touches on which bus. Any placement
of the buffers in blocks can then be scored without running again (same code, same instructions).
The rig's instance blocks are mapped to where the Floor puts them (DM: heap a, Block 0; PM: heap b,
Block 3). Stalls inside the wait loops (lw_l, fw_l, n_hw*) mostly only stretch the polling.
usage: [NAM_LB_B0=1 ...] stallmap.py [calls]       -> stalls/call by code label
       stallmap.py --search [calls]                 -> best placement of the movable buffers"""
import bisect
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nam_floor5 as n5  # noqa: E402

CODE_BLOCK = "B3"
WAITS = ("LW_L", "FW_L", "N_HW0", "LWAIT", "FWAIT")


def blk(a):
    return None if a < 0x80000 or a >= 0x100000 else "B%d" % ((a - 0x80000) >> 17)


def record(n=100, steady=6):
    """-> (Counter{(label, dm objs, pm objs): count per call}, {obj: (addr, size, region)}, sim cycles)"""
    taken = []
    take0 = n5.Regions.take

    def take(self, r, k, even=False):
        a = take0(self, r, k, even)
        taken.append((a, k, r))
        return a
    n5.Regions.take = take
    try:
        asm, lay = n5.build(inst_bounds=n5.RIG_BOUNDS)
    finally:
        n5.Regions.take = take0
    objs = {}
    for name, a in lay.alloc.items():
        for ta, k, r in taken:
            if ta == a:
                objs[name] = (a, k, r)
    nm = n5.nm
    nm.REP = lay.rep
    r = n5.Rig(asm, lay)
    w = n5.nam_lite.placeholder()
    nm.set_ir(r.sim, 1, n5.nam_lite.ir_samples(w, None))
    inst = r.inst("A", 0)
    inst.knobs(model=1)
    sim = r.sim
    spans = sorted([(a, a + k, name) for name, (a, k, _) in objs.items()] +
                   [(inst.i0, inst.i0 + 0x600, "INSTDM"), (inst.i8, inst.i8 + 0x200, "INSTPM")])
    starts = [s[0] for s in spans]

    def obj(a):
        j = bisect.bisect_right(starts, a) - 1
        if j >= 0 and a < spans[j][1]:
            return spans[j][2]
        b = blk(a)
        return b and "other" + b

    labels = sorted((a, k) for k, a in r.syms.items() if isinstance(a, int) and a in sim.pm)
    laddr = [a for a, _ in labels]
    idx, acc = [], []
    rd0, wr0, post0, pre0, step0 = sim.rd, sim.wr, sim.post, sim.pre, sim._step

    def post(i, step, scale=None):
        a = post0(i, step, scale)
        idx.append((i, a))
        return a

    def pre(i, step, scale=None):
        a = pre0(i, step, scale)
        idx.append((i, a))
        return a

    def rd(a):
        acc.append(a & 0xFFFFFFFF)
        return rd0(a)

    def wr(a, v):
        acc.append(a & 0xFFFFFFFF)
        return wr0(a, v)

    sig, on = Counter(), [False]

    def step():
        pc = sim.pc
        idx.clear()
        acc.clear()
        res = step0()
        if on[0] and acc:
            dm, pm = set(), set()
            for x in acc:
                bus = "DM"
                for i, a in idx:
                    if a <= x <= a + 2:
                        bus = "PM" if i >= 8 else "DM"
                        break
                o = obj(x)
                if o:
                    (pm if bus == "PM" else dm).add(o)
            if dm or pm:
                j = bisect.bisect_right(laddr, pc) - 1
                sig[(labels[j][1] if j >= 0 else "?", frozenset(dm), frozenset(pm))] += 1
        return res

    sim.rd, sim.wr, sim.post, sim.pre, sim._step = rd, wr, post, pre, step
    s = [n5.nf.ssim_f2b(0.2 * ((k * 7) % 11 - 5) / 5) for k in range(16)]
    for b in range(n):
        on[0] = b >= n - steady
        inst.call(s, f"A {b}")
    return Counter({k: v / steady for k, v in sig.items()}), objs, r.cycles[-1][1]


def block_of(o, place):
    if o == "INSTDM":
        return "B0"
    if o == "INSTPM":
        return "B3"
    if o.startswith("other"):
        return o[5:]
    return place[o]


def score(sig, place, waits=True):
    by = Counter()
    for (lab, dm, pm), c in sig.items():
        if not waits and lab in WAITS:
            continue
        d = {block_of(o, place) for o in dm}
        p = {block_of(o, place) for o in pm}
        k = (1 if d & p else 0) + (1 if not p and CODE_BLOCK in d else 0)
        if k:
            by[lab] += k * c
    return sum(by.values()), by


def current(objs):
    return {o: blk(a) for o, (a, k, r) in objs.items()}


def search(sig, objs):
    """Local search over which buffers sit in Block 0 (R3), by size, the rest in Block 3 (R1/R2)."""
    cap = n5.REGIONS3["R3"][1] - n5.REGIONS3["R3"][0] - n5.nf.GUARD - 2
    names = sorted(o for o in objs if objs[o][2] != "RX")
    size = {o: objs[o][1] for o in names}
    tie = {"SLOT0": "SLOT1", "SLOT1": "SLOT0", "RCH0": "RCH1", "RCH1": "RCH0", "FCH0": "FCH1", "FCH1": "FCH0"}
    place = current(objs)

    def cost(p):
        return score(sig, p, waits=False)[0]

    def fits(p):
        return sum(size[o] + 1 for o in names if p[o] == "B0") <= cap
    best = cost(place)
    improved = True
    while improved:
        improved = False
        for a in names:
            for b in [None] + names:
                p = dict(place)
                p[a] = "B3" if p[a] == "B0" else "B0"
                if b and b != a:
                    if p[b] == p[a] or b == tie.get(a):
                        continue
                    p[b] = "B3" if p[b] == "B0" else "B0"
                for o in (a, b):
                    if o in tie:
                        p[tie[o]] = p[o]
                if fits(p):
                    c = cost(p)
                    if c < best - 0.5:
                        best, place, improved = c, p, True
    return best, place, size, cap


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else 100
    sig, objs, cyc = record(n)
    place = current(objs)
    tot, by = score(sig, place)
    tw, _ = score(sig, place, waits=False)
    print(f"NAM_LB_B0={os.environ.get('NAM_LB_B0', '0')}: sim instructions/call {cyc}, "
          f"modelled stalls/call {tot:.0f} ({tw:.0f} outside the wait loops)")
    for k, v in by.most_common():
        if v >= 20:
            print(f"  {k:14s} {v:7.0f}")
    if "--search" in sys.argv:
        best, p, size, cap = search(sig, objs)
        b0 = sorted((o for o in p if p[o] == "B0"), key=lambda o: -size[o])
        print(f"\nsearch: outside waits {tw:.0f} -> {best:.0f}; Block 0 ({cap} words): "
              + ", ".join(f"{o} {size[o]}" for o in b0) + f" = {sum(size[o] + 1 for o in b0)}")
        _, by2 = score(sig, p)
        for k, v in by2.most_common():
            if v >= 20:
                print(f"  {k:14s} {v:7.0f}  (was {by[k]:.0f})")
