"""
water3d.py - moving water in the 3D view: rivers, the lake (terrain_draw.py) and ponds (view3d.py).

What the water does, all on the GPU (time is a uniform, so nothing is rebuilt on the CPU per frame):
  * Ripples: two layers of smooth procedural noise, read as little slopes (a "normal"), drift over the
    surface. Rivers carry them downstream: each vertex knows which way and how fast its water flows. To
    stop the pattern stretching where the river bends, it is read twice, half a cycle apart, and faded
    from one copy to the other (the usual "flow map" trick), so it never drifts more than one cycle.
  * Looking straight down (the tilted camera) you see into the water: dark blue in the middle, lighter and
    greener in the shallows by the bank. At a low angle (first person) it turns into a mirror of the sky,
    using the same two colours firstperson.py paints the sky with.
  * The sun (fx3d.sun) glints off the ripples - bright little sparkles plus a soft sheen - fading out at
    dusk. The night light map (fx3d.fx_lighting) darkens the water afterwards like everything else.
  * A frothy edge laps at the banks, and fast or shallow stretches (fords) get faint foam streaks that
    run with the current.
  * Ponds are painted sprites (art.py): the pond shader keeps the painted sandy rim and lily pads exactly
    as they are, and only the blue water pixels get the ripples, sky and glints.
  * The Mire's bog pools (swamp.py) are part of the ground, so the ground shader draws them; draw_bog then
    goes over just their murky water pixels with the same ripples and glints (on the very same heightfield
    triangles as the ground, so they sit exactly on the hills).
  * Sun shadows (shadows3d.py) fall across all of it, like on the ground.

The colours stay close to the old flat blue so the water still belongs to the low-poly painted world.
Cost: one extra (tiny) program each for rivers and ponds; per water pixel a handful of noise lookups.
"""
import time
from array import array

from arcade.gl import BufferDescription
from pyglet import gl

import lighting3d
import terrain3d

# The surface sits this far above the ground under it. Lying ON the ground (not sunk into it) matters on
# hilly worlds, where the ground mesh is depth tested and would hide anything below it.
LIFT = 1.6
BANK_LIFT = 0.8

