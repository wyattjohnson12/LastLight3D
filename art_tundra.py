"""
art_tundra.py - painted-in-code art for the Frostwood Tundra (tundra.py).

Same style and same assets/ override as art.py (drop e.g. assets/tundra_pine_0.png in to replace one).
Importing this module plugs the new pictures into the existing art functions:
  * art.tree(i) for i >= PINE_TREE draws a snow-laden pine (so chopped pines regrow as pines)
  * art_extra.animal("snow_fox" / "snow_hare" / "arctic_wolf")
  * art.icon(...) knows the new item icons, art_gear.gear(...) the worn hood and cloak

The 3D look comes from shapes3d.SHAPES (registered by tundra.py): the pictures here are DRAPED over those
shapes from above, so they are painted as concentric zones. A pine's picture is, from the centre out:
a white snow crown, dark needles dabbed with snow, then a snowy rim - the cone tiers pick those colours up
ring by ring (crown on top, white tips on every tier). Every picture is fully opaque where a shape samples
it, so nothing turns see-through.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import art
import art_extra
import art_gear
from art import S, _ball, _canvas, _circle, _finish, _line, _poly, _rrect, _shade, _shadow, _tex

PINE_TREE = 20           # tree variants from here up are pines (20, 21, 22)

SNOW = (236, 242, 250)
SNOW_SHADE = (196, 212, 232)
ICE = (168, 214, 240)
NEEDLE = [(34, 74, 58), (30, 66, 60), (44, 84, 56)]


def _wrap_blobs(d, n, rnd, count, rmin, rmax, palette, amin, amax):
    for _ in range(count):
        r = rnd.randint(rmin, rmax)
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        col = rnd.choice(palette) + (rnd.randint(amin, amax),)
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                d.ellipse([x + ox - r, y + oy - r, x + ox + r, y + oy + r], fill=col)


# =========================================================================== ground
def _snow_tile(seed):
    """256 px snow tile (wraps seamlessly): soft drifts, blue hollows, sparkles, a few grass tips."""
    rnd = random.Random(seed)
    n = 256
    img = Image.new("RGBA", (n, n), (230, 236, 246, 255))
    blobs = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    _wrap_blobs(ImageDraw.Draw(blobs), n, rnd, 120, 10, 40,
                [(212, 224, 240), (244, 248, 255), (220, 230, 244), (250, 252, 255), (204, 218, 238)], 70, 150)
    img.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    for _ in range(18):       # wind ripples
        x, y = rnd.randint(10, n - 40), rnd.randint(8, n - 8)
        w = rnd.randint(16, 40)
        d.arc([x, y - 4, x + w, y + 4], 200, 340, fill=(196, 212, 234, 150), width=1)
    for _ in range(rnd.randint(6, 14)):      # dead grass poking through
        x, y = rnd.randint(4, n - 4), rnd.randint(6, n - 2)
        for k in range(3):
            d.line([(x + k, y), (x + k + rnd.randint(-2, 2), y - rnd.randint(3, 6))], fill=(150, 140, 100, 200))
    for _ in range(90):       # sparkles
        x, y = rnd.randint(1, n - 2), rnd.randint(1, n - 2)
        d.point((x, y), fill=(255, 255, 255, 255))
    return img


def ground(i):
    return _tex(f"tundra_snow_{i}", lambda: _snow_tile(5100 + i))


def _patch_img(seed, cols, n=384):
    """Big soft-edged patch (for the seasonal snow line / summer thaw)."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (n, n), cols[0] + (255,))
    blobs = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    for _ in range(160):
        r = rnd.randint(8, 34)
        x, y = rnd.randint(0, n), rnd.randint(0, n)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice(cols) + (rnd.randint(60, 140),))
    img.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(9)))
    rag = Image.new("L", (n, n), 0)
    dr = ImageDraw.Draw(rag)
    for _ in range(36):
        a = rnd.uniform(0, math.tau)
        rr = rnd.uniform(0.05, 0.3) * n
        x, y = n / 2 + math.cos(a) * rr, n / 2 + math.sin(a) * rr
        s = rnd.uniform(0.12, 0.2) * n
        dr.ellipse([x - s, y - s, x + s, y + s], fill=255)
    img.putalpha(rag.filter(ImageFilter.GaussianBlur(n * 0.06)))
    return img


