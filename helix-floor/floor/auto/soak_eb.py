"""Unattended freeze soak for the Floor, EDIT-BUFFER version (2026-11-11: presets 06C/06D reused, so no saved
test presets): HOME (setlist 0, PC 1 = 01B, no NAM) gets SOAK_INJECT (06D_editbuf + NAM blocks) after every hop;
the check hops to AWAY (PC 0 = 01A, no NAM: silence), back to HOME, injects, and needs the tone through the NAMs.
Nothing is ever saved. Original header:

Runs 06C (a NAM test preset) and every PERIOD s checks the Floor still obeys a preset change (probe.check).
On a freeze: log it, power-cycle via a smart plug (plug.py, FLOOR_PLUG), wait for boot, reload 06C, carry on.
With --stop-on-freeze: stop and exit nonzero after a confirmed freeze, without a power cycle.
usage: soak_eb.py LABEL [hours=2] [period=60] [max_freezes=3] [--stop-on-freeze]   -> log floor/auto/soak_LABEL.log"""
import os, subprocess, sys, time, datetime as dt
STOP_ON_FREEZE = "--stop-on-freeze" in sys.argv[1:]
args = [arg for arg in sys.argv[1:] if arg != "--stop-on-freeze"]
import midi, probe
HOME = int(os.environ.get("SOAK_HOME", "1"))
AWAY = int(os.environ.get("SOAK_AWAY", "0"))
STRESS = os.environ.get("SOAK_STRESS", "")   # "1"/"hard": MIDI barrage; "real": one action every 10-20 s (a real-use pace)
STRESS = {"1": "hard"}.get(STRESS, STRESS)
import random
FS_CCS = [49, 50, 51, 52, 53, 54, 55, 56, 57, 58]  # footswitches FS1-5, FS7-11 (Helix Floor MIDI defaults)


def stress(m, secs):
    """Button presses, snapshot changes, pedal sweeps, tap tempo for secs seconds (~8 messages/s)."""
    t_end = time.time() + secs; n = 0
    if STRESS == "real":                    # a footswitch toggle (stomp mode: drives, delay, reverb...) or a
        while True:                         # pedal/knob move (EXP sweep over ~1 s), every 10-20 s
            wait = random.uniform(10, 20)
            if time.time() + wait > t_end:
                time.sleep(max(0, t_end - time.time())); return n
            time.sleep(wait)
            if random.random() < 0.7:
                m.cc(random.choice(FS_CCS), 127); n += 1
            else:
                cc, a, b = random.choice((1, 2)), random.randrange(128), random.randrange(128)
                for k in range(11):
                    m.cc(cc, a + (b - a) * k // 10); n += 1; time.sleep(0.1)
    while time.time() < t_end:
        r = random.random()
        if r < 0.35: m.cc(random.choice(FS_CCS), 127)                 # a footswitch press
        elif r < 0.55: m.cc(69, random.randrange(4))                  # snapshot 1-4
        elif r < 0.85: m.cc(random.choice((1, 2)), random.randrange(128))   # EXP 1 / EXP 2
        else: m.cc(64, 127)                                           # tap tempo
        n += 1; time.sleep(0.12)
    return n   # preset left running: 22 = 06C NAM, 20 = 06A empty

HERE = os.path.dirname(os.path.abspath(__file__))
INJECT = os.environ.get("SOAK_INJECT")      # a preset blob put in HOME's edit buffer after every hop (make555.py)
label = args[0]; hours = float(args[1]) if len(args) > 1 else 2
period = float(args[2]) if len(args) > 2 else 60; maxf = int(args[3]) if len(args) > 3 else 3
LOG = os.path.join(HERE, f"soak_{label}.log")


def sel(p):
    """setlist 0 preset p via USB control (MIDI PCs follow whatever setlist is current)."""
    sys.path.insert(0, os.path.join(HERE, "hx"))
    import hx_ctl as hc
    with hc.HxCtl(pid=0x4248) as h:
        h.select(p, setlist=0)


def check(m, settle=3.0):
    sel(AWAY); time.sleep(settle); off = probe.level()
    sel(HOME); time.sleep(settle); n = inject(); time.sleep(2); on = probe.level()
    return on > -40 and on - off > 15, on, off, n


def log(*a):
    s = dt.datetime.now().strftime("%H:%M:%S ") + " ".join(map(str, a))
    print(s, flush=True); open(LOG, "a").write(s + "\n")


def floor_on_usb():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-PnpDevice -PresentOnly | ? { $_.FriendlyName -eq 'Helix Floor' } | % Status"],
                       capture_output=True, text=True)
    return "OK" in r.stdout


