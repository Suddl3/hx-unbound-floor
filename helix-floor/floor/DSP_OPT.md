# Faster DSP code for stock models (`NAM_DSP_OPT=1`)

nocaseguy's bit-exact SHARC rewrites ([hx-stomp-nam-lite, branch `dsp-opt-patch-list`](https://github.com/nocaseguy/hx-stomp-nam-lite/tree/dsp-opt-patch-list),
GPL-3.0-or-later), carried over to the Helix Floor 3.80.0 DSP program. Off by default.

> **Do not use: it can freeze the Floor.** With the 32 listed groups, loading Poly Chorus or Infinite Sustain stops the unit until a
> power cycle (confirmed 2026-11-26). The builder page leaves this stage out until the responsible groups are found.
 All credit for the rewrites goes to
nocaseguy; their method and measurements are in that branch.

`dsp_opt_floor.json` lists **only the 32 groups proven on a Floor**. It holds the stock range's hash and the new values, no
stock code. `stage_dsp_opt.py` hashes every range first and writes nothing on a mismatch. Entry 2 keeps its length.

## Measured on one Floor

| Blocks | DSP cost saved |
|---|---|
| 8 amps | 14 to 16% each (1.7 to 4.3 points of one DSP) |
| Minotaur, Scream 808, Vermin | 8 to 14% (about 0.5 points) |
| Chamber reverb (not rewritten) | 0.1 points: the control |

- Meter image, two passes on stock and two with the groups, repeat within 0.05 points.
- Sound: 125 models recorded twice, against four stock runs. Only Cali Bass (-40 / -52 dB, stock runs agree to -62 dB) and
  Sweep Echo (varies a lot on stock too) differed beyond stock's own spread both times. So: **not proven bit-exact.**
- Soak: 2 hours, no freeze, NAM tone steady, rewritten amps running on the second DSP.

## Not included

- `ring_read`, `smallk_2719`, `smallk_271a`: the port leaves data addresses at the Stomp's values. An image with these (and
  10 others) did not boot.
- Every other group of the patch list: untested. **An unproven group can leave the Floor unable to boot** (recovery: footswitches
  6 + 12, install a good file).
- The Floor's DSP cost table is unchanged, so no more blocks fit in a preset yet.

`dsp_opt_port.py gen` guesses where addresses moved. Its output is a candidate, not a proof: test on a unit before listing a group.
