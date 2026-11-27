"""
art_highlands.py - painted-in-code art for the Stone Highlands (highlands.py).

Same style and same assets/ override as art.py (drop e.g. assets/hl_boulder_0.png in to replace one).
Importing this module plugs the new pictures into the existing art functions:
  * art.tree(i) for HL_TREE <= i < HL_TREE + 3 draws a wind-bent highland pine (chopped ones regrow as them)
  * art_extra.animal("goat") is the mountain goat
  * art.icon(...) knows the new item icons, art_gear.gear("wool_cloak") the worn cloak

Pictures that are draped over 3D shapes (boulders, ledges, standing stones, heather, the pine) are painted
fully OPAQUE over the whole area the shape samples, with no painted shadow, so nothing turns see-through.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
import art_extra
import art_gear
from art import S, _ball, _canvas, _circle, _finish, _line, _poly, _shade, _shadow, _tex

HL_TREE = 40             # tree variants HL_TREE .. HL_TREE + 2 are highland pines

STONE = (138, 134, 124)
STONE_D = (92, 88, 82)
STONE_L = (178, 174, 164)
LICHEN = (156, 164, 92)
HEATHER = [(150, 86, 146), (176, 108, 168), (128, 72, 128), (196, 132, 186)]
HEATH_GREEN = [(84, 100, 52), (100, 116, 60), (70, 86, 46)]


# =========================================================================== ground
def _scree_img(seed, grassy):
    """A 256 tile of scree and gravel (grassy=True: thin wiry grass and heather between the stones)."""
    rnd = random.Random(seed)
    n = 256
    base = (122, 122, 104) if grassy else (132, 128, 118)
    img = Image.new("RGBA", (n, n), base + (255,))
    blobs = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    pal = [(118, 114, 104), (146, 142, 130), (106, 104, 96), (138, 130, 112)]
    if grassy:
        pal += [(104, 120, 66), (96, 112, 60), (116, 126, 72)]
    for _ in range(140):
        r = rnd.randint(8, 30)
        x, y = rnd.randint(-10, n + 10), rnd.randint(-10, n + 10)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice(pal) + (rnd.randint(70, 150),))
    img.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(img)
    for _ in range(520 if not grassy else 300):         # gravel: little lit stones
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        r = rnd.uniform(1.0, 3.2)
        c = rnd.choice([(160, 156, 146), (120, 116, 108), (176, 170, 158), (100, 98, 92)])
        d.ellipse([x - r, y - r * 0.8, x + r, y + r * 0.8], fill=c + (255,))
        d.ellipse([x - r * 0.5, y - r * 0.6, x + r * 0.2, y], fill=_shade(c, 1.25) + (200,))
    for _ in range(34):                                 # flat slabs
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        rx, ry = rnd.uniform(5, 11), rnd.uniform(3, 7)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(150, 146, 136, 255), outline=(98, 94, 88, 255))
    if grassy:
        for _ in range(420):
            x, y = rnd.randint(0, n), rnd.randint(2, n)
            h = rnd.randint(3, 7)
            col = rnd.choice([(120, 136, 70), (92, 110, 54), (150, 150, 86)]) + (rnd.randint(140, 220),)
            d.line([(x, y), (x + rnd.randint(-2, 2), y - h)], fill=col, width=1)
        for _ in range(40):
            x, y = rnd.randint(0, n), rnd.randint(0, n)
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=rnd.choice(HEATHER) + (220,))
    return img


def ground(i):
    return _tex(f"hl_ground_{i}", lambda: _scree_img(6100 + i, i >= 2))


def _patch_img(seed, size, cols, slab=False):
    """A big soft-edged patch (plateau tops, scree fans, the Titan's stone circle)."""
    rnd = random.Random(seed)
    n = size
    img = Image.new("RGBA", (n, n), cols[0] + (255,))
    d = ImageDraw.Draw(img)
    for _ in range(int(n * n / 900)):
        r = rnd.randint(6, 24)
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice(cols) + (rnd.randint(80, 160),))
    img = img.filter(ImageFilter.GaussianBlur(4))
    d = ImageDraw.Draw(img)
    if slab:     # cracked flagstones
        for _ in range(int(n / 6)):
            x, y = rnd.randint(0, n), rnd.randint(0, n)
            ln = rnd.uniform(10, 34)
            a = rnd.uniform(0, math.tau)
            d.line([(x, y), (x + math.cos(a) * ln, y + math.sin(a) * ln)], fill=(84, 80, 74, 200), width=2)
    for _ in range(int(n * n / 260)):
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        r = rnd.uniform(1, 3)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice([(170, 166, 154), (110, 108, 100)]) + (220,))
    mask = art._radial(n).point(lambda v: 255 if v < 160 else max(0, int(255 - (v - 160) * 255 / 90)))
    mask = mask.resize((n, n))
    img.putalpha(mask)
    return img


