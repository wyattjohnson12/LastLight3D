"""
art_hollows.py - painted-in-code art for THE CRYSTAL HOLLOWS (hollows.py), same style as art.py.

  * floor(i) / wall(i)          the deep layer's blue-violet stone (walls become 3D blocks in view3d.py)
  * spire(pal) / stalagmite(i)  top-down pictures DRAPED over the 3D shapes in hollows.py (glow_spire,
                                stalagmite): the centre of the picture colours the tip, the rim the base
  * fungus()                    the faint glowing cave fungus that lights the regular cave a little
  * starstone()                 the rare deep ore node
  * seal() / rim() / hole() / shaft_exit()   the plugged shaft in the cave that leads down
  * enemies: shard_crawler, hollow_bat, geode_golem (plugged into art_extra.enemy)
  * icons: starstone, starstone_pickaxe, star_blade, starstone_helm (+ the worn helm)
Every texture can be overridden with assets/<name>.png like the rest of the art.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
import art_extra
import art_gear
from art import S, _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shade, _shadow, _tex

# crystal palettes: (deep edge colour, body colour, light tip colour) - also the glow / light colours
PALETTES = [
    ((40, 120, 190), (90, 210, 255), (225, 250, 255)),     # ice blue
    ((90, 50, 170), (170, 120, 255), (240, 225, 255)),     # violet
    ((30, 140, 120), (90, 240, 200), (220, 255, 245)),     # sea green
    ((160, 50, 130), (255, 130, 215), (255, 230, 250)),    # rose
]


def _glow_layer(img, x, y, r, col, a=120, blur=6):
    g = _canvas(img.width // S, img.height // S)
    _circle(g, x, y, r, col + (a,))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(blur * S)))


# =========================================================================== the layer itself
def _floor_img(seed):
    rnd = random.Random(seed)
    w = 60
    img = Image.new("RGBA", (w * S, w * S), (44, 44, 62, 255))
    d = ImageDraw.Draw(img)
    for _ in range(60):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0, w), rnd.uniform(2, 7)
        v = rnd.randint(36, 60)
        d.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=(v, v + 2, v + 22, 255))
    img = img.filter(ImageFilter.GaussianBlur(1.5 * S))
    for _ in range(4):           # little crystal glints in the floor
        x, y = rnd.uniform(5, 55), rnd.uniform(5, 55)
        col = rnd.choice(PALETTES)[1]
        _poly(img, [(x, y - 2.2), (x + 1.4, y), (x, y + 2.2), (x - 1.4, y)], col + (230,))
    return _finish(img, w, w)


def floor(i):
    return _tex(f"hollows_floor_{i}", lambda: _floor_img(1600 + i))


def _wall_img(seed):
    rnd = random.Random(seed)
    w = 60
    img = _canvas(w + 12, w + 12)
    _shadow(img, (0, 4, w + 12, w + 12), alpha=150, blur=4)
    for _ in range(5):
        x, y, r = rnd.uniform(14, w - 2), rnd.uniform(14, w - 2), rnd.uniform(16, 24)
        base = rnd.choice([(66, 68, 94), (58, 60, 84), (76, 76, 104)])
        _ball(img, (x - r, y - r, x + r, y + r), base + (255,), soft=1.2)
    for _ in range(3):           # crystal seams in the rock
        x, y = rnd.uniform(16, w - 4), rnd.uniform(16, w - 4)
        col = rnd.choice(PALETTES)[1]
        _line(img, [(x, y), (x + rnd.uniform(-7, 7), y + rnd.uniform(-7, 7))], col + (220,), 1.6)
    return _finish(img, w + 12, w + 12)


def wall(i):
    return _tex(f"hollows_wall_{i}", lambda: _wall_img(1700 + i), [(-30, -30), (30, -30), (30, 30), (-30, 30)])


# =========================================================================== pictures for 3D shapes
def _spire_img(pal):
    """Top-down crystal: a hexagon, bright at the tip (centre), deep colour at the base (rim)."""
    edge, body, tip = PALETTES[pal]
    w = 48
    c = w / 2
    img = _canvas(w, w)
    for k in range(14):
        t = k / 13
        r = 23 * (1 - t) + 0.5
        col = art._lerp(edge, body, min(1, t * 1.8)) if t < 0.55 else art._lerp(body, tip, (t - 0.55) / 0.45)
        pts = [(c + math.cos(a) * r, c + math.sin(a) * r) for a in (j * math.tau / 6 + 0.5 for j in range(6))]
        _poly(img, pts, col + (255,))
    for j in range(6):           # facet edges
        a = j * math.tau / 6 + 0.5
        _line(img, [(c, c), (c + math.cos(a) * 22, c + math.sin(a) * 22)], tip + (90,), 1)
    return _finish(img, w, w)


def spire(pal):
    return _tex(f"hollows_spire_{pal}", lambda: _spire_img(pal))


def _stalagmite_img(seed):
    rnd = random.Random(seed)
    w = 40
    c = w / 2
    img = _canvas(w, w)
    base = rnd.choice([(92, 88, 104), (84, 82, 96), (100, 94, 108)])
    for k in range(10):
        t = k / 9
        r = 19 * (1 - t) + 0.6
        _circle(img, c + rnd.uniform(-1, 1), c + rnd.uniform(-1, 1), r, _shade(base, 0.7 + 0.6 * t) + (255,))
    for _ in range(5):
        a, d = rnd.uniform(0, math.tau), rnd.uniform(4, 16)
        _circle(img, c + math.cos(a) * d, c + math.sin(a) * d, 1.4, _shade(base, 0.6) + (255,))
    return _finish(img, w, w)


def stalagmite(i):
    return _tex(f"hollows_stalagmite_{i}", lambda: _stalagmite_img(1800 + i))


def _fungus_img():
    w = 28
    c = w / 2
    img = _canvas(w, w)
    for k in range(9):
        t = k / 8
        _circle(img, c, c, 13 * (1 - t) + 0.5, art._lerp((40, 120, 110), (190, 255, 230), t) + (255,))
    for a in range(6):
        aa = a * math.tau / 6
        _circle(img, c + math.cos(aa) * 7, c + math.sin(aa) * 7, 1.3, (230, 255, 245, 255))
    return _finish(img, w, w)


def fungus():
    return _tex("hollows_fungus", _fungus_img)


def _starstone_img():
    rnd = random.Random(77)
    w, h = 70, 62
    img = _canvas(w, h)
    _shadow(img, (8, 16, 68, 62), alpha=90, blur=4)
    _glow_layer(img, 35, 30, 26, (190, 170, 255), 120, 7)
    pts = []
    for k in range(9):
        a = k / 9 * math.tau
        r = rnd.uniform(22, 28)
        pts.append((35 + math.cos(a) * r, 30 + math.sin(a) * r * 0.82))
    _poly(img, pts, (34, 30, 52, 255), (14, 12, 24, 255), 1.6)
    for k in range(10):          # radial gradient towards a white-hot core (the 3D shard's tip)
        t = k / 9
        _circle(img, 35, 30, 13 * (1 - t) + 1, art._lerp((120, 90, 220), (255, 252, 255), t) + (255,))
    for _ in range(16):          # starry specks
        a, d = rnd.uniform(0, math.tau), rnd.uniform(13, 24)
        x, y = 35 + math.cos(a) * d, 30 + math.sin(a) * d * 0.8
        r = rnd.uniform(0.8, 1.8)
        _poly(img, [(x, y - r * 2), (x + r * 0.6, y), (x, y + r * 2), (x - r * 0.6, y)], (240, 236, 255, 255))
        _poly(img, [(x - r * 2, y), (x, y + r * 0.6), (x + r * 2, y), (x, y - r * 0.6)], (240, 236, 255, 255))
    return _finish(img, w, h)


def starstone():
    return _tex("hollows_starstone", _starstone_img, art.ROCK_HIT)


# --------------------------------------------------------------------------- the shaft down
def _seal_img():
    rnd = random.Random(91)
    w = 76
    c = w / 2
    img = _canvas(w, w)
    _shadow(img, (6, 10, 72, 74), alpha=110, blur=4)
    for _ in range(9):           # a heap of boulders jammed into the shaft
        a, d = rnd.uniform(0, math.tau), rnd.uniform(0, 18)
        r = rnd.uniform(10, 16)
        x, y = c + math.cos(a) * d, c + math.sin(a) * d
        _ball(img, (x - r, y - r, x + r, y + r), rnd.choice([(96, 98, 118), (84, 86, 104), (108, 106, 122)]) + (255,))
    for _ in range(7):           # crusted together by pale crystal
        x, y = rnd.uniform(16, 60), rnd.uniform(16, 60)
        pts = [(x, y)]
        for _ in range(3):
            x += rnd.uniform(-7, 7)
            y += rnd.uniform(-7, 7)
            pts.append((x, y))
        _line(img, pts, (170, 225, 255, 235), 2)
    return _finish(img, w, w)


def seal():
    return _tex("hollows_seal", _seal_img, [(-28, -28), (28, -28), (28, 28), (-28, 28)])


def _rim_img():
    """Square timber-and-stone collar around the shaft (top-down)."""
    w = 120
    img = _canvas(w, w)
    wood, dark = (122, 86, 52), (70, 48, 28)
    for k in range(4):           # four beams, overlapping at the corners
        if k % 2 == 0:
            box = (14, 14 + k // 2 * 76, 106, 30 + k // 2 * 76)
        else:
            box = (14 + k // 2 * 76, 14, 30 + k // 2 * 76, 106)
        _rrect(img, box, 2, wood + (255,), dark + (255,), 1.4)
        x0, y0, x1, y1 = box
        for j in range(1, 4):    # grain
            if k % 2 == 0:
                y = y0 + (y1 - y0) * j / 4
                _line(img, [(x0 + 4, y), (x1 - 4, y)], _shade(wood, 0.75) + (200,), 0.8)
            else:
                x = x0 + (x1 - x0) * j / 4
                _line(img, [(x, y0 + 4), (x, y1 - 4)], _shade(wood, 0.75) + (200,), 0.8)
    for x in (22, 98):           # iron corner bolts
        for y in (22, 98):
            _circle(img, x, y, 2.4, (150, 150, 160, 255), (60, 60, 70, 255))
    return _finish(img, w, w)


def rim():
    return _tex("hollows_rim", _rim_img, [(-40, -40), (40, -40), (40, 40), (-40, 40)])


def _hole_img():
    """The shaft itself, flat on the floor: blackness, ladder rungs, cold crystal light far below."""
    w = 110
    c = w / 2
    img = _canvas(w, w)
    _rrect(img, (16, 16, 94, 94), 6, (6, 8, 14, 255))
    _glow_layer(img, c, c, 22, (90, 170, 255), 200, 8)
    _glow_layer(img, c, c, 8, (210, 240, 255), 230, 3)
    for k in range(5):           # ladder rungs disappearing into the light
        y = c - 20 + k * 9
        _line(img, [(c - 11, y), (c + 11, y)], (140, 104, 66, 255 - k * 40), 2.6)
    _line(img, [(c - 11, c - 26), (c - 11, c + 22)], (110, 80, 50, 230), 2.6)
    _line(img, [(c + 11, c - 26), (c + 11, c + 22)], (110, 80, 50, 230), 2.6)
    return _finish(img, w, w)


def hole():
    return _tex("hollows_hole", _hole_img)


def shaft_exit():
    """The cave-side exit sprite: invisible (the rim, hole and seal are the look), but it has a hit box."""
    return _tex("hollows_shaft_exit", lambda: Image.new("RGBA", (8, 8), (0, 0, 0, 0)),
                [(-4, -4), (4, -4), (4, 4), (-4, 4)])


# =========================================================================== creatures (face right)
def _crawler_img():
    rnd = random.Random(5)
    img = _canvas(60, 60)
    _shadow(img, (10, 14, 54, 54), alpha=80, blur=2)
    for k in range(4):
        for side in (-1, 1):
            a = side * (0.6 + k * 0.42)
            _line(img, [(30, 30), (30 + math.cos(a) * 15, 30 + math.sin(a) * 15),
                        (30 + math.cos(a) * 24 - 4, 30 + math.sin(a) * 27)], (44, 40, 70, 255), 2.4)
    _ball(img, (15, 19, 37, 41), (62, 52, 98, 255))
    _ball(img, (33, 22, 45, 38), (82, 70, 124, 255))
    for _ in range(6):           # crystal spikes on its back
        x, y = rnd.uniform(18, 34), rnd.uniform(22, 38)
        hgt = rnd.uniform(6, 10)
        _poly(img, [(x - 3, y + 2), (x - hgt, y - 1), (x + 3, y - 2)], (130, 230, 255, 255), (60, 120, 180, 255), 0.8)
    for y in (27, 30, 33):
        _circle(img, 43, y, 1.3, (150, 240, 255, 255))
    return _finish(img, 60, 60)


def _bat_img():
    img = _canvas(64, 64)
    _shadow(img, (22, 34, 46, 50), alpha=60, blur=3)    # small and far below: it's flying
    for side in (-1, 1):         # leathery wings
        pts = [(30, 32), (24, 32 + side * 10), (14, 32 + side * 24), (22, 32 + side * 20), (28, 32 + side * 27),
               (34, 32 + side * 18), (40, 32 + side * 6)]
        _poly(img, pts, (70, 56, 92, 255), (34, 26, 48, 255), 1.2)
        _line(img, [(32, 32), (16, 32 + side * 23)], (110, 90, 140, 255), 1)
        _line(img, [(32, 32), (28, 32 + side * 26)], (110, 90, 140, 255), 1)
    _ball(img, (24, 26, 40, 38), (92, 74, 116, 255))
    _ball(img, (36, 27, 46, 37), (104, 86, 128, 255))
    for side in (-1, 1):
        _poly(img, [(40, 32 + side * 3), (46, 32 + side * 7), (42, 32 + side * 1)], (104, 86, 128, 255))
        _circle(img, 44, 32 + side * 2, 1.2, (255, 120, 220, 255))
    return _finish(img, 64, 64)


def _geode_golem_img():
    rnd = random.Random(14)
    w = 96
    img = _canvas(w, w)
    _shadow(img, (10, 16, 92, 92), alpha=110, blur=4)
    for side in (-1, 1):         # crystal-studded fists
        _ball(img, (50, 48 + side * 28 - 11, 74, 48 + side * 28 + 11), (78, 76, 98, 255))
        for _ in range(3):
            x, y = rnd.uniform(56, 70), 48 + side * 28 + rnd.uniform(-6, 6)
            _poly(img, [(x - 3, y), (x + 4, y - 3), (x + 2, y + 3)], (200, 140, 255, 255))
    _ball(img, (16, 18, 68, 78), (70, 68, 90, 255))
    # the cracked-open geode in its chest
    _glow_layer(img, 40, 48, 16, (190, 120, 255), 160, 5)
    _ball(img, (28, 36, 54, 60), (40, 20, 70, 255), outline=False)
    for k in range(10):
        a = k / 10 * math.tau
        x, y = 41 + math.cos(a) * 8, 48 + math.sin(a) * 8
        _poly(img, [(41, 48), (x + math.cos(a + 0.4) * 5, y + math.sin(a + 0.4) * 5),
                    (x + math.cos(a - 0.4) * 5, y + math.sin(a - 0.4) * 5)], (210, 160, 255, 255))
    _circle(img, 41, 48, 3, (255, 240, 255, 255))
    _ball(img, (52, 36, 72, 60), (88, 86, 108, 255))       # head
    _circle(img, 66, 43, 2.2, (220, 170, 255, 255))
    _circle(img, 66, 53, 2.2, (220, 170, 255, 255))
    return _finish(img, w, w)


ENEMY_ART = {"shard_crawler": (_crawler_img, 14), "hollow_bat": (_bat_img, 13), "geode_golem": (_geode_golem_img, 25)}
_plain_enemy = art_extra.enemy


def _enemy(kind):
    if kind in ENEMY_ART:
        maker, hb = ENEMY_ART[kind]
        return _tex(f"enemy_{kind}", maker, [(-hb, -hb), (hb, -hb), (hb, hb), (-hb, hb)])
    return _plain_enemy(kind)


art_extra.enemy = _enemy


# =========================================================================== icons
def _starstone_icon(img):
    _glow_layer(img, 24, 24, 15, (180, 160, 255), 150, 4)
    _poly(img, [(24, 4), (31, 18), (44, 24), (31, 30), (24, 44), (17, 30), (4, 24), (17, 18)],
          (226, 220, 255, 255), (110, 90, 200, 255), 1.2)
    _poly(img, [(24, 12), (28, 20), (36, 24), (28, 28), (24, 36), (20, 28), (12, 24), (20, 20)], (255, 255, 255, 255))


def _star_pick_icon(img):
    _line(img, [(4, 26), (40, 24)], (70, 60, 96, 255), 4)
    _line(img, [(8, 25.5), (14, 25.2)], (200, 190, 255, 255), 4)       # bound grip
    _glow_layer(img, 38, 22, 10, (190, 170, 255), 130, 3)
    _poly(img, [(30, 5), (40, 15), (47, 30), (40, 43), (34, 26)], (210, 200, 255, 255), (100, 80, 190, 255))
    _line(img, [(36, 12), (43, 28)], (255, 255, 255, 220), 1.2)


def _star_blade_icon(img):
    g = _canvas(48, 48)
    _line(g, [(16, 24), (46, 23)], (200, 150, 255, 200), 9)
    _line(g, [(30, 24), (46, 23)], (255, 130, 60, 160), 6)
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
    _line(img, [(4, 24), (14, 24)], (60, 50, 80, 255), 4)
    _line(img, [(14, 15), (14, 33)], (210, 200, 255, 255), 3)
    _poly(img, [(15, 20.5), (40, 20), (47, 24), (40, 28), (15, 27.5)], (228, 222, 255, 255), (110, 90, 200, 255), 1)
    _line(img, [(30, 24), (44, 24)], (255, 150, 60, 255), 1.6)         # the ember heart still burns inside
    _line(img, [(17, 22.5), (38, 22)], (255, 255, 255, 200), 1)


def _star_helm_icon(img):
    _ball(img, (8, 10, 40, 38), (112, 104, 160, 255))
    _rrect(img, (6, 30, 42, 36), 2, (78, 70, 120, 255))
    _poly(img, [(24, 2), (28, 12), (24, 22), (20, 12)], (220, 210, 255, 255), (110, 90, 200, 255), 1)   # crest shard
    _circle(img, 24, 24, 2.6, (240, 236, 255, 255))


art.ICON_MAKERS.update({"starstone": _starstone_icon, "starstone_pickaxe": _star_pick_icon,
                        "star_blade": _star_blade_icon, "starstone_helm": _star_helm_icon})
art_gear.HEAD["starstone_helm"] = art_gear._helmet((116, 108, 168), "helm")


def all_textures():
    """Used by --export-art style tools: make every texture here."""
    for i in range(3):
        floor(i)
        wall(i)
        stalagmite(i)
    for p in range(len(PALETTES)):
        spire(p)
    fungus(), starstone(), seal(), rim(), hole(), shaft_exit()
    for k in ENEMY_ART:
        _enemy(k)
