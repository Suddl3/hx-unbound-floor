"""Stability of the current edit buffer (e.g. 2 NAM): every 30 s a 4 s tone check (level, dropouts) and
an hx_ctl status (the UI/host link alive). usage: stab2.py minutes"""
import subprocess, sys, time
mins = float(sys.argv[1]); end = time.time() + mins * 60; bad = 0
while time.time() < end:
    t = subprocess.run([sys.executable, "tonecheck.py", "4"], capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        u = subprocess.run([sys.executable, "hx/hx_ctl.py", "--pid", "0x4248", "status"], capture_output=True, text=True,
                           timeout=30).stdout.splitlines()[0]
    except Exception as e:
        u = "UI FAIL %r" % e
    ok = "jumps 0" in t and "FREEZE PROBE" in u
    bad += not ok
    print(time.strftime("%X"), "OK " if ok else "BAD", t.split(", H2")[0], "|", t.split("dB, ")[-1], "|", u[:40], flush=True)
    time.sleep(30)
print("done, bad checks:", bad)
