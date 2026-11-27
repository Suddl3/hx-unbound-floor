"""floor-web/floor-worker.js, the in-browser Floor build: it loads every Python module the build's scripts import.
A module missing from its SOURCES list fails only in the browser (the Pyodide run cannot fetch it), so check here."""
import itertools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = (ROOT / "floor-web/floor-worker.js").read_text(encoding="utf-8")
DIRS = ("helix-floor/floor", "tools", "tools/sharc")
NOT_IN_BROWSER = {"capstone", "bench2"}             # capstone: stubbed (listing only); bench2: the kernels' --bench only


def listed():
    return set(re.findall(r'"((?:helix-floor|tools)/[\w/.-]+)"', WORKER.split("var SOURCES")[1].split("];")[0]))


def local_module(name):
    for d in DIRS:
        if (ROOT / d / f"{name}.py").is_file():
            return f"{d}/{name}.py"
    return None


def test_listed_files_exist():
    assert all((ROOT / p).is_file() for p in listed())


def test_sources_cover_every_import():
    have = listed()
    need, todo = set(), [p for p in have if p.endswith(".py")]
    while todo:
        text = (ROOT / todo.pop()).read_text(encoding="utf-8")
        names = re.findall(r"^\s*import (\w+)", text, re.M) + re.findall(r"^\s*from (\w+) import", text, re.M)
        for name in set(names) - NOT_IN_BROWSER:
            path = local_module(name)
            if path and path not in need:
                need.add(path)
                todo.append(path)
    assert not need - have, f"missing from floor-worker.js SOURCES: {sorted(need - have)}"


def test_data_files_listed():
    """The stages also read assembled modules and data beside them; each must be fetched too."""
    have = listed()
    for p in [p for p in have if p.startswith("helix-floor/floor/") and p.endswith(".py")]:
        text = (ROOT / p).read_text(encoding="utf-8")
        for name in re.findall(r'os\.path\.join\(HERE, "m4", "(\w+\.(?:bin|json))"\)', text):
            assert f"helix-floor/floor/m4/{name}" in have, f"{p} reads m4/{name}"
    assert (ROOT / re.search(r'var SPLASH = "([^"]+)"', WORKER).group(1)).is_file()


def test_every_toggle_mix_has_a_reference():
    letters = ("S", "P", "M", "N")
    mixes = {"".join(c) for n in range(5) for c in itertools.combinations(letters, n)}
    table = WORKER.split("var REFERENCE")[1].split("};")[0]
    assert set(re.findall(r'"([SPMN]*)": "[0-9a-f]{32}"', table)) == mixes


def test_page_toggles_match_the_worker():
    page = (ROOT / "floor-web/index.html").read_text(encoding="utf-8")
    assert re.findall(r'data-opt="(\w+)" checked', page) == ["splash", "pedal", "meter", "names"]


def test_developer_file_is_handed_out():
    """stage_main writes <image>.live.json (the live tools' addresses); the page offers it beside the firmware, as
    build_floor2.py writes <out.hxf>.live.json, so a builder-page firmware works with helix-floor/floor/auto's tools."""
    assert '.live.json"' in WORKER and "live.hxf_md5 = out" in WORKER and "live: live ?" in WORKER
    page = (ROOT / "floor-web/index.html").read_text(encoding="utf-8")
    assert 'id="liveLink"' in page and 'id="devBox"' in page and '".live.json"' in page


def test_hidden_rows_stay_hidden():
    """The download row is hidden when a build differs from its reference; a display rule on .row must not show it."""
    page = (ROOT / "floor-web/index.html").read_text(encoding="utf-8")
    assert re.search(r"^\[hidden\] \{ display: none !important; \}", page, re.M)


def test_dma_abort_fix_stays_on():
    """NAM_PR1=0 builds the kernel without PR #1 (wait for DMA to be idle before clearing an aborted transfer)."""
    assert "NAM_PR1" not in WORKER


def test_tested_builds_are_current_references():
    """A "has run on a Floor" label must not outlive the build it was earned by."""
    tables = {name: dict(re.findall(r'"([SPMN]*)": "([0-9a-f]{32})"', WORKER.split(f"var {name}")[1].split("};")[0]))
              for name in ("REFERENCE", "TESTED")}
    assert tables["TESTED"]
    assert all(tables["REFERENCE"][mix] == md5 for mix, md5 in tables["TESTED"].items()), tables["TESTED"]
