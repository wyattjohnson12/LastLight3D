"""
ao3d.py - ambient occlusion (soft shade where things meet) and low ground mist for the 3D view. Mixed into
the game window.

Ambient occlusion: in a corner, at the foot of a wall, under a tree or round a creature's feet, less of the
sky's light gets in, so real places are a little darker there. Without it everything looks pasted on top of
the ground. This is the usual screen-space trick, kept cheap and soft:
  1. Half size: for each pixel, find where it is in the world from the depth buffer of post3d.py's offscreen
     picture (the inverse camera matrix, lighting3d.LightState.inv) and which way its surface faces (from
     the neighbouring pixels). Then look at 10 spots on a little spiral round it on screen, covering about
     RADIUS world pixels: every spot that sits above the surface (in the half-space it faces) and close by
     shades it a bit. Spots far in front (a tree trunk much nearer the camera) don't count, so nothing gets
     a dark halo.
  2. Blur it across and down (half size), but only between pixels at about the same distance, so the shade
     stays in its corner and doesn't bleed over edges.
  3. Multiply it into the picture - right after the solid world is drawn, before the smoke, rain, glows,
     bloom and colour grade (post3d.py), so it never darkens the sky, fire or glowing things.
  Where nothing was drawn into the depth buffer the sky is (first person), except on flat layers (the cave,
  old flat worlds), where the ground doesn't write depth: there the ground is put back as the plane z = 0.

Ground mist: on foggy days (and a little in the rain) the same pass lays a thin, slowly drifting mist in the
low ground: a few steps along each view ray through a layer that thins out with height, patchy with noise.
It is mixed in with the ambient light's colour, so at night it is dark mist, not a glowing sheet.

Only with "Glow effects" on (it needs post3d's offscreen picture and its depth). Its own option:
"Ambient occlusion" in Screen & graphics (config "ambient_occlusion", default on); the mist comes with the
weather either way. Cost: one half-size pass of ~10 depth taps, two small blur passes, one full-size multiply.
If anything here fails on an odd driver it prints once and switches itself off.
"""
from arcade.gl.geometry import quad_2d_fs

RADIUS = 46.0            # world px the shade reaches (a survivor is ~40 tall)
STRENGTH = 3.2           # how dark a deep corner gets (subtle: stylised, not gloomy)
TAPS = 10
MIST_HEIGHT = 46.0       # world px: the mist thins out above this

