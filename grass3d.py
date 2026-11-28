"""
grass3d.py - a field of real 3D grass blades around the camera (mixed into View3D).

How it stays cheap:
  * One small buffer of N x N points, made once: point (i, j) is "grid cell (i, j) counted from the
    corner of the field". Every frame the field's centre moves with the camera and the geometry shader
    turns each point into the WORLD cell it lands on, so a blade's place, size, colour and lean all come
    from a hash of its world cell: the grass never jumps and nothing is rebuilt on the CPU.
  * The geometry shader drops a tuft that is off screen, too far away (the field thins out towards its
    edge), or not on grassy ground. Where grass grows comes from ground3d.py's ground map: the biome
    (meadow tall and lush, forest, the Mire's darker sedge, sparse dry tufts in the Highlands, none on
    snow or ash), the same dirt patches the ground shader paints, steep slopes (bare rock), reeds near
    water, and the grass mask (none on water, roads, bridges, ponds, worn ground or under buildings).
  * Each tuft is 2-3 blades of 3 triangles. They stand on the hills (terrain3d.ground_z), sway in gusts
    that roll across the field, and bend away from survivors and creatures walking through them (the
    nearest few are passed in as uniforms).
  * They're drawn in the "ground" stage (lighting3d.py) with the ground, so the time of day, the light
    pools of fires at night and the sun's shadows light them exactly like the ground under them.

Option "grass" in lastlight_config.json (Screen & graphics): "high" (default), "low" (a smaller, thinner
field) or "off" (no grass, and the ground shader skips its finest detail too - ground3d.py g_detail).
"""
import math
import time
from array import array

from arcade.gl import BufferDescription

import ground3d
import lighting3d
import terrain3d

MODES = ("high", "low", "off")
# per setting: grid points per side, cell size (px), field radius (px), blades per tuft
LEVELS = {"high": (136, 11.0, 740.0, 3), "low": (84, 14.0, 560.0, 2)}
MAX_PUSH = 8

VS = """
#version 330
in vec2 in_idx;
out vec2 v_idx;
void main() { v_idx = in_idx; gl_Position = vec4(0.0, 0.0, 0.0, 1.0); }
"""