def plateau_top():
    return _tex("hl_plateau_top", lambda: _patch_img(6200, 512, [(150, 146, 132), (136, 140, 112), (160, 156, 142),
                                                                 (120, 132, 92)]))


def scree_fan():
    return _tex("hl_scree_fan", lambda: _patch_img(6201, 256, [(140, 136, 126), (120, 118, 110), (158, 152, 140)]))


def stone_circle():
    return _tex("hl_stone_circle", lambda: _patch_img(6202, 512, [(128, 124, 116), (112, 108, 102), (140, 134, 124)],
                                                      slab=True))


# --------------------------------------------------------------------------- decor (ground tufts)
def _heather_tuft(seed):
    rnd = random.Random(seed)
    img = _canvas(30, 24)
    for _ in range(7):
        x, y = rnd.uniform(6, 24), rnd.uniform(8, 18)
        _ball(img, (x - 4, y - 3, x + 4, y + 3), rnd.choice(HEATH_GREEN) + (255,), outline=False)
    for _ in range(14):
        _circle(img, rnd.uniform(5, 25), rnd.uniform(5, 19), rnd.uniform(1.2, 2.2), rnd.choice(HEATHER) + (255,))
    return _finish(img, 30, 24)


def _scree_bits(seed):
    rnd = random.Random(seed)
    img = _canvas(30, 22)
    for _ in range(5):
        x, y, r = rnd.uniform(6, 24), rnd.uniform(6, 16), rnd.uniform(2.5, 5)
        _ball(img, (x - r, y - r * 0.75, x + r, y + r * 0.75), rnd.choice([STONE, STONE_L, (120, 116, 108)]) + (255,),
              outline=False)
    return _finish(img, 30, 22)


def _dry_grass(seed):
    rnd = random.Random(seed)
    img = _canvas(28, 24)
    for _ in range(11):
        x = rnd.uniform(6, 22)
        h = rnd.uniform(8, 18)
        col = rnd.choice([(150, 150, 86), (126, 136, 70), (170, 164, 104)]) + (255,)
        _line(img, [(x, 22), (x + rnd.uniform(2, 7), 22 - h)], col, 1.4)    # leaning with the wind
    return _finish(img, 28, 24)


def decor(i):
    i %= 6
    if i < 2:
        return _tex(f"hl_decor_heather_{i}", lambda: _heather_tuft(6300 + i))
    if i < 4:
        return _tex(f"hl_decor_scree_{i}", lambda: _scree_bits(6310 + i))
    return _tex(f"hl_decor_grass_{i}", lambda: _dry_grass(6320 + i))