def snow_patch(i):
    return _tex(f"tundra_snowline_{i}", lambda: _patch_img(5200 + i, [SNOW, (222, 232, 246), (246, 250, 255),
                                                                     (210, 222, 240)]))


def thaw_patch(i):
    return _tex(f"tundra_thaw_{i}", lambda: _patch_img(5300 + i, [(104, 124, 70), (92, 112, 62), (120, 132, 80),
                                                                 (140, 136, 96), (200, 210, 220)]))


def _drift_img(seed):
    """A snowdrift: a long soft mound lit from the top-left with a blue shadow side."""
    rnd = random.Random(seed)
    w, h = 96, 54
    img = _canvas(w, h)
    _shadow(img, (10, 18, w - 2, h - 2), alpha=50, blur=4)
    for k in range(3):
        x0 = 8 + k * 22 + rnd.uniform(-4, 4)
        _ball(img, (x0, 12 + rnd.uniform(-3, 3), x0 + 44, 46), SNOW_SHADE + (255,), light=(-0.45, -0.55),
              outline=False, soft=1.8)
    for k in range(3):
        x0 = 12 + k * 22 + rnd.uniform(-3, 3)
        _ball(img, (x0, 12, x0 + 34, 34), (248, 251, 255, 230), light=(-0.4, -0.5), outline=False, soft=2.2)
    return _finish(img, w, h)


def _ice_chips_img(seed):
    rnd = random.Random(seed)
    img = _canvas(30, 22)
    for _ in range(4):
        x, y, r = rnd.uniform(6, 24), rnd.uniform(6, 16), rnd.uniform(2.2, 4)
        pts = [(x + math.cos(a) * r, y + math.sin(a) * r * 0.8) for a in (0.3, 1.9, 3.4, 4.9)]
        _poly(img, pts, ICE + (240,), (110, 160, 200, 255), 0.8)
        _circle(img, x - 1, y - 1, 0.9, (255, 255, 255, 255))
    return _finish(img, 30, 22)


def _frost_grass_img(seed):
    rnd = random.Random(seed)
    img = _canvas(28, 22)
    for _ in range(8):
        x = rnd.uniform(6, 22)
        h = rnd.uniform(7, 14)
        _line(img, [(x, 20), (x + rnd.uniform(-4, 4), 20 - h)], rnd.choice([(150, 146, 110), (176, 170, 130)]) + (255,), 1.4)
    _ball(img, (3, 15, 25, 22), (240, 245, 252, 255), outline=False)
    return _finish(img, 28, 22)


def _tracks_img(seed):
    rnd = random.Random(seed)
    img = _canvas(70, 26)
    for k in range(6):
        x = 6 + k * 11
        y = 9 + (k % 2) * 8
        _circle(img, x, y, 2.2, (186, 202, 226, 220))
        for j in (-1, 0, 1):
            _circle(img, x + 3, y + j * 1.8, 0.9, (186, 202, 226, 220))
    return _finish(img, 70, 26)


def decor(i):
    """0-2 snowdrifts, 3 ice chips, 4 frosted grass, 5 tracks."""
    makers = [lambda: _drift_img(5400), lambda: _drift_img(5401), lambda: _drift_img(5402),
              lambda: _ice_chips_img(5403), lambda: _frost_grass_img(5404), lambda: _tracks_img(5405)]
    return _tex(f"tundra_decor_{i}", makers[i % len(makers)])


