"""
art_lairs.py - painted-in-code pictures for the bosses' lairs (lairs.py).

Same style and assets/ override as art.py (drop e.g. assets/lair_ground_titan.png in to replace one).
  * ground(kind, quiet)   the scorched patch round a lair: dark earth, old bones and a ring of runes that
                          glow in the boss's colour (quiet=True: a beaten lair - the runes have gone grey)
  * altar(kind)           the top of the altar stone (draped over its 3D shape)
  * spire(kind)           a plain block of the spire's stone (its 3D shape has its own colours)
  * bones()               a small heap of bones (draped over the 3D rib cages)
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

from art import _tex

# boss kind -> (stone colour, glow colour) - also used by lairs.py for the 3D shapes and the lights
PALETTE = {
    "titan": ((118, 110, 98), (255, 150, 60)),
    "brood": ((74, 84, 50), (176, 236, 84)),
    "wraith": ((186, 214, 236), (140, 210, 255)),
    "mire": ((70, 62, 46), (90, 232, 200)),
    "colossus": ((40, 34, 38), (255, 112, 40)),
}
DEFAULT = ((110, 104, 96), (255, 140, 80))


def colours(kind):
    return PALETTE.get(kind, DEFAULT)


def _ground_img(kind, quiet):
    stone, glow = colours(kind)
    rnd = random.Random(f"lair-ground-{kind}")
    n = 256
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    # the scorched earth: a dark blot that fades out at the edge
    blot = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(blot)
    dark = tuple(int(c * 0.28) + 8 for c in stone)
    d.ellipse([18, 18, n - 18, n - 18], fill=dark + (215,))
    for _ in range(40):
        a, r = rnd.uniform(0, math.tau), rnd.uniform(70, 112)
        x, y, s = n / 2 + math.cos(a) * r, n / 2 + math.sin(a) * r, rnd.uniform(10, 22)
        d.ellipse([x - s, y - s, x + s, y + s], fill=dark + (rnd.randint(90, 170),))
    img.alpha_composite(blot.filter(ImageFilter.GaussianBlur(9)))
    d = ImageDraw.Draw(img)
    # flagstones round the altar
    for k in range(10):
        a = k / 10 * math.tau + rnd.uniform(-0.1, 0.1)
        r = rnd.uniform(34, 52)
        x, y = n / 2 + math.cos(a) * r, n / 2 + math.sin(a) * r
        c = tuple(int(v * rnd.uniform(0.55, 0.75)) for v in stone)
        d.ellipse([x - 11, y - 8, x + 11, y + 8], fill=c + (235,), outline=tuple(int(v * 0.4) for v in stone) + (255,))
    # the ring of runes
    rune = (120, 118, 116) if quiet else glow
    ring = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    R = 86
    rd.ellipse([n / 2 - R, n / 2 - R, n / 2 + R, n / 2 + R], outline=rune + (150 if not quiet else 90,), width=3)
    for k in range(16):
        a = k / 16 * math.tau
        x, y = n / 2 + math.cos(a) * (R + 9), n / 2 + math.sin(a) * (R + 9)
        pts = [(x + rnd.uniform(-5, 5), y + rnd.uniform(-5, 5)) for _ in range(3)]
        rd.line(pts, fill=rune + (210 if not quiet else 110,), width=2)
    if not quiet:
        img.alpha_composite(ring.filter(ImageFilter.GaussianBlur(3)))
    img.alpha_composite(ring)
    # old bones and ash
    for _ in range(26):
        a, r = rnd.uniform(0, math.tau), rnd.uniform(60, 118)
        x, y = n / 2 + math.cos(a) * r, n / 2 + math.sin(a) * r
        b = rnd.uniform(0, math.pi)
        ln = rnd.uniform(5, 11)
        bone = (214, 206, 186, 230)
        d.line([(x - math.cos(b) * ln, y - math.sin(b) * ln), (x + math.cos(b) * ln, y + math.sin(b) * ln)],
               fill=bone, width=3)
        for sgn in (-1, 1):
            ex, ey = x + sgn * math.cos(b) * ln, y + sgn * math.sin(b) * ln
            d.ellipse([ex - 2.5, ey - 2.5, ex + 2.5, ey + 2.5], fill=bone)
    for _ in range(60):
        x, y, s = rnd.uniform(30, n - 30), rnd.uniform(30, n - 30), rnd.uniform(1, 2.6)
        if math.hypot(x - n / 2, y - n / 2) < 116:
            d.ellipse([x - s, y - s, x + s, y + s], fill=(60, 56, 54, 200))
    return img


def ground(kind, quiet=False):
    return _tex(f"lair_ground_{kind}{'_quiet' if quiet else ''}", lambda: _ground_img(kind, quiet))


def _altar_img(kind):
    stone, glow = colours(kind)
    n = 64
    img = Image.new("RGBA", (n, n), stone + (255,))
    d = ImageDraw.Draw(img)
    rnd = random.Random(f"lair-altar-{kind}")
    for _ in range(50):
        x, y, s = rnd.uniform(0, n), rnd.uniform(0, n), rnd.uniform(2, 6)
        f = rnd.uniform(0.8, 1.15)
        d.ellipse([x - s, y - s, x + s, y + s], fill=tuple(min(255, int(c * f)) for c in stone) + (255,))
    d.ellipse([16, 16, n - 16, n - 16], outline=tuple(int(c * 0.5) for c in stone) + (255,), width=3)
    for k in range(6):
        a = k / 6 * math.tau
        x, y = n / 2 + math.cos(a) * 22, n / 2 + math.sin(a) * 22
        d.line([(x - 2, y - 3), (x + 1, y), (x - 1, y + 3)], fill=glow + (255,), width=2)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def altar(kind):
    return _tex(f"lair_altar_{kind}", lambda: _altar_img(kind))


def spire(kind):
    stone, _ = colours(kind)
    return _tex(f"lair_spire_{kind}", lambda: Image.new("RGBA", (64, 64), stone + (255,)))


def _bones_img():
    n = 48
    img = Image.new("RGBA", (n, n), (204, 196, 176, 255))
    d = ImageDraw.Draw(img)
    rnd = random.Random("lair-bones")
    for _ in range(30):
        x, y, s = rnd.uniform(0, n), rnd.uniform(0, n), rnd.uniform(2, 5)
        d.ellipse([x - s, y - s, x + s, y + s], fill=(rnd.randint(170, 226),) * 3 + (255,))
    return img


def bones():
    return _tex("lair_bones", _bones_img)


def all_textures():
    """Make every picture once (main.py --export-art)."""
    for kind in PALETTE:
        ground(kind)
        ground(kind, True)
        altar(kind)
        spire(kind)
    bones()
