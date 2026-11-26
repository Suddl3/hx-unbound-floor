# Boot screen

"HX FLOOR UNBOUND" on the Floor's boot screen. Off by default; build with it:

    NAM_SPLASH=helix-floor/floor/splash/unbound_boot.png

(`build_floor2.py` runs `stage_splash.py`.) Any 800x350 PNG works. `make_unbound_boot.py` redraws ours.

- The app draws `Helix_Splash` (image 372: 800x350, RGB555, in Entry 9). Its pixels are overwritten in place: same size, no
  new item, no code change. The stock pixels are hashed first, so the stage stops if anything else uses that space.
- `NAM_ART_STORE=splash` uses the LT and Rack splashes (images 370, 371), not this one.
- The bootloader's own picture, shown before the app starts, is unchanged. So are the boot text and loading bar.

Idea and contour style follow wisemandenny's Stomp boot splash (GPL-3.0, branch `integration/hxtra-tooling`).