# ---------------------------------------------------------------- GLSL shared by rivers and ponds
WATER_LIB = """
uniform float time;        // seconds, wrapping every hour (a whole number of CYCLEs: no jump)
uniform vec3 eye;          // camera position in the world
uniform vec2 sun;          // fx3d.sun: shadow direction * length (the light comes from the other way)
uniform float daylight;    // 1 by day, 0 at night: glints fade out
const vec3 SKY_LOW = vec3(0.698, 0.816, 0.910);    // firstperson.fp_draw_sky's horizon...
const vec3 SKY_TOP = vec3(0.376, 0.588, 0.839);    // ...and top colour
const float CYCLE = 3.0;                            // seconds per flow cycle (see the module docstring)

float hash(vec2 p) {
    p = fract(p * vec2(0.1031, 0.1030));
    p += dot(p, p.yx + 33.33);
    return fract((p.x + p.y) * p.x);
}
// value noise with its slope: (value, d/dx, d/dy)
vec3 noised(vec2 x) {
    vec2 i = floor(x), f = fract(x);
    vec2 u = f * f * (3.0 - 2.0 * f), du = 6.0 * f * (1.0 - f);
    float a = hash(i), b = hash(i + vec2(1.0, 0.0)), c = hash(i + vec2(0.0, 1.0)), d = hash(i + vec2(1.0, 1.0));
    float k = a - b - c + d;
    return vec3(a + (b - a) * u.x + (c - a) * u.y + k * u.x * u.y, du * (vec2(b - a, c - a) + k * u.yx));
}
const mat2 TURN = mat2(0.8, 0.6, -0.6, 0.8);
// two layers of ripples - broad swells read at p0, finer, turned chop at p1 - as (lumpiness 0..1, slope)
vec3 ripples(vec2 p0, vec2 p1) {
    vec3 a = noised(p0 / 48.0);
    vec3 b = noised(TURN * p1 / 17.0 + 7.3);
    return vec3(a.x * 0.6 + b.x * 0.4, a.yz * (6.0 / 48.0) + transpose(TURN) * b.yz * (3.2 / 17.0));
}
// the ripples at world point p carried along by `flow` (px/s); two gentle breezes move still water too.
// blend says how far we are from the first copy to the second (for anything else that flows).
vec3 flowing(vec2 p, vec2 flow, out float blend) {
    float t0 = fract(time / CYCLE), t1 = fract(time / CYCLE + 0.5);
    vec2 m1 = (flow + vec2(7.0, 3.0)) * CYCLE, m2 = (flow * 1.3 + vec2(-4.0, 6.0)) * CYCLE;
    vec3 r0 = ripples(p - m1 * t0, p - m2 * t0 + 31.0);
    vec3 r1 = ripples(p - m1 * t1 + 57.0, p - m2 * t1 + 93.0);
    blend = abs(2.0 * t0 - 1.0);
    return mix(r0, r1, blend);
}
// sky reflection, sun light and glints on top of the water's own colour
vec3 water_light(vec3 body, vec3 wp, vec3 n) {
    vec3 v = normalize(eye - wp);
    vec3 L = normalize(vec3(-sun, 0.95));
    // ripples facing the sun are a touch lighter (a high, steady light: a low evening sun would turn the
    // gentle ripples into big blotches)
    vec3 Ld = normalize(vec3(-sun * 0.5, 1.0));
    vec3 col = body * clamp(1.0 + 1.5 * (dot(n, Ld) - Ld.z), 0.7, 1.3);
    vec3 r = reflect(-v, n);
    vec3 sky = mix(SKY_LOW, SKY_TOP, smoothstep(0.0, 0.7, r.z));
    float fres = 0.04 + 0.9 * pow(1.0 - clamp(dot(n, v), 0.0, 1.0), 4.0);
    col = mix(col, sky * mix(0.7, 1.0, daylight), fres);   // a dimmer mirror by night
    float s = max(dot(r, L), 0.0);
    // where calm water would mirror the sun itself there'd be a solid blaze of glints: make that a soft
    // sheen instead and keep the sparkles for the ripples tipped towards the sun
    float s_flat = max(dot(reflect(-v, vec3(0.0, 0.0, 1.0)), L), 0.0);
    float glint = smoothstep(0.982, 0.995, s) * (1.1 - 0.8 * smoothstep(0.93, 0.99, s_flat))
                + pow(s, 16.0) * 0.12 + pow(s_flat, 30.0) * 0.25;
    float high = mix(0.35, 1.0, smoothstep(0.5, 0.75, L.z));     // a low morning / evening sun glints less
    return col + glint * high * daylight * vec3(1.0, 0.96, 0.86);
}
"""

