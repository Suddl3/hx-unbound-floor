# Faster DSP code for stock models (`NAM_DSP_OPT=1`)

nocaseguy's bit-exact SHARC rewrites ([hx-stomp-nam-lite, branch `dsp-opt-patch-list`](https://github.com/nocaseguy/hx-stomp-nam-lite/tree/dsp-opt-patch-list),
GPL-3.0-or-later), carried over to the Helix Floor 3.80.0 DSP program. Off by default. All credit for the rewrites goes to
nocaseguy; their method and measurements are in that branch.

`dsp_opt_floor.json` lists **only the 26 groups that held up on a Floor**. It holds the stock range's hash and the new values, no
stock code. `stage_dsp_opt.py` hashes every range first and writes nothing on a mismatch. Entry 2 keeps its length.

## Measured on one Floor

Each model loaded alone, stock against the 26 groups (272 models compared).

| Blocks | DSP cost saved |
|---|---|
| Amps (59) | 15.6% of the block on average (3.6 points of one DSP) |
| Distortions (41) | 13.6% on average (1.0 point) |
| All models | 177 save more than 0.25 points; none costs more |

- One model, Jazz Rivet 120, gave no meter reading with the groups.
- Sound: 179 recordings (125 models, 48 of them again switched on where the saved block was bypassed, 6 poly and dynamic-reverb
  models), twice each, against four stock runs. Five differed more than stock differs from itself, both times, at the same
  loudness: Cab 2x12 Blue Bell, Cab 2x12 Silver Bell, Simple Delay, Minotaur and Simple 3-Band EQ. So: **not proven bit-exact.**
- Soak: 2 hours, no freeze, NAM tone steady, with Poly Chorus, Dynamic Plate and Minotaur running on the second DSP.

## Not included

- The six poly pitch engine groups (`fft_post`, `e912`, `copy1`, `copy2`, `binscan`, `binscan_x2`): **they can freeze the
  Floor.** With them, Poly Chorus and Infinite Sustain among others stopped the unit until a power cycle. Which of the six
  is at fault is not known.
- `ring_read`, `smallk_2719`, `smallk_271a`: the port leaves data addresses at the Stomp's values. An image with these (and
  10 others) did not boot.
- Every other group of the patch list: untested. **An unproven group can leave the Floor unable to boot** (recovery: footswitches
  6 + 12, install a good file).
- The Floor's DSP cost table is unchanged, so no more blocks fit in a preset yet.

`dsp_opt_port.py gen` guesses where addresses moved. Its output is a candidate, not a proof: test on a unit before listing a group.
