"""
fx3d.py - lighting, sun shadows and particles for the 3D view (mixed into View3D).

  * Time-of-day colour grading: warm dawn, plain day, golden/orange-purple dusk, blue night.
    The whole view is multiplied by a small "light map" texture: it starts as the ambient colour
    and every light (your light, torches, campfires, braziers, fire pots, bosses...) is added on
    top as a soft pool on the ground. Half resolution, one draw call for all the lights.
  * Sun direction for the soft drop shadows (long in the morning/evening, short at noon, faint
    contact shadows at night) - used by the shadow pass in view3d.py.
  * Particles: embers, flame licks and smoke from fires and torches, hit sparks and blood puffs,
    wood chips / leaves / stone dust when chopping and mining. A fixed pool of slots (no growing
    lists), drawn as camera-facing dots by one shader - one buffer write + one draw per blend mode.
    Particles are purely visual and made locally on every machine (host, online clients and each
    split-screen view) from state that is already synced (hit flashes, node shakes, lit fires).
"""
import math
import random
from array import array

from arcade.gl import BufferDescription
from arcade.gl.geometry import quad_2d_fs
from pyglet import gl

import terrain3d
from settings import *

MAX_PARTS = 640           # particle pool size (oldest are recycled when it's full)
MAX_POINTS = 1200         # most dots we upload in one draw (pool + the game's own burst particles)
STRIDE = 8                # floats per point: x y z size r g b a

# particle slot fields
PX, PY, PZ, VX, VY, VZ, LIFE, MAXL, SIZE, GROW, CR, CG, CB, CA, GRAV, DRAG, ADD, LAYER = range(18)

# ----------------------------------------------------------------- colour grading
WHITE = (1.0, 1.0, 1.0)
NIGHT = (0.15, 0.18, 0.36)
CAVE_AMBIENT = (0.12, 0.11, 0.16)
_GRADE = [               # (phase, multiply colour) - see DUSK_START / NIGHT_START / DAWN_START
    (0.00, (1.00, 0.80, 0.66)),               # sunrise: warm
    (0.06, (1.00, 0.93, 0.85)),
    (0.13, WHITE),                            # day
    (DUSK_START - 0.10, WHITE),
    (DUSK_START, (1.00, 0.86, 0.64)),         # golden hour
    ((DUSK_START + NIGHT_START) / 2, (0.80, 0.50, 0.56)),   # dusk: orange / purple
    (NIGHT_START, NIGHT),                     # night: blue
    (DAWN_START, NIGHT),
    ((DAWN_START + 1) / 2, (0.52, 0.38, 0.56)),             # before dawn: purple
    (1.00, (1.00, 0.80, 0.66)),
]


def grade(phase):
    """Ambient multiply colour for this time of day."""
    phase %= 1.0
    for (p0, c0), (p1, c1) in zip(_GRADE, _GRADE[1:]):
        if p0 <= phase <= p1:
            k = (phase - p0) / (p1 - p0) if p1 > p0 else 0.0
            k = k * k * (3 - 2 * k)
            return tuple(a + (b - a) * k for a, b in zip(c0, c1))
    return WHITE


def sun(phase, dk):
    """Shadow direction * length (in shadow widths) and shadow strength."""
    t = 0.0 if phase >= DAWN_START else min(1.0, phase / NIGHT_START)
    c = math.cos(math.pi * t)              # +1 morning (sun in the east) .. -1 evening
    dx, dy = -c * (1 - dk), -0.45
    n = math.hypot(dx, dy) or 1.0
    ln = (0.35 + 0.95 * abs(c)) * (1 - dk) + 0.15 * dk
    return dx / n * ln, dy / n * ln, 1.0 - 0.45 * dk


# ----------------------------------------------------------------- shaders
POINT_VS = """
#version 330
in vec3 in_pos;
in float in_size;
in vec4 in_col;
out vec3 v_pos;
out float v_size;
out vec4 v_col;
void main() { v_pos = in_pos; v_size = in_size; v_col = in_col; gl_Position = vec4(in_pos, 1.0); }
"""

