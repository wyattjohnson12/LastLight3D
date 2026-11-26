"""
shapes3d.py - low-poly 3D volumes for the 3D view (used by view3d.py).

The game's art is painted from above. Instead of standing those pictures up as flat cut-outs
(which look like cardboard from eye level in first person), these objects become small 3D shapes
with their own picture DRAPED over them from above:

    rocks & ores  - lumpy faceted boulders          bushes   - round leafy domes
    trees         - a trunk and a two-tier canopy   stumps   - short cylinders
    campfires     - a ring of stones + a log teepee braziers - iron stand + bowl
    benches/bins  - boxes                           huts     - walls and a hip roof
    turrets       - a stone pedestal (the crossbow picture stands on top)
    first person only: animals and bosses get round bodies, survivors and zombies upright bodies

Seen from the tilted camera the draped picture still looks like the original art; from eye level
you see a solid shape in the same colours. All of it is made on the GPU by one geometry shader,
straight from the SpriteLists the game already keeps (one draw call per kind, nothing built on the
CPU per frame), so it stays fast with hundreds of trees and rocks.

A shape is a stack of RINGS (a surface of revolution, squashed to the sprite's footprint):
    (radius, height, picture radius, tint)
  radius   - share of the footprint (FOOT * half the sprite's size)
  height   - in units of R = half the sprite's smaller side (so shapes grow with the sprite)
  picture  - how far out in the picture this ring takes its colour from (0 centre .. 1 edge)
  tint     - brightness; a NEGATIVE tint means a plain colour (the shape's `solid`) instead of the picture
A ring index listed in `breaks` starts a new part (no band joins it to the ring before).
"""
import math

MAX_RINGS = 16
MAX_VERTS = 128           # most vertices one shader run may emit (GPU limit: 8 floats each, 1024 floats max).
                          # Bigger shapes take more passes - and every pass costs, so keep shapes within one

