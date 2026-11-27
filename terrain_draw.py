"""
terrain_draw.py - the 3D drawing for terrain.py (biome hook draw3d): rivers and the lake (a water surface a
little below the ground with muddy banks), dirt roads, worn ground, cliffs (solid rock blocks), road bridges,
grass / flower clumps and ford stones (shapes3d), bobbers. Built once per world, drawn every frame.
"""
import math
from array import array

from pyglet import gl

import terrain_map as TM

# Water and banks lie just ABOVE the ground: since the hills the ground is a depth-tested heightfield, so
# anything below it vanishes (rivers run in flat valleys, so a small lift reads as a surface; polygon offset
# keeps it from flickering on the ground mesh's triangles).
WATER_Z, BANK_Z, BANK_W = 1.4, 0.9, 16.0
MUD, MUD_OUT = (0.42, 0.33, 0.22, 1.0), (0.42, 0.33, 0.22, 0.0)

# rivers / lakes: the plain coloured-triangle program plus a slow ripple and glints (world xy + time)
WATER_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec4 in_col;
out vec4 v_col;
out vec2 v_xy;
void main() {
    gl_Position = window.projection * window.view * vec4(in_pos, 1.0);
    v_col = in_col;
    v_xy = in_pos.xy;
}
"""
WATER_FS = """
#version 330
uniform float time;
in vec4 v_col;
in vec2 v_xy;
out vec4 f_color;
void main() {
    vec2 p = v_xy;
    float w = sin(p.x * 0.043 + time * 1.5) * sin(p.y * 0.051 - time * 1.1)
            + 0.6 * sin((p.x - p.y) * 0.093 + time * 2.2) + 0.4 * sin((p.x + 2.0 * p.y) * 0.17 - time * 2.9);
    vec3 c = v_col.rgb * (1.0 + 0.09 * w);
    c += vec3(0.85, 0.95, 1.0) * smoothstep(1.25, 1.75, w) * 0.22;
    f_color = vec4(c, v_col.a * (0.9 + 0.06 * w));
}
"""


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


def _band(out, a, b, c, d):
    """A bank quad: a, d on the outer (grass) edge fade out, b, c at the water's edge are mud."""
    for p, col in ((a, MUD_OUT), (b, MUD), (c, MUD), (a, MUD_OUT), (c, MUD), (d, MUD_OUT)):
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
                for o, w in ((0, 1), (3, 2)):
                    _band(bank, (*pr[o], ph + BANK_Z), (*pr[w], ph + BANK_Z), (*row[w], h + BANK_Z),
                          (*row[o], h + BANK_Z))
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
            _band(bank, (*q0, h + BANK_Z), (*p0, h + BANK_Z), (*p1, h + BANK_Z), (*q1, h + BANK_Z))
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
    r.geo = {k: game._geo(v) for k, v in (("water", water), ("bank", bank), ("road", road), ("cliff", cliff))}


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
        gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
        gl.glPolygonOffset(-1.0, -4.0)
        try:
            for k in ("bank", "water", "road"):
                if r.geo[k]:
                    r.geo[k].render(_water_prog(game) if k == "water" else box)
        finally:
            gl.glDisable(gl.GL_POLYGON_OFFSET_FILL)
        game.flat(r.worn)
        return
    if r.geo["cliff"]:
        r.geo["cliff"].render(box)
    game.draw_kinds(r.deco)
    game.mesh(r.wbridges, "world_bridge")
    _draw_fishing(game, r, box)
    _draw_critters(game, r)


def _water_prog(game):
    p = getattr(game, "_water_prog3d", None)
    if p is None:
        p = game._water_prog3d = game.ctx.program(vertex_shader=WATER_VS, fragment_shader=WATER_FS)
    p["time"] = float(game.flame_t % 1000.0)
    return p


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
