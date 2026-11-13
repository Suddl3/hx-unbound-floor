"""Restart the Helix Floor, or put it in update mode (what holding footswitches 6 + 12 at power-on does), from the PC.
Stock firmware: HX Edit's editor service command 0x57 (handler 0x280f3480, params {0x3f: value}) calls the reset
0x28114d88(value): a non-zero value is first stored as a persistent boot flag (0x28110b60), then the unit resets
2 s later. At boot (0x2811525c) a stored flag v becomes the boot state v << 8 and is cleared:

  bit 17 (v = 0x200)          "Entered Update Mode!": update mode, as 6 + 12
  bits 8..14, 16, 18, 19      factory-restore parts (the firmware itself stores v = 1 after an update; 0xc0f00 = all)

so this tool sends only 0x200 (update mode) or 0 (a plain restart). HX Edit must be closed.

  floor_reboot.py update        restart into update mode (then install with Line 6 Updater, or power-cycle to leave)
  floor_reboot.py restart       a plain restart
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl  # noqa: E402

CMD_REBOOT, K_MODE = 0x57, 0x3F
MODES = {"update": 0x200, "restart": 0}


def reboot(mode, ctl=None):
    value = MODES[mode]
    own = ctl is None
    ctl = ctl or hx_ctl.HxCtl(pid=0x4248, timeout=5.0)
    try:
        r = ctl.ed.request(CMD_REBOOT, {K_MODE: value}, timeout=5)
    finally:
        if own:
            ctl.close()
    return r


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        sys.exit(__doc__)
    r = reboot(sys.argv[1])        # the unit answers "accepted, completes later" (hx_ctl.PENDING): it is restarting
    print(f"{sys.argv[1]}: {'accepted' if r is hx_ctl.PENDING else repr(r)}; the Floor restarts in about 2 s "
          f"(a plain restart was back on USB in ~30 s)")
