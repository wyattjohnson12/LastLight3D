"""
terrain_draw.py - the 3D drawing for terrain.py (biome hook draw3d): rivers and the lake (a water surface a
little below the ground with muddy banks), dirt roads, worn ground, cliffs (solid rock blocks), road bridges,
grass / flower clumps and ford stones (shapes3d), bobbers. Built once per world, drawn every frame.
"""
import math
from array import array

import terrain_map as TM
import water3d

BANK_W = 16.0
WATER_Z, BANK_Z = 1.6, 0.8   # how far the water surface / the mud banks lie above the ground (bobbers, frogs)


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
            za, zb = gh(*a) + 1.2, gh(*b) + 1.2
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
                lo = g + nb if nb > 0 else g - 14      # sink the foot: the hill may fall away below
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
    if not getattr(game, "_sh_pass", False):    # (shadows3d.py: fish under water and a thin line cast no shadow)
        _draw_fishing(game, r, box)
        _draw_critters(game, r)


def _box(out, x, y, z0, z1, h, col):
    """An axis-aligned little block (top + 4 sides) into a coloured-triangle list."""
    a, b, c, d = (x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)
    _quad(out, (*a, z1), (*b, z1), (*c, z1), (*d, z1), col)
    for p, q in ((a, b), (b, c), (c, d), (d, a)):
        _quad(out, (*p, z0), (*q, z0), (*q, z1), (*p, z1), col)


def _draw_fishing(game, r, box):
    """Bobbers on the water (bobbing, dipping on a bite) and the line up to the rod tip."""
    if not r.bobbers:
        return
    gh, m, t = game.ground_height, r.m, game.flame_t
    out = []
    for pid, (x, y, bite, _) in r.bobbers.items():
        wz = gh(x, y) + (WATER_Z if m.cell(x, y) & TM.WATER else 1.0)
        z = wz + (-2.2 + 1.2 * math.sin(t * 22) if bite else 0.5 * math.sin(t * 2.6 + pid))
        _box(out, x, y, z - 1.5, z + 1.0, 3.2, (0.96, 0.95, 0.9, 1.0))
        _box(out, x, y, z + 1.0, z + 4.4, 3.4, (0.86, 0.14, 0.12, 1.0))
        _box(out, x, y, z + 4.4, z + 7.5, 0.7, (0.96, 0.95, 0.9, 1.0))
        p = game.players.get(pid)
        if p is not None and p.alive and p.layer == "over":
            fx, fy = math.cos(p.face), math.sin(p.face)
            tx, ty = p.pos[0] + fx * 30 + fy * 10, p.pos[1] + fy * 30 - fx * 10     # rod tip, right hand
            tz = gh(tx, ty) + 52
            nx, ny = -(ty - y), tx - x
            n = math.hypot(nx, ny) or 1.0
            nx, ny = nx / n * 0.5, ny / n * 0.5
            col = (0.92, 0.92, 0.86, 0.75)
            _quad(out, (x - nx, y - ny, z + 7.5), (x + nx, y + ny, z + 7.5), (tx + nx, ty + ny, tz),
                  (tx - nx, ty - ny, tz), col)
            _quad(out, (x, y, z + 7.2), (x, y, z + 7.8), (tx, ty, tz + 0.3), (tx, ty, tz - 0.3), col)
    n = len(out)
    dyn = getattr(r, "dyn", None)
    if dyn is None or dyn[2] < n:
        from arcade.gl import BufferDescription
        cap = max(4096, 1 << (n - 1).bit_length()) * 7
        buf = game.ctx.buffer(reserve=cap * 4)
        geo = game.ctx.geometry([BufferDescription(buf, "3f 4f", ["in_pos", "in_col"])], mode=game.ctx.TRIANGLES)
        dyn = r.dyn = (buf, geo, cap)
    dyn[0].orphan()
    dyn[0].write(array("f", out))
    dyn[1].render(box, vertices=n // 7)


def _draw_critters(game, r):
    """Swimming fish, frogs on the banks and caught fish leaping out - as models3d instances."""
    fp = game.fp_on()
    if not (r.fish or r.frogs or r.leaps) or not game.models3d_mode(fp):
        return
    import models3d
    game._m3_init()
    saved = (game._m3_frame, game._m3_spots, getattr(game, "_m3_up", 1.0))
    cfg = getattr(game, "cfg", {}) or {}
    game._m3_frame, game._m3_spots = {}, []
    game._m3_up = 1.0 if fp else float(cfg.get("creature_models_up", models3d.TILT_UP))
    white = (255, 255, 255)
    try:
        for f in r.fish:         # just under the surface: water-tinted and faded
            game._m3_add(f.kind, f, f.x, f.y, f.heading, 1.0, (150, 200, 215), 175, z=-1.0)
        m = r.m
        for f in r.frogs:
            e = max(0.0, min(BANK_W, m.edge_at(f.x, f.y)))
            game._m3_add("frog", f, f.x, f.y, f.heading, 1.4, white, 255, z=BANK_Z * (1 - e / BANK_W))
        leaps = getattr(r, "leap_objs", None)
        if leaps is None:
            leaps = r.leap_objs = {}
        for lp in r.leaps:
            kind, x0, y0, x1, y1, t, T = lp
            k = t / T
            o = leaps.setdefault(id(lp), type("Leap", (), {})())
            x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
            game._m3_add(kind, o, x, y, math.atan2(y1 - y0, x1 - x0), 1.5, white, 255,
                         z=(WATER_Z - 2.0) * (1 - k) + 60 * math.sin(math.pi * k))
        if len(leaps) > 16:
            leaps.clear()
        game._m3_render()
    finally:
        game._m3_frame, game._m3_spots, game._m3_up = saved
