"""
art_extra.py - painted-in-code art for the bigger update: animals, bosses, caves, ores,
new buildings and every new item icon. Same style (and same assets/ override) as art.py.
Importing this module registers all the new icons with art.icon().
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
from art import (S, _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shade, _shadow, _tex)


# =========================================================================== animals (face right)
def _quad(img, c, body, size, legs_col, head_box, ear=None):
    """Generic four-legged animal seen from above."""
    bw, bh = size
    for dx in (-bw * 0.32, bw * 0.28):
        for side in (-1, 1):
            _ball(img, (c + dx - 3, c + side * bh * 0.42 - 3, c + dx + 3, c + side * bh * 0.42 + 3), legs_col + (255,),
                  outline=False)
    _ball(img, (c - bw / 2, c - bh / 2, c + bw / 2, c + bh / 2), body + (255,))
    _ball(img, head_box, _shade(body, 1.08) + (255,))


def _rabbit_img():
    img = _canvas(40, 40)
    _shadow(img, (8, 12, 34, 34), alpha=70, blur=2)
    _ball(img, (9, 12, 29, 28), (168, 136, 104, 255))
    _ball(img, (24, 14, 35, 26), (182, 150, 116, 255))
    for side in (-1, 1):   # long ears laid back
        _ball(img, (16, 20 + side * 5 - 2, 27, 20 + side * 5 + 2), (196, 164, 130, 255))
    _circle(img, 9, 20, 3.5, (240, 236, 228, 255))    # tail
    _circle(img, 32, 18, 1.2, (30, 20, 20, 255))
    _circle(img, 32, 22, 1.2, (30, 20, 20, 255))
    return _finish(img, 40, 40)


def _deer_img():
    img = _canvas(76, 76)
    _shadow(img, (10, 18, 72, 66), alpha=80, blur=3)
    _quad(img, 38, (176, 122, 72), (44, 24), (110, 74, 44), (50, 30, 66, 46))
    for x, y in [(28, 32), (34, 40), (24, 42)]:     # spots
        _circle(img, x, y, 1.6, (236, 220, 196, 220))
    for side in (-1, 1):   # antlers
        _line(img, [(56, 38 + side * 4), (52, 38 + side * 14), (58, 38 + side * 18)], (226, 210, 180, 255), 2)
        _line(img, [(53, 38 + side * 10), (47, 38 + side * 13)], (226, 210, 180, 255), 1.6)
    _circle(img, 64, 36, 1.4, (30, 20, 20, 255))
    _circle(img, 64, 40, 1.4, (30, 20, 20, 255))
    return _finish(img, 76, 76)


def _boar_img():
    img = _canvas(64, 64)
    _shadow(img, (8, 16, 60, 56), alpha=85, blur=3)
    _quad(img, 32, (98, 70, 52), (40, 28), (60, 42, 30), (42, 22, 58, 42))
    for x in range(16, 44, 4):   # bristly back
        _line(img, [(x, 31), (x + 2, 33)], (60, 44, 34, 255), 1.4)
    _ball(img, (54, 27, 61, 37), (160, 120, 110, 255))                     # snout
    for side in (-1, 1):
        _line(img, [(55, 32 + side * 5), (61, 32 + side * 8)], (240, 236, 220, 255), 2)   # tusks
    _circle(img, 51, 28, 1.3, (20, 10, 10, 255))
    _circle(img, 51, 36, 1.3, (20, 10, 10, 255))
    return _finish(img, 64, 64)


def _wolf_img():
    img = _canvas(64, 64)
    _shadow(img, (8, 16, 60, 56), alpha=85, blur=3)
    _quad(img, 32, (126, 128, 134), (40, 22), (84, 86, 92), (40, 23, 56, 41))
    _ball(img, (4, 28, 18, 36), (110, 112, 118, 255))                       # tail
    _ball(img, (53, 28, 62, 36), (150, 150, 156, 255))                      # muzzle
    for side in (-1, 1):
        _poly(img, [(44, 32 + side * 6), (50, 32 + side * 11), (50, 32 + side * 5)], (96, 98, 104, 255))
    _circle(img, 52, 29, 1.4, (250, 210, 80, 255))
    _circle(img, 52, 35, 1.4, (250, 210, 80, 255))
    return _finish(img, 64, 64)


ANIMAL_ART = {"rabbit": (_rabbit_img, 9), "deer": (_deer_img, 16), "boar": (_boar_img, 15), "wolf": (_wolf_img, 14)}


def animal(kind):
    maker, hb = ANIMAL_ART[kind]
    return _tex(f"animal_{kind}", maker, [(-hb, -hb), (hb, -hb), (hb, hb), (-hb, hb)])


# =========================================================================== cave enemies
def _crawler_img():
    img = _canvas(56, 56)
    _shadow(img, (10, 14, 50, 50), alpha=80, blur=2)
    for k in range(4):
        for side in (-1, 1):
            a = side * (0.6 + k * 0.42)
            _line(img, [(28, 28), (28 + math.cos(a) * 14, 28 + math.sin(a) * 14),
                        (28 + math.cos(a) * 22 - 4, 28 + math.sin(a) * 25)], (60, 52, 70, 255), 2.2)
    _ball(img, (14, 18, 34, 38), (78, 66, 96, 255))
    _ball(img, (30, 21, 42, 35), (96, 82, 116, 255))
    for y in (25, 28, 31):
        _circle(img, 40, y, 1.3, (120, 255, 160, 255))
    return _finish(img, 56, 56)


def _golem_img():
    rnd = random.Random(4)
    img = _canvas(84, 84)
    _shadow(img, (10, 16, 80, 80), alpha=100, blur=3)
    for side in (-1, 1):   # boulder fists
        _ball(img, (44, 42 + side * 24 - 9, 64, 42 + side * 24 + 9), (104, 100, 112, 255))
    _ball(img, (16, 18, 60, 66), (92, 88, 100, 255))
    _ball(img, (40, 30, 62, 54), (112, 108, 120, 255))
    for _ in range(6):   # glowing crystal veins
        x, y = rnd.uniform(22, 54), rnd.uniform(24, 60)
        _poly(img, [(x, y - 4), (x + 3, y), (x, y + 4), (x - 3, y)], (130, 220, 255, 255))
    _circle(img, 56, 38, 2, (160, 240, 255, 255))
    _circle(img, 56, 46, 2, (160, 240, 255, 255))
    return _finish(img, 84, 84)


def _broodling_img():
    img = _canvas(40, 40)
    _shadow(img, (8, 12, 34, 34), alpha=70, blur=2)
    for k in range(3):
        for side in (-1, 1):
            a = side * (0.8 + k * 0.5)
            _line(img, [(20, 20), (20 + math.cos(a) * 13, 20 + math.sin(a) * 13)], (60, 90, 40, 255), 1.6)
    _ball(img, (10, 13, 26, 27), (110, 160, 60, 255))
    _ball(img, (23, 15, 31, 25), (140, 190, 70, 255))
    _circle(img, 29, 18, 1.2, (255, 80, 60, 255))
    _circle(img, 29, 22, 1.2, (255, 80, 60, 255))
    return _finish(img, 40, 40)


def enemy(kind):
    """Textures for the new hostile kinds (zombies keep using art.zombie)."""
    makers = {"crawler": (_crawler_img, 13), "golem": (_golem_img, 22), "broodling": (_broodling_img, 9)}
    maker, hb = makers[kind]
    return _tex(f"enemy_{kind}", maker, [(-hb, -hb), (hb, -hb), (hb, hb), (-hb, hb)])


# =========================================================================== bosses
def _titan_img():
    rnd = random.Random(21)
    w = 170
    img = _canvas(w, w)
    c = w / 2
    _shadow(img, (20, 30, 160, 166), alpha=120, blur=7)
    for side in (-1, 1):     # huge arms with boulder fists
        _line(img, [(c - 6, c + side * 40), (c + 44, c + side * 46)], (96, 84, 70, 255), 22)
        _ball(img, (c + 34, c + side * 46 - 18, c + 70, c + side * 46 + 18), (118, 104, 88, 255))
    _ball(img, (c - 52, c - 52, c + 40, c + 52), (110, 96, 80, 255))
    _ball(img, (c - 30, c - 36, c + 26, c + 36), (128, 112, 92, 255), outline=False)
    _ball(img, (c + 12, c - 20, c + 50, c + 20), (138, 120, 98, 255))             # head
    for _ in range(14):      # molten cracks
        x, y = rnd.uniform(c - 44, c + 30), rnd.uniform(c - 44, c + 44)
        pts = [(x, y)]
        for _ in range(3):
            x += rnd.uniform(-8, 8)
            y += rnd.uniform(-8, 8)
            pts.append((x, y))
        _line(img, pts, (255, 140, 40, 230), 2.2)
    _circle(img, c + 40, c - 8, 4, (255, 180, 60, 255))
    _circle(img, c + 40, c + 8, 4, (255, 180, 60, 255))
    return _finish(img, w, w)


def _brood_img():
    w = 160
    img = _canvas(w, w)
    c = w / 2
    _shadow(img, (16, 24, 150, 150), alpha=110, blur=7)
    for k in range(4):
        for side in (-1, 1):
            a = side * (0.5 + k * 0.5)
            p1 = (c + math.cos(a) * 34, c + math.sin(a) * 34)
            p2 = (c + math.cos(a) * 62, c + math.sin(a) * 70)
            _line(img, [(c, c), p1, p2], (50, 70, 34, 255), 6)
            _line(img, [(c, c), p1, p2], (90, 120, 50, 255), 3.5)
    _ball(img, (c - 64, c - 40, c + 6, c + 40), (110, 150, 60, 255))               # egg sac abdomen
    for x, y in [(c - 44, c - 14), (c - 30, c + 16), (c - 18, c - 22), (c - 50, c + 12)]:
        _ball(img, (x - 7, y - 6, x + 7, y + 6), (210, 230, 140, 220))
    _ball(img, (c - 6, c - 26, c + 34, c + 26), (80, 112, 46, 255))
    _ball(img, (c + 26, c - 16, c + 52, c + 16), (96, 130, 54, 255))
    for y in (-8, -3, 3, 8):
        _circle(img, c + 46, c + y, 2.2, (255, 60, 50, 255))
    return _finish(img, w, w)


def _wraith_img():
    w = 150
    img = _canvas(w, w)
    c = w / 2
    glow = _canvas(w, w)
    _circle(glow, c, c, 56, (150, 210, 255, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * S)))
    pts = []   # tattered cloak
    for k in range(18):
        a = k / 18 * math.tau
        r = 50 if k % 2 == 0 else 38
        pts.append((c - 6 + math.cos(a) * r, c + math.sin(a) * r))
    _poly(img, pts, (190, 220, 245, 200), (120, 160, 210, 230), 1.5)
    _ball(img, (c - 30, c - 30, c + 24, c + 30), (220, 236, 250, 230))
    _ball(img, (c + 8, c - 16, c + 40, c + 16), (236, 244, 255, 255))
    for side in (-1, 1):
        _line(img, [(c, c + side * 26), (c + 46, c + side * 40)], (200, 225, 250, 220), 5)
        for k in range(3):
            _line(img, [(c + 46, c + side * 40), (c + 56, c + side * (36 + k * 5))], (230, 245, 255, 255), 1.6)
    _circle(img, c + 32, c - 6, 3, (80, 200, 255, 255))
    _circle(img, c + 32, c + 6, 3, (80, 200, 255, 255))
    return _finish(img, w, w)


def _colossus_img():
    rnd = random.Random(8)
    w = 180
    img = _canvas(w, w)
    c = w / 2
    glow = _canvas(w, w)
    _circle(glow, c, c, 70, (255, 90, 20, 110))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * S)))
    for side in (-1, 1):
        _line(img, [(c - 6, c + side * 42), (c + 48, c + side * 50)], (60, 30, 24, 255), 22)
        _ball(img, (c + 36, c + side * 50 - 17, c + 70, c + side * 50 + 17), (90, 40, 26, 255))
    _ball(img, (c - 56, c - 56, c + 42, c + 56), (66, 32, 26, 255))
    for _ in range(18):     # lava seams
        x, y = rnd.uniform(c - 48, c + 30), rnd.uniform(c - 48, c + 48)
        _line(img, [(x, y), (x + rnd.uniform(-10, 10), y + rnd.uniform(-10, 10))], (255, 120, 30, 240), 2.6)
    _ball(img, (c + 10, c - 22, c + 52, c + 22), (90, 42, 30, 255))
    for k in range(5):      # flaming crown
        a = -0.9 + k * 0.45
        _poly(img, [(c + 24 + math.cos(a) * 18, c + math.sin(a) * 18), (c + 18 + math.cos(a) * 34, c + math.sin(a) * 30),
                    (c + 30 + math.cos(a) * 20, c + math.sin(a) * 22)], (255, 170, 40, 255))
    _circle(img, c + 42, c - 9, 4, (255, 240, 140, 255))
    _circle(img, c + 42, c + 9, 4, (255, 240, 140, 255))
    return _finish(img, w, w)


BOSS_ART = {"titan": (_titan_img, 50), "brood": (_brood_img, 46), "wraith": (_wraith_img, 40),
            "colossus": (_colossus_img, 54)}


def boss(kind):
    maker, hb = BOSS_ART[kind]
    return _tex(f"boss_{kind}", maker, [(-hb, -hb), (hb, -hb), (hb, hb), (-hb, hb)])


# =========================================================================== caves
def _cave_floor_img(seed):
    rnd = random.Random(seed)
    w = 60
    img = Image.new("RGBA", (w * S, w * S), (58, 52, 50, 255))
    d = ImageDraw.Draw(img)
    for _ in range(60):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0, w), rnd.uniform(2, 7)
        v = rnd.randint(46, 72)
        d.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=(v, v - 5, v - 7, 255))
    img = img.filter(ImageFilter.GaussianBlur(1.5 * S))
    for _ in range(5):
        _circle(img, rnd.uniform(4, 56), rnd.uniform(4, 56), rnd.uniform(1, 2), (90, 84, 80, 255))
    return _finish(img, w, w)


def cave_floor(i):
    return _tex(f"cave_floor_{i}", lambda: _cave_floor_img(800 + i))


def _cave_wall_img(seed):
    rnd = random.Random(seed)
    w = 60
    img = _canvas(w + 12, w + 12)
    _shadow(img, (0, 4, w + 12, w + 12), alpha=150, blur=4)
    for _ in range(5):
        x, y, r = rnd.uniform(14, w - 2), rnd.uniform(14, w - 2), rnd.uniform(16, 24)
        base = rnd.choice([(84, 76, 72), (74, 68, 66), (92, 84, 78)])
        _ball(img, (x - r, y - r, x + r, y + r), base + (255,), soft=1.2)
    return _finish(img, w + 12, w + 12)


def cave_wall(i):
    return _tex(f"cave_wall_{i}", lambda: _cave_wall_img(900 + i), [(-30, -30), (30, -30), (30, 30), (-30, 30)])


def _entrance_img():
    w = 110
    img = _canvas(w, w)
    c = w / 2
    _shadow(img, (6, 10, 106, 108), alpha=120, blur=5)
    for k in range(11):
        a = k / 11 * math.tau
        x, y = c + math.cos(a) * 40, c + math.sin(a) * 38
        _ball(img, (x - 11, y - 10, x + 11, y + 10), (120, 114, 106, 255))
    hole = _canvas(w, w)
    _circle(hole, c, c, 33, (0, 0, 0, 255))
    img.alpha_composite(hole.filter(ImageFilter.GaussianBlur(3 * S)))
    _circle(img, c, c, 24, (4, 4, 8, 255))
    for k in range(4):   # ladder rungs disappearing into the dark
        y = c - 12 + k * 8
        _line(img, [(c - 9, y), (c + 9, y)], (130, 96, 60, 255 - k * 55), 2.4)
    _line(img, [(c - 9, c - 16), (c - 9, c + 16)], (110, 80, 50, 220), 2.4)
    _line(img, [(c + 9, c - 16), (c + 9, c + 16)], (110, 80, 50, 220), 2.4)
    return _finish(img, w, w)


def cave_entrance():
    return _tex("cave_entrance", _entrance_img, [(-30, -30), (30, -30), (30, 30), (-30, 30)])


def _ladder_img():
    w = 80
    img = _canvas(w, w)
    c = w / 2
    glow = _canvas(w, w)
    _circle(glow, c, c, 34, (255, 240, 190, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8 * S)))
    _line(img, [(c - 10, 10), (c - 10, 70)], (126, 90, 54, 255), 4)
    _line(img, [(c + 10, 10), (c + 10, 70)], (126, 90, 54, 255), 4)
    for k in range(6):
        _line(img, [(c - 10, 14 + k * 10), (c + 10, 14 + k * 10)], (156, 114, 70, 255), 3)
    return _finish(img, w, w)


def ladder():
    return _tex("cave_ladder", _ladder_img)


# --------------------------------------------------------------------------- ore nodes
def _ore_img(seed, base, speck, glow=None, crystal=False):
    rnd = random.Random(seed)
    w, h = 70, 62
    img = _canvas(w, h)
    _shadow(img, (8, 16, 68, 62), alpha=90, blur=4)
    if glow:
        g = _canvas(w, h)
        _circle(g, 35, 30, 28, glow + (110,))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(6 * S)))
    pts = []
    for k in range(9):
        a = k / 9 * math.tau
        r = rnd.uniform(22, 28)
        pts.append((35 + math.cos(a) * r, 30 + math.sin(a) * r * 0.82))
    _poly(img, pts, base + (255,), _shade(base, 0.4) + (255,), 1.6)
    top = [p for p in pts if p[1] < 30 or p[0] < 30]
    _poly(img, [(35, 26)] + top[:5], _shade(base, 1.2) + (140,))
    if crystal:
        for _ in range(6):
            x, y = rnd.uniform(20, 50), rnd.uniform(14, 44)
            hgt = rnd.uniform(8, 15)
            _poly(img, [(x - 4, y + 4), (x, y - hgt), (x + 4, y + 4)], speck + (255,), _shade(speck, 0.6) + (255,), 1)
            _line(img, [(x - 1, y), (x, y - hgt + 3)], (255, 255, 255, 160), 1)
    else:
        for _ in range(9):
            x, y = rnd.uniform(18, 52), rnd.uniform(14, 44)
            r = rnd.uniform(2.2, 4.2)
            _ball(img, (x - r, y - r, x + r, y + r), speck + (255,), outline=False)
    return _finish(img, w, h)


ORE_LOOK = {
    "iron": ((112, 100, 94), (196, 120, 70), None, False),
    "coal": ((96, 92, 90), (30, 28, 30), None, False),
    "crystal": ((76, 70, 90), (150, 220, 255), (120, 200, 255), True),
    "cave_rock": ((96, 88, 84), (120, 112, 106), None, False),
}


def ore(kind, i=0):
    base, speck, glow, cr = ORE_LOOK[kind]
    return _tex(f"ore_{kind}_{i}", lambda: _ore_img(1000 + i * 7 + len(kind), base, speck, glow, cr), art.ROCK_HIT)


# =========================================================================== buildings
def _workbench_img():
    img = _canvas(56, 48)
    _shadow(img, (2, 6, 56, 50), alpha=80, blur=2)
    _rrect(img, (3, 4, 53, 44), 3, (150, 106, 62, 255), (80, 54, 30, 255), 1.4)
    for y in (14, 24, 34):
        _line(img, [(5, y), (51, y)], (120, 82, 46, 255), 1)
    _line(img, [(12, 12), (30, 16)], (170, 170, 176, 255), 2.4)      # saw
    _poly(img, [(36, 26), (48, 22), (49, 30)], (150, 148, 142, 255), (70, 70, 72, 255), 0.8)   # hammer head
    _line(img, [(30, 34), (42, 27)], (110, 74, 42, 255), 2.4)
    return _finish(img, 56, 48)


def _furnace_img():
    img = _canvas(52, 52)
    _shadow(img, (2, 6, 52, 54), alpha=90, blur=2)
    _rrect(img, (4, 4, 48, 48), 8, (120, 116, 110, 255), (60, 58, 56, 255), 1.4)
    for row in range(4):
        for k in range(3):
            x = 8 + k * 13 + (row % 2) * 6
            _rrect(img, (x, 8 + row * 10, x + 11, 16 + row * 10), 2, (140, 134, 126, 255), (80, 78, 74, 255), 0.6)
    g = _canvas(52, 52)
    _circle(g, 26, 34, 12, (255, 120, 30, 200))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
    _rrect(img, (17, 28, 35, 42), 4, (40, 20, 14, 255))
    _circle(img, 26, 36, 5, (255, 170, 60, 255))
    return _finish(img, 52, 52)


def _storage_img():
    img = _canvas(48, 44)
    _shadow(img, (2, 6, 48, 46), alpha=80, blur=2)
    _rrect(img, (3, 4, 45, 40), 3, (128, 90, 52, 255), (70, 46, 24, 255), 1.4)
    _rrect(img, (3, 4, 45, 16), 3, (150, 108, 62, 255), (70, 46, 24, 255), 1.2)
    for x in (8, 40):
        _line(img, [(x, 5), (x, 39)], (90, 90, 96, 255), 2.4)
    _rrect(img, (20, 12, 28, 20), 1, (230, 190, 80, 255), (120, 90, 30, 255), 0.8)
    return _finish(img, 48, 44)


def _iron_wall_img():
    img = _canvas(40, 40)
    _shadow(img, (2, 6, 40, 42), alpha=80, blur=2)
    _rrect(img, (1, 1, 39, 39), 3, (120, 124, 132, 255), (60, 62, 68, 255), 1.4)
    for x in (13, 27):
        _line(img, [(x, 2), (x, 38)], (90, 94, 102, 255), 1.4)
    for x in (5, 20, 35):
        for y in (6, 20, 34):
            _circle(img, x, y, 1.4, (190, 194, 200, 255))
    _line(img, [(3, 5), (37, 5)], (170, 176, 186, 200), 1)
    return _finish(img, 40, 40)


def _brazier_img():
    img = _canvas(48, 48)
    _shadow(img, (4, 8, 48, 50), alpha=80, blur=2)
    for k in range(3):
        a = k / 3 * math.tau + 0.5
        _line(img, [(24, 24), (24 + math.cos(a) * 20, 24 + math.sin(a) * 20)], (70, 70, 76, 255), 3)
    _ball(img, (8, 8, 40, 40), (96, 98, 106, 255))
    _circle(img, 24, 24, 11, (40, 30, 30, 255))
    for x, y in [(20, 22), (27, 25), (23, 28)]:
        _circle(img, x, y, 3, (30, 26, 26, 255))
    return _finish(img, 48, 48)


def _tex_b(name, maker, hb):
    return lambda: _tex(f"build_{name}", maker, [(-hb[0], -hb[1]), (hb[0], -hb[1]), (hb[0], hb[1]), (-hb[0], hb[1])])


art.STRUCTURE_ICONS.update({
    "workbench": _tex_b("workbench", _workbench_img, (26, 20)),
    "furnace": _tex_b("furnace", _furnace_img, (22, 22)),
    "storage": _tex_b("storage", _storage_img, (22, 19)),
    "iron_wall": _tex_b("iron_wall", _iron_wall_img, (19, 19)),
    "brazier": _tex_b("brazier", _brazier_img, (16, 16)),
})


# =========================================================================== item icons
def _meat_icon(img, cooked=False):
    col = (150, 84, 46) if cooked else (200, 70, 80)
    _ball(img, (8, 12, 36, 38), col + (255,))
    _ball(img, (12, 16, 26, 28), _shade(col, 1.25) + (200,), outline=False)
    _line(img, [(32, 32), (42, 42)], (240, 232, 210, 255), 5)
    _circle(img, 43, 43, 3.4, (240, 232, 210, 255))
    if cooked:
        for x in (16, 24):
            _line(img, [(x, 10), (x + 2, 4)], (230, 230, 230, 140), 1.5)


def _hide_icon(img, col=(170, 120, 80)):
    _poly(img, [(8, 14), (16, 8), (24, 12), (32, 8), (40, 14), (36, 26), (42, 38), (30, 36), (24, 42), (18, 36),
                (6, 38), (12, 26)], col + (255,), _shade(col, 0.5) + (255,), 1.4)
    _ball(img, (16, 16, 32, 32), _shade(col, 1.12) + (200,), outline=False)


def _leather_icon(img):
    _rrect(img, (8, 12, 40, 36), 4, (140, 90, 50, 255), (80, 50, 26, 255))
    _line(img, [(8, 20), (40, 20)], (170, 120, 70, 255), 1.4)
    for x in range(12, 38, 5):
        _line(img, [(x, 30), (x + 2, 30)], (230, 210, 170, 255), 1.2)


def _fur_icon(img):
    _hide_icon(img, (150, 152, 160))
    for k in range(8):
        x = 12 + k * 3.5
        _line(img, [(x, 20), (x + 2, 15)], (220, 222, 228, 220), 1.4)


def _lump_icon(base, speck, crystal=False):
    def f(img):
        _ball(img, (8, 12, 40, 40), base + (255,))
        rnd = random.Random(sum(base))
        for _ in range(6 if not crystal else 0):
            x, y = rnd.uniform(14, 34), rnd.uniform(18, 34)
            _circle(img, x, y, rnd.uniform(2, 3.4), speck + (255,))
        if crystal:
            for x, hgt in [(18, 22), (26, 30), (33, 20)]:
                _poly(img, [(x - 5, 36), (x, 36 - hgt), (x + 5, 36)], speck + (255,), _shade(speck, 0.5) + (255,), 1)
    return f


def _ingot_icon(img):
    for dy in (8, -4):
        _poly(img, [(8, 30 + dy), (14, 20 + dy), (40, 20 + dy), (44, 30 + dy)], (170, 174, 184, 255),
              (80, 82, 90, 255), 1.2)
        _poly(img, [(14, 20 + dy), (40, 20 + dy), (37, 23 + dy), (17, 23 + dy)], (220, 224, 232, 255))


def _core_icon(img):
    _ball(img, (8, 8, 40, 40), (110, 96, 80, 255))
    for a in range(5):
        t = a / 5 * math.tau
        _line(img, [(24, 24), (24 + math.cos(t) * 14, 24 + math.sin(t) * 14)], (255, 150, 40, 255), 2)
    _circle(img, 24, 24, 5, (255, 200, 80, 255))


def _chitin_icon(img):
    for k, dx in enumerate((0, 10, 20)):
        _poly(img, [(6 + dx, 34), (16 + dx, 10), (24 + dx, 34)], (110 + k * 15, 150, 60, 255), (50, 70, 30, 255), 1)


def _shard_icon(img):
    _poly(img, [(24, 4), (32, 22), (26, 44), (16, 24)], (180, 225, 255, 255), (90, 150, 210, 255), 1.4)
    _line(img, [(24, 8), (22, 36)], (255, 255, 255, 200), 1.4)


def _ember_icon(img):
    g = _canvas(48, 48)
    _circle(g, 24, 26, 16, (255, 120, 30, 160))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
    _circle(img, 18, 22, 8, (220, 50, 30, 255))
    _circle(img, 30, 22, 8, (220, 50, 30, 255))
    _poly(img, [(11, 25), (37, 25), (24, 40)], (220, 50, 30, 255))
    _circle(img, 24, 26, 5, (255, 220, 100, 255))


def _torch_icon(img):
    _line(img, [(6, 30), (32, 24)], (118, 80, 46, 255), 4.5)
    _rrect(img, (28, 19, 36, 29), 2, (150, 130, 90, 255))
    _poly(img, [(32, 26), (40, 14), (46, 22), (42, 32)], (255, 150, 40, 255))
    _poly(img, [(35, 25), (41, 18), (43, 25)], (255, 236, 150, 255))


def _tool_icon(head_col, shape):
    def f(img):
        _line(img, [(4, 26), (40, 24)], (118, 80, 46, 255), 4)
        if shape == "axe":
            _poly(img, [(30, 22), (44, 8), (47, 28), (36, 29)], head_col + (255,), _shade(head_col, 0.45) + (255,))
        else:
            _poly(img, [(30, 5), (40, 15), (47, 30), (40, 43), (34, 26)], head_col + (255,),
                  _shade(head_col, 0.45) + (255,))
    return f


def _sword_icon(blade, glow=None):
    def f(img):
        if glow:
            g = _canvas(48, 48)
            _line(g, [(18, 24), (46, 23)], glow + (180,), 8)
            img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
        _line(img, [(4, 24), (14, 24)], (110, 74, 42, 255), 4)
        _line(img, [(14, 16), (14, 32)], (190, 160, 80, 255), 3)
        _poly(img, [(15, 21), (42, 21), (47, 24), (42, 27), (15, 27)], blade + (255,), _shade(blade, 0.45) + (255,), 1)
        _line(img, [(17, 23), (40, 23)], (255, 255, 255, 160), 1)
    return f


def _frost_spear_icon(img):
    _line(img, [(2, 26), (34, 24)], (200, 210, 230, 255), 3)
    _poly(img, [(32, 16), (47, 24), (32, 32), (36, 24)], (170, 225, 255, 255), (80, 140, 200, 255))


def _fang_icon(img):
    """Brood Fang: a curved chitin fang on a wrapped grip, venom glowing on the tip."""
    g = _canvas(48, 48)
    _circle(g, 40, 22, 7, (150, 255, 90, 150))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
    _rrect(img, (3, 21, 15, 28), 3, (96, 66, 38, 255), (54, 36, 20, 255))         # grip
    for x in (6, 9, 12):
        _line(img, [(x, 21), (x + 1, 28)], (150, 116, 70, 255), 1)              # wrapping
    _poly(img, [(14, 17), (19, 18), (19, 31), (14, 32)], (104, 146, 58, 255), (50, 70, 30, 255), 1)   # chitin guard
    blade = [(19, 20), (30, 17), (40, 15), (46, 20), (40, 21), (30, 25), (19, 28)]
    _poly(img, blade, (226, 222, 196, 255), (110, 104, 80, 255), 1)               # the fang, curving up
    _line(img, [(21, 23), (31, 20), (40, 18)], (255, 255, 240, 170), 1)          # shine
    _line(img, [(36, 19), (44, 20)], (150, 240, 80, 255), 1.6)                   # venom on the tip
    _circle(img, 42, 25, 1.8, (150, 240, 80, 255))                               # ...dripping
    _circle(img, 41, 30, 1.2, (150, 240, 80, 200))


def _hammer_icon(img):
    _line(img, [(4, 26), (34, 24)], (90, 64, 40, 255), 5)
    _rrect(img, (28, 8, 46, 40), 4, (118, 104, 88, 255), (60, 52, 44, 255))
    _line(img, [(31, 14), (43, 34)], (255, 150, 40, 255), 2)


def _medkit_icon(img):
    _rrect(img, (8, 12, 40, 38), 6, (236, 236, 240, 255), (140, 140, 150, 255))
    _rrect(img, (20, 16, 28, 34), 1, (80, 200, 255, 255))
    _rrect(img, (14, 22, 34, 28), 1, (80, 200, 255, 255))


def _helmet_icon(col):
    def f(img):
        _ball(img, (8, 10, 40, 38), col + (255,))
        _rrect(img, (6, 30, 42, 36), 2, _shade(col, 0.7) + (255,))
        _line(img, [(24, 10), (24, 30)], _shade(col, 1.3) + (200,), 2)
    return f


def _body_icon(col, trim):
    def f(img):
        _poly(img, [(14, 6), (34, 6), (44, 16), (38, 22), (36, 42), (12, 42), (10, 22), (4, 16)], col + (255,),
              _shade(col, 0.45) + (255,), 1.4)
        _line(img, [(18, 7), (24, 14), (30, 7)], trim + (255,), 2)
        _line(img, [(12, 34), (36, 34)], trim + (220,), 2)
    return f


def _cloak_icon(col, trim):
    def f(img):
        _poly(img, [(18, 6), (30, 6), (42, 42), (30, 38), (24, 44), (18, 38), (6, 42)], col + (255,),
              _shade(col, 0.5) + (255,), 1.4)
        _circle(img, 24, 9, 3, trim + (255,))
        for k in range(5):
            _line(img, [(10 + k * 7, 40), (12 + k * 7, 34)], _shade(col, 1.3) + (200,), 1.4)
    return f


def _cold_icon(img):
    for k in range(6):
        a = k / 6 * math.tau
        _line(img, [(24, 24), (24 + math.cos(a) * 18, 24 + math.sin(a) * 18)], (170, 220, 255, 255), 3)
        _line(img, [(24 + math.cos(a) * 11, 24 + math.sin(a) * 11),
                    (24 + math.cos(a + 0.5) * 15, 24 + math.sin(a + 0.5) * 15)], (170, 220, 255, 255), 2)


def _shield_icon(img):
    _poly(img, [(24, 4), (42, 10), (40, 28), (24, 44), (8, 28), (6, 10)], (130, 150, 180, 255), (60, 70, 90, 255), 1.6)
    _poly(img, [(24, 8), (38, 13), (24, 13)], (200, 214, 236, 160))


def _paw_icon(img):
    _ball(img, (14, 22, 34, 40), (230, 210, 190, 255))
    for x, y in [(12, 16), (20, 10), (28, 10), (36, 16)]:
        _ball(img, (x - 4.5, y - 4.5, x + 4.5, y + 4.5), (230, 210, 190, 255))


def _bow_icon(img):
    arc = [(14 + 22 * math.sin(k / 12 * math.pi) * 0.9, 4 + k / 12 * 40) for k in range(13)]
    _line(img, arc, (130, 86, 46, 255), 4)
    _line(img, [arc[0], arc[-1]], (230, 230, 220, 230), 1.2)
    _rrect(img, (30, 20, 37, 28), 2, (90, 60, 36, 255))     # grip


def _arrows_icon(img):
    for k, dy in enumerate((-7, 0, 7)):
        y0 = 30 + dy
        _line(img, [(6, y0 + 8), (38, y0 - 8)], (190, 150, 96, 255), 2.4)
        _poly(img, [(36, y0 - 11), (45, y0 - 13), (40, y0 - 5)], (170, 176, 186, 255), (80, 84, 92, 255), 1)
        _poly(img, [(5, y0 + 5), (11, y0 + 4), (9, y0 + 10), (3, y0 + 11)], (220, 80, 70, 255))


def _fire_pot_icon(img):
    _ball(img, (10, 16, 38, 44), (176, 96, 60))
    _rrect(img, (17, 12, 31, 18), 2, (140, 74, 46, 255), (80, 40, 24, 255))
    _line(img, [(24, 12), (27, 6)], (230, 220, 180, 255), 2)
    _poly(img, [(25, 7), (29, 0), (33, 6), (29, 10)], (255, 150, 40, 255))
    _poly(img, [(28, 6), (30, 2), (31, 6)], (255, 236, 150, 255))


def _salve_icon(img):
    _rrect(img, (11, 18, 37, 43), 6, (236, 172, 48, 255), (150, 96, 20, 255))
    _rrect(img, (9, 11, 39, 19), 3, (150, 110, 70, 255), (90, 64, 40, 255))
    _rrect(img, (16, 24, 32, 33), 2, (255, 236, 200, 230))
    _line(img, [(24, 25), (24, 32)], (220, 70, 70, 255), 2.2)
    _line(img, [(20, 28.5), (28, 28.5)], (220, 70, 70, 255), 2.2)


def _bear_trap_icon(img):
    _circle(img, 24, 24, 19, (96, 92, 88, 255), (50, 48, 46, 255), 2)
    _circle(img, 24, 24, 12, (70, 60, 52, 255))
    for k in range(12):          # teeth pointing in
        a = k / 12 * math.tau
        p1 = (24 + math.cos(a - 0.18) * 18, 24 + math.sin(a - 0.18) * 18)
        p2 = (24 + math.cos(a + 0.18) * 18, 24 + math.sin(a + 0.18) * 18)
        tip = (24 + math.cos(a) * 10, 24 + math.sin(a) * 10)
        _poly(img, [p1, p2, tip], (200, 204, 210, 255))
    _circle(img, 24, 24, 4, (150, 120, 70, 255), (60, 48, 30, 255), 1)     # trigger plate


def _repair_hammer_icon(img):
    _line(img, [(8, 40), (30, 16)], (118, 80, 46, 255), 4.5)
    _poly(img, [(22, 10), (34, 4), (44, 16), (32, 22)], (170, 176, 186, 255), (70, 74, 82, 255), 1.4)
    _line(img, [(36, 8), (44, 4)], (200, 204, 212, 255), 3)          # claw
    _circle(img, 13, 33, 5, None, (120, 220, 120, 255), 2)            # green "fix" spark
    _line(img, [(13, 30), (13, 36)], (120, 220, 120, 255), 2)
    _line(img, [(10, 33), (16, 33)], (120, 220, 120, 255), 2)


def _pet_armor_icon(col, trim):
    def f(img):
        _poly(img, [(8, 16), (40, 16), (44, 34), (34, 40), (14, 40), (4, 34)], col + (255,),
              _shade(col, 0.5) + (255,), 1.4)
        _line(img, [(8, 22), (40, 22)], trim + (255,), 2)
        for x in (14, 24, 34):
            _circle(img, x, 31, 2.2, trim + (255,))
        _ball(img, (18, 6, 30, 18), (230, 210, 190))                     # paw pad
    return f


art.ICON_MAKERS.update({
    "repair_hammer": _repair_hammer_icon,
    "pet_leather_armor": _pet_armor_icon((150, 100, 56), (210, 180, 120)),
    "pet_iron_armor": _pet_armor_icon((160, 166, 178), (220, 224, 232)),
    "bow": _bow_icon, "arrows": _arrows_icon, "fire_pot": _fire_pot_icon, "honey_salve": _salve_icon,
    "bear_trap": _bear_trap_icon,
    "meat": lambda img: _meat_icon(img), "cooked_meat": lambda img: _meat_icon(img, True),
    "hide": lambda img: _hide_icon(img), "leather": _leather_icon, "fur": _fur_icon,
    "iron_ore": _lump_icon((110, 100, 94), (200, 120, 70)), "coal": _lump_icon((50, 48, 50), (20, 20, 22)),
    "crystal": _lump_icon((70, 64, 86), (150, 220, 255), crystal=True), "iron_ingot": _ingot_icon,
    "titan_core": _core_icon, "chitin": _chitin_icon, "frost_shard": _shard_icon, "ember_heart": _ember_icon,
    "torch": _torch_icon, "medkit": _medkit_icon,
    "iron_axe": _tool_icon((190, 194, 204), "axe"), "iron_pickaxe": _tool_icon((190, 194, 204), "pick"),
    "iron_sword": _sword_icon((200, 204, 214)), "ember_blade": _sword_icon((240, 120, 50), (255, 120, 30)),
    "frost_spear": _frost_spear_icon, "titan_hammer": _hammer_icon, "brood_fang": _fang_icon,
    "leather_cap": _helmet_icon((150, 100, 56)), "iron_helmet": _helmet_icon((170, 176, 188)),
    "leather_tunic": _body_icon((150, 100, 56), (210, 180, 120)),
    "iron_armor": _body_icon((160, 166, 178), (220, 224, 232)),
    "chitin_armor": _body_icon((110, 150, 60), (190, 220, 120)),
    "titan_plate": _body_icon((120, 104, 88), (255, 150, 40)),
    "fur_cloak": _cloak_icon((150, 152, 160), (200, 160, 80)),
    "frost_cloak": _cloak_icon((170, 210, 245), (80, 200, 255)),
    "cold": _cold_icon, "shield": _shield_icon, "paw": _paw_icon,
})


def all_new_textures():
    """Make sure every texture exists (used by --export-art)."""
    for k in ANIMAL_ART:
        animal(k)
    for k in ("crawler", "golem", "broodling"):
        enemy(k)
    for k in BOSS_ART:
        boss(k)
    for i in range(3):
        cave_floor(i)
        cave_wall(i)
    for k in ORE_LOOK:
        ore(k)
    cave_entrance()
    ladder()
