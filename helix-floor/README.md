# NAM A2 Lite on the Line 6 Helix Floor: build, install, details

A port of [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite) (NAM A2 Lite on the
HX Stomp) to the **Helix Floor, firmware 3.80.0**. You build a modified firmware file from Line 6's
own stock 3.80.0 file on your PC. No firmware is distributed here, and **a built file must never be
shared**. Overview, status and findings: the [repository README](../README.md).

> **Experimental, one unit tested.** Rehearse the recovery (below) before you rely on it.

For desktop editing, use the maintained [Floor editor setup and pairing guide](../EDITOR.md).
The stock HX Edit prerequisite and the modified Floor editor are separate installations;
installing the editor does not flash the Floor. Source integration and later offline fixes
are recorded in [the November 12 review](../REVIEW-2026-11-12.md).

## What is different from the HX Stomp build

- **Up to two NAM A2 Lite blocks per DSP** (four per preset: Path 1 runs on one DSP, Path 2 on the
  other), under Amp > NAM. Same User IR captures and knobs as upstream at `2e80164`.
- **Memory:** the Floor's DSP has far less free on-chip memory than the Stomp's. Each DSP's third
  "big" block slot (the room for a Cab Dual next to two amps) is cut to a normal slot, so a path
  holds **at most two amp-type blocks** (amps, preamps, amp+cab; or one amp and a Cab Dual).
  All 16 block positions per path stay. The kernel streams each layer's weights and the long
  delay lines from SDRAM through external-port DMA channel 0's job queue.
