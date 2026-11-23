"""The editor's store file (`floor_emmc_art.py write --input store.json`, `icons --input store.json`).

HX Edit Unbound's "Floor look" page writes it (format 1, posted on issue #10): everything the picture and icon stores need,
so the tool imports no editor code and reads no editor memory file. Pure Python, no hardware: the tool calls `load()`.

    {
      "format": 1,
      "pictures": {"size": 256, "models_dir": "<folder with HX Edit's picture file names, or null: HX Edit's own res>"},
      "backgrounds": {"scenes_dir": "<folder of <name>.png, 800 x 480>",
                      "assign": {"scenes": [], "default": null, "category": {}, "preset": {}, "stored": {}}, "theme": null},
      "nam": {"preset_ids": [380], "slots": {"1": {"picture": "<png>", "icon": "<png>"}, "2": {"picture": "<png>"}}},
      "icons": {"size": 36}
    }

Anything left out falls back to what the tool does without a file. `assign` / `theme` are inline, in the shape of
auto/assign_default.json. `nam.slots` keys are capture slots "1".."128"; a slot left out (or without `picture` / `icon`) keeps
the model's picture. `nam.preset_ids` is a list so the pedal block (768) can share the table later; the firmware takes one id
today, so the first is used. `format` changes only when a key changes meaning. Unknown keys are ignored.
"""
import json
import os

FORMAT = 1
MAX_PICTURE_SIZE = 256          # the picture store's limit (docs/PICTURE_STORE.md)
MAX_ICON_SIZE = 44              # the signal-flow frame's inside


class StoreInputError(ValueError):
    pass


def _path(value, what, check_files):
    if not isinstance(value, str) or not value:
        raise StoreInputError(f"{what}: a path is expected, got {value!r}")
    if check_files and not os.path.exists(value):
        raise StoreInputError(f"{what}: {value} does not exist")
    return value


def _size(value, what, limit):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= limit:
        raise StoreInputError(f"{what}: a size from 1 to {limit} is expected, got {value!r}")
    return value


def _assign(value, what):
    if not isinstance(value, dict) or not isinstance(value.get("scenes"), list):
        raise StoreInputError(f"{what}: an assignment {{scenes: [...], default, category, preset}} is expected")
    out = {"scenes": [str(x) for x in value["scenes"]], "default": value.get("default"),
           "category": dict(value.get("category") or {}), "preset": dict(value.get("preset") or {}),
           "stored": {str(k): v for k, v in dict(value.get("stored") or {}).items()}}
    return out


def normalize(obj, check_files=True):
    """The file's content as the tool uses it: {size, models_dir, scenes_dir, assign, theme, nam_pid, nam: {slot: {picture,
    icon}}, icon_size}; None where the file says nothing."""
    if not isinstance(obj, dict):
        raise StoreInputError("the file must hold one JSON object")
    if obj.get("format") != FORMAT:
        raise StoreInputError(f"format {obj.get('format')!r}: this tool reads format {FORMAT}")
    pic = obj.get("pictures") or {}
    bg = obj.get("backgrounds") or {}
    nam = obj.get("nam") or {}
    out = {"size": None, "models_dir": None, "scenes_dir": None, "assign": None, "theme": None, "nam_pid": None,
           "nam": {}, "icon_size": None, "cutout": False}
    if pic.get("size") is not None:
        out["size"] = _size(pic["size"], "pictures.size", MAX_PICTURE_SIZE)
    if pic.get("models_dir") is not None:
        out["models_dir"] = _path(pic["models_dir"], "pictures.models_dir", check_files)
    if bg.get("scenes_dir") is not None:
        out["scenes_dir"] = _path(bg["scenes_dir"], "backgrounds.scenes_dir", check_files)
        if bg.get("assign") is None:
            raise StoreInputError("backgrounds.scenes_dir needs backgrounds.assign")
        out["assign"] = _assign(bg["assign"], "backgrounds.assign")
        if bg.get("theme") is not None:
            out["theme"] = _assign(bg["theme"], "backgrounds.theme")
        if bg.get("cutout") is not None:
            if not isinstance(bg["cutout"], bool):
                raise StoreInputError("backgrounds.cutout must be true or false")
            out["cutout"] = bg["cutout"]
    elif bg.get("assign") is not None or bg.get("theme") is not None:
        raise StoreInputError("backgrounds.assign / theme need backgrounds.scenes_dir")
    ids = nam.get("preset_ids")
    if ids is not None:
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and not isinstance(i, bool) and 0 < i < 1000 for i in ids):
            raise StoreInputError("nam.preset_ids: a non-empty list of preset ids (1..999) is expected")
        out["nam_pid"] = ids[0]
    for key, entry in (nam.get("slots") or {}).items():
        try:
            slot = int(key)
        except (TypeError, ValueError):
            raise StoreInputError(f"nam.slots: key {key!r} is not a capture slot") from None
        if not 1 <= slot <= 128 or not isinstance(entry, dict):
            raise StoreInputError(f"nam.slots[{key}]: slots are 1..128, each an object with picture / icon")
        out["nam"][slot] = {k: _path(entry[k], f"nam.slots[{key}].{k}", check_files) if entry.get(k) is not None else None
                            for k in ("picture", "icon")}
    if (obj.get("icons") or {}).get("size") is not None:
        out["icon_size"] = _size(obj["icons"]["size"], "icons.size", MAX_ICON_SIZE)
    return out


def load(path, check_files=True):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise StoreInputError(f"{path}: {e}") from None
    return normalize(obj, check_files)
