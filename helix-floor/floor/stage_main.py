#!/usr/bin/env python3
"""Build stage E: the main program (Entry 0 only; its identical copy, Entry 1, stays stock).

- seg0 (local SRAM, 0x10000000 + 0x11870) grows into the cave from 0x10011870 (no code
  names it, no stack or heap there: floor-port-findings.md; the bootloader's view of a
  bigger seg0 needs the hardware test). The cave holds, in order: the guard HOOK
  (floor/arm_guards.py, fixed at 0x10011870), then the relocated tables.
- The stock budget check 0x28135070 jumps to HOOK (8 bytes).
- As upstream's add_model_entry0, with the Floor's addresses (no Table 2 "+5" pointer on
  the Floor): Table 1 + the NAM row (a free preset id), Table 2 + the NAM row (short name,
  8 parameters), every browser list holding Clarity relocated with a NAM item, and a new
  folder "NAM" under Amp (category 12) with one item.

usage: stage_main.py <in.l6ia> <out.l6ia>
"""
import json
import struct
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upstream import TOOLS  # noqa: E402
sys.path.insert(0, TOOLS)
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402
import arm_guards  # noqa: E402
import ir_title  # noqa: E402
import screen_mirror  # noqa: E402
import dsp_meter  # noqa: E402
import focus_emmc  # noqa: E402
import clk_stop  # noqa: E402
import unbound_info  # noqa: E402
import nam_pedal  # noqa: E402

E_MAIN, E_COPY, E_DB = 0, 1, 4
TAB1_BASE_PTRS = (0x28134D70, 0x28134DBC, 0x28134DD4, 0x28134EC8, 0x28134F80)
TAB1_END_PTR = 0x28134DB8
TAB1_CNT_INSN = 0x28134DC0
TAB1_CNT_M1_INSNS = (0x28134DA8, 0x28134E32, 0x28134EDA)
TAB2_BASE_PTR, TAB2_CNT_INSN = 0x280E027C, 0x280E01DC
BLIST_PTR_TAB, BLIST_CNT_TAB = 0x28134220, 0x28134350
SUBCAT_CNT, SUBCAT_NAMES = 0x28134480, 0x281344CC
CAVE, CAVE_END = 0x10011870, 0x10020000
SEG0 = (0x10000000, 0x11870)
# 2026-11-06: 2700 (~30%) was too low: the Floor meter reads ~37% a NAM call (55K of ~150K cycles),
# plus ~1% graph overhead (Stomp). Upstream calibrated ~100 units a 1% real, the 9,000 cap at ~95.7%
# real, and saw an overloaded DSP hang the UI/USB while audio plays on (the freezes seen on the test unit).
# 3800 refuses 2 NAMs on one path (7,600 + the ~1,500 an empty preset counts > 9,000), as the unit
# needs, and admits ~3,700 units of effects beside one. Floor calibration still to measure.
DSP_COST = int(os.environ.get("NAM_DSP_COST", "3600"))   # 11-07: measured ~35% a call on the unit (meter 52.8K of ~150K cycles)
NAME, DISPLAY, SHORT, FOLDER = 'HD2_AmpNAMLite', 'NAM A2 Lite', 'NAM A2 Lite', (12, 'NAM')
# NAM_PEDAL=1 (nam_pedal.py): a second model, 'NAM Pedal', beside the NAM block (stage_model adds both). Its
# cost measured on the unit (2026-11-18, meter build, cycles a call): 9,888 median / 12,448 worst against a NAM block's 47,272 /
# 56,656 at cost 3250, so 680-710 by ratio; 750 leaves a margin.
PEDAL = nam_pedal.PEDAL
PEDAL_NAME, PEDAL_DISPLAY, PEDAL_COST, PEDAL_PID = 'HD2_AmpNAMPedal', 'NAM Pedal', int(os.environ.get("NAM_PEDAL_COST", "750")), 768
E555 = bool(os.environ.get("NAM_555"))     # EXPERIMENT build/EXPERIMENT-555: preset id 555, a Distortion-type item
XENO, XENO_PID = 'HD2_DistXenomorphFuzzMono', 555
# 555 variants (stock never pairs browser btype 1 with Table 2 class 2/3; hybrid did, and the unit dropped it):
#   hybrid: Xenomorph's item (btype 1) + Clarity's Table 2 row (category 16, class 2)   [failed 11-07]
#   amp:    Clarity's items (btype 17/18/33) + Clarity's row: the 380 build on preset id 555
#   fx:     Xenomorph's item + Xenomorph's row (category 4, class 0) + its model DB record (stage_model)
V555 = os.environ.get("NAM_555_VARIANT", "hybrid")
assert V555 in ("hybrid", "amp", "fx"), V555