QUAD_VS = """
#version 330
in vec2 in_vert;
in vec2 in_uv;
out vec2 uv;
void main() { uv = in_uv; gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

# 1. half-size occlusion + mist. Out: r = light left (1 = open), g = distance / 1000 (for the blur), b = mist.
AO_FS = """
#version 330
uniform %SAMPLER% depth_tex;     // post3d's depth (multisampled with "Smooth edges": sample 0 is enough)
uniform ivec4 rect;              // this view in the picture (pixels)
uniform mat4 inv;                // inverse of projection * view
uniform vec3 eye;
uniform float pscale;            // pixels per world px, one unit in front of the camera
uniform float radius;
uniform float strength;
uniform int flat_ground;         // flat layer: the ground wrote no depth, it's the plane z = 0
uniform int ao_on;
uniform vec4 mist;               // amount, height, time, ground height
uniform vec2 wind;
in vec2 uv;
out vec4 f_color;
const int TAPS = %TAPS%;
float hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
vec3 world_at(vec2 vuv, float d) {
    vec4 w = inv * vec4(vuv * 2.0 - 1.0, d * 2.0 - 1.0, 1.0);
    return w.xyz / w.w;
}
// where on screen (0..1 across this view) -> where in the world. false = sky
bool pos_at(vec2 vuv, out vec3 p) {
    ivec2 px = clamp(rect.xy + ivec2(vuv * vec2(rect.zw)), rect.xy, rect.xy + rect.zw - 1);
    float d = texelFetch(depth_tex, px, 0).r;
    if (d < 0.99999) { p = world_at(vuv, d); return true; }
    vec3 dir = normalize(world_at(vuv, 0.5) - eye);     // (half way in: the far plane is too imprecise)
    p = eye + dir * 9000.0;
    if (flat_ground == 0 || dir.z >= -1e-4) return false;
    float t = -eye.z / dir.z;
    if (t > 9000.0) return false;
    p = eye + dir * t;
    return true;
}
float mist_along(vec3 p) {
    if (mist.x <= 0.0) return 0.0;
    vec3 d = p - eye;
    float len = length(d);
    if (len > 2200.0) { d *= 2200.0 / len; len = 2200.0; p = eye + d; }
    // the mist's density falls off with height above mist.w: exp(-h / mist.y). Its sum along the ray, exactly:
    float h0 = max(eye.z - mist.w, 0.0), h1 = max(p.z - mist.w, 0.0);
    float e0 = exp(-h0 / mist.y), e1 = exp(-h1 / mist.y);
    float dz = h1 - h0;
    float sum = abs(dz) < 0.5 ? len * e0 : len * mist.y * (e0 - e1) / dz;
    // ...in drifting patches (read where the ray meets the ground: that's where the mist is)
    vec2 w = p.xy / 300.0 + wind * mist.z;
    float pk = smoothstep(0.15, 0.75, vnoise(w) * 0.65 + vnoise(w * 2.7 + 5.0) * 0.35) * 1.3 + 0.15;
    return clamp(1.0 - exp(-sum * mist.x * pk * 0.0022), 0.0, 0.7);
}
void main() {
    vec3 p;
    if (!pos_at(uv, p)) {
        f_color = vec4(1.0, 60.0, mist_along(p), 1.0);
        return;
    }
    float dist = length(p - eye);
    float m = mist_along(p);
    if (ao_on == 0) { f_color = vec4(1.0, dist / 1000.0, m, 1.0); return; }
    // the surface's facing from the nearer neighbour on each side (no smearing across edges)
    vec2 du = vec2(2.0 / float(rect.z), 0.0), dv = vec2(0.0, 2.0 / float(rect.w));
    vec3 a, b;
    bool ha = pos_at(uv + du, a), hb = pos_at(uv - du, b);
    vec3 dx = (ha && (!hb || dot(a - p, a - p) < dot(b - p, b - p))) ? a - p : (hb ? p - b : vec3(1.0, 0.0, 0.0));
    ha = pos_at(uv + dv, a); hb = pos_at(uv - dv, b);
    vec3 dy = (ha && (!hb || dot(a - p, a - p) < dot(b - p, b - p))) ? a - p : (hb ? p - b : vec3(0.0, 1.0, 0.0));
    vec3 n = normalize(cross(dx, dy));
    if (dot(n, eye - p) < 0.0) n = -n;
    float rpx = clamp(radius * pscale / dist, 3.0, 90.0);     // the radius on screen (full-size pixels)
    float spin = hash(floor(gl_FragCoord.xy)) * 6.2832;
    float occ = 0.0;
    float r2 = radius * radius;
    for (int i = 0; i < TAPS; i++) {
        float f = (float(i) + 0.5) / float(TAPS);
        float ang = spin + float(i) * 2.39996;               // golden-angle spiral
        vec2 o = vec2(cos(ang), sin(ang)) * rpx * sqrt(f);
        vec3 s;
        if (!pos_at(uv + o / vec2(rect.zw), s)) continue;
        vec3 v = s - p;
        float vv = dot(v, v);
        float fall = max(0.0, 1.0 - vv / (r2 * 1.4));             // nothing far away counts (no halos)
        occ += max(0.0, dot(n, v) * inversesqrt(vv + 1e-3) - 0.12) * fall;
    }
    float ao = clamp(1.0 - strength * occ / float(TAPS), 0.25, 1.0);
    f_color = vec4(ao, dist / 1000.0, m, 1.0);
}
"""

# 2. bilateral blur, one direction: neighbours at about the same distance only.
BLUR_FS = """
#version 330
uniform sampler2D src;
uniform vec2 step;
in vec2 uv;
out vec4 f_color;
void main() {
    vec4 c = texture(src, uv);
    vec3 acc = vec3(c.r, 0.0, c.b);
    float wsum = 1.0;
    for (int i = -3; i <= 3; i++) {
        if (i == 0) continue;
        vec4 s = texture(src, uv + step * float(i));
        float w = exp(-float(i * i) / 8.0) * (1.0 - smoothstep(0.0, 0.05 * c.g + 0.01, abs(s.g - c.g)));
        acc.xz += vec2(s.r, s.b) * w;
        wsum += w;
    }
    f_color = vec4(acc.x / wsum, c.g, acc.z / wsum, 1.0);
}
"""

# 3. into the picture: blend (ONE, SRC_ALPHA) -> picture * ao * (1 - mist) + mist colour * mist
COMP_FS = """
#version 330
uniform sampler2D ao_tex;
uniform vec3 mist_col;
in vec2 uv;
out vec4 f_color;
void main() {
    vec4 a = texture(ao_tex, uv);
    f_color = vec4(mist_col * a.b, a.r * (1.0 - a.b));
}
"""


def _allow_ms_samplers():
    """arcade's uniform table doesn't know multisampled samplers; they're set like any other sampler."""
    try:
        from arcade.gl.backends.opengl.uniform import Uniform
        from pyglet import gl
        table = Uniform._uniform_setters
        table.setdefault(gl.GL_SAMPLER_2D_MULTISAMPLE, table[gl.GL_SAMPLER_2D])
    except Exception as e:      # noqa: BLE001 - another arcade version: AO then only works without MSAA
        print("ao3d: can't register multisample samplers:", e)


