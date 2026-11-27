"""
terrain3d.py - the hills in the 3D view (hills.py has the heights; this file puts them on the GPU).

How everything ends up standing on the hills without touching every sprite list:
  * The surface's total height grid (hills.render_grid) is uploaded ONCE per world as a small float texture
    (93 x 93 for the big map, 64 px cells, linear filtering = the same bilinear lookup hills.ground_z does).
  * GLSL below adds ground_z(xy) to every shader that draws the world: inject() puts it into a shader and
    lifts the shader's `mvp` by the ground height under the sprite, so cut-outs, 3D shapes (shapes3d),
    particles and light pools (fx3d) all stand on the ground with one texture fetch each. view3d.py's flat
    shader lifts each corner of things lying on the ground (tufts, ponds, shadows) so they hug the slope.
  * The ground tiles themselves become a heightfield: GROUND_GEO splits each 256 px tile into 4 x 4 quads on
    the height grid (so tiles meet exactly), with per-vertex normals from the height texture for soft
    shading, the tile's own texture / biome tint, and off-screen tiles culled in the shader. Nothing is
    built on the CPU per frame.
  * hill_on = 0 (old worlds, the cave, any underground layer) makes every lookup return 0: exactly flat.
"""
from array import array

import hills

GLSL = """
uniform sampler2D hill_tex;
uniform int hill_on;
uniform vec3 hill_map;      // grid origin, 1 / cell size, 1 / grid points
float ground_z(vec2 p) {
    if (hill_on == 0) return 0.0;
    vec2 uv = ((p - vec2(hill_map.x)) * hill_map.y + 0.5) * hill_map.z;
    return textureLod(hill_tex, uv, 0.0).r;
}
// lowest ground under a footprint of radius r: wide things on a slope sink in instead of floating
float ground_foot(vec2 p, float r) {
    float z = ground_z(p);
    if (hill_on == 0 || r <= 0.0) return z;
    z = min(z, ground_z(p + vec2(r, 0.0)));
    z = min(z, ground_z(p - vec2(r, 0.0)));
    z = min(z, ground_z(p + vec2(0.0, r)));
    return min(z, ground_z(p - vec2(0.0, r)));
}
mat4 hill_lift(float z) {
    return mat4(1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, z, 1.0);
}
"""

MVP_LINE = "mat4 mvp = window.projection * window.view;"


def inject(src, foot=None):
    """Add the ground lookup to a shader source. With `foot` (a GLSL expression, "0.0" = just the centre),
    also lift the shader's `mvp` by the ground under `c.xy` (c = the sprite's position)."""
    if "float ground_z(" not in src:
        at = src.index("\n", src.index("uniform WindowBlock")) + 1
        src = src[:at] + GLSL + src[at:]
    if foot is not None:
        if MVP_LINE not in src:
            print("terrain3d: no mvp line to lift in a shader - its objects won't follow the hills")
        src = src.replace(MVP_LINE, "mat4 mvp = window.projection * window.view * hill_lift(ground_foot(c.xy, "
                          + foot + "));")
    return src


MODEL_LINE = "w.z *= up_k;"


def inject_models(src):
    """models3d.py's instanced creature vertex shader: stand each instance on the ground under it."""
    src = inject(src)
    if MODEL_LINE not in src:
        print("terrain3d: models3d's vertex shader changed - creature models won't follow the hills")
    return src.replace(MODEL_LINE, "w.z = w.z * up_k + ground_z(i_a.xy);")


# The ground tiles as a heightfield (sprite list geometry shader: one point per tile in).
GROUND_GEO = """
#version 330
layout (points) in;
layout (triangle_strip, max_vertices = 40) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform sampler2D sprite_texture;
uniform sampler2D uv_texture;
uniform float uv_offset_bias;
uniform vec2 sun;           // shadow direction (light comes from the other side)
uniform float hill_max;     // highest ground (for culling)
in float v_angle[];
in vec4 v_color[];
in vec2 v_size[];
in float v_texture[];
out vec2 gs_uv;
out vec4 gs_color;
%LIB%
const int Q = 4;            // quads per side (256 px tile / 64 px grid)
void main() {
    vec3 c = gl_in[0].gl_Position.xyz;
    vec2 hs = v_size[0] / 2.0;
    mat4 mvp = window.projection * window.view;
    // cull the tile against the view (a sphere round the tile's box from the ground up to hill_max)
    float rb = length(vec3(hs, hill_max * 0.5)) + 2.0;
    vec4 q = mvp * vec4(c.xy, ground_z(c.xy) * 0.5 + hill_max * 0.25, 1.0);
    float bx = rb * sqrt(window.projection[0][0] * window.projection[0][0] + 1.0);
    float by = rb * sqrt(window.projection[1][1] * window.projection[1][1] + 1.0);
    if (q.w < -rb || q.x - bx > q.w || q.x + bx < -q.w || q.y - by > q.w || q.y + by < -q.w) return;
    vec2 uv0, uv1, uv2, uv3;
    getSpriteUVs(uv_texture, int(v_texture[0]), uv0, uv1, uv2, uv3);
    vec2 hp = 0.5 / vec2(textureSize(sprite_texture, 0)) * uv_offset_bias;
    uv0 += hp; uv1 += vec2(-hp.x, hp.y); uv2 += vec2(hp.x, -hp.y); uv3 += -hp;
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    vec3 L = normalize(vec3(-sun.x, -sun.y, 1.4));
    for (int r = 0; r < Q; r++) {
        for (int i = 0; i <= Q; i++) {
            for (int k = 1; k >= 0; k--) {
                vec2 st = vec2(float(i), float(r + k)) / float(Q);
                vec2 p = c.xy + rot * ((st * 2.0 - 1.0) * hs);
                vec3 hg = textureLod(hill_tex, ((p - vec2(hill_map.x)) * hill_map.y + 0.5) * hill_map.z, 0.0).rgb;
                float z = hg.r;
                vec3 n = normalize(vec3(-hg.g, -hg.b, 1.0));     // slope baked into the texture
                float shade = clamp(1.0 + 1.15 * (dot(n, L) - L.z), 0.55, 1.2);
                gs_color = vec4(v_color[0].rgb * shade, v_color[0].a);
                gs_uv = mix(mix(uv2, uv3, st.x), mix(uv0, uv1, st.x), st.y);
                gl_Position = mvp * vec4(p, z, 1.0);
                EmitVertex();
            }
        }
        EndPrimitive();
    }
}
"""