# =========================================================================== ponds
def _frozen_pond_img(seed, frozen):
    rnd = random.Random(seed)
    w, h = 220, 160
    img = _canvas(w, h)
    _ball(img, (4, 6, 216, 156), (224, 232, 244, 255), outline=False, soft=2)        # snowy bank
    layer = _canvas(w, h)
    if frozen:
        _ball(layer, (16, 16, 204, 144), (170, 210, 232, 255), light=(-0.3, -0.35), outline=False, soft=2.5)
    else:
        _ball(layer, (16, 16, 204, 144), (44, 92, 136, 255), light=(0.2, 0.25), outline=False, soft=2.5)
    img.alpha_composite(layer)
    d = ImageDraw.Draw(img)
    d.ellipse([16 * S, 16 * S, 204 * S, 144 * S], outline=(120, 170, 204, 255), width=2 * S)
    if frozen:
        for _ in range(9):      # cracks
            x, y = rnd.uniform(50, 170), rnd.uniform(40, 120)
            pts = [(x, y)]
            for _ in range(3):
                x += rnd.uniform(-16, 16)
                y += rnd.uniform(-10, 10)
                pts.append((x, y))
            _line(img, pts, (236, 246, 255, 200), 1.0)
        for _ in range(6):      # snow dusting
            x, y = rnd.uniform(40, 180), rnd.uniform(36, 124)
            _ball(img, (x - 14, y - 6, x + 14, y + 6), (240, 246, 255, 150), outline=False, soft=2)
        _poly(img, [(70, 50), (120, 40), (100, 60)], (250, 252, 255, 120))                 # shine
    else:
        for _ in range(8):      # drifting ice floes in black water
            x, y = rnd.uniform(40, 180), rnd.uniform(36, 124)
            r = rnd.uniform(5, 12)
            pts = [(x + math.cos(a) * r * rnd.uniform(0.7, 1.2), y + math.sin(a) * r * 0.7) for a in
                   [k * math.tau / 6 for k in range(6)]]
            _poly(img, pts, (220, 236, 248, 235), (150, 190, 220, 255), 0.8)
        for _ in range(5):
            x, y = rnd.uniform(50, 170), rnd.uniform(40, 120)
            rw = rnd.uniform(10, 22)
            d.arc([(x - rw) * S, (y - rw * 0.4) * S, (x + rw) * S, (y + rw * 0.4) * S], 200, 340,
                  fill=(150, 196, 226, 170), width=int(1.2 * S))
    return _finish(img, w, h)


def pond(i, frozen):
    return _tex(f"tundra_pond_{'ice' if frozen else 'water'}_{i}",
                lambda: _frozen_pond_img(5500 + i, frozen), art.POND_HIT)