# =========================================================================== stone
def _facet_rock(img, cx, cy, rx, ry, base, rnd, k=9, moss=True):
    """A fully opaque faceted rock polygon with lit / shaded facets."""
    pts = []
    for j in range(k):
        a = j / k * math.tau + rnd.uniform(-0.15, 0.15)
        r = rnd.uniform(0.9, 1.0)
        pts.append((cx + math.cos(a) * rx * r, cy + math.sin(a) * ry * r))
    _poly(img, pts, base + (255,), _shade(base, 0.45) + (255,), 1.4)
    ctr = (cx - rx * 0.12, cy - ry * 0.12)
    for j in range(k):          # facets: light from the top-left
        p0, p1 = pts[j], pts[(j + 1) % k]
        mx, my = (p0[0] + p1[0]) / 2 - cx, (p0[1] + p1[1]) / 2 - cy
        f = 1.0 - 0.28 * (mx / rx + my / ry) + rnd.uniform(-0.08, 0.08)
        _poly(img, [ctr, p0, p1], _shade(base, max(0.6, min(1.35, f))) + (255,))
    _poly(img, [(ctr[0] + (p[0] - ctr[0]) * 0.42, ctr[1] + (p[1] - ctr[1]) * 0.42) for p in pts],
          _shade(base, 1.18) + (255,))
    for _ in range(5):          # cracks
        x, y = cx + rnd.uniform(-0.6, 0.6) * rx, cy + rnd.uniform(-0.6, 0.6) * ry
        _line(img, [(x, y), (x + rnd.uniform(-6, 6), y + rnd.uniform(2, 8))], _shade(base, 0.5) + (220,), 1)
    if moss:
        for _ in range(7):      # lichen
            _circle(img, cx + rnd.uniform(-0.6, 0.5) * rx, cy + rnd.uniform(-0.7, 0.1) * ry, rnd.uniform(1.5, 3.5),
                    LICHEN + (230,))


def _boulder_img(seed):
    rnd = random.Random(seed)
    w, h = 100, 92
    img = _canvas(w, h)
    base = rnd.choice([(136, 132, 122), (124, 120, 114), (146, 138, 124)])
    _facet_rock(img, 50, 46, 48, 44, base, rnd, k=10)
    return _finish(img, w, h)


BOULDER_HIT = [(-34, -30), (34, -30), (40, 4), (20, 34), (-20, 34), (-40, 4)]


def boulder(i):
    return _tex(f"hl_boulder_{i % 3}", lambda: _boulder_img(6400 + i % 3), BOULDER_HIT)


def _ledge_img(seed):
    rnd = random.Random(seed)
    img = _canvas(64, 64)
    base = rnd.choice([(128, 124, 114), (118, 116, 108), (136, 130, 118)])
    _facet_rock(img, 32, 32, 31, 31, base, rnd, k=7, moss=False)
    for _ in range(10):          # grass / heather growing on the top
        x, y = rnd.uniform(14, 50), rnd.uniform(12, 50)
        _circle(img, x, y, rnd.uniform(1.5, 3.2), rnd.choice(HEATH_GREEN + [LICHEN]) + (255,))
    for _ in range(3):
        _circle(img, rnd.uniform(16, 48), rnd.uniform(14, 48), 1.4, rnd.choice(HEATHER) + (255,))
    return _finish(img, 64, 64)


def ledge(i):
    return _tex(f"hl_ledge_{i % 4}", lambda: _ledge_img(6500 + i % 4))


def _menhir_img(seed):
    rnd = random.Random(seed)
    img = _canvas(64, 64)
    base = (112, 110, 106)
    _facet_rock(img, 32, 32, 26, 17, base, rnd, k=8, moss=True)
    # the Titan's runes, worn into the top
    for k in range(3):
        x = 24 + k * 8
        _line(img, [(x, 26), (x + 2, 32), (x - 1, 38)], (230, 150, 70, 255), 1.6)
    return _finish(img, 64, 64)


def menhir(i):
    return _tex(f"hl_menhir_{i % 3}", lambda: _menhir_img(6600 + i % 3))


