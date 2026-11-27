#!/usr/bin/env python3
"""Port of nocaseguy's bit-exact DSP rewrites (hx-stomp-nam-lite, branch dsp-opt-patch-list, tools/dsp_opt/patch.json, GPL-3.0-or-later)
to the Helix Floor's SHARC program (Entry 2).

The Floor's DSP program is the Stomp's code relocated by constant offsets per region, so a routine the patch list rewrites is, in
the Floor image, the same stock bytes at another address. Two commands:

  dsp_opt_port.py gen STOMP_E2.bin FLOOR_E2.bin PATCH.json OUT.json [--only a,b]
      per group: find the Stomp stock routine in the Floor's Entry 2 (exact match, the offset is recorded), keep its SHA-256 there and
      the rewrite's new 16-bit parcels at the Floor's addresses. Groups that do not match exactly are listed and left out.
      OUT.json holds only the new values and hashes, no stock code (as the patch list).
  dsp_opt_port.py apply FLOOR_E2.bin PORT.json OUT_E2.bin [--only a,b] [--without a,b]
      every selected group's stock range is hashed in the image first (one that differs stops the run, nothing is written); the new
      parcels are written in place in the loader block that last loads each (Entry 2 keeps its length); the result is parsed again and
      must equal the base's program memory with exactly the intended parcels changed.

Entry 2 is the SHARC loader stream: 32-bit LE words, blocks {tag, count, address} from word 384. Tag 3: 16-bit parcels (short VISA code),
two to a word (the even one in the high half); tag 5: 48-bit instructions at PM addresses, each 3 parcels (the 48-bit value, LE, parcel k
is bits 16k..16k+15). A parcel is addressed as in pm_parcel(). Later blocks override earlier ones.
"""
import hashlib
import json
import struct
import sys

TAGS_PROGRAM = (3, 5)


def pm_parcel(a):
    base = a & ~0x1FFFF
    return 0x100000 + 2 * (base - 0x80000) + 3 * (a - base)


