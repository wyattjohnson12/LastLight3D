"""
hills.py - REAL HILLS: a ground height map for the surface (worldgen 2+ only).

What it does
  * height(game, x, y): smooth rolling hills from seeded noise (biomes.fbm), with an amplitude per biome
    (gentle forest and meadow, bigger tundra / ash, the Stone Highlands the highest, the Mire flat). The ground
    is flattened around the spawn centre, ponds, cave entrances and any water a module reports
    (game.terrain_water: rivers), so water always sits in flat valleys. Old worlds (worldgen 1), the cave and
    every other layer stay perfectly flat.
  * It's a pure function of the seed + layout + the generated ponds / exits, so every computer agrees. The
    noise is worked out ONCE per world on a 64 px grid (about 0.1 s) and looked up with bilinear filtering,
    so a call costs about a microsecond.
  * speed_at: walking uphill is slower, downhill a little faster (main.move_player multiplies it in).
  * render_grid(game) / ground_z(game, x, y): the TOTAL height (game.ground_height, i.e. every module's
    height hook summed) on the same grid. The 3D view (terrain3d.py + view3d.py) uploads it as a texture
    and lifts the ground mesh and everything standing on it by it, so what you see and ground_z() agree.

Other modules may add their own height on top (a highlands plateau, terrain cliffs): just register a
`height` hook; it is summed by game.ground_height and picked up by render_grid automatically.
"""
import math

import biomes

NAME = "hills"

CELL = 64                 # grid spacing (px). The 256 px ground tiles are split into 4 x 4 quads on this grid
ORIGIN = -128.0           # grid point 0 (the ground tiles' outer edge: they're centred on multiples of 256)
AMP = {"forest": 62, "meadow": 52, "tundra": 92, "ash": 84, "highlands": 185, "mire": 0}
DEFAULT_AMP = 55
BASE = {"highlands": 80, "tundra": 14, "ash": 10}    # a raised plateau under the hills (px); ponds sit on it
SPAWN_FLAT = (300.0, 720.0)     # fully flat inside, full hills outside (distance from the centre)
WATER_FLAT_CELLS = 4            # how many cells it takes to climb out of a river valley
UPHILL = 0.8                    # speed lost per unit of uphill slope
UPHILL_MIN = 0.6
DOWNHILL = 0.35                 # speed gained per unit of downhill slope...
DOWNHILL_MAX = 1.15             # ...up to this


def _smooth(e0, e1, x):
    t = (x - e0) / (e1 - e0)
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return t * t * (3 - 2 * t)


class Grid:
    """Heights on a square grid of n x n points, CELL apart, starting at (ORIGIN, ORIGIN)."""

    def __init__(self, n, vals):
        self.n, self.v = n, vals
        self.hmax = max(vals) if vals else 0.0

    def at(self, x, y):
        n = self.n
        fx = (x - ORIGIN) / CELL
        fy = (y - ORIGIN) / CELL
        if fx < 0:
            fx = 0.0
        elif fx > n - 1.001:
            fx = n - 1.001
        if fy < 0:
            fy = 0.0
        elif fy > n - 1.001:
            fy = n - 1.001
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        v = self.v
        k = j * n + i
        a, b = v[k], v[k + 1]
        c, d = v[k + n], v[k + n + 1]
        return a + (b - a) * tx + (c - a) * ty + (a - b - c + d) * tx * ty


