#!/usr/bin/env python3
"""Draws unbound_boot.png, the 800x350 "HX FLOOR UNBOUND" boot picture, in the Floor's 15-bit colour.

The contour terrain follows the idea of wisemandenny's tools/splash_topo.py (GPL-3.0, branch integration/hxtra-tooling).
Needs numpy, Pillow and the Bahnschrift font that ships with Windows.   usage: make_unbound_boot.py [out.png]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, SS = 800, 350, 3
FONT = "C:/Windows/Fonts/bahnschrift.ttf"
TEAL, VIOLET = np.array([0, 220, 210]) / 255, np.array([150, 70, 255]) / 255


def font(px, weight):
    f = ImageFont.truetype(FONT, px)
    f.set_variation_by_axes([weight, 100])
    return f


def tracked(d, y, text, f, fill, track):
    """text centred on the picture with its baseline at y and extra space between the letters."""
    ws = [d.textlength(c, font=f) for c in text]
    x = W / 2 - (sum(ws) + track * (len(text) - 1)) / 2
    for c, w in zip(text, ws):
        d.text((x, y), c, font=f, fill=fill, anchor="ls")
        x += w + track


def terrain(seed, hills=26):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H * SS, 0:W * SS].astype(np.float64) / SS
    for _ in range(2):
        a, b = rng.uniform(0.005, 0.012, 2)
        p, q = rng.uniform(0, 6.28, 2)
        x, y = x + 22 * np.sin(y * a + p), y + 22 * np.sin(x * b + q)
    z = np.zeros_like(x)
    for _ in range(hills):
        cx, cy = rng.uniform(-80, W + 80), rng.uniform(-80, H + 80)
        s = rng.uniform(50, 160)
        z += rng.choice([-1, 1]) * rng.uniform(0.5, 1) * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * s * s))
    return (z - z.min()) / (z.max() - z.min())


def contours(seed, levels):
    f = terrain(seed) * levels
    gy, gx = np.gradient(f)
    slope = np.hypot(gx, gy) * SS + 1e-6
    k = np.round(f)
    dist = np.abs(f - k) / slope
    major = (k.astype(int) % 5) == 0
    ink = np.clip(np.where(major, 1.5, 0.6) + 0.5 - dist, 0, 1) * np.where(major, 1.0, 0.7)
    x = np.arange(W * SS)[None, :] / (W * SS)
    mix = np.clip(x * 1.2 - 0.1 + 0.35 * (f / levels - 0.5), 0, 1)[..., None]
    glow = 0.04 + 0.045 * (np.floor(f) % 2)
    a = (TEAL + (VIOLET - TEAL) * mix) * (glow + ink)[..., None]
    return a.reshape(H, SS, W, SS, 3).mean(axis=(1, 3))


def render():
    a = contours(7, 40)
    y, x = np.mgrid[0:H, 0:W]
    m = np.clip(1.35 - np.hypot((x - 400) / 410, (y - 178) / 160), 0, 1)
    a *= (1 - 0.9 * m * m * (3 - 2 * m))[..., None]                               # darker behind the title
    a *= (1 - 0.65 * np.clip((np.arange(H) - 305) / 45, 0, 1))[:, None, None]     # soft edge into the loading area
    img = Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tracked(d, 118, "HX FLOOR", font(34, 600), (0, 230, 215, 255), 14)
    tracked(d, 224, "UNBOUND", font(112, 700), (255, 255, 255, 255), 8)
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    halo.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(9)).point(lambda v: min(255, int(v * 2.2))))
    img.alpha_composite(halo)
    img.alpha_composite(layer)
    # the screen's 5 bits a channel, with ordered dithering so the gradients do not band
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 - 0.47
    d5 = np.tile(bayer, (H // 4 + 1, W // 4))[:H, :, None]
    q = np.clip(np.round(np.asarray(img.convert("RGB"), np.float64) / 255 * 31 + d5), 0, 31)
    return Image.fromarray((q * 255 / 31 + 0.5).astype(np.uint8))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "unbound_boot.png")
    render().save(out, optimize=True)
    print("wrote", out)
