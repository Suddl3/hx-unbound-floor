"""The NAM Pedal block on the Floor (NAM_PEDAL=1, nam_floor5.py): a NAM block that plays a pedal model
(FIR, curve, FIR, curve, FIR, curve, FIR) for about 8% of a DSP, with no DMA. Ported from the Helix LT
tree's lt_pedal.py (Suddl3's design); off by default, so a default build is unchanged.

Kernel side only; the ARM side (model entry, P_LIM member init, cost) is in stage_model.py / stage_main.py.
"""
import os

PEDAL = os.environ.get("NAM_PEDAL") == "1"        # off by default: a default build is unchanged

# PEDAL: the NAM Pedal block plays a pedal model, a cheap stand-in for a NAM pedal capture made by the
# converter: FIR a -> curve 1 -> FIR b -> curve 2 -> FIR c -> curve 3 -> FIR d (FIR: y = sum c[k] x[n-k],
# c[0] the newest tap; curve: 65 knots evenly on [-4, 4], linear between, the end segments continued).
# Its User IR: the NAM header (0.5, -0.5, 3.0, 2^e, then word 4 = PED_N / 1024, not 1871 / 1024, so
# NAM blocks and older kernels refuse it, and a pedal block refuses NAM captures), word 5 the input
# level as a NAM capture's, words 6, 7 = 0, then the PED_N coefficients / 2^e in the order below.
# The block's instance P_LIM is PED_TAG. It takes no slot: its slot state lives in its own DM block
# (PSLOT, as a static slot's: the model check, crossfade, tone stack and knobs are the NAM path's), the
# coefficients after it, the four histories in its PM block. No DMA, no far rings.
PED_FIR = (64, 64, 48, 256)                     # taps of FIR a, b, c, d
PED_K = 65                                      # knots of each curve, on [-PED_R, PED_R]
PED_R = 4
PED_N = sum(PED_FIR) + 3 * PED_K                # 627: a, k1, b, k2, c, k3, d
PED_H = sum(PED_FIR)                            # 432 history words (the PM block's room past its own)
PED_KS = PED_K + 1                              # a curve's stride in memory: a pad word, so every FIR stage starts on an even address
PED_CW = 2 * sum(PED_FIR) + 3 * PED_KS          # the coefficient words in memory: each FIR stage in two layouts (O, E) for the SIMD loops
P_LIM = 16                                      # the instance word (pid) a block's tag is set in (0: none)
LIM_TAG = 0x4E4C0000
PED_TAG = LIM_TAG | 0xFE                        # P_LIM of a NAM Pedal block
PSLOT = 146                                     # INST_DM + 1: past the block's own DM words

PEDAL_PATCHES = [
    # a pedal block goes its own way before the slots (ped_entry: its slot is in its DM block)
    ("""    R12 = R0;                           // R12 = this call's count until the layers
""", """    R12 = R0;                           // R12 = this call's count until the layers
    R0 = DM(P_LIM, I0);                 // a NAM Pedal block: its own slot (ped_entry)
    R1 = PED_TAG;
    COMP(R0, R1);
    IF EQ JUMP ped_entry;
"""),
    # the model check: a pedal block wants a pedal model's word count, a NAM block a capture's
    ("""    F3 = 1.8271484375;                  // 1871 / 1024
    COMP(F2, F3);
""", f"""    F3 = 1.8271484375;                  // 1871 / 1024
    F4 = {PED_N / 1024!r};                  // PED_N / 1024: a pedal model's
    R0 = DM(S_PED, I6);
    R0 = PASS R0;
    IF NE F3 = PASS F4;
    COMP(F2, F3);
"""),
    # the load: a pedal model's coefficients (ped_load returns for ld_model)
    ("""    DM(S_TRIM, I6) = F0;
""", """    DM(S_TRIM, I6) = F0;
    R0 = DM(S_PED, I6);
    R0 = PASS R0;
    IF NE JUMP ped_load;
"""),
    # the block: the pedal model instead of the layers and the head, then the mix as NAM's
    ("""n_eqdone:
""", """n_eqdone:
    R0 = DM(S_PED, I6);
    R0 = PASS R0;
    IF NE JUMP ped_run;
"""),
    # room for the pedal code: report counters only the simulator's bench read
    ("""    R0 = DM(REP + R_NOSLOT);
    R0 = R0 + 1;
    DM(REP + R_NOSLOT) = R0;
""", ""),
    ("""    R1 = I5;                            // the report's owner word of this slot
    R2 = SLOTTAB + 1;
    R1 = R1 - R2;
    R2 = REP + R_OWNERS;
    R1 = R1 + R2;
    I5 = R1;
    R1 = I0;
    DM(0, I5) = R1;
""", ""),
    ("""    DM(REP + R_DMAC) = R0;
""", ""),
    ("""    DM(REP + R_ICEP) = R0;
""", ""),
    ("""    R0 = DM(REP + R_NOSDR);
    R0 = R0 + 1;
    DM(REP + R_NOSDR) = R0;
""", ""),
]

