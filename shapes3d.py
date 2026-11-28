"""
shapes3d.py - low-poly 3D shapes for the world's terrain props (used by view3d.py).

The game's art is painted from above. Instead of standing those pictures up as flat cut-outs, world
objects become small 3D shapes built on the GPU, straight from the SpriteLists the game already keeps:
one geometry-shader draw per kind of object, no per-frame CPU work, nothing to keep in sync.

(Creatures and other organic, detailed props come from Blender models - models3d.py, see docs/MODELS.md.
Terrain props - trees, rocks, plants, crystals, buildings - stay in the SHAPES table here.)

=====================================================================================================
HOW TO ADD A NEW 3D OBJECT (e.g. for a new biome)
=====================================================================================================
1. Give the sprite a `.kind` (Node / Structure already have one) and put it in one of the lists the
   3D view draws with `draw_kinds`: L.trees, L.rocks, L.bushes or L.builds.
2. Register a shape for that kind, ideally with a ready-made builder:

       import shapes3d as S3
       S3.SHAPES["pine"] = S3.conifer(tiers=4, height=3.2, radius=0.9, needles=S3.Fill(0.5, 0.45))
       S3.SHAPES["ash_rock"] = S3.boulder(height=0.9, lump=0.3)
       S3.SHAPES["ice_crystal"] = S3.crystal_cluster(n=5, color=(150, 220, 255), glow=0.5, seed=3)
       S3.SHAPES["river_reeds"] = S3.blade_clump(n=14, height=2.4, colors=[(96, 128, 56), (120, 144, 64)])
       S3.SHAPES["frost_cap"] = S3.mushroom_cluster(cap=(160, 220, 255), glow=0.9)

   That's all: kinds are matched to shapes by `sprite.kind` (SHAPES[kind]). If one kind needs several
   looks (trees: oak / willow / dead tree), add a picker to VARIANTS: VARIANTS["tree"] = lambda s: name.
   Kinds without a shape are still drawn as upright cut-outs, so nothing ever disappears.
   Builder functions: boulder, dome_bush, crystal_cluster, canopy_tree, conifer, willow, dead_tree,
   blade_clump, mushroom_cluster, box_prop. Keep extra-biome builders in this file, keyed by parameters.

3. Units. A shape lives in its sprite's own frame, measured in R = half the sprite's smaller side:
       x = forward (the picture's right), y = left (the picture's top), z = up.
   So shapes grow with the sprite. `foot` squashes x / y to the picture's footprint (1.0 = edge).

4. A Shape is a list of Parts. A Part is one surface of revolution - a stack of RINGS
       (radius, height, picture radius, shade)
   placed with at=(x, y, z), size=(sx, sy, sz) and leaned with tilt (towards +x) / roll (towards +y).
   Ready-made ring stacks: ball(), tube(), cone(), dome(), disc(). Its colour (`color=`) is one of:
       None          drape the sprite's picture over it from above, dropping see-through pixels (rocks)
       Fill(u, v)    drape the picture, but fill the see-through / painted-shadow bits with the picture's
                     colour at (u, v) - ALWAYS use this for foliage, so canopies stay solid from below
       Pick(u, v)    one plain colour, picked from the picture at (u, v) (u, v = 0..1 like PIL: y down).
                     Follows each variant's palette automatically
       (r, g, b)     a fixed plain colour
5. Effects (per Part, all on the GPU):
       glow=0.8      emissive: ignores the sun and is drawn again additively after the night lighting
                     (glowcaps, lantern glass, crystals). Keep a ground glow sprite in L.glows too for
                     the light pool on the ground (see swamp.py swamp_glows).
       sway=0.3      bends in the wind, more towards the top (foliage, reeds, grass)
       jitter=0.2    lumpy, different per object (rocks, canopy blobs)
6. Foliage / canopies: build them from several overlapping Fill-ed ball() blobs (canopy_tree does this),
   never from one open sheet: the top-down picture has transparent edges and a painted shadow, and a
   thin draped sheet turns into holes and black fringes from eye level.
   Thin plants (reeds, grass, cattails): blade_clump - each blade a 3-sided cone(sides=3), leaned
   out with tilt/roll, swaying. Cheap and solid from every side.
7. Trees: depth "alt" - sprite.depth >= 1 is the standing tree, depth 0 the stump (alt=[...] parts).
   view3d sets the depth. Things hanging in trees (beehives) use depth "lift" (raised by sprite.depth).
8. Budget: every band (pair of rings) costs 2 * (sides + 1) vertices per object. A shape is split into
   GPU invocations of MAX_VERTS vertices; aim for <= 4 invocations (~450 vertices) for things that are
   common (trees, rocks), and use few sides (3-7) for small parts. Check with:  print(SHAPES[k].passes)
=====================================================================================================
"""
import math
import random
import struct

import lighting3d

MAX_RINGS = 160
MAX_PARTS = 56
MAX_BANDS = 224
MAX_INV = 12
MAX_VERTS = 112           # per invocation: 9 floats out per vertex, 1024 floats max (GPU limit)
BINDING = 3               # uniform block binding the shape data is bound to