MESH_GEO = """
#version 330
layout (points) in;
layout (triangle_strip, max_vertices = %VERTS%) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform sampler2D sprite_texture;
uniform sampler2D uv_texture;
uniform float uv_offset_bias;
uniform vec4 rings[%MAX%];  // radius, height (xR), picture radius, tint (<0 = solid colour)
uniform int nrings;
uniform int alt_start;      // rings [alt_start, nrings) are a second shape (tree stumps)...
uniform float alt_below;    // ...used when sprite.depth < alt_below
uniform int breaks;         // bit k set: ring k starts a new part
uniform int segs;           // sides (<= 10)
uniform float phase;        // turn the sides (45 degrees makes a 4-sided shape a box)
uniform vec2 foot;          // footprint: share of the sprite's half width / half height
uniform vec3 solid;         // colour of the plain rings
uniform float jitter;       // lumpy rocks
uniform float inflate;      // armor worn over a body
uniform vec2 sun;           // shadow direction (light comes from the other side)
uniform int pass_id;        // which share of the bands this draw call makes
uniform int band_per;       // ...and how many bands make a share
in float v_angle[];
in vec4 v_color[];
in vec2 v_size[];
in float v_texture[];
out vec2 gs_uv;
out float gs_shade;
flat out uint gs_rgba;      // the sprite's colour, packed (keeps the output small: more vertices per pass)
%LIB%
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
    vec3 c = gl_in[0].gl_Position.xyz;
    if (c.z < -0.5 || c.z >= 1000.0 || v_color[0].a <= 0.0) return;   // wall blocks, beehives, hidden
    vec2 hs = v_size[0] / 2.0;
    float R = min(hs.x, hs.y);
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    mat4 mvp = window.projection * window.view;
    vec2 ext = foot * hs * inflate;
    // off screen (most of the map in the tilted view)? skip it before doing any work
    float rb = max(max(ext.x, ext.y), 3.0 * R) * 1.3;
    vec4 q = mvp * vec4(c.xy, R, 1.0);
    float bx = rb * abs(window.projection[0][0]);
    float by = rb * abs(window.projection[1][1]);
    if (q.w < -rb || q.x - bx > q.w || q.x + bx < -q.w || q.y - by > q.w || q.y + by < -q.w) return;
    int sides = q.w > 1100.0 ? max(4, segs / 2) : segs;     // far away: fewer sides
    vec2 uv0, uv1, uv2, uv3;
    getSpriteUVs(uv_texture, int(v_texture[0]), uv0, uv1, uv2, uv3);
    vec2 hp = 0.5 / vec2(textureSize(sprite_texture, 0)) * uv_offset_bias;
    uv0 += hp; uv1 += vec2(-hp.x, hp.y); uv2 += vec2(hp.x, -hp.y); uv3 += -hp;
    vec3 L = normalize(vec3(-sun.x, -sun.y, 1.4));
    bool alt = c.z < alt_below;
    int k0 = alt ? alt_start : 0;
    int k1 = alt ? nrings : alt_start;
    float Rr = R * (foot.x + foot.y) * 0.5 * inflate;    // radial unit for the normals
    float seed = hash(c.xy * 0.173);
    uvec4 c8 = uvec4(clamp(v_color[0], 0.0, 1.0) * 255.0 + 0.5);
    uint rgba = c8.r | (c8.g << 8) | (c8.b << 16) | (c8.a << 24);
    int band = 0;
    for (int k = k0; k < k1 - 1; k++) {
        if (((breaks >> (k + 1)) & 1) == 1) continue;
        if (band++ / band_per != pass_id) continue;
        vec4 r0 = rings[k];
        vec4 r1 = rings[k + 1];
        vec2 n2 = normalize(vec2((r1.y - r0.y) * R, (r0.x - r1.x) * Rr) + vec2(1e-5, 0.0));
        for (int i = 0; i <= sides; i++) {
            float ph = phase + 6.2831853 * float(i) / float(sides);
            vec2 cs = vec2(cos(ph), sin(ph));
            float j = 1.0 + jitter * (hash(vec2(seed, float(i % sides))) - 0.5) * 2.0;
            vec3 n = vec3(rot * cs * n2.x, n2.y);
            float light = 0.66 + 0.48 * max(dot(n, L), 0.0);
            for (int e = 1; e >= 0; e--) {
                vec4 rg = e == 1 ? r1 : r0;
                vec2 lp = cs * rg.x * ext * j;
                float z = rg.y * R * inflate * (1.0 + jitter * 0.4 * (hash(vec2(seed, float(i % sides) + 17.0)) - 0.5));
                if (rg.y <= 0.0) z = 0.0;
                gl_Position = mvp * vec4(c.xy + rot * lp, z, 1.0);
                gs_shade = abs(rg.w) * light;
                gs_rgba = rgba;
                if (rg.w < 0.0) {
                    gs_uv = vec2(-10.0);
                } else {
                    vec2 st = 0.5 + 0.5 * cs * rg.z * foot;
                    gs_uv = mix(mix(uv2, uv3, st.x), mix(uv0, uv1, st.x), st.y);
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
uniform vec3 solid;
in vec2 gs_uv;
in float gs_shade;
flat in uint gs_rgba;
out vec4 f_color;
void main() {
    vec4 col = vec4(uvec4(gs_rgba, gs_rgba >> 8, gs_rgba >> 16, gs_rgba >> 24) & 255u) / 255.0;
    vec3 rgb = solid;
    if (gs_uv.x > -5.0) {
        vec4 t = texture(sprite_texture, gs_uv);
        if (t.a <= alpha_cut) discard;
        rgb = t.rgb;
    }
    f_color = vec4(rgb * col.rgb * gs_shade, col.a) * spritelist_color;
}
"""


def program_sources(lib):
    geo = MESH_GEO.replace("%LIB%", lib).replace("%VERTS%", str(MAX_VERTS)).replace("%MAX%", str(MAX_RINGS))
    return geo, MESH_FS