LOAD_STAGES = "\n".join(f"    R4 = {n};\n    CALL ped_lf;" + ("\n    CALL ped_lc;" if st < 3 else "")
                        for st, n in enumerate(PED_FIR))

PEDAL_SUB = f"""
// ---- the NAM Pedal block (PEDAL): its slot state at PSLOT in its own DM block, then the NAM path
ped_entry:
    R0 = I0;
    R1 = PSLOT;
    R0 = R0 + R1;
    R0 = BCLR R0 BY 0;
    I6 = R0;
    R0 = 1;
    DM(S_PED, I6) = R0;
    JUMP m_slot;

// a pedal model's load (from ld_model, I3 = R8 the IR's top word): PED_N words from word 8 down,
// x the scale, into the coefficients after the slot; the histories zero; each stage's
// [base, length, pointer] from PTAB's [offset, length] and the PM block past its own words
ped_load:
    F3 = DM(-3, I3);
    I4 = R8;
    MODIFY(I4, -8);
    I5 = I6;
    MODIFY(I5, SLOT_SIZE);
    M2 = -1;
{LOAD_STAGES}
    R4 = DM(SAVE + 46);
    R1 = INST_PM + 1;
    R4 = R4 + R1;
    R4 = BCLR R4 BY 0;
    I9 = R4;
    R0 = 0;
    LCNTR = PED_H, DO ped_z UNTIL LCE;
ped_z: PM(I9, M9) = R0;
    I4 = I6;
    MODIFY(I4, S_PD);
    I5 = PTAB;
    LCNTR = 4, DO ped_d UNTIL LCE;
      R1 = DM(I5, 1);
      R1 = R1 + R4;
      DM(0, I4) = R1;
      DM(2, I4) = R1;
      R1 = DM(I5, 1);
      DM(1, I4) = R1;
ped_d: MODIFY(I4, 3);
    RTS;

// a FIR stage's coefficients (R4 taps, from the IR's words, x the scale F3) in two layouts of L words, for the
// two-at-a-time loops (ped_fir): O, for a newest sample at an odd address, pairs (c[2i+1], c[2i]); E, for an even
// one, pairs (c[2i+2], c[2i+1]) for i = 0 .. L/2 - 2, then c0, then c[L-1]. I5 at the stage's O, left past its E.
ped_lf:
    R6 = I5;
    R6 = R6 + R4;
    R7 = R6 + R4;
    R5 = 2;
    R7 = R7 - R5;
    I3 = R7;
    F0 = DM(I4, M2);
    F1 = DM(I4, M2);
    F0 = F0 * F3;
    F1 = F1 * F3;
    DM(0, I3) = F0;
    I3 = R6;
    DM(1, I3) = F1;
    DM(I5, 1) = F1;
    DM(I5, 1) = F0;
    R2 = R4;
    R2 = LSHIFT R2 BY -1;
    R2 = R2 - 1;
    LCNTR = R2, DO ped_lp UNTIL LCE;
      F0 = DM(I4, M2);
      F1 = DM(I4, M2);
      F0 = F0 * F3;
      F1 = F1 * F3;
      DM(I5, 1) = F1;
      DM(I5, 1) = F0;
      DM(3, I3) = F1;
ped_lp: DM(I3, 2) = F0;
    R7 = R6 + R4;
    I5 = R7;
    RTS;

// a curve's PED_K knots, then a pad word (the next stage starts on an even address)
ped_lc:
    LCNTR = {PED_K}, DO ped_lcl UNTIL LCE;
      F0 = DM(I4, M2);
      F0 = F0 * F3;
ped_lcl: DM(I5, 1) = F0;
    MODIFY(I5, 1);
    RTS;

// the block: x = in x Drive (F14), FIR a, curve, FIR b, curve, FIR c, curve, FIR d, x the level
ped_run:
    R0 = I6;
    R1 = SLOT_SIZE;
    R7 = R0 + R1;
    R1 = S_PD;
    R6 = R0 + R1;
    F13 = DM(G_LEVEL);
    M0 = 2;
    M1 = 1;
    M8 = -1;
    M10 = -2;
    LCNTR = 16, DO ped_smp UNTIL LCE;
      F8 = PM(I10, M9);
      F8 = F8 * F14;
      I1 = R7;
      I4 = R6;
      LCNTR = 3, DO ped_st UNTIL LCE;
        CALL ped_fir;
        CALL ped_pwl;
        NOP;                          // (no CALL in a loop's last three)
        NOP;
ped_st:   NOP;
      CALL ped_fir;
      F8 = F8 * F13;
      PM(I11, M9) = F8;
ped_smp: NOP;
    JUMP n_mix;

// F8 into this stage's history (I4: its [base, length, pointer]); F8 = sum c[k] x[n-k], the
// coefficients from I1 on
ped_fir:
    B9 = DM(0, I4);
    L9 = DM(1, I4);
    I9 = DM(2, I4);
    PM(I9, M9) = F8;
    DM(2, I4) = I9;
    MODIFY(I9, M8);
    R2 = DM(1, I4);
    M2 = R2;
    R2 = LSHIFT R2 BY -1;
    R0 = I9;
    R1 = 1;
    R0 = R0 AND R1;
    IF EQ JUMP ped_fe;
    R2 = R2 - 1;                        // the newest sample at an odd address: L/2 pairs from the one before it
    MODIFY(I9, M8);
    BIT SET MODE1 PEYEN;
    NOP;
    R8 = R8 - R8;
    R12 = R12 - R12;
    F0 = DM(I1, M0), F4 = PM(I9, M10);
    LCNTR = R2, DO ped_l UNTIL LCE;
ped_l: F12 = F0 * F4, F8 = F8 + F12, F0 = DM(I1, M0), F4 = PM(I9, M10);
    F12 = F0 * F4, F8 = F8 + F12;
    F8 = F8 + F12;
    BIT CLR MODE1 PEYEN;
    NOP;
    R0 = S8;
    F8 = F8 + F0;
    MODIFY(I1, M2);
    MODIFY(I4, 3);
    RTS;
ped_fe:                                 // at an even address: x[n] c0, L/2 - 1 pairs from two before it, x[n-L+1] c[L-1]
    R3 = 2;
    R2 = R2 - R3;
    MODIFY(I1, M2);
    F5 = PM(I9, M10);
    R0 = I1;
    R3 = M2;
    R0 = R0 + R3;
    R3 = 2;
    R0 = R0 - R3;
    I3 = R0;
    F11 = DM(I3, M1);
    F15 = DM(I3, M1);
    F9 = F11 * F5;
    BIT SET MODE1 PEYEN;
    NOP;
    R8 = R8 - R8;
    R12 = R12 - R12;
    F0 = DM(I1, M0), F4 = PM(I9, M10);
    LCNTR = R2, DO ped_l2 UNTIL LCE;
ped_l2: F12 = F0 * F4, F8 = F8 + F12, F0 = DM(I1, M0), F4 = PM(I9, M10);
    F12 = F0 * F4, F8 = F8 + F12;
    F8 = F8 + F12;
    BIT CLR MODE1 PEYEN;
    NOP;
    R0 = S8;
    F8 = F8 + F0;
    MODIFY(I9, M9);
    F5 = PM(I9, M9);
    F10 = F15 * F5;
    F8 = F8 + F9;
    F8 = F8 + F10;
    MODIFY(I1, 2);
    MODIFY(I4, 3);
    RTS;

// F8 through the curve at I1 ({PED_K} knots on [-{PED_R}, {PED_R}]); I1 past it
ped_pwl:
    F0 = {(PED_K - 1) / (2 * PED_R)!r};
    F8 = F8 * F0;
    F0 = {(PED_K - 1) / 2!r};
    F8 = F8 + F0;
    R0 = TRUNC F8;
    R1 = 0;
    R0 = MAX(R0, R1);
    R1 = {PED_K - 2};
    R0 = MIN(R0, R1);
    F1 = FLOAT R0;
    F8 = F8 - F1;
    R1 = I1;
    R0 = R0 + R1;
    I5 = R0;
    F0 = DM(0, I5);
    F1 = DM(1, I5);
    F1 = F1 - F0;
    F1 = F1 * F8;
    F8 = F0 + F1;
    MODIFY(I1, {PED_KS});
    RTS;
"""


