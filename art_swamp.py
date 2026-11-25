"""
art_swamp.py - painted-in-code art for the Mire (the swamp biome) and its boss, the Mire Lurker.

Same style and same assets/ override as art.py (drop e.g. assets/boss_mire.png in to replace one).
Importing this module plugs the new pictures into the existing art functions:
  * art.tree(i) for i >= SWAMP_TREE draws a swamp tree (so chopped swamp trees regrow as swamp trees)
  * art_extra.enemy("drowned") is the Drowned zombie
  * art_extra.boss("mire") is the Mire Lurker
  * art.icon(...) knows the new item icons, art_gear.gear("mire_mask") the worn mask
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
import art_extra
import art_gear
from art import S, _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shade, _shadow, _tex

SWAMP_TREE = 10          # tree variants from here up are swamp trees (10, 11 = willows, 12 = dead tree)

MUD = (64, 70, 44)
MOSS = (84, 104, 50)
MURK = (40, 58, 50)


# =========================================================================== ground
def _ground_img(seed):
    """A big soft-edged patch of bog: mud, moss and dark puddles. Overlapping patches make the swamp."""
    rnd = random.Random(seed)
    n = 512
    img = Image.new("RGBA", (n, n), MUD + (255,))
    blobs = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    palette = [(56, 62, 40), (74, 80, 48), (80, 70, 46), (66, 84, 46), (50, 58, 44)]
    for _ in range(240):
        r = rnd.randint(10, 46)
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice(palette) + (rnd.randint(70, 150),))
    img.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    for _ in range(26):       # dark standing water
        x, y = rnd.randint(40, n - 40), rnd.randint(40, n - 40)
        rx, ry = rnd.randint(8, 26), rnd.randint(5, 14)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=MURK + (200,))
        d.arc([x - rx + 3, y - ry + 2, x + rx - 3, y + ry - 2], 200, 320, fill=(110, 130, 110, 140), width=1)
    for _ in range(700):      # moss & sedge strokes
        x, y = rnd.randint(2, n - 3), rnd.randint(4, n - 2)
        h = rnd.randint(2, 6)
        col = rnd.choice([(96, 116, 56), (58, 76, 38), (120, 128, 66), (72, 92, 44)]) + (rnd.randint(110, 200),)
        d.line([(x, y), (x + rnd.randint(-2, 2), y - h)], fill=col, width=1)
    # soft, ragged edge so patches melt into the grass around them
    mask = art._radial(n).point(lambda v: 255 if v < 150 else max(0, int(255 - (v - 150) * 255 / 100)))
    rag = Image.new("L", (n, n), 0)
    dr = ImageDraw.Draw(rag)
    for _ in range(40):
        a = rnd.uniform(0, math.tau)
        rr = rnd.uniform(0.32, 0.46) * n
        x, y = n / 2 + math.cos(a) * rr, n / 2 + math.sin(a) * rr
        s = rnd.uniform(20, 50)
        dr.ellipse([x - s, y - s, x + s, y + s], fill=255)
    rag = rag.filter(ImageFilter.GaussianBlur(14))
    mask = Image.composite(Image.new("L", (n, n), 255), mask, rag.point(lambda v: min(255, v * 2)))
    mask = Image.composite(mask, Image.new("L", (n, n), 0), art._radial(n).point(lambda v: 255 if v < 250 else 0))
    img.putalpha(mask)
    return img


def ground(i):
    return _tex(f"swamp_ground_{i}", lambda: _ground_img(4400 + i))


def _pool_img(seed):
    rnd = random.Random(seed)
    w, h = 190, 130
    img = _canvas(w, h)
    _ball(img, (4, 6, w - 4, h - 4), (70, 62, 40, 255), outline=False, soft=2.2)            # muddy rim
    layer = _canvas(w, h)
    _ball(layer, (16, 16, w - 16, h - 16), (44, 66, 54, 255), light=(0.2, 0.25), outline=False, soft=2.4)
    img.alpha_composite(layer)
    d = ImageDraw.Draw(img)
    d.ellipse([16 * S, 16 * S, (w - 16) * S, (h - 16) * S], outline=(30, 44, 34, 255), width=2 * S)
    for _ in range(9):        # green scum
        x, y = rnd.uniform(40, w - 40), rnd.uniform(34, h - 34)
        r = rnd.uniform(5, 13)
        _circle(img, x, y, r, (96, 128, 56, 150))
    for _ in range(5):        # lily pads
        x, y = rnd.uniform(36, w - 36), rnd.uniform(30, h - 30)
        d.pieslice([(x - 8) * S, (y - 8) * S, (x + 8) * S, (y + 8) * S], 30, 340, fill=(70, 122, 54, 255))
    for _ in range(4):        # bubbles
        x, y = rnd.uniform(40, w - 40), rnd.uniform(34, h - 34)
        _circle(img, x, y, rnd.uniform(1.5, 3), (150, 170, 140, 170), (200, 220, 190, 200), 0.6)
    return _finish(img, w, h)


def pool(i):
    return _tex(f"swamp_pool_{i}", lambda: _pool_img(4500 + i))


def _lily_img(seed):
    rnd = random.Random(seed)
    img = _canvas(40, 30)
    d = ImageDraw.Draw(img)
    for _ in range(3):
        x, y, r = rnd.uniform(9, 31), rnd.uniform(8, 22), rnd.uniform(4, 7)
        a = rnd.uniform(0, 360)
        d.pieslice([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], a, a + 310, fill=(74, 126, 58, 255))
    if rnd.random() < 0.6:
        _circle(img, rnd.uniform(12, 28), rnd.uniform(10, 20), 2.6, (240, 200, 230, 255), (200, 140, 190, 255), 0.6)
    return _finish(img, 40, 30)


def _sedge_img(seed):
    rnd = random.Random(seed)
    img = _canvas(30, 24)
    for _ in range(10):
        x = rnd.uniform(6, 24)
        _line(img, [(x, 22), (x + rnd.uniform(-5, 5), 22 - rnd.uniform(8, 16))],
              rnd.choice([(92, 104, 52), (124, 120, 64), (70, 86, 42)]) + (255,), 1.4)
    return _finish(img, 30, 24)


def decor(i):
    """Flat bits scattered on the bog: lily pads (even) and sedge tufts (odd)."""
    if i % 2 == 0:
        return _tex(f"swamp_lily_{i}", lambda: _lily_img(4600 + i))
    return _tex(f"swamp_sedge_{i}", lambda: _sedge_img(4600 + i))


# =========================================================================== nature
def _willow_img(seed, palette):
    rnd = random.Random(seed)
    w = h = 150
    img = _canvas(w, h)
    _shadow(img, (28, 40, 142, 142), alpha=100, blur=6)
    _ball(img, (64, 64, 86, 86), (70, 56, 40, 255))
    clusters = []
    for _ in range(8):
        a = rnd.uniform(0, math.tau)
        dd = rnd.uniform(8, 32)
        clusters.append((75 + math.cos(a) * dd, 72 + math.sin(a) * dd * 0.8, rnd.uniform(22, 32)))
    clusters.sort(key=lambda c: c[1])
    for cx, cy, r in clusters:
        _ball(img, (cx - r, cy - r, cx + r, cy + r), rnd.choice(palette) + (255,), soft=1.6)
    for _ in range(46):       # hanging moss: drooping strands
        x = rnd.uniform(36, 114)
        y = rnd.uniform(52, 104)
        ln = rnd.uniform(10, 24)
        col = rnd.choice([(150, 160, 112), (128, 140, 96), (170, 176, 130)]) + (230,)
        _line(img, [(x, y), (x + rnd.uniform(-2, 2), y + ln * 0.5), (x + rnd.uniform(-3, 3), y + ln)], col, 1.2)
    for _ in range(10):
        _circle(img, rnd.uniform(44, 106), rnd.uniform(36, 96), rnd.uniform(2, 3.5), _shade(palette[0], 1.4) + (110,))
    return _finish(img, w, h)


def _dead_tree_img(seed):
    rnd = random.Random(seed)
    w = h = 150
    img = _canvas(w, h)
    _shadow(img, (40, 50, 130, 130), alpha=80, blur=6)
    bark = (92, 84, 70)

    def branch(x, y, a, ln, wd, depth):
        x2, y2 = x + math.cos(a) * ln, y + math.sin(a) * ln
        _line(img, [(x, y), ((x + x2) / 2 + rnd.uniform(-4, 4), (y + y2) / 2 + rnd.uniform(-4, 4)), (x2, y2)],
              _shade(bark, 0.9 + depth * 0.08) + (255,), wd)
        if depth < 3:
            for k in (-1, 1):
                branch(x2, y2, a + k * rnd.uniform(0.3, 0.7), ln * rnd.uniform(0.55, 0.75), max(1.2, wd * 0.6),
                       depth + 1)
        elif rnd.random() < 0.6:    # moss hanging off the twig tips
            _line(img, [(x2, y2), (x2 + rnd.uniform(-2, 2), y2 + rnd.uniform(8, 16))], (150, 160, 112, 220), 1.2)

    for k in range(5):
        branch(75, 75, k / 5 * math.tau + rnd.uniform(-0.3, 0.3), rnd.uniform(22, 30), 5, 0)
    _ball(img, (62, 62, 88, 88), bark + (255,))
    _circle(img, 75, 75, 5, (60, 52, 42, 255))
    return _finish(img, w, h)


SWAMP_PALETTES = [
    [(62, 88, 52), (76, 100, 58), (54, 78, 50)],
    [(72, 92, 42), (88, 104, 50), (60, 80, 40)],
]


def swamp_tree(i):
    if i % 3 == 2:
        return _tex("swamp_tree_dead", lambda: _dead_tree_img(4700), art.TRUNK_HIT)
    return _tex(f"swamp_tree_{i % 3}", lambda: _willow_img(4710 + i % 3, SWAMP_PALETTES[i % 3]), art.TRUNK_HIT)


def _reeds_img():
    rnd = random.Random(4800)
    w, h = 50, 62
    img = _canvas(w, h)
    for _ in range(16):         # tall blades, drawn from the ground up (they stand up in 3D)
        x = rnd.uniform(10, 40)
        top = rnd.uniform(6, 30)
        col = rnd.choice([(96, 128, 56), (120, 144, 64), (150, 150, 76), (80, 110, 48)]) + (255,)
        _line(img, [(x, h - 2), (x + rnd.uniform(-3, 3), (h + top) / 2), (x + rnd.uniform(-6, 6), top)], col, 1.6)
    for _ in range(5):          # cattails
        x = rnd.uniform(14, 36)
        y = rnd.uniform(8, 22)
        _line(img, [(x, h - 2), (x, y + 6)], (110, 130, 60, 255), 1.4)
        _rrect(img, (x - 2.4, y, x + 2.4, y + 10), 2.4, (110, 72, 40, 255), (70, 44, 24, 255), 0.6)
        _line(img, [(x, y), (x, y - 4)], (150, 150, 90, 255), 0.8)
    return _finish(img, w, h)


def reeds():
    return _tex("swamp_reeds", _reeds_img, [(-10, -8), (10, -8), (10, 8), (-10, 8)])


def _glowcap_img():
    rnd = random.Random(4900)
    w, h = 46, 44
    img = _canvas(w, h)
    g = _canvas(w, h)
    _circle(g, 23, 20, 17, (120, 255, 210, 120))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(4 * S)))
    for x, top, r in [(14, 18, 7), (30, 12, 9), (23, 24, 6), (36, 24, 5)]:
        _line(img, [(x, h - 2), (x + rnd.uniform(-1, 1), top + 2)], (214, 220, 196, 255), 2.4)
        _ball(img, (x - r, top - r * 0.7, x + r, top + r * 0.6), (90, 230, 200, 255))
        for _ in range(3):
            _circle(img, x + rnd.uniform(-r * 0.6, r * 0.6), top + rnd.uniform(-r * 0.4, 0), 1.1,
                    (230, 255, 250, 255))
    return _finish(img, w, h)


def glowcap(full=True):
    return _tex("swamp_glowcap", _glowcap_img, [(-10, -8), (10, -8), (10, 8), (-10, 8)])


# =========================================================================== enemies
def _drowned_img():
    img = art._zombie_img((112, 150, 140), (62, 76, 62), 66, 1.08)
    over = _canvas(66, 66)
    rnd = random.Random(5000)
    c = 33
    for _ in range(9):          # weeds draped over it, dripping
        x, y = c + rnd.uniform(-14, 8), c + rnd.uniform(-16, 16)
        _line(over, [(x, y), (x - rnd.uniform(3, 9), y + rnd.uniform(-3, 3))], (70, 110, 50, 255), 1.6)
    for _ in range(5):
        _circle(over, c + rnd.uniform(-12, 10), c + rnd.uniform(-16, 16), rnd.uniform(1.5, 2.6), (60, 84, 70, 230))
    for side in (-1, 1):        # pale swamp-light eyes over the red ones
        _circle(over, c + 6.5, c + side * 4.3, 1.9, (170, 255, 140, 255))
    img.alpha_composite(_finish(over, 66, 66))
    return img


# =========================================================================== the boss
def _mire_img():
    rnd = random.Random(5100)
    w = 176
    img = _canvas(w, w)
    c = w / 2
    _shadow(img, (18, 28, 166, 168), alpha=130, blur=8)
    glow = _canvas(w, w)
    _circle(glow, c, c, 66, (110, 220, 120, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * S)))
    for side in (-1, 1):        # two long root-arms with hooked claws, reaching forward
        pts = [(c - 10, c + side * 34), (c + 26, c + side * 52), (c + 58, c + side * 46), (c + 74, c + side * 34)]
        _line(img, pts, (52, 40, 28, 255), 14)
        _line(img, pts, (86, 66, 42, 255), 8)
        for k in range(3):
            tx, ty = c + 74, c + side * 34
            _line(img, [(tx, ty), (tx + 10, ty + side * (k * 6 - 6)), (tx + 8, ty + side * (k * 6 - 10))],
                  (200, 190, 150, 255), 2.4)
        for k in range(4):      # little thorns
            px, py = pts[1][0] + k * 10, pts[1][1] - side * 3
            _poly(img, [(px, py), (px + 3, py - side * 7), (px + 5, py)], (60, 46, 30, 255))
    _ball(img, (c - 62, c - 56, c + 40, c + 56), (66, 74, 44, 255))               # mud mound body
    _ball(img, (c - 46, c - 40, c + 20, c + 40), (80, 96, 52, 255), outline=False)  # moss back
    for _ in range(26):         # reeds growing out of its back
        x, y = rnd.uniform(c - 50, c + 10), rnd.uniform(c - 44, c + 44)
        _line(img, [(x, y), (x - rnd.uniform(6, 14), y + rnd.uniform(-5, 5))],
              rnd.choice([(120, 140, 64), (150, 150, 76)]) + (255,), 1.6)
    for x, y, r in [(c - 30, c - 22, 7), (c - 18, c + 24, 6), (c - 42, c + 6, 5), (c - 4, c - 34, 5)]:
        _ball(img, (x - r, y - r, x + r, y + r), (90, 230, 200, 255))             # glowcaps on its back
    for _ in range(10):         # dripping mud
        x, y = rnd.uniform(c - 50, c + 30), rnd.uniform(c - 50, c + 50)
        _circle(img, x, y, rnd.uniform(2, 4), (48, 52, 34, 230))
    _ball(img, (c + 8, c - 28, c + 54, c + 28), (74, 84, 50, 255))                # head
    _poly(img, [(c + 40, c - 16), (c + 58, c - 10), (c + 58, c + 10), (c + 40, c + 16), (c + 46, c)],
          (40, 26, 22, 255))                                                     # wide maw
    for k in range(4):
        y = c - 12 + k * 8
        _poly(img, [(c + 50, y), (c + 56, y + 2), (c + 50, y + 4)], (226, 220, 190, 255))
    for side in (-1, 1):
        _circle(img, c + 36, c + side * 14, 4.6, (220, 255, 120, 255))
        _circle(img, c + 37, c + side * 14, 1.8, (40, 60, 20, 255))
    return _finish(img, w, w)


# =========================================================================== item icons
def _reeds_icon(img):
    for k in range(7):
        x = 14 + k * 3.4
        _line(img, [(x, 44), (x + (k - 3) * 2.2, 8)], [(110, 140, 60), (150, 150, 76)][k % 2] + (255,), 2.2)
    _rrect(img, (21, 6, 27, 18), 3, (110, 72, 40, 255), (70, 44, 24, 255))
    _rrect(img, (12, 28, 36, 33), 2, (170, 130, 80, 255))


def _glowcap_icon(img):
    g = _canvas(48, 48)
    _circle(g, 24, 20, 16, (120, 255, 210, 140))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(4 * S)))
    _line(img, [(24, 42), (24, 22)], (214, 220, 196, 255), 6)
    _ball(img, (8, 8, 40, 28), (90, 230, 200, 255))
    for x, y in [(16, 14), (26, 12), (32, 18), (20, 20)]:
        _circle(img, x, y, 1.6, (230, 255, 250, 255))


def _mire_heart_icon(img):
    g = _canvas(48, 48)
    _circle(g, 24, 25, 16, (130, 230, 110, 140))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(4 * S)))
    _circle(img, 17, 19, 9, (70, 92, 46, 255))
    _circle(img, 31, 19, 9, (70, 92, 46, 255))
    _poly(img, [(9, 22), (39, 22), (24, 41)], (70, 92, 46, 255))
    for pts in ([(16, 14), (21, 22), (19, 30)], [(30, 14), (27, 23), (29, 31)], [(21, 22), (27, 23)]):
        _line(img, pts, (170, 255, 120, 255), 1.6)
    _circle(img, 15, 15, 2.6, (150, 180, 110, 255))


def _mask_icon(img):
    _ball(img, (8, 6, 40, 42), (88, 104, 56, 255))
    for x in (17, 31):
        _ball(img, (x - 5, 16, x + 5, 24), (30, 34, 24, 255), outline=False)
        _circle(img, x, 20, 1.6, (170, 255, 140, 255))
    _rrect(img, (16, 30, 32, 38), 3, (60, 70, 40, 255), (40, 46, 28, 255), 0.8)     # filter
    for x in (19, 24, 29):
        _line(img, [(x, 31), (x, 37)], (110, 126, 72, 255), 1)
    for k in range(7):          # reed fringe
        x = 10 + k * 4.6
        _line(img, [(x, 8), (x - 1, 2)], (150, 150, 76, 255), 1.6)


def _tonic_icon(img):
    _rrect(img, (20, 4, 28, 12), 2, (120, 84, 50, 255))
    _line(img, [(24, 12), (24, 18)], (190, 210, 200, 255), 6)
    _ball(img, (9, 16, 39, 44), (80, 210, 170, 255))
    _circle(img, 19, 26, 3, (230, 255, 245, 210))
    _circle(img, 28, 34, 1.6, (230, 255, 245, 170))


def _whip_icon(img):
    _rrect(img, (4, 22, 16, 30), 3, (110, 74, 42, 255), (60, 40, 22, 255))
    pts = [(16, 26), (24, 20), (32, 24), (38, 16), (44, 8)]
    _line(img, pts, (70, 54, 34, 255), 4)
    _line(img, pts, (110, 88, 54, 255), 2)
    for x, y in [(22, 21), (29, 22), (35, 19), (40, 13)]:
        _poly(img, [(x, y), (x + 2, y - 5), (x + 4, y)], (200, 190, 150, 255))
    _circle(img, 44, 8, 2.4, (170, 255, 120, 255))


art.ICON_MAKERS.update({
    "reeds": _reeds_icon, "glowcap": _glowcap_icon, "mire_heart": _mire_heart_icon,
    "mire_mask": _mask_icon, "swamp_tonic": _tonic_icon, "thornroot_whip": _whip_icon,
})


# --------------------------------------------------------------------------- the mask, worn
def _worn_mask():
    img = _canvas(64, 64)
    _ball(img, (22, 21, 40, 43), (84, 100, 54, 255))
    _rrect(img, (36, 27, 43, 37), 2, (60, 70, 40, 255), (40, 46, 28, 255), 0.8)      # filter over the mouth
    for y in (27, 37):
        _circle(img, 35, y, 1.4, (170, 255, 140, 255))                              # goggle glints
    for k in range(7):          # reed fringe trailing off the back of the head
        y = 23 + k * 3
        _line(img, [(23, y), (16, y + (k - 3) * 0.8)], (150, 150, 76, 255), 1.4)
    return _finish(img, 64, 64)


art_gear.HEAD["mire_mask"] = _worn_mask
art_extra.BOSS_ART["mire"] = (_mire_img, 52)

# --------------------------------------------------------------------------- plug into art.tree / art_extra.enemy
_plain_tree = art.tree
_plain_enemy = art_extra.enemy


def _tree(i):
    return swamp_tree(i - SWAMP_TREE) if i >= SWAMP_TREE else _plain_tree(i)


def _enemy(kind):
    if kind == "drowned":
        return _tex("enemy_drowned", _drowned_img, [(-13, -13), (13, -13), (13, 13), (-13, 13)])
    return _plain_enemy(kind)


art.tree = _tree
art_extra.enemy = _enemy


def all_textures():
    """Used by --export-art."""
    for i in range(3):
        ground(i)
        pool(i)
        swamp_tree(i)
    for i in range(4):
        decor(i)
    reeds()
    glowcap()
    _enemy("drowned")
    art_extra.boss("mire")