class Shape:
    """One kind of 3D shape (see the module docstring)."""

    def __init__(self, rings, foot=(0.9, 0.9), segs=8, phase=0.0, solid=(0.5, 0.5, 0.5), jitter=0.0,
                 breaks=(), alt=None, cut=0.2, card_lift=None):
        allr = list(rings) + list(alt or [])
        assert len(allr) <= MAX_RINGS and segs <= 10
        self.nrings = len(allr)
        self.alt_start = len(rings)
        self.alt_below = 1.0 if alt else -1e9      # trees: depth 0 = stump, depth > 0 = standing tree
        flat = []
        for r in allr:
            flat.extend(r)
        flat.extend([0.0] * (4 * MAX_RINGS - len(flat)))
        self.rings = tuple(float(v) for v in flat)
        b = 0
        for k in breaks:
            b |= 1 << k
        if alt:
            b |= 1 << len(rings)
        self.breaks = b
        bands = max(sum(1 for k in range(1, len(rings)) if not b >> k & 1),
                    len(alt or []) - 1 if alt else 0)
        self.band_per = MAX_VERTS // (2 * (segs + 1))
        self.passes = -(-bands // self.band_per)
        self.foot = tuple(map(float, foot))
        self.segs = segs
        self.phase = float(phase)
        self.solid = tuple(c / 255 for c in solid)
        self.jitter = float(jitter)
        self.cut = cut
        self.card_lift = card_lift      # also stand the picture up on top, this many R high


Q = math.pi / 4          # turns 4 sides into a box lined up with the sprite
BOX = 1.3                # 4-sided footprint scale so the box corners reach the picture's corners
BOXPIC = 0.74            # ...and the picture radius that keeps them inside it

_ROCK = [(1.0, 0.0, 0.8, 0.72), (1.04, 0.32, 0.78, 0.88), (0.78, 0.8, 0.6, 1.0), (0.36, 1.08, 0.28, 1.06),
         (0.0, 1.16, 0.0, 1.08)]

SHAPES = {
    "rock": Shape(_ROCK, foot=(0.88, 0.86), segs=7, phase=0.3, jitter=0.2, cut=0.25),
    "crystal": Shape([(1.0, 0.0, 0.8, 0.75), (0.92, 0.55, 0.75, 0.95), (0.5, 1.45, 0.5, 1.15), (0.0, 2.05, 0.0, 1.3)],
                     foot=(0.85, 0.85), segs=5, phase=0.5, jitter=0.3, cut=0.2),
    "bush": Shape([(0.55, 0.0, 0.3, 0.6), (0.95, 0.42, 0.62, 0.85), (1.0, 0.88, 0.9, 0.95), (0.8, 1.32, 0.64, 1.0),
                   (0.45, 1.62, 0.34, 1.05), (0.0, 1.72, 0.0, 1.08)], foot=(0.86, 0.86), segs=9, jitter=0.12, cut=0.3),
    # trunk (plain bark colour), then the canopy in two tiers; the alt rings are the stump left after chopping
    "tree": Shape([(0.15, 0.0, 0, -0.75), (0.1, 1.6, 0, -1.0),
                   (0.45, 1.28, 0.45, 0.85), (0.95, 1.55, 0.9, 0.92), (1.0, 1.85, 0.97, 0.92), (0.62, 2.12, 0.62, 1.0),
                   (0.42, 1.95, 0.42, 0.85), (0.74, 2.2, 0.74, 0.95), (0.55, 2.62, 0.55, 1.05), (0.0, 2.85, 0.0, 1.12)],
                  foot=(0.9, 0.9), segs=8, solid=(104, 72, 44), breaks=(2, 6), cut=0.3,
                  alt=[(0.82, 0.0, 0.8, 0.6), (0.76, 0.45, 0.78, 0.85), (0.6, 0.55, 0.62, 1.0), (0.0, 0.55, 0.0, 1.0)]),
    "campfire": Shape([(1.0, 0.0, 0.98, 0.7), (1.0, 0.12, 0.98, 0.9), (0.78, 0.2, 0.78, 1.0), (0.0, 0.12, 0.0, 1.0),
                       (0.42, 0.06, 0, -0.8), (0.0, 1.0, 0, -1.0)],
                      foot=(0.92, 0.92), segs=10, solid=(110, 70, 40), breaks=(4,), cut=0.25),
    "brazier": Shape([(0.38, 0.0, 0, -0.5), (0.18, 0.9, 0, -0.7),
                      (0.22, 0.88, 0.25, 0.6), (1.0, 1.38, 0.98, 0.85), (0.9, 1.48, 0.9, 1.0), (0.0, 1.38, 0.0, 0.8)],
                     foot=(0.86, 0.86), segs=10, solid=(62, 60, 64), breaks=(2,), cut=0.2),
    "workbench": Shape([(0.8, 0.0, 0, -0.6), (0.8, 0.9, 0, -0.75),
                        (1.0, 0.88, BOXPIC, 0.75), (1.0, 1.2, BOXPIC, 0.9), (0.0, 1.2, 0.0, 1.0)],
                       foot=(BOX * 0.95, BOX * 0.9), segs=4, phase=Q, solid=(96, 64, 38), breaks=(2,), cut=0.1),
    "storage": Shape([(1.0, 0.0, BOXPIC, 0.7), (1.0, 0.95, BOXPIC, 0.88), (0.92, 1.08, BOXPIC * 0.92, 1.0),
                      (0.0, 1.08, 0.0, 1.0)], foot=(BOX * 0.92, BOX * 0.88), segs=4, phase=Q, cut=0.1),
    "arrow_turret": Shape([(0.78, 0.0, 0, -0.7), (0.72, 0.62, 0, -0.95), (0.84, 0.62, 0, -0.85),
                           (0.84, 0.8, 0, -1.05), (0.0, 0.8, 0, -1.1)],
                          foot=(0.9, 0.9), segs=8, phase=0.39, solid=(132, 130, 128), card_lift=0.8),
    "hut": Shape([(1.0, 0.0, 0, -0.65), (1.0, 0.85, 0, -0.95),
                  (1.1, 0.8, BOXPIC, 0.95), (0.0, 1.55, 0.0, 1.12)],
                 foot=(BOX, BOX), segs=4, phase=Q, solid=(124, 88, 54), breaks=(2,), cut=0.1),
    # first person only: living things
    "body": Shape([(0.62, 0.0, 0.6, 0.45), (0.62, 0.14, 0.6, 0.55), (0.92, 0.34, 0.9, 0.8), (1.0, 0.62, 0.98, 0.95),
                   (0.76, 0.88, 0.72, 1.02), (0.0, 0.98, 0.0, 1.06)], foot=(0.8, 0.42), segs=8, cut=0.15),
    "boss": Shape([(0.6, 0.0, 0.55, 0.5), (0.9, 0.55, 0.85, 0.75), (1.0, 1.1, 0.98, 0.95), (0.78, 1.6, 0.72, 1.02),
                   (0.0, 1.8, 0.0, 1.06)], foot=(0.78, 0.7), segs=10, cut=0.15),
    # a peg person: legs, body, shoulders, neck and a round head (the top of the picture is the head)
    "person": Shape([(0.5, 0.0, 0.5, 0.45), (0.58, 1.1, 0.52, 0.6), (0.92, 1.25, 0.62, 0.8), (1.0, 1.85, 0.68, 0.95),
                     (0.82, 2.08, 0.6, 1.0), (0.32, 2.14, 0.26, 0.9), (0.56, 2.24, 0.32, 1.0), (0.62, 2.44, 0.34, 1.05),
                     (0.42, 2.64, 0.24, 1.08), (0.0, 2.72, 0.0, 1.1)], foot=(0.55, 0.55), segs=6, cut=0.15),
}
SHAPES["iron"] = SHAPES["coal"] = SHAPES["rock"]

# extra height for the flame of a fire that sits on a 3D shape (in sprite pixels, like sprite.depth)
FLAME_DEPTH = {"brazier": 19}
