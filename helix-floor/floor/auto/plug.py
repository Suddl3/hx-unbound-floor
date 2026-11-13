"""Floor power through a Kasa smart plug. usage: plug.py state|on|off|cycle [off_seconds]
Set FLOOR_PLUG to the plug's IP address (no default). Needs: pip install python-kasa.
Never call during a firmware install (the INSTALLING.lock file blocks off/cycle)."""
import asyncio, os, sys, kasa
HOST = os.environ.get("FLOOR_PLUG")
if not HOST:
    sys.exit("set FLOOR_PLUG to the smart plug's IP address")
LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "INSTALLING.lock")


async def main(cmd, secs):
    if cmd in ("off", "cycle") and os.path.exists(LOCK):
        sys.exit("refused: firmware install in progress (INSTALLING.lock)")
    d = await kasa.Device.connect(host=HOST)
    await d.update()
    if cmd == "off": await d.turn_off()
    elif cmd == "on": await d.turn_on()
    elif cmd == "cycle":
        await d.turn_off(); await asyncio.sleep(secs); await d.turn_on()
    await d.update(); print(d.alias, "on" if d.is_on else "off")
    await d.disconnect()

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "state", float(sys.argv[2]) if len(sys.argv) > 2 else 10))
