"""Find the Floor's per-DSP fixed price: 1 NAM (3600) on path 0 plus blocks of known price, rising, until the
unit refuses the edit buffer (it empties it). Edit buffer only, nothing saved.
usage: bracket.py <hx dir> <base 2-NAM blob> <backup dir>"""


def main():
    import copy
    import os
    import sys
    import time

    sys.path.insert(0, sys.argv[1])
    import hx_ctl as hc  # noqa: E402

    BASE, BK = sys.argv[2], sys.argv[3]
    B = {  # price, source
        "shimmer": (1800, "setlist2/p014.bin", 0, 7), "hall": (1450, "setlist2/p068.bin", 0, 7),
        "spring": (1338, "setlist2/p001.bin", 0, 6), "glitz": (1025, "setlist2/p001.bin", 0, 7),
        "chamber": (793, "setlist2/p014.bin", 0, 6), "boost": (509, "setlist2/p001.bin", 0, 3),
        "ballistic": (1200, "setlist2/p009.bin", 0, 4), "tape": (1166, "setlist2/p014.bin", 0, 5),
    }
    COMBOS = [
        ["shimmer", "hall"],                                  # 3250
        ["shimmer", "hall", "boost"],                         # 3759
        ["shimmer", "hall", "chamber"],                       # 4043
        ["shimmer", "hall", "glitz"],                         # 4275
        ["shimmer", "hall", "spring"],                        # 4588
        ["shimmer", "hall", "spring", "boost"],               # 5097
    ]
    base = open(BASE, "rb").read()


    def make(names):
        magic, sec = hc.decode_preset(base)
        bl = hc.blocks(sec)
        empty = copy.deepcopy(bl[hc.slot_index(0, 2)])
        bl[hc.slot_index(0, 1)] = copy.deepcopy(empty)          # one NAM only
        for pos, n in enumerate(names, start=2):
            _, f, p, s = B[n]
            _, s2 = hc.decode_preset(open(os.path.join(BK, f), "rb").read())
            bl[hc.slot_index(0, pos)] = copy.deepcopy(hc.blocks(s2)[hc.slot_index(p, s)])
        return hc.encode_preset(magic, sec, like=base)


    last_ok = None
    with hc.HxCtl(pid=0x4248) as h:
        for names in COMBOS:
            blob = make(names)
            price = sum(B[n][0] for n in names)
            h.select(1, setlist=0)
            time.sleep(2)
            h.set_preset_blob(blob)
            time.sleep(2)
            _, sec = hc.decode_preset(h.get_preset_blob())
            kept = [b["model_id"] for b in hc.summarize(sec)]
            ok = len(kept) == 1 + len(names)
            print(f"1 NAM + {'+'.join(names)} = 3600 + {price} = {3600 + price}: {'kept' if ok else 'REFUSED'} {kept}",
                  flush=True)
            if not ok:
                if last_ok is not None:
                    print(f"fixed price per DSP: between {9000 - 3600 - price + 1} and {9000 - 3600 - last_ok}")
                break
            last_ok = price
        h.select(1, setlist=0)


if __name__ == "__main__":
    main()