# PEDAL needs code room: the entry saves and the exit restores R0-R14 and S0-S14 four at a time (SIMD:
# R n at the address, S n at the next; DM and PM in one instruction), 8 instructions each way for 31
# (was 31). The SAVE layout: R n, S n at SAVE + 1 + 2n (n = 0..14), I0 at +31 and I8 at +46 (as before:
# the kernel reads them there), R15 at +32, the rest after. The rig checks every register on every call.
SAVE_OLD = (["R%d" % n for n in range(16)] + ["S%d" % n for n in range(6)] + ["S%d" % n for n in range(8, 15)] +
            ["B0", "I0", "B1", "B2", "B3", "I6", "B4", "I4", "B5", "I5", "M0", "M1", "M2", "M3", "M4", "B8", "I8",
             "B9", "I9", "B10", "I10", "B11", "I11", "M8", "M9", "M10", "M11", "S6", "S7", "M5", "M6", "M7", "I12",
             "L12"])
SAVE_REST = ["B0", "B1", "B2", "B3", "I6", "B4", "I4", "B5", "I5", "M0", "M1", "M2", "M3", "I8", "M4", "B8", "B9",
             "I9", "B10", "I10", "B11", "I11", "M8", "M9", "M10", "M11", "M5", "M6", "M7", "I12", "L12"]
