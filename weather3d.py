"""
weather3d.py - the weather in the 3D view: rain, snow, lightning, wet ground and snow cover. Mixed into the
game window (before View3D, so its overrides of _lt_frame and fx_ambient come first).

weather.py decides WHAT the weather is (the host picks it, co-op clients get it in the snapshots) and eases
it in and out (weather_shown, weather_k). Everything here is only looks, worked out on each computer for
itself, so online clients and split-screen players all see the same weather in their own view:

  * Rain and snow are real 3D drops falling in the world around the camera, drawn by the GPU. One fixed
    buffer of random seeds (never rebuilt) goes through a geometry shader that places each drop in a box
    around the camera from the seed, the time and how far the wind has blown everything. The box wraps:
    a drop that falls out of the bottom comes back in at the top, and drops stay put in the world when the
    camera moves (they wrap round at the box's far edges instead of sliding along with you). Heights are
    measured from the ground under each drop, so the rain never falls inside a hill.
      - rain: thin streaks stretched along the way they fall (faster and slanted by the wind in a storm,
        with gusts), lit faintly by the time of day and brighter near fires and lamps. At the bottom each
        drop turns into a little splash ring on the ground.
      - snow: soft flakes drifting from side to side and tumbling as they fall.
    The "Rain & snow" option (Screen & graphics) halves the number of drops on slow computers.
  * Wet ground: wx_wet rises while it rains and dries slowly afterwards (faster in the sun). Snow cover:
    wx_snow builds up while it snows and melts afterwards (leaving the ground wet). Both go to every world
    shader through lighting3d's LightBlock (lt_wx); lighting3d.lt_weather darkens and glosses wet surfaces,
    fills puddles on the ground and whitens the tops of things (ground, rocks, roofs, tree tops) under snow.
    Rivers and ponds get rings from the rain (water3d.py, lighting3d.lt_rain_rings).
  * Lightning: weather.py's flash (and its thunder) starts a bolt here. For a moment the whole scene is lit
    up - the ambient light (light map and every lit shader) jumps towards a cold white and lt_weather
    brightens the surfaces - with a flicker or two. In first person a jagged bolt (and a glow round it in
    the clouds) shows in the sky; it blooms with the other glows (post3d.py).
Underground none of this happens (the layers keep their own haze, biomes.py).
"""
import math
import random
import time
from array import array

from arcade.gl import BufferDescription
from pyglet import gl

import lighting3d

MAX_DROPS = 6000
DROPS = {"rain": 2800, "storm": 4600, "snow": 2600}     # at full strength ("Rain & snow: Light" = half)
FALL = {"rain": 780.0, "storm": 1000.0, "snow": 70.0}  # px per second
WIND = {"rain": 45.0, "storm": 260.0, "snow": 18.0}    # px per second, blowing east (+ gusts in a storm)
WET_RISE = {"rain": 1 / 40, "storm": 1 / 22}           # per second at full rain: soaked in ~half a minute
DRY_DAY, DRY_NIGHT = 1 / 150, 1 / 300                  # per second: dries in a few minutes, slower at night
SNOW_RISE = 1 / 80                                     # per second while it snows: white in about a minute
SNOW_MELT, SNOW_MELT_WINTER = 1 / 45, 1 / 160          # per second once it stops (slow in winter)
FLASH_COL = (0.86, 0.9, 1.0)                           # lightning's light


# ----------------------------------------------------------------- the drops
DROP_VS = """
#version 330
in vec4 in_seed;
out vec4 v_seed;
void main() { v_seed = in_seed; gl_Position = vec4(0.0); }
"""

