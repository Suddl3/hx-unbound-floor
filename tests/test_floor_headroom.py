"""Offline only: forbid real USB/audio imports and replay runner failures with fakes."""
import ast
import builtins
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / 'helix-floor/floor/auto'
HEADROOM = AUTO / 'headroom'
HARDWARE = {'hx_ctl', 'probe', 'sounddevice', 'midi', 'numpy', 'kasa'}


def load_guarded(path, fake_hx=None):
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == 'hx_ctl' and fake_hx is not None:
            return fake_hx
        if name.split('.')[0] in HARDWARE:
            raise AssertionError('Real hardware/audio import forbidden: ' + name)
        return original_import(name, *args, **kwargs)

    spec = importlib.util.spec_from_file_location('offline_headroom_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    with patch('builtins.__import__', guarded):
        # Compile source directly; do not create bytecode files in the checkout.
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    return module, guarded


@pytest.mark.parametrize('filename', [
    'bracket.py', 'dump_costs.py', 'enc_check.py', 'listen_clip.py', 'make_one.py',
    'run_headroom.py', 'scan_blocks.py', 'show_preset.py', 'try_load.py',
])
def test_cli_import_has_no_arguments_files_hardware_or_process_effects(filename):
    path = HEADROOM / filename
    tree = ast.parse(path.read_text(encoding='utf-8'))
    guards = [node for node in tree.body if isinstance(node, ast.If) and
              ast.dump(node.test) == ast.dump(ast.parse('__name__ == "__main__"', mode='eval').body)]
    assert len(guards) == 1
    with patch.object(sys, 'argv', ['offline-import']), \
         patch('subprocess.run', side_effect=AssertionError('process started during import')), \
         patch('builtins.open', side_effect=AssertionError('file opened during import')):
        module, _ = load_guarded(path)
    assert callable(module.main)


@pytest.mark.parametrize('failure', [None, 'initial-readback', 'reload-readback', 'load-error',
                                     'tone-before', 'tone-after', 'tone-timeout', 'soak-exit',
                                     'soak-summary', 'soak-timeout'])
def test_runner_stops_on_every_failure_and_bounds_children(tmp_path, failure):
    auto = tmp_path / 'auto'
    (auto / 'headroom').mkdir(parents=True)
    blob = tmp_path / 'good.bin'
    blob.write_bytes(b'good')
    operations, calls = [], []
    reads = 0

    class Device:
        def __init__(self, **kwargs):
            assert kwargs == {'pid': 0x4248}

        def __enter__(self):
            operations.append('open')
            return self

        def __exit__(self, *args):
            operations.append('close')

        def select(self, preset, *, setlist):
            assert (preset, setlist) == (1, 0)

        def set_preset_blob(self, data):
            assert data == b'good'
            if failure == 'load-error':
                raise RuntimeError('fake USB error')

        def get_preset_blob(self):
            nonlocal reads
            reads += 1
            bad = failure == 'initial-readback' or failure == 'reload-readback' and reads == 2
            return b'bad' if bad else b'good'

    fake = SimpleNamespace(HxCtl=Device,
                           decode_preset=lambda data: (0, [{'model_id': 380 if data == b'good' else 0}]),
                           summarize=lambda sections: sections)
    module, guard = load_guarded(HEADROOM / 'run_headroom.py', fake)

    def run(command, **kwargs):
        calls.append((command, kwargs))
        is_soak = command[1].endswith('soak_eb.py')
        if is_soak:
            assert '--stop-on-freeze' in command
            assert kwargs['timeout'] == 315
            assert kwargs['env']['SOAK_INJECT'] == str(blob.resolve())
            if failure == 'soak-timeout':
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return SimpleNamespace(returncode=1 if failure == 'soak-exit' else 0,
                                   stdout='incomplete' if failure == 'soak-summary' else 'end: 0 freeze(s)', stderr='')
        assert kwargs['timeout'] == 120
        if failure == 'tone-timeout':
            raise subprocess.TimeoutExpired(command, kwargs['timeout'])
        before = len(calls) == 1
        failed = failure == 'tone-before' and before or failure == 'tone-after' and not before
        return SimpleNamespace(returncode=1 if failed else 0, stdout='fake tone metrics', stderr='')

    with patch('builtins.__import__', guard), patch.object(module.subprocess, 'run', run), \
         patch.object(module.time, 'sleep', lambda _: None), patch.object(sys, 'path', list(sys.path)):
        result = module.main([str(auto), '.25', str(blob)])
    assert result == (0 if failure is None else 1)
    assert operations.count('open') == operations.count('close')
    if failure in ('initial-readback', 'load-error'):
        assert not calls
    elif failure in ('tone-before', 'tone-timeout'):
        assert len(calls) == 1
    elif failure in ('soak-exit', 'soak-summary', 'soak-timeout', 'reload-readback'):
        assert len(calls) == 2
    else:
        assert len(calls) == 3
    text = (auto / 'headroom/headroom_run.log').read_text()
    assert ('FAILED:' in text) == (failure is not None)


@pytest.mark.parametrize('minutes', ['0', '-1', 'nan', 'inf'])
def test_invalid_duration_fails_before_hardware_import(minutes, tmp_path):
    module, guard = load_guarded(HEADROOM / 'run_headroom.py')
    with patch('builtins.__import__', guard), pytest.raises(SystemExit) as error:
        module.main([str(tmp_path), minutes, 'unused.bin'])
    assert error.value.code == 2


@pytest.mark.parametrize('stop_on_freeze', [True, False])
def test_actual_soak_freeze_branch_stops_without_reboot_when_requested(stop_on_freeze):
    # Only the AST function body is compiled, with every dependency supplied as
    # a fake. Never import or execute the hardware module's top-level imports.
    tree = ast.parse((AUTO / 'soak_eb.py').read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    clock, logs, reboots, handles = [0.0], [], [], []

    class Midi:
        def __init__(self):
            self.closed = 0
            handles.append(self)

        def close(self):
            self.closed += 1

        def pc(self, *args):
            pass

    namespace = dict(STOP_ON_FREEZE=stop_on_freeze, label='offline', hours=1, period=60, maxf=1,
                     HOME=1, STRESS='', time=SimpleNamespace(time=lambda: clock[0],
                         sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)),
                     log=lambda *parts: logs.append(' '.join(map(str, parts))),
                     midi=SimpleNamespace(Midi=Midi), sel=lambda _: None, inject=lambda: '',
                     check=lambda _: (False, -100.0, -100.0, ''), reboot=lambda: reboots.append(True))
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'offline-soak-main', 'exec'), namespace)
    result = namespace['main']()
    assert result == (1 if stop_on_freeze else 0)
    assert len(reboots) == (0 if stop_on_freeze else 1)
    assert all(handle.closed == 1 for handle in handles)
    assert any('1 freeze(s)' in line for line in logs)