# =========================================================================== pines (draped over the "pine" shape)
def _pine_img(seed, needles, size=130):
    """Top-down snow-laden pine, painted as zones by distance from the centre (f = share of the half size):
    f < 0.24 snow crown | 0.24 - 0.8 needles with snow clumps | 0.8 - 0.93 snowy rim | outside: clear."""
    rnd = random.Random(seed)
    w = size
    c = w / 2
    img = _canvas(w, w)
    R = c * 0.93
    # needles: a solid dark disc (opaque everywhere the shape samples), then branch spokes on top
    _circle(img, c, c, R, _shade(needles[0], 0.8) + (255,))
    for k in range(26):
        a = k / 26 * math.tau + rnd.uniform(-0.08, 0.08)
        col = rnd.choice(needles) + (255,)
        r0, r1 = R * 0.2, R * rnd.uniform(0.84, 0.97)
        _poly(img, [(c + math.cos(a - 0.12) * r0, c + math.sin(a - 0.12) * r0),
                    (c + math.cos(a) * r1, c + math.sin(a) * r1),
                    (c + math.cos(a + 0.12) * r0, c + math.sin(a + 0.12) * r0)], col)
        for j in range(4):    # needle strokes along the branch
            t = 0.35 + j * 0.15
            x, y = c + math.cos(a) * R * t, c + math.sin(a) * R * t
            for side in (-1, 1):
                _line(img, [(x, y), (x + math.cos(a + side * 0.9) * 6, y + math.sin(a + side * 0.9) * 6)],
                      _shade(col[:3], 1.25) + (200,), 1.0)
    # snowy rim: white tips on every branch end
    ring = _canvas(w, w)
    _circle(ring, c, c, R, SNOW + (255,))
    ImageDraw.Draw(ring).ellipse([(c - R * 0.8) * S, (c - R * 0.8) * S, (c + R * 0.8) * S, (c + R * 0.8) * S],
                                 fill=(0, 0, 0, 0))
    img.alpha_composite(ring)
    for k in range(18):       # ragged inner edge of the rim
        a = k / 18 * math.tau + rnd.uniform(-0.1, 0.1)
        x, y = c + math.cos(a) * R * 0.8, c + math.sin(a) * R * 0.8
        _ball(img, (x - 6, y - 4, x + 6, y + 4), SNOW + (255,), outline=False, soft=1.4)
    # snow clumps resting on the branches
    for _ in range(30):
        a = rnd.uniform(0, math.tau)
        d = R * rnd.uniform(0.3, 0.72)
        x, y = c + math.cos(a) * d, c + math.sin(a) * d
        s = rnd.uniform(2.5, 5)
        _ball(img, (x - s, y - s * 0.7, x + s, y + s * 0.7), (242, 247, 255, 255), light=(-0.4, -0.5),
              outline=False, soft=1.2)
    # snow crown
    _ball(img, (c - R * 0.27, c - R * 0.27, c + R * 0.27, c + R * 0.27), SNOW + (255,), light=(-0.35, -0.4),
          outline=False, soft=1.5)
    d = ImageDraw.Draw(img)
    d.ellipse([(c - R) * S, (c - R) * S, (c + R) * S, (c + R) * S], outline=(150, 174, 200, 255), width=int(1.2 * S))
    return _finish(img, w, w)


def pine(i):
    return _tex(f"tundra_pine_{i}", lambda: _pine_img(5600 + i, [_shade(col, 0.9 + 0.12 * i) for col in NEEDLE]),
                art.TRUNK_HIT)


def _whitewood_img(seed):
    """Top-down whitewood: a round crown of silver-green leaves (opaque) with a light dusting of frost."""
    rnd = random.Random(seed)
    w = 140
    c = w / 2
    img = _canvas(w, w)
    R = c * 0.93
    _circle(img, c, c, R, (112, 138, 128, 255))
    for _ in range(11):
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0, R * 0.55)
        r = rnd.uniform(R * 0.3, R * 0.42)
        x, y = c + math.cos(a) * d, c + math.sin(a) * d
        _ball(img, (x - r, y - r, x + r, y + r), rnd.choice([(150, 176, 160), (166, 190, 174), (134, 162, 150)]) + (255,),
              outline=False, soft=1.5)
    for _ in range(90):         # small leaves
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0, R * 0.92)
        x, y = c + math.cos(a) * d, c + math.sin(a) * d
        _circle(img, x, y, rnd.uniform(1.6, 3.0), rnd.choice([(196, 214, 200), (120, 150, 136), (210, 226, 216)]) + (230,))
    for _ in range(14):         # frost glints
        a = rnd.uniform(0, math.tau)
        d = rnd.uniform(0, R * 0.8)
        _circle(img, c + math.cos(a) * d, c + math.sin(a) * d, 1.2, (245, 250, 255, 230))
    ImageDraw.Draw(img).ellipse([(c - R) * S, (c - R) * S, (c + R) * S, (c + R) * S], outline=(90, 112, 104, 255),
                                width=int(1.2 * S))
    return _finish(img, w, w)


def whitewood():
    return _tex("tundra_whitewood", lambda: _whitewood_img(5700), [(-14, -14), (14, -14), (14, 14), (-14, 14)])


