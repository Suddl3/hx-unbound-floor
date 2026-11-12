# Hardware test scripts (Helix Floor)

Scripts that drive a real Floor over USB/MIDI to measure and soak a build. Use at your own risk, and keep the
Floor on a non-NAM preset before installing any build that might hang.

- `probe.py`: alive check (does the Floor still obey a preset change). `midi.py`: MIDI helpers.
- `meter48.py`, `idle48.py`: DSP meter capture (record at 48 kHz over ASIO; 44.1 kHz resamples the frames).
- `tonecheck.py`, `tonerec.py`, `clicktest.py`, `clickscan.py`: record and compare output.
- `namtest.py`, `namtest555.py`: put NAM into the edit buffer only (never saved). `namtest.py` reads `06C_editbuf.bin` and
  `06D_editbuf.bin`: your own preset dumps, not included.
- `soak.py`, `soak_eb.py`, `stab2.py`: unattended stability soaks. `soak*.py` power-cycle a frozen Floor with `plug.py`
  (Kasa smart plug; set `FLOOR_PLUG` to its IP address; python-kasa).
