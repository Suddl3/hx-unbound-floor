# Roadmap

Written 2026-11-12, before any firmware work in this repository. Everything below is a plan, not a result. Each item gets a status tag when it is worked on: **verified on the unit**, **verified offline**, or **hypothesis** (the convention HXtra's research notes use).

## What is known going in

- The Floor's main program is the same code family as the HX Stomp's (an LPC43xx Cortex-M4 application, Thumb-2), but a different link: 4 segments instead of the Stomp's 7, with one large segment at `0x28000000`. Source: HXtra's `docs/research/HELIX_FLOOR_FEASIBILITY.md` (static analysis, no unit) and `helix-floor/docs/FINDINGS.md`.
- Every address HXtra hooks on the Stomp has to be found again on the Floor. None of HXtra's `tools/features/` modules or `src/m4/` code applies as it is.
- The Floor's firmware file carries the main program twice (Entries 0 and 1, byte-identical). Which one the bootloader runs is unknown, so both are patched. Source: `helix-floor/docs/FINDINGS.md`.
- The Floor port already patches the main program in a few places (`helix-floor/floor/arm_guards.py`, `ir_title.py`), so there is working precedent for main-program patches on this unit.
- One NAM block costs about 35% of a DSP on the Floor (the Floor port's measurement). Any feature that adds DSP code competes with that.
- The Floor is not a Stomp: twelve footswitches with scribble strips, a larger screen, two DSPs, eight snapshots. Stomp features such as long press or more snapshots need rethinking here, not porting one to one.

## Phase 0: a baseline we can trust

- [x] Build `main` from the stock file and confirm the output is byte-identical to the Floor port's tested build. **Verified offline**, 2026-11-12, `main` at `a84fcdb`, Windows 11, Python 3.10.11, capstone 5.0.7:
  - With the setup page's settings (`NAM_KERNEL=nam_floor5 NAM_MAX_BLOCKS=16 NAM_PR1=0`, simulator check on): MD5 `f4338695c5fa965f9100a0d82e632b7e`, the setup page's pinned `BUILT_MD5` and the file tested on a unit. KernelCheck PASS (steady mean 34874 instructions). About 4 minutes.
  - With no settings (PR #1's DMA patches on, the default since `8f54b04`): MD5 `d44f61687519f9557265658748ac828f`, KernelCheck PASS (34877). This is not the pinned build, and as far as we know this exact file has not been installed on a unit.
- [x] Run the test suite on `main` (fast tests and the simulator tests) and record the result. **Verified offline**, 2026-11-12, `main` at `a84fcdb`:
  - `pytest -m "not slow and not firmware"`: 96 passed, 1 skipped (`test_ramrun.py`: needs `arm-none-eabi-gcc`).
  - `pytest -m slow`: 2 passed (about 8 minutes).
  - The `firmware` tests need a Stomp file (`HX_STOMP_HXF`) and were not run.
  - The Floor's own checks in `helix-floor/floor/` are scripts, not pytest tests. Run each with `python <script>`: `test_arm_guards.py`, `test_ir_title.py` and `test_probe.py` PASS. `test_ir_title_knob.py` PASS. It needs `pip install unicorn` and the stock Entry 0 in its byte-swapped form as its argument (`tools/hxf.py unpack`, then `tools/l6ia.py <l6ia> <dir>`, then pass `00_type2.sw4.bin`).
- [ ] Decide how this repository follows its upstreams: merge from `floor-upstream/helix-floor` on a schedule, and how often to refresh `integration/hxtra-tooling` from `hxtra/main`.
- [ ] Write down the recovery procedure both maintainers have rehearsed, and on which units.

## Phase 1: the tooling, on the Floor

Goal: add a patch to the Floor's main program as a small module that checks the stock bytes it replaces, the way HXtra's feature engine does.

- [ ] On `integration/hxtra-tooling`, rebuild the Floor image and confirm it is still byte-identical to `main`'s. Until then that branch is for reading only.
- [ ] Make HXtra's main-program tools (`tools/m4asm.py`, the Entry 0 segment parser, the feature engine in `tools/features/`) device-aware: the Floor's segment layout and both copies of the main program.
- [ ] Start a Floor research index in `helix-floor/docs/`, one note per part of the system, addresses only.
- [ ] Find out whether a build can be run from RAM on the Floor without installing it, as HXtra and upstream do on the Stomp. If not, agree the test routine that replaces it.
- [ ] First end-to-end proof: one trivial, visible, reversible main-program change, built by the engine and run on a unit.

## Phase 2: first features

In the order we expect them to be useful. Each is its own branch and pull request.

- [ ] **Metronome.** HXtra's is a block (`tools/patch_click.py`, `tools/features/metronome.py`, `src/m4/metronome.s`) and is HX Stomp only. Decide whether the Floor's is a block too, and what DSP budget it may take next to two NAM blocks.
- [ ] **NAM block menu options**, for amp and for pedal captures. Scope to be agreed first: which parameters, which categories the blocks appear under, and how the settings are stored in a preset.
- [ ] **Settings pages** for features that need them (HXtra's virtual settings are the model).

## Phase 3: staying compatible with desktop editing

- [ ] NAM blocks that HX Edit keeps when it rewrites a preset. Upstream's approach is to give NAM a stock model's preset ID with matching knob types; the Floor port lists this as future work.
- [ ] Agree block identities and parameter layouts with [HX Edit NAM](https://github.com/andreidevs/hx-edit-nam) so presets, captures and TONE3000 imports move between its supported builds and this one. Any new NAM menu option from Phase 2 has to be designed with this in mind.
- [ ] Record which editor versions each firmware build was tested with.

## Open questions

- The name of the built firmware file and of the project on the unit (boot screen, if any).
- Whether to publish a setup page for this repository, or keep pointing at the Floor port's until the builds differ. The Pages workflow is manual-only for now.
- Helix LT: [andreidevs/helix-lt-nam](https://github.com/andreidevs/helix-lt-nam) builds on the Floor port. Whether work here should aim to be shared with it.