MESH_GEO = """
#version %VER%
layout (points%INV%) in;
layout (triangle_strip, max_vertices = %VERTS%) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
layout (std140) uniform ShapeBlock {
    vec4 rings[%RINGS%];    // radius, height, picture radius, shade
    vec4 pa[%PARTS%];       // at x, y, z ; sway
    vec4 pb[%PARTS%];       // size x, y, z ; tilt
    vec4 pc[%PARTS%];       // roll, swing, swing phase, glow
    vec4 pd[%PARTS%];       // colour a, b, c ; mode (0 drape, 1 drape + fill at (a,b), 2 pick at (a,b) * c, 3 rgb)
    vec4 pe[%PARTS%];       // reach, jitter, sides, detail (1: skipped far away)
    ivec4 bands[%BANDS2%];  // (part, ring) pairs
    ivec4 runs[%INVS%];     // per invocation: band range when standing [x, y), as a stump [z, w)
    vec4 g0;                // foot x, foot y, turn, alt_below
    vec4 g1;                // stride, bob, lean, extent (R)
    vec4 g2;                // depth use (0 alt, 1 lunge, 2 lift)
};
uniform sampler2D sprite_texture;
uniform sampler2D uv_texture;
uniform float uv_offset_bias;
uniform float inflate;      // armor worn over a body
uniform vec2 sun;           // shadow direction (light comes from the other side)
uniform float time;         // wind
uniform int glow_pass;      // 1: only the glowing parts, added on top of the night
uniform int coarse;         // 1: leave out the small extras, as far away (the shadow pass: cheaper)
%PASSUNI%
in float v_angle[];
in vec4 v_color[];
in vec2 v_size[];
in float v_texture[];
out vec2 gs_uv;
out float gs_shade;
flat out uint gs_rgba;      // the sprite's colour, packed
flat out uint gs_fill;      // the part's plain colour (alpha 0: none - drop see-through pixels)
%LIB%
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
uint pack4(vec4 c) {
    uvec4 c8 = uvec4(clamp(c, 0.0, 1.0) * 255.0 + 0.5);
    return c8.r | (c8.g << 8) | (c8.b << 16) | (c8.a << 24);
}
vec2 uv0, uv1, uv2, uv3;
vec2 pic(vec2 st) { return mix(mix(uv2, uv3, st.x), mix(uv0, uv1, st.x), st.y); }
vec4 pick(vec2 at) {        // average colour around a picture spot (PIL-style, y down), alpha weighted
    vec2 st = vec2(at.x, 1.0 - at.y);
    vec4 acc = vec4(0.0);
    for (int k = 0; k < 5; k++) {
        vec2 o = k == 0 ? vec2(0.0) : vec2((k & 1) == 1 ? 0.04 : -0.04, k < 3 ? 0.04 : -0.04);
        vec4 t = textureLod(sprite_texture, pic(clamp(st + o, 0.0, 1.0)), 0.0);
        acc += vec4(t.rgb * t.a, t.a);
    }
    return acc.a > 0.01 ? vec4(acc.rgb / acc.a, acc.a / 5.0) : vec4(0.0);
}
void main() {
    vec3 c = gl_in[0].gl_Position.xyz;
    if (c.z < -0.5 || c.z >= 1000.0 || v_color[0].a <= 0.0) return;   // wall blocks, hidden
    int pass = %PASS%;
    vec2 hs = v_size[0] / 2.0;
    float R = min(hs.x, hs.y) * inflate;
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    mat4 mvp = window.projection * window.view;
    vec2 foot = g0.xy;
    vec2 fs = foot * hs * inflate / R;
    int du = int(g2.x);
    float lift = du == 2 ? c.z : 0.0;
    // off screen (most of the map in the tilted view)? skip it before doing any work
    float rb = g1.w * R * max(max(fs.x, fs.y), 1.0) * 1.15;
    vec4 q = mvp * vec4(c.xy, lift + R, 1.0);
    float bx = rb * abs(window.projection[0][0]);
    float by = rb * abs(window.projection[1][1]);
    if (q.w < -rb || q.x - bx > q.w || q.x + bx < -q.w || q.y - by > q.w || q.y + by < -q.w) return;
    bool far = q.w > 1100.0;
    bool alt = du == 0 && c.z < g0.w;
    ivec4 run = runs[pass];
    int b0 = alt ? run.z : run.x;
    int b1 = alt ? run.w : run.y;
    if (b0 >= b1) return;
    getSpriteUVs(uv_texture, int(v_texture[0]), uv0, uv1, uv2, uv3);
    vec2 hp = 0.5 / vec2(textureSize(sprite_texture, 0)) * uv_offset_bias;
    uv0 += hp; uv1 += vec2(-hp.x, hp.y); uv2 += vec2(hp.x, -hp.y); uv3 += -hp;
    vec3 L = normalize(vec3(-sun.x, -sun.y, 1.4));
    float seed = hash(c.xy * 0.173);
    float lunge = du == 1 ? clamp(c.z, 0.0, 1.0) : 0.0;
    vec2 fwd = rot * vec2(1.0, 0.0);
    float walk = dot(c.xy, fwd) / R * g1.x * 6.2831853;
    vec3 base = vec3(c.xy + fwd * (g1.z * lunge * R), lift + g1.y * R * abs(sin(walk)));
    uint rgba = pack4(v_color[0]);
    int cur = -1;
    bool skip = false;
    int mode = 0;
    int sides = 8;
    float glow = 0.0, jit = 0.0, sway = 0.0, srad = 1.0;
    uint fill = 0u;
    vec3 at = vec3(0.0), sz = vec3(1.0);
    mat3 M = mat3(1.0);
    for (int b = b0; b < b1; b++) {
        ivec4 pr = bands[b >> 1];
        int p = (b & 1) == 0 ? pr.x : pr.z;
        int k = (b & 1) == 0 ? pr.y : pr.w;
        if (p != cur) {
            cur = p;
            vec4 A = pa[p], B = pb[p], C = pc[p], D = pd[p], E = pe[p];
            mode = int(D.w);
            glow = C.w;
            skip = (glow_pass == 1 && glow <= 0.0) || (E.w > 0.5 && (q.w > 1500.0 || coarse == 1));
            vec4 col = vec4(D.rgb, 1.0);
            if (mode == 1 || mode == 2) {
                vec4 s = pick(D.xy);
                col = vec4(s.rgb * (mode == 2 ? D.z : 1.0), s.a < 0.2 ? 0.0 : 1.0);
                if (mode == 2 && s.a < 0.2) skip = true;     // nothing there in this picture (gear)
            }
            if (mode == 0) col.a = 0.0;
            fill = pack4(col);
            float tilt = B.w + E.x * lunge + C.y * sin(walk + C.z);
            float ct = cos(tilt), st = sin(tilt), cr = cos(C.x), sr = sin(C.x);
            M = mat3(1.0, 0.0, 0.0, 0.0, cr, -sr, 0.0, sr, cr) * mat3(ct, 0.0, -st, 0.0, 1.0, 0.0, st, 0.0, ct);
            at = A.xyz;
            sz = B.xyz;
            sway = A.w * 0.07 * sin(time * 1.6 + seed * 6.2831853 + float(p) * 1.3);
            jit = E.y;
            srad = (sz.x + sz.y) * 0.5;
            sides = int(E.z);
            if (far) sides = max(3, sides / 2);
        }
        if (skip) continue;
        vec4 r0 = rings[k];
        vec4 r1 = rings[k + 1];
        vec2 n2 = normalize(vec2((r1.y - r0.y) * sz.z, (r0.x - r1.x) * srad) + vec2(1e-5, 0.0));
        float hseed = seed + float(p) * 0.37;
        for (int i = 0; i <= sides; i++) {
            float ph = g0.z + 6.2831853 * float(i) / float(sides);
            vec2 cs = vec2(cos(ph), sin(ph));
            float j = 1.0 + jit * (hash(vec2(hseed, float(i % sides))) - 0.5) * 2.0;
            float zj = 1.0 + jit * 0.4 * (hash(vec2(hseed, float(i % sides) + 17.0)) - 0.5);
            vec3 n = M * vec3(cs * n2.x, n2.y);
            n.xy = rot * n.xy;
            float light = 0.66 + 0.48 * max(dot(n, L), 0.0);
            for (int e = 1; e >= 0; e--) {
                vec4 rg = e == 1 ? r1 : r0;
                vec3 lp = M * (vec3(cs * rg.x * j, rg.y * zj) * sz) + at;
                if (sway != 0.0) lp.xy += vec2(1.0, 0.45) * sway * max(lp.z, 0.0) * max(lp.z, 0.0);
                gl_Position = mvp * vec4(base.xy + rot * (lp.xy * fs) * R, base.z + lp.z * R, 1.0);
                float s = abs(rg.w) * light;
                gs_shade = glow_pass == 1 ? glow : max(s, glow * 0.8);
                gs_rgba = rgba;
                gs_fill = fill;
                if (mode >= 2) {
                    gs_uv = vec2(-10.0);
                } else {
                    vec3 pp = M * (vec3(cs * rg.z * j, rg.y) * sz) + at;
                    gs_uv = pic(clamp(0.5 + 0.5 * pp.xy * foot, 0.0, 1.0));
                }
                EmitVertex();
            }
        }
        EndPrimitive();
    }
}
"""

