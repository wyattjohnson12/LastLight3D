"""
art_explore.py - painted-in-code pictures for the places you can discover (explore.py).

Same style and same assets/ override as art.py (drop e.g. assets/ex_planks_chest.png in to replace one).
Most of these pictures are draped over 3D shapes (shapes3d.py), so they are painted fully OPAQUE over the
whole square, with no painted shadow - except the torn tent canvas, whose holes are meant to show.
Every picture is square, so a shape's units (R = half the sprite's side) are the same in x and y.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
from art import _shade, _tex


def _noise_fill(img, rnd, cols, n, rmin, rmax, alpha=(60, 140), blur=2):
    """Soft blotches of colour over the whole picture (weathering, dirt, moss)."""
    w, h = img.size
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for _ in range(n):
        r = rnd.uniform(rmin, rmax)
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice(cols) + (rnd.randint(*alpha),))
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(blur)))


# =========================================================================== surfaces
def _planks_img(seed, n, col, bands=None, rows=5):
    """Weathered planks (running left-right) with grain lines; bands = colour of two iron straps."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), col + (255,))
    d = ImageDraw.Draw(img)
    ph = n / rows
    for i in range(rows):
        c = _shade(col, rnd.uniform(0.82, 1.12))
        d.rectangle([0, i * ph, n, (i + 1) * ph], fill=c + (255,))
        for _ in range(4):
            y = i * ph + rnd.uniform(2, ph - 2)
            d.line([(0, y), (n, y + rnd.uniform(-1.5, 1.5))], fill=_shade(c, 0.8) + (150,), width=1)
        d.line([(0, i * ph), (n, i * ph)], fill=_shade(col, 0.45) + (255,), width=max(1, n // 48))
        x = rnd.uniform(0.2, 0.8) * n                   # a butt joint somewhere along the row
        d.line([(x, i * ph), (x, (i + 1) * ph)], fill=_shade(col, 0.5) + (255,), width=max(1, n // 64))
    _noise_fill(img, rnd, [_shade(col, 0.6), (90, 96, 60)], n // 6, n * 0.03, n * 0.09, (30, 80))
    if bands:
        d = ImageDraw.Draw(img)
        for fx in (0.22, 0.78):
            x = fx * n
            d.rectangle([x - n * 0.05, 0, x + n * 0.05, n], fill=bands + (255,))
            for k in range(3):
                y = (k + 0.5) * n / 3
                d.ellipse([x - 1.5, y - 1.5, x + 1.5, y + 1.5], fill=_shade(bands, 1.6) + (255,))
    return img


def planks(name, n=64, col=(124, 86, 50), bands=None, rows=5, seed=0):
    return _tex(f"ex_planks_{name}", lambda: _planks_img(7100 + seed, n, col, bands, rows))


def _stone_img(seed, n, base=(132, 128, 120), moss=True):
    """Fitted grey stones with dark joints (tower tops, altar slabs, rubble)."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), _shade(base, 0.55) + (255,))
    d = ImageDraw.Draw(img)
    step = n / 6
    for gy in range(7):
        for gx in range(7):
            x = gx * step + (step / 2 if gy % 2 else 0) + rnd.uniform(-2, 2)
            y = gy * step + rnd.uniform(-2, 2)
            rx, ry = step * rnd.uniform(0.42, 0.5), step * rnd.uniform(0.4, 0.48)
            c = _shade(base, rnd.uniform(0.85, 1.15))
            d.rounded_rectangle([x - rx, y - ry, x + rx, y + ry], radius=step * 0.18, fill=c + (255,))
            d.line([(x - rx * 0.7, y - ry * 0.6), (x + rx * 0.4, y - ry * 0.6)], fill=_shade(c, 1.2) + (160,))
    if moss:
        _noise_fill(img, rnd, [(104, 120, 64), (90, 108, 56)], n // 5, n * 0.03, n * 0.08, (40, 120))
    return img


def stone(name="grey", n=64, base=(132, 128, 120), moss=True, seed=0):
    return _tex(f"ex_stone_{name}", lambda: _stone_img(7200 + seed, n, base, moss))


def _canvas_img(seed, n, col, torn=True):
    """Stained tent canvas with patches and seams; torn=True leaves ragged see-through holes."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), col + (255,))
    d = ImageDraw.Draw(img)
    for i in range(1, 4):
        x = i * n / 4
        d.line([(x, 0), (x, n)], fill=_shade(col, 0.75) + (200,), width=1)
    _noise_fill(img, rnd, [_shade(col, 0.7), _shade(col, 0.85), (110, 96, 70)], n // 3, n * 0.04, n * 0.12,
                (40, 110), 3)
    d = ImageDraw.Draw(img)
    for _ in range(3):                                   # sewn-on patches
        x, y = rnd.uniform(0.15, 0.85) * n, rnd.uniform(0.15, 0.85) * n
        s = rnd.uniform(0.07, 0.12) * n
        pc = _shade(col, rnd.uniform(0.7, 0.9))
        d.rectangle([x - s, y - s * 0.8, x + s, y + s * 0.8], fill=pc + (255,), outline=_shade(pc, 0.6) + (255,))
    if torn:
        mask = Image.new("L", (n, n), 255)
        md = ImageDraw.Draw(mask)
        for _ in range(4):
            x, y = rnd.uniform(0.1, 0.9) * n, rnd.uniform(0.1, 0.9) * n
            pts = []
            for k in range(9):
                a = k / 9 * math.tau
                r = rnd.uniform(0.02, 0.07) * n
                pts.append((x + math.cos(a) * r * 1.6, y + math.sin(a) * r))
            md.polygon(pts, fill=0)
        img.putalpha(mask)
    return img


def canvas(name="tent", n=96, col=(176, 160, 122), torn=True, seed=0):
    return _tex(f"ex_canvas_{name}", lambda: _canvas_img(7300 + seed, n, col, torn))


def _ashpit_img(seed, n):
    """A cold firepit from above: grey ash and charcoal in a ring of stones."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), (120, 116, 108, 255))
    d = ImageDraw.Draw(img)
    c = n / 2
    for i in range(14):                                   # the stones round the rim
        a = i / 14 * math.tau
        x, y = c + math.cos(a) * n * 0.4, c + math.sin(a) * n * 0.4
        r = n * rnd.uniform(0.07, 0.1)
        col = _shade((128, 124, 116), rnd.uniform(0.85, 1.15))
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,), outline=_shade(col, 0.5) + (255,))
    d.ellipse([c - n * 0.3, c - n * 0.3, c + n * 0.3, c + n * 0.3], fill=(70, 66, 62, 255))
    _noise_fill(img, rnd, [(40, 36, 34), (150, 146, 140), (90, 86, 82)], 40, n * 0.02, n * 0.06, (90, 200), 1)
    return img


def ash_pit():
    return _tex("ex_ashpit", lambda: _ashpit_img(7400, 52))


def _plain_img(n, col, seed, var=0.08):
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), col + (255,))
    _noise_fill(img, rnd, [_shade(col, 1 - var * 2), _shade(col, 1 + var * 2)], n // 2, n * 0.04, n * 0.12,
                (60, 140), 2)
    return img


def plain(name, col, n=32, seed=0):
    """A lightly mottled plain colour (for shapes that pick one colour from their picture)."""
    return _tex(f"ex_plain_{name}", lambda: _plain_img(n, col, 7500 + seed))


def _dirt_img(seed, n, col):
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), col + (255,))
    _noise_fill(img, rnd, [_shade(col, 0.75), _shade(col, 1.2), (96, 110, 60)], n, n * 0.03, n * 0.1, (60, 150), 2)
    d = ImageDraw.Draw(img)
    for _ in range(n // 2):
        x, y = rnd.uniform(0, n), rnd.uniform(0, n)
        r = rnd.uniform(0.6, 1.6)
        d.ellipse([x - r, y - r, x + r, y + r], fill=_shade(col, rnd.choice((0.6, 1.4))) + (220,))
    return img


def dirt(name="mound", col=(112, 88, 62), n=64, seed=0):
    return _tex(f"ex_dirt_{name}", lambda: _dirt_img(7600 + seed, n, col))


def _ore_heap_img(seed, n):
    rnd = random.Random(seed)
    img = _dirt_img(seed, n, (88, 80, 74))
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x, y = rnd.uniform(0, n), rnd.uniform(0, n)
        r = rnd.uniform(1.2, 3.2)
        c = rnd.choice([(170, 104, 70), (60, 56, 56), (200, 130, 90), (40, 38, 40)])
        d.ellipse([x - r, y - r, x + r, y + r], fill=c + (255,))
    return img


def ore_heap():
    return _tex("ex_ore_heap", lambda: _ore_heap_img(7700, 44))


def _obsidian_img(seed, n):
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), (34, 26, 40, 255))
    d = ImageDraw.Draw(img)
    for _ in range(n // 2):                               # glassy facets
        x, y = rnd.uniform(0, n), rnd.uniform(0, n)
        pts = [(x + rnd.uniform(-6, 6), y + rnd.uniform(-6, 6)) for _ in range(3)]
        d.polygon(pts, fill=rnd.choice([(54, 40, 66), (24, 18, 30), (80, 62, 96)]) + (200,))
    for _ in range(6):                                    # glowing cracks
        x, y = rnd.uniform(0, n), rnd.uniform(0, n)
        a = rnd.uniform(0, math.tau)
        d.line([(x, y), (x + math.cos(a) * 8, y + math.sin(a) * 8)], fill=(255, 120, 40, 230), width=1)
    return img


def obsidian():
    return _tex("ex_obsidian", lambda: _obsidian_img(7800, 44))


# =========================================================================== flat ground patches
def _patch(name, seed, size, cols, slab=False):
    import art_highlands
    return _tex(f"ex_patch_{name}", lambda: art_highlands._patch_img(seed, size, cols, slab))


def patch(kind):
    """A soft-edged ground patch under a place, so it reads as somewhere people once lived."""
    looks = {
        "dirt": (7900, 256, [(116, 96, 66), (100, 84, 58), (132, 110, 76), (92, 100, 60)], False),
        "flagstone": (7901, 256, [(130, 126, 116), (112, 108, 100), (146, 140, 128), (100, 112, 72)], True),
        "gravel": (7902, 256, [(96, 90, 84), (80, 76, 72), (118, 110, 100), (70, 64, 60)], False),
        "scorch": (7903, 256, [(46, 36, 34), (70, 50, 40), (36, 30, 30), (96, 60, 40)], True),
        "mud": (7904, 256, [(78, 70, 50), (64, 60, 44), (92, 84, 58), (60, 72, 48)], False),
        "frost": (7905, 256, [(214, 226, 236), (196, 212, 226), (230, 238, 244), (180, 200, 220)], False),
    }
    seed, size, cols, slab = looks[kind]
    return _patch(kind, seed, size, cols, slab)


def glow(r, col):
    return art.glow(r, col)