# =========================================================================== ice
def _ice_rock_img(seed, w=74):
    """A block of blue ice seen from above: faceted, opaque, with white frost on the facets."""
    rnd = random.Random(seed)
    c = w / 2
    img = _canvas(w, w)
    R = c * 0.92
    pts = [(c + math.cos(a) * R * rnd.uniform(0.92, 1.0), c + math.sin(a) * R * rnd.uniform(0.92, 1.0))
           for a in [k * math.tau / 7 + 0.3 for k in range(7)]]
    _poly(img, pts, (110, 170, 214, 255), (60, 110, 160, 255), 1.4)
    for k in range(7):          # facets: lighter top-left
        a0, a1 = k * math.tau / 7 + 0.3, (k + 1) * math.tau / 7 + 0.3
        light = 0.8 + 0.5 * (0.5 + 0.5 * math.cos((a0 + a1) / 2 + 2.3))
        col = _shade((128, 190, 228), light)
        _poly(img, [(c, c), pts[k], pts[(k + 1) % 7]], col + (255,))
        _line(img, [(c, c), pts[k]], (226, 244, 255, 220), 1.0)
    _circle(img, c, c, R * 0.32, (214, 238, 252, 255))
    _circle(img, c - R * 0.1, c - R * 0.1, R * 0.12, (255, 255, 255, 255))
    return _finish(img, w, w)


def ice_rock(i):
    return _tex(f"tundra_ice_{i}", lambda: _ice_rock_img(5800 + i), [(-24, -24), (24, -24), (24, 24), (-24, 24)])


def _frost_crystal_img():
    w = 56
    c = w / 2
    img = _canvas(w, w)
    g = _canvas(w, w)
    _circle(g, c, c, c * 0.95, (140, 220, 255, 150))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(3 * S)))
    R = c * 0.86
    pts = [(c + math.cos(a) * R, c + math.sin(a) * R) for a in [k * math.tau / 5 + 0.5 for k in range(5)]]
    _poly(img, pts, (150, 226, 255, 255), (80, 160, 220, 255), 1.2)
    for k in range(5):
        col = _shade((170, 236, 255), 0.85 + 0.3 * (k % 2))
        _poly(img, [(c, c), pts[k], pts[(k + 1) % 5]], col + (255,))
    _circle(img, c, c, R * 0.3, (240, 252, 255, 255))
    return _finish(img, w, w)


def frost_crystal():
    return _tex("tundra_frost_crystal", _frost_crystal_img, [(-14, -14), (14, -14), (14, 14), (-14, 14)])


def _lair_img():
    """The Wraith's Hollow: a ring of frost and a cold blue scar on the snow (flat on the ground)."""
    rnd = random.Random(5900)
    n = 420
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = n / 2
    d.ellipse([20, 20, n - 20, n - 20], fill=(170, 206, 236, 170))
    d.ellipse([60, 60, n - 60, n - 60], fill=(120, 170, 220, 170))
    for _ in range(40):
        a = rnd.uniform(0, math.tau)
        r0, r1 = rnd.uniform(40, 90), rnd.uniform(140, 200)
        d.line([(c + math.cos(a) * r0, c + math.sin(a) * r0), (c + math.cos(a + 0.1) * r1, c + math.sin(a + 0.1) * r1)],
               fill=(236, 248, 255, 200), width=2)
    for k in range(3):
        rr = 70 + k * 45
        d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=(200, 236, 255, 160), width=3)
    return img.filter(ImageFilter.GaussianBlur(2))


def lair():
    return _tex("tundra_lair", _lair_img)


# =========================================================================== animals (face right)
def _snow_fox_img():
    img = _canvas(56, 56)
    _shadow(img, (8, 14, 52, 48), alpha=60, blur=2)
    for k in range(5):           # big bushy tail curling behind
        x = 6 + k * 2.4
        _ball(img, (x - 6, 24 - k * 0.6, x + 6, 34 + k * 0.6), (238, 242, 248, 255), outline=False)
    _circle(img, 4, 29, 3, (250, 252, 255, 255))
    art_extra._quad(img, 28, (232, 236, 244), (28, 16), (196, 204, 216), (36, 21, 48, 35))
    _ball(img, (46, 25, 54, 31), (242, 244, 250, 255))                 # pointed muzzle
    _circle(img, 54, 28, 1.3, (30, 26, 30, 255))                       # nose
    for side in (-1, 1):
        _poly(img, [(38, 28 + side * 4), (36, 28 + side * 11), (43, 28 + side * 6)], (226, 230, 240, 255),
              (150, 150, 160, 255), 0.8)
        _circle(img, 45, 28 + side * 3, 1.2, (40, 40, 50, 255))
    return _finish(img, 56, 56)


