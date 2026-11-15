"""Assemble a live-uploaded module (m4/live_bulk.s, m4/ram_art.s, m4/emmc_art.s) to its .bin beside it.

  python asm_live.py m4/emmc_art.s [...]
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def assemble(src):
    src = os.path.join(HERE, src) if not os.path.isabs(src) else src
    with tempfile.TemporaryDirectory() as d:
        obj, binf = os.path.join(d, "m.o"), os.path.join(d, "m.bin")
        zig = [sys.executable, "-m", "ziglang"]
        env = dict(os.environ, ZIG_LOCAL_CACHE_DIR=os.path.join(d, "l"), ZIG_GLOBAL_CACHE_DIR=os.path.join(d, "g"))
        subprocess.run(zig + ["cc", "-target", "thumb-freestanding-eabi", "-mcpu=cortex_m4", "-c", src, "-o", obj],
                       check=True, timeout=60, env=env)
        subprocess.run(zig + ["objcopy", "-O", "binary", "-j", ".text", obj, binf], check=True, timeout=60, env=env)
        code = open(binf, "rb").read()
    out = os.path.splitext(src)[0] + ".bin"
    open(out, "wb").write(code)
    return out, code


if __name__ == "__main__":
    for s in sys.argv[1:]:
        out, code = assemble(s)
        print(f"{out}: {len(code)} bytes")
