"""SELENE logo - an original mark: a gradient crescent moon (the Moon), an orbiting
spark (the AI), and a heartbeat line (health). Rendered with Pillow, so it needs
no image files. `frames(size, state)` returns animation frames for each AI state:
idle, listening, thinking, speaking."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

C1, C2, C3 = (61, 220, 255), (123, 97, 255), (255, 95, 210)   # cyan -> violet -> pink


def _gradient(size, angle=0.0):
    y, x = np.mgrid[0:size, 0:size] / max(size - 1, 1)
    a = math.radians(angle)
    t = np.clip((x * math.cos(a) + y * math.sin(a) + 0.2) / 1.4, 0, 1)[..., None]
    c1, c2, c3 = (np.array(c, float) for c in (C1, C2, C3))
    rgb = np.where(t < 0.5, c1 + (c2 - c1) * (t / 0.5), c2 + (c3 - c2) * ((t - 0.5) / 0.5))
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def _crescent_mask(S, cx, cy, r):
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    off = r * 0.42
    d.ellipse([cx - r + off, cy - r - off * 0.55, cx + r + off, cy + r - off * 0.55], fill=0)
    return m


def render(size=256, t=0.0, state="idle"):
    """One frame. t in [0,1) is the animation phase."""
    k = 3                                    # supersampling for smooth edges
    S = size * k
    cx = cy = S / 2
    r = S * 0.30
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # soft glow
    pulse = 0.5 + 0.5 * math.sin(2 * math.pi * t)
    glow_strength = {"idle": 0.35 + 0.2 * pulse, "listening": 0.6, "thinking": 0.5, "speaking": 0.45 + 0.3 * pulse}[state]
    glow = Image.new("L", (S, S), 0)
    ImageDraw.Draw(glow).ellipse([cx - r * 1.15, cy - r * 1.15, cx + r * 1.15, cy + r * 1.15], fill=int(255 * glow_strength))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.07))
    img.paste(_gradient(S, 35 + 360 * t * (0.3 if state == "thinking" else 0.05)).convert("RGBA"), (0, 0), glow)

    # listening ripples
    if state == "listening":
        d = ImageDraw.Draw(img)
        for i in range(3):
            p = (t + i / 3) % 1
            rr = r * (1.05 + 0.55 * p)
            a = int(200 * (1 - p))
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(*C1, a), width=max(2, int(S * 0.008)))

    # crescent with gradient
    grad = _gradient(S, 35).convert("RGBA")
    img.paste(grad, (0, 0), _crescent_mask(S, cx, cy, r))

    # orbit ellipse (tilted) + spark
    orbit = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    od = ImageDraw.Draw(orbit)
    rx, ry = r * 1.42, r * 0.48
    od.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=(255, 255, 255, 110), width=max(2, int(S * 0.007)))
    orbit = orbit.rotate(-24, center=(cx, cy), resample=Image.BICUBIC)
    img.alpha_composite(orbit)
    speed = {"idle": 1, "listening": 1, "thinking": 3, "speaking": 2}[state]
    ang = 2 * math.pi * ((t * speed) % 1)
    px, py = rx * math.cos(ang), ry * math.sin(ang)
    rot = math.radians(-24)
    sx = cx + px * math.cos(rot) + py * math.sin(rot)
    sy = cy - px * math.sin(rot) + py * math.cos(rot)
    spark = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spark)
    sr = S * 0.035
    sd.ellipse([sx - sr * 2.2, sy - sr * 2.2, sx + sr * 2.2, sy + sr * 2.2], fill=(*C1, 90))
    spark = spark.filter(ImageFilter.GaussianBlur(sr))
    sd = ImageDraw.Draw(spark)
    sd.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 255, 255, 255))
    img.alpha_composite(spark)

    # heartbeat line through the crescent's open side
    amp = {"idle": 1.0, "listening": 0.6, "thinking": 0.8, "speaking": 0.6 + 0.8 * pulse}[state]
    w = max(3, int(S * 0.016))
    x0, x1, base = cx - r * 0.25, cx + r * 0.95, cy + r * 0.12
    pts = [(x0, base), (x0 + r * 0.30, base), (x0 + r * 0.42, base - r * 0.42 * amp),
           (x0 + r * 0.55, base + r * 0.30 * amp), (x0 + r * 0.66, base), (x1, base)]
    ImageDraw.Draw(img).line(pts, fill=(255, 255, 255, 235), width=w, joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def frames(size=200, state="idle", n=24):
    return [render(size, i / n, state) for i in range(n)]


def wordmark_colors():
    return ["#3DDCFF", "#7B61FF", "#FF5FD2"]