GS = """
#version 330
layout (points) in;
layout (triangle_strip, max_vertices = 15) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
%NOISE%
%MAP%
uniform vec2 g_centre;      // middle of the field
uniform float g_cell;       // px between tufts
uniform float g_n;          // points per side
uniform float g_radius;     // the field fades out towards this distance from the centre
uniform float g_time;
uniform vec3 g_wind;        // direction x, y ; strength
uniform vec4 g_push[%PUSH%];    // walkers: x, y, reach, 0
uniform int g_npush;
uniform int g_blades;
uniform float g_autumn;
uniform float g_winter;
in vec2 v_idx[];
out vec3 b_pos;
out vec3 b_col;
out float b_up;
void main() {
    vec2 w = floor(g_centre / g_cell) + v_idx[0] - floor(g_n * 0.5);     // this point's world cell
    vec2 h = gh2(w * 1.37 + 0.5);
    vec2 root = (w + 0.15 + 0.7 * h) * g_cell;
    float d = length(root - g_centre);
    float fade = 1.0 - smoothstep(g_radius * 0.5, g_radius, d);
    if (fade <= 0.0) return;
    float roll = gh(w + 91.7);
    if (roll > fade) return;
    // ---- does grass grow here? (the same patches the ground shader paints - ground3d.py)
    vec4 ba, bb;
    float n2 = gfbm(root / 150.0 + 11.0);
    gm_biomes(root + (vec2(n2, gnoise(root / 150.0 + 4.0)) - 0.5) * 90.0, ba, bb);
    float forest = ba.x, meadow = ba.y, mire = bb.x, high = bb.y, water = bb.w;
    float green = forest + meadow + mire + high;
    if (green < 0.05) return;
    float amount = forest * (0.5 + 0.5 * smoothstep(0.3, 0.6, n2)) + meadow + mire * 0.6
                 + high * 0.4 * smoothstep(0.42, 0.62, n2);
    float dirt_amt = forest * 0.8 + meadow * 0.45 + mire + high * 0.9;
    float dn = gfbm(root / 120.0 + 31.0);
    amount *= 1.0 - smoothstep(0.6, 0.67, dn) * min(dirt_amt, 1.0);
    if (hill_on == 1) {     // steep slopes are bare soil and rock
        vec3 hg = textureLod(hill_tex, ((root - vec2(hill_map.x)) * hill_map.y + 0.5) * hill_map.z, 0.0).rgb;
        amount *= 1.0 - smoothstep(0.36, 0.6, length(hg.gb));
    }
    amount *= gm_grass_mask(root);
    if (roll > amount * fade) return;
    float z0 = ground_z(root);
    mat4 mvp = window.projection * window.view;
    vec4 cq = mvp * vec4(root, z0 + 8.0, 1.0);
    float m = 30.0 * window.projection[0][0];
    if (cq.w < 1.0 || abs(cq.x) > cq.w + m || abs(cq.y) > cq.w + m) return;

    // ---- size and colour (matching the ground's big lush / dry patches)
    float n1 = gfbm(root / 520.0 + 3.0);
    float reed = smoothstep(0.7, 0.95, water) * (1.0 - high) * smoothstep(0.3, 0.55, gnoise(root / 70.0));
    float tall = (forest * 1.0 + meadow * 1.3 + mire * 1.45 + high * 0.75) / green;
    tall *= 1.0 + 1.0 * reed;
    float H = (8.0 + 10.0 * gh(w + 3.3)) * tall * (0.75 + 0.25 * min(amount, 1.0)) * (1.0 - 0.35 * g_winter)
            * (0.5 + 0.5 * fade);
    vec3 c = (forest * vec3(0.27, 0.45, 0.16) + meadow * vec3(0.43, 0.6, 0.22) + mire * vec3(0.31, 0.38, 0.16)
            + high * vec3(0.5, 0.48, 0.28)) / green;
    float dry = smoothstep(0.5, 0.78, n1 + 0.18 * g_autumn) * (0.55 + 0.35 * g_autumn);
    c *= mix(vec3(1.0), vec3(1.12, 1.02, 0.66), dry) * mix(vec3(1.0), vec3(0.82, 1.0, 0.78), smoothstep(0.45, 0.2, n1));
    c = mix(c, vec3(0.36, 0.44, 0.2), reed * 0.7);
    c = mix(c, vec3(0.6, 0.5, 0.26), 0.3 * g_autumn);
    c = mix(c, vec3(0.55, 0.53, 0.44), 0.4 * g_winter);
    c *= 0.85 + 0.3 * gh(w + 5.1);

    // ---- wind: gusts rolling across the field, plus a little flutter
    vec2 wd = g_wind.xy;
    float wave = 0.5 + 0.5 * sin(dot(root, wd) * 0.011 - g_time * 2.1 + gnoise(root / 300.0) * 4.0);
    vec2 bend = wd * g_wind.z * (0.2 + 0.9 * wave * wave)
              + vec2(sin(g_time * 3.1 + roll * 30.0), cos(g_time * 2.7 + roll * 17.0)) * 0.05 * g_wind.z;
    // ---- walkers push it aside and flatten it
    float flat_k = 0.0;
    for (int i = 0; i < g_npush; i++) {
        vec2 v = root - g_push[i].xy;
        float dd = length(v);
        float f = 1.0 - smoothstep(g_push[i].z * 0.35, g_push[i].z, dd);
        if (f <= 0.0) continue;
        bend += (dd > 0.01 ? v / dd : vec2(1.0, 0.0)) * f * 1.1;
        flat_k = max(flat_k, f);
    }
    for (int b = 0; b < g_blades; b++) {
        vec2 hb = gh2(w * 3.1 + float(b) * 7.7);
        float a = hb.x * 6.2831;
        vec2 side = vec2(cos(a), sin(a));
        vec2 r0 = root + (hb - 0.5) * g_cell * 0.45;
        float hh = H * (0.65 + 0.5 * hb.y) * (1.0 - 0.45 * flat_k);
        vec2 lean = vec2(-side.y, side.x) * (hb.y - 0.5) * 0.7 + bend;
        float ll = length(lean);
        if (ll > 1.15) lean *= 1.15 / ll;
        float wid = (1.2 + 1.0 * hb.x) * (1.0 + 0.4 * reed);
        float drop = 1.0 - 0.38 * dot(lean, lean);
        b_col = c * (0.92 + 0.16 * hb.y);
        for (int k = 0; k < 3; k++) {
            float t = float(k) * 0.5;
            vec3 P = vec3(r0 + lean * hh * t * t, z0 + hh * t * drop);
            b_up = t;
            if (k < 2) {
                vec2 s = side * wid * (1.0 - t * 0.6) * 0.5;
                b_pos = P - vec3(s, 0.0); gl_Position = mvp * vec4(b_pos, 1.0); EmitVertex();
                b_pos = P + vec3(s, 0.0); gl_Position = mvp * vec4(b_pos, 1.0); EmitVertex();
            } else {
                b_pos = P; gl_Position = mvp * vec4(b_pos, 1.0); EmitVertex();
            }
        }
        EndPrimitive();
    }
}
"""

