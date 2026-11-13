# DSP headroom tests (Helix Floor)

Scripts used to find how much room the Floor's DSP budget leaves next to NAM blocks, and to check that a
build at a lower NAM price is still stable and sounds the same. Everything goes into the edit buffer of
setlist 0 preset 1: nothing is saved to the unit. Selecting a preset discards the current unsaved
edit buffer. The scripts do not restore the previous preset or its unsaved edits; save or back up
anything needed before deliberately running these hardware tests. They are not installation steps.

Needs `hx_ctl.py` (USB preset control, from andreidevs/helix-lt-nam) in an `hx/` folder, and the hardware
test scripts in `floor/auto/` (`probe.py`, `tonecheck.py`, `soak_eb.py`). Preset blobs are your own dumps
(`hx_ctl` `get_preset_blob`); none are included.

| Script | What it does |
|---|---|
| `dump_costs.py` | Writes the Floor's Table 1 (model, preset id, DSP cost) with short names to a CSV. |
| `scan_blocks.py` | Lists every block model used in a preset backup, heaviest DSP price first. |
| `show_preset.py` | Prints a blob's blocks with their DSP prices. |
| `make_one.py` | Builds a test blob: a 2-NAM base, optionally 1 NAM, plus blocks copied from backup presets. |
| `enc_check.py` | Shows whether a blob re-encodes byte-exact (it only does with `like=`). |
| `try_load.py` | Sends a blob to the edit buffer and reads back which blocks the unit kept. |
| `bracket.py` | Raises the price beside 1 NAM until the unit refuses the preset: brackets the fixed per-DSP cost. |
| `run_headroom.py` | Per blob: load, check it was kept, tonecheck, soak (`soak_eb.py`, real-use stress), tonecheck. |
| `listen_clip.py` | Plays a synthetic pluck riff, or a real DI take (`wavio.py` reads it), through a blob and records it. |

Two facts these scripts depend on:

- The Floor checks the DSP budget when a preset loads and **empties the edit buffer** if a DSP is over
  9,000 units. "Kept" therefore means "fits the budget".
- Re-encode blobs with `hx_ctl.encode_preset(magic, sec, like=original)`. Without `like=` the bytes differ
  and the unit refuses the preset, which looks like a budget refusal.

## Execution and recovery

The headroom command-line tools run only when invoked directly; importing them does not open USB,
play audio, or start a test. `wavio.py` is an offline helper for trusted PCM/float WAV files.

`run_headroom.py` stops at the first load/readback, tone-command, soak, or timeout failure and exits
nonzero. Tone commands have a 120-second deadline; each soak has its requested duration plus five
minutes for setup/checks. It invokes `soak_eb.py --stop-on-freeze`: a confirmed freeze stops the test
without a power cycle. Recovery requires the operator. This flag does not alter standalone
`soak_eb.py`'s historical recovery behavior: without the flag, it can power-cycle through `plug.py`
and `FLOOR_PLUG`, as described in the parent hardware-tests README.

Readback checks compare block model lists, not every parameter. Tone metrics still require human
review; successful process exit alone does not certify audio quality or DSP safety. A command timeout
ends the child process but cannot restore the edit buffer or recover a hung Floor. Do not run alongside
HX Edit or a firmware update.
