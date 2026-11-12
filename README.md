# HX Unbound Floor

Custom firmware for the **Line 6 Helix Floor (3.80.0)**, built by patching your own copy of Line 6's stock firmware file on your own computer. Part of the [HX Unbound](https://github.com/Suddl3/hx-unbound) community.

> **Unofficial and experimental.** Not affiliated with, endorsed by or supported by Line 6 or Yamaha Guitar Group. Installing modified firmware is at your own risk and may void your warranty. No firmware is distributed here, and a built file must never be shared. Rehearse the [recovery](helix-floor/README.md#install-and-recovery) before you install anything.

> **This is the `integration/hxtra-tooling` branch:** `main` with [HXtra](https://github.com/wisemandenny/hxtra) merged in at its commit `28a93fe`, so its tooling, features and research notes can be read and ported next to the Floor code. HXtra's README is [README_HXTRA.md](README_HXTRA.md). HXtra changes tools the Floor build shares, and **the Floor build has not been run on this branch**: build firmware from `main`, not from here.

## Status (2026-11-12): day one

**Nothing new has been added to the firmware yet.** The `main` branch builds exactly what [savedadodo/helix-floor-nam-lite](https://github.com/savedadodo/helix-floor-nam-lite/tree/helix-floor) builds at commit `ad69ec4`: NAM A2 Lite as an amp block on the Helix Floor, up to two blocks per DSP. That port's own README, with its status, limits and findings, is kept as [README_FLOOR_NAM.md](README_FLOOR_NAM.md). Build, install and recovery are in [helix-floor/README.md](helix-floor/README.md).

This repository exists to take the Floor further than NAM, the way [HXtra](https://github.com/wisemandenny/hxtra) took the HX Stomp further: new functionality on the Floor's UI and control processor, not only on its DSPs.

## What we want to build

| Goal | State |
|---|---|
| Keep NAM A2 Lite on the Floor working and in step with the Floor port | Inherited, builds from `main` |
| A feature engine for the Floor's main program (small, self-checking patches, one module per feature), modelled on HXtra's | Not started. HXtra's tooling is on the [`integration/hxtra-tooling`](../../tree/integration/hxtra-tooling) branch to port from |
| A metronome | Not started. HXtra has one for the HX Stomp |
| More menu options on the NAM blocks, for amp and pedal captures | Not started, scope to be written down |
| NAM presets that survive desktop editing, in step with [HX Edit NAM](https://github.com/andreidevs/hx-edit-nam) and its TONE3000 flow | Not started |

The plan, in order, is in [ROADMAP.md](ROADMAP.md). How to work here is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Where this comes from

Each project keeps its own ownership and licence. This repository does not replace any of them.

| Project | Owner | What it is to us |
|---|---|---|
| [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite) | nocaseguy (Derek Bui) | The foundation: the NAM A2 Lite kernel in SHARC assembly, the SHARC assembler and simulator, the `.hxf` tools. Its README is kept as [README_UPSTREAM.md](README_UPSTREAM.md). |
| [helix-floor-nam-lite](https://github.com/savedadodo/helix-floor-nam-lite/tree/helix-floor) | savedadodo | The Helix Floor port (`helix-floor/`, `floor-web/`). `main` here starts from its `helix-floor` branch with the full commit history. |
| [HXtra](https://github.com/wisemandenny/hxtra) | wisemandenny | Custom firmware for the HX Stomp on the same foundation: the feature engine, the main-program patches and the research notes this project learns from. HX Stomp only: its patches do not apply to the Floor as they are. |
| [HX Edit NAM](https://github.com/andreidevs/hx-edit-nam) | andreidevs | The desktop editing side that firmware built here should stay compatible with. |

HX Unbound Floor is to helix-floor-nam-lite what HXtra is to hx-stomp-nam-lite: a separate project layered on top of it. Fixes to the Floor's NAM kernel and DSP work that the plain NAM port can use are offered back to that repository.

This is a standalone repository with imported history, not a GitHub fork, so GitHub does not list it in the hx-stomp-nam-lite fork network. The lineage is in the commit history and in this table.

## Build

Today the build is the Floor port's, unchanged. You need Python 3.10+, `capstone`, and Line 6's stock `Helix_Floor_v3.80.0_0x7d01f5efb.hxf` (MD5 `805caa03e8a30fd6ff7892f32ed5a9f4`):

```bash
PYTHONUTF8=1 python helix-floor/floor/build_floor2.py path/to/Helix_Floor_v3.80.0_0x7d01f5efb.hxf -o Helix_Floor_v3.80.0_NAM2.hxf
```

Details, install and recovery: [helix-floor/README.md](helix-floor/README.md).

## Maintainers

[Suddl3](https://github.com/Suddl3) and [savedadodo](https://github.com/savedadodo). Questions and discussion: the Discord linked from the [HX Unbound hub](https://github.com/Suddl3/hx-unbound).

## Licence

GNU General Public License v3 or later, as the projects it builds on. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
