"""
terrain_draw.py - the 3D drawing for terrain.py (biome hook draw3d): rivers and the lake (a water surface a
little below the ground with muddy banks), dirt roads, worn ground, cliffs (solid rock blocks), road bridges,
grass / flower clumps and ford stones (shapes3d), bobbers. Built once per world, drawn every frame.
"""
import math

import terrain_map as TM

WATER_Z, BANK_W = -4.0, 16.0


def _patch_view():
    """Our buildings draw as 3D shapes / wall blocks (view3d reads these tables at draw time)."""
    import view3d
    import terrain
    if "bridge" not in view3d.MESH_BUILDS:
        view3d.MESH_BUILDS = tuple(view3d.MESH_BUILDS) + terrain.FLAT_BUILDS
    if "brick_wall" not in view3d.WALL_KINDS:
        view3d.WALL_KINDS = tuple(view3d.WALL_KINDS) + ("brick_wall",)
        view3d.WALL_SIDES["brick_wall"] = (160, 84, 62)


def _tri(out, a, b, c, col):
    for p in (a, b, c):
        out.extend(p)
        out.extend(col)


def _quad(out, a, b, c, d, col_ab, col_cd=None):
    col_cd = col_cd or col_ab
    for p, col in ((a, col_ab), (b, col_ab), (c, col_cd), (a, col_ab), (c, col_cd), (d, col_cd)):
        out.extend(p)
        out.extend(col)


def _build(game, r):
    m = r.m
    gh = game.ground_height
    water, bank, road = [], [], []
    for rv in m.rivers:
        pts, hw = rv.pts, rv.hw
        prev = None
        for i, p in enumerate(pts):
            dx, dy = TM._dir_at(pts, i)
            nx, ny = -dy, dx
            h = gh(*p)
            ford = any(math.hypot(p[0] - f[0], p[1] - f[1]) < 50 for f in m.fords)
            col = (0.42, 0.62, 0.64, 0.85) if ford else (0.17, 0.38, 0.50, 0.9)
            row = [(p[0] + nx * s * (hw[i] + e), p[1] + ny * s * (hw[i] + e)) for s, e in
                   ((-1, BANK_W), (-1, 0), (1, 0), (1, BANK_W))]
            if prev is not None:
                pr, pcol, ph = prev
                z0, z1 = ph + WATER_Z, h + WATER_Z
                _quad(water, (*pr[1], z0), (*pr[2], z0), (*row[2], z1), (*row[1], z1), pcol, col)
                mud = (0.42, 0.33, 0.22, 1.0)
                for o, w in ((0, 1), (3, 2)):
                    _quad(bank, (*pr[o], ph), (*pr[w], ph + WATER_Z - 2), (*row[w], h + WATER_Z - 2),
                          (*row[o], h), mud)
            prev = (row, col, h)
    for lx, ly, lr, s in m.lakes:
        n = 40
        h = gh(lx, ly)
        for k in range(n):
            a0, a1 = k * math.tau / n, (k + 1) * math.tau / n
            r0 = lr * (0.85 + 0.35 * TM.biomes.fbm(s, math.cos(a0) * 1.6 + 5, math.sin(a0) * 1.6 + 5))
            r1 = lr * (0.85 + 0.35 * TM.biomes.fbm(s, math.cos(a1) * 1.6 + 5, math.sin(a1) * 1.6 + 5))
            p0 = (lx + math.cos(a0) * r0, ly + math.sin(a0) * r0)
            p1 = (lx + math.cos(a1) * r1, ly + math.sin(a1) * r1)
            _tri(water, (lx, ly, h + WATER_Z), (*p0, h + WATER_Z), (*p1, h + WATER_Z), (0.16, 0.36, 0.5, 0.9))
            q0 = (lx + math.cos(a0) * (r0 + BANK_W), ly + math.sin(a0) * (r0 + BANK_W))
            q1 = (lx + math.cos(a1) * (r1 + BANK_W), ly + math.sin(a1) * (r1 + BANK_W))
            _quad(bank, (*q0, h), (*p0, h + WATER_Z - 2), (*p1, h + WATER_Z - 2), (*q1, h), (0.42, 0.33, 0.22, 1.0))
    for name, pts in m.roads:
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if m.cell(*a) & TM.WATER or m.cell(*b) & TM.WATER:
                continue
            dx, dy = TM._dir_at(pts, i)
            nx, ny = -dy * TM.ROAD_HALF, dx * TM.ROAD_HALF
            za, zb = gh(*a) + 0.4, gh(*b) + 0.4
            col = (0.55, 0.44, 0.30, 0.9)
            _quad(road, (a[0] - nx, a[1] - ny, za), (a[0] + nx, a[1] + ny, za), (b[0] + nx, b[1] + ny, zb),
                  (b[0] - nx, b[1] - ny, zb), col)
    # cliffs: one rock column per cell, sides where the neighbour is lower
    cliff = []
    N, C = m.N, TM.C
    for k, hgt in m.cliff_h.items():
        ix, iy = k % N, k // N
        x0, y0 = ix * C, iy * C
        x1, y1 = x0 + C, y0 + C
        g = gh(x0 + C / 2, y0 + C / 2)
        top = g + hgt
        v = ((ix * 73 + iy * 31) % 17) / 17 * 0.12
        rock = (0.46 + v, 0.42 + v, 0.37 + v, 1.0)
        dark = (0.26 + v, 0.23 + v, 0.2 + v, 1.0)
        _quad(cliff, (x0, y0, top), (x1, y0, top), (x1, y1, top), (x0, y1, top), (0.40 + v, 0.46 + v, 0.30, 1.0))
        for (nx, ny), (a, b) in (((0, -1), ((x0, y0), (x1, y0))), ((1, 0), ((x1, y0), (x1, y1))),
                                 ((0, 1), ((x1, y1), (x0, y1))), ((-1, 0), ((x0, y1), (x0, y0)))):
            nb = m.cliff_h.get((iy + ny) * N + ix + nx, 0.0)
            if nb < hgt:
                lo = g + nb
                _quad(cliff, (*a, lo), (*b, lo), (*b, top), (*a, top), dark, rock)
    r.geo = {k: game._geo(v) for k, v in (("water", water), ("bank", bank), ("road", road), ("cliff", cliff))}


def draw3d(game, L, vl, stage):
    if vl != "over" or getattr(game, "worldgen", 1) == 1:
        return
    import terrain
    r = terrain.rt(game)
    if r.m is None:
        return
    _patch_view()
    if r.geo is None:
        _build(game, r)
    box = game._progs3d[2]
    ctx = game.ctx
    if stage == "ground":
        ctx.enable(ctx.BLEND)
        for k in ("bank", "water", "road"):
            if r.geo[k]:
                r.geo[k].render(box)
        game.flat(r.worn)
        return
    if r.geo["cliff"]:
        r.geo["cliff"].render(box)
    game.draw_kinds(r.deco)
    game.mesh(r.wbridges, "world_bridge")