MESH_FS = """
#version 330
uniform sampler2D sprite_texture;
uniform vec4 spritelist_color;
uniform float alpha_cut;
uniform int glow_pass;
in vec2 gs_uv;
in float gs_shade;
flat in uint gs_rgba;
flat in uint gs_fill;
out vec4 f_color;
vec4 unpack4(uint u) { return vec4(uvec4(u, u >> 8, u >> 16, u >> 24) & 255u) / 255.0; }
void main() {
    vec4 col = unpack4(gs_rgba);
    vec4 fill = unpack4(gs_fill);
    vec3 rgb = fill.rgb;
    if (gs_uv.x > -5.0) {
        vec4 t = texture(sprite_texture, gs_uv);
        if (fill.a > 0.5) {
            rgb = mix(fill.rgb, t.rgb, smoothstep(0.55, 0.95, t.a));   // foliage: never holes
        } else {
            if (t.a <= alpha_cut) discard;
            rgb = t.rgb;
        }
    }
    rgb *= col.rgb;
    // lighting3d.py (pasted in by program_sources): gs_shade is the sun shading from the geometry shader;
    // here the hemisphere tint, the time of day, the night's point lights, a faint rim and the fog. The
    // position comes from the depth buffer and the normal from the flat face, so the geometry shader
    // (already at the GPU's output limit) passes nothing extra.
    vec3 p = lt_world();
    if (glow_pass == 1) {
        rgb = lt_fogged(rgb * gs_shade, p);
    } else {
        vec3 n = lt_face(p);
        rgb = lt_weather(rgb, p, n, 0.0);               // wet in the rain, white tops in the snow (weather3d.py)
        float sun = gs_shade * lt_sunlit(p, n);         // in the shadow of something else (shadows3d.py)
        rgb = rgb * sun * lt_hemi(n) * lt_light(p, n) + 0.5 * lt_rimlight(p, n) * (0.3 + rgb);
        rgb = lt_fogged(rgb, p);
    }
    f_color = vec4(rgb, col.a) * spritelist_color;
}
"""


# The shadow pass (shadows3d.py): the same geometry shader seen from the sun, writing only depth. Picture
# pixels that are see-through (and not filled, like foliage) let the sun through, as they do on screen.
SHADOW_FS = """
#version 330
uniform sampler2D sprite_texture;
uniform vec4 spritelist_color;
uniform float alpha_cut;
in vec2 gs_uv;
flat in uint gs_fill;
void main() {
    if (spritelist_color.a <= 0.0) discard;
    if (gs_uv.x > -5.0 && (gs_fill >> 24) < 128u && texture(sprite_texture, gs_uv).a <= alpha_cut) discard;
}
"""