def _snow_hare_img():
    img = _canvas(42, 42)
    _shadow(img, (8, 12, 36, 36), alpha=60, blur=2)
    _ball(img, (8, 12, 30, 30), (236, 240, 246, 255))
    _ball(img, (24, 14, 36, 27), (244, 246, 250, 255))
    for side in (-1, 1):
        _ball(img, (14, 21 + side * 5 - 2, 27, 21 + side * 5 + 2), (226, 230, 238, 255))
        _ball(img, (13, 21 + side * 5 - 1.3, 17, 21 + side * 5 + 1.3), (60, 60, 68, 255), outline=False)  # black tips
    _circle(img, 8, 21, 3.2, (252, 252, 255, 255))
    _circle(img, 33, 19, 1.2, (40, 30, 40, 255))
    _circle(img, 33, 23, 1.2, (40, 30, 40, 255))
    return _finish(img, 42, 42)


def _arctic_wolf_img():
    img = _canvas(68, 68)
    _shadow(img, (8, 16, 64, 60), alpha=85, blur=3)
    art_extra._quad(img, 34, (214, 222, 232), (42, 24), (160, 170, 184), (42, 24, 58, 44))
    _ball(img, (3, 30, 19, 38), (204, 212, 224, 255))                  # tail
    _ball(img, (55, 30, 65, 38), (232, 236, 242, 255))                 # muzzle
    for x in range(16, 44, 5):                                         # thick ruff
        _line(img, [(x, 33), (x + 3, 35)], (190, 200, 214, 255), 1.4)
    for side in (-1, 1):
        _poly(img, [(46, 34 + side * 6), (52, 34 + side * 11), (52, 34 + side * 5)], (176, 186, 200, 255))
    _circle(img, 54, 31, 1.4, (120, 200, 255, 255))                    # icy eyes
    _circle(img, 54, 37, 1.4, (120, 200, 255, 255))
    _circle(img, 65, 34, 1.4, (30, 30, 36, 255))
    return _finish(img, 68, 68)


art_extra.ANIMAL_ART.update({"snow_fox": (_snow_fox_img, 12), "snow_hare": (_snow_hare_img, 9),
                             "arctic_wolf": (_arctic_wolf_img, 15)})


# =========================================================================== item icons
def _whitewood_icon(img):
    for dy in (8, -4):
        _rrect(img, (6, 18 + dy, 40, 30 + dy), 6, (222, 226, 230, 255), (120, 126, 136, 255))
        for x in (14, 22, 30):
            _line(img, [(x, 21 + dy), (x + 3, 21 + dy)], (60, 64, 72, 255), 1.4)    # birch-like marks
        _ball(img, (34, 18 + dy, 44, 30 + dy), (236, 226, 200, 255))
        _circle(img, 39, 24 + dy, 2.2, (200, 180, 140, 255))


def _pelt_icon(img):
    pts = [(10, 10), (24, 6), (38, 10), (42, 24), (36, 40), (24, 44), (12, 40), (6, 24)]
    _poly(img, pts, (236, 240, 248, 255), (160, 170, 186, 255), 1.4)
    for k in range(10):
        a = k / 10 * math.tau
        _line(img, [(24 + math.cos(a) * 8, 25 + math.sin(a) * 8), (24 + math.cos(a) * 14, 25 + math.sin(a) * 14)],
              (206, 214, 228, 255), 1.2)
    _ball(img, (16, 18, 32, 32), (248, 250, 255, 255), outline=False)