# =========================================================================== plants
def _heather_img(seed):
    rnd = random.Random(seed)
    img = _canvas(44, 44)
    _ball(img, (2, 2, 42, 42), (80, 96, 50, 255), outline=False)       # solid green base (opaque)
    for _ in range(16):
        x, y, r = rnd.uniform(9, 35), rnd.uniform(9, 35), rnd.uniform(4, 8)
        _ball(img, (x - r, y - r, x + r, y + r), rnd.choice(HEATH_GREEN) + (255,), outline=False)
    for _ in range(60):
        a, d = rnd.uniform(0, math.tau), 19 * math.sqrt(rnd.random())
        _circle(img, 22 + math.cos(a) * d, 22 + math.sin(a) * d, rnd.uniform(1.2, 2.4), rnd.choice(HEATHER) + (255,))
    return _finish(img, 44, 44)


def heather():
    return _tex("hl_heather", lambda: _heather_img(6700), [(-14, -14), (14, -14), (14, 14), (-14, 14)])


def _pine_img(seed, palette):
    """Wind-bent highland pine seen from above. The wind blows towards +x (the picture's right): the crown is
    swept that way. The whole crown area is opaque (the 3D shape drapes this picture over solid blobs)."""
    rnd = random.Random(seed)
    w = h = 132
    img = _canvas(w, h)
    c = 66
    _ball(img, (c - 62, c - 60, c + 62, c + 60), palette[0] + (255,), outline=False, soft=0.6)
    clusters = []
    for _ in range(11):
        a = rnd.uniform(-1.3, 1.3) if rnd.random() < 0.7 else rnd.uniform(0, math.tau)
        d = rnd.uniform(4, 40)
        clusters.append((c + 6 + math.cos(a) * d, c + math.sin(a) * d * 0.8, rnd.uniform(16, 26)))
    clusters.sort(key=lambda q: q[1])
    for x, y, r in clusters:
        _ball(img, (x - r * 1.25, y - r * 0.8, x + r * 1.25, y + r * 0.8), rnd.choice(palette) + (255,), soft=1.4)
    for _ in range(60):          # needle streaks, combed by the wind
        x, y = rnd.uniform(14, 112), rnd.uniform(18, 114)
        if math.hypot(x - c, y - c) > 54:
            continue
        ln = rnd.uniform(6, 14)
        _line(img, [(x, y), (x + ln, y + rnd.uniform(-1.5, 1.5))], _shade(rnd.choice(palette), 1.35) + (150,), 1.2)
    return _finish(img, w, h)


PINE_PALETTES = [
    [(46, 78, 52), (58, 92, 60), (40, 68, 46)],
    [(54, 82, 48), (70, 98, 56), (46, 72, 42)],
    [(42, 72, 60), (54, 88, 70), (36, 62, 52)],
]


def pine(i):
    return _tex(f"hl_pine_{i % 3}", lambda: _pine_img(6800 + i % 3, PINE_PALETTES[i % 3]), art.TRUNK_HIT)


# =========================================================================== the goat
def _goat_img():
    img = _canvas(64, 64)
    _shadow(img, (8, 16, 60, 56), alpha=80, blur=3)
    art_extra._quad(img, 32, (226, 220, 204), (38, 24), (170, 162, 146), (44, 25, 58, 39))
    for k in range(6):               # shaggy flank hair
        x = 18 + k * 5
        for side in (-1, 1):
            _line(img, [(x, 32 + side * 10), (x - 1, 32 + side * 14)], (200, 194, 178, 255), 1.4)
    _circle(img, 13, 32, 3, (244, 240, 228, 255))          # tail
    for side in (-1, 1):             # swept-back horns
        _line(img, [(49, 32 + side * 4), (43, 32 + side * 7), (37, 32 + side * 6)], (120, 104, 84, 255), 2.4)
    _ball(img, (55, 29, 62, 35), (196, 188, 172, 255))      # muzzle
    _circle(img, 53, 28.5, 1.3, (40, 30, 20, 255))
    _circle(img, 53, 35.5, 1.3, (40, 30, 20, 255))
    return _finish(img, 64, 64)


art_extra.ANIMAL_ART["goat"] = (_goat_img, 14)


# =========================================================================== icons
def _wool_icon(img):
    for x, y, r in ((16, 26, 10), (28, 22, 11), (24, 32, 10), (34, 30, 9)):
        _ball(img, (x - r, y - r, x + r, y + r), (232, 226, 210, 255))