def _height_slope(g):
    """(height, dh/dx, dh/dy) per grid point - the ground shader's normals need one fetch, not five."""
    n, v = g.n, g.v
    out = array("f", bytes(12 * n * n))
    for j in range(n):
        for i in range(n):
            k = j * n + i
            i0, i1 = max(0, i - 1), min(n - 1, i + 1)
            j0, j1 = max(0, j - 1), min(n - 1, j + 1)
            out[3 * k] = v[k]
            out[3 * k + 1] = (v[j * n + i1] - v[j * n + i0]) / ((i1 - i0) * hills.CELL)
            out[3 * k + 2] = (v[j1 * n + i] - v[j0 * n + i]) / ((j1 - j0) * hills.CELL)
    return out


class Terrain3D:
    """Mixed into View3D: the height texture + the heightfield ground program."""

    def _hill_init(self, vs, lib, fs):
        ctx = self.ctx
        p = self._hill_prog = ctx.program(vertex_shader=vs, geometry_shader=GROUND_GEO.replace("%LIB%", lib),
                                          fragment_shader=fs)
        p["sprite_texture"] = 0
        p["uv_texture"] = 1
        p["mode"] = 0
        p["alpha_cut"] = -1.0
        p["shade"] = 1.0
        self._hill_key = None
        self._hill_tex = None
        self._hill_grid = None

    def _m3_init(self):
        """models3d.CreatureModels._m3_init with its vertex shader lifted onto the hills (no edit to models3d.py:
        it reads the module's VS when it builds the program)."""
        if getattr(self, "_m3_prog", None):
            return
        import models3d
        vs = models3d.VS
        models3d.VS = inject_models(vs)
        try:
            super()._m3_init()
        finally:
            models3d.VS = vs
        self.hill_apply(self._m3_prog)

    def _hill_programs(self):
        progs = [self._hill_prog] + list(self._progs3d[:2]) + list(getattr(self, "_mesh_progs", {}).values())
        for name in ("_m3_prog", "_fx_progs"):
            p = getattr(self, name, None)
            if p is not None:
                progs.append(p[0] if isinstance(p, tuple) else p)
        return progs

    def hill_grid(self, layer=None):
        """The total height grid for drawing `layer` (default: the layer being viewed), or None if it's flat."""
        if (layer or getattr(self, "view_layer", "over")) != "over":
            return None
        return hills.render_grid(self)

    def ground_z(self, x, y, layer=None):
        """Height of the drawn ground at (x, y) - matches the 3D ground mesh (0 off the surface / old worlds)."""
        g = self.hill_grid(layer)
        return g.at(x, y) if g is not None else 0.0

    def hill_bind(self, vl, progs=None):
        """Before drawing layer `vl`: bind the height texture (unit 2) and switch the lookup on/off in every
        world shader. Returns True if the ground has hills."""
        if progs is None:
            progs = self._hill_programs()
        g = self.hill_grid(vl)
        if g is not None and self._hill_key is not g:
            self._hill_key = g
            ctx = self.ctx
            if self._hill_tex is not None:
                self._hill_tex.delete()
            self._hill_tex = ctx.texture((g.n, g.n), components=3, dtype="f4", data=_height_slope(g),
                                         filter=(ctx.LINEAR, ctx.LINEAR), wrap_x=ctx.CLAMP_TO_EDGE,
                                         wrap_y=ctx.CLAMP_TO_EDGE)
            self._hill_grid = g
        on = g is not None
        if on:
            self._hill_tex.use(2)
        m = (hills.ORIGIN, 1.0 / hills.CELL, 1.0 / g.n) if on else (0.0, 1.0, 1.0)
        self._hill_uni = (int(on), m)
        for p in progs:
            self.hill_apply(p)
        if on:
            self._hill_prog["hill_max"] = float(g.hmax)
        return on

    def hill_apply(self, p):
        """Give one program the current hill settings (for programs made in the middle of a frame)."""
        on, m = getattr(self, "_hill_uni", (0, (0.0, 1.0, 1.0)))
        try:
            p["hill_tex"] = 2
            p["hill_on"] = on
            p["hill_map"] = m
        except KeyError:
            pass

    def draw_hill_ground(self, lst, sun):
        """The ground tiles of the surface as the heightfield (depth test on: hills hide what's behind)."""
        if not len(lst):
            return
        p = self._hill_prog
        p["sun"] = sun
        lst._init_deferred()
        old = lst.data.program
        lst.data.program = p
        try:
            lst.draw()
        finally:
            lst.data.program = old