def _ice_icon(img):
    pts = [(10, 18), (24, 6), (40, 14), (40, 32), (26, 42), (8, 34)]
    _poly(img, pts, (140, 200, 236, 255), (70, 130, 180, 255), 1.4)
    _poly(img, [(10, 18), (24, 6), (24, 24)], (190, 228, 250, 255))
    _poly(img, [(24, 24), (40, 14), (40, 32)], (110, 170, 214, 255))
    _line(img, [(24, 24), (26, 42)], (230, 246, 255, 220), 1.0)
    _circle(img, 18, 14, 2, (255, 255, 255, 255))


def _hood_icon(img):
    _ball(img, (8, 8, 40, 42), (236, 240, 248, 255))
    _ball(img, (14, 18, 34, 40), (60, 56, 60, 255), outline=False)       # opening
    for side in (-1, 1):
        x = 24 + side * 11
        _poly(img, [(x - 5, 12), (x, 0), (x + 5, 12)], (236, 240, 248, 255), (150, 160, 176, 255), 1.0)  # ears
        _poly(img, [(x - 2.5, 10), (x, 4), (x + 2.5, 10)], (230, 190, 190, 255))
    _ball(img, (16, 22, 32, 36), (226, 196, 170, 255), outline=False)    # face


def _cloak_icon(img):
    _poly(img, [(14, 6), (34, 6), (42, 42), (24, 46), (6, 42)], (232, 236, 246, 255), (150, 160, 180, 255), 1.4)
    _poly(img, [(18, 10), (30, 10), (36, 40), (24, 42), (12, 40)], (246, 248, 255, 200))
    _circle(img, 24, 10, 3, (150, 200, 240, 255))
    for k in range(6):
        x = 9 + k * 6
        _line(img, [(x, 42), (x - 1, 46)], (210, 218, 232, 255), 1.6)


def _warmer_icon(img):
    g = _canvas(48, 48)
    _circle(g, 24, 26, 16, (255, 170, 70, 140))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(4 * S)))
    _rrect(img, (10, 14, 38, 40), 8, (226, 228, 232, 255), (120, 126, 136, 255))
    for x in (16, 24, 32):
        _line(img, [(x, 18), (x + 2, 18)], (60, 64, 72, 255), 1.4)
    _ball(img, (16, 22, 32, 36), (255, 150, 50, 255))
    _circle(img, 22, 27, 2.6, (255, 230, 150, 255))
    _rrect(img, (18, 6, 30, 14), 3, (150, 110, 80, 255), (90, 60, 40, 255))   # leather strap


art.ICON_MAKERS.update({
    "whitewood": _whitewood_icon, "snow_pelt": _pelt_icon, "clear_ice": _ice_icon,
    "snowfox_hood": _hood_icon, "pelt_cloak": _cloak_icon, "hand_warmer": _warmer_icon,
})


# --------------------------------------------------------------------------- worn gear
def _worn_hood():
    img = _canvas(64, 64)
    _ball(img, (21, 20, 41, 44), (236, 240, 248, 255))
    for side in (-1, 1):          # fox ears
        y = 32 + side * 8
        _poly(img, [(26, y - 3), (20, y + side * 3), (28, y + 3)], (236, 240, 248, 255), (150, 160, 176, 255), 0.8)
    _line(img, [(24, 32), (38, 32)], (200, 208, 222, 230), 1.2)
    return _finish(img, 64, 64)


art_gear.HEAD["snowfox_hood"] = _worn_hood
art_gear.CLOAK["pelt_cloak"] = art_gear._cloak((228, 234, 244), (250, 252, 255))

# --------------------------------------------------------------------------- plug into art.tree
_plain_tree = art.tree


def _tree(i):
    return pine(i - PINE_TREE) if PINE_TREE <= i < PINE_TREE + 3 else _plain_tree(i)


art.tree = _tree


def all_textures():
    """Used by --export-art."""
    for i in range(3):
        ground(i)
        pine(i)
        snow_patch(i)
        thaw_patch(i)
        pond(i, True)
        pond(i, False)
    for i in range(6):
        decor(i)
    for i in range(2):
        ice_rock(i)
    whitewood()
    frost_crystal()
    lair()
    for k in ("snow_fox", "snow_hare", "arctic_wolf"):
        art_extra.animal(k)
