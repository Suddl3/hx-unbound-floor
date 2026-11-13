# Contributing

## Remotes

This repository keeps the projects it builds on as named remotes:

```bash
git clone https://github.com/Suddl3/hx-unbound-floor.git
cd hx-unbound-floor
git remote add floor-upstream https://github.com/savedadodo/helix-floor-nam-lite.git
git remote add hxtra https://github.com/wisemandenny/hxtra.git
git remote add nam-upstream https://github.com/nocaseguy/hx-stomp-nam-lite.git
git fetch --all
```

| Remote | Branch | Role |
|---|---|---|
| `origin` | `main` | This project's integration line. See the recorded validation for each commit and firmware/editor pairing. |
| `origin` | `integration/hxtra-tooling` | `main` with HXtra merged in, to read and port from. Not verified on a unit. |
| `floor-upstream` | `helix-floor` | The Floor NAM port. Merged into `main`. |
| `hxtra` | `main` | HXtra (HX Stomp). Source of the tooling and feature ideas. |
| `nam-upstream` | `main` | hx-stomp-nam-lite, the foundation. |

## Branches and pull requests

The maintained editor companion is [Suddl3/hx-edit-nam, floor branch](https://github.com/Suddl3/hx-edit-nam/tree/floor). Keep firmware changes here and desktop workflow changes there; use [EDITOR.md](EDITOR.md) as the pairing contract. Review upstream changes selectively, preserving attribution and offering separable fixes back. Never assume a new upstream editor feature is compatible with every Floor build.

- Work on a branch, open a pull request into `main`, and let the other maintainer look at it before it is merged.
- One feature or fix per pull request. Say what was tested and how: on a unit (which one, which build, for how long), offline (simulator, emulator, tests), or not at all.
- Keep changes to files that come from an upstream small and separate from new files, so merging from upstream stays easy. New Floor work goes under `helix-floor/` or in new files.
- A fix that the plain Floor NAM port can use goes to [helix-floor-nam-lite](https://github.com/savedadodo/helix-floor-nam-lite) as well.

## What must never be committed

- Line 6 firmware files (`.hxf`), or anything built from one. A built file contains Line 6's firmware and must not be shared anywhere.
- Line 6 code or data copied out of the firmware. Notes and patches carry addresses, sizes and our own code only.
- NAM captures (`.nam`), converted captures (`.wav`), impulse responses, presets, backups, or names from anyone's personal library.
- Keys, tokens or account details.

`.gitignore` already excludes the usual file types. Check `git status` before you commit.

## Working on a real unit

- Rehearse the [recovery](helix-floor/README.md#install-and-recovery) on your own unit before you install any build from here.
- Never power the unit off during a firmware, preset or storage write.
- Back up presets before a test. Stock HX Edit backups have been seen to lose NAM block settings, so do not rely on one to restore a NAM preset.
- A unit that answers on USB is not proof that its screen, footswitches and audio work. Check them.
- Write down what was installed (the build's MD5), what was tested and what happened, in the pull request or in `helix-floor/docs/`.

## Tests

```bash
pip install -r requirements-dev.txt capstone
pytest -m "not slow and not firmware"
pytest -m slow
```

The `firmware` tests need a stock file and are skipped without one.

## Credit

Refer to other projects' authors by their GitHub handles, link their repositories, and keep their commits and notices intact when code is brought in. The licence is GPL-3.0-or-later throughout.
