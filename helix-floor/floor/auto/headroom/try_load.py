"""Edit buffer only: select setlist 0 preset 1, send a blob, read back the blocks.
usage: try_load.py <hx dir> <blob>"""
import sys
import time

sys.path.insert(0, sys.argv[1])
import hx_ctl as hc  # noqa: E402

blob = open(sys.argv[2], "rb").read()
with hc.HxCtl(pid=0x4248) as h:
    h.select(1, setlist=0)
    time.sleep(2)
    h.set_preset_blob(blob)
    time.sleep(2)
    _, sec = hc.decode_preset(h.get_preset_blob())
print("sent", [b["model_id"] for b in hc.summarize(hc.decode_preset(blob)[1])])
print("kept", [b["model_id"] for b in hc.summarize(sec)])
