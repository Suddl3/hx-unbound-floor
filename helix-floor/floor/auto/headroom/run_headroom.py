"""Run an explicit Floor headroom ladder; edit buffer only, nothing saved.

usage: run_headroom.py <auto dir> <minutes per level> <blob> [<blob> ...]
Replaces current unsaved edits. Stops on failure/freeze; never requests a reboot.
"""
import argparse
import math
import os
import subprocess
import sys
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('auto_dir')
    parser.add_argument('minutes', type=float)
    parser.add_argument('blobs', nargs='+')
    args = parser.parse_args(argv)
    if not math.isfinite(args.minutes) or args.minutes <= 0:
        parser.error('minutes must be a positive finite number')
    auto = os.path.abspath(args.auto_dir)
    blobs = [os.path.abspath(blob) for blob in args.blobs]
    sys.path.insert(0, os.path.join(auto, 'hx'))
    import hx_ctl as hc

    log_path = os.path.join(auto, 'headroom', 'headroom_run.log')
    soak_timeout = math.ceil(args.minutes * 60) + 300

    def log(message):
        line = time.strftime('%H:%M:%S ') + message
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as stream:
            stream.write(line + '\n')

    def load(blob):
        with open(blob, 'rb') as stream:
            data = stream.read()
        want = [block['model_id'] for block in hc.summarize(hc.decode_preset(data)[1])]
        with hc.HxCtl(pid=0x4248) as device:
            device.select(1, setlist=0)
            time.sleep(2)
            device.set_preset_blob(data)
            time.sleep(2)
            _, sections = hc.decode_preset(device.get_preset_blob())
        got = [block['model_id'] for block in hc.summarize(sections)]
        if want != got:
            raise RuntimeError(f'unit did not keep the blocks: sent {want}, kept {got}')
        log(f'  blocks sent {want}, unit kept {got}')

    def tone(tag):
        result = subprocess.run([sys.executable, os.path.join(auto, 'tonecheck.py'), '10'],
                                cwd=auto, capture_output=True, text=True, timeout=120)
        log(f'  tonecheck {tag}: {(result.stdout or result.stderr).strip()[-200:]}')
        if result.returncode:
            raise RuntimeError(f'tonecheck {tag} exited {result.returncode}')

    try:
        for blob in blobs:
            name = os.path.splitext(os.path.basename(blob))[0]
            log(f'=== {name}')
            load(blob)
            tone('before')
            env = dict(os.environ, SOAK_INJECT=blob, SOAK_STRESS='real')
            result = subprocess.run(
                [sys.executable, os.path.join(auto, 'soak_eb.py'), f'headroom_{name}',
                 str(args.minutes / 60), '60', '1', '--stop-on-freeze'],
                cwd=auto, env=env, capture_output=True, text=True, timeout=soak_timeout)
            tail = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()][-3:]
            for line in tail:
                log('  soak: ' + line[-200:])
            if result.returncode or not any('0 freeze(s)' in line for line in tail):
                raise RuntimeError('soak failed, froze, or did not report a completed clean run')
            load(blob)
            tone('after')
    except (Exception, KeyboardInterrupt) as error:
        log(f'FAILED: {type(error).__name__}: {error}'[:300])
        return 130 if isinstance(error, KeyboardInterrupt) else 1
    log('done')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
