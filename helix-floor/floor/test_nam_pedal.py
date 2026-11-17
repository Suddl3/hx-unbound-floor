#!/usr/bin/env python3
"""The NAM Pedal block in the kernel simulator (NAM_PEDAL=1, nam_pedal.py).

Needs the PAIR layout (the pinned f4338695 kernel has no room for the pedal's code). Run directly, or
through pytest (it starts itself in a child process with the build's flags):

  A, B  two ordinary NAM blocks (slots 1, 3): bit for bit the NAM reference, as without the pedal
  P1    a NAM Pedal block (P_LIM = PED_TAG) on a pedal model (slot 11): each block bit for bit ped_ref
        (float32, op for op), then through the crossfade and tone stack as any block
  P1 -> a NAM capture (slot 1): refused, silence
  B  -> the pedal model: refused, silence
  P1 -> the pedal model again: plays again, from the silence state
"""
import math
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = dict(NAM_PEDAL="1", NAM_PAIR="1", NAM_NOSENT="1", NAM_KERNEL="nam_floor5", NAM_MAX_BLOCKS="16")


def test_pedal_in_simulator():
    import pytest
    pytest.importorskip("numpy")
    env = {**os.environ, **FLAGS}
    r = subprocess.run([sys.executable, os.path.join(HERE, "test_nam_pedal.py")], env=env, cwd=HERE,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]


def pedal_model(seed=3):
    """A pedal model's PED_N coefficients: decaying FIRs and soft-clipping curves."""
    import nam_pedal as npd
    rnd = random.Random(seed)
    out = []
    for st, n in enumerate(npd.PED_FIR):
        fir = [rnd.uniform(-1, 1) * math.exp(-k / (n / 5)) for k in range(n)]
        fir[0] += 1.0
        s = sum(abs(x) for x in fir)
        out += [0.9 * x / s * (1.0 if st == 3 else 2.5) for x in fir]
        if st < 3:
            out += [math.tanh(2.0 * (-npd.PED_R + 2.0 * npd.PED_R * i / (npd.PED_K - 1))) for i in range(npd.PED_K)]
    assert len(out) == npd.PED_N
    return out


def main():
    import nam_floor5 as n5
    import nam_pedal as npd
    nm, nam_lite, nam_pack = n5.nm, n5.nam_lite, n5.nam_pack
    ssim = nam_lite.ssim
    f32 = nm.f32
    assert n5.PEDAL and n5.PAIR, "run with the flags in FLAGS"
    n5.nm.MAX_STEADY = 60000

    asm, lay = n5.build(inst_bounds=n5.RIG_BOUNDS)
    nm.Rig, rig0 = n5.Rig, nm.Rig
    nm.REP = lay.rep
    try:
        k = nm.KernelCheck(asm, lay, nam_lite.placeholder())
    finally:
        nm.Rig = rig0
    k.silence_fixed_point()
    k.two_models_load()                    # A (slot 1) and B (slot 3) on their NAM models
    r, sim = k.rig, k.rig.sim
    k.two_models_play()

    # the pedal model as a User IR in slot 11: the NAM header, word 4 = PED_N / 1024, then the coefficients
    coefs = pedal_model()
    e = 0
    while max(abs(x) for x in coefs) / 2.0 ** e > 15.5:
        e += 1
    head = [0.5, -0.5, float(nm.C), 2.0 ** e, npd.PED_N / 1024.0, 0.0, 0.0, 0.0]
    ir = [nam_pack.f2b(x) for x in head + [x / 2.0 ** e for x in coefs]]
    ir += [0] * (2048 - len(ir))
    nm.set_ir(sim, 11, ir)
    nm.set_ir(sim, 12, ir)                  # the same model in a second slot: a model change = a reload
    loaded = [ssim.b2f(nam_pack.f2b(ssim.b2f(w) * 2.0 ** e)) for w in ir[8:8 + npd.PED_N]]

    # a NAM Pedal block: the instance's P_LIM = PED_TAG; its DM / PM blocks past the stock words hold stale
    # words (the loader does not clear them)
    P1 = r.inst("P1", 4)
    rnd = random.Random(11)
    for a in range(P1.i0 + 145, P1.i0 + lay.inst_dm_need):
        sim.wr(a, rnd.getrandbits(32))
    for a in range(P1.i8 + 13, P1.i8 + lay.inst_pm_need):
        sim.wr(a, rnd.getrandbits(32))
    sim.wr(P1.i0 + npd.P_LIM, npd.PED_TAG)
    P1.knobs(drive=0.62, vol=0.7, model=11, eq=(0.3, 0.7, 0.45, 0.9))

    def expect(inst, block, label, words):
        got = inst.call(block, label)
        want = inst.pipe.block(words)
        if got != want:
            n = sum(a != b for a, b in zip(got, want))
            err = max(abs(ssim.b2f(a) - ssim.b2f(b)) for a, b in zip(got, want))
            raise nm.CheckFailed(f"{label}: {n} of 16 samples differ from the reference, by up to {err:.3g}")
        return got

    def play_pedal(inst, sig, label, nblk):
        """inst's next call loads the pedal model; then nblk blocks, each ped_ref on the block's input."""
        inst.pipe.cut()
        expect(inst, sig[0], f"{label} (load)", None)
        inst.pipe.knobs(inst.eq)
        g = f32(nm.drive_gain(inst.drive))
        lv = nm.level(inst.vol)
        state = None
        peak = 0.0
        for b in range(nblk):
            x = [ssim.b2f(v) for v in sig[1 + b]]
            ref, state = npd.ped_ref(loaded, x, g, lv, state)
            words = [ssim.f2b(v) for v in ref]
            peak = max(peak, max(abs(v) for v in ref))
            expect(inst, sig[1 + b], f"{label} block {b}", words)
        assert peak > 1e-3, "the pedal test signal is too quiet to show anything"
        return peak

    sig = k.sig("P1", 40)
    peak = play_pedal(P1, sig, "P1 pedal", 30)

    # A and B go on playing as before, between the pedal's blocks
    k.play(k.A, "A")
    for j in range(3):
        P1.knobs(model=12 if j % 2 == 0 else 11)
        peak = play_pedal(P1, sig, "P1 pedal again", 6)    # (a reload: a new silence state each time)
        k.play(k.A, "A")

    # a pedal block on a NAM capture: refused, silence
    P1.knobs(model=1)
    P1.pipe.cut()
    for j in range(20):
        expect(P1, k.sig("P1x", 24)[j % 8], f"P1 on a NAM capture, {j}", None)
    # a NAM block on the pedal model: refused, silence
    k.B.knobs(model=11)
    k.B.pipe.cut()
    for j in range(20):
        expect(k.B, k.sig("Bx", 24)[j % 8], f"B on the pedal model, {j}", None)
    k.A.knobs(model=1)
    k.play(k.A, "A")
    # and back
    P1.knobs(model=11)
    play_pedal(P1, sig, "P1 pedal after the refusals", 8)

    print(f"pedal bit-exact: peak {peak:.3f}; steady calls of the pedal block: "
          f"{[c for lbl, c in r.cycles if lbl.startswith('P1 pedal') and 'load' not in lbl][-1:]}")
    worst = max(c for lbl, c in r.cycles if lbl.startswith("P1 pedal") and "load" not in lbl)
    print(f"pedal block worst steady call: {worst} instructions")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()
    print("PASS")
