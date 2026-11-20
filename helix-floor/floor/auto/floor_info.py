"""Which HX Unbound firmware runs on the Floor: editor command 0x53 (every build has it unless built with NAM_UNBOUND_INFO=0, unbound_info.py).
Read only; nothing on the unit changes. HX Edit must be closed (this tool opens the editor service itself).

  floor_info.py          prints the reply, e.g. {"fmt": 1, "blocks": [[380, 3250]], "feat": ["pair", "mirror", "meter"]}

Stock firmware and builds without the module refuse the command: the tool then says so.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx"))
import hx_ctl  # noqa: E402

CMD = 0x53


def text(value):
    if isinstance(value, bytes):
        return value.decode("ascii", "replace")
    if isinstance(value, dict):
        return {text(k): text(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [text(v) for v in value]
    return value


def info(ctl):
    """The reply's map, or None when the firmware has no command 0x53."""
    try:
        return text(ctl.ed.request(CMD))
    except hx_ctl.HxError as error:
        if "refused" in str(error):
            return None
        raise


def main():
    with hx_ctl.HxCtl(pid=0x4248, timeout=10.0) as ctl:
        got = info(ctl)
    if got is None:
        print("no answer to 0x53: stock firmware, or an image built before 0x53 was on by default")
        return 1
    print(json.dumps(got))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
