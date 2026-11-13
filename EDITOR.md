# Floor firmware and editor pairing

The maintained desktop companion is **[Suddl3/hx-edit-nam, floor branch](https://github.com/Suddl3/hx-edit-nam/tree/floor)**. The direct installation guide is **[FLOOR-SETUP.md](https://github.com/Suddl3/hx-edit-nam/blob/floor/FLOOR-SETUP.md)**.

We keep the firmware here and desktop workflow there. That lets Suddl3 and savedadodo (Red Dragon) preserve the Floor's tested workflow while reviewing upstream features on their merits. We continue crediting the source projects and contributing useful fixes upstream. A fork is a maintained integration boundary, not a claim to have written the underlying editor or NAM engine.

## Current source-preview contract — November 12, 2026

| Component | Version/contract |
| --- | --- |
| Official desktop prerequisite | Windows Line 6 HX Edit 3.82 and drivers |
| Official firmware input | Helix Floor 3.80.0, built locally; never distribute a patched `.hxf` |
| NAM block | Normal `HD2_AmpNAMLite`, preset ID 380, original eight parameters |
| Floor editor code baseline | [`f72e7af`](https://github.com/Suddl3/hx-edit-nam/tree/f72e7afd9ef073ef1b890fd9ad819bc9d97d0a1e), published Floor-library source with Candidate 53 tab fix |
| Setup/documentation channel | Editor `floor` branch; current docs commit `c4757ca` |
| Converter | `andreidevs/helix-lt-nam` tools at `c948347`; not LT firmware for the Floor |

The setup guide gives the clone, dependency and launch commands. Launch with `--floor-library`; generic upstream mode is different. Use your own TONE3000 account/publishable key. There is no new one-click Floor installer in this cleanup.

**Do not pair this preview with `NAM_555` / `--e555`, shortened-layer or NAM Pedal experiments without a separately verified editor change.** Kernel layout, model naming and mirror options do not by themselves change the normal eight-parameter model contract, but a matching contract is not proof that every build combination is hardware-tested.

The development Candidate 53 lineage has owner-tested workflow results. The published reconciled source also has offline test/build evidence; it was not retested as every exact firmware/editor pairing. New navigation Candidates 54–57 are withdrawn and are not installation targets. See the editor guide's verification section for the distinction.

## Updating and cooperating

- Each maintainer uses this pairing document and the linked setup guide, rather than independently choosing the newest firmware and editor from unrelated repositories.
- Review upstream releases/commits before an integration batch and record adopt/adapt/defer decisions. No automatic merge or scheduled watcher is configured.
- Preserve the NAM sidebar, preview restoration, current-preset Clear protection and installed-slot verification when integrating a new editor feature.
- Changes to model IDs, parameter types/order, capture format or DSP variants need a paired editor change and explicit compatibility evidence.
- Record source commit, build flags and local firmware hash with hardware results. Keep author-reported and independently reproduced results distinct.
- Close all editors before using direct-USB research/mirror tools. Do not flash or change a working unit merely because documentation or a source PR was merged.

## Short collaborator note

> I'm keeping a Floor-focused HX Edit fork so the NAM workflow stays consistent with HX Unbound Floor, while still bringing in useful upstream features and contributing fixes back. The Floor repo now links to [our editor setup guide](https://github.com/Suddl3/hx-edit-nam/blob/floor/FLOOR-SETUP.md); use its pinned Floor source preview and launch instructions rather than the newer unfinished navigation candidates.