def segments(e0):
    magic, size, icrc, ver, nsegs = struct.unpack_from('<5I', e0, 0)
    assert magic == 0x230B0C5E and size == len(e0), (hex(magic), size, len(e0))
    segs, off = [], 0x34
    for _ in range(nsegs):
        slen, dst, nxt = struct.unpack_from('<3I', e0, off)
        assert nxt == off + 12 + slen
        segs.append([off, off + 12, slen, dst, nxt])
        off = nxt
    return segs


class Image:
    def __init__(self, e0):
        self.b = bytearray(e0)
        self.segs = segments(self.b)

    def fo(self, va, n=4):
        for _, p, l, d, _ in self.segs:
            if d <= va and va + n <= d + l:
                return p + va - d
        raise SystemExit(f"{va:#x} not mapped")

    def rd(self, va, n):
        return bytes(self.b[self.fo(va, n): self.fo(va, n) + n])

    def wr(self, va, data):
        f = self.fo(va, len(data))
        self.b[f: f + len(data)] = data

    def u32(self, va):
        return struct.unpack('<I', self.rd(va, 4))[0]


def tables(im, src_ni, new_ni, n_params, xeno_ni=None, ped_ni=None):
    """The new Table 1, Table 2 and browser lists (upstream add_model_entry0's steps 1-3)."""
    log = []
    tab1 = im.u32(TAB1_BASE_PTRS[0])
    assert all(im.u32(p) == tab1 for p in TAB1_BASE_PTRS)
    rd_cnt, n1 = pa._decode_thumb_movw(im.rd(TAB1_CNT_INSN, 4))
    assert n1 == 823 and im.u32(TAB1_END_PTR) == tab1 + 12 * n1
    for a in TAB1_CNT_M1_INSNS:
        assert pa._decode_thumb_movw(im.rd(a, 4))[1] == n1 - 1
    t1 = bytearray(im.rd(tab1, 12 * n1))
    rows = [struct.unpack_from('<IHHI', t1, 12 * i) for i in range(n1)]
    assert new_ni not in [r[0] for r in rows]
    src = next(r for r in rows if r[0] == src_ni)
    free = sorted(set(range(1, 833)) - {r[1] for r in rows})
    pid = free[0]
    if E555:                                  # Xenomorph Fuzz Mono's row leaves Table 1 (its code stays)
        assert xeno_ni is not None and (xeno_ni, XENO_PID) in [(r[0], r[1]) for r in rows], "no Xenomorph row on 555"
        t1 = bytearray(b"".join(t1[12 * i: 12 * i + 12] for i, r in enumerate(rows) if r[1] != XENO_PID))
        pid = XENO_PID
        n1 -= 1
    t1 += struct.pack('<IHHI', new_ni, pid, 0, DSP_COST)
    pids = [pid]
    if ped_ni is not None:                    # NAM Pedal: preset id 768 (a Thumb-2 immediate) if free, else the next valid one
        assert not E555
        okp = [p for p in free[1:] if p < 256 or pa._thumb_modimm(p) is not None]
        ppid = PEDAL_PID if PEDAL_PID in free else okp[0]
        t1 += struct.pack('<IHHI', ped_ni, ppid, 0, PEDAL_COST)
        pids.append(ppid)
        n1 += 1
        log.append(f"Table 1: NAM Pedal preset id {ppid}, DSP cost {PEDAL_COST}")
    log.append(f"Table 1: {n1} -> {n1 + 1} rows; NAM preset id {pid} (free: {free[:8]}...), DSP cost {DSP_COST} "
               f"(Clarity {src[3]})")
    tab2 = im.u32(TAB2_BASE_PTR)
    rd2, n2 = pa._decode_thumb_movw(im.rd(TAB2_CNT_INSN, 4))
    assert n2 == 823
    t2 = bytearray(im.rd(tab2, 44 * n2))
    row_ni = xeno_ni if E555 and V555 == "fx" else src_ni
    row = bytearray(next(t2[44 * i: 44 * i + 44] for i in range(n2) if struct.unpack_from('<I', t2, 44 * i)[0] == row_ni))
    struct.pack_into('<I', row, 0, new_ni)
    row[4:20] = SHORT.encode('latin1')[:16].ljust(16, b'\0')
    counts = struct.unpack_from('<3I', row, 24)
    assert len(set(counts)) == 1
    struct.pack_into('<3I', row, 24, n_params, n_params, n_params)
    t2 += row
    n2x = 1
    if ped_ni is not None:
        prow = bytearray(row)
        struct.pack_into('<I', prow, 0, ped_ni)
        prow[4:20] = PEDAL_DISPLAY.encode('latin1')[:16].ljust(16, b'\0')
        t2 += prow
        n2x = 2
    log.append(f"Table 2: {n2} -> {n2 + n2x} rows (row from model {row_ni}: category {row[21]}, class {row[22]})")
    dname = DISPLAY.encode('latin1')[:25].ljust(26, b'\0')
    lists, folder_item = [], None
    for idx in range(pa.E0_BLIST_SLOTS):
        lp, lc = im.u32(BLIST_PTR_TAB + 4 * idx), im.u32(BLIST_CNT_TAB + 4 * idx)
        if not lp or not lc:
            continue
        raw = bytearray(im.rd(lp, 48 * lc))
        item = None
        for k in range(lc):
            bt, mi, ci, u12 = struct.unpack_from('<IIiH', raw, 48 * k)
            if E555 and mi == xeno_ni:
                item = bytearray(raw[48 * k: 48 * k + 48])
                struct.pack_into('<IIiH', item, 0, bt, new_ni, ci, pid if ci == -1 else u12)
                item[14:40] = dname
                struct.pack_into('<2I', item, 40, 1, 0)
                if folder_item is None and ci == -1 and V555 != "amp":
                    folder_item = bytes(item)
                lists.append((idx, lc - 1, bytes(raw[:48 * k] + raw[48 * k + 48:])))
                log.append(f"browser list ({idx // 4},{idx % 4}): Xenomorph item removed, {lc} -> {lc - 1} items" +
                           ("" if V555 == "amp" else f"; btype {bt} kept for the NAM item"))
                item = None
                break
            if (not E555 or V555 == "amp") and mi == src_ni:
                item = bytearray(raw[48 * k: 48 * k + 48])
                struct.pack_into('<IIiH', item, 0, bt, new_ni, ci, pid if ci == -1 else u12)
                item[14:40] = dname
                struct.pack_into('<2I', item, 40, 1, 0)
                if ped_ni is not None:          # NAM Pedal's item beside it (its own model and preset id)
                    pitem = bytearray(item)
                    struct.pack_into('<IIiH', pitem, 0, bt, ped_ni, ci, pids[1] if ci == -1 else u12)
                    pitem[14:40] = PEDAL_DISPLAY.encode('latin1')[:25].ljust(26, b'\0')
                    item += pitem
                break
        if item is None:
            continue
        nit = len(item) // 48
        if idx // 4 == FOLDER[0]:
            if folder_item is None and ci == -1:
                folder_item = bytes(item)
        else:
            lists.append((idx, lc + nit, bytes(raw + item)))
            log.append(f"browser list ({idx // 4},{idx % 4}): {lc} -> {lc + nit} items")
    cat, fname = FOLDER
    nsub = im.u32(SUBCAT_CNT + 4 * cat)
    fb = fname.encode('latin1')[:25].ljust(26, b'\0')
    assert nsub < 4 and not im.u32(BLIST_PTR_TAB + 4 * (4 * cat + nsub))
    assert not any(im.rd(SUBCAT_NAMES + 104 * cat + 26 * nsub, 26))
    assert folder_item is not None
    lists.append((4 * cat + nsub, len(folder_item) // 48, folder_item))
    log.append(f"new folder '{fname}' = subcategory {nsub} of category {cat}, {len(folder_item) // 48} item(s)")
    return pids, (rd_cnt, n1 + 1, bytes(t1)), (rd2, n2 + n2x, bytes(t2)), lists, (cat, nsub, fb), log


def rename(im, names):
    """Real-gear names (names/names_map.csv via NAM_NAMES) in place in the stock Table 2 rows (16-byte short
    name) and browser items (26-byte name): {name index: name}. Text only; ids, presets and code unchanged."""
    tab2 = im.u32(TAB2_BASE_PTR)
    n2 = pa._decode_thumb_movw(im.rd(TAB2_CNT_INSN, 4))[1]
    t2 = it = 0
    for i in range(n2):
        ni = im.u32(tab2 + 44 * i)
        if ni in names:
            im.wr(tab2 + 44 * i + 4, names[ni].encode('ascii')[:16].ljust(16, b'\0'))
            t2 += 1
    for idx in range(pa.E0_BLIST_SLOTS):
        lp, lc = im.u32(BLIST_PTR_TAB + 4 * idx), im.u32(BLIST_CNT_TAB + 4 * idx)
        for k in range(lc if lp else 0):
            ni = im.u32(lp + 48 * k + 4)
            if ni in names:
                im.wr(lp + 48 * k + 14, names[ni].encode('ascii')[:25].ljust(26, b'\0'))
                it += 1
    return f"real names: {t2} Table 2 rows, {it} browser items renamed ({len(names)} models)"


def cost_labels(im, t1, t2, lists):
    """EXPERIMENT (NAM_COST_LABELS=1, 2026-11-11): names end with the model's DSP cost as a share of one
    DSP's 9,000-unit budget (Table 1), e.g. "Some Drive (10%)". On the unit the browser item name (26
    bytes) is what a block in the path shows, the Table 2 short name (16 bytes) what the add-block
    catalog shows, so both get it, each name cut to fit its field."""
    cost = {struct.unpack_from('<I', t1, i)[0]: struct.unpack_from('<I', t1, i + 8)[0] for i in range(0, len(t1), 12)}
    for i in range(0, len(t2), 44):                    # the fixed path blocks (inputs, mixer, output) keep their names
        if t2[i + 22] in (9, 10) and bytes(t2[i + 4: i + 20]).split(b'\x00')[0] in (b"A", b"B", b"Mixer", b"OUTPUT"):
            cost.pop(struct.unpack_from('<I', t2, i)[0], None)

    def fit(name, room):
        """name in room chars; a short last word (a variant: Brt, Nrm, Jump, Lead, Ch1) is kept, the rest cut."""
        if len(name) <= room:
            return name
        w = name.split()
        if len(w) >= 2 and len(w[-1]) <= 4:
            return " ".join(w[:-1])[:room - len(w[-1]) - 1].rstrip() + " " + w[-1]
        return name[:room].rstrip()

    def put(raw, at, size, ni):
        c = cost.get(ni)
        if not c:
            return 0
        name = bytes(raw[at: at + size]).split(b'\x00')[0].decode('latin1')
        suf = f" ({max(1, round(c / 90))}%)"
        room = size - 1 if size > 16 else size          # (a browser name keeps its NUL; Table 2's 16 may fill)
        raw[at: at + size] = (fit(name, room - len(suf)) + suf).encode('latin1').ljust(size, b'\x00')
        return 1

    def label(raw, k):
        return put(raw, 48 * k + 14, 26, struct.unpack_from('<I', raw, 48 * k + 4)[0])
    n2 = sum(put(t2, i + 4, 16, struct.unpack_from('<I', t2, i)[0]) for i in range(0, len(t2), 44))
    n, done = 0, set()
    for j, (idx, cnt, raw) in enumerate(lists):
        done.add(idx)
        raw = bytearray(raw)
        n += sum(label(raw, k) for k in range(cnt))
        lists[j] = (idx, cnt, bytes(raw))
    for idx in range(pa.E0_BLIST_SLOTS):
        lp, lc = im.u32(BLIST_PTR_TAB + 4 * idx), im.u32(BLIST_CNT_TAB + 4 * idx)
        if idx in done or not lp or not lc:
            continue
        raw = bytearray(im.rd(lp, 48 * lc))
        n += sum(label(raw, k) for k in range(lc))
        im.wr(lp, bytes(raw))
    return f"cost labels: {n} browser items, {n2} Table 2 rows"


def build_e0(e0, src_ni, new_ni, n_params, xeno_ni=None, names=None, ped_ni=None):
    im = Image(e0)
    name_log = rename(im, names) if names else None
    assert (im.segs[0][3], im.segs[0][2]) == SEG0, "seg0 is not the stock one"
    pids, (rd1, c1, t1), (rd2, c2, t2), lists, (cat, nsub, fb), log = tables(im, src_ni, new_ni, n_params, xeno_ni, ped_ni)
    pid = pids[0]
    if name_log:
        log.append(name_log)
    if os.environ.get("NAM_COST_LABELS") == "1":
        t2 = bytearray(t2)
        log.append(cost_labels(im, t1, t2, lists))
        t2 = bytes(t2)
    hook = arm_guards.build().assemble()
    assert arm_guards.CAVE == CAVE
    cave = bytearray(hook)
    cave += bytes((-len(cave)) & 3)

    def put(data):
        nonlocal cave
        va = CAVE + len(cave)
        cave += data
        cave += bytes((-len(cave)) & 3)
        return va

    a1, a2 = put(t1), put(t2)
    la = [(idx, cnt, put(raw)) for idx, cnt, raw in lists]
    title_base = CAVE + len(cave)
    # 555 amp: Model is knob 6, a float (ir_title knob_pids); hybrid/fx: the item is an effect, not CAT_AMP: no title
    tcode, ca, cb = (ir_title.build(title_base, [], [pid], 6) if E555 and V555 == "amp" else
                     ir_title.build(title_base, [] if E555 else pids))
    put(tcode)
    mirror = None
    if screen_mirror.ENABLED:                          # NAM_SCREEN_MIRROR=1: editor command 0x52 (screen_mirror.py)
        mcode, msyms = screen_mirror.load()
        # NAM_PEDAL: the cave is full (the pedal's rows need ~210 bytes): the mirror module (position-independent;
        # only the trampoline at REGALL names it) goes after segment 1's bytes instead, behind the Focus View reader
        # and the clock-stop wrappers
        mirror = (None if PEDAL else put(mcode), mcode, msyms)
    meter = None
    if dsp_meter.ENABLED:                              # NAM_DSP_METER=1: block costs on the home view (dsp_meter.py)
        dcode, dsyms = dsp_meter.load()
        meter = (put(dcode), dcode, dsyms)
    ck = None
    if clk_stop.ENABLED:                               # NAM_CLK_STOP=1: Transparent also on the MIDI clock stop (clk_stop.py)
        # no room left in the seg0 cave beside the mirror and the meter: the wrappers go after segment 1's bytes
        # (local SRAM bank 2, where the Focus View reader also lives), behind the reader when there is one
        cbase = focus_emmc.VA + (((len(focus_emmc.load()) + 3) & ~3) if focus_emmc.ENABLED else 0)
        ccode, cwrap = clk_stop.build(cbase)
        assert cbase + len(ccode) <= focus_emmc.END, "clock-stop wrappers do not fit after segment 1"
        ck = (cbase, ccode, cwrap)
    # NAM_PEDAL: the cave is full (the pedal's table rows need ~210 bytes), so the screen mirror module (position-independent;
    # only the trampoline at REGALL names it) goes after segment 1's bytes: behind the Focus View reader and the clock-stop
    # wrappers, ahead of the info module
    tail_end = (ck[0] + ((len(ck[1]) + 3) & ~3) if ck else
                focus_emmc.VA + (((len(focus_emmc.load()) + 3) & ~3) if focus_emmc.ENABLED else 0))
    if mirror and mirror[0] is None:
        assert tail_end + len(mirror[1]) <= focus_emmc.END, "the mirror module does not fit after segment 1"
        mirror = (tail_end, mirror[1], mirror[2])
        tail_end += (len(mirror[1]) + 3) & ~3
    ui = None
    if unbound_info.ENABLED:                           # NAM_UNBOUND_INFO=1: editor command 0x53, which firmware this is
        # after segment 1 too (the seg0 cave is full with the mirror and the meter), behind the reader and the wrappers
        ubase = tail_end
        ublocks = [(pids[0], DSP_COST)] + ([(pids[1], PEDAL_COST)] if ped_ni is not None else [])
        ucode = unbound_info.build(ubase, ublocks, (mirror[0] + mirror[2]["fm_regall"]) if mirror else None)
        assert ubase + len(ucode) <= focus_emmc.END, "the unbound info module does not fit after segment 1"
        ui = (ubase, ucode, ublocks)
    assert CAVE + len(cave) <= CAVE_END, f"cave {len(cave)} bytes, room {CAVE_END - CAVE}"
    fe = None
    if focus_emmc.ENABLED:                             # NAM_EMMC_ART=1: Focus View's pictures from the eMMC store
        assert meter, "NAM_EMMC_ART needs NAM_DSP_METER"
        mpatch, focus_fill = focus_emmc.patches(meter[0], meter[1])
        pre_ret = focus_emmc.pre_ret(meter[0], meter[1])     # before the module is patched: it finds dm_paint's stock-paint call
        dpatched = bytearray(meter[1])
        for off, jb in mpatch.items():
            cave[meter[0] - CAVE + off:meter[0] - CAVE + off + len(jb)] = jb
            dpatched[off:off + len(jb)] = jb
        meter = (meter[0], bytes(dpatched), meter[2])   # verify() reads the module back with the patches in
        fe = (focus_emmc.with_literals(focus_emmc.load(), meter[0] + meter[2]["dm_cfg"], focus_fill,
                                       pre_ret),
              [(meter[0] + off, jb) for off, jb in mpatch.items()])
    # pointers and counts (all in seg2: the file offsets don't move with seg0's growth... they do,
    # so everything is written before the cave is spliced in)
    for p in TAB1_BASE_PTRS:
        im.wr(p, struct.pack('<I', a1))
    im.wr(TAB1_END_PTR, struct.pack('<I', a1 + len(t1)))
    im.wr(TAB1_CNT_INSN, pa._encode_thumb_movw(rd1, c1))
    for a in TAB1_CNT_M1_INSNS:
        im.wr(a, pa._encode_thumb_movw(pa._decode_thumb_movw(im.rd(a, 4))[0], c1 - 1))
    im.wr(TAB2_BASE_PTR, struct.pack('<I', a2))
    im.wr(TAB2_CNT_INSN, pa._encode_thumb_movw(rd2, c2))
    for idx, cnt, va in la:
        im.wr(BLIST_PTR_TAB + 4 * idx, struct.pack('<I', va))
        im.wr(BLIST_CNT_TAB + 4 * idx, struct.pack('<I', cnt))
    im.wr(SUBCAT_CNT + 4 * cat, struct.pack('<I', nsub + 1))
    im.wr(SUBCAT_NAMES + 104 * cat + 26 * nsub, fb)
    stock_check = im.rd(arm_guards.TRAMP, 16)
    assert stock_check[:4] == bytes.fromhex("42f22830"), f"0x28135070 is not the stock budget check: {stock_check.hex()}"
    im.wr(arm_guards.TRAMP, arm_guards.tramp_bytes())
    for va, want in ir_title.STOCK.items():
        assert im.rd(va, len(want)) == want, f"title site {va:#x} is not stock: {im.rd(va, len(want)).hex()}"
    assert im.rd(ir_title.RELAY, 8) == ir_title.RELAY_BEFORE, "the relay's 8 bytes are not the old check's tail"
    for va, b in ir_title.site_patches(ca, cb).items():
        im.wr(va, b)
    if mirror:
        log.append(screen_mirror.apply(im, mirror[0], mirror[2]))
    if meter:
        log.append(dsp_meter.apply(im, meter[0], meter[2]))
    if ck:
        for va, want in clk_stop.STOCK.items():
            assert im.rd(va, len(want)) == want, f"clock-stop site {va:#x} is not stock: {im.rd(va, len(want)).hex()}"
        for va, b in clk_stop.site_patches(ck[2]).items():
            im.wr(va, b)
        log.append(f"clock-stop Transparent fix: wrappers {ck[0]:#x} ({len(ck[1])} B), {len(clk_stop.SITES)} sites")
    if ui:                                             # after the mirror: its trampoline is replaced, fm_regall still runs
        log.append(unbound_info.apply(im, ui[0], ui[2], mirror))
    # splice the cave after seg0's bytes and move every later segment
    b, segs = im.b, im.segs
    h0, p0, l0, d0, n0 = segs[0]
    out = bytearray(b[:n0]) + cave + b[n0:]
    delta = len(cave)
    struct.pack_into('<3I', out, h0, l0 + delta, d0, n0 + delta)
    for h, p, l, d, n in segs[1:]:
        struct.pack_into('<3I', out, h + delta, l, d, n + delta)
    struct.pack_into('<I', out, 4, len(out))
    mtail = bool(mirror and PEDAL)                     # (NAM_PEDAL: the mirror module after segment 1)
    if fe or ck or ui or mtail:                        # code after segment 1's bytes: the Focus View reader, the clock-stop wrappers, the mirror, the info
        tail = (fe[0] + bytes((-len(fe[0])) & 3)) if fe else b""
        if ck:
            assert focus_emmc.VA + len(tail) == ck[0], "clock-stop wrappers are not where the sites point"
            tail += ck[1] + bytes((-len(ck[1])) & 3)
        if mtail:
            assert focus_emmc.VA + len(tail) == mirror[0], "the mirror module is not where its trampoline points"
            tail += mirror[1] + bytes((-len(mirror[1])) & 3)
        if ui:
            assert focus_emmc.VA + len(tail) == ui[0], "the unbound info module is not where the trampoline points"
            tail += ui[1]
        out = bytearray(focus_emmc.append_to_seg1(bytes(out), segments, tail))
        if fe:
            log.append(f"Focus View from the eMMC store: {len(fe[0])} B at {focus_emmc.VA:#x} (after segment 1); "
                       "focus_img -> fe_img, the end of dm_paint -> bl fe_hook (the block icons)")
        if ck:
            log.append(f"clock-stop wrappers appended after segment 1 at {ck[0]:#x} ({len(ck[1])} B)")
        if ui:
            log.append(f"unbound info appended after segment 1 at {ui[0]:#x} ({len(ui[1])} B)")
    out = l6ia.fix_internal_crcs(bytes(out))
    log.append(f"seg0 {l0:#x} -> {l0 + delta:#x} bytes (cave {CAVE:#x}..{CAVE + delta:#x}, "
               f"{CAVE_END - CAVE - delta} bytes left); Entry 0 {len(e0):#x} -> {len(out):#x}")
    log.append(f"guards: HOOK {len(hook)} bytes at {CAVE:#x}; 0x28135070 -> ldr.w pc, [pc] ; .word {CAVE | 1:#x}")
    log.append(f"IR-name title: caves {ca:#x} / {cb:#x} ({len(tcode)} B); sites {ir_title.SITE_A:#x}, "
               f"{ir_title.SITE_B:#x} (via relay {ir_title.RELAY:#x}) for preset ids {pids}")
    log.append(f"tables at Table 1 {a1:#x}, Table 2 {a2:#x}, lists " + ", ".join(f"({i // 4},{i % 4}) {v:#x}" for i, _, v in la))
    return out, pid, log, (a1, a2, la, ca, cb, tcode, mirror, meter, fe, ck, ui)


def verify(e0, src_ni, new_ni, addrs, xeno_ni=None, ped_ni=None):
    """Read the result back: segments chain, pointers and counts, the new rows, and the guard
    code in the cave run through the guard tests' interpreter."""
    n_t1 = 823 if E555 else 824 + (ped_ni is not None)
    last_ni = ped_ni if ped_ni is not None else new_ni
    im = Image(e0)
    a1, a2, la, ca, cb, tcode, mirror, meter, fe, ck, ui = addrs
    if fe:
        assert im.rd(focus_emmc.VA, len(fe[0])) == fe[0], "Focus View eMMC reader"
        assert all(im.rd(va, len(b)) == b for va, b in fe[1]), "Focus View eMMC reader's patches in the DSP meter"
    for va, b in ir_title.site_patches(ca, cb).items():
        assert im.rd(va, len(b)) == b
    assert im.rd(ca, len(tcode)) == tcode
    if mirror:
        mva, mcode, msyms = mirror
        assert im.rd(mva, len(mcode)) == mcode
        if not ui:                                     # with the info module its trampoline sits there and calls fm_regall
            assert im.rd(screen_mirror.REGALL, 8) == screen_mirror.tramp(mva + msyms["fm_regall"])
    if ui:
        usyms = unbound_info.load()[1]
        assert im.rd(ui[0], len(ui[1])) == ui[1], "unbound info module"
        assert im.rd(unbound_info.REGALL, 8) == unbound_info.tramp(ui[0] + usyms["ui_regall"]), "unbound info trampoline"
    if meter:
        dva, dcode, dsyms = meter
        assert im.rd(dva, len(dcode)) == dcode
        for va, want in dsp_meter.patches(dva, dsyms).items():
            assert im.rd(va, len(want)) == want, f"DSP meter patch at {va:#x}"
    if ck:
        assert im.rd(ck[0], len(ck[1])) == ck[1], "clock-stop wrappers"
        for va, b in clk_stop.site_patches(ck[2]).items():
            assert im.rd(va, len(b)) == b, f"clock-stop site {va:#x}"
    assert all(im.u32(p) == a1 for p in TAB1_BASE_PTRS)
    assert pa._decode_thumb_movw(im.rd(TAB1_CNT_INSN, 4))[1] == n_t1 and im.u32(TAB1_END_PTR) == a1 + 12 * n_t1
    assert im.u32(TAB2_BASE_PTR) == a2 and pa._decode_thumb_movw(im.rd(TAB2_CNT_INSN, 4))[1] == 824 + (ped_ni is not None)
    assert struct.unpack_from('<I', im.rd(a1 + 12 * (n_t1 - 1), 12))[0] == last_ni
    assert struct.unpack_from('<I', im.rd(a2 + 44 * (823 + (ped_ni is not None)), 44))[0] == last_ni
    if ped_ni is not None:
        assert struct.unpack_from('<I', im.rd(a1 + 12 * (n_t1 - 2), 12))[0] == new_ni
        assert struct.unpack_from('<I', im.rd(a2 + 44 * 823, 44))[0] == new_ni
    for idx, cnt, va in la:
        assert im.u32(BLIST_PTR_TAB + 4 * idx) == va and im.u32(BLIST_CNT_TAB + 4 * idx) == cnt
        mis = [struct.unpack_from('<I', im.rd(va + 48 * k, 48), 4)[0] for k in range(cnt)]
        if E555:                                       # (the Distortion list lost Xenomorph; NAM is in the folder)
            assert xeno_ni not in mis and (new_ni in mis or idx // 4 == 2)
        else:
            assert mis[-1] == last_ni and (ped_ni is None or mis[-2] == new_ni)
    if E555:
        pids = [struct.unpack_from('<IHHI', im.rd(a1 + 12 * i, 12))[1] for i in range(n_t1)]
        assert pids.count(XENO_PID) == 1 and pids[-1] == XENO_PID
        assert any(idx // 4 == FOLDER[0] and new_ni in [struct.unpack_from('<I', im.rd(va + 48 * k, 48), 4)[0]
                                                         for k in range(cnt)] for idx, cnt, va in la)
    assert im.rd(arm_guards.TRAMP, 8) == arm_guards.tramp_bytes()
    assert im.rd(CAVE, len(arm_guards.build().assemble())) == arm_guards.build().assemble()
    return "read back: pointers, counts, new rows, trampoline and HOOK bytes as built"


def live_addresses(addrs):
    """What auto/floor_poke.py's live.json holds for this build (the build writes it beside its output, so no tool has to
    guess or keep a stale one): the mirror and meter modules' bases and the words the live tools use."""
    mirror, meter = addrs[6], addrs[7]
    live = {}
    if mirror:
        live["mirror"] = hex(mirror[0])
        live["fm_ptr"] = hex(mirror[0] + mirror[2]["fm_ptr"])
    if meter:
        live["meter"] = hex(meter[0])
        live["dm_imgs"] = hex(meter[0] + meter[2]["dm_imgs"])
        live["dm_cfg"] = hex(meter[0] + meter[2]["dm_cfg"])
    return live


def main():
    src, out = sys.argv[1], sys.argv[2]
    data, _ = pa.load_l6ia_from_any(src)
    db = pa.parse_entry3_full(pa.get_entry_swapped(data, E_DB))
    src_ni = pa.find_model(db, 'HD2_AmpLine6Clarity')['words'][2]
    nam = pa.find_model(db, NAME)
    assert nam['name'] == NAME, "run stage_model first"
    new_ni, n_params = nam['words'][2], len(nam['params'])
    ped_ni = None
    if PEDAL:
        ped = pa.find_model(db, PEDAL_NAME)
        assert ped['name'] == PEDAL_NAME, "run stage_model with NAM_PEDAL=1 first"
        ped_ni = ped['words'][2]
    e0 = pa.get_entry_swapped(data, E_MAIN)
    assert e0 == pa.get_entry_swapped(data, E_COPY), "Entries 0 and 1 are not identical"
    xeno_ni = pa.find_model(db, XENO)['words'][2] if E555 else None
    names = None
    if os.environ.get("NAM_NAMES"):                 # real-gear names (names/draft_names.py -> names_map.csv)
        import csv
        names = {pa.find_model(db, r['internal'])['words'][2]: r['real_name']
                 for r in csv.DictReader(open(os.environ["NAM_NAMES"], encoding='utf-8'))}
        assert all(len(v) <= 16 and v.isascii() for v in names.values())
    new0, pid, log, addrs = build_e0(e0, src_ni, new_ni, n_params, xeno_ni, names, ped_ni)
    msg = verify(new0, src_ni, new_ni, addrs, xeno_ni, ped_ni)
    # Entry 1 stays stock: on the Floor the app itself runs update mode ("Entered Update Mode!"),
    # so an untouched copy may be the way back if the patched one fails; it also shows which copy runs.
    img, _, _ = l6ia.rebuild_archive(data, {E_MAIN: new0})
    assert pa.get_entry_swapped(img, E_COPY) == e0, "Entry 1 changed"
    open(out, 'wb').write(img)
    for line in log + [msg]:
        print(line)
    live = live_addresses(addrs)
    if live:
        json.dump(live, open(out + ".live.json", "w"), indent=1)
        print(f"wrote {out}.live.json: {live}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