def _size_n(game):
    size = game.world_size
    last = (size // 256 + 1) * 256 + 128      # the far edge of the last ground tile
    return int(math.ceil((last - ORIGIN) / CELL)) + 1


def _blur(vals, n, r):
    """Separable box blur (radius r cells), edges clamped."""
    out = [0.0] * (n * n)
    w = 2 * r + 1
    for j in range(n):
        row = j * n
        for i in range(n):
            s = 0.0
            for k in range(i - r, i + r + 1):
                s += vals[row + (0 if k < 0 else n - 1 if k >= n else k)]
            out[row + i] = s / w
    res = [0.0] * (n * n)
    for i in range(n):
        for j in range(n):
            s = 0.0
            for k in range(j - r, j + r + 1):
                s += out[(0 if k < 0 else n - 1 if k >= n else k) * n + i]
            res[j * n + i] = s / w
    return res


def _water_dist(game, n):
    """Grid steps from each point to the nearest water a module reports (capped), or None if no water hook."""
    if not biomes.with_hook("water"):
        return None
    m = 2 * n - 1                 # sample water on a half-cell lattice (rivers can be narrower than a cell)
    wet_l = bytearray(m * m)
    tw = game.terrain_water
    for b in range(m):
        y = ORIGIN + b * CELL / 2
        for a in range(m):
            if tw(ORIGIN + a * CELL / 2, y, "over"):
                wet_l[b * m + a] = 1
    cap = WATER_FLAT_CELLS + 1
    dist = [cap] * (n * n)
    front = []
    for j in range(n):
        for i in range(n):
            a, b = 2 * i, 2 * j
            if any(wet_l[bb * m + aa] for aa in (a - 1, a, a + 1) for bb in (b - 1, b, b + 1)
                   if 0 <= aa < m and 0 <= bb < m):
                dist[j * n + i] = 0
                front.append((i, j))
    for step in range(1, cap):
        nxt = []
        for i, j in front:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                ii, jj = i + di, j + dj
                if 0 <= ii < n and 0 <= jj < n and dist[jj * n + ii] > step:
                    dist[jj * n + ii] = step
                    nxt.append((ii, jj))
        front = nxt
    return dist


def _build(game):
    """This module's own heights for the whole surface (worldgen 2+)."""
    n = _size_n(game)
    lay = game.layout
    s = biomes.seed_int(game.seed, "hills")
    amp = [0.0] * (n * n)
    base = [0.0] * (n * n)
    pts = [(ORIGIN + i * CELL) for i in range(n)]
    for j, y in enumerate(pts):
        for i, x in enumerate(pts):
            b = lay.biome_at(x, y)
            amp[j * n + i] = AMP.get(b, DEFAULT_AMP)
            base[j * n + i] = BASE.get(b, 0.0)
    amp = _blur(_blur(amp, n, 2), n, 2)          # soft ramps between biomes (about +-250 px)
    base = _blur(_blur(base, n, 3), n, 3)
    cx, cy = lay.centre
    over = game.layers["over"]
    flats = [(p.center_x, p.center_y, max(p.width, p.height) / 2 + 30, 260) for p in over.ponds]
    flats += [(e.center_x, e.center_y, 70, 200) for e in over.exits]

    def base_at(x, y):
        i = max(0, min(n - 1, int(round((x - ORIGIN) / CELL))))
        j = max(0, min(n - 1, int(round((y - ORIGIN) / CELL))))
        return base[j * n + i]
    flats = [(x, y, r0, ramp, base_at(x, y)) for x, y, r0, ramp in flats]
    wd = _water_dist(game, n)
    fbm = biomes.fbm
    vals = [0.0] * (n * n)
    for j, y in enumerate(pts):
        for i, x in enumerate(pts):
            k = j * n + i
            a = amp[k]
            f = _smooth(SPAWN_FLAT[0], SPAWN_FLAT[1], math.hypot(x - cx, y - cy))
            if wd is not None:
                f *= _smooth(0.6, WATER_FLAT_CELLS, wd[k])          # rivers run in the valleys
            if f <= 0:
                continue
            fw = f
            plat = base[k]
            for fx, fy, r0, ramp, pb in flats:
                dx, dy = x - fx, y - fy
                if abs(dx) < r0 + ramp and abs(dy) < r0 + ramp:
                    w = _smooth(r0, r0 + ramp, math.hypot(dx, dy))
                    f *= w
                    plat = pb + (plat - pb) * w      # ponds lie level, even on a sloping plateau
            vals[k] = plat * fw
            if a <= 0.5 or f <= 0:
                continue
            shape = _smooth(0.3, 0.78, fbm(s, x / 1050.0, y / 1050.0, 4))      # broad rolling hills
            detail = fbm(s + 7, x / 400.0, y / 400.0, 2)                          # smaller bumps on them
            vals[k] += a * f * shape * (0.72 + 0.56 * detail)
    return Grid(n, vals)


def _key(game):
    return (game.seed, game.worldgen, id(game.layers.get("over")))


def grid(game):
    """This module's height grid (None on old flat worlds)."""
    if getattr(game, "worldgen", biomes.LEGACY) == biomes.LEGACY or not hasattr(game, "layers"):
        return None
    c = game.__dict__.get("_hills_grid")
    key = _key(game)
    if c is not None and c[0] == key:
        return c[1]
    if game.__dict__.get("_hills_building"):
        return None                   # a water / blocked hook asked for the height while we build: flat
    game._hills_building = True
    try:
        g = _build(game)
    finally:
        game._hills_building = False
    game._hills_grid = (key, g)
    return g


def height(game, x, y):
    """Ground height (px) at surface point (x, y) from this module (0 on old worlds)."""
    g = grid(game)
    return g.at(x, y) if g is not None else 0.0


def render_grid(game):
    """The TOTAL ground height (every module's height hook) on the hills grid, for the 3D view.
    None when the surface is flat everywhere (old worlds)."""
    if getattr(game, "worldgen", biomes.LEGACY) == biomes.LEGACY or not hasattr(game, "layers"):
        return None
    c = game.__dict__.get("_hills_total")
    key = _key(game)
    if c is not None and c[0] == key:
        return c[1]
    own = grid(game)
    others = [b for b in biomes.with_hook("height") if b.name != NAME]
    if own is None and not others:
        g = None
    elif not others:
        g = own
    else:
        n = _size_n(game)
        vals = list(own.v) if own is not None else [0.0] * (n * n)
        for j in range(n):
            y = ORIGIN + j * CELL
            for i in range(n):
                x = ORIGIN + i * CELL
                vals[j * n + i] += sum(b.height(game, x, y) for b in others)
        g = Grid(n, vals)
    if g is not None and g.hmax <= 0.01 and min(g.v) >= -0.01:
        g = None
    game._hills_total = (key, g)
    return g


def ground_z(game, x, y):
    """Total ground height for drawing (matches the 3D ground mesh). 0 on flat worlds."""
    g = render_grid(game)
    return g.at(x, y) if g is not None else 0.0


def speed_at(game, p, dx, dy):
    """Uphill is slower, downhill a little faster (runs on the computer that moves p)."""
    if p.layer != "over" or not (dx or dy) or getattr(game, "worldgen", 1) == biomes.LEGACY:
        return 1.0
    n = math.hypot(dx, dy)
    ux, uy = dx / n * 20.0, dy / n * 20.0
    x, y = p.pos
    slope = (game.ground_height(x + ux, y + uy) - game.ground_height(x - ux, y - uy)) / 40.0
    if slope > 0:
        return max(UPHILL_MIN, 1.0 - UPHILL * slope)
    return min(DOWNHILL_MAX, 1.0 - DOWNHILL * slope)


biomes.register(biomes.Biome(
    NAME, title="Hills", order=70, region=False, legacy=False,
    height=height,
    speed_at=speed_at,
))
