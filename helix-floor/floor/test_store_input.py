"""The editor's store file (store_input.py): what it accepts, what it refuses, and what it leaves to the tool's defaults.
Pure Python, no hardware, no PIL."""
import json
import os
import tempfile

import store_input as si

POSTED = {                      # the shape posted on issue #10, paths made up (not checked here)
    "format": 1,
    "pictures": {"size": 256, "models_dir": "/models"},
    "backgrounds": {"scenes_dir": "/scenes", "assign": {"scenes": ["synthwave"], "default": "synthwave", "category": {}, "preset": {}},
                    "theme": None},
    "nam": {"preset_ids": [380], "slots": {"1": {"picture": "/p1.png", "icon": "/i1.png"}, "2": {"picture": "/p2.png"}}},
    "icons": {"size": 36},
}


def refused(obj, text):
    try:
        si.normalize(obj, check_files=False)
    except si.StoreInputError as e:
        assert text in str(e), (text, str(e))
        return
    raise AssertionError(f"accepted, but should refuse ({text}): {obj}")


n = si.normalize(POSTED, check_files=False)
assert n["size"] == 256 and n["models_dir"] == "/models" and n["scenes_dir"] == "/scenes" and n["theme"] is None
assert n["assign"] == {"scenes": ["synthwave"], "default": "synthwave", "category": {}, "preset": {}}
assert n["nam_pid"] == 380 and n["icon_size"] == 36
assert n["nam"] == {1: {"picture": "/p1.png", "icon": "/i1.png"}, 2: {"picture": "/p2.png", "icon": None}}, n["nam"]

# only the format key: every default stays the tool's
e = si.normalize({"format": 1}, check_files=False)
assert e == {"size": None, "models_dir": None, "scenes_dir": None, "assign": None, "theme": None, "nam_pid": None, "nam": {},
             "icon_size": None}, e

# the pedal can share the table later: the first id is the one used today; unknown keys are ignored
n = si.normalize({"format": 1, "nam": {"preset_ids": [380, 768]}, "future": {"x": 1}}, check_files=False)
assert n["nam_pid"] == 380

refused({"format": 2}, "format 2")
refused([], "one JSON object")
refused({"format": 1, "pictures": {"size": 300}}, "pictures.size")
refused({"format": 1, "pictures": {"size": 0}}, "pictures.size")
refused({"format": 1, "icons": {"size": 45}}, "icons.size")
refused({"format": 1, "nam": {"slots": {"0": {}}}}, "slots are 1..128")
refused({"format": 1, "nam": {"slots": {"129": {}}}}, "slots are 1..128")
refused({"format": 1, "nam": {"slots": {"x": {}}}}, "not a capture slot")
refused({"format": 1, "nam": {"slots": {"1": {"picture": 5}}}}, "a path is expected")
refused({"format": 1, "nam": {"preset_ids": []}}, "nam.preset_ids")
refused({"format": 1, "backgrounds": {"scenes_dir": "/s"}}, "needs backgrounds.assign")
refused({"format": 1, "backgrounds": {"assign": {"scenes": []}}}, "need backgrounds.scenes_dir")
refused({"format": 1, "backgrounds": {"scenes_dir": "/s", "assign": {"default": None}}}, "an assignment")

# files are checked when asked to be, and a file that isn't JSON is a clear error
with tempfile.TemporaryDirectory() as d:
    png = os.path.join(d, "p.png")
    open(png, "wb").write(b"x")
    ok = {"format": 1, "nam": {"slots": {"3": {"picture": png}}}}
    f = os.path.join(d, "store.json")
    json.dump(ok, open(f, "w"))
    assert si.load(f)["nam"][3]["picture"] == png
    ok["nam"]["slots"]["3"]["picture"] = os.path.join(d, "missing.png")
    json.dump(ok, open(f, "w"))
    try:
        si.load(f)
        raise AssertionError("a missing picture file was accepted")
    except si.StoreInputError as e:
        assert "does not exist" in str(e), str(e)
    open(f, "w").write("{not json")
    try:
        si.load(f)
        raise AssertionError("a file that is not JSON was accepted")
    except si.StoreInputError:
        pass
print("store input: shape, defaults, refusals and file checks: OK")
