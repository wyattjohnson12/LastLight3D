"""
ambient3d.py - small signs of life in the 3D world (mixed into View3D). Visual only: made on every computer
from what it can already see (time of day, season, biome, the viewer's position), never sent over the network.

  * falling leaves drifting down from the tree canopies (lots in autumn, a few the rest of the year)
  * fireflies by water and in the woods at dusk and night: glowing, blinking, slowly wandering
  * dust motes floating in the sunlight by day; pollen and butterflies in spring and summer meadows
  * ash flakes and rising embers in the Ashlands, glittering snow flurries in the tundra
  * gnat swarms over the Mire's bog pools
  * little flocks of birds pecking at the ground that flutter up and fly off when someone comes near

How it stays cheap: a fixed pool of MAX_MOTES slots in one GPU buffer. A slot holds where and when its mote
was born and a few numbers for its path; the geometry shader works out where it is NOW from its age (falling,
wandering, blinking, flapping), so the CPU only writes a slot when something is born or a flock takes off -
no per-frame movement in Python. Two draws: solid things (leaves, flakes, butterflies, gnats, birds) lit like
everything standing up (lighting3d.py "lit" stage), and glowing ones added on top of the night ("glow" stage).
"""
import math
import random
from array import array

from arcade.gl import BufferDescription

import ground3d
import lighting3d
import terrain3d

MAX_MOTES = 420
STRIDE = 12          # floats per mote: x y z kind | born life seed p1 | vx vy p2 p3
LEAF, FIREFLY, DUST, POLLEN, BUTTERFLY, ASH, EMBER, SPARKLE, GNAT, BIRD = range(10)
GLOWING = (FIREFLY, DUST, POLLEN, EMBER, SPARKLE)
FLOCK_CELL = 230     # px: at most one flock of birds per cell of this size
FLOCK_NEAR = 150     # someone this close and the flock takes off
NEVER = 1.0e6        # a sitting bird's take-off time until something startles it

VS = """
#version 330
in vec4 in_a;
in vec4 in_b;
in vec4 in_c;
out vec4 v_a;
out vec4 v_b;
out vec4 v_c;
void main() { v_a = in_a; v_b = in_b; v_c = in_c; gl_Position = vec4(0.0, 0.0, 0.0, 1.0); }
"""

