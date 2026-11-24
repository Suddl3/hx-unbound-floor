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


def gen(stomp_e2, floor_e2, patch, only=None):
    stomp, floor = Ldr(stomp_e2), Ldr(floor_e2)
    runs = runs_of(floor)
    out, left = [], []
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
        if len(hits) != 1:
            left.append((g["name"], f"{len(hits)} exact matches in the Floor image"))
            continue
        off = hits[0] - lo
        out.append({"name": g["name"], "engine": g.get("engine"), "about": g.get("about"), "first": hits[0], "end": hits[0] + hi - lo,
                    "offset": off, "stock_sha256": sha(seq),
                    "set": sorted([p + off, v] for p, v in new.items() if seq[p - lo] != v)})
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
