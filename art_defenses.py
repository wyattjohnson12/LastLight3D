"""
art_defenses.py - painted art for the base defenses: Arrow Turret, Gate and Lantern.

Importing this module registers them with art.icon() (the same picture is the hotbar icon and the
upright cut-out you see in the 3D world). Same painted style as art.py: drawn at 3x and scaled down.
"""
import random

from PIL import ImageFilter, ImageOps

import art
from art import S, _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shade, _tex

WOOD = (150, 104, 62)
WOOD_DARK = (84, 56, 32)
IRON = (150, 156, 168)
IRON_DARK = (62, 64, 72)


def _hb(w, h):
    return [(-w, -h), (w, -h), (w, h), (-w, h)]


# --------------------------------------------------------------------------- arrow turret
def _turret_img():
    """A squat stone-and-timber tower with a loaded crossbow on top (pointing right)."""
    rnd = random.Random(21)
    w = h = 52
    img = _canvas(w, h)
    # stone footing
    _rrect(img, (8, 36, 44, 51), 3, (110, 108, 104, 255), (58, 56, 54, 255), 1.2)
    for row in range(2):
        x = 9 + (row % 2) * 5
        while x < 42:
            bw = rnd.uniform(7, 10)
            col = rnd.choice([(146, 142, 134), (128, 126, 120), (156, 150, 140)])
            _rrect(img, (x, 37.5 + row * 6.5, min(43, x + bw), 42.5 + row * 6.5), 1.5,
                   col + (255,), _shade(col, 0.55) + (255,), 0.6)
            x += bw + 1
    # timber legs with a cross brace
    for x0, x1 in ((13, 18), (34, 39)):
        _poly(img, [(x0, 37), (x0 + 2, 20), (x1 - 2, 20), (x1, 37)], WOOD + (255,), WOOD_DARK + (255,), 1)
    _line(img, [(16, 34), (36, 23)], _shade(WOOD, 0.85) + (255,), 2.2)
    _line(img, [(16, 23), (36, 34)], _shade(WOOD, 0.8) + (255,), 2.2)
    # platform
    _rrect(img, (10, 17, 42, 22), 2, (128, 88, 52, 255), WOOD_DARK + (255,), 1)
    # crossbow: stock, bow limbs, string and a bolt ready to fly
    _rrect(img, (14, 10, 40, 14.5), 2, (118, 80, 46, 255), WOOD_DARK + (255,), 0.9)
    _line(img, [(36, 2.5), (40.5, 12), (36, 21.5)], IRON_DARK + (255,), 2.6)
    _line(img, [(36, 3.5), (40, 12), (36, 20.5)], IRON + (255,), 1.2)
    _line(img, [(36, 3), (27, 12), (36, 21)], (230, 220, 190, 230), 0.8)
    _line(img, [(25, 12), (49, 12)], (214, 180, 120, 255), 1.6)
    _poly(img, [(47, 9.5), (51, 12), (47, 14.5)], (210, 214, 224, 255), IRON_DARK + (255,), 0.6)
    _line(img, [(25, 10), (22, 9), (25, 12), (22, 15), (25, 14)], (220, 70, 60, 230), 0.8)  # fletching
    _circle(img, 20, 16, 2.2, IRON_DARK + (255,))               # swivel
    _circle(img, 20, 16, 1.0, IRON + (255,))
    return _finish(img, w, h)


def turret(left=False):
    if left:
        return _tex("build_arrow_turret_left", lambda: ImageOps.mirror(_turret_img()), _hb(18, 18))
    return _tex("build_arrow_turret", _turret_img, _hb(18, 18))


# --------------------------------------------------------------------------- gate
def _gate_img():
    """A plank gate between two posts, with iron hinges - a bit lower than a wall so it reads as a door."""
    w = h = 40
    img = _canvas(w, h)
    for x in (1, 34):                                      # posts
        _rrect(img, (x, 4, x + 5, 40), 1.5, (120, 82, 46, 255), WOOD_DARK + (255,), 1)
        _ball(img, (x - 0.5, 1.5, x + 5.5, 7), (140, 96, 56, 255))
    for k in range(5):                                     # vertical planks, little gaps between them
        x0 = 7 + k * 5.4
        col = [(160, 112, 66), (146, 100, 58), (166, 118, 70), (150, 104, 62), (158, 110, 64)][k]
        _rrect(img, (x0, 10 - (k % 2), x0 + 4.6, 38), 1.2, col + (255,), WOOD_DARK + (255,), 0.8)
    for y in (15, 31):                                     # rails
        _rrect(img, (6, y - 1.6, 34, y + 1.6), 1, (128, 88, 52, 255), WOOD_DARK + (255,), 0.7)
    _line(img, [(8, 30), (32, 16)], (118, 80, 46, 255), 2.2)   # Z brace
    for y in (15, 31):                                     # hinges & latch
        _rrect(img, (4, y - 1.8, 11, y + 1.8), 0.8, IRON_DARK + (255,))
    _circle(img, 30, 23, 1.6, (214, 190, 110, 255), IRON_DARK + (255,), 0.6)
    return _finish(img, w, h)


def gate():
    return _tex("build_gate", _gate_img, art.BLOCK_HIT)


# --------------------------------------------------------------------------- lantern
def _lantern_img(lit=True):
    """A lantern on a post: stone foot, wooden pole, iron cage with warm glass."""
    w = h = 40
    img = _canvas(w, h)
    _ball(img, (12, 33, 28, 40), (128, 126, 120, 255))                  # stone foot
    _rrect(img, (18, 12, 22, 36), 1.2, (120, 82, 46, 255), WOOD_DARK + (255,), 0.8)   # pole
    _line(img, [(20, 7), (28, 7), (28, 9)], IRON_DARK + (255,), 1.4)    # hanging arm
    if lit:
        glow = _canvas(w, h)
        _circle(glow, 28, 15, 9, (255, 200, 90, 150))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3 * S)))
    glass = (255, 214, 120) if lit else (120, 110, 90)
    _poly(img, [(24, 10), (32, 10), (33, 20), (23, 20)], glass + (255,), IRON_DARK + (255,), 1.1)
    if lit:
        _ball(img, (26, 12, 30, 18), (255, 246, 200, 255), outline=False)
    _line(img, [(28, 10), (28, 20)], IRON_DARK + (220,), 0.8)
    _poly(img, [(23, 10), (28, 6.5), (33, 10)], IRON + (255,), IRON_DARK + (255,), 0.9)   # cap
    _rrect(img, (22.5, 19.5, 33.5, 22), 0.8, IRON + (255,), IRON_DARK + (255,), 0.7)       # base
    return _finish(img, w, h)


def lantern():
    return _tex("build_lantern", _lantern_img, _hb(8, 8))


art.STRUCTURE_ICONS.update({"arrow_turret": turret, "gate": gate, "lantern": lantern})


def all_textures():
    """Make sure every texture exists (used by --export-art)."""
    turret()
    turret(True)
    gate()
    lantern()
