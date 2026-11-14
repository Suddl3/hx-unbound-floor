"""Focus View's pictures from RAM, loaded live (FOCUS15-style build: mirror with the poke, DSP meter with focus_img).

  floor_ram_art.py [SIZE]      HX Edit's model pictures (art_map.py, the user's own install; never stored on the unit)
                               at SIZE x SIZE (default 86: all 412 fit in 6 MB), uploaded to free SDRAM, and Focus View
                               switched to draw them (m4/ram_art.bin over focus_img). Gone at the next restart.

Turn Focus View off before running it (the jump over focus_img is written in place). live.json gives the addresses.
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FLOOR = os.environ.get("NAM_FLOOR_DIR", os.path.dirname(HERE))
sys.path.insert(0, FLOOR)
import floor_poke  # noqa: E402

PICS = 0x29900000               # free SDRAM (boot test pattern) up to CODE
CODE = 0x29f01000               # ram_img (the bulk write sits at 0x29f00800)
FOCUS_IMG = 1082                # focus_img's offset in the DSP meter module (m4/floor_dsp_meter.bin)
CENTRE_Y = 196                  # the middle of Focus View's area (y 52..340)


def blob(size):
    import art_map
    from PIL import Image
    from stage_art import rgb555
    m = art_map.build()
    n = len(m["symbols"])
    mp = [m["ids"].get(pid, 0xFFFF) for pid in range(n)]
    head = 8 + 2 * n
    head += -head % 4
    out = bytearray(struct.pack("<HHI", size, n, head) + struct.pack(f"<{n}H", *mp))
    out += bytes(head - len(out))
    for p in m["pictures"]:
        out += rgb555(Image.open(os.path.join(art_map.RES, p)), size)
    assert PICS + len(out) <= CODE - 0x1800, f"{len(out)} bytes: too big for the free RAM (a smaller size)"
    return bytes(out), len(m["pictures"])


def main():
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 86
    lv = floor_poke.live()
    data, npics = blob(size)
    code = bytearray(open(os.path.join(FLOOR, "m4", "ram_art.bin"), "rb").read())
    struct.pack_into("<I", code, len(code) - 8, lv["dm_imgs"])
    fi = lv["meter"] + FOCUS_IMG
    assert fi % 4 == 2
    jump = b"\x00\xbf" + b"\xdf\xf8\x00\xf0" + struct.pack("<I", CODE | 1)    # nop; ldr.w pc, [pc]; .word ram_img
    with floor_poke.Poke() as p:
        t = time.time()
        p.enable_bulk()
        p.write_bulk(PICS, data)
        p.write_bulk(CODE, bytes(code))
        p.write(lv["dm_imgs"] + 2, struct.pack("<4H", 400, CENTRE_Y - size // 2, size, size))
        p.write(fi, jump)
    print(f"{npics} pictures {size}x{size}, {len(data) / 1e6:.2f} MB in {time.time() - t:.0f} s; Focus View draws from RAM")


if __name__ == "__main__":
    main()
