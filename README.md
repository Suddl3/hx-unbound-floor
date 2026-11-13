# HX Unbound Floor

Custom firmware for the **Line 6 Helix Floor (3.80.0)**, built by patching your own copy of Line 6's stock firmware file on your own computer. Part of the [HX Unbound](https://github.com/Suddl3/hx-unbound) community.

> **Unofficial and experimental.** Not affiliated with, endorsed by or supported by Line 6 or Yamaha Guitar Group. Installing modified firmware is at your own risk and may void your warranty. No firmware is distributed here, and a built file must never be shared. Rehearse the [recovery](helix-floor/README.md#install-and-recovery) before you install anything.

## Firmware and editor

**This repository owns the Floor firmware. The maintained editor companion is [Suddl3/hx-edit-nam, `floor` branch](https://github.com/Suddl3/hx-edit-nam/tree/floor).** Start with [EDITOR.md](EDITOR.md) for the compatible source preview and installation instructions. Do not assume an upstream editor ZIP or a private development candidate is our current Floor editor.

The firmware builds on [savedadodo's Floor port](https://github.com/savedadodo/helix-floor-nam-lite/tree/helix-floor), with its history and attribution retained. The port's README is kept as [README_FLOOR_NAM.md](README_FLOOR_NAM.md). Current build, feature options, install and recovery are in [helix-floor/README.md](helix-floor/README.md).

Merged source includes the PAIR kernel option, custom model names, DSP timing/headroom tools and an **opt-in screen mirror**. Defaults remain conservative: DSP cost 3600; screen mirror disabled. Cost 3250 findings apply to the PAIR layout. Author-reported hardware tests and later offline hardening are distinguished in [REVIEW-2026-11-12.md](REVIEW-2026-11-12.md). Merging source does not authorize or perform a firmware flash.

We maintain the Floor experience across these two repositories, selectively bring in useful upstream features, and offer reusable fixes back. Firmware and editor versions remain separate and are paired by an explicit model/parameter contract; see [EDITOR.md](EDITOR.md).

This repository exists to take the Floor further than NAM, the way [HXtra](https://github.com/wisemandenny/hxtra) took the HX Stomp further: new functionality on the Floor's UI and control processor, not only on its DSPs.

## What we want to build

| Goal | State |
|---|---|
| Keep NAM A2 Lite on the Floor working and in step with the Floor port | Inherited, builds from `main` |
| A feature engine for the Floor's main program (small, self-checking patches, one module per feature), modelled on HXtra's | Not started. HXtra's tooling is on the [`integration/hxtra-tooling`](../../tree/integration/hxtra-tooling) branch to port from |
| A metronome | Not started. HXtra has one for the HX Stomp |
| More menu options on the NAM blocks, for amp and pedal captures | Not started, scope to be written down |
| A maintained Floor editor, NAM library and TONE3000 workflow | [Floor source preview and setup](https://github.com/Suddl3/hx-edit-nam/blob/floor/FLOOR-SETUP.md); newer navigation work remains under repair |

The plan, in order, is in [ROADMAP.md](ROADMAP.md). How to work here is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Where this comes from

Each project keeps its own ownership and licence. This repository does not replace any of them.

| Project | Owner | What it is to us |
|---|---|---|
| [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite) | nocaseguy (Derek Bui) | The foundation: the NAM A2 Lite kernel in SHARC assembly, the SHARC assembler and simulator, the `.hxf` tools. Its README is kept as [README_UPSTREAM.md](README_UPSTREAM.md). |
| [helix-floor-nam-lite](https://github.com/savedadodo/helix-floor-nam-lite/tree/helix-floor) | savedadodo | The Helix Floor port (`helix-floor/`, `floor-web/`). `main` here starts from its `helix-floor` branch with the full commit history. |
| [HXtra](https://github.com/wisemandenny/hxtra) | wisemandenny | Custom firmware for the HX Stomp on the same foundation: the feature engine, the main-program patches and the research notes this project learns from. HX Stomp only: its patches do not apply to the Floor as they are. |
| [HX Edit NAM](https://github.com/andreidevs/hx-edit-nam) | andreidevs | Editor upstream; features are reviewed and selectively brought into [our Floor editor fork](https://github.com/Suddl3/hx-edit-nam/tree/floor). Existing attribution and licence remain intact. |

HX Unbound Floor is to helix-floor-nam-lite what HXtra is to hx-stomp-nam-lite: a separate project layered on top of it. Fixes to the Floor's NAM kernel and DSP work that the plain NAM port can use are offered back to that repository.

This is a standalone repository with imported history, not a GitHub fork, so GitHub does not list it in the hx-stomp-nam-lite fork network. The lineage is in the commit history and in this table.

## Build

You need Python 3.10+, `capstone`, and your own Line 6 stock `Helix_Floor_v3.80.0_0x7d01f5efb.hxf` (MD5 `805caa03e8a30fd6ff7892f32ed5a9f4`):

```bash
PYTHONUTF8=1 python helix-floor/floor/build_floor2.py path/to/Helix_Floor_v3.80.0_0x7d01f5efb.hxf -o Helix_Floor_v3.80.0_NAM2.hxf
```

Details, install and recovery: [helix-floor/README.md](helix-floor/README.md).

## Maintainers

[Suddl3](https://github.com/Suddl3) and [savedadodo](https://github.com/savedadodo). Questions and discussion: the Discord linked from the [HX Unbound hub](https://github.com/Suddl3/hx-unbound).

## Licence

GNU General Public License v3 or later, as the projects it builds on. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