GS = """
#version 330
layout (points) in;
layout (triangle_strip, max_vertices = 8) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform float u_time;
uniform int u_glow;          // 0 = the solid pass, 1 = the glowing pass
uniform float u_night;       // 0 day .. 1 night
uniform vec2 u_wind;
in vec4 v_a[];
in vec4 v_b[];
in vec4 v_c[];
out vec2 a_uv;
out vec4 a_col;
flat out int a_soft;
const vec3 LEAF_COLS[6] = vec3[6](vec3(0.85, 0.45, 0.12), vec3(0.92, 0.7, 0.18), vec3(0.7, 0.24, 0.12),
                                  vec3(0.5, 0.62, 0.2), vec3(0.38, 0.55, 0.18), vec3(0.62, 0.68, 0.24));
const vec3 WING_COLS[5] = vec3[5](vec3(1.0, 0.92, 0.4), vec3(0.98, 0.98, 0.95), vec3(0.95, 0.55, 0.2),
                                  vec3(0.55, 0.7, 1.0), vec3(0.92, 0.6, 0.85));
mat4 mvp;
void put(vec3 p, vec2 uv) { a_uv = uv; gl_Position = mvp * vec4(p, 1.0); EmitVertex(); }
// a quad facing the camera, r px
void dot_at(vec3 p, float r) {
    vec4 q = mvp * vec4(p, 1.0);
    vec2 k[4] = vec2[4](vec2(-1.0, 1.0), vec2(-1.0, -1.0), vec2(1.0, 1.0), vec2(1.0, -1.0));
    for (int i = 0; i < 4; i++) {
        vec4 o = q;
        o.x += k[i].x * r * window.projection[0][0];
        o.y += k[i].y * r * window.projection[1][1];
        a_uv = k[i];
        gl_Position = o;
        EmitVertex();
    }
    EndPrimitive();
}
vec3 lit(vec3 c, vec3 p) { return lt_fogged(c * lt_light(p, vec3(0.0)), p); }
void main() {
    int kind = int(v_a[0].w + 0.5);
    float age = u_time - v_b[0].x;
    float life = v_b[0].y;
    if (age < 0.0 || age > life) return;
    bool glow = kind == 1 || kind == 2 || kind == 3 || kind == 6 || kind == 7;
    if (glow != (u_glow == 1)) return;
    float s = v_b[0].z;
    vec3 p0 = v_a[0].xyz;
    vec2 drift = v_c[0].xy;
    float fade = min(1.0, age * 1.5) * min(1.0, (life - age) * 0.8);
    mvp = window.projection * window.view;
    vec4 cq = mvp * vec4(p0.xy, p0.z + ground_z(p0.xy), 1.0);
    if (cq.w < 1.0 || abs(cq.x) > cq.w * 1.5 + 300.0 || abs(cq.y) > cq.w * 1.5 + 300.0) return;
    a_soft = glow ? 1 : 0;
    if (kind == 0 || kind == 5) {                       // ---- a leaf / ash flake fluttering down
        float fall = v_b[0].w;
        float t_land = p0.z / fall;
        float tf = min(age, t_land);
        vec2 xy = p0.xy + drift * tf + vec2(sin(tf * 1.7 + s * 6.0), cos(tf * 1.3 + s * 4.0)) * 9.0;
        vec3 p = vec3(xy, max(p0.z - fall * age, 0.0) + 0.6 + ground_z(xy));
        float r = kind == 0 ? 2.6 : 1.5;
        vec3 c = kind == 0 ? LEAF_COLS[int(v_c[0].z) % 6] : mix(vec3(0.62, 0.6, 0.58), vec3(0.3, 0.29, 0.28), fract(s * 7.0));
        a_col = vec4(lit(c * (0.85 + 0.3 * fract(s * 13.0)), p), fade);
        float spin = age < t_land ? age * (2.5 + 2.0 * s) + s * 6.0 : t_land * 3.0 + s * 6.0;
        float tilt = age < t_land ? cos(age * 4.0 + s * 9.0) : 0.0;     // flutter: the leaf turns edge-on
        vec3 u = vec3(cos(spin), sin(spin), 0.0) * r;
        vec3 v = vec3(-sin(spin) * r * 0.6, cos(spin) * r * 0.6, tilt * r * 0.6);
        put(p - u - v, vec2(-1.0, -1.0)); put(p + u - v, vec2(1.0, -1.0));
        put(p - u + v, vec2(-1.0, 1.0)); put(p + u + v, vec2(1.0, 1.0));
        EndPrimitive();
        return;
    }
    if (kind == 4) {                                    // ---- a butterfly: two flapping wings
        vec2 xy = p0.xy + drift * age + vec2(sin(age * 0.9 + s * 7.0) * 34.0 + sin(age * 2.3 + s) * 8.0,
                                             cos(age * 0.7 + s * 5.0) * 34.0);
        vec3 p = vec3(xy, p0.z + sin(age * 1.6 + s * 3.0) * 7.0 + ground_z(xy));
        float hd = atan(cos(age * 0.7 + s * 5.0) * 0.7 * 34.0, -sin(age * 0.9 + s * 7.0) * 0.9 * 34.0 + drift.x);
        vec3 f = vec3(cos(hd), sin(hd), 0.0), r = vec3(-f.y, f.x, 0.0);
        float flap = sin(age * 17.0 + s * 10.0);
        vec3 wing = (r * cos(flap) + vec3(0.0, 0.0, 1.0) * sin(flap) * 0.9) * 5.5;
        a_col = vec4(lit(WING_COLS[int(v_c[0].z) % 5], p), fade);
        put(p + f * 2.0, vec2(0.0)); put(p - f * 2.0, vec2(0.0)); put(p + f * 1.5 + wing, vec2(0.0));
        put(p - f * 1.0 + wing * 0.8, vec2(0.0));
        EndPrimitive();
        vec3 wing2 = vec3(-wing.x, -wing.y, wing.z);
        put(p + f * 2.0, vec2(0.0)); put(p - f * 2.0, vec2(0.0)); put(p + f * 1.5 + wing2, vec2(0.0));
        put(p - f * 1.0 + wing2 * 0.8, vec2(0.0));
        EndPrimitive();
        return;
    }
    if (kind == 9) {                                    // ---- a bird: pecking on the ground, then away
        float t_fly = v_b[0].w;
        float af = age - t_fly;
        vec2 dir = drift;
        vec3 p;
        float flap, spread;
        if (af < 0.0) {
            float hop = max(sin(age * 2.6 + s * 20.0), 0.0);
            hop = hop * hop * hop * hop;
            p = vec3(p0.xy + vec2(sin(s * 40.0 + floor(age * 0.4 + s)), cos(s * 31.0 + floor(age * 0.4 + s))) * 6.0,
                     hop * 3.0 + 11.0);         // on top of the grass
            flap = 0.0;
            spread = 0.25;
        } else {
            p = vec3(p0.xy + dir * (70.0 * af + 30.0 * af * af), 11.0 + 34.0 * af + 16.0 * af * af);
            flap = sin(af * 22.0 + s * 9.0);
            spread = 1.0;
            fade = min(fade, 1.0 - smoothstep(3.0, 4.5, af));
        }
        p.z += ground_z(p.xy);
        vec3 f = vec3(dir, 0.0) * 1.5, r = vec3(-dir.y, dir.x, 0.0) * 1.5;
        vec3 c = mix(vec3(0.22, 0.17, 0.14), vec3(0.36, 0.34, 0.33), fract(s * 5.0));
        a_col = vec4(lit(c, p), fade);
        vec3 wing = (r * cos(flap * 0.9) + vec3(0.0, 0.0, 1.0) * sin(flap * 0.9)) * 8.0 * spread;
        vec3 up = vec3(0.0, 0.0, 2.2);
        put(p + f * 5.5 + up * 0.6, vec2(0.0)); put(p - f * 5.0 + up * 0.3, vec2(0.0));
        put(p + wing - f * 0.8 + up * 0.5, vec2(0.0)); put(p + f * 0.5 + up, vec2(0.0));
        EndPrimitive();
        vec3 wing2 = vec3(-wing.x, -wing.y, wing.z);
        put(p + f * 5.5 + up * 0.6, vec2(0.0)); put(p - f * 5.0 + up * 0.3, vec2(0.0));
        put(p + wing2 - f * 0.8 + up * 0.5, vec2(0.0)); put(p + f * 0.5 + up, vec2(0.0));
        EndPrimitive();
        return;
    }
    if (kind == 8) {                                    // ---- a gnat circling its swarm's centre
        vec2 xy = p0.xy + vec2(sin(age * 5.0 + s * 13.0) * 9.0 + sin(age * 9.1 + s * 7.0) * 3.0,
                               cos(age * 4.3 + s * 11.0) * 9.0);
        vec3 p = vec3(xy, p0.z + sin(age * 6.0 + s * 5.0) * 5.0 + ground_z(xy));
        a_col = vec4(lit(vec3(0.12, 0.12, 0.1), p), fade * 0.9);
        a_soft = 2;
        dot_at(p, 0.9);
        return;
    }
    // ---- glowing dots
    vec3 c;
    float r, a;
    vec3 p;
    if (kind == 1) {                                    // firefly
        vec2 xy = p0.xy + vec2(sin(age * 0.5 + s * 7.0) * 26.0 + sin(age * 1.3 + s * 3.0) * 7.0,
                               cos(age * 0.43 + s * 5.0) * 26.0);
        p = vec3(xy, p0.z + sin(age * 0.8 + s * 2.0) * 9.0);
        float blink = smoothstep(0.2, 0.9, sin(age * 1.9 + s * 20.0)) * 0.85 + 0.15;
        c = vec3(0.78, 1.0, 0.35);
        r = 6.5;
        a = min(1.0, blink * (0.35 + 0.95 * u_night));
    } else if (kind == 6) {                             // ember rising from the ash
        vec2 xy = p0.xy + drift * age + vec2(sin(age * 2.0 + s * 9.0), cos(age * 1.7 + s * 4.0)) * 6.0;
        p = vec3(xy, p0.z + 22.0 * age);
        c = vec3(1.0, 0.45 + 0.2 * fract(s * 3.0), 0.12);
        r = 1.8;
        a = (0.6 + 0.4 * sin(age * 9.0 + s * 30.0)) * (1.0 - age / life);
    } else if (kind == 7) {                             // snow glitter blown along low
        vec2 xy = p0.xy + (u_wind * 26.0 + drift) * age;
        p = vec3(xy, p0.z + sin(age * 2.0 + s * 6.0) * 4.0);
        float tw = pow(max(sin(age * 7.0 + s * 40.0), 0.0), 6.0);
        c = vec3(0.92, 0.96, 1.0);
        r = 1.4 + 1.2 * tw;
        a = 0.25 + 0.75 * tw;
    } else {                                            // dust mote / pollen drifting in the sun
        vec2 xy = p0.xy + (drift + u_wind * (kind == 3 ? 9.0 : 3.0)) * age
                + vec2(sin(age * 0.7 + s * 8.0), cos(age * 0.6 + s * 5.0)) * 5.0;
        p = vec3(xy, p0.z + sin(age * 0.5 + s * 3.0) * 6.0);
        c = kind == 3 ? vec3(1.0, 0.9, 0.45) : vec3(1.0, 0.95, 0.8);
        r = kind == 3 ? 1.1 : 0.9;
        a = (kind == 3 ? 0.55 : 0.32) * (1.0 - u_night);
    }
    p.z += ground_z(p.xy);
    a_col = vec4(lt_fogged(c, p), a * fade);
    dot_at(p, r);
}
"""