# One point (seed) in, one quad out: a streak (rain), a splash ring on the ground (rain), or a flake (snow).
DROP_GEO = """
#version 330
layout (points) in;
layout (triangle_strip, max_vertices = 4) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
%LIB%
uniform vec2 box_c;       // the box's centre (x, y)
uniform vec3 box_s;       // its size; the height is measured up from the ground under each drop
uniform vec2 drift;       // how far the wind has blown everything (wrapped by the box)
uniform float t;          // seconds (wrapped)
uniform float fall;       // px / s
uniform vec2 wind;        // px / s now (for the slant of the streaks)
uniform int kind;         // 0 rain, 1 snow
uniform float streak;     // rain: streak length, in seconds of fall
uniform float size;       // rain: width, snow: flake radius (world px)
uniform float splash_h;   // rain: below this height a drop is drawn as its splash
uniform vec3 eye;
uniform vec3 cam_r;       // camera right / up (snow flakes face the camera)
uniform vec3 cam_u;
uniform vec2 vp_size;     // the view in pixels
uniform float count_k;    // 0..1: how many of the drops to show (the weather easing in)
uniform vec2 near_fade;   // drops closer than this to the camera fade out (they'd be big blurry columns)
in vec4 v_seed[];
out vec2 g_uv;
out vec3 g_pos;
out float g_a;
flat out int g_mode;      // 0 drop / flake, 1 splash
void emit(vec3 p, vec2 uv) {
    g_pos = p;
    g_uv = uv;
    gl_Position = window.projection * window.view * vec4(p, 1.0);
    EmitVertex();
}
void main() {
    vec4 s = v_seed[0];
    if (s.w > count_k) return;
    float speed = fall * (0.85 + 0.3 * fract(s.w * 7.13));
    vec2 lo = box_c - box_s.xy * 0.5;
    vec2 xy = s.xy * box_s.xy + drift;
    if (kind == 1)    // flakes wander from side to side
        xy += vec2(sin(t * (0.6 + s.z) + s.x * 40.0), cos(t * (0.45 + s.y * 0.5) + s.z * 30.0)) * 16.0;
    xy = lo + mod(xy - lo, box_s.xy);
    float h = mod(s.z * box_s.z - t * speed, box_s.z);
    vec2 e = min(xy - lo, lo + box_s.xy - xy);
    g_a = smoothstep(0.0, 120.0, min(e.x, e.y));      // fade out at the box's sides (no popping)
    if (kind == 0 && h < splash_h) {
        // a splash: a ring spreading on the ground
        float ph = 1.0 - h / splash_h;
        float r = 2.0 + 7.0 * ph;
        g_a *= (1.0 - ph) * 0.9;
        g_mode = 1;
        float z = ground_z(xy) + 1.5;
        emit(vec3(xy + vec2(-r, -r), z), vec2(-1.0, -1.0));
        emit(vec3(xy + vec2(r, -r), z), vec2(1.0, -1.0));
        emit(vec3(xy + vec2(-r, r), z), vec2(-1.0, 1.0));
        emit(vec3(xy + vec2(r, r), z), vec2(1.0, 1.0));
        EndPrimitive();
        return;
    }
    g_mode = 0;
    vec3 p = vec3(xy, ground_z(xy) + h);
    float dist = length(p - eye);
    if (dist < near_fade.x) return;
    g_a *= smoothstep(near_fade.x, near_fade.y, dist);
    if (kind == 1) {
        // a flake: a little quad facing the camera, spinning and flipping as it tumbles
        float a = t * (1.0 + 2.0 * s.y) + s.x * 6.28;
        float flip = max(0.3, abs(cos(t * (1.3 + s.z) + s.w * 9.0)));
        float r = size * (0.6 + 0.8 * fract(s.w * 3.7));
        vec3 ax = (cam_r * cos(a) + cam_u * sin(a)) * r;
        vec3 ay = (-cam_r * sin(a) + cam_u * cos(a)) * r * flip;
        g_a *= smoothstep(0.0, 25.0, h);
        emit(p - ax - ay, vec2(-1.0, -1.0));
        emit(p + ax - ay, vec2(1.0, -1.0));
        emit(p - ax + ay, vec2(-1.0, 1.0));
        emit(p + ax + ay, vec2(1.0, 1.0));
        EndPrimitive();
        return;
    }
    // a streak from where the drop was a moment ago (tail) to where it is (head), a few pixels wide
    vec3 tail = p - vec3(wind, -speed) * streak;
    mat4 mvp = window.projection * window.view;
    vec4 c0 = mvp * vec4(tail, 1.0), c1 = mvp * vec4(p, 1.0);
    if (c0.w < 3.0 || c1.w < 3.0) return;
    vec2 s0 = c0.xy / c0.w * vp_size, s1 = c1.xy / c1.w * vp_size;
    vec2 d = s1 - s0;
    float ln = length(d);
    if (ln < 0.01) return;
    vec2 side = vec2(-d.y, d.x) / ln;
    float wpx = size * window.projection[1][1] * vp_size.y / c1.w;    // the width in pixels...
    g_a *= min(1.0, wpx);                                             // ...thinner than 1: fainter instead
    vec2 off = side * clamp(wpx, 1.0, 3.0) / vp_size;
    g_pos = tail; g_uv = vec2(-1.0, 0.0); gl_Position = c0 - vec4(off * c0.w, 0.0, 0.0); EmitVertex();
    g_pos = tail; g_uv = vec2(1.0, 0.0); gl_Position = c0 + vec4(off * c0.w, 0.0, 0.0); EmitVertex();
    g_pos = p; g_uv = vec2(-1.0, 1.0); gl_Position = c1 - vec4(off * c1.w, 0.0, 0.0); EmitVertex();
    g_pos = p; g_uv = vec2(1.0, 1.0); gl_Position = c1 + vec4(off * c1.w, 0.0, 0.0); EmitVertex();
    EndPrimitive();
}
"""