# ---------------------------------------------------------------- rivers and the lake
RIVER_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec2 in_flow;
in float in_shore;
in float in_depth;
out vec3 v_pos;
out vec2 v_flow;
out float v_shore;
out float v_depth;
void main() {
    gl_Position = window.projection * window.view * vec4(in_pos, 1.0);
    v_pos = in_pos;
    v_flow = in_flow;
    v_shore = in_shore;
    v_depth = in_depth;
}
"""

RIVER_FS = """
#version 330
in vec3 v_pos;
in vec2 v_flow;
in float v_shore;
in float v_depth;
out vec4 f_color;
%LIB%
const vec3 DEEP = vec3(0.10, 0.28, 0.41);
const vec3 SHALLOW = vec3(0.26, 0.50, 0.53);
const vec3 FOAM = vec3(0.84, 0.92, 0.93);
void main() {
    float blend;
    vec3 rp = flowing(v_pos.xy, v_flow, blend);
    float speed = length(v_flow);
    // calmer ripples in deep, slow water; choppier in fast shallows
    float chop = 0.75 + 0.5 * clamp(speed / 60.0, 0.0, 1.0) * (1.2 - v_depth);
    vec3 n = lt_rain_normal(normalize(vec3(-rp.yz * chop, 1.0)), v_pos.xy);     // + rain rings (weather3d.py)
    float deep = v_depth * smoothstep(0.0, 60.0, v_shore);
    vec3 body = mix(SHALLOW, DEEP, deep);
    vec3 col = water_light(body, v_pos, n);
    // froth lapping at the bank: a ragged band that breathes in and out
    float edge = 1.0 + 9.0 * smoothstep(0.35, 0.75, rp.x) + 2.0 * sin(time * 6.2832 / CYCLE + dot(v_pos.xy, vec2(0.05, 0.04)));
    float foam = (1.0 - smoothstep(edge - 3.0, edge, v_shore)) * 0.75;
    // streaks running with the current where the water is fast or shallow
    if (speed > 1.0) {
        vec2 d = v_flow / speed;
        float fast = clamp((speed - 30.0) / 40.0, 0.0, 1.0) + (1.0 - v_depth) * 0.8;
        if (fast > 0.02) {
            float t0 = fract(time / CYCLE), t1 = fract(time / CYCLE + 0.5);
            vec2 q = vec2(dot(v_pos.xy, d) / 70.0, dot(v_pos.xy, vec2(-d.y, d.x)) / 11.0);
            float s0 = noised(q - vec2(speed * t0 * CYCLE / 70.0, 0.0)).x;
            float s1 = noised(q - vec2(speed * t1 * CYCLE / 70.0, 0.0) + 17.0).x;
            foam = max(foam, smoothstep(0.66, 0.9, mix(s0, s1, blend)) * 0.55 * min(fast, 1.0));
        }
    }
    col = mix(col, FOAM, foam);
    col *= lt_sunlit(v_pos, vec3(0.0, 0.0, 1.0));         // shadows3d.py: trees' shadows across the river
    float a = mix(0.7, 0.93, deep);
    a = max(a, foam) * smoothstep(0.0, 2.5, v_shore);    // soft edge into the mud bank
    f_color = vec4(col, a);
}
"""

# ---------------------------------------------------------------- ponds (painted sprites lying flat)
# Same as view3d's flat sprite shader (corners on the ground, hills included) plus the world position.
POND_GEO_MAIN = """
out vec3 gs_world;
void main() {
    vec3 c = gl_in[0].gl_Position.xyz;
    vec2 hs = v_size[0] / 2.0;
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    mat4 mvp = window.projection * window.view;
    vec2 uv0, uv1, uv2, uv3;
    uvs(uv0, uv1, uv2, uv3);
    gs_color = v_color[0];
    float zc = c.z + (hill_on == 1 ? 1.5 : 0.0);
    vec2 p[4] = vec2[4](rot * vec2(-hs.x, hs.y) + c.xy, rot * vec2(-hs.x, -hs.y) + c.xy,
                        rot * vec2(hs.x, hs.y) + c.xy, rot * vec2(hs.x, -hs.y) + c.xy);
    vec2 uv[4] = vec2[4](uv0, uv2, uv1, uv3);
    for (int i = 0; i < 4; i++) {
        gs_world = vec3(p[i], zc + ground_z(p[i]));
        gl_Position = mvp * vec4(gs_world, 1.0);
        gs_uv = uv[i];
        EmitVertex();
    }
    EndPrimitive();
}
"""

POND_FS = """
#version 330
uniform sampler2D sprite_texture;
uniform vec4 spritelist_color;
uniform int murky;          // 1: a bog pool (draw_bog) - murky green water, and only its water pixels
in vec2 gs_uv;
in vec4 gs_color;
in vec3 gs_world;
out vec4 f_color;
%LIB%
// a bog pool's open water: dark and a touch bluer than it is red (the muddy rim is redder, the lily pads and
// green scum much greener)
float bog(vec3 c) {
    return smoothstep(0.0, 0.035, c.b - c.r) * (1.0 - smoothstep(0.12, 0.2, c.g - c.r))
         * (1.0 - smoothstep(0.35, 0.5, max(c.g, c.b)));
}
// how sure we are this painted pixel is open water: a strong, deep blue. Pale ice and snow (tundra ponds in
// winter), the sandy rim, lily pads and floating ice are much less blue for how bright they are, so they stay
// exactly as painted.
float wet(vec3 c) {
    float blue = c.b - c.r;
    return smoothstep(0.34, 0.46, blue / max(c.b, 0.05)) * smoothstep(0.06, 0.12, blue);
}
void main() {
    vec4 t = texture(sprite_texture, gs_uv);
    if (t.a <= 0.0) discard;
    float w = murky == 1 ? bog(t.rgb) : wet(t.rgb);
    if (murky == 1 && w <= 0.01) discard;      // the ground shader already drew everything else
    vec3 body = t.rgb;
    if (murky == 0 && w < 0.99 && t.b - t.r > 0.08) {
        // the painted ripple lines are pale blue: with water on both sides they're water too (and take the
        // colour of the water round them - our own ripples replace them)
        vec2 px = 3.0 / vec2(textureSize(sprite_texture, 0));
        vec3 n0 = texture(sprite_texture, gs_uv + vec2(0.0, px.y)).rgb, s0 = texture(sprite_texture, gs_uv - vec2(0.0, px.y)).rgb;
        vec3 e0 = texture(sprite_texture, gs_uv + vec2(px.x, 0.0)).rgb, w0 = texture(sprite_texture, gs_uv - vec2(px.x, 0.0)).rgb;
        float ns = min(wet(n0), wet(s0)), ew = min(wet(e0), wet(w0));
        if (max(ns, ew) > w) {
            w = max(ns, ew);
            body = ns >= ew ? (n0 + s0) * 0.5 : (e0 + w0) * 0.5;
        }
    }
    vec3 col = t.rgb;
    if (w > 0.0) {
        float blend;
        vec3 rp = flowing(gs_world.xy, vec2(0.0), blend);
        vec3 n = normalize(vec3(-rp.yz * (murky == 1 ? 0.5 : 0.8), 1.0));     // still, thick bog water
        n = lt_rain_normal(n, gs_world.xy);                                    // + rain rings (weather3d.py)
        // the painted water (with its shading) is the body colour, pulled a little deeper (bog water stays
        // its own murky green); the ripples, sky and sun do the rest
        vec3 deep = murky == 1 ? body : mix(body, vec3(0.10, 0.28, 0.41), 0.25);
        col = mix(col, water_light(deep, gs_world, n), w);
    }
    col *= lt_sunlit(gs_world, vec3(0.0, 0.0, 1.0));      // shadows3d.py
    f_color = vec4(col, t.a * (murky == 1 ? w : 1.0)) * gs_color * spritelist_color;
}
"""


# ---------------------------------------------------------------- building the river / lake mesh
def vert(out, x, y, z, flow=(0.0, 0.0), shore=0.0, depth=1.0):
    """Append one water vertex to `out`: ground height z (lifted by LIFT here), which way and how fast the water
    flows (px/s), how far it is to the nearest bank (px) and how deep it is (1 = a full river, less = a ford)."""
    out.extend((x, y, z + LIFT, flow[0], flow[1], shore, depth))


def geometry(game, data):
    """The GPU mesh for a list of water vertices (built once per world). None if there's no water."""
    if not data:
        return None
    buf = game.ctx.buffer(data=array("f", data))
    return game.ctx.geometry([BufferDescription(buf, "3f 2f 1f 1f", ["in_pos", "in_flow", "in_shore", "in_depth"])],
                             mode=game.ctx.TRIANGLES)


