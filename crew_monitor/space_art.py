"""Generates SELENE's original deep-space backdrop: fractal nebula clouds, a glowing
core, stars with diffraction spikes, a small planet and a glowing planet horizon.
Drawn procedurally (no copyrighted images). Put your own picture in assets/
(background.png/.jpg) to replace it - NASA/JWST images are generally public domain."""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _fractal(w, h, rng, octaves=6, base=3):
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = base * 2 ** o
        grid = rng.random((cells + 1, int(cells * w / h) + 2)).astype(np.float32)
        layer = np.asarray(Image.fromarray((grid * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
        out += layer * amp
        total += amp
        amp *= 0.55
    return out / total


def _star(draw, x, y, r, color, spikes=True):
    for k, a in ((3.2, 30), (2.0, 70), (1.0, 255)):
        rr = r * k
        draw.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(*color, a))
    if spikes:
        L = r * 9
        for dx, dy, w in ((L, 0, 1), (0, L, 1), (L * 0.45, L * 0.45, 0), (-L * 0.45, L * 0.45, 0)):
            if w or r > 2.2:
                draw.line([x - dx, y - dy, x + dx, y + dy], fill=(*color, 150 if w else 70), width=max(1, int(r / 2)))


def generate(w=1600, h=1000, seed=7):
    custom = next((p for p in ASSETS.glob("background.*")), None) if ASSETS.is_dir() else None
    if custom:
        try:
            return Image.open(custom).convert("RGB").resize((w, h), Image.LANCZOS)
        except Exception:
            pass
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    # deep space gradient
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0], img[..., 1], img[..., 2] = 4, 5, 16
    cx, cy = w * 0.62, h * 0.38
    dist = np.sqrt(((x - cx) / w) ** 2 + ((y - cy) / h) ** 2)

    # nebula layers: violet body, magenta/pink veil, orange dust, teal gas
    n1, n2, n3, n4 = (_fractal(w, h, rng) for _ in range(4))
    core = np.clip(1.0 - dist * 2.2, 0, 1) ** 1.6
    violet = np.clip((n1 - 0.38) * 2.4, 0, 1) * (0.35 + core)
    pink = np.clip((n2 - 0.45) * 2.6, 0, 1) * (0.2 + core * 1.2)
    dust = np.clip((n3 - 0.52) * 3.0, 0, 1) * np.clip(1.2 - dist * 1.6, 0, 1)
    teal = np.clip((n4 - 0.55) * 2.5, 0, 1) * np.clip(dist * 1.6 - 0.2, 0, 1)
    for layer, col in ((violet, (110, 60, 200)), (pink, (230, 80, 190)), (dust, (255, 140, 60)), (teal, (40, 150, 200))):
        img += layer[..., None] * np.array(col, np.float32) * 0.55
    img += (core ** 3)[..., None] * np.array([255, 200, 230], np.float32) * 0.9      # glowing heart
    # darker dust lanes
    lanes = np.clip((n3 - 0.6) * 4, 0, 1) * np.clip((n1 - 0.5) * 3, 0, 1)
    img *= (1 - 0.55 * lanes)[..., None]
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))

    # stars
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(int(w * h / 900)):
        sx, sy = rng.uniform(0, w), rng.uniform(0, h)
        b = int(rng.uniform(90, 255))
        d.point((sx, sy), fill=(b, b, min(255, b + 20), 255))
    palette = [(200, 220, 255), (255, 230, 240), (255, 200, 150), (170, 200, 255)]
    for _ in range(26):
        _star(d, rng.uniform(0, w), rng.uniform(0, h * 0.85), rng.uniform(1.2, 3.6), palette[rng.integers(0, 4)])
    glow = layer.filter(ImageFilter.GaussianBlur(2))
    base = base.convert("RGBA")
    base.alpha_composite(glow)
    base.alpha_composite(layer)

    # small planet with rim light (upper left)
    pl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pl)
    px, py, pr = w * 0.16, h * 0.24, h * 0.055
    pd.ellipse([px - pr * 1.25, py - pr * 1.25, px + pr * 1.25, py + pr * 1.25], fill=(255, 150, 200, 60))
    pl = pl.filter(ImageFilter.GaussianBlur(pr * 0.4))
    pd = ImageDraw.Draw(pl)
    pd.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(28, 22, 48, 255))
    pd.arc([px - pr, py - pr, px + pr, py + pr], 290, 70, fill=(255, 190, 220, 255), width=max(2, int(pr * 0.08)))
    base.alpha_composite(pl)

    # planet horizon at the bottom (like the view from orbit), with atmosphere glow
    hz = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hz)
    R = w * 1.6
    hcx, hcy = w * 0.5, h + R - h * 0.12
    hd.ellipse([hcx - R - 18, hcy - R - 18, hcx + R + 18, hcy + R + 18], fill=(90, 160, 255, 210))
    hd.ellipse([hcx - R - 6, hcy - R - 6, hcx + R + 6, hcy + R + 6], fill=(255, 170, 90, 230))
    hz = hz.filter(ImageFilter.GaussianBlur(14))
    hd = ImageDraw.Draw(hz)
    hd.ellipse([hcx - R, hcy - R, hcx + R, hcy + R], fill=(6, 8, 18, 255))
    base.alpha_composite(hz)
    return base.convert("RGB")
