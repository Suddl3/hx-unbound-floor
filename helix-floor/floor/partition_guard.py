"""Refuse a build whose entries do not fit their eMMC partitions.

The Floor writes l6ia Entry i to partition i of the table in the main program (records {header sector, data sector,
size in sectors} at 0x281160dc.., indexed by {index, name, record} at 0x2811619c). The installer does NOT check the
sizes: FOCUS11 (2026-11-14) had a 24 MB Entry 9 for a 12 MiB partition and the install wrote ~3.2 MB past it, over the
system data at sector 0x1d27e and the start of the user IR store (the owner's IRs and NAM captures in slots 1-119 were
lost). The readers stop at the partition size, so an oversized entry is unusable anyway.

Rule: payload <= size * 512, for every entry, no exceptions. (An earlier version let Entry 2 run into the free sectors
before the next partition's header, for a NAM kernel that needed 0x40d of 0x400 sectors; no current build needs it:
the 2-NAM images have Entry 2 at 0x3f6. A build that grows past 0x400 is refused until that is measured again.)

Runs inside floor_hxf.pack, so no route to an .hxf skips it; the table is printed so a build log records the headroom.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upstream import TOOLS  # noqa: E402
sys.path.insert(0, TOOLS)
import patch_amp as pa  # noqa: E402
import stage_main  # noqa: E402

INDEX = 0x2811619C


def table(e0):
    im = stage_main.Image(e0)
    parts = {}
    for i in range(16):
        idx, _name, rec = struct.unpack_from("<3I", im.rd(INDEX + 12 * i, 12))
        hdr, data, size = struct.unpack_from("<3I", im.rd(rec, 12))
        assert data == hdr + 1 and idx == i, (i, hex(hdr), hex(data))
        parts[i] = (data, size)
    return parts


def check(l6ia_path):
    data, _ = pa.load_l6ia_from_any(l6ia_path)
    return check_data(data)


def check_data(data):
    """(problems, table lines) for an L6IA image (bytes)."""
    parts = table(pa.get_entry_swapped(data, 0))
    bad, lines = [], []
    for i, (sec, size) in sorted(parts.items()):
        n = len(pa.get_entry_swapped(data, i))
        room = size * 512
        lines.append(f"  Entry {i:2d}: {n:>10} B of {room:>10} B (partition {sec:#x}, {size:#x} sectors)")
        if n > room:
            bad.append(f"Entry {i} is {n} bytes, its partition holds {room}: the install would overwrite the next data")
    return bad, lines


if __name__ == "__main__":
    bad, lines = check(sys.argv[1])
    print("\n".join(lines))
    if bad:
        sys.exit("PARTITION GUARD: " + "; ".join(bad))
    print("partition guard: every entry fits")