# ---------------------------------------------------------------- drawing
def _progs(game):
    """(river program, pond program, start time, bog pool program), made the first time they're needed."""
    got = getattr(game, "_water3d", None)
    if got is None:
        import view3d
        ctx = game.ctx
        river = ctx.program(vertex_shader=RIVER_VS,
                            fragment_shader=lighting3d.inject(RIVER_FS.replace("%LIB%", WATER_LIB), frag=True))
        game._init3d()
        geo = view3d._SPRITE_IN.replace("%LIB%", game._mesh_lib) + POND_GEO_MAIN
        pond_fs = lighting3d.inject(POND_FS.replace("%LIB%", WATER_LIB), frag=True)
        pond = ctx.program(vertex_shader=game._mesh_vs, geometry_shader=geo, fragment_shader=pond_fs)
        # bog pools: the ground's own heightfield geometry shader, passing the world position on
        bog_geo = (terrain3d.GROUND_GEO.replace("%LIB%", game._mesh_lib + lighting3d.glsl())
                   .replace("out vec4 gs_color;", "out vec4 gs_color;\nout vec3 gs_world;")
                   .replace("gl_Position = mvp * vec4(p, z, 1.0);",
                            "gs_world = vec3(p, z); gl_Position = mvp * vec4(p, z, 1.0);"))
        bog = ctx.program(vertex_shader=game._mesh_vs, geometry_shader=bog_geo, fragment_shader=pond_fs)
        for p in (pond, bog):
            p["sprite_texture"] = 0
            p["uv_texture"] = 1
        pond["murky"] = 0
        bog["murky"] = 1
        for p in (river, pond, bog):
            lighting3d.bind(p)
        got = game._water3d = (river, pond, time.perf_counter(), bog)
    return got


