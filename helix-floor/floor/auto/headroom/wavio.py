"""Minimal WAV reader (PCM 16/24/32-bit, float 32/64, WAVE_FORMAT_EXTENSIBLE). Returns (fs, float64 array [n, ch])."""
import struct

import numpy as np


def read(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE", "not a WAV file"
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, fs, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE:                       # extensible: real tag in the sub-format GUID
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, fs, bits)
        elif cid == b"data":
            raw = body
        pos += 8 + size + (size & 1)
    tag, ch, fs, bits = fmt
    if tag == 3:
        y = np.frombuffer(raw[:len(raw) // (bits // 8) * (bits // 8)], "<f4" if bits == 32 else "<f8").astype(np.float64)
    elif bits == 16:
        y = np.frombuffer(raw[:len(raw) // 2 * 2], "<i2") / 32768.0
    elif bits == 24:
        b = np.frombuffer(raw[:len(raw) // 3 * 3], np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        y = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif bits == 32:
        y = np.frombuffer(raw[:len(raw) // 4 * 4], "<i4") / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV: tag {tag} bits {bits}")
    return fs, y[: len(y) // ch * ch].reshape(-1, ch)