DROP_FS = """
#version 330
uniform int kind;
uniform vec3 col;
uniform float alpha;
in vec2 g_uv;
in vec3 g_pos;
in float g_a;
flat in int g_mode;
out vec4 f_color;
void main() {
    float a;
    if (g_mode == 1) {                  // splash ring
        float r = length(g_uv);
        a = smoothstep(0.55, 0.8, r) * smoothstep(1.0, 0.85, r) * 0.6;
    } else if (kind == 0) {             // streak: soft sides, fading towards the tail
        a = (1.0 - abs(g_uv.x)) * g_uv.y;
    } else {                            // flake: a soft round blob
        float r = length(g_uv);
        if (r > 1.0) discard;
        a = smoothstep(1.0, 0.35, r);
    }
    // lit by the time of day, brighter near fires and lamps (lighting3d.py "lit" stage), and the lightning
    vec3 light = lt_amb.rgb + lt_points(g_pos, vec3(0.0)) * 1.8 + vec3(lt_wx.z * 1.5);
    vec3 c = col * min(light, vec3(1.8));
    a *= alpha * g_a * (1.0 - lt_fog_k(g_pos) * 0.85);
    if (a < 0.004) discard;
    f_color = vec4(c, a);
}
"""

# ----------------------------------------------------------------- the lightning bolt (first person)
BOLT_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec3 in_uv;        // across (-1..1), 0, 1 = the bolt / 2 = the glow round it
out vec3 v_uv;
void main() { v_uv = in_uv; gl_Position = window.projection * window.view * vec4(in_pos, 1.0); }
"""

BOLT_FS = """
#version 330
uniform float bright;
in vec3 v_uv;
out vec4 f_color;
void main() {
    if (v_uv.z > 1.5) {                 // the clouds lit up round the bolt
        float r = length(v_uv.xy);
        float k = (1.0 - smoothstep(0.0, 1.0, r)) * 0.22;
        f_color = vec4(vec3(0.7, 0.75, 0.95) * k * bright, 1.0);
        return;
    }
    float x = abs(v_uv.x);
    float core = 1.0 - smoothstep(0.15, 0.5, x);
    float halo = (1.0 - x) * 0.45;
    f_color = vec4(vec3(0.85, 0.9, 1.0) * (core * 1.4 + halo) * bright, 1.0);
}
"""


class Weather3D:
    """Mixed into the game window, before View3D."""

    wx_wet = 0.0          # how wet the ground is (0..1)
    wx_snow = 0.0         # how much snow lies on things (0..1)
    wx_flash_k = 0.0      # lightning light right now (0..1)
    wx_bolt_age = 9.0     # seconds since the last bolt
    wx_bolt_seed = 0
    _wx_prev_flash = 0.0
    _wx_drift = (0.0, 0.0)
    _wx_t0 = None
    _wx_broken = False

    # ------------------------------------------------------------------ option
    def wx_light(self):
        """"Rain & snow: Light" in Screen & graphics: half the drops (config "weather_drops": "light")."""
        return (getattr(self, "cfg", {}) or {}).get("weather_drops", "full") == "light"

    def toggle_weather_drops(self):
        self.cfg["weather_drops"] = "full" if self.wx_light() else "light"
        self.save_cfg()

    # ------------------------------------------------------------------ every frame (weather.py)
    def wx_tick(self, dt):
        """Wetness, snow cover, wind and the lightning bolt. Called once a frame from weather._weather_visuals."""
        kind = getattr(self, "weather_shown", "clear")
        k = getattr(self, "weather_k", 0.0)
        dark = getattr(self, "darkness", 0.0)
        if self._wx_t0 is None:
            self._wx_t0 = time.perf_counter()
        # wet ground
        rain = k if kind in WET_RISE else 0.0
        if rain > 0.05:
            self.wx_wet = min(1.0, self.wx_wet + WET_RISE[kind] * rain * dt)
        else:
            dry = DRY_DAY + (DRY_NIGHT - DRY_DAY) * dark
            self.wx_wet = max(0.0, self.wx_wet - dry * dt)
        # snow cover (snow only comes in winter - settings.SEASON_WEATHER)
        if kind == "snow" and k > 0.05:
            self.wx_snow = min(1.0, self.wx_snow + SNOW_RISE * k * dt)
        elif self.wx_snow > 0:
            melt = SNOW_MELT_WINTER if getattr(self, "season", "") == "winter" else SNOW_MELT
            gone = min(self.wx_snow, melt * dt)
            self.wx_snow -= gone
            self.wx_wet = min(1.0, self.wx_wet + gone * 0.8)        # melting snow leaves the ground wet
        # wind: blows the drops along (gusty in a storm)
        t = self.wx_time()
        w = WIND.get(kind, 0.0)
        if kind == "storm":
            w *= 1.0 + 0.45 * math.sin(t * 0.7) * math.sin(t * 1.9 + 1.0)
        self._wx_wind = (w, w * 0.18)
        dx, dy = self._wx_drift
        self._wx_drift = ((dx + self._wx_wind[0] * dt) % 1.0e6, (dy + self._wx_wind[1] * dt) % 1.0e6)
        # lightning: weather.py sets weather_flash to 1 (and plays the thunder) - a new bolt
        f = getattr(self, "weather_flash", 0.0)
        if f > self._wx_prev_flash + 0.5:
            self.wx_bolt_age = 0.0
            self.wx_bolt_seed = random.randrange(1 << 30)
            self._wx_bolt_geo = None
        self._wx_prev_flash = f
        self.wx_bolt_age += dt
        self.wx_flash_k = self._wx_flicker(self.wx_bolt_age)

    @staticmethod
    def _wx_flicker(age):
        """Lightning's brightness `age` seconds after the strike: a bright flash, a flicker or two, gone."""
        if age > 0.6:
            return 0.0
        k = math.exp(-age * 5.0)
        if 0.07 < age < 0.12 or 0.2 < age < 0.25:
            k *= 0.35                       # the flicker
        return k

    def wx_time(self):
        return (time.perf_counter() - (self._wx_t0 or 0.0)) % 600.0

    def wx_bolt_on(self):
        return self.wx_bolt_age < 0.4

    # ------------------------------------------------------------------ hooks into the lighting
    def fx_ambient(self, vl):
        """fx3d.fx_ambient with the lightning flash: the ambient light jumps towards white for a moment, so the
        light map (the ground) and every lit shader light up together."""
        amb = super().fx_ambient(vl)
        f = self.wx_flash_k
        if vl == "over" and f > 0.01:
            f = min(1.0, f * 0.9)
            amb = tuple(a + (c - a) * f for a, c in zip(amb, FLASH_COL))
        return amb

    def _lt_frame(self, L, vl, dk, sx, sy, fp):
        """View3D._lt_frame + the weather on surfaces (lighting3d.lt_weather) for this view."""
        super()._lt_frame(L, vl, dk, sx, sy, fp)
        st = self._lt
        t = self.wx_time()
        if vl != "over":
            st.wx, st.wx2 = (0.0, 0.0, 0.0, t), (0.0, 0.0, 0.0, 0.0)
            return
        kind, k = getattr(self, "weather_shown", "clear"), getattr(self, "weather_k", 0.0)
        rain = k * (1.0 if kind == "storm" else 0.7) if kind in ("rain", "storm") else 0.0
        st.wx = (self.wx_wet, self.wx_snow, self.wx_flash_k * 0.6, t)
        st.wx2 = (rain, 0.0, 0.0, 0.0)

    # ------------------------------------------------------------------ GPU bits
    def _wx_init(self):
        if getattr(self, "_wx_prog", None) is not None:
            return
        ctx = self.ctx
        geo = DROP_GEO.replace("%LIB%", self._mesh_lib)        # sprite lib + ground_z (terrain3d.py)
        p = self._wx_prog = ctx.program(vertex_shader=DROP_VS, geometry_shader=geo,
                                        fragment_shader=lighting3d.inject(DROP_FS, frag=True))
        lighting3d.bind(p)
        rnd = random.Random(1234)
        seeds = array("f", [rnd.random() for _ in range(MAX_DROPS * 4)])
        self._wx_geo = ctx.geometry([BufferDescription(ctx.buffer(data=seeds), "4f", ["in_seed"])],
                                    mode=ctx.POINTS)
        self._wx_bolt_prog = ctx.program(vertex_shader=BOLT_VS, fragment_shader=BOLT_FS)
        self._wx_bolt_buf = ctx.buffer(reserve=4 * 6 * 6 * 64)
        self._wx_bolt_vao = ctx.geometry([BufferDescription(self._wx_bolt_buf, "3f 3f", ["in_pos", "in_uv"])],
                                         mode=ctx.TRIANGLES)
        self._wx_bolt_geo = None

    def _wx_fail(self, e):
        print("3D rain / snow switched off - this graphics card didn't like it:", e)
        self._wx_broken = True

    # ------------------------------------------------------------------ drawing (view3d.py)
    def wx_draw_precip(self, vl):
        """Rain or snow around this view's camera. Call in the "lit" stage with the 3D camera on (depth test
        is turned on here, depth writes off)."""
        kind = getattr(self, "weather_shown", "clear")
        k = getattr(self, "weather_k", 0.0)
        if vl != "over" or kind not in DROPS or k <= 0.01 or self._wx_broken:
            return
        try:
            self._wx_init()
            self._wx_draw(kind, k)
        except Exception as e:          # noqa: BLE001 - a graphics extra never stops the game
            self._wx_fail(e)

    def _wx_draw(self, kind, k):
        ctx = self.ctx
        p = self._wx_prog
        (ex, ey, ez), f, r, u, d, vw, vh = self._basis()
        snow = kind == "snow"
        if self.fp_on():
            # first person: a box round your eyes, reaching a little further ahead than behind
            fx, fy = f[0], f[1]
            n = math.hypot(fx, fy) or 1.0
            c = (ex + fx / n * 220, ey + fy / n * 220)
            s = (900.0, 900.0, 380.0) if snow else (1000.0, 1000.0, 460.0)
            many = 1.0
            p["near_fade"] = (30.0, 130.0) if snow else (12.0, 70.0)
        else:
            # tilted camera: the patch of ground on screen (more of it to the north), up to below the camera
            fx, fy = self.camera.position
            c = (fx, fy + 190)
            top = max(200.0, ez - self.ground_z(fx, fy) - 70)
            s = (2100.0, 1400.0, min(560.0, top))
            many = 1.0
            p["near_fade"] = (80.0, 300.0)
        n = int(DROPS[kind] * many * (0.5 if self.wx_light() else 1.0))
        dx, dy = self._wx_drift
        p["box_c"] = c
        p["box_s"] = s
        p["drift"] = (dx % s[0], dy % s[1])
        p["t"] = self.wx_time()
        p["fall"] = FALL[kind]
        p["wind"] = getattr(self, "_wx_wind", (0.0, 0.0))
        p["kind"] = int(snow)
        p["streak"] = 0.045 if kind == "storm" else 0.04
        p["size"] = 2.6 if snow else 0.9
        p["splash_h"] = 0.0 if snow else FALL[kind] * 0.09
        p["eye"] = (ex, ey, ez)
        p["cam_r"] = tuple(r)
        p["cam_u"] = tuple(u)
        vx, vy, vpw, vph = self.ctx.viewport
        p["vp_size"] = (max(1.0, vpw / 2), max(1.0, vph / 2))
        p["count_k"] = min(1.0, k * 1.2)
        p["col"] = (0.95, 0.97, 1.0) if snow else (0.72, 0.78, 0.88)
        p["alpha"] = 0.9 if snow else (0.5 if kind == "storm" else 0.42)
        self.hill_apply(p)              # HILLS (terrain3d.py): heights above the ground under each drop
        ctx.enable(ctx.BLEND, ctx.DEPTH_TEST)
        ctx.blend_func = ctx.BLEND_DEFAULT
        gl.glDepthMask(gl.GL_FALSE)
        try:
            self._wx_geo.render(p, vertices=min(n, MAX_DROPS))
        finally:
            gl.glDepthMask(gl.GL_TRUE)

    def wx_draw_bolt(self, vl):
        """First person: the lightning bolt in the sky (call in the glow stage, 3D camera on: it blooms)."""
        if vl != "over" or not self.fp_on() or not self.wx_bolt_on() or self._wx_broken:
            return
        try:
            self._wx_init()
            if self._wx_bolt_geo is None:
                self._wx_bolt_geo = self._wx_make_bolt()
            age = self.wx_bolt_age
            bright = 1.0 if age < 0.07 else 0.25 if age < 0.12 else 0.8 if age < 0.2 else 0.15 if age < 0.25 else 0.5
            bright *= 1.0 - age / 0.4
            (ex, ey, ez), f, r, u, *_ = self._basis()
            verts = self._wx_quads(self._wx_bolt_geo, (ex, ey, ez))
            self._wx_bolt_buf.write(verts)
            prog = self._wx_bolt_prog
            prog["bright"] = bright
            ctx = self.ctx
            ctx.enable(ctx.BLEND, ctx.DEPTH_TEST)
            ctx.blend_func = (ctx.ONE, ctx.ONE)
            gl.glDepthMask(gl.GL_FALSE)
            try:
                self._wx_bolt_vao.render(prog, vertices=len(verts) // 6)
            finally:
                gl.glDepthMask(gl.GL_TRUE)
                ctx.blend_func = ctx.BLEND_DEFAULT
        except Exception as e:          # noqa: BLE001
            self._wx_fail(e)

    def _wx_make_bolt(self):
        """A jagged bolt (with a branch or two) far away in the direction you're looking, as line segments
        (x0, y0, z0, x1, y1, z1, width) plus its centre - built once per strike."""
        rnd = random.Random(self.wx_bolt_seed)
        (ex, ey, ez), f, *_ = self._basis()
        yaw = math.atan2(f[1], f[0]) + rnd.uniform(-0.45, 0.45)
        dist = rnd.uniform(2200, 3200)
        bx, by = ex + math.cos(yaw) * dist, ey + math.sin(yaw) * dist
        top, bottom = ez + 2500, ez - 60
        segs = []

        def branch(x, y, z, z_end, width, depth):
            steps = max(3, int((z - z_end) / 150))
            for i in range(steps):
                nz = z - (z - z_end) / (steps - i)
                nx, ny = x + rnd.uniform(-120, 120), y + rnd.uniform(-120, 120)
                segs.append((x, y, z, nx, ny, nz, width))
                if depth < 2 and rnd.random() < 0.16:
                    branch(nx, ny, nz, nz - rnd.uniform(200, 500), width * 0.55, depth + 1)
                x, y, z = nx, ny, nz

        branch(bx, by, top, bottom, 30.0, 0)
        return segs[:60], (bx, by, (top + bottom) / 2)

    def _wx_quads(self, bolt, eye):
        """The bolt's segments as quads facing the camera, plus one big soft glow quad round it."""
        segs, (cx, cy, cz) = bolt
        out = array("f")
        ex, ey, ez = eye
        for x0, y0, z0, x1, y1, z1, w in segs:
            # sideways = along the segment x towards the eye
            ax, ay, az = x1 - x0, y1 - y0, z1 - z0
            vx, vy, vz = ex - x0, ey - y0, ez - z0
            sx, sy, sz = ay * vz - az * vy, az * vx - ax * vz, ax * vy - ay * vx
            n = math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0
            sx, sy, sz = sx / n * w, sy / n * w, sz / n * w
            a = (x0 - sx, y0 - sy, z0 - sz, -1, 0, 1)
            b = (x0 + sx, y0 + sy, z0 + sz, 1, 0, 1)
            c = (x1 - sx, y1 - sy, z1 - sz, -1, 0, 1)
            d = (x1 + sx, y1 + sy, z1 + sz, 1, 0, 1)
            for v in (a, b, c, b, d, c):
                out.extend(v)
        # the glow: a big quad facing the camera round the bolt's middle
        vx, vy = ex - cx, ey - cy
        n = math.hypot(vx, vy) or 1.0
        rx, ry = -vy / n * 1100, vx / n * 1100
        h = 1100
        a = (cx - rx, cy - ry, cz - h, -1, -1, 2)
        b = (cx + rx, cy + ry, cz - h, 1, -1, 2)
        c = (cx - rx, cy - ry, cz + h, -1, 1, 2)
        d = (cx + rx, cy + ry, cz + h, 1, 1, 2)
        for v in (a, b, c, b, d, c):
            out.extend(v)
        return out
