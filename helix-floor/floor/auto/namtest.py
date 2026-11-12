"""Edit-buffer only (never saved): 06D FREEZE PROBE (USB 3/4 in) + a copy of 06C's path-0 NAM block at
path 0 position 0. usage: namtest.py [load|show]   (any preset change afterwards discards it)"""
import copy, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl as hc

NAM_MODEL = 380                      # 06C path 0 slot 4 (kind 17, 8 knobs: Model .. Polarity)
with hc.HxCtl(pid=0x4248) as h:
    if sys.argv[1:] == ["show"]:
        cur = h.current(); magic, sec = hc.decode_preset(h.get_preset_blob())
        print(cur["name"], [(i, b) for i, b in enumerate(hc.blocks(sec)) if b and b.get(19) == hc.BLOCK_TYPE][:4])
        sys.exit()
    if os.environ.get("NAM_FROM_06C") == "1":
        h.select(22, setlist=2)                               # 06C: take its NAM block as it is
        blob = h.get_preset_blob()
    else:                                                     # (safe on untested images: 06C never loads)
        blob = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "06C_editbuf.bin"), "rb").read()
    magic, sec = hc.decode_preset(blob)
    assert hc.encode_preset(magic, sec, like=blob) == blob, "re-encode differs: Floor format not understood"
    bl = hc.blocks(sec)
    nam = [(i, b) for i, b in enumerate(bl) if b and b.get(19) == hc.BLOCK_TYPE and b[20][24][25] == NAM_MODEL]
    assert nam, "no NAM block in 06C"
    print("06C NAM at list index", nam[0][0], "slot_index(0,4) =", hc.slot_index(0, 4), "list len", len(bl))
    assert nam[0][0] == hc.slot_index(0, 4), "slot mapping differs on the Floor"
    nam = [nam[0][1]]
    if os.environ.get("NAM_06D_FILE") != "1":
        h.select(23, setlist=2)                               # 06D FREEZE PROBE
    if os.environ.get("NAM_06D_FILE") == "1":                 # (stays on the current, NAM-free preset)                 # (11-11: 06D reused; the saved copy, edit buffer only)
        blob2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "06D_editbuf.bin"), "rb").read()
    else:
        blob2 = h.get_preset_blob()
    magic2, sec2 = hc.decode_preset(blob2)
    assert hc.encode_preset(magic2, sec2, like=blob2) == blob2
    bl2 = hc.blocks(sec2)
    assert not (bl2[hc.slot_index(0, 0)] or {}).get(20), "06D path 0 position 0 not empty"
    npos = int(os.environ.get("NAM_COUNT", "1"))          # NAM blocks in a row on path 0 (same DSP)
    for p in range(npos):
        assert not (bl2[hc.slot_index(0, p)] or {}).get(20), "06D path 0 position %d not empty" % p
        bl2[hc.slot_index(0, p)] = copy.deepcopy(nam[0])
    h.set_preset_blob(hc.encode_preset(magic2, sec2, like=blob2))
    magic3, sec3 = hc.decode_preset(h.get_preset_blob())
    ok = [b for b in hc.blocks(sec3) if b and b.get(19) == hc.BLOCK_TYPE and b[20][24][25] == NAM_MODEL]
    print(h.current()["name"], "NAM blocks in edit buffer:", len(ok))