FS = """
#version 330
in vec3 b_pos;
in vec3 b_col;
in float b_up;
out vec4 f_color;
void main() {
    vec3 L = lt_sun.xyz;
    vec3 V = normalize(lt_eye.xyz - b_pos);
    vec3 col = b_col * (0.52 + 0.6 * b_up);                         // darker down in the tuft
    col += b_col * pow(max(dot(-V, L), 0.0), 3.0) * b_up * 0.4;     // the sun shining through the blades
    float sun = lt_sunlit(b_pos, vec3(0.0, 0.0, 1.0));
    col *= 1.0 - 0.3 * lt_wx.x;                                      // weather3d.py: darker when soaked...
    col = mix(col, vec3(0.88, 0.91, 0.96), lt_wx.y * 0.7 * b_up);    // ...and frosted white at the tips in snow
    col *= 1.0 + lt_wx.z * 0.8;                                      // a lightning flash
    vec3 rgb = col * lt_light(b_pos, vec3(0.0)) * sun;
    f_color = vec4(lt_fogged(rgb, b_pos), 1.0);
}
"""


class Grass3D:
    """Mixed into View3D."""

    _grass = None            # (mode, program, geometry, n)

    # ------------------------------------------------------------------ the option
    def grass_mode(self):
        """"high", "low" or "off" (config "grass")."""
        v = (getattr(self, "cfg", {}) or {}).get("grass", "high")
        if v is False:
            return "off"
        return v if v in MODES else "high"

    def toggle_grass(self):
        """Screen & graphics: High -> Low -> Off -> High."""
        nxt = {"high": "low", "low": "off", "off": "high"}[self.grass_mode()]
        self.cfg["grass"] = nxt
        self.save_cfg()

    # ------------------------------------------------------------------ GPU bits
    def _grass_init(self, mode):
        g = self._grass
        if g is not None and g[0] == mode:
            return g
        ctx = self.ctx
        if g is None or g[1] is None:
            gs = GS.replace("%NOISE%", ground3d.NOISE).replace("%MAP%", ground3d.MAP).replace("%PUSH%", str(MAX_PUSH))
            gs = terrain3d.inject(gs)
            prog = ctx.program(vertex_shader=VS, geometry_shader=gs, fragment_shader=lighting3d.inject(FS, frag=True))
            lighting3d.bind(prog)
        else:
            prog = g[1]
        n = LEVELS[mode][0]
        pts = array("f", [v for j in range(n) for i in range(n) for v in (float(i), float(j))])
        geo = ctx.geometry([BufferDescription(ctx.buffer(data=pts), "2f", ["in_idx"])], mode=ctx.POINTS)
        self._grass = (mode, prog, geo, n)
        self._grass_t0 = time.perf_counter()
        return self._grass

    def _grass_pushers(self, L, centre, reach):
        """The nearest few survivors / creatures (x, y, how far they push the grass, 0)."""
        cx, cy = centre
        got = []
        for p in self.players.values():
            if p.alive and p.layer == "over" and not p.in_hut:
                got.append((p.sprite.center_x, p.sprite.center_y, 30.0))
        for lst, r in ((L.animals, 24.0), (L.zombies, 30.0), (L.bosses, 70.0)):
            for s in lst:
                x, y = s.center_x, s.center_y
                if abs(x - cx) < reach and abs(y - cy) < reach:
                    got.append((x, y, r))
        if len(got) > MAX_PUSH:
            vx, vy = self.view_pos()
            got.sort(key=lambda e: (e[0] - vx) ** 2 + (e[1] - vy) ** 2)
            got = got[:MAX_PUSH]
        return got

    def grass_draw(self, L, vl, fp, hilly):
        """Draw the grass field (in the "ground" stage, after the ground and what lies on it). Leaves the
        depth state as the ground stage had it (hilly: test on, writes off; flat: test off)."""
        mode = self.grass_mode()
        if vl != "over" or mode == "off" or self._sh_pass or getattr(self, "_grass_broken", False):
            return
        gm = ground3d.ground_map(self)
        if gm is None:
            return
        try:
            _, prog, geo, n = self._grass_init(mode)
        except Exception as e:       # noqa: BLE001 - an old driver: carry on without grass
            print("grass3d: no grass:", e)
            self._grass_broken = True
            return
        _, cell, radius, blades = LEVELS[mode]
        (ex, ey, _), f, _, _, _, _, _ = self._basis()
        if fp:
            fl = math.hypot(f[0], f[1]) or 1.0
            centre = (ex + f[0] / fl * radius * 0.55, ey + f[1] / fl * radius * 0.55)
        else:
            centre = tuple(self.camera.position)
        gm.bind()
        ground3d.apply(prog, gm, True)
        self.hill_apply(prog)
        prog["g_centre"] = centre
        prog["g_cell"] = cell
        prog["g_n"] = float(n)
        prog["g_radius"] = radius
        prog["g_time"] = (time.perf_counter() - self._grass_t0) % 3600.0
        kind, k = getattr(self, "weather_shown", "clear"), getattr(self, "weather_k", 0.0)
        wind = 0.3 + (0.25 if kind == "rain" else 0.55 if kind == "storm" else 0.1 if kind == "snow" else 0.0) * k
        prog["g_wind"] = (0.91, 0.41, wind)
        push = self._grass_pushers(L, centre, radius)
        flat = []
        for i in range(MAX_PUSH):
            flat.extend(push[i] + (0.0,) if i < len(push) else (0.0, 0.0, 0.0, 0.0))
        prog["g_push"] = flat
        prog["g_npush"] = len(push)
        prog["g_blades"] = blades
        autumn, winter = ground3d.season_k(self)
        prog["g_autumn"] = autumn
        prog["g_winter"] = winter
        ctx = self.ctx
        ctx.enable(ctx.DEPTH_TEST)
        ctx.disable(ctx.BLEND)
        from pyglet import gl
        gl.glDepthFunc(gl.GL_LEQUAL)
        gl.glDepthMask(gl.GL_TRUE)
        try:
            geo.render(prog)
        finally:
            ctx.enable(ctx.BLEND)
            if hilly:
                gl.glDepthMask(gl.GL_FALSE)
            else:
                ctx.disable(ctx.DEPTH_TEST)