def program_sources(lib, invocations=None, verts=MAX_VERTS, shadow=False):
    """GLSL for the shape program. invocations=n (OpenGL 4.0+): one draw call does all n passes of a shape.
    invocations=None: plain 3.3 - the caller draws once per pass with the `pass_id` uniform.
    verts: the most vertices one pass emits (smaller = cheaper on GPUs that emulate geometry shaders).
    shadow: the depth-only version for the sun's shadow map (shadows3d.py)."""
    geo = MESH_GEO
    if invocations:
        geo = geo.replace("%VER%", "410").replace("%INV%", f", invocations = {invocations}")
        geo = geo.replace("%PASS%", "gl_InvocationID").replace("%PASSUNI%", "")
    else:
        geo = geo.replace("%VER%", "330").replace("%INV%", "")
        geo = geo.replace("%PASS%", "pass_id").replace("%PASSUNI%", "uniform int pass_id;")
    geo = (geo.replace("%LIB%", lib).replace("%VERTS%", str(verts)).replace("%RINGS%", str(MAX_RINGS))
           .replace("%PARTS%", str(MAX_PARTS)).replace("%BANDS2%", str(MAX_BANDS // 2)).replace("%INVS%", str(MAX_INV)))
    return geo, SHADOW_FS if shadow else lighting3d.inject(MESH_FS, frag=True)


# =========================================================================== building blocks
class Fill:
    """Drape the picture, filling see-through bits with the picture's colour at (u, v) (0..1, y down)."""

    def __init__(self, u=0.5, v=0.5):
        self.u, self.v = u, v


class Pick:
    """One plain colour picked from the picture at (u, v) (0..1, y down), times `mul`."""

    def __init__(self, u, v, mul=1.0):
        self.u, self.v, self.mul = u, v, mul


class Part:
    """One surface of revolution (see the module docstring)."""

    def __init__(self, rings, at=(0.0, 0.0, 0.0), size=1.0, tilt=0.0, roll=0.0, color=None, sides=8,
                 sway=0.0, glow=0.0, jitter=0.0, swing=0.0, swing_phase=0.0, reach=0.0, detail=False):
        self.rings = [tuple(map(float, r)) for r in rings]
        assert len(self.rings) >= 2
        self.at = tuple(map(float, at))
        self.size = (float(size),) * 3 if isinstance(size, (int, float)) else tuple(map(float, size))
        self.tilt, self.roll = float(tilt), float(roll)
        self.color, self.sides = color, int(sides)
        assert 3 <= self.sides <= 12
        self.sway, self.glow, self.jitter = float(sway), float(glow), float(jitter)
        self.swing, self.swing_phase, self.reach = float(swing), float(swing_phase), float(reach)
        self.detail = bool(detail)      # small extra: left out far away (cheaper forests)

    def mirrored(self):
        """The same part on the other side (y and roll flipped)."""
        p = Part(self.rings, (self.at[0], -self.at[1], self.at[2]), self.size, self.tilt, -self.roll, self.color,
                 self.sides, self.sway, self.glow, self.jitter, self.swing, self.swing_phase + math.pi, self.reach,
                 self.detail)
        return p

    def verts(self):
        return (len(self.rings) - 1) * 2 * (self.sides + 1)

    def extent(self):
        sx, sy, sz = self.size
        e = 0.0
        for r, h, _, _ in self.rings:
            e = max(e, math.hypot(r * max(sx, sy), h * sz))
        return math.hypot(*self.at) + e

    def colour_vec(self):
        c = self.color
        if c is None:
            return (0.0, 0.0, 0.0, 0.0)
        if isinstance(c, Fill):
            return (c.u, c.v, 0.0, 1.0)
        if isinstance(c, Pick):
            return (c.u, c.v, c.mul, 2.0)
        return (c[0] / 255, c[1] / 255, c[2] / 255, 3.0)


DEPTH_USE = {"alt": 0, "lunge": 1, "lift": 2}


class Shape:
    """A list of Parts drawn for every sprite of one kind. alt = the parts shown instead when sprite.depth < 1
    (tree stumps). depth: how sprite.depth is used - "alt", "lunge" (0..1 leans forward) or "lift" (raised).
    card_lift: also stand the picture up on top, this many R high (turret crossbow)."""

    def __init__(self, parts, alt=None, foot=(0.9, 0.9), turn=0.0, cut=0.2, card_lift=None, depth="alt",
                 stride=0.0, bob=0.0, lean=0.0):
        parts = sorted(parts, key=lambda p: p.detail)      # details last: far away whole passes drop out
        self.parts = list(parts) + list(alt or [])
        assert len(self.parts) <= MAX_PARTS, "too many parts"
        nmain = len(parts)
        rings, starts = [], []
        for p in self.parts:
            starts.append(len(rings))
            rings.extend(p.rings)
        assert len(rings) <= MAX_RINGS, "too many rings"

        def pack(idx):
            runs, bands, cur, used = [], [], [], 0
            for i in idx:
                p = self.parts[i]
                for k in range(len(p.rings) - 1):
                    v = 2 * (p.sides + 1)
                    if used + v > MAX_VERTS and cur:
                        runs.append(cur)
                        cur, used = [], 0
                    cur.append((i, starts[i] + k))
                    used += v
            if cur:
                runs.append(cur)
            return runs

        main = pack(range(nmain))
        alts = pack(range(nmain, len(self.parts))) if alt else []
        bands, rmain, ralt = [], [], []
        for runs, out in ((main, rmain), (alts, ralt)):
            for r in runs:
                out.append((len(bands), len(bands) + len(r)))
                bands.extend(r)
        assert len(bands) <= MAX_BANDS, "too many bands"
        self.passes = max(len(rmain), len(ralt), 1)
        most = max(sum(2 * (self.parts[i].sides + 1) for i, _ in r) for r in main + alts)
        self.verts = min(MAX_VERTS, -(-most // 16) * 16)      # what one pass emits at most, rounded up
        assert self.passes <= MAX_INV, "shape too big: use fewer parts / sides"
        self.has_glow = any(p.glow > 0 for p in self.parts)
        self.cut = cut
        self.card_lift = card_lift
        self.foot = tuple(map(float, foot))
        extent = max(p.extent() for p in self.parts)

        f = struct.pack
        data = bytearray()
        rflat = rings + [(0.0, 0.0, 0.0, 0.0)] * (MAX_RINGS - len(rings))
        for r in rflat:
            data += f("4f", *r)
        blank = (0.0, 0.0, 0.0, 0.0)
        cols = [[], [], [], [], []]
        for p in self.parts:
            cols[0].append(p.at + (p.sway,))
            cols[1].append(p.size + (p.tilt,))
            cols[2].append((p.roll, p.swing, p.swing_phase, p.glow))
            cols[3].append(p.colour_vec())
            cols[4].append((p.reach, p.jitter, float(p.sides), float(p.detail)))
        for col in cols:
            for v in col + [blank] * (MAX_PARTS - len(col)):
                data += f("4f", *v)
        bflat = [x for b in bands for x in b] + [0] * (2 * MAX_BANDS - 2 * len(bands))
        data += f(f"{2 * MAX_BANDS}i", *bflat)
        for i in range(MAX_INV):
            m = rmain[i] if i < len(rmain) else (0, 0)
            a = ralt[i] if i < len(ralt) else (0, 0)
            data += f("4i", m[0], m[1], a[0], a[1])
        data += f("4f", self.foot[0], self.foot[1], float(turn), 1.0 if alt else -1e9)
        data += f("4f", float(stride), float(bob), float(lean), float(extent))
        data += f("4f", float(DEPTH_USE[depth]), 0.0, 0.0, 0.0)
        self.data = bytes(data)
        self.ubo = None           # GPU buffer, made by view3d on first use


# --------------------------------------------------------------------------- ring stacks
def ball(n=4, shade=(0.72, 1.06)):
    """A closed ellipsoid from z=-1 to z=1 (radius 1 at z=0), n bands. Squash it with Part(size=...)."""
    out = []
    for i in range(n + 1):
        ang = -math.pi / 2 + math.pi * i / n
        r = 0.0 if i in (0, n) else math.cos(ang)
        out.append((r, math.sin(ang), r, shade[0] + (shade[1] - shade[0]) * i / n))
    return out


def tube(r0, r1, h, z0=0.0, caps=False, shade=(0.8, 1.0)):
    """A (tapered) tube from z0 to z0 + h. caps=True closes both ends."""
    body = [(r0, z0, r0, shade[0]), (r1, z0 + h, r1, shade[1])]
    if caps:
        return [(0.0, z0, 0.0, shade[0])] + body + [(0.0, z0 + h, 0.0, shade[1])]
    return body


def cone(r, h, z0=0.0, shade=(0.8, 1.05)):
    return [(r, z0, r, shade[0]), (0.0, z0 + h, 0.0, shade[1])]


def dome(r, h, z0=0.0, shade=(0.7, 1.08)):
    """A mushroom cap: a flat-ish underside, then a rounded top (3 bands)."""
    return [(r * 0.25, z0, r * 0.25, shade[0] * 0.8), (r, z0 + h * 0.08, r, shade[0]),
            (r * 0.78, z0 + h * 0.62, r * 0.78, 1.0), (0.0, z0 + h, 0.0, shade[1])]


def disc(r, z=0.0, shade=1.0):
    return [(r, z, r, shade), (0.0, z, 0.0, shade)]


# =========================================================================== builders (reusable)
_ROCK = [(1.0, 0.0, 0.8, 0.72), (1.04, 0.32, 0.78, 0.88), (0.78, 0.8, 0.6, 1.0), (0.36, 1.08, 0.28, 1.06),
         (0.0, 1.16, 0.0, 1.08)]


def boulder(height=1.16, lump=0.2, sides=7, foot=(0.88, 0.86), turn=0.3, color=None, glow=0.0):
    """Lumpy faceted rock with its picture draped on (color=Pick / rgb for plain ones)."""
    rings = [(r, h * height / 1.16, p, s) for r, h, p, s in _ROCK]
    return Shape([Part(rings, sides=sides, jitter=lump, color=color, glow=glow)], foot=foot, turn=turn, cut=0.25)


def dome_bush(height=1.72, sides=9, lump=0.12, sway=0.0):
    rings = [(0.55, 0.0, 0.3, 0.6), (0.95, 0.42, 0.62, 0.85), (1.0, 0.88, 0.9, 0.95), (0.8, 1.32, 0.64, 1.0),
             (0.45, 1.62, 0.34, 1.05), (0.0, 1.72, 0.0, 1.08)]
    rings = [(r, h * height / 1.72, p, s) for r, h, p, s in rings]
    return Shape([Part(rings, sides=sides, jitter=lump, sway=sway)], foot=(0.86, 0.86), cut=0.3)


def crystal_cluster(n=5, height=2.0, color=None, glow=0.0, seed=1, spread=0.45, sides=5):
    """A big crystal with smaller ones leaning out around it. color None = draped picture."""
    rnd = random.Random(seed)
    spike = [(1.0, 0.0, 0.8, 0.75), (0.92, 0.27, 0.75, 0.95), (0.5, 0.71, 0.5, 1.15), (0.0, 1.0, 0.0, 1.3)]
    main = 1.0 if n == 1 else 0.62
    parts = [Part(spike, size=(main, main, height), sides=sides, jitter=0.25, color=color, glow=glow)]
    for i in range(n - 1):
        a = i / max(1, n - 1) * math.tau + rnd.uniform(-0.4, 0.4)
        d = spread * rnd.uniform(0.8, 1.2)
        s = rnd.uniform(0.3, 0.42)
        lean = rnd.uniform(0.35, 0.6)
        parts.append(Part(spike, at=(math.cos(a) * d, math.sin(a) * d, -0.05), size=(s, s, height * rnd.uniform(0.4, 0.6)),
                          tilt=math.cos(a) * lean, roll=math.sin(a) * lean, sides=max(3, sides - 1), jitter=0.2,
                          color=color, glow=glow))
    return Shape(parts, foot=(0.85, 0.85), turn=0.5, cut=0.2)


def _stump(bark):
    return [Part([(0.82, 0.0, 0.8, 0.6), (0.76, 0.45, 0.78, 0.85), (0.6, 0.55, 0.62, 1.0), (0.0, 0.55, 0.0, 1.0)],
                 size=(1.0, 1.0, 1.0), sides=8)]


def canopy_tree(trunk=1.9, crown=(2.15, 0.62), blobs=4, ring_r=0.46, leaves=None, bark=(104, 72, 44), seed=7,
                sway=0.12, blob_sides=6, foot=(0.9, 0.9)):
    """Broadleaf tree: a trunk and a lush crown of overlapping draped blobs (filled - no holes).
    crown = (height of the crown's centre, radius of the main blob) in R. leaves = Fill(u, v)."""
    rnd = random.Random(seed)
    leaves = leaves or Fill(0.5, 0.42)
    cz, cr = crown
    parts = [Part(tube(0.15, 0.09, trunk, shade=(0.7, 0.95)), color=bark, sides=5),
             Part(ball(4), at=(0, 0, cz), size=(cr, cr, cr * 0.85), color=leaves, sides=blob_sides,
                  jitter=0.14, sway=sway)]
    for i in range(blobs):
        a = i / blobs * math.tau + rnd.uniform(-0.3, 0.3)
        r = rnd.uniform(0.42, 0.5)
        parts.append(Part(ball(4), at=(math.cos(a) * ring_r, math.sin(a) * ring_r, cz - rnd.uniform(0.25, 0.45)),
                          size=(r, r, r * 0.8), color=leaves, sides=blob_sides, jitter=0.16, sway=sway, detail=i % 2 == 1))
    parts.append(Part(ball(3), at=(rnd.uniform(-0.1, 0.1), rnd.uniform(-0.1, 0.1), cz + cr * 0.62),
                      size=(cr * 0.62, cr * 0.62, cr * 0.5), color=leaves, sides=blob_sides, jitter=0.14, sway=sway))
    return Shape(parts, alt=_stump(bark), foot=foot)


def conifer(tiers=4, height=3.2, radius=0.9, trunk=0.6, needles=None, bark=(96, 66, 40), sway=0.08, sides=8,
            foot=(0.9, 0.9)):
    """Pine / fir: a trunk with stacked, drooping cones. needles = Fill(u, v) / rgb / Pick."""
    needles = needles or Fill(0.5, 0.5)
    parts = [Part(tube(0.14, 0.06, height * 0.9, shade=(0.7, 0.95)), color=bark, sides=6)]
    span = height - trunk
    for i in range(tiers):
        t = i / max(1, tiers - 1)
        r = radius * (1.0 - 0.62 * t)
        z0 = trunk + span * 0.78 * i / tiers
        h = span * (0.42 - 0.12 * t)
        parts.append(Part([(r * 0.25, 0.0, r * 0.25, 0.6), (r, -0.06, r, 0.78), (r * 0.45, h * 0.55, r * 0.45, 0.95),
                           (0.0, h, 0.0, 1.08)], at=(0, 0, z0), color=needles, sides=sides, jitter=0.08, sway=sway))
    return Shape(parts, alt=_stump(bark), foot=foot)


def willow(trunk=1.6, crown=(2.0, 0.72), leaves=None, bark=(70, 56, 40), seed=11, curtain=1.0):
    """Drooping swamp willow: a low wide crown and a curtain of hanging leaves that sways."""
    rnd = random.Random(seed)
    leaves = leaves or Fill(0.5, 0.45)
    cz, cr = crown
    parts = [Part(tube(0.2, 0.11, trunk + 0.3, shade=(0.65, 0.9)), color=bark, sides=7),
             Part(ball(4), at=(0, 0, cz), size=(cr, cr, cr * 0.6), color=leaves, sides=8, jitter=0.15, sway=0.1)]
    for i in range(4):
        a = i / 4 * math.tau + rnd.uniform(-0.3, 0.3)
        parts.append(Part(ball(3), at=(math.cos(a) * 0.4, math.sin(a) * 0.4, cz - 0.15), size=(0.45, 0.45, 0.3),
                          color=leaves, sides=7, jitter=0.15, sway=0.1, detail=i % 2 == 1))
    # the hanging curtain: an open, slightly flared skirt from the crown's rim. It stops above eye height
    # (~1.15 R for a 150 px tree), or standing next to the trunk in first person would bury you in leaves
    drop = curtain * (cz - 1.35)
    parts.append(Part([(0.86, 0.0, 0.84, 1.0), (0.98, -drop * 0.5, 0.9, 0.85), (1.02, -drop, 0.94, 0.72)],
                      at=(0, 0, cz - 0.05), size=(cr * 1.18, cr * 1.18, 1.0), color=leaves, sides=10, jitter=0.12,
                      sway=0.25))
    return Shape(parts, alt=_stump(bark), foot=(0.92, 0.92))


def dead_tree(branches=5, bark=(92, 84, 70), height=2.3, seed=5):
    """Bare dead tree: a twisted trunk and forking branches (plain bark colour)."""
    rnd = random.Random(seed)
    parts = [Part(tube(0.17, 0.08, height, shade=(0.65, 0.95)), color=bark, sides=6)]
    for i in range(branches):
        a = i / branches * math.tau + rnd.uniform(-0.3, 0.3)
        z = height * rnd.uniform(0.5, 0.85)
        lean = rnd.uniform(0.7, 1.1)
        ln = rnd.uniform(0.7, 0.95)
        parts.append(Part(tube(0.07, 0.025, ln), at=(0, 0, z), tilt=math.cos(a) * lean, roll=math.sin(a) * lean,
                          color=bark, sides=4))
        ex, ey = math.cos(a) * ln * math.sin(lean), math.sin(a) * ln * math.sin(lean)
        b = a + rnd.choice((-0.6, 0.6))
        parts.append(Part(tube(0.035, 0.012, ln * 0.6), at=(ex, ey, z + ln * math.cos(lean) * 0.9),
                          tilt=math.cos(b) * 0.5, roll=math.sin(b) * 0.5, color=bark, sides=3, sway=0.15))
    return Shape(parts, alt=_stump(bark), foot=(0.9, 0.9))


def blade_clump(n=16, height=2.4, spread=0.5, colors=((96, 128, 56), (120, 144, 64), (150, 150, 76)), cattails=0,
                head=(110, 72, 40), seed=3, sway=0.35, width=0.06):
    """Reeds / grass / sedge: thin 3-sided blades leaning out from a clump, swaying. cattails = how many
    stalks get a brown seed head."""
    rnd = random.Random(seed)
    parts = []
    for i in range(n):
        a = rnd.uniform(0, math.tau)
        d = spread * math.sqrt(rnd.random())
        lean = rnd.uniform(0.05, 0.35)
        parts.append(Part(cone(width, height * rnd.uniform(0.6, 1.0), shade=(0.7, 1.1)),
                          at=(math.cos(a) * d, math.sin(a) * d, 0.0), tilt=math.cos(a) * lean, roll=math.sin(a) * lean,
                          color=rnd.choice(colors), sides=3, sway=sway, detail=i >= n // 2))
    for i in range(cattails):
        a = rnd.uniform(0, math.tau)
        d = spread * 0.7 * math.sqrt(rnd.random())
        h = height * rnd.uniform(0.85, 1.05)
        lean = rnd.uniform(0.0, 0.15)
        at = (math.cos(a) * d, math.sin(a) * d, 0.0)
        tl, rl = math.cos(a) * lean, math.sin(a) * lean
        parts.append(Part(tube(width * 0.5, width * 0.4, h), at=at, tilt=tl, roll=rl, color=colors[0], sides=3, sway=sway))
        parts.append(Part(tube(width * 1.15, width * 1.15, h * 0.13, z0=h * 0.74, caps=True) + [(0.0, h * 0.95, 0.0, 1.0)],
                          at=at, tilt=tl, roll=rl, color=head, sides=4, sway=sway))
    return Shape(parts, foot=(1.0, 1.0))


def mushroom_cluster(caps=((0.0, 0.0, 1.1, 0.42), (0.42, 0.25, 0.75, 0.3), (-0.3, 0.38, 0.6, 0.26),
                           (-0.1, -0.45, 0.85, 0.34)), stem=(214, 220, 196), cap=(90, 230, 200), glow=0.0,
                     sway=0.05, sides=6):
    """Mushrooms: caps = (x, y, height, cap radius) in R. glow > 0 makes the caps emissive."""
    parts = []
    for x, y, h, r in caps:
        parts.append(Part(tube(r * 0.24, r * 0.18, h), at=(x, y, 0.0), color=stem, sides=4, sway=sway))
        parts.append(Part(dome(r, r * 0.8, z0=h - r * 0.1), at=(x, y, 0.0), color=cap, sides=sides, glow=glow,
                          sway=sway))
    return Shape(parts, foot=(1.0, 1.0))


def box_prop(height=1.0, top=None, sides_col=(110, 110, 110), foot=(1.3, 1.3), extra=()):
    """A box: plain sides, the picture draped on the lid. extra = more Parts (chimney, lamp...)."""
    BOXPIC = 0.74
    parts = [Part([(1.0, 0.0, 0, 0.62), (1.0, height * 0.92, 0, 0.9)], color=sides_col, sides=4),
             Part([(1.0, height * 0.92, BOXPIC, 0.9), (0.94, height, BOXPIC * 0.94, 1.0), (0.0, height, 0.0, 1.0)],
                  color=top, sides=4)] + list(extra)
    return Shape(parts, foot=foot, turn=math.pi / 4, cut=0.1)


# =========================================================================== the table
Q = math.pi / 4          # turns 4 sides into a box lined up with the sprite
BOX = 1.3                # 4-sided footprint scale so the box corners reach the picture's corners
BOXPIC = 0.74            # ...and the picture radius that keeps them inside it


def _solid(rings, col):
    return Part(rings, color=col, sides=8)


SHAPES = {
    "rock": boulder(),
    "crystal": crystal_cluster(n=1, height=2.05),
    "bush": dome_bush(),
    # broadleaf trees; swamp trees are picked by VARIANTS below
    "tree": canopy_tree(),
    "willow": willow(),
    "dead_tree": dead_tree(),
    # a beehive hanging under the canopy (sprite.depth = how high)
    "hive": Shape([Part(tube(0.05, 0.05, 0.6, z0=1.7), color=(96, 66, 36), sides=3),
                   Part([(0.0, 0.0, 0.0, 0.7), (0.42, 0.08, 0.3, 0.75), (0.62, 0.45, 0.5, 0.9), (0.7, 0.9, 0.62, 1.0),
                         (0.55, 1.35, 0.5, 1.05), (0.35, 1.68, 0.3, 1.05), (0.0, 1.85, 0.0, 1.0)],
                        color=Pick(0.5, 0.55), sides=7, sway=0.04)], foot=(1.0, 1.0), depth="lift"),
    # the Mire
    "reeds": blade_clump(n=13, height=2.3, spread=0.45, cattails=4, seed=4800,
                         colors=((96, 128, 56), (120, 144, 64), (150, 150, 76), (80, 110, 48))),
    "glowcap": mushroom_cluster(cap=(90, 230, 200), glow=0.85),
    "campfire": Shape([Part([(1.0, 0.0, 0.98, 0.7), (1.0, 0.12, 0.98, 0.9), (0.78, 0.2, 0.78, 1.0), (0.0, 0.12, 0.0, 1.0)],
                            sides=10),
                       Part([(0.42, 0.06, 0, 0.8), (0.0, 1.0, 0, 1.0)], color=(110, 70, 40), sides=6)],
                      foot=(0.92, 0.92), cut=0.25),
    "brazier": Shape([_solid([(0.38, 0.0, 0, 0.5), (0.18, 0.9, 0, 0.7)], (62, 60, 64)),
                      Part([(0.22, 0.88, 0.25, 0.6), (1.0, 1.38, 0.98, 0.85), (0.9, 1.48, 0.9, 1.0), (0.0, 1.38, 0.0, 0.8)],
                           sides=10)], foot=(0.86, 0.86)),
    "workbench": Shape([Part([(0.8, 0.0, 0, 0.6), (0.8, 0.9, 0, 0.75)], color=(96, 64, 38), sides=4),
                        Part([(1.0, 0.88, BOXPIC, 0.75), (1.0, 1.2, BOXPIC, 0.9), (0.0, 1.2, 0.0, 1.0)], sides=4)],
                       foot=(BOX * 0.95, BOX * 0.9), turn=Q, cut=0.1),
    "storage": Shape([Part([(1.0, 0.0, BOXPIC, 0.7), (1.0, 0.95, BOXPIC, 0.88), (0.92, 1.08, BOXPIC * 0.92, 1.0),
                            (0.0, 1.08, 0.0, 1.0)], sides=4)], foot=(BOX * 0.92, BOX * 0.88), turn=Q, cut=0.1),
    "furnace": box_prop(1.35, sides_col=(120, 116, 110), foot=(BOX * 0.92, BOX * 0.92), extra=[
        Part(tube(0.22, 0.2, 0.75, z0=1.3, caps=True), at=(-0.35, 0.35, 0), color=(96, 92, 88), sides=6),
        Part(disc(0.3), at=(0.72, 0.0, 0.5), size=(1.0, 1.4, 1.0), tilt=math.pi / 2, color=(255, 150, 50),
             sides=6, glow=0.9)]),
    "lantern": Shape([Part(tube(0.32, 0.28, 0.22, caps=True), color=(128, 126, 120), sides=7),
                      Part(tube(0.07, 0.07, 2.2), color=(120, 82, 46), sides=5),
                      Part(tube(0.05, 0.05, 0.5), at=(0, 0, 2.15), tilt=math.pi / 2, color=(62, 58, 56), sides=3),
                      Part(tube(0.2, 0.23, 0.45, z0=1.55, caps=True), at=(0.45, 0, 0), color=(255, 214, 120), sides=6,
                           glow=1.0),
                      Part(cone(0.27, 0.18, z0=2.0), at=(0.45, 0, 0), color=(70, 70, 76), sides=6)],
                     foot=(1.0, 1.0)),
    "gate": Shape([Part(tube(0.14, 0.14, 1.6, caps=True), at=(0, 0.85, 0), color=(120, 82, 46), sides=5),
                   Part(tube(0.14, 0.14, 1.6, caps=True), at=(0, -0.85, 0), color=(120, 82, 46), sides=5),
                   Part([(1.0, 0.1, 0, 0.75), (1.0, 1.35, 0, 1.0), (0.0, 1.35, 0, 1.0)], size=(0.16, 0.95, 1.0),
                        color=(152, 106, 62), sides=4)],
                  foot=(1.0, 1.0), turn=Q, cut=0.1),
    "arrow_turret": Shape([_solid([(0.78, 0.0, 0, 0.7), (0.72, 0.62, 0, 0.95), (0.84, 0.62, 0, 0.85),
                                   (0.84, 0.8, 0, 1.05), (0.0, 0.8, 0, 1.1)], (132, 130, 128))],
                          foot=(0.9, 0.9), turn=0.39, card_lift=0.8),
    "hut": Shape([Part([(1.0, 0.0, 0, 0.65), (1.0, 0.85, 0, 0.95)], color=(124, 88, 54), sides=4),
                  Part([(1.1, 0.8, BOXPIC, 0.95), (0.0, 1.55, 0.0, 1.12)], sides=4)],
                 foot=(BOX, BOX), turn=Q, cut=0.1),
    # first person only: living things (models3d.py will replace these with real models)
    "body": Shape([Part([(0.62, 0.0, 0.6, 0.45), (0.62, 0.14, 0.6, 0.55), (0.92, 0.34, 0.9, 0.8), (1.0, 0.62, 0.98, 0.95),
                         (0.76, 0.88, 0.72, 1.02), (0.0, 0.98, 0.0, 1.06)])], foot=(0.8, 0.42), cut=0.15),
    "boss": Shape([Part([(0.6, 0.0, 0.55, 0.5), (0.9, 0.55, 0.85, 0.75), (1.0, 1.1, 0.98, 0.95), (0.78, 1.6, 0.72, 1.02),
                         (0.0, 1.8, 0.0, 1.06)], sides=10)], foot=(0.78, 0.7), cut=0.15),
    # a peg person: legs, body, shoulders, neck and a round head (the top of the picture is the head)
    "person": Shape([Part([(0.5, 0.0, 0.5, 0.45), (0.58, 1.1, 0.52, 0.6), (0.92, 1.25, 0.62, 0.8), (1.0, 1.85, 0.68, 0.95),
                           (0.82, 2.08, 0.6, 1.0), (0.32, 2.14, 0.26, 0.9), (0.56, 2.24, 0.32, 1.0), (0.62, 2.44, 0.34, 1.05),
                           (0.42, 2.64, 0.24, 1.08), (0.0, 2.72, 0.0, 1.1)], sides=5)], foot=(0.55, 0.55), cut=0.15),
}
SHAPES["iron"] = SHAPES["coal"] = SHAPES["rock"]

SWAMP_TREE = 10          # tree variants from here up are swamp trees (10, 11 willows, 12 dead) - see art_swamp.py
# kinds with more than one look: kind -> function(sprite) -> shape name
VARIANTS = {
    "tree": lambda s: "tree" if s.variant < SWAMP_TREE else ("dead_tree" if (s.variant - SWAMP_TREE) % 3 == 2 else "willow"),
}


def shape_key(s):
    """Which SHAPES entry draws sprite s (or a kind with no shape -> a cut-out)."""
    kind = getattr(s, "kind", "")
    pick = VARIANTS.get(kind)
    return pick(s) if pick else kind


# extra height for the flame of a fire that sits on a 3D shape (in sprite pixels, like sprite.depth)
FLAME_DEPTH = {"brazier": 19}