SAVE_AT = {"I0": 31, "R15": 32, **{r: 33 + k for k, r in enumerate(SAVE_REST)}}
assert SAVE_AT["I8"] == 46 and sorted(SAVE_AT.values()) == list(range(31, 64))


def packed_saves(src):
    import re
    a = src.index("    DM(SAVE + 1) = R0;\n")
    b = src.index("    L8 = 0; L9 = 0; L10 = 0; L11 = 0; L12 = 0;\n") + len("    L8 = 0; L9 = 0; L10 = 0; L11 = 0; L12 = 0;\n")
    old = re.findall(r"DM\(SAVE \+ (\d+)\) = (\w+);", src[a:b])
    assert [r for _, r in old] == SAVE_OLD and [int(k) for k, _ in old] == list(range(1, 64)), old
    pairs = "".join(f"    DM(I4, M2) = R{n}, PM(I12, M10) = R{n + 1};\n" for n in range(0, 14, 2))
    first = ["I4", "M2", "I12", "M10", "L12"]
    entry = "".join(f"    DM(SAVE + {SAVE_AT[r]}) = {r};\n" for r in first)
    entry += ("    L4 = 0;\n    L12 = 0;\n    I4 = SAVE + 1;\n    I12 = SAVE + 3;\n    M2 = 4;\n    M10 = 4;\n"
              "    BIT SET MODE1 PEYEN;\n    NOP;\n" + pairs + "    DM(I4, M2) = R14;\n"
              "    BIT CLR MODE1 PEYEN;\n    NOP;\n    DM(SAVE + 32) = R15;\n    DM(SAVE + 31) = I0;\n")
    entry += "".join(f"    DM(SAVE + {SAVE_AT[r]}) = {r};\n" for r in SAVE_REST if r not in first)
    entry += "    L0 = 0; L1 = 0; L2 = 0; L3 = 0; L5 = 0;\n    L8 = 0; L9 = 0; L10 = 0; L11 = 0;\n"
    src = src[:a] + entry + src[b:]
    a = src.index("    R0 = DM(SAVE + 1);\n")
    b = src.index("    MODE1 = DM(SAVE + 0);\n")
    old = src[a:b]
    assert old.count("DM(SAVE + ") == 63 and "L0 = 0; L1 = 0; L2 = 0; L3 = 0; L4 = 0; L5 = 0;" in old
    rest = re.findall(r"    (\w+) = DM\(SAVE \+ (\d+)\);\n", old)
    order = [r for r, _ in rest if r not in SAVE_OLD[:29] and r not in ("S6", "S7")]
    assert order[:2] == ["B0", "I0"] and len(order) == 32, order
    pairs = "".join(f"    R{n} = DM(I4, M2), R{n + 1} = PM(I12, M10);\n" for n in range(0, 14, 2))
    exit_ = ("    I4 = SAVE + 1;\n    I12 = SAVE + 3;\n    M2 = 4;\n    M10 = 4;\n    BIT SET MODE1 PEYEN;\n    NOP;\n"
             + pairs + "    R14 = DM(I4, M2);\n    BIT CLR MODE1 PEYEN;\n    NOP;\n    R15 = DM(SAVE + 32);\n"
             "    L0 = 0; L1 = 0; L2 = 0; L3 = 0; L4 = 0; L5 = 0;\n    L8 = 0; L9 = 0; L10 = 0; L11 = 0;\n")
    exit_ += "".join(f"    {r} = DM(SAVE + {SAVE_AT[r]});\n" for r in order)
    return src[:a] + exit_ + src[b:]


