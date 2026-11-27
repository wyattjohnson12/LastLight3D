"""
terrain_draw.py - the 3D drawing for terrain.py (biome hook draw3d): rivers and the lake (a water surface a
little below the ground with muddy banks), dirt roads, worn ground, cliffs (solid rock blocks), road bridges,
grass / flower clumps and ford stones (shapes3d), bobbers. Built once per world, drawn every frame.
"""
import math

import terrain_map as TM
import water3d

BANK_W = 16.0


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


def _bank(out, inner, outer, z_in, z_out):
    """A strip of wet mud lying on the ground from just under the water's edge out onto the grass
    (inner / outer: two points each, along the edge). Fades out into the grass at the far side."""
    wet, dry = (0.36, 0.28, 0.19, 1.0), (0.45, 0.36, 0.24, 0.5)
    _quad(out, (*inner[0], z_in[0]), (*inner[1], z_in[1]), (*outer[1], z_out[1]), (*outer[0], z_out[0]), wet, dry)


def _build(game, r):
    """Water (water3d.py: moving ripples, sky, glints, foam), mud banks, roads and cliffs, once per world.
    The water and banks lie ON the ground (a hair above it): on hilly worlds the ground mesh is depth tested,
    and water sunk below it would be hidden."""
    m = r.m
    gh = game.ground_height
    water, bank, road = [], [], []
    bz = water3d.BANK_LIFT
    for rv in m.rivers:
        pts, hw = rv.pts, rv.hw
        prev = None
        for i, p in enumerate(pts):
            dx, dy = TM._dir_at(pts, i)
            nx, ny = -dy, dx
            ford = any(math.hypot(p[0] - f[0], p[1] - f[1]) < 50 for f in m.fords)
            sp = water3d.flow_speed(hw[i], ford)
            flow, depth = (dx * sp, dy * sp), (0.3 if ford else 1.0)
            # across the river: outer bank, bank under the water, water's edge, middle, other edge...
            offs = (-hw[i] - BANK_W, -hw[i] + 6, -hw[i], 0.0, hw[i], hw[i] - 6, hw[i] + BANK_W)
            row = [(p[0] + nx * o, p[1] + ny * o) for o in offs]
            z = [gh(*q) for q in row]
            # where another river or the lake carries on past this edge (a junction, the stream's mouth) the
            # water is open: no bank froth there ("shore" = as if mid-river)
            edge = [hw[i] if all(m.cell(p[0] + nx * s * (hw[i] + o), p[1] + ny * s * (hw[i] + o)) & TM.WATER
                                 for o in (28, 44)) else 0.0 for s in (-1, 1)]
            if prev is not None:
                pr, pz, pf, pd, phw, pedge = prev
                # two halves (edge -> middle -> edge), so `shore` is the real distance to the nearest bank
                shore, pshore = (edge[0], hw[i], edge[1]), (pedge[0], phw, pedge[1])
                for a in (2, 3):
                    b = a + 1
                    old = [(pr[c], pz[c], pf, pshore[c - 2], pd) for c in (a, b)]
                    new = [(row[c], z[c], flow, shore[c - 2], depth) for c in (a, b)]
                    for q, zz, f, sh, d in (old[0], old[1], new[1], old[0], new[1], new[0]):
                        water3d.vert(water, *q, zz, f, sh, d)
                for o, w in ((0, 1), (6, 5)):
                    _bank(bank, (pr[w], row[w]), (pr[o], row[o]), (pz[w] + bz, z[w] + bz), (pz[o] + bz, z[o] + bz))
            prev = (row, z, flow, depth, hw[i], edge)
    for lx, ly, lr, s in m.lakes:
        n = 40
        rad = [lr * (0.85 + 0.35 * TM.biomes.fbm(s, math.cos(k * math.tau / n) * 1.6 + 5,
                                                 math.sin(k * math.tau / n) * 1.6 + 5)) for k in range(n)]
        zc = gh(lx, ly)

        def ring(k, d):
            a = k % n * math.tau / n
            q = (lx + math.cos(a) * (rad[k % n] + d), ly + math.sin(a) * (rad[k % n] + d))
            return q, gh(*q)

        for k in range(n):
            # middle -> an inner ring 60 px from the shore -> the shore, so `shore` is the real distance
            (i0, zi0), (i1, zi1) = ring(k, -60), ring(k + 1, -60)
            (e0, ze0), (e1, ze1) = ring(k, 0), ring(k + 1, 0)
            mid = min(rad[k % n], rad[(k + 1) % n])
            water3d.vert(water, lx, ly, zc, shore=mid)
            water3d.vert(water, *i0, zi0, shore=60.0)
            water3d.vert(water, *i1, zi1, shore=60.0)
            for q, zz, sh in ((i0, zi0, 60.0), (e0, ze0, 0.0), (e1, ze1, 0.0),
                              (i0, zi0, 60.0), (e1, ze1, 0.0), (i1, zi1, 60.0)):
                water3d.vert(water, *q, zz, shore=sh)
            (u0, zu0), (u1, zu1) = ring(k, -6), ring(k + 1, -6)
            (o0, zo0), (o1, zo1) = ring(k, BANK_W), ring(k + 1, BANK_W)
            _bank(bank, (u0, u1), (o0, o1), (zu0 + bz, zu1 + bz), (zo0 + bz, zo1 + bz))
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
    r.geo = {k: game._geo(v) for k, v in (("bank", bank), ("road", road), ("cliff", cliff))}
    r.geo["water"] = water3d.geometry(game, water)


def draw3d(game, L, vl, stage):
    if stage == "props" or vl != "over" or getattr(game, "worldgen", 1) == 1:
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
        if r.geo["bank"]:
            r.geo["bank"].render(box)
        water3d.draw(game, r.geo["water"])
        if r.geo["road"]:
            r.geo["road"].render(box)
        game.flat(r.worn)
        return
    if r.geo["cliff"]:
        r.geo["cliff"].render(box)
    game.draw_kinds(r.deco)
    game.mesh(r.wbridges, "world_bridge")