def reboot():
    subprocess.run([sys.executable, os.path.join(HERE, "plug.py"), "cycle", "10"], check=True)
    time.sleep(20)
    t0 = time.time()
    while not floor_on_usb() and time.time() - t0 < 180: time.sleep(5)
    time.sleep(45)                                  # app + DSP up


def inject():
    """HOME's edit buffer <- INJECT; returns the number of model-555 blocks the unit kept ('' when off)."""
    if not INJECT:
        return ""
    sys.path.insert(0, os.path.join(HERE, "hx"))
    import hx_ctl as hc
    err = ""
    for attempt in range(2):                    # one retry: the unit's USB control can reply oddly right after a PC
        try:
            with hc.HxCtl(pid=0x4248) as h:
                h.set_preset_blob(open(INJECT, "rb").read())
                _, sec = hc.decode_preset(h.get_preset_blob())
            n = sum(1 for b in hc.blocks(sec) if isinstance((b or {}).get(20), dict) and b[20].get(24, {}).get(25) == 380)
            return f"  NAM x{n}" + (f" (retry after {err})" if err else "")
        except BaseException as e:              # (hx_ctl exits on a USB claim it can't get: never end the soak)
            err = repr(e)[:120]
            time.sleep(3)
    return f"  inject error {err}"


def main():
    log(f"start {label} (home PC {HOME}{', STRESS ' + STRESS if STRESS else ''}): {hours} h, check every {period:.0f} s, stop after {maxf} freezes")
    end = time.time() + hours * 3600; freezes = []; up_since = time.time()
    m = midi.Midi(); sel(HOME); time.sleep(5); log("inject" + inject())
    while time.time() < end and len(freezes) < maxf:
        sent = stress(m, period) if STRESS else (time.sleep(period) or 0)
        try:
            alive, on, off, nam = check(m)
        except Exception as e:
            alive, on, off, nam = False, float("nan"), float("nan"), ""; log("probe error", repr(e))
        if alive:
            log(f"alive  up {(time.time()-up_since)/60:5.1f} min  NAM tone {on:.1f} / away {off:.1f} dBFS" + (f"  ({sent} msgs)" if STRESS else "") + nam)
            continue
        alive2, on2, off2, _ = check(m)          # confirm
        if alive2:
            log(f"glitch (one failed check: {on:.1f}/{off:.1f}), alive on retry"); continue
        mins = (time.time() - up_since) / 60; freezes.append(mins)
        if STOP_ON_FREEZE:
            log(f"FROZEN after {mins:.1f} min up: stopping without power cycle")
            break
        log(f"FROZEN after {mins:.1f} min up (probe {on2:.1f} / 06C {off2:.1f} dBFS) -> power cycle")
        m.close(); reboot(); m = midi.Midi(); m.pc(HOME); time.sleep(5); up_since = time.time(); inject()
        a, on, off, _ = check(m); log(f"rebooted: {'alive' if a else 'STILL NOT ANSWERING'} ({on:.1f}/{off:.1f})")
        if not a: break
    m.close()
    log(f"end {label}: {len(freezes)} freeze(s) at {[round(x, 1) for x in freezes]} min; "
        f"last uptime {(time.time()-up_since)/60:.1f} min")
    return 1 if STOP_ON_FREEZE and freezes else 0


if __name__ == "__main__":
    raise SystemExit(main())