- **Interrupts:** the kernel never touches the interrupt mask. On both units the stock DSP program
  routes programmable interrupt P9I to link port 1 (the Floor's DSP-to-DSP link) and gives neither
  external-port DMA channel an interrupt, so channel 0 can be used whenever it is idle. (Earlier
  builds masked P9I for each call, believing it was channel 0's: that froze the UI at random.)
- **Cost:** about 52.8K cycles per 16-sample call on the unit, **~35% of a DSP** per block. The
  declared DSP cost is 3,600 (`NAM_DSP_COST`), so the Floor's own budget refuses a block that would
  overload a DSP. With the faster PAIR kernel layout (`NAM_PAIR=1`, ~31% per block) a cost of 3,250 is
  tested on the unit: it lets one ~800-unit block (e.g. Chamber) share a DSP with two NAMs. Keep 3,600
  for the default kernel. See FINDINGS "NAM DSP cost 3250" and `floor/auto/headroom/`.
- **Optional kernel path** (off by default, verified bit-exact in the simulator and on the unit):
  `NAM_GATHER=1` fetches each far layer's taps with one scatter/gather (tap-list) DMA and writes
  them back with scatter DMA. No measurable speed gain on hardware; kept for reference.

Details, measurements and the full history: [docs/FINDINGS.md](docs/FINDINGS.md) and
[docs/DESIGN_2NAM.md](docs/DESIGN_2NAM.md).

## Build

Needs Python 3.10+ and `capstone` (`pip install capstone`), plus Line 6's stock Helix Floor
3.80.0 file `Helix_Floor_v3.80.0_0x7d01f5efb.hxf` (MD5 `805caa03e8a30fd6ff7892f32ed5a9f4`).
From the root of this repository:

```bash
PYTHONUTF8=1 python helix-floor/floor/build_floor2.py path/to/Helix_Floor_v3.80.0_0x7d01f5efb.hxf -o Helix_Floor_v3.80.0_NAM2.hxf
```

The build runs every stage's own checks (the NAM kernel's bit-exact KernelCheck in the
simulator, ~5 minutes; partition sizes; the main-program guard tests) and stops on any failure.

Test images (not for playing): `--meter` replaces the NAM output with numbers about each call
(cycles, the instance's memory, the guard state; read them from USB 1 at 48 kHz), `--probe` runs
a tap-list DMA probe, `--diag` beeps a code where the block would be silent.

Optional extras (each its own environment flag; none is on by default):
`NAM_DSP_METER=1` the DSP meter and its two Preferences settings (page 2: DSP Meter / Blocks and DSP Meter / Paths; their
values are **Blocks 0 = On, 1 = Off** and **Paths 0 = Off, 1 = Meters, 2 = Numbers**, defaults Off and Meters, so a fresh
install shows bars only); `NAM_FOCUS_VIEW=1` Focus View (Home's block-selection key; also hooks the UI event post; implied
by `NAM_EMMC_ART=1`); `NAM_EMMC_ART=1` the pictures from the eMMC store (needs the meter); `NAM_SCREEN_MIRROR=1` the editor's
screen mirror. A plain `NAM_DSP_METER=1` build leaves the event post stock and never enters Focus View.
Every build prints the partition guard's table (each entry against its partition; `floor_hxf.py pack` refuses an image
that does not fit, whatever script calls it) and, when the mirror or meter is on, writes `<out>.hxf.live.json` (the
modules' addresses and the image's MD5: copy it to `floor/auto/live.json` or set `HX_LIVE_JSON` for the live tools).

## Captures

Use upstream's converter (`web/`, or its hosted setup page) to turn a `.nam` A2 Lite file into a
User IR `.wav`, and import it into a User IR slot with HX Edit. The Floor stores User IRs the same
way the Stomp does. In the NAM block, **Model** = the IR slot number; a slot without a NAM capture
is silent.

## Install and recovery

Install with Line 6 Updater (Offline Mode, choose the built file). The Updater's last page may show
a web error; the install itself is done once it reports success or the unit restarts. After any
firmware install the Floor starts on a factory setlist.

To go back: hold footswitches **6 + 12** while powering on (update mode), then install the stock
3.80.0 file. Presets survive.

Tip for testing new builds: leave the unit on a preset **without** a NAM block before installing.
The Floor restarts on the last preset, so if a build misbehaves with NAM running, a power cycle
still brings it up without NAM.

Known issue: **stock HX Edit can drop NAM blocks** when it rewrites or backs up a preset,
because it does not know the custom model. The [Floor editor preview](../EDITOR.md) recognizes
the normal ID 380 NAM block; this does not make stock backup/restore lossless or cover every
experimental model layout. Keep independent NAM-preserving records and check the pairing guide.

## NAM Pedal (experimental, off by default)

`NAM_PEDAL=1` adds a second model, **NAM Pedal**, beside NAM A2 Lite: a cheap pedal model (FIR, curve, FIR, curve, FIR, curve, FIR; 627 words, no DMA, about 10K instructions a call against about 33K for a NAM block). The kernel side is `floor/nam_pedal.py`; the build adds the model, a Table 1/2 row (preset id 768 if free, cost 850, `NAM_PEDAL_COST` to change it), browser items and the IR-name title.

- **Needs the PAIR layout** (`NAM_PAIR=1 NAM_NOSENT=1`): on the pinned non-PAIR kernel (f4338695) the pedal is 90 words over the code room. A pedal build is a separate image, not the pinned one. With PAIR the NAM block's cost is nearer 3250 than the default 3600 (`NAM_DSP_COST`).
- Excludes `NAM_GR_METER` and `NAM_555`. The pedal counts as an amp for the two-amps-per-DSP limit, and has to: the stock firmware counts type-0x11 blocks itself and its instance (1418 DM + 446 PM words) needs one of the DSP's two big slots; exempting it would mean shrinking its instance to a normal slot and patching Line 6's own counter, so each DSP holds two amp-type blocks (two NAM, NAM + pedal, or two pedals). Tested on the unit: two NAM on DSP 0 + the pedal on DSP 1 loads and plays (30 s steady; the preset blob has one block list per DSP); three amp-type blocks on one DSP are refused.
- The block is told apart by the instance word `P_LIM` (16) = `0x4E4C00FE`, set by the pedal's graph at creation. A pedal block refuses NAM captures and a NAM block refuses pedal models (silence), by the model's word count in IR word 4.
- Test: `floor/test_nam_pedal.py` (bit-exact against `ped_ref`, refusals both ways, NAM blocks unchanged). Build: `NAM_PEDAL=1 NAM_PAIR=1 NAM_NOSENT=1 NAM_PR1=0 python floor/build_floor2.py <stock.hxf> -o <out>`.
- With `NAM_LB_B0=2` placement (your installed FOCUS27 build) the pedal build lets the block chains fall back to R3, and `NAM_SCREEN_MIRROR` puts the mirror module after segment 1 (the seg0 cave is full otherwise).
- Unit test (2026-11-17, FOCUS27 flags + pedal, `FOCUS28_NAMPEDAL`): NAM block unchanged, pedal block plays a pedal model (level within 0.3 dB of `ped_ref`, odd harmonics only), refuses NAM captures and NAM blocks refuse pedal models, NAM + pedal on one DSP steady for 30 s. Cost measured on the unit: 11,520 cycles a call median (worst 14,016) against 46,976 / 54,848 for a NAM block, so 850 holds. The pedal's own pictures (an original stompbox: big picture for Focus View, 36 px icon for the chain view) are appended to the existing stores by `floor/auto/pedal_picture.py` (about 130 KB, no full store rewrite; `--preview DIR` writes the PNGs, `--dry-run` reads only); power cycle afterwards.

## Layout

| Folder | What |
|---|---|
| `floor/` | The build: stages (`stage_*.py`), kernels (`nam_floor*.py`, current `nam_floor5.py`), tests |
| `dsp/`, `alloc/`, `scope/`, `scripts/` | Research tools used to map the Floor firmware (read-only analysis) |
| `docs/` | Findings and design notes |

The scripts find upstream's `tools/` one level up (this folder sits at the repository root).