_allow_ms_samplers()


class AO3D:
    """Mixed into the game window (needs post3d.Post3D's offscreen picture and View3D's lighting state)."""

    _ao_broken = False

    def ao_wanted(self):
        """Ambient occlusion on? (config "ambient_occlusion", default on; needs Glow effects)."""
        return bool((getattr(self, "cfg", {}) or {}).get("ambient_occlusion", True)) and not self._ao_broken

    def toggle_ao(self):
        self.cfg["ambient_occlusion"] = not self.ao_wanted()
        self._ao_broken = False
        self.save_cfg()

    def _ao_fail(self, e):
        print("Ambient occlusion switched off - this graphics card didn't like it:", e)
        self._ao_broken = True

    def _ao_mist(self, vl):
        """How much ground mist (0..1): foggy weather, and a little in the rain, on the surface only."""
        if vl != "over":
            return 0.0
        kind, k = getattr(self, "weather_shown", "clear"), getattr(self, "weather_k", 0.0)
        return k * {"fog": 1.0, "rain": 0.3, "storm": 0.4}.get(kind, 0.0)

    # ------------------------------------------------------------------ GPU bits
    def _ao_prog(self, ms):
        progs = self.__dict__.setdefault("_ao_progs", {})
        key = "ao_ms" if ms else "ao"
        if key not in progs:
            ctx = self.ctx
            fs = AO_FS.replace("%SAMPLER%", "sampler2DMS" if ms else "sampler2D").replace("%TAPS%", str(TAPS))
            progs[key] = ctx.program(vertex_shader=QUAD_VS, fragment_shader=fs)
            progs[key]["depth_tex"] = 0
            if "blur" not in progs:
                progs["blur"] = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BLUR_FS)
                progs["comp"] = ctx.program(vertex_shader=QUAD_VS, fragment_shader=COMP_FS)
                self._ao_quad = quad_2d_fs()
                self._ao_targets = {}
        return progs[key]

    def _ao_target(self, w, h):
        t = self._ao_targets.get((w, h))
        if t is None:
            ctx = self.ctx
            t = []
            for _ in range(2):
                tex = ctx.texture((max(1, w // 2), max(1, h // 2)), components=4, dtype="f2",
                                  filter=(ctx.LINEAR, ctx.LINEAR), wrap_x=ctx.CLAMP_TO_EDGE, wrap_y=ctx.CLAMP_TO_EDGE)
                t.append((ctx.framebuffer(color_attachments=[tex]), tex))
            self._ao_targets = {(w, h): t}      # (one size at a time: split-screen views are all the same)
        return t

    # ------------------------------------------------------------------ the hook (view3d.py)
    def ao_apply(self, vl):
        """After the solid world is drawn (before smoke, rain and glows): shade the corners, lay the mist.
        Leaves the 3D camera on."""
        if not getattr(self, "_post_active", False) or self._ao_broken:
            return
        ao_on = self.ao_wanted()
        mist = self._ao_mist(vl)
        if not ao_on and mist <= 0.01:
            return
        try:
            self._ao_run(vl, ao_on, mist)
        except Exception as e:          # noqa: BLE001 - never let a graphics extra stop the game
            self._ao_fail(e)
        self.use_world3d()

    def _ao_run(self, vl, ao_on, mist):
        ctx = self.ctx
        main = self._post_main
        dep = main.depth_attachment
        ms = getattr(dep, "samples", 0) > 0
        if not ms and dep.compare_func is not None:
            dep.compare_func = None         # read it as plain depth values (it's not a shadow map)
        prog = self._ao_prog(ms)
        x, y, w, h = self._post_rect_px
        st = self._lt
        prog["rect"] = (x, y, w, h)
        prog["inv"] = st.inv
        prog["eye"] = st.eye
        prog["pscale"] = self.projection[5] * h / 2
        prog["radius"] = RADIUS
        prog["strength"] = STRENGTH
        prog["flat_ground"] = int(self.hill_grid(vl) is None)
        prog["ao_on"] = int(ao_on)
        t = getattr(self, "flame_t", 0.0) % 1000.0
        vx, vy = self.view_pos()
        prog["mist"] = (mist, MIST_HEIGHT, t, self.ground_z(vx, vy) - 10.0)
        prog["wind"] = (0.035, 0.012)
        (fa, ta), (fb, tb) = self._ao_target(w, h)
        blend = ctx.is_enabled(ctx.BLEND)
        depth = ctx.is_enabled(ctx.DEPTH_TEST)
        ctx.disable(ctx.BLEND, ctx.DEPTH_TEST)
        try:
            dep.use(0)
            with fa.activate():
                fa.viewport = (0, 0, ta.width, ta.height)
                self._ao_quad.render(prog)
            blur = self._ao_progs["blur"]
            for src, dst, step in ((ta, fb, (1.0 / ta.width, 0.0)), (tb, fa, (0.0, 1.0 / ta.height))):
                src.use(0)
                blur["step"] = step
                with dst.activate():
                    dst.viewport = (0, 0, ta.width, ta.height)
                    self._ao_quad.render(blur)
            # into the picture, this view only
            self.camera.use()
            comp = self._ao_progs["comp"]
            amb = st.amb if vl == "over" else (0.0, 0.0, 0.0)
            comp["mist_col"] = tuple(min(1.0, a * 1.05) * c for a, c in zip(amb, st.fog))     # the fog's colour, lit
            comp["ao_tex"] = 0
            ta.use(0)
            ctx.enable(ctx.BLEND)
            ctx.blend_func = (ctx.ONE, ctx.SRC_ALPHA)
            self._ao_quad.render(comp)
        finally:
            ctx.blend_func = ctx.BLEND_DEFAULT
            if not blend:
                ctx.disable(ctx.BLEND)
            if depth:
                ctx.enable(ctx.DEPTH_TEST)
