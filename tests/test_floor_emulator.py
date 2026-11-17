"""The Helix Floor's Cortex-M4 modules in an emulator (unicorn), and the committed .bin files against their sources.

Each helix-floor/floor/test_*.py below is a plain script that asserts and prints one OK line; this runs them so CI
catches a change to a module (or its test) that the Floor build would only find on a unit. Needs unicorn (and Pillow
for the background store); the --check of the committed binaries needs zig (pip install ziglang) and is skipped
without it.
"""
import os
import subprocess
import sys

import pytest

FLOOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "helix-floor", "floor")

EMULATOR = ["test_dsp_meter", "test_focus_emmc", "test_block_icons", "test_emmc_art", "test_clk_stop", "test_screen_mirror", "test_unbound_info"]


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=FLOOR, capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("name", EMULATOR)
def test_emulator_script(name):
    pytest.importorskip("unicorn")
    r = run(name + ".py")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


def test_background_store():
    pytest.importorskip("PIL")
    r = run("test_bg_store.py")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


@pytest.mark.parametrize("module", ["dsp_meter.py", "focus_emmc.py"])
def test_committed_binary_matches_source(module):
    pytest.importorskip("ziglang")
    r = run(module, "--check")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
