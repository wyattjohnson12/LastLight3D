"""
art_terrain.py - painted-in-code art and 3D shapes for the Riverlands (terrain.py).

Same style and assets/ override as art.py (drop e.g. assets/node_clay.png in to replace one picture).
Importing it:
  * adds item icons (art.ICON_MAKERS) and building pictures (art.STRUCTURE_ICONS: bridge, brick wall,
    stone path, farm plot and every crop growth stage)
  * adds the duck to art_extra.ANIMAL_ART (its 3D model is assets/models/duck.glb, see
    tools/blender/models/meadow.py)
  * registers the 3D shapes (shapes3d.SHAPES / VARIANTS): clay lumps, river reeds, tall grass, meadow
    grass and wildflower clumps, crops in three growth stages, a plank bridge with posts and rails,
    stone paving, tilled farm plots.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
import art_extra
import shapes3d as S3
from art import S, _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shadow, _tex

CLAY = (176, 104, 74)
WATER_DEEP = (34, 78, 96)
WHEAT = (226, 190, 96)
CARROT = (236, 128, 44)
LEAF = (86, 140, 58)


# =========================================================================== ground
def _meadow_tile(seed):
    """Lush, light meadow grass with lots of little flowers (tinted further by the biome)."""
    rnd = random.Random(seed)
    n = 256
    img = Image.new("RGBA", (n, n), (96, 140, 58, 255))
    blobs = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    palette = [(88, 132, 52), (110, 154, 64), (120, 160, 66), (92, 138, 56), (132, 156, 70)]
    for _ in range(150):
        r = rnd.randint(8, 34)
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        col = rnd.choice(palette) + (rnd.randint(60, 140),)
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                d.ellipse([x + ox - r, y + oy - r, x + ox + r, y + oy + r], fill=col)
    img.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(9)))
    d = ImageDraw.Draw(img)
    for _ in range(520):
        x, y = rnd.randint(2, n - 3), rnd.randint(4, n - 2)
        h = rnd.randint(3, 8)
        col = rnd.choice([(70, 112, 42), (132, 170, 76), (80, 120, 46), (146, 176, 84)]) + (rnd.randint(110, 200),)
        d.line([(x, y), (x + rnd.randint(-2, 2), y - h)], fill=col, width=1)
    for _ in range(rnd.randint(14, 24)):
        x, y = rnd.randint(6, n - 6), rnd.randint(6, n - 6)
        col = rnd.choice([(250, 240, 150), (248, 248, 250), (230, 150, 210), (250, 190, 90), (170, 170, 250)])
        for a in range(5):
            ang = a * math.tau / 5
            d.ellipse([x + math.cos(ang) * 2 - 1.3, y + math.sin(ang) * 2 - 1.3,
                       x + math.cos(ang) * 2 + 1.3, y + math.sin(ang) * 2 + 1.3], fill=col)
        d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(250, 200, 60))
    return img


def meadow_ground(i):
    return _tex(f"meadow_ground_{i}", lambda: _meadow_tile(7100 + i))


def _petals_img(seed):
    """A flat little patch of fallen petals / clover for the ground (decor)."""
    rnd = random.Random(seed)
    img = _canvas(30, 24)
    cols = [(250, 240, 150), (248, 248, 250), (230, 150, 210), (250, 190, 90), (170, 170, 250)]
    c = rnd.choice(cols)
    for _ in range(6):
        x, y = rnd.uniform(5, 25), rnd.uniform(5, 19)
        for a in range(5):
            ang = a * math.tau / 5
            _circle(img, x + math.cos(ang) * 1.8, y + math.sin(ang) * 1.8, 1.4, c + (255,))
        _circle(img, x, y, 0.9, (250, 200, 60, 255))
    return _finish(img, 30, 24)


def petals(i):
    return _tex(f"meadow_petals_{i}", lambda: _petals_img(7200 + i))


def _dirt_img(seed):
    """Worn ground (trampled around bases): a soft-edged patch of bare dirt."""
    rnd = random.Random(seed)
    n = 96
    img = Image.new("RGBA", (n, n), (124, 98, 66, 255))
    d = ImageDraw.Draw(img)
    for _ in range(120):
        x, y, r = rnd.uniform(0, n), rnd.uniform(0, n), rnd.uniform(1, 4)
        col = rnd.choice([(108, 84, 56), (140, 112, 78), (100, 80, 54), (150, 124, 90)]) + (160,)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    for _ in range(18):
        x, y = rnd.uniform(4, n - 4), rnd.uniform(4, n - 4)
        d.ellipse([x - 1.5, y - 1, x + 1.5, y + 1], fill=(160, 150, 136, 220))
    mask = art._radial(n).point(lambda v: 255 if v < 120 else max(0, int(255 - (v - 120) * 255 / 120)))
    img.putalpha(mask)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def dirt(i):
    return _tex(f"terrain_dirt_{i}", lambda: _dirt_img(7300 + i))


# =========================================================================== nodes
def _clay_img():
    img = _canvas(44, 36)
    _shadow(img, (6, 10, 40, 34), alpha=70, blur=2)
    for x, y, rx, ry in ((14, 18, 10, 8), (28, 20, 11, 9), (21, 12, 8, 6), (24, 27, 7, 5)):
        _ball(img, (x - rx, y - ry, x + rx, y + ry), CLAY + (255,))
    for x, y in ((12, 15), (27, 17), (20, 10)):
        _circle(img, x, y, 1.4, (214, 150, 120, 255))
    return _finish(img, 44, 36)


def clay():
    return _tex("node_clay", _clay_img, [(-15, -12), (15, -12), (15, 12), (-15, 12)])


def _blades_img(w, colors, n, seed, heads=None):
    """A clump of blades painted from above (radial strokes) - the fallback picture; the 3D shape
    uses plain colours."""
    rnd = random.Random(seed)
    img = _canvas(w, w)
    c = w / 2
    _shadow(img, (c - w * 0.3, c - w * 0.22, c + w * 0.3, c + w * 0.32), alpha=60, blur=2)
    for _ in range(n):
        a = rnd.uniform(0, math.tau)
        ln = rnd.uniform(0.25, 0.46) * w
        _line(img, [(c, c), (c + math.cos(a) * ln, c + math.sin(a) * ln)], rnd.choice(colors) + (255,), 1.8)
    for a in range(heads or 0):
        ang = rnd.uniform(0, math.tau)
        ln = rnd.uniform(0.25, 0.4) * w
        _circle(img, c + math.cos(ang) * ln, c + math.sin(ang) * ln, 2.2, (120, 76, 40, 255))
    return _finish(img, w, w)


REED_COLS = ((96, 128, 56), (120, 144, 64), (150, 150, 76), (80, 116, 50))
GRASS_COLS = ((118, 156, 66), (140, 170, 76), (170, 178, 92), (100, 140, 56))


def river_reeds():
    return _tex("node_river_reeds", lambda: _blades_img(40, REED_COLS, 16, 7401, 3),
                [(-8, -8), (8, -8), (8, 8), (-8, 8)])


def tall_grass():
    return _tex("node_tall_grass", lambda: _blades_img(44, GRASS_COLS, 20, 7402),
                [(-8, -8), (8, -8), (8, 8), (-8, 8)])


def deco_grass():
    return _tex("deco_meadow_grass", lambda: _blades_img(30, GRASS_COLS, 12, 7403))


FLOWER_COLS = [(250, 236, 120), (246, 246, 250), (226, 120, 200), (250, 170, 70), (150, 150, 250)]


def _flower_img(i):
    rnd = random.Random(7410 + i)
    img = _canvas(30, 30)
    for _ in range(8):
        a = rnd.uniform(0, math.tau)
        _line(img, [(15, 15), (15 + math.cos(a) * 11, 15 + math.sin(a) * 11)], (90, 140, 60, 255), 1.6)
    for _ in range(5):
        a, d = rnd.uniform(0, math.tau), rnd.uniform(3, 10)
        _circle(img, 15 + math.cos(a) * d, 15 + math.sin(a) * d, 2.6, FLOWER_COLS[i % len(FLOWER_COLS)] + (255,))
    return _finish(img, 30, 30)


def wildflower(i):
    return _tex(f"deco_flower_{i}", lambda: _flower_img(i))


# =========================================================================== buildings
def _brick_wall_img():
    img = _canvas(40, 40)
    _rrect(img, (0.5, 0.5, 39.5, 39.5), 2, (150, 78, 58, 255), (90, 44, 32, 255), 1.2)
    for row in range(5):
        y = 1 + row * 7.8
        off = 0 if row % 2 else 6
        for k in range(-1, 4):
            x = off + k * 12
            x0, x1 = max(1.5, x + 1), min(38.5, x + 11)
            if x1 - x0 > 2:
                col = (172 + (k * 7 + row * 13) % 24, 88 + (k * 5) % 16, 64, 255)
                _rrect(img, (x0, y + 0.8, x1, y + 6.8), 1, col)
    return _finish(img, 40, 40)


def brick_wall():
    return _tex("build_brick_wall", _brick_wall_img, art.BLOCK_HIT)


def _bridge_img():
    """Planks across, a rail along the top and bottom edge (the 3D shape adds posts and rails)."""
    img = _canvas(80, 80)
    for k in range(10):
        x = 1 + k * 7.8
        col = (150 + (k * 37) % 26, 108 + (k * 23) % 18, 66, 255)
        _rrect(img, (x, 8, x + 7.2, 72), 1, col, (96, 66, 38, 255), 0.8)
        _circle(img, x + 3.6, 12, 0.8, (70, 50, 30, 255))
        _circle(img, x + 3.6, 68, 0.8, (70, 50, 30, 255))
    for y in (3, 72):
        _rrect(img, (0.5, y, 79.5, y + 5), 1.5, (120, 82, 46, 255), (80, 54, 30, 255), 0.8)
    return _finish(img, 80, 80)


def bridge():
    return _tex("build_bridge", _bridge_img, [(-38, -38), (38, -38), (38, 38), (-38, 38)])


def _stone_path_img():
    rnd = random.Random(7501)
    img = _canvas(40, 40)
    _rrect(img, (0, 0, 40, 40), 2, (110, 104, 92, 255))
    for x, y, w, h in ((1, 1, 18, 13), (20, 1, 19, 17), (1, 15, 13, 24), (15, 19, 24, 20), (15, 15, 4, 3)):
        g = rnd.randint(150, 180)
        _rrect(img, (x + 0.6, y + 0.6, x + w - 0.6, y + h - 0.6), 3, (g, g - 4, g - 14, 255), (100, 96, 88, 255), 0.7)
    return _finish(img, 40, 40)


def stone_path():
    return _tex("build_stone_path", _stone_path_img, art.BLOCK_HIT)


def _plot_img():
    img = _canvas(40, 40)
    _rrect(img, (1, 1, 39, 39), 4, (104, 74, 48, 255), (74, 52, 34, 255), 1)
    for k in range(4):
        y = 6 + k * 9.3
        _rrect(img, (3, y - 2.6, 37, y + 2.6), 2.5, (126, 92, 60, 255))
        _line(img, [(4, y + 2.4), (36, y + 2.4)], (82, 58, 38, 255), 0.8)
    return _finish(img, 40, 40)


def farm_plot():
    return _tex("build_farm_plot", _plot_img, art.BLOCK_HIT)


def _crop_img(crop, stage):
    img = _canvas(40, 40)
    _rrect(img, (1, 1, 39, 39), 4, (104, 74, 48, 255), (74, 52, 34, 255), 1)
    rnd = random.Random(f"{crop}{stage}")
    for row in range(3):
        y = 8 + row * 12
        for col in range(3):
            x = 8 + col * 12
            if crop == "berry":
                r = 3 + stage * 3
                _ball(img, (20 - r, 20 - r, 20 + r, 20 + r), (70, 120, 50, 255))
                if stage == 3:
                    for _ in range(8):
                        a, d = rnd.uniform(0, math.tau), rnd.uniform(2, r - 2)
                        _circle(img, 20 + math.cos(a) * d, 20 + math.sin(a) * d, 1.6, (200, 40, 70, 255))
                return _finish(img, 40, 40)
            ln = 2 + stage * 2.5
            leaf = (120, 160, 60) if crop == "carrot" else ((200, 180, 90) if stage == 3 else (110, 160, 64))
            for a in range(5):
                ang = a * math.tau / 5 + row
                _line(img, [(x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln)], leaf + (255,), 1.4)
            if stage == 3:
                _circle(img, x, y, 2.2, (CARROT if crop == "carrot" else WHEAT) + (255,))
    return _finish(img, 40, 40)


def crop(crop, stage):
    return _tex(f"build_{crop}_{stage}", lambda: _crop_img(crop, stage), art.BLOCK_HIT)


# =========================================================================== creatures
def _duck_img():
    img = _canvas(40, 40)
    _shadow(img, (8, 12, 34, 32), alpha=70, blur=2)
    _ball(img, (8, 12, 30, 28), (150, 132, 108, 255))
    for side in (-1, 1):
        _ball(img, (11, 20 + side * 5 - 3, 25, 20 + side * 5 + 3), (128, 112, 92, 255), outline=False)
        _rrect(img, (15, 20 + side * 6 - 1, 20, 20 + side * 6 + 1), 0.5, (60, 90, 200, 255))
    _circle(img, 27, 20, 4.2, (240, 240, 236, 255))
    _ball(img, (25, 15, 35, 25), (40, 110, 70, 255))
    _poly(img, [(34, 18), (39, 19), (39, 21), (34, 22)], (236, 180, 50, 255))
    _circle(img, 31, 17.5, 0.9, (20, 20, 20, 255))
    _circle(img, 31, 22.5, 0.9, (20, 20, 20, 255))
    return _finish(img, 40, 40)


def _fish_img(back=(92, 110, 96)):
    img = _canvas(32, 16)
    _ball(img, (5, 4, 26, 12), back + (255,), outline=False)
    _poly(img, [(6, 8), (1, 3), (2, 8), (1, 13)], back + (255,))
    _circle(img, 23, 7, 0.8, (20, 20, 20, 255))
    return _finish(img, 32, 16)


def fish_shadow(i=0):
    return _tex(f"fish_shadow_{i}", lambda: _fish_img([(60, 70, 66), (72, 80, 50), (200, 120, 50)][i]))


def _bobber_img():
    img = _canvas(14, 14)
    _ball(img, (2, 2, 12, 12), (236, 70, 60, 255))
    _rrect(img, (2, 6.2, 12, 7.8), 0.5, (250, 250, 250, 255))
    return _finish(img, 14, 14)


def bobber():
    return _tex("fish_bobber", _bobber_img)


def _ripple_img():
    img = _canvas(40, 40)
    ImageDraw.Draw(img).ellipse([4 * S, 4 * S, 36 * S, 36 * S], outline=(230, 245, 255, 220), width=int(1.6 * S))
    return _finish(img, 40, 40)


def ripple():
    return _tex("fish_ripple", _ripple_img)


art_extra.ANIMAL_ART["duck"] = (_duck_img, 11)

# =========================================================================== item icons
def _clay_icon(img):
    _ball(img, (8, 14, 40, 40), CLAY + (255,))
    _circle(img, 18, 22, 2.5, (214, 150, 120, 255))


def _brick_icon(img):
    _poly(img, [(6, 22), (30, 12), (42, 20), (18, 30)], (196, 110, 82, 255), (120, 60, 44, 255))
    _poly(img, [(6, 22), (18, 30), (18, 40), (6, 32)], (150, 78, 58, 255), (110, 54, 40, 255))
    _poly(img, [(18, 30), (42, 20), (42, 30), (18, 40)], (170, 90, 66, 255), (110, 54, 40, 255))


def _fish_icon(img, cooked=False):
    back = (170, 110, 60) if cooked else (92, 110, 96)
    _ball(img, (8, 16, 38, 32), back + (255,))
    _poly(img, [(10, 24), (2, 14), (4, 24), (2, 34)], back + (255,), (50, 50, 40, 255))
    _circle(img, 33, 22, 1.6, (20, 20, 20, 255))
    if cooked:
        for x in (16, 22, 28):
            _line(img, [(x, 18), (x - 3, 30)], (100, 56, 30, 255), 1.6)
    else:
        _ball(img, (12, 24, 34, 31), (226, 214, 190, 255), outline=False)


def _feather_icon(img):
    _line(img, [(10, 40), (36, 8)], (200, 190, 170, 255), 1.6)
    _poly(img, [(14, 34), (22, 16), (36, 8), (30, 24)], (120, 110, 96, 255), (80, 70, 60, 255))
    _poly(img, [(22, 26), (34, 12), (32, 18)], (60, 90, 200, 255))


def _wheat_icon(img):
    for k, x in enumerate((16, 24, 32)):
        _line(img, [(24, 44), (x, 10)], (190, 160, 80, 255), 1.6)
        for j in range(4):
            yy = 12 + j * 5
            xx = 24 + (x - 24) * (1 - (yy - 10) / 34)
            _ball(img, (xx - 3, yy - 2.5, xx + 3, yy + 2.5), WHEAT + (255,), outline=False)


def _bread_icon(img):
    _ball(img, (6, 14, 42, 38), (200, 140, 70, 255))
    for x in (16, 24, 32):
        _line(img, [(x - 3, 20), (x + 3, 30)], (240, 210, 150, 255), 2)


def _carrot_icon(img):
    _poly(img, [(14, 16), (30, 14), (24, 44)], CARROT + (255,), (160, 80, 30, 255))
    for x in (17, 22, 27):
        _line(img, [(22, 15), (x, 3)], LEAF + (255,), 2.4)


def _seeds_icon(img, col):
    rnd = random.Random(sum(col))
    _poly(img, [(10, 16), (38, 16), (34, 42), (14, 42)], (190, 160, 110, 255), (120, 96, 60, 255))
    _line(img, [(10, 16), (38, 16)], (140, 110, 70, 255), 2)
    for _ in range(7):
        x, y = rnd.uniform(15, 33), rnd.uniform(9, 17)
        _ball(img, (x - 2, y - 1.5, x + 2, y + 1.5), col + (255,), outline=False)


def _sapling_icon(img):
    _rrect(img, (14, 30, 34, 44), 3, (150, 90, 60, 255), (100, 60, 40, 255))
    _ball(img, (10, 8, 38, 34), (70, 130, 60, 255))
    for x, y in ((18, 18), (28, 16), (24, 26)):
        _circle(img, x, y, 2.4, (200, 40, 70, 255))


def _rod_icon(img):
    _line(img, [(6, 42), (40, 6)], (130, 90, 50, 255), 2.6)
    _line(img, [(40, 6), (42, 30)], (230, 230, 230, 200), 0.8)
    _circle(img, 42, 31, 2.6, (236, 70, 60, 255))
    _circle(img, 12, 36, 3.6, (90, 90, 96, 255))


def _hoe_icon(img):
    _line(img, [(8, 42), (34, 10)], (130, 90, 50, 255), 3)
    _poly(img, [(30, 8), (42, 6), (44, 16), (36, 14)], (150, 150, 156, 255), (80, 80, 86, 255))


def _stew_icon(img):
    _ball(img, (6, 18, 42, 42), (110, 80, 60, 255))
    _ball(img, (10, 18, 38, 30), (210, 140, 70, 255), outline=False)
    for x, y, c in ((16, 23, CARROT), (26, 22, (236, 236, 220)), (31, 25, CARROT)):
        _circle(img, x, y, 2.2, c + (255,))


art.ICON_MAKERS.update({
    "clay": _clay_icon, "brick": _brick_icon, "raw_fish": _fish_icon,
    "cooked_fish": lambda img: _fish_icon(img, True), "feather": _feather_icon, "wheat": _wheat_icon,
    "bread": _bread_icon, "carrot": _carrot_icon, "wheat_seeds": lambda img: _seeds_icon(img, (210, 180, 100)),
    "carrot_seeds": lambda img: _seeds_icon(img, (120, 90, 60)), "berry_sapling": _sapling_icon,
    "fishing_rod": _rod_icon, "hoe": _hoe_icon, "river_stew": _stew_icon,
})
art.STRUCTURE_ICONS.update({"brick_wall": brick_wall, "bridge": bridge, "stone_path": stone_path,
                            "farm_plot": farm_plot})
for _c in ("wheat", "carrot", "berry"):
    for _s in (1, 2, 3):
        art.STRUCTURE_ICONS[f"{_c}_{_s}"] = (lambda c, s: lambda: crop(c, s))(_c, _s)


# =========================================================================== 3D shapes (shapes3d.py)
def _register_shapes():
    Part, Shape, Fill = S3.Part, S3.Shape, S3.Fill
    ball, tube, cone = S3.ball, S3.tube, S3.cone
    SH = S3.SHAPES

    # clay: a few rounded wet lumps, the picture draped on (the gaps between lumps filled)
    lumps = []
    for x, y, r, h in ((-0.35, -0.1, 0.55, 0.42), (0.38, 0.05, 0.6, 0.48), (0.0, 0.42, 0.45, 0.36),
                       (0.05, -0.45, 0.4, 0.3)):
        lumps.append(Part(ball(3), at=(x, y, 0.0), size=(r, r * 0.9, h), color=Fill(0.5 + x * 0.4, 0.5 - y * 0.4),
                          sides=7, jitter=0.18))
    SH["clay"] = Shape(lumps, foot=(1.0, 1.0), cut=0.2)

    SH["river_reeds"] = S3.blade_clump(n=14, height=2.6, spread=0.45, cattails=3, seed=7401, colors=REED_COLS)
    SH["tall_grass"] = S3.blade_clump(n=18, height=1.7, spread=0.55, seed=7402, sway=0.45, colors=GRASS_COLS,
                                      width=0.07)
    SH["meadow_grass"] = S3.blade_clump(n=9, height=1.5, spread=0.5, seed=7403, sway=0.5, colors=GRASS_COLS,
                                        width=0.08)
    # wildflowers: stems with a little round flower head on each, five colours (VARIANTS by sprite.variant)
    for i, col in enumerate(FLOWER_COLS):
        rnd = random.Random(7410 + i)
        parts = []
        for k in range(7):
            a, d = rnd.uniform(0, math.tau), 0.45 * math.sqrt(rnd.random())
            h = rnd.uniform(0.9, 1.5)
            lean = rnd.uniform(0.05, 0.3)
            at = (math.cos(a) * d, math.sin(a) * d, 0.0)
            tl, rl = math.cos(a) * lean, math.sin(a) * lean
            parts.append(Part(tube(0.035, 0.025, h), at=at, tilt=tl, roll=rl, color=(86, 136, 58), sides=3, sway=0.4))
            head = [(0.0, h - 0.05, 0.0, 0.8), (0.17, h + 0.02, 0.17, 1.0), (0.12, h + 0.08, 0.12, 1.1),
                    (0.0, h + 0.1, 0.0, 1.15)]          # a flat flower head on top of its stem
            parts.append(Part(head, at=at, tilt=tl, roll=rl, color=col, sides=5, sway=0.4))
        for k in range(5):      # leaves at the foot
            a = k * math.tau / 5 + rnd.uniform(-0.3, 0.3)
            parts.append(Part(cone(0.07, 0.6), at=(math.cos(a) * 0.12, math.sin(a) * 0.12, 0), tilt=math.cos(a) * 0.9,
                              roll=math.sin(a) * 0.9, color=(96, 146, 62), sides=3, sway=0.3, detail=True))
        SH[f"wildflower_{i}"] = Shape(parts, foot=(1.0, 1.0))
    S3.VARIANTS["wildflower"] = lambda s: f"wildflower_{s.variant % len(FLOWER_COLS)}"

    # crops: three growth stages each (the stage is the building's kind: wheat_1 .. wheat_3)
    soil = Part([(1.0, 0.0, 0, 0.6), (1.0, 0.1, 0, 0.8), (0.0, 0.1, 0, 0.85)], size=(1.3, 1.3, 1.0),
                color=(112, 80, 52), sides=4)

    def rows(height, n, colors, heads=0, head=WHEAT, width=0.05, seed=1):
        """Three rows of little clumps on a soil bed."""
        rnd = random.Random(seed)
        parts = [soil]
        for rx in (-0.55, 0.0, 0.55):
            for ry in (-0.5, 0.0, 0.5):
                for k in range(n):
                    a = rnd.uniform(0, math.tau)
                    lean = rnd.uniform(0.1, 0.45)
                    h = height * rnd.uniform(0.7, 1.0)
                    parts.append(Part(cone(width, h), at=(rx + rnd.uniform(-0.06, 0.06), ry + rnd.uniform(-0.06, 0.06), 0.08),
                                      tilt=math.cos(a) * lean, roll=math.sin(a) * lean, color=rnd.choice(colors),
                                      sides=3, sway=0.3))
                if heads:
                    a = rnd.uniform(0, math.tau)
                    parts.append(Part(tube(0.07, 0.06, height * 0.35, z0=height * 0.75, caps=True)
                                      + [(0.0, height * 1.15, 0.0, 1.0)], at=(rx, ry, 0.08),
                                      tilt=math.cos(a) * 0.15, roll=math.sin(a) * 0.15, color=head, sides=4, sway=0.3))
        return Shape(parts, foot=(1.0, 1.0))

    greens = ((110, 160, 64), (96, 146, 58), (130, 170, 72))
    SH["wheat_1"] = rows(0.5, 2, greens, seed=1)
    SH["wheat_2"] = rows(1.1, 3, greens, seed=2)
    SH["wheat_3"] = rows(1.5, 3, ((206, 178, 92), (190, 160, 80), (220, 196, 110)), heads=1, head=WHEAT, seed=3)
    SH["carrot_1"] = rows(0.4, 2, greens, seed=4, width=0.06)
    SH["carrot_2"] = rows(0.8, 3, greens, seed=5, width=0.07)
    c3 = rows(0.9, 3, ((90, 150, 56), (110, 166, 66)), seed=6, width=0.07)
    c3_parts = list(c3.parts)
    for rx in (-0.55, 0.0, 0.55):        # orange carrot shoulders poking out of the soil
        for ry in (-0.5, 0.0, 0.5):
            c3_parts.append(Part(tube(0.13, 0.1, 0.16, z0=0.0, caps=True), at=(rx, ry, 0.0), color=CARROT, sides=5))
    SH["carrot_3"] = Shape(c3_parts, foot=(1.0, 1.0))
    for st, (h, r) in ((1, (0.55, 0.3)), (2, (0.95, 0.55)), (3, (1.25, 0.78))):
        parts = [soil, Part(tube(0.06, 0.04, h * 0.5), color=(110, 80, 50), sides=4),
                 Part(ball(4), at=(0, 0, h * 0.6), size=(r, r, r * 0.8), color=Fill(0.5, 0.5), sides=7, jitter=0.15,
                      sway=0.08)]
        if st == 3:
            rnd = random.Random(77)
            for k in range(9):
                a = rnd.uniform(0, math.tau)
                parts.append(Part(ball(2), at=(math.cos(a) * r * 0.85, math.sin(a) * r * 0.85, h * 0.6 + rnd.uniform(-0.2, 0.3)),
                                  size=(0.09, 0.09, 0.09), color=(200, 40, 70), sides=4, detail=True))
        SH[f"berry_{st}"] = Shape(parts, foot=(1.0, 1.0))

    # tilled farm plot and stone paving: low slabs with the picture on top
    SH["farm_plot"] = S3.box_prop(0.18, sides_col=(92, 64, 40))
    SH["stone_path"] = S3.box_prop(0.1, sides_col=(118, 114, 104))
    # bridge: plank deck, posts and two rails along the long sides (sprite x = along the bridge)
    wood, dark = (138, 96, 56), (104, 70, 40)
    deck = [Part([(1.0, 0.0, 0, 0.55), (1.0, 0.2, 0, 0.8)], size=(1.414, 1.414, 1.0), color=dark, sides=4),
            Part([(1.0, 0.2, 1.0, 0.95), (0.0, 0.2, 0.0, 1.0)], size=(1.414, 1.414, 1.0), sides=4)]
    rail = []
    for y in (-0.9, 0.9):
        for x in (-0.94, -0.31, 0.31, 0.94):
            rail.append(Part(tube(0.07, 0.06, 0.8, caps=True), at=(x, y, 0.15), color=wood, sides=4))
        rail.append(Part(tube(0.06, 0.06, 1.95, caps=True), at=(-0.97, y, 0.88), tilt=math.pi / 2, color=wood, sides=4))
        rail.append(Part(tube(0.04, 0.04, 1.95), at=(-0.97, y, 0.5), tilt=math.pi / 2, color=dark, sides=3,
                         detail=True))
    SH["bridge"] = Shape(deck + rail, foot=(1.0, 1.0), turn=math.pi / 4, cut=0.1)
    SH["world_bridge"] = SH["bridge"]


_register_shapes()


def all_textures():
    """Used by --export-art."""
    for i in range(3):
        meadow_ground(i)
        dirt(i)
        petals(i)
        fish_shadow(i)
    for i in range(len(FLOWER_COLS)):
        wildflower(i)
    clay(), river_reeds(), tall_grass(), deco_grass(), brick_wall(), bridge(), stone_path(), farm_plot()
    bobber(), ripple()
    for c in ("wheat", "carrot", "berry"):
        for s in (1, 2, 3):
            crop(c, s)
    art_extra.animal("duck")
