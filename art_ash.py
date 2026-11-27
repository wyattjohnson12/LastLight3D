"""
art_ash.py - painted-in-code art for the Ashlands (the volcanic biome, ashlands.py).

Same style and same assets/ override as art.py (drop e.g. assets/ash_obsidian_0.png in to replace one).
Importing this module plugs the new pictures into the existing art tables:
  * art_extra.animal("fire_beetle") is the Fire Beetle (art_extra.ANIMAL_ART)
  * art.icon(...) knows the new item icons, art_gear.gear(...) the worn Ember Crown / Obsidian Plate
Lava cracks also come with their shape (CRACKS: the burning line, in world offsets from the decal's centre),
so the hazard in ashlands.py matches the painted crack exactly.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
import art_extra
import art_gear
from art import S, _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shade, _shadow, _tex

ASH = (62, 58, 56)
BASALT = (38, 36, 36)
CINDER = (92, 84, 78)
LAVA = (255, 120, 30)
LAVA_HOT = (255, 214, 120)


# =========================================================================== ground
def _ground_img(seed):
    """A seamless 256px tile of ash and basalt (drawn wrapped so neighbouring tiles join up)."""
    rnd = random.Random(seed)
    n = 256
    img = Image.new("RGBA", (n, n), ASH + (255,))
    blobs = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    palette = [(48, 45, 44), (74, 70, 66), (88, 82, 76), (40, 38, 38), (70, 62, 58), (100, 94, 88)]
    for _ in range(150):
        r = rnd.randint(8, 34)
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        col = rnd.choice(palette) + (rnd.randint(70, 160),)
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                d.ellipse([x + ox - r, y + oy - r, x + ox + r, y + oy + r], fill=col)
    img.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(img)
    for _ in range(9):          # dark basalt plates with hairline cracks
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        pts = []
        for k in range(6):
            a = k / 6 * math.tau + rnd.uniform(-0.3, 0.3)
            rr = rnd.uniform(9, 20)
            pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                q = [(px + ox, py + oy) for px, py in pts]
                d.polygon(q, fill=BASALT + (150,))
                d.line(q + [q[0]], fill=(28, 26, 26, 200), width=1)
    for _ in range(520):        # ash grit and cinders
        x, y = rnd.randint(0, n - 1), rnd.randint(0, n - 1)
        col = rnd.choice([(120, 114, 108), (36, 34, 34), (140, 132, 124), (82, 76, 70)]) + (rnd.randint(90, 190),)
        d.point((x, y), fill=col)
        if rnd.random() < 0.3:
            d.point((x + 1, y), fill=col)
    for _ in range(rnd.randint(1, 4)):   # a few faint embers still glowing in the ash
        x, y = rnd.randint(4, n - 4), rnd.randint(4, n - 4)
        d.ellipse([x - 1.5, y - 1.5, x + 1.5, y + 1.5], fill=(200, 90, 40, 180))
    return img


def ground(i):
    return _tex(f"ash_ground_{i}", lambda: _ground_img(7100 + i))


def _cinders_img(seed):
    rnd = random.Random(seed)
    img = _canvas(30, 24)
    for _ in range(6):
        x, y, r = rnd.uniform(6, 24), rnd.uniform(6, 18), rnd.uniform(1.6, 3.4)
        _ball(img, (x - r, y - r * 0.8, x + r, y + r * 0.8), rnd.choice([(54, 50, 48), (76, 68, 62), (40, 36, 36)]) + (255,),
              outline=False)
    if rnd.random() < 0.5:
        _circle(img, rnd.uniform(8, 22), rnd.uniform(8, 16), 1.2, (240, 120, 50, 230))
    return _finish(img, 30, 24)


def _drift_img(seed):
    rnd = random.Random(seed)
    img = _canvas(44, 28)
    for _ in range(5):
        x, y = rnd.uniform(12, 32), rnd.uniform(9, 19)
        rx, ry = rnd.uniform(6, 12), rnd.uniform(3, 6)
        _ball(img, (x - rx, y - ry, x + rx, y + ry), (128, 122, 116, 150), outline=False, soft=2.2)
    return _finish(img, 44, 28)


def _bones_img(seed):
    rnd = random.Random(seed)
    img = _canvas(36, 28)
    for _ in range(3):
        x, y = rnd.uniform(8, 28), rnd.uniform(8, 20)
        a = rnd.uniform(0, math.pi)
        dx, dy = math.cos(a) * 7, math.sin(a) * 7
        _line(img, [(x - dx, y - dy), (x + dx, y + dy)], (196, 186, 168, 255), 2)
        for sx, sy in ((x - dx, y - dy), (x + dx, y + dy)):
            _circle(img, sx, sy, 1.8, (210, 200, 182, 255))
    return _finish(img, 36, 28)


def decor(i):
    """Flat bits on the ash: cinders (0, 1), pale ash drifts (2) and old bones (3)."""
    k = i % 4
    if k < 2:
        return _tex(f"ash_cinders_{i}", lambda: _cinders_img(7200 + i))
    if k == 2:
        return _tex(f"ash_drift_{i}", lambda: _drift_img(7200 + i))
    return _tex(f"ash_bones_{i}", lambda: _bones_img(7200 + i))


# =========================================================================== lava cracks
CRACK_SIZE = (180, 180)
CRACKS = {}            # variant -> [((x0, y0), (x1, y1), half width), ...] in WORLD offsets (y up) from the centre


def _crack_paths(seed):
    """Main crack + a couple of branches, in picture coordinates (y down)."""
    rnd = random.Random(seed)
    w, h = CRACK_SIZE
    paths = []
    a = rnd.uniform(0, math.pi)
    ln = rnd.uniform(62, 78)
    pts = []
    for k in range(7):
        t = -1 + 2 * k / 6
        x = w / 2 + math.cos(a) * ln * t + rnd.uniform(-7, 7)
        y = h / 2 + math.sin(a) * ln * t + rnd.uniform(-7, 7)
        pts.append((x, y))
    paths.append((pts, 6.0))
    for _ in range(rnd.randint(1, 3)):
        sx, sy = pts[rnd.randint(1, 5)]
        b = a + rnd.choice((-1, 1)) * rnd.uniform(0.7, 1.3)
        bl = rnd.uniform(22, 40)
        br = [(sx, sy)]
        for k in range(1, 4):
            br.append((sx + math.cos(b) * bl * k / 3 + rnd.uniform(-4, 4), sy + math.sin(b) * bl * k / 3 + rnd.uniform(-4, 4)))
        paths.append((br, 3.6))
    return paths


def _crack_img(seed):
    w, h = CRACK_SIZE
    paths = _crack_paths(seed)
    img = _canvas(w, h)
    glow = _canvas(w, h)
    for pts, wd in paths:
        _line(glow, pts, (255, 110, 30, 150), wd * 3.6)
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6 * S)))
    for pts, wd in paths:      # scorched rim, then the molten core and its white-hot middle
        _line(img, pts, (34, 26, 24, 255), wd * 2.0)
    for pts, wd in paths:
        _line(img, pts, (232, 84, 24, 255), wd * 1.2)
    for pts, wd in paths:
        _line(img, pts, LAVA_HOT + (255,), wd * 0.5)
    return _finish(img, w, h)


def crack(i):
    """A glowing lava crack decal (lies flat on the ground). Also fills CRACKS[i] with its burning lines."""
    seed = 7300 + i
    if i not in CRACKS:
        w, h = CRACK_SIZE
        segs = []
        for pts, wd in _crack_paths(seed):
            wp = [(x - w / 2, h / 2 - y) for x, y in pts]
            for p0, p1 in zip(wp, wp[1:]):
                segs.append((p0, p1, wd * 0.9))
        CRACKS[i] = segs
    return _tex(f"ash_crack_{i}", lambda: _crack_img(seed))


POOL_SIZE = (300, 220)


def _pool_img():
    rnd = random.Random(7400)
    w, h = POOL_SIZE
    img = _canvas(w, h)
    glow = _canvas(w, h)
    _circle(glow, w / 2, h / 2, 100, (255, 100, 20, 170))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14 * S)))
    _ball(img, (18, 16, w - 18, h - 16), (40, 30, 28, 255), outline=False, soft=2.0)      # cooled black crust rim
    _ball(img, (34, 30, w - 34, h - 30), (236, 92, 22, 255), light=(0.1, 0.1), outline=False, soft=2.5)
    for _ in range(14):       # floating crust plates
        x, y = rnd.uniform(70, w - 70), rnd.uniform(60, h - 60)
        r = rnd.uniform(6, 16)
        pts = [(x + math.cos(k / 5 * math.tau) * r * rnd.uniform(0.7, 1.1),
                y + math.sin(k / 5 * math.tau) * r * rnd.uniform(0.6, 1.0)) for k in range(5)]
        _poly(img, pts, (60, 40, 34, 230), (150, 60, 24, 255), 1.2)
    for _ in range(18):       # white-hot swirls
        x, y = rnd.uniform(60, w - 60), rnd.uniform(50, h - 50)
        _line(img, [(x, y), (x + rnd.uniform(-14, 14), y + rnd.uniform(-6, 6))], LAVA_HOT + (220,), 2.2)
    return _finish(img, w, h)


def lava_pool():
    return _tex("ash_lava_pool", _pool_img)


# =========================================================================== nodes
def _obsidian_img(seed):
    """Glassy black spires seen from above: sharp facets with a purple sheen."""
    rnd = random.Random(seed)
    w = h = 64
    img = _canvas(w, h)
    _shadow(img, (8, 14, 60, 60), alpha=110, blur=4)
    c = 32
    for k in range(5):        # five shards fanning out from the middle
        a = k / 5 * math.tau + rnd.uniform(-0.3, 0.3)
        ln = rnd.uniform(18, 27)
        wd = rnd.uniform(0.32, 0.45)
        tip = (c + math.cos(a) * ln, c + math.sin(a) * ln)
        l = (c + math.cos(a - wd) * ln * 0.45, c + math.sin(a - wd) * ln * 0.45)
        r = (c + math.cos(a + wd) * ln * 0.45, c + math.sin(a + wd) * ln * 0.45)
        _poly(img, [(c, c), l, tip], (34, 28, 44, 255), (14, 10, 20, 255), 0.8)
        _poly(img, [(c, c), tip, r], (66, 54, 92, 255), (14, 10, 20, 255), 0.8)
        _line(img, [(c + (tip[0] - c) * 0.2, c + (tip[1] - c) * 0.2), (c + (tip[0] - c) * 0.85, c + (tip[1] - c) * 0.85)],
              (170, 150, 220, 200), 1.0)
    _poly(img, [(c - 8, c), (c, c - 9), (c + 8, c), (c, c + 9)], (52, 42, 72, 255), (14, 10, 20, 255), 1.0)
    _poly(img, [(c - 8, c), (c, c - 9), (c, c)], (120, 104, 170, 255))
    _circle(img, c - 3, c - 4, 1.6, (235, 225, 255, 255))           # gleam
    return _finish(img, w, h)


OBSIDIAN_HIT = [(-16, -16), (16, -16), (16, 16), (-16, 16)]


def obsidian(i):
    return _tex(f"ash_obsidian_{i}", lambda: _obsidian_img(7500 + i), OBSIDIAN_HIT)


def _vent_img(seed):
    """A squat volcanic vent from above: sulfur-crusted cone and a glowing throat."""
    rnd = random.Random(seed)
    w = h = 72
    img = _canvas(w, h)
    _shadow(img, (6, 12, 68, 68), alpha=100, blur=4)
    c = 36
    _ball(img, (6, 6, 66, 66), (78, 70, 64, 255))
    for _ in range(16):       # sulfur crust and streaks running down the cone
        a = rnd.uniform(0, math.tau)
        r0, r1 = rnd.uniform(9, 14), rnd.uniform(20, 29)
        col = rnd.choice([(214, 196, 70), (190, 170, 60), (120, 110, 96), (60, 54, 50)]) + (230,)
        _line(img, [(c + math.cos(a) * r0, c + math.sin(a) * r0), (c + math.cos(a) * r1, c + math.sin(a) * r1)], col, 1.8)
    for _ in range(7):
        a, r = rnd.uniform(0, math.tau), rnd.uniform(11, 16)
        _circle(img, c + math.cos(a) * r, c + math.sin(a) * r, rnd.uniform(1.6, 3), (230, 212, 80, 255))
    g = _canvas(w, h)
    _circle(g, c, c, 15, (255, 120, 30, 200))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
    _circle(img, c, c, 10, (60, 30, 24, 255))                       # the throat
    _circle(img, c, c, 7, (240, 96, 24, 255))
    _circle(img, c, c, 3.4, LAVA_HOT + (255,))
    return _finish(img, w, h)


VENT_HIT = [(-20, -20), (20, -20), (20, 20), (-20, 20)]


def vent(i):
    return _tex(f"ash_vent_{i}", lambda: _vent_img(7600 + i), VENT_HIT)


def _charred_img(seed):
    """A burnt, leafless tree from above: black forking branches with a few embers in the bark."""
    rnd = random.Random(seed)
    w = h = 120
    img = _canvas(w, h)
    _shadow(img, (30, 38, 106, 108), alpha=80, blur=6)
    bark = (44, 38, 36)
    c = w / 2

    def branch(x, y, a, ln, wd, depth):
        x2, y2 = x + math.cos(a) * ln, y + math.sin(a) * ln
        _line(img, [(x, y), ((x + x2) / 2 + rnd.uniform(-3, 3), (y + y2) / 2 + rnd.uniform(-3, 3)), (x2, y2)],
              _shade(bark, 0.9 + depth * 0.12) + (255,), wd)
        if depth < 2:
            for k in (-1, 1):
                branch(x2, y2, a + k * rnd.uniform(0.3, 0.7), ln * rnd.uniform(0.55, 0.7), max(1.2, wd * 0.6), depth + 1)
        elif rnd.random() < 0.35:
            _circle(img, x2, y2, 1.3, (255, 120, 40, 230))

    for k in range(5):
        branch(c, c, k / 5 * math.tau + rnd.uniform(-0.3, 0.3), rnd.uniform(18, 26), 4.4, 0)
    _ball(img, (c - 11, c - 11, c + 11, c + 11), bark + (255,))
    for _ in range(4):       # glowing cracks in the burnt trunk
        a = rnd.uniform(0, math.tau)
        _line(img, [(c + math.cos(a) * 3, c + math.sin(a) * 3), (c + math.cos(a) * 9, c + math.sin(a) * 9)],
              (255, 110, 40, 230), 1.2)
    return _finish(img, w, h)


CHARRED_HIT = [(-12, -12), (12, -12), (12, 12), (-12, 12)]


def charred_tree(i):
    return _tex(f"ash_charred_tree_{i}", lambda: _charred_img(7700 + i), CHARRED_HIT)


def _seam_img(seed, speck, glint):
    rnd = random.Random(seed)
    w, h = 70, 62
    img = _canvas(w, h)
    _shadow(img, (8, 16, 68, 62), alpha=100, blur=4)
    pts = []
    for k in range(9):
        a = k / 9 * math.tau
        r = rnd.uniform(22, 28)
        pts.append((35 + math.cos(a) * r, 30 + math.sin(a) * r * 0.82))
    _poly(img, pts, (52, 48, 48, 255), (20, 18, 18, 255), 1.6)
    top = [p for p in pts if p[1] < 30 or p[0] < 30]
    _poly(img, [(35, 26)] + top[:5], (84, 78, 76, 150))
    for _ in range(10):
        x, y = rnd.uniform(18, 52), rnd.uniform(14, 44)
        r = rnd.uniform(2.2, 4.4)
        _ball(img, (x - r, y - r, x + r, y + r), speck + (255,), outline=False)
        if glint:
            _circle(img, x - r * 0.3, y - r * 0.3, 0.9, glint + (230,))
    return _finish(img, w, h)


def ash_ore(kind, i=0):
    """Basalt boulders with coal / iron seams."""
    speck, glint = ((22, 20, 22), (120, 120, 130)) if kind == "coal" else ((200, 118, 64), (255, 200, 150))
    return _tex(f"ash_{kind}_{i}", lambda: _seam_img(7800 + i * 3 + len(kind), speck, glint), art.ROCK_HIT)


def _basalt_img(seed):
    rnd = random.Random(seed)
    w, h = 70, 62
    img = _canvas(w, h)
    _shadow(img, (8, 16, 68, 62), alpha=100, blur=4)
    pts = []
    for k in range(7):        # basalt breaks into flat-topped columns: a few angular facets
        a = k / 7 * math.tau + rnd.uniform(-0.15, 0.15)
        r = rnd.uniform(22, 28)
        pts.append((35 + math.cos(a) * r, 30 + math.sin(a) * r * 0.82))
    base = rnd.choice([(70, 66, 64), (60, 58, 58), (78, 72, 68)])
    _poly(img, pts, base + (255,), _shade(base, 0.4) + (255,), 1.6)
    for k in range(3):
        q = pts[k * 2:(k * 2) + 3]
        _poly(img, [(35, 30)] + q, _shade(base, 1.1 + 0.12 * k) + (160,))
    for _ in range(5):
        x, y = rnd.uniform(22, 48), rnd.uniform(18, 40)
        _line(img, [(x, y), (x + rnd.uniform(-6, 6), y + rnd.uniform(3, 7))], _shade(base, 0.5) + (200,), 1)
    for _ in range(6):       # ash dusting on top
        _circle(img, rnd.uniform(20, 46), rnd.uniform(10, 24), rnd.uniform(1.5, 3), (150, 144, 138, 170))
    return _finish(img, w, h)


def basalt(i):
    """The shared rocks restyled in the Ashlands."""
    return _tex(f"ash_basalt_{i}", lambda: _basalt_img(7900 + i), art.ROCK_HIT)


# =========================================================================== the Fire Beetle (faces right)
def _beetle_img():
    rnd = random.Random(8000)
    w = 56
    img = _canvas(w, w)
    c = w / 2
    _shadow(img, (8, 12, 52, 50), alpha=90, blur=3)
    for k, dx in enumerate((-9, 0, 9)):       # six legs
        for side in (-1, 1):
            _line(img, [(c + dx, c + side * 7), (c + dx + 3, c + side * 15), (c + dx - 2 + k * 2, c + side * 20)],
                  (34, 22, 20, 255), 2.2)
    for side in (-1, 1):                      # mandibles
        _line(img, [(c + 15, c + side * 4), (c + 22, c + side * 6), (c + 25, c + side * 2)], (60, 30, 22, 255), 2.4)
    _ball(img, (c - 17, c - 13, c + 11, c + 13), (70, 26, 22, 255))          # abdomen / wing cases
    _line(img, [(c - 16, c), (c + 9, c)], (20, 10, 10, 255), 1.6)           # the split between the shells
    for _ in range(7):                        # glowing seams in the shell
        x, y = rnd.uniform(c - 13, c + 6), rnd.choice((-1, 1)) * rnd.uniform(3, 9) + c
        _line(img, [(x, y), (x + rnd.uniform(3, 6), y + rnd.uniform(-2, 2))], LAVA + (240,), 1.4)
    for side in (-1, 1):
        _circle(img, c - 5, c + side * 6, 2.0, LAVA_HOT + (255,))
    _ball(img, (c + 7, c - 8, c + 19, c + 8), (52, 22, 20, 255))             # head
    for side in (-1, 1):
        _circle(img, c + 16, c + side * 4, 1.5, (255, 220, 100, 255))
    return _finish(img, w, w)


art_extra.ANIMAL_ART["fire_beetle"] = (_beetle_img, 13)


# =========================================================================== item icons
def _obsidian_icon(img):
    _poly(img, [(10, 40), (16, 14), (24, 4), (32, 16), (40, 40)], (40, 32, 52, 255), (16, 12, 22, 255), 1.4)
    _poly(img, [(16, 14), (24, 4), (24, 40), (10, 40)], (74, 60, 104, 255))
    _line(img, [(20, 12), (17, 34)], (190, 170, 240, 220), 1.4)
    _circle(img, 21, 11, 1.8, (240, 235, 255, 255))


def _sulfur_icon(img):
    rnd = random.Random(8100)
    for _ in range(5):
        x, y, r = rnd.uniform(14, 34), rnd.uniform(16, 34), rnd.uniform(6, 9)
        _ball(img, (x - r, y - r, x + r, y + r), (226, 206, 70, 255))
    for _ in range(4):
        _circle(img, rnd.uniform(14, 34), rnd.uniform(14, 32), 1.4, (255, 250, 190, 255))


def _ember_icon(img):
    g = _canvas(48, 48)
    _circle(g, 24, 25, 15, (255, 120, 30, 170))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(4 * S)))
    _ball(img, (11, 13, 37, 37), (60, 30, 26, 255))
    for a in (0.4, 1.7, 3.0, 4.4, 5.5):
        _line(img, [(24, 25), (24 + math.cos(a) * 10, 25 + math.sin(a) * 10)], LAVA + (255,), 2)
    _circle(img, 24, 25, 4, LAVA_HOT + (255,))


def _shell_icon(img):
    _ball(img, (8, 8, 40, 40), (80, 28, 22, 255))
    _line(img, [(24, 9), (24, 39)], (24, 12, 10, 255), 2)
    for x, y in ((16, 18), (31, 20), (18, 31), (30, 32)):
        _line(img, [(x - 3, y), (x + 3, y + 1)], LAVA + (230,), 1.6)
    _circle(img, 16, 14, 2.4, (200, 120, 100, 200))


def _crown_icon(img):
    g = _canvas(48, 48)
    _circle(g, 24, 22, 17, (255, 110, 30, 150))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(4 * S)))
    _ball(img, (8, 16, 40, 40), (44, 36, 52, 255))
    for k in range(5):                         # obsidian spikes
        x = 10 + k * 7
        top = 4 if k == 2 else 9
        _poly(img, [(x - 3, 22), (x, top), (x + 3, 22)], (60, 48, 84, 255), (16, 12, 22, 255), 1)
    _rrect(img, (8, 24, 40, 30), 2, (120, 70, 40, 255), (40, 24, 18, 255), 0.8)
    _circle(img, 24, 27, 3.2, LAVA_HOT + (255,))                       # the ember heart set in it
    _circle(img, 24, 27, 1.6, (255, 255, 230, 255))


def _plate_icon(img):
    g = _canvas(48, 48)
    _circle(g, 24, 26, 18, (255, 110, 30, 120))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(4 * S)))
    _poly(img, [(14, 6), (34, 6), (44, 16), (38, 22), (36, 42), (12, 42), (10, 22), (4, 16)], (40, 32, 50, 255),
          (14, 10, 18, 255), 1.4)
    _poly(img, [(14, 6), (24, 14), (34, 6), (36, 22), (24, 30), (12, 22)], (70, 58, 98, 255))
    for pts in ([(17, 26), (21, 32), (19, 38)], [(31, 26), (27, 33), (30, 38)]):
        _line(img, pts, LAVA + (255,), 1.6)
    _circle(img, 24, 21, 3.6, LAVA_HOT + (255,))
    _line(img, [(12, 34), (36, 34)], (120, 70, 40, 230), 2)


def _sulfur_pot_icon(img):
    _ball(img, (10, 14, 38, 42), (120, 96, 60, 255))
    _rrect(img, (17, 8, 31, 16), 3, (150, 120, 70, 255))
    _circle(img, 24, 28, 5, (230, 210, 70, 255))


art.ICON_MAKERS.update({
    "obsidian": _obsidian_icon, "sulfur": _sulfur_icon, "ember": _ember_icon, "beetle_shell": _shell_icon,
    "ember_crown": _crown_icon, "obsidian_plate": _plate_icon,
})


# --------------------------------------------------------------------------- worn gear
def _worn_crown():
    img = _canvas(64, 64)
    g = _canvas(64, 64)
    _circle(g, 32, 32, 12, (255, 110, 30, 140))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
    _ball(img, (21, 20, 41, 44), (44, 36, 54, 255))
    for k in range(7):                         # obsidian spikes standing out round the back of the head
        a = math.pi / 2 + (k - 3) * 0.42
        x0, y0 = 31 + math.cos(a + math.pi) * 9, 32 + math.sin(a + math.pi) * 9
        x1, y1 = 31 + math.cos(a + math.pi) * 15, 32 + math.sin(a + math.pi) * 15
        nx, ny = math.cos(a) * 2.2, math.sin(a) * 2.2
        _poly(img, [(x0 - ny, y0 + nx), (x1, y1), (x0 + ny, y0 - nx)], (70, 56, 98, 255), (16, 12, 22, 255), 0.8)
    _circle(img, 38, 32, 2.6, LAVA_HOT + (255,))      # the ember over the brow
    return _finish(img, 64, 64)


def _worn_plate():
    img = _canvas(64, 64)
    _ball(img, (14, 12, 46, 52), (42, 34, 52, 255))
    for y0 in (10, 40):                        # faceted obsidian pauldrons
        _poly(img, [(20, y0 + 7), (26, y0), (38, y0 + 1), (42, y0 + 7), (36, y0 + 13), (24, y0 + 13)],
              (72, 58, 100, 255), (16, 12, 22, 255), 0.9)
    rnd = random.Random(8200)
    for _ in range(6):                         # ember seams
        x, y = rnd.uniform(16, 34), rnd.uniform(18, 46)
        _line(img, [(x, y), (x + rnd.uniform(-4, 4), y + rnd.uniform(-5, 5))], LAVA + (255,), 1.4)
    art_gear._cut_head(img)
    return _finish(img, 64, 64)


art_gear.HEAD["ember_crown"] = _worn_crown
art_gear.BODY["obsidian_plate"] = _worn_plate


def all_textures():
    """Used by --export-art."""
    for i in range(3):
        ground(i)
        obsidian(i)
        vent(i)
        charred_tree(i)
    for i in range(4):
        decor(i)
        basalt(i)
    for i in range(8):
        crack(i)
    lava_pool()
    ash_ore("coal")
    ash_ore("iron")
    art_extra.animal("fire_beetle")
