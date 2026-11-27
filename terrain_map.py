"""
terrain_map.py - the shape of the land for terrain.py: rivers (with fords and lakes), worn dirt roads from the
spawn to every region (bridged where they cross water), and cliffs / rock ledges. Worldgen 2+ only.

Everything here is a PURE function of the layout (seed + size), built once per world and cached, so the host,
every co-op client and every load of a save get exactly the same map without sending anything. It has to work
before the game object exists: world._build_v2 asks biomes.keepout(layout, x, y) while it places the shared
trees, rocks, ponds and cave entrances, and that reads this map.

Randomness: one private stream, random.Random(f"{seed}:meadow:land") (never the global random), plus the
deterministic biomes.noise / fbm.

The map is a grid of C x C px cells holding bit flags (WATER, DEEP, FORD, BANK, CLIFF, ROAD, BRIDGE, KEEP).
After drawing it, a flood fill from the spawn checks that every bit of dry land can be reached (through fords
and road bridges); cliffs that would cut a region off are dropped and extra fords are added where rivers
enclose a pocket, until everything is connected.
"""
import math
import random
from array import array
from collections import deque

import biomes

C = 20                       # cell size (px)
WATER, DEEP, FORD, BANK, CLIFF, ROAD, BRIDGE, KEEP = 1, 2, 4, 8, 16, 32, 64, 128
SPAWN_CLEAR = 680            # rivers never come closer than this to the spawn
CLIFF_CLEAR = 820            # ...nor do cliffs
ROAD_HALF = 22               # half width of a dirt road
BANK_W = 36                  # the river bank (clay, reeds) past the water's edge
KEEP_W = 64                  # shared trees / rocks / ponds stay this far from water
FORD_EVERY = 820             # a shallow ford about this often along a river (px of river length)

_cache = {}


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def get(layout):
    """The TerrainMap for this layout (None on legacy worlds). Cached per seed / size."""
    if getattr(layout, "version", 1) == biomes.LEGACY:
        return None
    key = (layout.seed, layout.size, layout.version)
    m = _cache.get(key)
    if m is None:
        if len(_cache) > 3:
            _cache.clear()
        m = _cache[key] = TerrainMap(layout)
    return m