FS = """
#version 330
in vec2 a_uv;
in vec4 a_col;
flat in int a_soft;
out vec4 f_color;
void main() {
    float d = dot(a_uv, a_uv);
    if (a_soft == 1) {          // glow: a soft dot with a bright core
        if (d >= 1.0) discard;
        float k = 1.0 - d;
        vec3 rgb = mix(a_col.rgb, vec3(1.0), k * k * k * 0.6);
        f_color = vec4(rgb, a_col.a * k * k);
        return;
    }
    if (d > 1.0) discard;       // leaves / flakes / gnats: rounded; wings and birds: uv is 0
    if (a_col.a < 0.5) discard;
    f_color = vec4(a_col.rgb, 1.0);
}
"""


class AmbientLife:
    """Mixed into View3D."""

    _amb = None

    def _amb_init(self):
        if self._amb is not None:
            return self._amb
        ctx = self.ctx
        gs = lighting3d.inject(terrain3d.inject(GS))
        prog = ctx.program(vertex_shader=VS, geometry_shader=gs, fragment_shader=FS)
        lighting3d.bind(prog)
        buf = ctx.buffer(reserve=MAX_MOTES * STRIDE * 4)
        geo = ctx.geometry([BufferDescription(buf, "4f 4f 4f", ["in_a", "in_b", "in_c"])], mode=ctx.POINTS)
        data = array("f", bytes(MAX_MOTES * STRIDE * 4))
        self._amb = {"prog": prog, "buf": buf, "geo": geo, "data": data, "end": [0.0] * MAX_MOTES,
                     "kind": [-1] * MAX_MOTES, "cur": 0, "dirty": True, "t": None, "flocks": {}, "cool": {},
                     "trees": [], "tree_t": -99.0, "acc": {}, "seed": random.random() * 1000.0}
        return self._amb

    # ------------------------------------------------------------------ the pool
    def _amb_now(self):
        return float(getattr(self, "flame_t", 0.0))

    def amb_spawn(self, kind, x, y, z, life, seed=None, p1=0.0, vx=0.0, vy=0.0, p2=0.0):
        """Put one mote into a free slot (or the oldest). Returns the slot."""
        a = self._amb
        now = self._amb_now()
        end = a["end"]
        i = a["cur"]
        for _ in range(MAX_MOTES):          # the next slot that's finished (else just the next one)
            if end[i] <= now:
                break
            i = (i + 1) % MAX_MOTES
        a["cur"] = (i + 1) % MAX_MOTES
        if a.get("warm") and kind != BIRD:      # arriving somewhere: as if they'd been there a while
            now -= random.random() * life * 0.8
        end[i] = now + life
        a["kind"][i] = kind
        d = a["data"]
        o = i * STRIDE
        d[o:o + STRIDE] = array("f", (x, y, z, float(kind), now, life, random.random() if seed is None else seed, p1,
                                      vx, vy, p2, 0.0))
        a["dirty"] = True
        return i

    def _amb_count(self, kind):
        a = self._amb
        now = self._amb_now()
        return sum(1 for k, e in zip(a["kind"], a["end"]) if k == kind and e > now)

    # ------------------------------------------------------------------ what lives where (every frame)
    def amb_tick(self, vl):
        """Spawn ambient motes around the viewer and startle flocks. Call once per frame per view."""
        a = self._amb_init()
        now = self._amb_now()
        last = a["t"]
        a["t"] = now
        if vl != "over" or last is None or self.state != "playing":
            return
        dt = min(0.1, max(0.0, now - last))
        if dt <= 0.0:
            return
        gm = ground3d.ground_map(self)
        if gm is None:
            return
        vx, vy = self.view_pos()
        seen = a.get("at")
        a["at"] = (vx, vy)
        if seen is None or abs(seen[0] - vx) + abs(seen[1] - vy) > 600:     # just arrived (start, travel)
            a["warm"] = True
            for _ in range(3):
                self._amb_spawn_all(a, gm, vx, vy, 2.0, now)
            a["warm"] = False
        self._amb_spawn_all(a, gm, vx, vy, dt, now)

    def _amb_spawn_all(self, a, gm, vx, vy, dt, now):
        share = {b: gm.at(b, vx, vy) for b in ("tundra", "ash", "mire", "highlands", "meadow")}
        forest = max(0.0, 1.0 - sum(share.values()))
        water = gm.at("water", vx, vy)
        night = min(1.0, self.darkness * 1.4)
        season = self.season
        acc = a["acc"]
        rnd = random.random
        wind = (0.91, 0.41)

        def due(key, rate, cap, kind):
            """How many of `kind` to make this frame (rate per second, at most cap alive)."""
            if rate <= 0.0:
                return 0
            acc[key] = acc.get(key, 0.0) + rate * dt
            n = int(acc[key])
            acc[key] -= n
            if n and self._amb_count(kind) >= cap:
                return 0
            return n

        def around(r0, r1):
            ang = rnd() * math.tau
            d = r0 + (r1 - r0) * math.sqrt(rnd())
            return vx + math.cos(ang) * d, vy + math.sin(ang) * d

        # ---- falling leaves from the canopies nearby
        L = self.layers["over"]
        if now - a["tree_t"] > 1.0:
            a["tree_t"] = now
            a["trees"] = [t for t in L.trees if getattr(t, "kind", "") == "tree" and getattr(t, "state", "") == "full"
                          and abs(t.center_x - vx) < 700 and abs(t.center_y - vy) < 600]
        trees = a["trees"]
        if trees:
            rate = {"autumn": 0.5, "winter": 0.03, "spring": 0.06, "summer": 0.08}.get(season, 0.08) * len(trees)
            for _ in range(due("leaf", rate, 140 if season == "autumn" else 40, LEAF)):
                t = random.choice(trees)
                R = min(t.width, t.height) / 2
                ang, d = rnd() * math.tau, rnd() * R * 0.8
                col = random.choice((0, 1, 2, 3)) if season == "autumn" else random.choice((3, 4, 5, 1))
                z = R * (1.2 + 0.6 * rnd())
                fall = 12 + rnd() * 10
                self.amb_spawn(LEAF, t.center_x + math.cos(ang) * d, t.center_y + math.sin(ang) * d, z,
                               z / fall + 3.0 + rnd() * 3.0, p1=fall, vx=wind[0] * 8 + (rnd() - 0.5) * 8,
                               vy=wind[1] * 8 + (rnd() - 0.5) * 8, p2=float(col))
        # ---- fireflies: dusk and night, by water and in the woods
        ff = (0.3 + water + 0.6 * forest + 0.3 * share["meadow"] + 0.4 * share["mire"]) * \
            (1.0 - share["tundra"]) * (1.0 - share["ash"]) * (0.0 if season == "winter" else 1.0)
        if night > 0.25 and ff > 0.2:
            for _ in range(due("firefly", 6.0 * ff, int(18 + 26 * min(ff, 1.0)), FIREFLY)):
                x, y = around(30, 460)
                if gm.at("water", x, y) + 0.5 * self._amb_green(gm, x, y) > 0.35:
                    self.amb_spawn(FIREFLY, x, y, 8 + rnd() * 26, 6 + rnd() * 6)
        # ---- dust motes in the sunlight; pollen and butterflies in spring / summer meadows
        if night < 0.3 and share["tundra"] < 0.5:
            for _ in range(due("dust", 8.0, 50, DUST)):
                x, y = around(0, 420)
                self.amb_spawn(DUST, x, y, 10 + rnd() * 70, 5 + rnd() * 5, vx=(rnd() - 0.5) * 6, vy=(rnd() - 0.5) * 6)
            if season in ("spring", "summer") and share["meadow"] + 0.4 * forest > 0.3:
                k = share["meadow"] + 0.4 * forest
                for _ in range(due("pollen", 10.0 * k, 60, POLLEN)):
                    x, y = around(0, 450)
                    self.amb_spawn(POLLEN, x, y, 6 + rnd() * 40, 6 + rnd() * 4)
                for _ in range(due("butterfly", 0.6 * k, 7, BUTTERFLY)):
                    x, y = around(80, 420)
                    if self._amb_green(gm, x, y) > 0.5:
                        self.amb_spawn(BUTTERFLY, x, y, 14 + rnd() * 14, 10 + rnd() * 8,
                                       vx=(rnd() - 0.5) * 20, vy=(rnd() - 0.5) * 20, p2=float(random.randrange(5)))
        # ---- the Ashlands: ash flakes drifting down, embers rising
        if share["ash"] > 0.25:
            k = share["ash"]
            for _ in range(due("ash", 14.0 * k, 90, ASH)):
                x, y = around(0, 520)
                z = 40 + rnd() * 90
                fall = 7 + rnd() * 7
                self.amb_spawn(ASH, x, y, z, z / fall + 2.0, p1=fall, vx=wind[0] * 12, vy=wind[1] * 12)
            for _ in range(due("ember", 5.0 * k, 30, EMBER)):
                x, y = around(0, 480)
                self.amb_spawn(EMBER, x, y, 2 + rnd() * 6, 1.5 + rnd() * 2.0, vx=(rnd() - 0.5) * 10)
        # ---- the tundra: glittering snow blown along the ground
        if share["tundra"] > 0.25 and night < 0.6:
            for _ in range(due("sparkle", 14.0 * share["tundra"], 70, SPARKLE)):
                x, y = around(0, 480)
                self.amb_spawn(SPARKLE, x - wind[0] * 60, y - wind[1] * 60, 2 + rnd() * 16, 2.5 + rnd() * 2.5,
                               vx=(rnd() - 0.5) * 10, vy=(rnd() - 0.5) * 10)
        # ---- the Mire: gnat swarms over the bog pools
        if share["mire"] > 0.2 and night < 0.8:
            pools = [(x, y, r) for x, y, r, _ in getattr(self, "swamp_pools", ())
                     if abs(x - vx) < 650 and abs(y - vy) < 550]
            if pools:
                for _ in range(due("gnats", 0.5, 4 * 14, GNAT)):
                    x, y, r = random.choice(pools)
                    ang = rnd() * math.tau
                    cx, cy, cz = x + math.cos(ang) * r * 0.7, y + math.sin(ang) * r * 0.7, 16 + rnd() * 12
                    life = 10 + rnd() * 6
                    for _ in range(14):
                        self.amb_spawn(GNAT, cx, cy, cz, life)
        self._amb_birds(gm, vx, vy, night, now)

    @staticmethod
    def _amb_green(gm, x, y):
        """How grassy the land is at (x, y) (forest + meadow + some of the Highlands / Mire)."""
        other = sum(gm.at(b, x, y) for b in ("tundra", "ash", "mire", "highlands"))
        return max(0.0, 1.0 - other) + 0.4 * (gm.at("mire", x, y) + gm.at("highlands", x, y))

    def _amb_birds(self, gm, vx, vy, night, now):
        """Flocks pecking at the ground on a fixed scatter of spots near the viewer; anyone walking up to one
        sends it flapping off away from them."""
        a = self._amb
        flocks, cool = a["flocks"], a["cool"]
        C = FLOCK_CELL
        reach = 620
        movers = [p.sprite.position for p in self.players.values() if p.alive and p.layer == "over"]
        movers += [(z.center_x, z.center_y) for z in self.layers["over"].zombies
                   if abs(z.center_x - vx) < reach and abs(z.center_y - vy) < reach]
        # startle / forget flocks
        for key in list(flocks):
            fl = flocks[key]
            x, y, slots, t_fly = fl
            if t_fly is None:
                if abs(x - vx) > reach + 200 or abs(y - vy) > reach + 200 or night > 0.5:
                    for i in slots:
                        a["end"][i] = 0.0
                    a["dirty"] = True
                    del flocks[key]
                    continue
                near = [m for m in movers if (m[0] - x) ** 2 + (m[1] - y) ** 2 < FLOCK_NEAR ** 2]
                if near:
                    mx, my = near[0]
                    ang = math.atan2(y - my, x - mx)
                    d = self._amb["data"]
                    for i in slots:
                        o = i * STRIDE
                        aa = ang + (random.random() - 0.5) * 1.2
                        d[o + 7] = now - d[o + 4] + random.random() * 0.25      # take off (age at take-off)
                        d[o + 8], d[o + 9] = math.cos(aa), math.sin(aa)
                        d[o + 5] = d[o + 7] + 5.0
                        a["end"][i] = d[o + 4] + d[o + 5]
                    a["dirty"] = True
                    fl[3] = now
                    cool[key] = now + 90.0
            elif now - t_fly > 6.0:
                del flocks[key]
        if night > 0.4:
            return
        seed = int(getattr(self, "seed", 0) or 0) % 100003
        for cj in range(int((vy - reach) // C), int((vy + reach) // C) + 1):
            for ci in range(int((vx - reach) // C), int((vx + reach) // C) + 1):
                key = (ci, cj)
                if key in flocks or cool.get(key, 0.0) > now:
                    continue
                h = ground3d_hash(ci, cj, seed)
                x, y = (ci + 0.2 + 0.6 * ground3d_hash(ci, cj, seed + 7)) * C, (cj + 0.2 + 0.6 * ground3d_hash(ci, cj, seed + 13)) * C
                green = self._amb_green(gm, x, y) - gm.at("highlands", x, y) * 0.6
                if h > 0.12 * green or (vx - x) ** 2 + (vy - y) ** 2 < 260 ** 2:
                    continue
                if gm.mask_at(x, y) < 0.5:
                    continue
                slots = [self.amb_spawn(BIRD, x + (random.random() - 0.5) * 30, y + (random.random() - 0.5) * 30, 0.0,
                                        NEVER * 2, p1=NEVER, vx=1.0, vy=0.0)
                         for _ in range(3 + int(ground3d_hash(ci, cj, seed + 3) * 4))]
                flocks[key] = [x, y, slots, None]

    # ------------------------------------------------------------------ drawing
    def amb_draw(self, vl, glow):
        """Draw the motes: glow=False with the standing things ("lit" stage, depth test on), glow=True with the
        additive glows ("glow" stage)."""
        a = self._amb
        if a is None or vl != "over" or self._sh_pass:
            return
        if a["dirty"]:
            a["buf"].write(a["data"])
            a["dirty"] = False
        prog = a["prog"]
        self.hill_apply(prog)
        prog.set_uniform_safe("u_time", self._amb_now())
        prog.set_uniform_safe("u_glow", int(glow))
        prog.set_uniform_safe("u_night", min(1.0, self.darkness * 1.4))
        prog.set_uniform_safe("u_wind", (0.91, 0.41))
        ctx = self.ctx
        from pyglet import gl
        ctx.enable(ctx.BLEND)
        if glow:
            ctx.blend_func = (ctx.SRC_ALPHA, ctx.ONE)
            gl.glDepthMask(gl.GL_FALSE)
        try:
            a["geo"].render(prog, vertices=MAX_MOTES)
        finally:
            ctx.blend_func = ctx.BLEND_DEFAULT
            gl.glDepthMask(gl.GL_TRUE)


def ground3d_hash(i, j, s):
    """A steady 0..1 hash of a grid cell (where the bird flocks sit)."""
    h = (i * 374761393 + j * 668265263 + s * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0