def nwords(tag, cnt):
    return {5: ((cnt + 1) & ~1) * 3 // 2, 4: cnt, 3: (cnt + 1) // 2, 6: cnt * 2, 10: cnt, 9: cnt}.get(tag, 0)


class Ldr:
    """The program memory (parcels) a loader stream fills, with where each parcel's two bytes sit in the stream."""

    def __init__(self, e2):
        self.data = bytearray(e2)
        w = struct.unpack("<%dI" % (len(e2) // 4), e2)
        self.where = {}                              # parcel -> byte offset in the stream (the last block that loads it)
        i = 384
        while i + 3 <= len(w):
            tag, cnt, addr = w[i:i + 3]
            if tag > 12:
                raise SystemExit(f"loader stream: no block at word {i} (tag {tag:#x})")
            if tag == 0:
                break
            base = (i + 3) * 4
            if tag == 3:
                for j in range(cnt):
                    self.where[addr + j] = base + 4 * (j // 2) + (2 if j % 2 == 0 else 0)
            elif tag == 5:
                for j in range(cnt):
                    p = pm_parcel(addr + j)
                    for k in range(3):
                        self.where[p + k] = base + 6 * j + 2 * k
            i += 3 + nwords(tag, cnt)

    def get(self, parcel):
        o = self.where.get(parcel)
        return None if o is None else self.data[o] | self.data[o + 1] << 8

    def put(self, parcel, value):
        o = self.where[parcel]
        self.data[o], self.data[o + 1] = value & 0xFF, value >> 8 & 0xFF

    def span(self, first, end):
        vals = [self.get(p) for p in range(first, end)]
        return None if None in vals else vals

    def snapshot(self):
        return {p: self.get(p) for p in self.where}


def sha(vals):
    return hashlib.sha256(b"".join(struct.pack("<H", v) for v in vals)).hexdigest()


def new_parcels(group):
    """The parcels a patch-list group sets, as {Stomp parcel: 16-bit value} (tags 3 and 5; DDR2 / 32-bit units are not program)."""
    out = {}
    for tag, addr, value in group["set"]:
        if tag == 3:
            out[addr] = value
        elif tag == 5:
            p = pm_parcel(addr)
            for k in range(3):
                out[p + k] = value >> (16 * k) & 0xFFFF
        else:
            return None
    return out


def runs_of(img):
    runs, cur, start, last = [], bytearray(), None, None
    for p in sorted(img.where):
        if last is None or p != last + 1:
            if cur:
                runs.append((start, bytes(cur)))
            cur, start = bytearray(), p
        cur += struct.pack("<H", img.get(p))
        last = p
    runs.append((start, bytes(cur)))
    return runs


def find_all(runs, pattern):
    hits = []
    for start, blob in runs:
        i = blob.find(pattern)
        while i != -1:
            if i % 2 == 0:
                hits.append(start + i // 2)
            i = blob.find(pattern, i + 1)
    return hits


def gen(stomp_e2, floor_e2, patch, only=None, max_diff=0.25):
    """Per group, the rewrite at the Floor's addresses. A routine that is the same code with some operands relocated (data and code
    addresses that differ per region) is found at the region offset with the fewest differing parcels; the rewrite's parcels are then
    translated: a parcel the rewrite leaves as the Stomp stock keeps the Floor's own value, one it changes and that is a known
    relocated operand (same Stomp value -> same Floor value everywhere in the groups' stock) is written as the Floor's value."""
    stomp, floor = Ldr(stomp_e2), Ldr(floor_e2)
    runs = runs_of(floor)
    out, left, work = [], [], []
    offsets = set()
    for g in patch["groups"]:
        if only and g["name"] not in only:
            continue
        if g.get("space") != "internal":
            left.append((g["name"], "not program memory"))
            continue
        lo, hi = int(g["first"]), int(g["end"])
        seq = stomp.span(lo, hi)
        new = new_parcels(g)
        if seq is None or new is None or any(not lo <= p < hi for p in new):
            left.append((g["name"], "no Stomp stock bytes / not parcels"))
            continue
        hits = find_all(runs, b"".join(struct.pack("<H", v) for v in seq))
        if len(hits) > 1:
            left.append((g["name"], f"{len(hits)} exact matches in the Floor image"))
            continue
        if hits:
            offsets.add(hits[0] - lo)
        work.append((g, lo, hi, seq, new, hits[0] - lo if hits else None))
    # relocated operands: every parcel of a group's stock that the Floor has differently at the group's region offset
    reloc, hi_changes, chosen = {}, set(), {}
    for g, lo, hi, seq, new, off in work:
        if off is None:
            scored = []
            for o in sorted(offsets):
                fl = floor.span(lo + o, hi + o)
                if fl is not None:
                    scored.append((sum(1 for a, b in zip(fl, seq) if a != b), o))
            scored.sort()
            if not scored or scored[0][0] > max_diff * (hi - lo) or (len(scored) > 1 and scored[1][0] == scored[0][0]):
                left.append((g["name"], "no region offset with few differing parcels"))
                continue
            off = scored[0][1]
        chosen[g["name"]] = off
        fl = floor.span(lo + off, hi + off)
        for k, (a, b) in enumerate(zip(seq, fl)):
            if a != b:
                if a == 0xC and b == 0xE and k and seq[k - 1] != fl[k - 1]:
                    continue                             # the companion parcel of a relocated pair, handled with its first
                if reloc.setdefault(a, b) != b:
                    reloc[a] = None                      # one Stomp value, two Floor values: cannot translate it
                if k + 1 < len(seq) and seq[k + 1] == 0xC and fl[k + 1] == 0xE:
                    hi_changes.add(a)
    keys = sorted(k for k, v in reloc.items() if v is not None and k >= 0xA000)

    def bracket(v):
        lower = [k for k in keys if k <= v]
        upper = [k for k in keys if k >= v]
        if not lower or not upper:
            return None
        d1, d2 = reloc[lower[-1]] - lower[-1], reloc[upper[0]] - upper[0]
        return d1 if d1 == d2 else None

    for g, lo, hi, seq, new, _ in work:
        if g["name"] not in chosen:
            continue
        off = chosen[g["name"]]
        fl = floor.span(lo + off, hi + off)
        eff = {p: new.get(p, seq[p - lo]) for p in range(lo, hi)}
        target, tr, bad, comp, unresolved = {}, 0, False, [], []
        literal = {a for a, b in zip(seq, fl) if a == b}       # values the stock has unrelocated in this routine: not addresses
        a_lo, a_hi = 0x80000 + (lo - 0x100000) // 3, 0x80000 + (hi - 0x100000) // 3
        for p in range(lo, hi):
            v, s0 = eff[p], seq[p - lo]
            if v == s0:
                target[p] = fl[p - lo]
            elif reloc.get(v, 0) is None:
                bad = True
            elif v in reloc:
                target[p] = reloc[v]
                tr += 1
                if v in hi_changes and p + 1 < hi and eff[p + 1] == 0xC:
                    comp.append(p + 1)
            elif p + 1 < hi and eff[p + 1] in (8, 9) and a_lo - 8 <= (eff[p + 1] << 16 | v) < a_hi + 8 and off % 3 == 0:
                target[p] = v + off // 3                 # a jump / call target inside the routine itself: it moves with it
                tr += 1
            elif p + 2 < hi and eff[p + 1] in (8, 9) and eff[p + 2] != 0 and v >= 0xA000 and v not in literal and bracket(v) is not None:
                target[p] = v + bracket(v)               # between two relocated addresses that share one offset: it moves the same
                tr += 1
            elif p + 2 < hi and eff[p + 1] in (8, 9) and eff[p + 2] != 0 and v >= 0xA000 and v not in literal:
                unresolved.append((p - lo, hex(v), eff[p + 1]))  # looks like a code / table address outside the routine, not seen in the stock
                target[p] = v
            elif p + 1 < hi and eff[p + 1] == 0xC and 0x6000 <= v <= 0x7600 and v not in literal:
                unresolved.append((p - lo, hex(v)))      # looks like a data address of the relocated heaps, not seen in the stock
                target[p] = v
            else:
                target[p] = v
        for p in comp:
            target[p] = 0xE
        if bad or unresolved:
            left.append((g["name"], "a rewritten parcel is an ambiguous or unseen relocated operand " + str(unresolved[:4])))
            continue
        sets = sorted([p + off, v] for p, v in target.items() if fl[p - lo] != v)
        out.append({"name": g["name"], "engine": g.get("engine"), "about": g.get("about"), "first": lo + off, "end": hi + off,
                    "offset": off, "stock_sha256": sha(fl), "relocated": sum(1 for a, b in zip(seq, fl) if a != b),
                    "translated": tr, "set": sets})
    for names in patch.get("together", []):
        have = [n in {x["name"] for x in out} for n in names]
        if any(have) and not all(have):
            keep = [n for n, h in zip(names, have) if h]
            out = [x for x in out if x["name"] not in keep]
            left += [(n, "its partner " + "/".join(names) + " is not an exact match") for n in keep]
    return {"about": "nocaseguy's bit-exact DSP rewrites (hx-stomp-nam-lite dsp-opt-patch-list, GPL-3.0-or-later) at the Helix Floor 3.80.0 "
                     "Entry 2 addresses: per group the stock range's SHA-256 and the parcels the rewrite changes. No stock code.",
            "source": patch.get("firmware"), "groups": out}, left


def apply(e2, port, only=None, without=None):
    img = Ldr(e2)
    chosen = [g for g in port["groups"] if (not only or g["name"] in only) and not (without and g["name"] in without)]
    for names in port.get("together", []):
        picked = [n for n in names if n in {g["name"] for g in chosen}]
        if picked and len(picked) != len(names):
            raise SystemExit(f"groups {names} go together: select all or none")
    for g in chosen:
        vals = img.span(g["first"], g["end"])
        if vals is None or sha(vals) != g["stock_sha256"]:
            raise SystemExit(f"group {g['name']}: the base's bytes at {g['first']:#x}..{g['end']:#x} are not the stock ones "
                             "(another patch changed that routine?). Leave it out with --without.")
    before = img.snapshot()
    want = {}
    for g in chosen:
        for p, v in g["set"]:
            if p in want and want[p] != v:
                raise SystemExit(f"parcel {p:#x} is set to two values (groups overlap)")
            want[p] = v
    for p, v in want.items():
        img.put(p, v)
    after = Ldr(bytes(img.data)).snapshot()
    expect = dict(before)
    expect.update(want)
    if after != expect or len(img.data) != len(e2):
        raise SystemExit("the patched program is not the base's with exactly the intended parcels changed")
    return bytes(img.data), len(chosen), len(want)


def main():
    a = sys.argv[1:]
    if len(a) < 4 or a[0] not in ("gen", "apply"):
        sys.exit(__doc__)

    def opt(name):
        return set(a[a.index(name) + 1].split(",")) if name in a else None
    if a[0] == "gen":
        patch = json.load(open(a[3], encoding="utf-8"))
        port, left = gen(open(a[1], "rb").read(), open(a[2], "rb").read(), patch, opt("--only"))
        port["together"] = patch.get("together", [])
        json.dump(port, open(a[4], "w", encoding="utf-8"), indent=1)
        print(f"{len(port['groups'])} groups ported, {sum(len(g['set']) for g in port['groups'])} parcels; left out: {len(left)}")
        for n, why in left:
            print("  left out:", n, "-", why)
    else:
        port = json.load(open(a[2], encoding="utf-8"))
        data, ng, npar = apply(open(a[1], "rb").read(), port, opt("--only"), opt("--without"))
        open(a[3], "wb").write(data)
        print(f"{ng} groups applied, {npar} parcels changed in place; Entry 2 length unchanged ({len(data):#x} bytes)")


if __name__ == "__main__":
    main()