# =========================================================================== polylines
def _catmull(pts, step=24.0):
    """A smooth curve through the points, resampled about every `step` px."""
    if len(pts) < 2:
        return list(pts)
    p = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        n = max(2, int(_dist(p1, p2) / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(pts[-1])
    return out


def _resample(pts, step=24.0):
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = _dist(a, b)
        if d < 1e-6:
            continue
        t = step - acc
        while t <= d:
            out.append((a[0] + (b[0] - a[0]) * t / d, a[1] + (b[1] - a[1]) * t / d))
            t += step
        acc = d - (t - step)
    if _dist(out[-1], pts[-1]) > step * 0.3:
        out.append(pts[-1])
    return out


def _meander(pts, s, amp, wave=420.0):
    """Wiggle a polyline sideways with smooth noise (amp px), keeping both ends put."""
    out = []
    L = 0.0
    total = sum(_dist(a, b) for a, b in zip(pts, pts[1:])) or 1.0
    for i, p in enumerate(pts):
        if i:
            L += _dist(pts[i - 1], p)
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n
        fade = min(1.0, L / 300.0, (total - L) / 300.0)
        off = (biomes.fbm(s, L / wave, 0.37, 3) - 0.5) * 2.0 * amp * fade
        out.append((p[0] + nx * off, p[1] + ny * off))
    return out


def _lengths(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + _dist(a, b))
    return s


def _dir_at(pts, i):
    a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def seg_dist(p, a, b):
    """(distance from p to segment ab, t along it 0..1)."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - ax - dx * t, p[1] - ay - dy * t), t


# =========================================================================== the map
class River:
    def __init__(self, pts, hw):
        self.pts = pts
        self.hw = hw                 # half width at each point
        self.s = _lengths(pts)
        self.length = self.s[-1]


class TerrainMap:
    def __init__(self, layout):
        self.layout = layout
        self.size = S = layout.size
        self.N = N = int(math.ceil(S / C)) + 1
        self.flags = bytearray(N * N)
        self.edge = array("f", [1e9]) * (N * N)       # signed distance to the nearest water edge (px)
        self.flow = {}                                # cell -> (dx, dy) river direction (water cells)
        self.rng = random.Random(f"{layout.seed}:meadow:land")
        self.rivers, self.lakes, self.fords, self.bridges, self.roads, self.cliffs = [], [], [], [], [], []
        self.cliff_h = {}                             # cell -> wall height (px)
        self.pond0 = self._spawn_pond()
        self._make_rivers()
        self._paint_water()
        self._make_fords()
        self._make_roads()
        self._make_cliffs()
        self._connect()
        self.crossings = [(f[0], f[1]) for f in self.fords] + [(b[0], b[1]) for b in self.bridges]

    # ------------------------------------------------------------------ queries (fast)
    def cell(self, x, y):
        i, j = int(x // C), int(y // C)
        if 0 <= i < self.N and 0 <= j < self.N:
            return self.flags[j * self.N + i]
        return 0

    def edge_at(self, x, y):
        i, j = int(x // C), int(y // C)
        if 0 <= i < self.N and 0 <= j < self.N:
            return self.edge[j * self.N + i]
        return 1e9

    def blocked(self, x, y):
        f = self.cell(x, y)
        return bool((f & DEEP and not f & BRIDGE) or f & CLIFF)

    # ------------------------------------------------------------------ generation
    def _spawn_pond(self):
        """world._build_v2 always puts pond 0 a short walk from spawn (with its own stream): steer clear of it."""
        ri = random.Random(f"{self.layout.seed}:world:pond:0")
        a = ri.uniform(0, math.tau)
        cx, cy = self.layout.centre
        return cx + math.cos(a) * 360, cy + math.sin(a) * 300

    def _polar(self, ang, r):
        cx, cy = self.layout.centre
        return cx + math.cos(ang) * r, cy + math.sin(ang) * r

    def _ring_angle(self, name, frac=0.5):
        lay = self.layout
        i = lay.ring.index(name)
        return lay.rot + (i + frac) * lay.wedge

    def _river_line(self, way, amp, sname):
        pts = _catmull(way, 60.0)
        pts = _meander(pts, biomes.seed_int(self.layout.seed, sname), amp)
        pts = _resample(pts, 24.0)
        # never into the spawn clearing, never off the map
        cx, cy = self.layout.centre
        out = []
        for x, y in pts:
            d = math.hypot(x - cx, y - cy)
            if d < SPAWN_CLEAR:
                k = SPAWN_CLEAR / max(d, 1.0)
                x, y = cx + (x - cx) * k, cy + (y - cy) * k
            out.append((max(-40.0, min(self.size + 40.0, x)), max(-40.0, min(self.size + 40.0, y))))
        return _resample(out, 24.0)

    def _make_rivers(self):
        r, S, lay = self.rng, self.size, self.layout
        fr = lay.forest_r
        am = self._ring_angle("meadow")
        side = r.choice((-1, 1))                     # which way the big river bends round the forest
        w = lay.wedge
        # 1. the great river: in from the meadow's outer edge, round the forest, out through the next region
        way = [self._polar(am + side * 0.1 * w, S * 0.75),
               self._polar(am + side * 0.05 * w, S * 0.40),
               self._polar(am - side * 0.08 * w, fr * 1.02),
               self._polar(am + side * 0.30 * w, fr * 0.78),
               self._polar(am + side * 0.62 * w, fr * 0.80),
               self._polar(am + side * 0.95 * w, fr * 1.05),
               self._polar(am + side * 1.18 * w, S * 0.36),
               self._polar(am + side * 1.25 * w, S * 0.75)]
        main = self._river_line(way, 110, "river-main")
        # 2. a tributary from the meadow's far side, joining the great river at its first bend
        join = way[2]
        t_way = [self._polar(am - side * 0.42 * w, S * 0.75),
                 self._polar(am - side * 0.40 * w, S * 0.36),
                 self._polar(am - side * 0.22 * w, fr * 1.3),
                 join]
        trib = self._river_line(t_way, 80, "river-trib")
        # 3. a stream across the far side of the map that ends in a lake at the forest's edge
        ao = am + math.pi + r.uniform(-0.35, 0.35) * w
        lake = self._polar(ao, fr * 1.08)
        s_way = [self._polar(ao + 0.25 * w, S * 0.75), self._polar(ao + 0.18 * w, S * 0.38),
                 self._polar(ao + 0.05 * w, fr * 1.5), lake]
        stream = self._river_line(s_way, 90, "river-stream")
        for pts, base, sname in ((main, 58.0, "w-main"), (trib, 46.0, "w-trib"), (stream, 40.0, "w-stream")):
            s = biomes.seed_int(lay.seed, sname)
            hw = []
            L = 0.0
            for i, p in enumerate(pts):
                if i:
                    L += _dist(pts[i - 1], p)
                meadow = lay.biome_at(p[0], p[1]) == "meadow"
                hw.append(base * (1.1 if meadow else 0.9) + (biomes.fbm(s, L / 300.0, 0.5) - 0.5) * 16)
            self.rivers.append(River(pts, hw))
        self.lakes.append((lake[0], lake[1], 175.0 + r.uniform(0, 50), biomes.seed_int(lay.seed, "lake")))

    def _paint_water(self):
        N, edge = self.N, self.edge
        reach = KEEP_W + 8
        for ri, rv in enumerate(self.rivers):
            pts, hw = rv.pts, rv.hw
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                h = max(hw[i], hw[i + 1])
                R = h + reach
                x0, x1 = int((min(a[0], b[0]) - R) // C), int((max(a[0], b[0]) + R) // C)
                y0, y1 = int((min(a[1], b[1]) - R) // C), int((max(a[1], b[1]) + R) // C)
                dx, dy = b[0] - a[0], b[1] - a[1]
                n = math.hypot(dx, dy) or 1.0
                fl = (dx / n, dy / n)
                for ix in range(max(0, x0), min(N, x1 + 1)):
                    px = ix * C + C / 2
                    for iy in range(max(0, y0), min(N, y1 + 1)):
                        py = iy * C + C / 2
                        d, t = seg_dist((px, py), a, b)
                        e = d - (hw[i] + (hw[i + 1] - hw[i]) * t)
                        k = iy * N + ix
                        if e < edge[k]:
                            edge[k] = e
                            if e < 8:
                                self.flow[k] = fl
        for lx, ly, lr, s in self.lakes:
            R = lr * 1.3 + reach
            for ix in range(max(0, int((lx - R) // C)), min(N, int((lx + R) // C) + 1)):
                px = ix * C + C / 2
                for iy in range(max(0, int((ly - R) // C)), min(N, int((ly + R) // C) + 1)):
                    py = iy * C + C / 2
                    ang = math.atan2(py - ly, px - lx)
                    rr = lr * (0.85 + 0.35 * biomes.fbm(s, math.cos(ang) * 1.6 + 5, math.sin(ang) * 1.6 + 5))
                    e = math.hypot(px - lx, py - ly) - rr
                    k = iy * N + ix
                    if e < edge[k]:
                        edge[k] = e
        F = self.flags
        for k in range(N * N):
            e = edge[k]
            if e < 0:
                F[k] = WATER | DEEP | KEEP
            elif e < BANK_W:
                F[k] = BANK | KEEP
            elif e < KEEP_W:
                F[k] = KEEP

    def _ford_at(self, rv, i):
        """Make a shallow ford across river rv at point i."""
        p = rv.pts[i]
        dx, dy = _dir_at(rv.pts, i)
        hw = rv.hw[i]
        N, F = self.N, self.flags
        R = hw + 40
        for ix in range(max(0, int((p[0] - R) // C)), min(N, int((p[0] + R) // C) + 1)):
            px = ix * C + C / 2
            for iy in range(max(0, int((p[1] - R) // C)), min(N, int((p[1] + R) // C) + 1)):
                py = iy * C + C / 2
                along = (px - p[0]) * dx + (py - p[1]) * dy
                across = -(px - p[0]) * dy + (py - p[1]) * dx
                if abs(along) < 38 and abs(across) < hw + 30:
                    k = iy * N + ix
                    if F[k] & WATER:
                        F[k] = (F[k] & ~DEEP) | FORD
        self.fords.append((p[0], p[1], math.atan2(dy, dx), hw))

    def _near_other_water(self, p, rv, hw):
        for o in self.rivers:
            if o is rv:
                continue
            for q in o.pts[::2]:
                if _dist(p, q) < hw * 2 + 140:
                    return True
        for lx, ly, lr, _ in self.lakes:
            if _dist(p, (lx, ly)) < lr * 1.3 + hw + 100:
                return True
        return False

    def _make_fords(self):
        r = self.rng
        for rv in self.rivers:
            target = r.uniform(420, 620)
            for i, p in enumerate(rv.pts):
                if rv.s[i] < target:
                    continue
                if not (90 < p[0] < self.size - 90 and 90 < p[1] < self.size - 90) or \
                        self._near_other_water(p, rv, rv.hw[i]):
                    continue
                self._ford_at(rv, i)
                target = rv.s[i] + FORD_EVERY * r.uniform(0.8, 1.2)

    # ------------------------------------------------------------------ roads
    def _make_roads(self):
        lay = self.layout
        cx, cy = lay.centre
        N, F = self.N, self.flags
        for name in lay.ring:
            tx, ty = lay.centres[name]
            a = math.atan2(ty - cy, tx - cx)
            start = (cx + math.cos(a) * 150, cy + math.sin(a) * 150)
            mid = ((start[0] + tx) / 2, (start[1] + ty) / 2)
            way = [start, mid, (tx - math.cos(a) * 170, ty - math.sin(a) * 170)]
            pts = _resample(_meander(_resample(way, 30.0), biomes.seed_int(lay.seed, "road-" + name), 120, 520), 16.0)
            # bend round the pond next to spawn
            px, py = self.pond0
            out = []
            for x, y in pts:
                d = math.hypot(x - px, y - py)
                if d < 175:
                    k = 175 / max(d, 1.0)
                    x, y = px + (x - px) * k, py + (y - py) * k
                out.append((x, y))
            pts = _resample(out, 16.0)
            self.roads.append((name, pts))
            # bridges where it crosses water
            run = []
            for i, p in enumerate(pts + [None]):
                wet = p is not None and self.edge_at(*p) < 6
                if wet:
                    run.append(i)
                elif run:
                    self._bridge(pts, run[0], run[-1])
                    run = []
            for x, y in pts:
                R = ROAD_HALF + 4
                for ix in range(max(0, int((x - R) // C)), min(N, int((x + R) // C) + 1)):
                    for iy in range(max(0, int((y - R) // C)), min(N, int((y + R) // C) + 1)):
                        if math.hypot(ix * C + C / 2 - x, iy * C + C / 2 - y) < R:
                            k = iy * N + ix
                            F[k] |= ROAD | KEEP

    def _bridge(self, pts, i0, i1):
        """A wooden bridge carrying a road over the water between road points i0..i1."""
        a = pts[max(0, i0 - 2)]
        b = pts[min(len(pts) - 1, i1 + 2)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        a = (a[0] - ux * 14, a[1] - uy * 14)
        L += 28
        mx, my = a[0] + ux * L / 2, a[1] + uy * L / 2
        half_w = 34
        N, F = self.N, self.flags
        R = L / 2 + half_w + C
        for ix in range(max(0, int((mx - R) // C)), min(N, int((mx + R) // C) + 1)):
            px = ix * C + C / 2
            for iy in range(max(0, int((my - R) // C)), min(N, int((my + R) // C) + 1)):
                py = iy * C + C / 2
                along = (px - mx) * ux + (py - my) * uy
                across = -(px - mx) * uy + (py - my) * ux
                if abs(along) < L / 2 and abs(across) < half_w - 4:
                    F[iy * N + ix] |= BRIDGE | KEEP
        self.bridges.append((mx, my, math.atan2(uy, ux), L, half_w * 2))

    # ------------------------------------------------------------------ cliffs
    def _make_cliffs(self):
        r, lay, S = self.rng, self.layout, self.size
        cx, cy = lay.centre
        N, F = self.N, self.flags
        want = {"highlands": 6, "ash": 3, "tundra": 3, "meadow": 2, "mire": 1, "forest": 2}
        for name, count in want.items():
            made = 0
            for _ in range(count * 30):
                if made >= count:
                    break
                if name == "forest":
                    a, d = r.uniform(0, math.tau), r.uniform(CLIFF_CLEAR, lay.forest_r * 1.05)
                    p = (cx + math.cos(a) * d, cy + math.sin(a) * d)
                else:
                    p = (r.uniform(300, S - 300), r.uniform(300, S - 300))
                if lay.biome_at(*p) != name or _dist(p, (cx, cy)) < CLIFF_CLEAR:
                    continue
                if any(_dist(p, c) < 420 for c in lay.centres.values()):
                    continue          # keep the lairs / landmarks open
                ang = r.uniform(0, math.tau)
                n = r.randint(6, 13)
                bend = r.uniform(-0.25, 0.25)
                pts = [p]
                for k in range(n):
                    ang += bend + r.uniform(-0.2, 0.2)
                    q = pts[-1]
                    pts.append((q[0] + math.cos(ang) * 44, q[1] + math.sin(ang) * 44))
                thick = r.uniform(34, 52)
                cells = self._cliff_cells(pts, thick)
                if cells is None:
                    continue
                for k in cells:
                    F[k] |= CLIFF | KEEP
                self.cliffs.append([pts, thick, cells])
                made += 1
        hs = biomes.seed_int(lay.seed, "cliff-h")
        for pts, thick, cells in self.cliffs:
            for k in cells:
                ix, iy = k % N, k // N
                self.cliff_h[k] = 70 + 60 * biomes.fbm(hs, ix / 5.0, iy / 5.0)

    def _cliff_cells(self, pts, thick):
        """Cells under a cliff line, or None if it would touch water, roads, other cliffs or the map edge."""
        N, F = self.N, self.flags
        out = set()
        R = thick / 2
        pad = 70
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            for ix in range(int((min(ax, bx) - R - pad) // C), int((max(ax, bx) + R + pad) // C) + 1):
                for iy in range(int((min(ay, by) - R - pad) // C), int((max(ay, by) + R + pad) // C) + 1):
                    if not (4 <= ix < N - 4 and 4 <= iy < N - 4):
                        return None
                    d, _ = seg_dist((ix * C + C / 2, iy * C + C / 2), (ax, ay), (bx, by))
                    k = iy * N + ix
                    if d < R + pad and F[k] & (WATER | ROAD | CLIFF | BRIDGE | BANK):
                        return None
                    if d < R:
                        out.add(k)
        return sorted(out)

    # ------------------------------------------------------------------ everything reachable
    def passable(self, k):
        f = self.flags[k]
        return not ((f & DEEP and not f & BRIDGE) or f & CLIFF)

    def flood(self, start):
        """Set of reachable cells from the spawn, moving between passable neighbours (a bytearray mask)."""
        N = self.N
        seen = bytearray(N * N)
        i, j = int(start[0] // C), int(start[1] // C)
        k0 = j * N + i
        if not self.passable(k0):
            return seen
        seen[k0] = 1
        q = deque([k0])
        F = self.flags
        while q:
            k = q.popleft()
            x = k % N
            for nk in ((k - 1) if x > 0 else -1, (k + 1) if x < N - 1 else -1, k - N, k + N):
                if 0 <= nk < N * N and not seen[nk]:
                    f = F[nk]
                    if (f & DEEP and not f & BRIDGE) or f & CLIFF:
                        continue
                    seen[nk] = 1
                    q.append(nk)
        return seen

    def _connect(self):
        """Drop cliffs / add fords until every dry cell inside the map is reachable from the spawn."""
        N, F = self.N, self.flags
        lo, hi = int(60 // C), int((self.size - 60) // C)
        for _ in range(12):
            seen = self.flood(self.layout.centre)
            lost = [j * N + i for j in range(lo, hi) for i in range(lo, hi)
                    if not seen[j * N + i] and self.passable(j * N + i)]
            self.unreached = len(lost)
            if not lost:
                return
            lost_set = set(lost)
            # a cliff touching the lost land? drop it
            dropped = False
            for c in list(self.cliffs):
                cells = c[2]
                if any((k + d) in lost_set for k in cells for d in (1, -1, N, -N)):
                    for k in cells:
                        F[k] &= ~(CLIFF | KEEP)
                    self.cliffs.remove(c)
                    dropped = True
            if dropped:
                continue
            # water in the way: a ford at the river point nearest the biggest lost pocket
            k = lost[len(lost) // 2]
            p = ((k % N) * C + C / 2, (k // N) * C + C / 2)
            best = None
            for rv in self.rivers:
                for i, q in enumerate(rv.pts):
                    d = _dist(p, q)
                    if best is None or d < best[0]:
                        best = (d, rv, i)
            if best is None:
                break
            self._ford_at(best[1], best[2])
        seen = self.flood(self.layout.centre)
        self.unreached = sum(1 for j in range(lo, hi) for i in range(lo, hi)
                             if not seen[j * N + i] and self.passable(j * N + i))
