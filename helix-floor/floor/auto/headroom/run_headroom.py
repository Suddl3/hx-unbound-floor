"""Headroom ladder on the Floor (edit buffer only, nothing saved). For each level blob, lowest first:
put it in HOME's (setlist 0 preset 1) edit buffer, read it back (blocks kept?), tonecheck 10 s, then a
soak_eb run with real-use stress, then tonecheck again. Stops at the first level that fails.
usage: run_headroom.py <auto dir> <minutes per level> <blob> [<blob> ...]"""
import os
import subprocess
import sys
import time

AUTO = sys.argv[1]
MINS = float(sys.argv[2])
BLOBS = sys.argv[3:]
sys.path.insert(0, os.path.join(AUTO, "hx"))
import hx_ctl as hc  # noqa: E402

PY = sys.executable
LOG = os.path.join(AUTO, "headroom", "headroom_run.log")


def log(s):
    line = time.strftime("%H:%M:%S ") + s
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


def load(blob):
    with hc.HxCtl(pid=0x4248) as h:
        h.select(1, setlist=0)
        time.sleep(2)
        h.set_preset_blob(open(blob, "rb").read())
        time.sleep(2)
        _, sec = hc.decode_preset(h.get_preset_blob())
    want = [b["model_id"] for b in hc.summarize(hc.decode_preset(open(blob, "rb").read())[1])]
    got = [b["model_id"] for b in hc.summarize(sec)]
    return want, got


def tone(tag):
    r = subprocess.run([PY, os.path.join(AUTO, "tonecheck.py"), "10"], cwd=AUTO, capture_output=True,
                       text=True, timeout=120)
    log(f"  tonecheck {tag}: {(r.stdout or r.stderr).strip()[-200:]}")


for blob in BLOBS:
    name = os.path.splitext(os.path.basename(blob))[0]
    log(f"=== {name}")
    try:
        want, got = load(blob)
    except BaseException as e:  # noqa: BLE001
        log(f"  load FAILED: {e!r}"[:300])
        break
    log(f"  blocks sent {want}, unit kept {got}")
    if want != got:
        log("  unit did not keep the blocks: stop")
        break
    tone("before")
    env = dict(os.environ, SOAK_INJECT=blob, SOAK_STRESS="real")
    r = subprocess.run([PY, os.path.join(AUTO, "soak_eb.py"), f"headroom_{name}", str(MINS / 60), "60", "1"],
                       cwd=AUTO, env=env, capture_output=True, text=True)
    tail = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()][-3:]
    for ln in tail:
        log("  soak: " + ln[-200:])
    if r.returncode != 0 or not any("0 freeze(s)" in ln for ln in tail):
        log("  FAILED (freeze or soak error): stop")
        break
    try:
        load(blob)
        tone("after")
    except BaseException as e:  # noqa: BLE001
        log(f"  reload FAILED: {e!r}"[:300])
        break
log("done")
