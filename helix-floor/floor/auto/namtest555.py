"""EXPERIMENT 555: edit-buffer only (never saved): 06D FREEZE PROBE + one NAM block on preset id 555 (kind 1,
Xenomorph's value types: ten knobs in upstream order) at path 0 position 0.
usage: namtest555.py [load|show]   (any preset change afterwards discards it)"""
import copy, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl as hc

# Input, Treble, Output | Polarity, Bass, Mid | Model, Mid Freq, Q | High Cut: the same sound as the 06C block
VALUES = [0.7, 0.5, 0.44, 0, 0.5, 0.5, float(os.environ.get("NAM_MODEL_SLOT", "50")), 650.0, 0, 0.5]
BLOCK = {24: {23: False, 25: 555, 26: -1}, 9: int(os.environ.get("NAM_KIND", "1")), 10: True,   # NAM_KIND=17: the AMP variant
         11: {2: 10, 3: 10, 4: VALUES}, 12: {2: 0, 3: 0, 4: []}}
with hc.HxCtl(pid=0x4248) as h:
    cur = h.current()
    print("now on", cur["name"])
    assert cur["name"] == "FREEZE PROBE", "park the Floor on 06D first"
    blob = h.get_preset_blob()
    magic, sec = hc.decode_preset(blob)
    assert hc.encode_preset(magic, sec, like=blob) == blob
    bl = hc.blocks(sec)
    n = int(os.environ.get("NAM_COUNT", "1"))
    if sys.argv[1:] == ["show"]:
        print([(i, b) for i, b in enumerate(bl) if b and b.get(19) == hc.BLOCK_TYPE][:4]); sys.exit()
    for p in range(n):
        assert not (bl[hc.slot_index(0, p)] or {}).get(20), "06D path 0 position %d not empty" % p
        bl[hc.slot_index(0, p)] = {19: hc.BLOCK_TYPE, 20: copy.deepcopy(BLOCK)}
    h.set_preset_blob(hc.encode_preset(magic, sec, like=blob))
    m2, s2 = hc.decode_preset(h.get_preset_blob())
    ok = [b for b in hc.blocks(s2) if b and b.get(19) == hc.BLOCK_TYPE and b[20][24][25] == 555]
    print(h.current()["name"], "555 NAM blocks in edit buffer:", len(ok))
    for b in ok: print(b[20][9], b[20][11][4])