POINT_GS = """
#version 330
layout (points) in;
layout (triangle_strip, max_vertices = 4) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform int ground;      // 1 = a pool of light lying on the ground, 0 = a dot facing the camera
in vec3 v_pos[];
in float v_size[];
in vec4 v_col[];
out vec2 g_uv;
out vec4 g_col;
void main() {
    vec3 c = v_pos[0];
    float s = v_size[0];
    if (s <= 0.0) return;
    mat4 mvp = window.projection * window.view;
    vec4 q = mvp * vec4(c, 1.0);
    vec2 k[4] = vec2[4](vec2(-1.0, 1.0), vec2(-1.0, -1.0), vec2(1.0, 1.0), vec2(1.0, -1.0));
    g_col = v_col[0];
    for (int i = 0; i < 4; i++) {
        g_uv = k[i];
        if (ground == 1) {
            gl_Position = mvp * vec4(c.xy + k[i] * s, c.z, 1.0);
        } else {
            vec4 o = q;
            o.x += k[i].x * s * window.projection[0][0];
            o.y += k[i].y * s * window.projection[1][1];
            gl_Position = o;
        }
        EmitVertex();
    }
    EndPrimitive();
}
"""

POINT_FS = """
#version 330
uniform int ground;
uniform float hot;       // additive particles get a white-hot core
in vec2 g_uv;
in vec4 g_col;
out vec4 f_color;
void main() {
    float d = dot(g_uv, g_uv);
    if (d >= 1.0) discard;
    if (ground == 1) {
        float a = 1.0 - smoothstep(0.3, 1.0, sqrt(d));
        f_color = vec4(g_col.rgb, g_col.a * a);
        return;
    }
    float a = 1.0 - d;
    vec3 rgb = mix(g_col.rgb, vec3(1.0, 0.96, 0.85), hot * a * a * a);
    f_color = vec4(rgb, g_col.a * a * a);
}
"""