def ped_ref(coefs, x, gain, level, state=None):
    """The pedal model as ped_run computes it, float32 op for op: (outputs, state). coefs: the PED_N loaded words (the
    model's order); x: the block's input samples (floats); state: the histories, pointers and sample count.
    Each FIR stage runs two chains (the SIMD loops of ped_fir): with the newest sample at an odd address
    L/2 pairs (c[2i+1] x[n-2i-1] on one chain, c[2i] x[n-2i] on the other); at an even address c0 x[n], L/2 - 1 pairs
    (c[2i+2] x[n-2i-2], c[2i+1] x[n-2i-1]) and c[L-1] x[n-L+1]; each chain a running sum, the chains added, then the
    head and the tail."""
    import nam_lite
    ssim = nam_lite.ssim
    f = lambda v: ssim.b2f(ssim.f2b(v))
    if state is None:
        state = [[[0.0] * n for n in PED_FIR], [0] * 4]
    hs, ps = state
    out = []
    for s in x:
        v = f(s * gain)
        o = 0
        for st in range(4):
            n = PED_FIR[st]
            h, p = hs[st], ps[st]
            h[p] = v
            c = coefs[o:o + n]
            xk = lambda k: h[(p - k) % n]
            ax = ay = 0.0
            if p % 2:
                for i in range(n // 2):
                    ax = f(ax + f(c[2 * i + 1] * xk(2 * i + 1)))
                    ay = f(ay + f(c[2 * i] * xk(2 * i)))
                acc = f(ax + ay)
            else:
                for i in range(n // 2 - 1):
                    ax = f(ax + f(c[2 * i + 2] * xk(2 * i + 2)))
                    ay = f(ay + f(c[2 * i + 1] * xk(2 * i + 1)))
                acc = f(f(f(ax + ay) + f(c[0] * xk(0))) + f(c[n - 1] * xk(n - 1)))
            ps[st] = (p + 1) % n
            o += n
            v = acc
            if st < 3:
                u = f(f(v * ((PED_K - 1) / (2 * PED_R))) + (PED_K - 1) / 2)
                i = min(max(int(u) if abs(u) < 2 ** 31 else (2 ** 31 - 1 if u > 0 else -2 ** 31), 0), PED_K - 2)
                fr = f(u - float(i))
                k0, k1 = coefs[o + i], coefs[o + i + 1]
                v = f(k0 + f(f(k1 - k0) * fr))
                o += PED_K
        out.append(f(v * level))
    return out, state


def ped_ref_scalar(coefs, x, gain, level, state=None):
    """The first version of the block (one tap a cycle, one running sum a stage): what the NAM Pedal did before the
    SIMD loops. ped_ref differs from it only by the rounding of the sums (about 1e-7 relative)."""
    import nam_lite
    ssim = nam_lite.ssim
    f = lambda v: ssim.b2f(ssim.f2b(v))
    if state is None:
        state = [[[0.0] * n, 0] for n in PED_FIR]
    out = []
    for s in x:
        v = f(s * gain)
        o = 0
        for st in range(4):
            n = PED_FIR[st]
            h, p = state[st]
            h[p] = v
            acc, prod = 0.0, 0.0
            for k in range(n):
                acc = f(acc + prod)
                prod = f(coefs[o + k] * h[(p - k) % n])
            acc = f(acc + prod)
            state[st][1] = (p + 1) % n
            o += n
            v = acc
            if st < 3:
                u = f(f(v * ((PED_K - 1) / (2 * PED_R))) + (PED_K - 1) / 2)
                i = min(max(int(u) if abs(u) < 2 ** 31 else (2 ** 31 - 1 if u > 0 else -2 ** 31), 0), PED_K - 2)
                fr = f(u - float(i))
                k0, k1 = coefs[o + i], coefs[o + i + 1]
                v = f(k0 + f(f(k1 - k0) * fr))
                o += PED_K
        out.append(f(v * level))
    return out, state


NAMES = ["PED_TAG", "PSLOT", "SLOT_SIZE", "S_PED", "S_PD", "PED_N", "PED_H", "PTAB", "P_LIM"]


def kernel_src(src):
    """The kernel with the NAM Pedal block added (NAM_PEDAL=1)."""
    for a, b in PEDAL_PATCHES:
        assert src.count(a) == 1, a[:70]
        src = src.replace(a, b)
    a = "\nld_model:\n"
    assert src.count(a) == 1
    src = src.replace(a, PEDAL_SUB + a)
    return packed_saves(src)
