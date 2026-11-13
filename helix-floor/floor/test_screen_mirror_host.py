"""Offline screen-mirror build guards and decoder tests; never open USB."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import numpy as np
import pytest

import screen_mirror


@pytest.mark.parametrize("value, enabled", [(None, False), ("", False), ("0", False), ("true", False), ("1", True)])
def test_feature_requires_explicit_one_and_import_needs_no_payload(monkeypatch, value, enabled):
    if value is None:
        monkeypatch.delenv("NAM_SCREEN_MIRROR", raising=False)
    else:
        monkeypatch.setenv("NAM_SCREEN_MIRROR", value)
    spec = importlib.util.spec_from_file_location("mirror_gate_test", screen_mirror.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ENABLED is enabled


@pytest.fixture
def host(monkeypatch):
    class HxError(Exception):
        pass
    monkeypatch.setitem(sys.modules, "hx_ctl", SimpleNamespace(HxError=HxError))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    spec = importlib.util.spec_from_file_location("mirror_host_test", Path(__file__).parent / "auto/floor_mirror.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Editor:
    def __init__(self, responses):
        self.responses, self.seq, self.calls = iter(responses), 0, 0

    def request(self, command, *, timeout):
        assert command == 0x52 and timeout == 15
        self.seq = (self.seq + 1) & 0xffff
        self.calls += 1
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def payload(rows, value=0, *, width=800, height=480):
    rows = list(rows)
    bits = [0] * 30
    for row in rows:
        bits[row // 16] |= 1 << (row % 16)
    pixels = np.full((len(rows), width), value, dtype="<u2").tobytes()
    return (struct.pack("<4H2I30H", 0xf100, width, height, len(rows), 0x285a3f50, 0x10929, *bits)
            + pixels + struct.pack("<3I", 1, 2, 3))


def mirror(host, replies):
    editor = Editor(replies)
    return host.Mirror(SimpleNamespace(ed=editor)), editor


def test_full_frame_and_delta_preserve_unchanged_rows(host):
    item, editor = mirror(host, [payload(range(480), 17), payload([479], 23), payload([])])
    assert item.frame().shape == (480, 800, 3)
    item.frame()
    assert np.all(item.img[:479] == 17) and np.all(item.img[479] == 23)
    item.frame()
    assert item.last["rows"] == 0 and editor.calls == 3


def test_initial_partial_frame_resyncs_once(host):
    item, editor = mirror(host, [payload([]), payload(range(480), 19)])
    item.frame()
    assert editor.calls == 2 and editor.seq == 3 and np.all(item.img == 19)
    item, editor = mirror(host, [payload([])] * 3)
    with pytest.raises(host.hx_ctl.HxError, match="after resync"):
        item.frame()
    assert editor.calls == 2 and item.img is None


@pytest.mark.parametrize("bad", [b"", bytes(87), payload([], width=0), payload([], width=65535),
                                 payload([], height=481), payload([], height=0), payload([0])[:-1]])
def test_invalid_dimensions_and_lengths_fail_before_decode(host, bad):
    item, editor = mirror(host, [bad])
    with pytest.raises(host.hx_ctl.HxError):
        item.frame()
    assert editor.calls == 1 and item.img is None


def test_bitmap_count_mismatch_is_rejected(host):
    bad = bytearray(payload([0]))
    struct.pack_into("<H", bad, 16, 0)
    item, _ = mirror(host, [bad])
    with pytest.raises(host.hx_ctl.HxError, match="bitmap/count"):
        item.frame()


def test_missed_reply_invalidates_delta_baseline(host):
    item, editor = mirror(host, [payload(range(480)), OSError("read failed"), payload([]), payload(range(480), 31)])
    item.frame()
    with pytest.raises(OSError, match="read failed"):
        item.frame()
    assert item.img is None
    item.frame()
    assert editor.calls == 4 and np.all(item.img == 31)


def test_every_stock_guard_blocks_mutation_before_trampoline_write(monkeypatch):
    class Image:
        def __init__(self):
            self.data = {va: bytes.fromhex(want) for va, want, _ in screen_mirror.STOCK}
            self.writes = []
        def rd(self, va, size):
            return self.data[va][:size]
        def wr(self, va, data):
            self.writes.append((va, data))
    monkeypatch.setattr(screen_mirror, "load", lambda: (b"code", {"fm_regall": 0}))
    for address, expected, _ in screen_mirror.STOCK:
        # In particular, this covers bytes8/9 of the second replayed BL.
        for offset in range(len(expected) // 2):
            image = Image()
            damaged = bytearray(image.data[address])
            damaged[offset] ^= 1
            image.data[address] = bytes(damaged)
            with pytest.raises(AssertionError):
                screen_mirror.apply(image, 0x10012000, {"fm_regall": 0})
            assert not image.writes
    image = Image()
    screen_mirror.apply(image, 0x10012000, {"fm_regall": 0})
    assert image.writes == [(screen_mirror.REGALL, screen_mirror.tramp(0x10012000))]


def object_with_symbol(value):
    """Minimal ELF layout consumed by the generator, with one fm_ symbol."""
    data = bytearray(0x120)
    struct.pack_into("<I", data, 0x20, 0x40)
    struct.pack_into("<HHH", data, 0x2e, 40, 3, 0)
    struct.pack_into("<10I", data, 0x40 + 40, 0, 2, 0, 0, 0xc0, 16, 2, 0, 4, 16)
    struct.pack_into("<10I", data, 0x40 + 80, 0, 3, 0, 0, 0x100, 11, 0, 0, 1, 0)
    struct.pack_into("<IIIBBH", data, 0xc0, 1, value, 0, 0, 0, 1)
    data[0x100:0x10b] = b"\0fm_regall\0"
    return data


def test_generator_checks_symbols_before_publishing_and_bounds_tools(tmp_path, monkeypatch):
    binary, symbols = tmp_path / "mirror.bin", tmp_path / "mirror.json"
    binary.write_bytes(b"old")
    symbols.write_text(json.dumps({"fm_regall": 0}))
    monkeypatch.setattr(screen_mirror, "BIN", str(binary))
    monkeypatch.setattr(screen_mirror, "SYMS", str(symbols))
    value, calls = [2], []
    def run(args, **options):
        calls.append(options)
        if "cc" in args:
            Path(args[-1]).write_bytes(object_with_symbol(value[0]))
        else:
            Path(args[-1]).write_bytes(b"new")
    monkeypatch.setattr(screen_mirror.subprocess, "run", run)
    with pytest.raises(ValueError, match="symbols differ"):
        screen_mirror.assemble()
    assert binary.read_bytes() == b"old" and json.loads(symbols.read_text()) == {"fm_regall": 0}
    value[0] = 0
    assert screen_mirror.assemble() == (b"new", {"fm_regall": 0})
    assert binary.read_bytes() == b"new"
    assert screen_mirror.assemble(check=True) == (b"new", {"fm_regall": 0})
    assert all(call["timeout"] == 60 and call["check"] for call in calls)
    binary.write_bytes(b"different")
    with pytest.raises(ValueError, match="bytes differ"):
        screen_mirror.assemble(check=True)
    assert binary.read_bytes() == b"different"
