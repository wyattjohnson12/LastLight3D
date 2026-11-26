"""
art_flag.py - the Base Flag: a tall banner on a pole that marks your base.

Importing this module registers the flag with art.icon() (the same picture is the hotbar icon and the
upright cut-out you see in the 3D world and in first person). It also has the little bits of drawing
the base marker needs on screen (called in GUI space, after the 3D world is drawn):

  * draw_beacon()  - a soft column of light rising out of the flag, so you can spot it from far away
  * draw_label()   - "BASE  12m" floating over the flag when it's on screen
  * draw_arrow()   - an arrow on the edge of the screen pointing home when it isn't

Nothing here touches view3d.py: the flag is an ordinary building cut-out, and the marker only needs
game.project() (world point -> screen), which every camera mode has.
"""
import math

import arcade

import art
from art import _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shade, _tex

CLOTH = (196, 52, 46)
CLOTH_DARK = (120, 28, 26)
GOLD = (236, 196, 96)
POLE = (122, 84, 48)
POLE_DARK = (70, 46, 26)
FRAMES = 4                    # the banner flaps through these pictures
SIZE = 96                     # square canvas, so the hotbar icon isn't squashed; the pole is the tall part


def _hb(w, h):
    return [(-w, -h), (w, -h), (w, h), (-w, h)]


def _flag_img(frame=0):
    """A stone foot, a tall pole with a gold knob, and a red swallow-tailed banner with a gold sun."""
    w = h = SIZE
    img = _canvas(w, h)
    px = 34                                          # pole x
    # stone foot
    _ball(img, (px - 13, 84, px + 13, 95), (126, 124, 118, 255))
    _ball(img, (px - 8, 80, px + 8, 89), (146, 142, 134, 255))
    # pole
    _rrect(img, (px - 2.4, 6, px + 2.4, 88), 1.2, POLE + (255,), POLE_DARK + (255,), 0.9)
    _line(img, [(px - 0.8, 8), (px - 0.8, 86)], _shade(POLE, 1.3) + (200,), 0.8)
    _ball(img, (px - 4.5, 1, px + 4.5, 10), GOLD + (255,))
    # banner: a wavy swallow-tail, its free edge swings with the frame
    ph = frame / FRAMES * math.tau
    top, bot, length = 12.0, 50.0, 54.0
    n = 10
    upper, lower = [], []
    for i in range(n + 1):
        k = i / n
        wave = math.sin(ph + k * 4.2) * 3.2 * k
        x = px + 2 + k * length
        upper.append((x, top + wave))
        lower.append((x, bot + wave + k * 2))
    tail = upper[-1][0] - 12, (upper[-1][1] + lower[-1][1]) / 2
    pts = upper + [tail] + lower[::-1]
    _poly(img, pts, CLOTH + (255,), CLOTH_DARK + (255,), 1.4)
    # a darker fold along the bottom and a highlight along the top
    _line(img, [(x, y - 3) for x, y in lower[1:-1]], _shade(CLOTH, 0.75) + (200,), 2.4)
    _line(img, [(x, y + 2.5) for x, y in upper[1:-1]], _shade(CLOTH, 1.25) + (180,), 1.6)
    # gold sun emblem in the middle of the cloth
    mx = px + 2 + length * 0.42
    my = (top + bot) / 2 + math.sin(ph + 0.42 * 4.2) * 3.2 * 0.42
    for a in range(8):
        t = a / 8 * math.tau
        _line(img, [(mx + math.cos(t) * 6, my + math.sin(t) * 6), (mx + math.cos(t) * 10, my + math.sin(t) * 10)],
              GOLD + (255,), 1.6)
    _circle(img, mx, my, 5.2, GOLD + (255,), _shade(GOLD, 0.6) + (255,), 0.8)
    return _finish(img, w, h)


def flag(frame=0):
    frame %= FRAMES
    return _tex(f"build_base_flag_{frame}", lambda: _flag_img(frame), _hb(10, 10))


art.STRUCTURE_ICONS["base_flag"] = flag


def all_textures():
    for f in range(FRAMES):
        flag(f)


# --------------------------------------------------------------------------- on-screen marker bits
BEACON = (255, 214, 120)


def draw_beacon(game, x, y, strength=1.0):
    """A faint column of light from the flag up into the sky (GUI space; projected from the world)."""
    if strength <= 0:
        return
    base = game.project(x, y, 60)
    if base is None:
        return
    a = int(70 * strength)
    prev = base
    for i in range(1, 7):
        top = game.project(x, y, 60 + i * 110)
        if top is None:
            break
        fade = 1 - i / 7
        arcade.draw_line(prev[0], prev[1], top[0], top[1], BEACON + (int(a * fade),), 10 * fade + 2)
        arcade.draw_line(prev[0], prev[1], top[0], top[1], (255, 250, 230, int(a * 1.4 * fade)), 2)
        prev = top


def draw_label(game, sx, sy, metres, key="baselbl"):
    """'BASE 12m' with a little gold diamond, floating above the flag."""
    d = 7
    arcade.draw_polygon_filled([(sx, sy + d), (sx + d, sy), (sx, sy - d), (sx - d, sy)], GOLD + (230,))
    arcade.draw_polygon_outline([(sx, sy + d), (sx + d, sy), (sx, sy - d), (sx - d, sy)], (90, 50, 20, 230), 1.5)
    game.txt(key, f"BASE  {metres}m", sx, sy + 11, (255, 236, 180, 235), 10, anchor_x="center", bold=True)


def draw_arrow(game, ang, metres, W, H, key="basearr"):
    """An edge-of-screen arrow pointing home (ang = screen angle, radians), with how far it is."""
    ex = max(40, min(W - 40, W / 2 + math.cos(ang) * (W / 2 - 50)))
    ey = max(120, min(H - 180, H / 2 + math.sin(ang) * (H / 2 - 50)))
    tip = (ex + math.cos(ang) * 16, ey + math.sin(ang) * 16)
    l = (ex + math.cos(ang + 2.4) * 12, ey + math.sin(ang + 2.4) * 12)
    r = (ex + math.cos(ang - 2.4) * 12, ey + math.sin(ang - 2.4) * 12)
    arcade.draw_triangle_filled(*tip, *l, *r, GOLD + (235,))
    arcade.draw_triangle_outline(*tip, *l, *r, (90, 50, 20, 230), 1.5)
    tx, ty = ex - math.cos(ang) * 24, ey - math.sin(ang) * 24 - 4
    game.txt(key, f"BASE {metres}m", tx, ty, (255, 230, 160, 235), 10, anchor_x="center", bold=True)