def _horn_icon(img):
    _line(img, [(8, 38), (16, 26), (26, 16), (38, 12), (42, 18)], (120, 104, 84, 255), 6)
    _line(img, [(10, 36), (17, 26), (26, 18), (37, 14)], (176, 160, 130, 255), 2)
    for k in range(5):
        x, y = 12 + k * 6, 33 - k * 5
        _line(img, [(x - 2, y - 2), (x + 2, y + 2)], (84, 70, 56, 255), 1.2)


def _heather_icon(img):
    _line(img, [(24, 42), (22, 22)], (80, 96, 50, 255), 2.2)
    _line(img, [(24, 42), (14, 18)], (80, 96, 50, 255), 2)
    _line(img, [(24, 42), (32, 16)], (80, 96, 50, 255), 2)
    rnd = random.Random(5)
    for x0, y0 in ((22, 20), (14, 16), (32, 14)):
        for _ in range(7):
            _circle(img, x0 + rnd.uniform(-4, 4), y0 + rnd.uniform(-6, 6), 2.2, rnd.choice(HEATHER) + (255,))


def _cloak_icon(img):
    _poly(img, [(14, 8), (34, 8), (42, 40), (24, 44), (6, 40)], (198, 186, 160, 255), (110, 100, 80, 255), 1.4)
    _poly(img, [(18, 12), (30, 12), (34, 36), (24, 38), (14, 36)], (222, 212, 188, 200))
    for k in range(5):
        _line(img, [(8 + k * 8, 40), (9 + k * 8, 45)], (150, 86, 146, 255), 1.6)    # heather-dyed fringe
    _circle(img, 24, 11, 2.6, (150, 86, 146, 255))


def _bow_icon(img):
    _line(img, [(12, 6), (22, 14), (26, 24), (22, 34), (12, 42)], (120, 104, 84, 255), 4)
    _line(img, [(12, 6), (16, 9)], (176, 160, 130, 255), 3)
    _line(img, [(12, 42), (16, 39)], (176, 160, 130, 255), 3)
    _line(img, [(12, 6), (12, 42)], (230, 226, 210, 255), 1)
    _line(img, [(10, 24), (42, 24)], (150, 104, 62, 255), 1.6)
    _poly(img, [(42, 21), (47, 24), (42, 27)], (160, 160, 170, 255))


def _tea_icon(img):
    _poly(img, [(10, 18), (34, 18), (31, 40), (13, 40)], (176, 150, 120, 255), (100, 80, 60, 255), 1.4)
    _line(img, [(34, 22), (40, 24), (38, 32), (32, 33)], (176, 150, 120, 255), 2.4)
    ImageDraw.Draw(img).ellipse([12 * S, 16 * S, 32 * S, 22 * S], fill=(170, 96, 120, 255))
    for k in range(3):
        _line(img, [(16 + k * 6, 13), (18 + k * 6, 8), (16 + k * 6, 3)], (220, 220, 230, 150), 1.2)


art.ICON_MAKERS.update({
    "wool": _wool_icon, "goat_horn": _horn_icon, "heather": _heather_icon, "wool_cloak": _cloak_icon,
    "horn_bow": _bow_icon, "heather_tea": _tea_icon,
})
art_gear.CLOAK["wool_cloak"] = art_gear._cloak((198, 186, 160), (150, 86, 146))

# --------------------------------------------------------------------------- plug into art.tree
_prev_tree = art.tree


def _tree(i):
    return pine(i - HL_TREE) if HL_TREE <= i < HL_TREE + 3 else _prev_tree(i)


art.tree = _tree


def all_textures():
    """Used by --export-art."""
    for i in range(4):
        ground(i)
        ledge(i)
    for i in range(6):
        decor(i)
    for i in range(3):
        boulder(i)
        menhir(i)
        pine(i)
    heather()
    plateau_top()
    scree_fan()
    stone_circle()
    art_extra.animal("goat")
