"""EXPERIMENT (build/EXPERIMENT-555): NAM's ten knobs on Xenomorph Fuzz Mono's preset id 555, in
upstream's live order and Xenomorph's value types (Gain/Tone/Level float 0..1, Clipping int 0..1,
OscLevel/OscTone float, MinFreq/MaxFreq float 0..6000, WaveShape int 0..2, Sensitivity float).

Same knob words as the Floor kernel (nam_floor5) reads today, so the sound is unchanged at defaults:
Drive 5, ChVol 6, Model 7 (a float is truncated by the kernel), Bass 8, Mid 9, Treble 10, Presence 11,
Polarity 15. Mid Freq (19) and Q (20) are free words nothing reads yet. High Cut is a PLACEHOLDER on
Presence (11, default 0.5): it acts as Presence until the tone stack is ported.
"""
import struct

import patch_amp as pa

X = "HD2_DistXenomorphFuzzMono"
C = "HD2_AmpLine6Clarity"
SPEC = (
    (1, C, "Drive", 5, "Input", 0.5),
    (2, C, "Treble", 10, None, 0.5),
    (3, C, "ChVol", 6, "Output", 0.5),
    (4, X, "Clipping", 15, "Polarity", None),
    (5, C, "Bass", 8, None, 0.5),
    (6, C, "Mid", 9, None, 0.5),
    (7, C, "Boost", 7, "Model", None),
    (8, X, "MaxFreq", 19, "Mid Freq", None),
    (9, X, "WaveShape", 20, "Q", None),
    (10, C, "Presence", 11, "High Cut", 0.5),
)
MODEL_RANGE = (0.0, 1000.0, 1.0)
MID_FREQ = (150.0, 3000.0, 650.0)
Q_LABELS = ("0.7", "1.4", "2.8")


def f2u(f):
    return struct.unpack("<I", struct.pack("<f", f))[0]


def nam_params(e3, info):
    saved = pa.NAM_PARAMS
    pa.NAM_PARAMS = SPEC
    try:
        out = pa.nam_params(e3, info)
    finally:
        pa.NAM_PARAMS = saved
    for p in out:
        s = p["slot"]
        if s == 7:
            p["raw"][5], p["raw"][6], p["raw"][7] = (f2u(v) for v in MODEL_RANGE)
            p["default_word"] = p["raw"][7]
            p["meta"] = [("displayName", 7, "Model"), ("displayType", 7, "dynamicList"), ("displayNameShort", 7, "Model")]
        elif s == 4:
            p["raw"][7], p["default_word"] = 0, 0
            p["meta"] = [("displayType", 7, "list"), ("0", 7, "Normal"), ("1", 7, "Inverted"),
                         ("displayName", 7, "Polarity"), ("displayNameShort", 7, "Polarity")]
        elif s == 8:
            p["raw"][5], p["raw"][6], p["raw"][7] = (f2u(v) for v in MID_FREQ)
            p["default_word"] = p["raw"][7]
            p["meta"] = [("displayType", 7, "hz"), ("displayName", 7, "Mid Freq"), ("displayNameShort", 7, "MidFreq")]
        elif s == 9:
            p["raw"][7], p["default_word"] = 0, 0
            p["meta"] = [("displayType", 7, "list")] + [(str(k), 7, q) for k, q in enumerate(Q_LABELS)] + \
                        [("displayName", 7, "Q"), ("displayNameShort", 7, "Q")]
        elif s == 10:
            p["meta"] = [("displayType", 7, "knob"), ("displayName", 7, "High Cut"), ("displayNameShort", 7, "HighCut")]
    return out