def _common(game, prog, t0):
    """Per-draw uniforms: time, camera, sun and how much daylight there is."""
    prog["time"] = (time.perf_counter() - t0) % 3600.0
    prog["eye"] = tuple(game._basis()[0])
    prog["sun"] = tuple(game._progs3d[1]["sun"])
    vl = getattr(game, "view_layer", "over")
    dk = game.darkness if vl == "over" else game.layer_dark(vl)
    prog["daylight"] = max(0.0, 1.0 - dk) ** 1.5


def draw(game, geo):
    """Draw a river / lake mesh made by geometry() (with the 3D camera on, blending enabled)."""
    if geo is None:
        return
    river, _, t0, _ = _progs(game)
    _common(game, river, t0)
    geo.render(river)


def draw_ponds(game, lst):
    """Draw the ponds (painted sprites lying on the ground) with moving water. Replaces game.flat(L.ponds)."""
    if not len(lst):
        return
    _, pond, t0, _ = _progs(game)
    _common(game, pond, t0)
    game.hill_apply(pond)          # HILLS (terrain3d.py): lie on the ground like the flat sprites do
    lst._init_deferred()
    old = lst.data.program
    lst.data.program = pond
    try:
        lst.draw()
    finally:
        lst.data.program = old


def draw_bog(game, lst):
    """Moving water on the Mire's bog pools (swamp.py's swamp_pool_list). Call right after the ground: it
    redraws only their water pixels, blended over what the ground shader painted there."""
    if lst is None or not len(lst):
        return
    _, _, t0, bog = _progs(game)
    _common(game, bog, t0)
    bog["hill_max"] = game._hill_prog["hill_max"]
    game.hill_apply(bog)
    ctx = game.ctx
    ctx.enable(ctx.BLEND)
    # the same triangles as the ground under them: pull them a hair towards the camera so they always win
    gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
    gl.glPolygonOffset(-1.0, -2.0)
    lst._init_deferred()
    old = lst.data.program
    lst.data.program = bog
    try:
        lst.draw()
    finally:
        lst.data.program = old
        gl.glDisable(gl.GL_POLYGON_OFFSET_FILL)


def flow_speed(hw, ford):
    """How fast a river runs (px/s): narrow stretches and fords run faster."""
    return 34.0 * max(0.7, min(1.6, 55.0 / max(hw, 1.0))) * (1.6 if ford else 1.0)