COMP_VS = """
#version 330
in vec2 in_vert;
in vec2 in_uv;
out vec2 uv;
void main() { uv = in_uv; gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

COMP_FS = """
#version 330
uniform sampler2D light;
uniform float vignette;
in vec2 uv;
out vec4 f_color;
void main() {
    vec3 l = texture(light, uv).rgb;
    float r = length((uv - 0.5) * vec2(1.6, 2.0));
    l *= 1.0 - vignette * smoothstep(0.55, 1.35, r);
    f_color = vec4(l, 1.0);
}
"""


class FX3D:
    """Lighting + particles. Mixed into View3D (and so into the game window)."""

    # ------------------------------------------------------------------ GPU bits
    def _fx_init(self):
        if getattr(self, "_fx_progs", None):
            return
        ctx = self.ctx
        pts = ctx.program(vertex_shader=POINT_VS, geometry_shader=terrain3d.inject(POINT_GS, "0.0"),  # on the hills
                          fragment_shader=POINT_FS)
        pts["ground"] = 0
        pts["hot"] = 0.0
        comp = ctx.program(vertex_shader=COMP_VS, fragment_shader=COMP_FS)
        comp["light"] = 0
        comp["vignette"] = 0.0
        self._fx_progs = (pts, comp)
        self._fx_bufs = []
        self._fx_geos = []
        for _ in range(3):        # lights, normal particles, additive particles
            buf = ctx.buffer(reserve=MAX_POINTS * STRIDE * 4)
            self._fx_bufs.append(buf)
            self._fx_geos.append(ctx.geometry([BufferDescription(buf, "3f 1f 4f", ["in_pos", "in_size", "in_col"])],
                                              mode=ctx.POINTS))
        self._fx_quad = quad_2d_fs()
        self._fx_fbo = None
        self._fx_fbo_size = None
        self._fx_pool = [[0.0] * 17 + ["over"] for _ in range(MAX_PARTS)]
        self._fx_cur = 0
        self._fx_t = getattr(self, "flame_t", 0.0)

    def _fx_points(self, which, data, ground=0, blend=None, hot=0.0):
        n = len(data) // STRIDE
        if not n:
            return
        if n > MAX_POINTS:
            n = MAX_POINTS
            data = data[:n * STRIDE]
        buf = self._fx_bufs[which]
        buf.orphan()
        buf.write(data)
        prog = self._fx_progs[0]
        prog["ground"] = ground
        prog["hot"] = hot
        ctx = self.ctx
        ctx.enable(ctx.BLEND)
        ctx.blend_func = blend or ctx.BLEND_DEFAULT
        self._fx_geos[which].render(prog, vertices=n)
        ctx.blend_func = ctx.BLEND_DEFAULT

    # ------------------------------------------------------------------ particles
    def fx_spawn(self, layer, x, y, z, vx, vy, vz, life, size, col, a=1.0, grav=0.0, drag=0.0, grow=0.0, add=False):
        """One particle into the next pool slot (recycles the oldest when the pool is full)."""
        p = self._fx_pool[self._fx_cur]
        self._fx_cur = (self._fx_cur + 1) % MAX_PARTS
        p[PX], p[PY], p[PZ], p[VX], p[VY], p[VZ] = x, y, z, vx, vy, vz
        p[LIFE] = p[MAXL] = life
        p[SIZE], p[GROW] = size, grow
        p[CR], p[CG], p[CB], p[CA] = col[0] / 255, col[1] / 255, col[2] / 255, a
        p[GRAV], p[DRAG], p[ADD], p[LAYER] = grav, drag, 1.0 if add else 0.0, layer

    def fx_puff(self, layer, x, y, z, col, n, speed, up, life, size, a=1.0, grav=0.0, drag=2.0, grow=0.0,
                add=False, spread=4.0):
        rnd = random.random
        for _ in range(n):
            ang = rnd() * math.tau
            v = (0.35 + 0.65 * rnd()) * speed
            self.fx_spawn(layer, x + (rnd() - 0.5) * spread, y + (rnd() - 0.5) * spread, z + (rnd() - 0.5) * spread,
                          math.cos(ang) * v, math.sin(ang) * v, up * (0.5 + rnd()), life * (0.7 + 0.6 * rnd()),
                          size * (0.7 + 0.6 * rnd()), col, a, grav, drag, grow, add)

    def _fx_viewers(self, name):
        """Camera centres currently looking at layer `name` (one per split-screen view)."""
        if getattr(self, "local", False) and getattr(self, "slots", None):
            return [s.camera.position for s in self.slots if s.p.layer == name]
        return [self.camera.position] if name == self.view_layer else []

    def fx_tick(self):
        """Advance particles once per game frame (draw runs once per split-screen view)."""
        self._fx_init()
        t = self.flame_t
        dt = t - self._fx_t
        self._fx_t = t
        if dt <= 0:
            return
        dt = min(dt, 0.05)
        for p in self._fx_pool:
            if p[LIFE] <= 0:
                continue
            p[LIFE] -= dt
            p[PX] += p[VX] * dt
            p[PY] += p[VY] * dt
            p[PZ] += p[VZ] * dt
            p[VZ] -= p[GRAV] * dt
            if p[DRAG]:
                f = max(0.0, 1 - p[DRAG] * dt)
                p[VX] *= f
                p[VY] *= f
                p[VZ] *= f
            if p[GROW]:
                p[SIZE] = max(0.3, p[SIZE] + p[GROW] * dt)
            if p[PZ] < 0:
                p[PZ] = 0.0
                p[VZ] *= -0.3
                p[VX] *= 0.5
                p[VY] *= 0.5
        for name, L in self.layers.items():
            if self.layer_seen(name):
                self._fx_emit(L, name, dt)

    def _fx_emit(self, L, name, dt):
        rnd = random.random
        views = self._fx_viewers(name)

        def near(x, y):
            return any(abs(x - vx) < 820 and abs(y - vy) < 720 for vx, vy in views)

        def count(rate):
            return int(rate * dt + rnd())

        spawn = self.fx_spawn
        # ---- fires: embers, flame licks, a little smoke
        for f in L.flames:
            if not f.visible or not near(f.center_x, f.center_y):
                continue
            x, y = f.center_x, f.center_y - 5
            for _ in range(count(7)):
                spawn(name, x + (rnd() - 0.5) * 16, y + (rnd() - 0.5) * 8, 10 + rnd() * 10,
                      (rnd() - 0.5) * 30, (rnd() - 0.5) * 20, 45 + rnd() * 45, 0.9 + rnd() * 0.8, 1.6 + rnd() * 1.2,
                      (255, 150 + int(rnd() * 70), 60), 1.0, -12, 0.6, 0, True)
            for _ in range(count(9)):
                spawn(name, x + (rnd() - 0.5) * 12, y, 6 + rnd() * 6, (rnd() - 0.5) * 10, 0, 55 + rnd() * 35,
                      0.32 + rnd() * 0.2, 6 + rnd() * 4, (255, 110 + int(rnd() * 50), 30), 0.55, 0, 0, -10, True)
            for _ in range(count(2.2)):
                spawn(name, x + (rnd() - 0.5) * 10, y, 34, 8 + rnd() * 10, (rnd() - 0.5) * 6, 26 + rnd() * 14,
                      1.8 + rnd(), 6, (74, 70, 68), 0.22, 0, 0.3, 11)
        # ---- torches in hand
        for p in self.players.values():
            if p.alive and p.layer == name and p.held.visible and p.holding_torch:
                h = p.held
                if not near(h.center_x, h.center_y):
                    continue
                z = (8 + h.height * 0.8) * (1 / math.cos(math.radians(CAM_PITCH_DEG)))
                for _ in range(count(9)):
                    spawn(name, h.center_x + (rnd() - 0.5) * 6, h.center_y - 3, z + rnd() * 4, (rnd() - 0.5) * 24,
                          (rnd() - 0.5) * 14, 30 + rnd() * 40, 0.5 + rnd() * 0.5, 1.4 + rnd(),
                          (255, 160 + int(rnd() * 60), 60), 1.0, -8, 0.8, 0, True)
        # ---- burning ground, burning zombies, fire pots in the air
        if name == "over":
            for h in self.hazards:
                if h.kind == "fire" and h.tele <= 0 and near(h.x, h.y):
                    for _ in range(count(h.r * 0.4)):
                        a, r = rnd() * math.tau, rnd() * h.r
                        spawn(name, h.x + math.cos(a) * r, h.y + math.sin(a) * r, 4, 0, 0, 50 + rnd() * 50,
                              0.5 + rnd() * 0.4, 2 + rnd() * 3, (255, 130 + int(rnd() * 80), 40), 0.9, 0, 0.5, -2, True)
        for z in L.zombies:
            if getattr(z, "burn", 0) > 0 and near(z.center_x, z.center_y):
                for _ in range(count(10)):
                    spawn(name, z.center_x + (rnd() - 0.5) * 20, z.center_y - 4, 10 + rnd() * 30, 0, 0,
                          50 + rnd() * 30, 0.35 + rnd() * 0.2, 5 + rnd() * 3, (255, 120, 30), 0.6, 0, 0, -8, True)
        for s in self.shots:
            if s.layer == name and s.kind != "arrow":
                for _ in range(count(28)):
                    spawn(name, s.x, s.y, s.height + 8, (rnd() - 0.5) * 30, (rnd() - 0.5) * 30, 20 + rnd() * 30,
                          0.3 + rnd() * 0.3, 1.6 + rnd() * 1.4, (255, 150 + int(rnd() * 80), 50), 1.0, 0, 1.0, 0, True)
        # ---- hits: sparks and blood when something starts flashing
        for z in L.zombies:
            if self._fx_edge(z, "_fx_fl", z.flash > 0) and near(z.center_x, z.center_y):
                if z.kind in ("golem", "crawler"):
                    self._fx_hit(name, z.center_x, z.center_y, 26, (120, 110, 104), stone=True)
                else:
                    self._fx_hit(name, z.center_x, z.center_y, 26, (110, 26, 30))
        for b in L.bosses:
            if self._fx_edge(b, "_fx_fl", b.flash > 0) and near(b.center_x, b.center_y):
                self._fx_hit(name, b.center_x, b.center_y, 40, (90, 30, 40), big=True)
        for a in L.animals:
            if self._fx_edge(a, "_fx_fl", a.flash > 0) and near(a.center_x, a.center_y):
                col = (240, 200, 60) if a.kind == "bee" else (170, 26, 26)
                self._fx_hit(name, a.center_x, a.center_y, 16, col)
        for p in self.players.values():
            if p.layer == name and self._fx_edge(p, "_fx_fl", p.hurt > 0) and p.alive:
                self._fx_hit(name, p.sprite.center_x, p.sprite.center_y, 26, (170, 22, 22), sparks=False)
        # ---- chopping and mining: chips, leaves, dust
        for lst in L.node_lists():
            for n in lst:
                if self._fx_edge(n, "_fx_sh", n.shake > 0) and near(n.center_x, n.center_y):
                    self._fx_gather(name, n)

    @staticmethod
    def _fx_edge(obj, attr, now):
        """True when `now` just became true for this object."""
        d = obj.__dict__
        was = d.get(attr, False)
        if was != now:
            d[attr] = now
        return now and not was

    def _fx_hit(self, name, x, y, z, col, stone=False, big=False, sparks=True):
        y -= 6                     # just in front of the cut-out
        k = 1.6 if big else 1.0
        self.fx_spawn(name, x, y, z, 0, 0, 0, 0.09, 16 * k, (255, 245, 220), 0.9, add=True)    # impact flash
        if sparks:
            self.fx_puff(name, x, y, z, (255, 230, 160), int(5 * k), 220 * k, 60, 0.18, 1.6, add=True, drag=5)
        if stone:
            self.fx_puff(name, x, y, z, col, 7, 110, 120, 0.6, 2.6, grav=420, drag=1)
            self.fx_puff(name, x, y, z - 10, (150, 140, 130), 3, 30, 20, 0.6, 6, a=0.4, grow=22)
        else:
            self.fx_puff(name, x, y, z, col, int(7 * k), 120 * k, 110, 0.55, 2.8 * k, a=0.95, grav=420, drag=1.5)
            self.fx_puff(name, x, y, z, col, 2, 20, 10, 0.4, 7 * k, a=0.35, grow=14)

    def _fx_gather(self, name, n):
        x, y = n.center_x, n.center_y - 8
        kind = n.kind
        if kind == "tree":
            self.fx_puff(name, x, y, 26, (156, 108, 62), 6, 120, 130, 0.65, 2.6, grav=440, drag=1)
            if n.state == "full":
                self.fx_puff(name, x, y, 70, (78, 146, 58), 5, 60, 10, 1.3, 2.6, grav=40, drag=2.5, spread=40)
            self.fx_puff(name, x, y, 6, (150, 130, 100), 3, 30, 10, 0.6, 6, a=0.3, grow=20)
        elif kind in ("bush", "hive"):
            col = (84, 150, 60) if kind == "bush" else (230, 180, 60)
            self.fx_puff(name, x, y, 20, col, 6, 70, 60, 0.9, 2.4, grav=120, drag=2, spread=16)
        else:                      # rock and ores
            col = {"iron": (176, 130, 104), "coal": (54, 54, 58), "crystal": (150, 220, 255)}.get(kind, (140, 136, 130))
            self.fx_puff(name, x, y, 18, col, 7, 130, 140, 0.6, 2.4, grav=460, drag=1)
            self.fx_puff(name, x, y, 8, (160, 154, 146), 4, 36, 14, 0.7, 7, a=0.35, grow=24, spread=12)
            if kind == "crystal":
                self.fx_puff(name, x, y, 22, (200, 240, 255), 5, 140, 60, 0.3, 1.6, add=True, drag=4)
            else:
                self.fx_puff(name, x, y, 18, (255, 220, 150), 3, 180, 50, 0.15, 1.4, add=True, drag=5)

    def fx_draw_particles(self, vl, additive):
        """Draw the pooled particles of one blend kind (call with the 3D camera on, depth test on).
        The normal pass also draws the game's own burst particles (self.particles)."""
        want = 1.0 if additive else 0.0
        out = []
        ext = out.extend
        for p in self._fx_pool:
            if p[LIFE] > 0 and p[ADD] == want and p[LAYER] == vl:
                fr = p[LIFE] / p[MAXL]
                ext((p[PX], p[PY], p[PZ], p[SIZE], p[CR], p[CG], p[CB], p[CA] * fr * min(1.0, (1 - fr) * 8 + 0.25)))
        if not additive:
            for x, y, _, _, life, maxlife, col, size, *ly in self.particles:
                if ly and ly[0] != vl:
                    continue
                k = max(0.0, life / maxlife)
                ext((x, y - 4, 22.0, size * 1.35 * (0.5 + k / 2), col[0] / 255, col[1] / 255, col[2] / 255, k))
        if not out:
            return
        gl.glDepthMask(gl.GL_FALSE)
        ctx = self.ctx
        self._fx_points(2 if additive else 1, array("f", out),
                        blend=(ctx.SRC_ALPHA, ctx.ONE) if additive else None, hot=0.8 if additive else 0.0)
        gl.glDepthMask(gl.GL_TRUE)

    # ------------------------------------------------------------------ lighting
    def fx_light_data(self, L, vl, dk):
        k = min(1.0, dk * 1.4)
        t = self.flame_t
        out = []
        ext = out.extend
        if k > 0:
            for g in L.glows:                     # campfires and braziers (and any other lit fire)
                if g.visible:
                    fl = 1 + 0.05 * math.sin(t * 11 + g.center_x) + 0.03 * math.sin(t * 27 + g.center_y)
                    ext((g.center_x, g.center_y, 0.5, g.width * 0.72 * fl, 1.0, 0.74, 0.46, 0.95 * k))
            centre = tuple(self.cam_pos) if self.cut else self.view_pos()
            r = self.light_radius() if not self.cut else 330
            me = self.me
            if me is not None and me.alive and me.holding_torch:
                fl = 1 + 0.04 * math.sin(t * 13) + 0.03 * math.sin(t * 31)
                ext((centre[0], centre[1], 0.5, r * fl, 1.0, 0.86, 0.64, 1.0))
            else:
                ext((centre[0], centre[1], 0.5, r, 0.92, 0.92, 0.88, 1.0))
            for p in self.players.values():       # friends: a torch or a small lantern
                if p is me or not p.alive or p.layer != vl:
                    continue
                c = p.color
                rr = 210 if p.holding_torch else 120
                ext((p.sprite.center_x, p.sprite.center_y, 0.5, rr, 0.7 + c[0] / 850, 0.62 + c[1] / 850,
                     0.5 + c[2] / 850, 0.85 * k))
            for b in L.bosses:
                ext((b.center_x, b.center_y, 0.5, b.radius + 120, 1.0, 0.36, 0.22, 0.6 * k))
            for z in L.zombies:
                if getattr(z, "burn", 0) > 0:
                    ext((z.center_x, z.center_y, 0.5, 90, 1.0, 0.55, 0.2, 0.7 * k))
            for s in self.shots:
                if s.layer == vl and s.kind != "arrow":
                    ext((s.x, s.y, 0.5, 120, 1.0, 0.6, 0.25, 0.8 * k))
            if vl == "cave":
                for s in L.exits:
                    ext((s.center_x, s.center_y, 0.5, 140, 1.0, 0.94, 0.8, 0.7))
            else:
                for h in self.hazards:
                    if h.kind == "fire" and h.tele <= 0:
                        ext((h.x, h.y, 0.5, h.r * 2.4, 1.0, 0.55, 0.2, 0.9 * k))
                    elif h.kind == "meteor" and h.tele > 0:
                        ext((h.x, h.y, 0.5, h.r * 1.8, 1.0, 0.5, 0.2, (1 - min(1.0, h.tele)) * 0.8 * k))
        return out

    def fx_lighting(self, L, vl, dk):
        """Colour-grade the view for the time of day and light it with every light source.
        Call after the world is drawn; leaves the GUI camera active."""
        self._fx_init()
        amb = CAVE_AMBIENT if vl == "cave" else grade(self.phase)
        if dk <= 0 and min(amb) > 0.995:
            return                                 # plain daylight: nothing to do
        ctx = self.ctx
        vp = self.camera.viewport
        w, h = max(16, int(vp.width) // 2), max(16, int(vp.height) // 2)
        if self._fx_fbo_size != (w, h):
            tex = ctx.texture((w, h), components=4, filter=(ctx.LINEAR, ctx.LINEAR))
            self._fx_fbo = ctx.framebuffer(color_attachments=[tex])
            self._fx_fbo_tex = tex
            self._fx_fbo_size = (w, h)
        self.use_world3d()                         # same camera matrices for the light pools
        data = self.fx_light_data(L, vl, dk)
        ctx.disable(ctx.DEPTH_TEST)
        with self._fx_fbo.activate() as fbo:
            fbo.viewport = (0, 0, w, h)
            fbo.clear(color_normalized=(amb[0], amb[1], amb[2], 1.0))
            if data:
                self._fx_points(0, array("f", data), ground=1, blend=(ctx.SRC_ALPHA, ctx.ONE))
        self.gui.use()                             # back to this view's viewport / scissor
        ctx.enable(ctx.BLEND)
        ctx.blend_func = (ctx.DST_COLOR, ctx.ZERO)  # multiply
        comp = self._fx_progs[1]
        comp["vignette"] = 0.35 * dk
        self._fx_fbo_tex.use(0)
        self._fx_quad.render(comp)
        ctx.blend_func = ctx.BLEND_DEFAULT
