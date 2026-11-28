"""
ground3d.py - painterly detail on the 3D ground, and the small "ground map" textures it (and grass3d.py) read.

The ground tiles are painted 256 px pictures, so from the 3D camera the land read as one flat green with the
same tufts repeating every tile. This file adds detail made from the WORLD position in the ground's fragment
shader, so it costs no memory and nothing is built per frame:

  * big soft colour patches (lusher and drier grass, moss), soft dirt / earth patches, pebbles, flowers
    specks in the meadow, leaf litter under the trees (more in autumn);
  * bare soil and rock on steep slopes (the hills of hills.py), with layered strata;
  * per biome: snow drifts with blue hollows and glints in the tundra, ash drifts and glowing ember cracks
    in the Ashlands, dark wet mud with shiny puddles in the Mire, heather and scree in the Highlands;
  * a second, turned copy of the tile's own picture blended in by patches, so the 256 px grid no longer shows;
  * a little bump from noise for the sun to catch;
  * underground (cave floors, the Hollows): rocky detail - cracks, grit, damp patches, rare mineral glints.

How it plugs in: terrain3d.Terrain3D._hill_init builds the ground program with geometry() / fragment() below.
The same program now also draws the FLAT ground (old worlds, the cave, every underground layer) with the hill
lookup switched off, so they all get their detail from one shader.

The ground map (GroundMap, one per world, rebuilt only when the world or the buildings change):
  gm_bio  RGBA8 on the hills grid (64 px):   tundra, ash, mire, highlands share   (forest = what's left)
  gm_aux  RGBA8 on the hills grid:          meadow share, tree cover, near water, 0
  gm_mask R8   on terrain_map's 20 px grid: where grass may grow (0 on water, roads, cliffs, bridges, ponds,
                                             bog pools, cave mouths, worn ground and under every building)

WETNESS (rain - another module adds it): the end of GROUND_FS builds a `Surf` (colour, normal, gloss) and
shades it in ground_finish(). A wetness term goes right before ground_finish: darken s.alb a little and
raise s.gloss (the Mire's puddles already do exactly that with their own `wet` amount).
"""
import math

import hills

BIO_UNIT, AUX_UNIT, MASK_UNIT = 3, 4, 5        # texture units (0-2: sprites + hills, 6: sun shadows)
MASK_CELL = 20                                  # px per grass-mask texel (terrain_map.C)

# ---------------------------------------------------------------- shared GLSL (ground, grass, ambient life)
NOISE = """
float gh(vec2 p) {          // a hash that stays steady for big world coordinates
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
vec2 gh2(vec2 p) { return vec2(gh(p), gh(p + 17.31)); }
float gnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(gh(i), gh(i + vec2(1.0, 0.0)), f.x), mix(gh(i + vec2(0.0, 1.0)), gh(i + vec2(1.0, 1.0)), f.x), f.y);
}
float gfbm(vec2 p) { return gnoise(p) * 0.6 + gnoise(p * 2.07 + 5.3) * 0.28 + gnoise(p * 4.13 + 1.7) * 0.12; }
"""

MAP = """
uniform sampler2D gm_bio;
uniform sampler2D gm_aux;
uniform sampler2D gm_mask;
uniform int gm_on;          // 1 = the surface's ground map is bound
uniform vec3 gm_map;        // hills grid: origin, 1 / cell, 1 / grid points
uniform vec2 gm_mask_map;   // grass mask: 1 / cell, 1 / texels
vec2 gm_uv(vec2 p) { return ((p - vec2(gm_map.x)) * gm_map.y + 0.5) * gm_map.z; }
// biome shares at p: (forest, meadow, tundra, ash) and (mire, highlands, tree cover, near water)
void gm_biomes(vec2 p, out vec4 a, out vec4 b) {
    if (gm_on == 0) { a = vec4(1.0, 0.0, 0.0, 0.0); b = vec4(0.0); return; }
    vec4 t = texture(gm_bio, gm_uv(p));
    vec4 x = texture(gm_aux, gm_uv(p));
    float forest = clamp(1.0 - t.r - t.g - t.b - t.a - x.r, 0.0, 1.0);
    a = vec4(forest, x.r, t.r, t.g);
    b = vec4(t.b, t.a, x.g, x.b);
}
float gm_grass_mask(vec2 p) {
    if (gm_on == 0) return 1.0;
    return texture(gm_mask, p * gm_mask_map.x * gm_mask_map.y).r;
}
"""

# ---------------------------------------------------------------- the ground program
GEO_OUT = """out vec4 gs_color;
out vec3 gs_pos;
out vec3 gs_nrm;
flat out vec4 gs_uva;
flat out vec4 gs_uvb;
flat out float gs_tile;"""


def geometry(src):
    """terrain3d.GROUND_GEO -> the same heightfield, also handing the fragment shader the world position, the
    normal, the tile's picture corners and its size; and exactly flat when the hills are off (old worlds,
    underground), so the flat ground can use it too."""
    src = src.replace("out vec4 gs_color;", GEO_OUT)
    src = src.replace("vec3 hg = textureLod(", "vec3 hg = hill_on == 0 ? vec3(0.0) : textureLod(")
    src = src.replace("gl_Position = mvp * vec4(p, z, 1.0);",
                      "gs_pos = vec3(p, z); gs_nrm = n; gs_uva = vec4(uv0, uv1); gs_uvb = vec4(uv2, uv3); "
                      "gs_tile = v_size[0].x; gl_Position = mvp * vec4(p, z, 1.0);")
    return src


GROUND_FS = """
#version 330
uniform sampler2D sprite_texture;
uniform vec4 spritelist_color;
uniform int g_under;        // 1 = underground: a rock floor
uniform int g_detail;       // 0 = cheap (slow machines: the grass option is Off), 1 = everything
uniform float g_time;
uniform float g_autumn;     // 0..1 how autumnal (more fallen leaves, drier grass)
uniform float g_winter;     // 0..1
in vec2 gs_uv;
in vec4 gs_color;
in vec3 gs_pos;
in vec3 gs_nrm;
flat in vec4 gs_uva;
flat in vec4 gs_uvb;
flat in float gs_tile;
out vec4 f_color;
%NOISE%
%MAP%
struct Surf { vec3 alb; vec3 n; float gloss; vec3 glow; };

// the tile's own picture at q (0..1 across the tile)
vec3 tile_at(vec2 q) {
    vec2 uv = mix(mix(gs_uvb.xy, gs_uvb.zw, q.x), mix(gs_uva.xy, gs_uva.zw, q.x), q.y);
    return textureLod(sprite_texture, uv, 0.0).rgb;
}
// a small round thing (pebble, leaf, flower) in a jittered grid of `cell` px: returns (inside 0..1,
// its own random 0..1, offset from its centre x, y in its radius units)
vec4 speck(vec2 p, float cell, float chance, float rad, float stretch) {
    vec2 c = floor(p / cell);
    vec2 h = gh2(c + 3.1);
    if (h.x > chance) return vec4(0.0);
    vec2 ctr = (c + 0.2 + 0.6 * h) * cell;
    float a = h.y * 6.2831;
    vec2 d = mat2(cos(a), -sin(a), sin(a), cos(a)) * (p - ctr);
    float r = rad * (0.6 + 0.8 * fract(h.x * 13.7 + h.y));
    d /= vec2(r * stretch, r);
    float k = 1.0 - smoothstep(0.75, 1.0, length(d));
    return vec4(k, fract(h.y * 7.3 + h.x * 3.1), d);
}
float W(vec4 a, vec4 b, vec4 va, vec2 vb) { return dot(a, va) + dot(b.xy, vb); }
vec3 W3(vec4 a, vec4 b, vec3 f, vec3 m, vec3 t, vec3 s, vec3 mi, vec3 h) {
    return f * a.x + m * a.y + t * a.z + s * a.w + mi * b.x + h * b.y;
}

// ---- the final step: light the surface (the ground stage: the light map does the night later)
vec4 ground_finish(Surf s, vec3 p, float alpha) {
    s.alb = lt_weather(s.alb, p, s.n, 1.0);        // weather3d.py: soaked / puddles in the rain, snow cover in winter
    vec3 L = lt_sun.xyz;
    float bump = 1.0 + 0.9 * (dot(s.n, L) - dot(normalize(gs_nrm), L));     // detail bumps catch the sun
    vec3 V = normalize(lt_eye.xyz - p);
    float spec = pow(max(dot(reflect(-L, s.n), V), 0.0), 24.0) * s.gloss;
    float sun = lt_sunlit(p, lt_face(p));
    vec3 rgb = s.alb * bump + spec * vec3(0.9, 0.92, 0.85) * sun;
    rgb = rgb * lt_light(p, vec3(0.0)) * sun + s.glow;
    return vec4(lt_fogged(rgb, p), alpha);
}

void main() {
    vec3 p = gs_pos;
    vec4 t = texture(sprite_texture, gs_uv);
    if (t.a <= 0.0) discard;
    vec3 tint = gs_color.rgb * spritelist_color.rgb;
    Surf s;
    s.alb = t.rgb * tint;
    s.n = normalize(gs_nrm);
    s.gloss = 0.0;
    s.glow = vec3(0.0);
    vec2 q = p.xy;
    float px = length(fwidth(q));                 // world px per screen pixel (fades the fine detail)
    float fine = g_detail == 1 ? 1.0 - smoothstep(1.2, 3.2, px) : 0.0;
    bool tile = gs_tile > 250.0 || g_under == 1;  // real ground tiles (not the Mire's bog pool pictures)
    if (!tile || t.a < 0.99) { f_color = ground_finish(s, p, t.a * gs_color.a * spritelist_color.a); return; }

    float n1 = gfbm(q / 520.0 + 3.0);             // big patches
    float n2 = gfbm(q / 150.0 + 11.0);            // medium patches
    float n3 = gnoise(q / 23.0);                  // grain
    // ---- break up the 256 px tiling: in patches, the tile's picture turned and shifted
    float ts = g_under == 1 ? gs_tile : 256.0;
    vec2 q2 = fract(mat2(0.8, -0.6, 0.6, 0.8) * q / ts + vec2(0.37, 0.61));
    float mb = smoothstep(0.44, 0.56, gnoise(q / 310.0 + 7.0));
    if (mb > 0.0) s.alb = mix(s.alb, tile_at(q2) * tint, mb);

    if (g_under == 1) {
        // ---- a rock floor: lumpy tone, cracks, damp patches, grit and the odd mineral glint
        float crack = smoothstep(0.03, 0.0, abs(gnoise(q / 38.0 + 2.0) - 0.5)) * smoothstep(0.35, 0.6, n2);
        s.alb *= 0.8 + 0.4 * n2 + 0.12 * (n3 - 0.5);
        s.alb = mix(s.alb, s.alb * vec3(0.62, 0.64, 0.7), smoothstep(0.55, 0.72, n1) * 0.7);   // damp
        s.gloss = smoothstep(0.6, 0.75, n1) * 0.35;
        s.alb *= 1.0 - 0.5 * crack;
        if (fine > 0.0) {
            vec4 g = speck(q, 13.0, 0.3, 2.4, 1.3);
            vec3 pc = s.alb * (1.05 + 0.4 * g.y);         // grit: a shade lighter than the rock around it
            float lit = 0.85 + 0.35 * clamp(-dot(g.zw, lt_sun.xy), -1.0, 1.0);
            s.alb = mix(s.alb, pc * lit, g.x * fine * 0.8);
            vec4 m = speck(q + 5.0, 23.0, 0.05, 1.2, 1.0);
            s.glow += vec3(0.5, 0.75, 0.9) * m.x * fine * (0.5 + 0.5 * sin(g_time * 2.0 + m.y * 40.0)) * 0.35;
        }
        f_color = ground_finish(s, p, t.a);
        return;
    }

    vec4 ba, bb;
    gm_biomes(q + (vec2(n2, gnoise(q / 150.0 + 4.0)) - 0.5) * 90.0, ba, bb);     // wobbly, soft borders
    float forest = ba.x, meadow = ba.y, snow = ba.z, ash = ba.w, mire = bb.x, high = bb.y;
    float grassy = clamp(forest + meadow + mire * 0.6 + high * 0.6, 0.0, 1.0);

    // ---- big colour patches: lusher and drier grass (drier in autumn), and moss in the woods / Mire
    float dry = smoothstep(0.5, 0.78, n1 + 0.18 * g_autumn) * (0.55 + 0.35 * g_autumn);
    float lush = smoothstep(0.45, 0.2, n1);
    vec3 dryc = W3(ba, bb, vec3(1.1, 1.0, 0.7), vec3(1.15, 1.06, 0.68), vec3(1.0), vec3(1.0), vec3(1.05, 0.98, 0.78),
                   vec3(1.12, 0.98, 0.78));
    vec3 lushc = W3(ba, bb, vec3(0.78, 0.96, 0.74), vec3(0.84, 1.03, 0.8), vec3(1.0), vec3(1.0), vec3(0.8, 0.9, 0.7),
                    vec3(0.86, 0.95, 0.8));
    s.alb *= mix(vec3(1.0), dryc, dry * grassy) * mix(vec3(1.0), lushc, lush * grassy);
    s.alb *= 0.9 + 0.2 * n2 + 0.08 * (n3 - 0.5);
    float moss = smoothstep(0.58, 0.72, n2) * (forest * 0.5 + mire * 0.6) * (1.0 - dry);
    s.alb = mix(s.alb, vec3(0.2, 0.32, 0.12) * (0.85 + 0.3 * n3), moss);

    // ---- heather in the Highlands: purple-brown patches
    float heather = smoothstep(0.55, 0.68, gnoise(q / 90.0 + 9.0) * 0.7 + n1 * 0.3) * high;
    s.alb = mix(s.alb, vec3(0.42, 0.3, 0.38) * (0.8 + 0.4 * n3), heather * 0.45);

    // ---- dirt / earth patches with soft, grainy edges
    vec3 dirtc = W3(ba, bb, vec3(0.38, 0.29, 0.19), vec3(0.5, 0.4, 0.26), vec3(0.62, 0.63, 0.66), vec3(0.17, 0.15, 0.14),
                    vec3(0.24, 0.21, 0.14), vec3(0.46, 0.4, 0.31));
    float dirt_amt = W(ba, bb, vec4(0.8, 0.45, 0.0, 0.9), vec2(1.0, 0.9));
    float dn = gfbm(q / 120.0 + 31.0) + 0.14 * (n3 - 0.5);
    float dirt = smoothstep(0.64, 0.7, dn) * dirt_amt;
    s.alb = mix(s.alb, dirtc * (0.85 + 0.3 * n3), dirt * 0.85);

    // ---- steep slopes: soil, then layered rock
    float slope = 1.0 - s.n.z;
    float soil = smoothstep(0.05, 0.13, slope + 0.05 * (n2 - 0.5)) * (1.0 - snow * 0.5);
    float rock = smoothstep(0.11, 0.2, slope + 0.07 * (n3 - 0.5));
    vec3 rockc = W3(ba, bb, vec3(0.46, 0.44, 0.41), vec3(0.55, 0.52, 0.47), vec3(0.44, 0.46, 0.52), vec3(0.28, 0.25, 0.24),
                    vec3(0.34, 0.33, 0.28), vec3(0.52, 0.5, 0.48));
    float strata = 0.86 + 0.18 * sin(p.z * 0.22 + n2 * 9.0) + 0.12 * (n3 - 0.5);
    s.alb = mix(s.alb, dirtc * (0.9 + 0.2 * n3), soil * 0.7);
    s.alb = mix(s.alb, rockc * strata, rock * 0.9);

    // ---- the tundra: snow drifts in wind ripples, blue hollows, glints
    if (snow > 0.01) {
        float rip = 0.5 + 0.5 * sin(dot(q, vec2(0.05, 0.02)) + gfbm(q / 80.0) * 6.0);
        vec3 sn = mix(vec3(0.8, 0.86, 0.98), vec3(1.02, 1.02, 1.04), clamp(n2 * 0.7 + rip * 0.3, 0.0, 1.0));
        s.alb = mix(s.alb, s.alb * sn, snow * (1.0 - rock * 0.6));
        if (fine > 0.0) {
            vec4 gl = speck(q, 7.0, 0.22, 0.9, 1.0);
            float tw = pow(max(sin(g_time * 1.7 + gl.y * 60.0 + dot(lt_eye.xy, vec2(0.02, 0.013))), 0.0), 12.0);
            s.glow += vec3(0.95, 0.98, 1.0) * gl.x * tw * snow * fine * 0.55 * (1.0 - rock);
        }
    }
    // ---- the Ashlands: pale ash drifts, cinder, glowing ember cracks
    if (ash > 0.01) {
        float drift = smoothstep(0.5, 0.75, gfbm(q / 70.0 + 13.0));
        s.alb = mix(s.alb, vec3(0.5, 0.48, 0.47) * (0.85 + 0.3 * n3), drift * ash * 0.55);
        float cr = smoothstep(0.022, 0.0, abs(gnoise(q / 46.0 + 8.0) - 0.5)) * smoothstep(0.5, 0.68, n2);
        float pulse = 0.65 + 0.35 * sin(g_time * 1.3 + n1 * 20.0);
        s.alb = mix(s.alb, vec3(0.1, 0.07, 0.06), cr * ash * 0.7);
        s.glow += vec3(1.0, 0.36, 0.08) * cr * ash * pulse * 0.45;
    }
    // ---- the Mire: dark wet mud, shiny puddles
    float wet = 0.0;
    if (mire > 0.01) {
        float mf = gfbm(q / 95.0 + 21.0);
        float mud = smoothstep(0.52, 0.64, mf);
        s.alb = mix(s.alb, vec3(0.2, 0.18, 0.12) * (0.85 + 0.3 * n3), mud * mire * 0.75);
        wet = smoothstep(0.66, 0.72, mf + 0.06 * (n3 - 0.5)) * mire;
    }
    // (WETNESS: a rain term would add to `wet` here)
    s.alb *= 1.0 - 0.35 * wet;
    s.gloss = max(s.gloss, wet * 0.6);

    if (fine > 0.0) {
        // ---- pebbles: a lit top towards the sun and a soft shadow on the far side
        float peb = W(ba, bb, vec4(0.08, 0.06, 0.03, 0.12), vec2(0.04, 0.28)) + rock * 0.35 + dirt * 0.3;
        vec4 g = speck(q, 17.0, peb, 2.6, 1.35);
        if (g.x > 0.0) {
            vec3 pc = mix(rockc * 1.25, vec3(0.62, 0.6, 0.57), 0.5) * (0.78 + 0.4 * g.y);
            float lit = 0.8 + 0.45 * clamp(dot(g.zw, -lt_sun.xy) * 1.5, -1.0, 1.0);
            s.alb = mix(s.alb, pc * lit, g.x * fine);
        }
        vec4 sh = speck(q - lt_sun.xy * 1.4, 17.0, peb, 2.6, 1.35);
        s.alb *= 1.0 - 0.3 * sh.x * (1.0 - g.x) * fine;
        // ---- leaf litter under the trees (most in autumn)
        float lit_amt = bb.z * (0.35 + 0.65 * g_autumn) * (1.0 - snow) * (1.0 - ash) * (1.0 - rock);
        vec4 lf = speck(q + 3.0, 9.0, lit_amt * 0.55, 2.2, 1.9);
        if (lf.x > 0.0) {
            vec3 lc = lf.y < 0.33 ? vec3(0.62, 0.36, 0.14) : lf.y < 0.66 ? vec3(0.72, 0.56, 0.2) : vec3(0.46, 0.3, 0.16);
            lc = mix(lc, vec3(0.34, 0.44, 0.18), (1.0 - g_autumn) * 0.5);
            s.alb = mix(s.alb, lc * (0.85 + 0.3 * n3), lf.x * fine * 0.9);
        }
        // ---- tiny flowers in the meadow grass (not in winter)
        float fl = meadow * (1.0 - g_winter) * (1.0 - dirt) * (1.0 - rock) * 0.1;
        vec4 fw = speck(q + 7.0, 8.0, fl, 0.9, 1.0);
        if (fw.x > 0.0) {
            vec3 fc = fw.y < 0.4 ? vec3(1.0, 0.97, 0.85) : fw.y < 0.7 ? vec3(1.0, 0.85, 0.3) : vec3(0.78, 0.6, 0.95);
            s.alb = mix(s.alb, fc, fw.x * fine * 0.85);
        }
        // ---- the detail bump: grain for the sun to catch (stronger on bare ground)
        float e = 1.5;
        float bk = 0.35 + 0.65 * max(max(dirt, rock), max(snow, ash));
        float b0 = gnoise(q / 6.0), bx = gnoise((q + vec2(e, 0.0)) / 6.0), by = gnoise((q + vec2(0.0, e)) / 6.0);
        s.n = normalize(s.n + vec3(b0 - bx, b0 - by, 0.0) * 0.5 * bk * fine);
    }
    f_color = ground_finish(s, p, t.a * gs_color.a * spritelist_color.a);
}
"""


def fragment(lib):
    """The ground's fragment shader with the lighting library (lighting3d.glsl(frag=True)) pasted in."""
    src = GROUND_FS.replace("%NOISE%", NOISE).replace("%MAP%", MAP)
    at = src.index("\n", src.index("#version")) + 1
    return src[:at] + lib + src[at:]


# ---------------------------------------------------------------- the ground map (CPU, once per world)
def _blur3(v, n):
    """1-2-1 blur on an n x n grid (edges clamped) - softens biome borders to about two cells."""
    out = [0.0] * (n * n)
    for j in range(n):
        r = j * n
        for i in range(n):
            out[r + i] = (v[r + max(i - 1, 0)] + 2 * v[r + i] + v[r + min(i + 1, n - 1)]) * 0.25
    res = [0.0] * (n * n)
    for j in range(n):
        r0, r1 = max(j - 1, 0) * n, min(j + 1, n - 1) * n
        for i in range(n):
            res[j * n + i] = (out[r0 + i] + 2 * out[j * n + i] + out[r1 + i]) * 0.25
    return res


class GroundMap:
    """The three ground-map textures of one world's surface (see the module docstring)."""

    def __init__(self, game, ctx):
        self.game, self.ctx = game, ctx
        over = game.layers["over"]
        size = game.world_size
        self.n = n = int(math.ceil(((size // 256 + 1) * 256 + 128 - hills.ORIGIN) / hills.CELL)) + 1
        lay = game.layout
        names = ("tundra", "ash", "mire", "highlands", "meadow")
        ch = {k: [0.0] * (n * n) for k in names}
        for j in range(n):
            y = hills.ORIGIN + j * hills.CELL
            for i in range(n):
                b = lay.biome_at(hills.ORIGIN + i * hills.CELL, y)
                if b in ch:
                    ch[b][j * n + i] = 1.0
        for k in names:
            if any(ch[k]):
                ch[k] = _blur3(_blur3(ch[k], n), n)
        trees = [0.0] * (n * n)
        for t in over.trees:
            if getattr(t, "kind", "") != "tree":
                continue
            fi, fj = (t.center_x - hills.ORIGIN) / hills.CELL, (t.center_y - hills.ORIGIN) / hills.CELL
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    i, j = int(round(fi)) + di, int(round(fj)) + dj
                    if 0 <= i < n and 0 <= j < n:
                        d = math.hypot(i - fi, j - fj)
                        trees[j * n + i] += max(0.0, 1.0 - d / 1.8) * 0.8
        water = self._water_near(n)
        clamp8 = lambda v: max(0, min(255, int(v * 255 + 0.5)))
        bio, aux = bytearray(4 * n * n), bytearray(4 * n * n)
        for k in range(n * n):
            bio[4 * k:4 * k + 4] = bytes((clamp8(ch["tundra"][k]), clamp8(ch["ash"][k]), clamp8(ch["mire"][k]),
                                          clamp8(ch["highlands"][k])))
            aux[4 * k:4 * k + 3] = bytes((clamp8(ch["meadow"][k]), clamp8(trees[k]), clamp8(water[k])))
        lin = (ctx.LINEAR, ctx.LINEAR)
        cl = dict(wrap_x=ctx.CLAMP_TO_EDGE, wrap_y=ctx.CLAMP_TO_EDGE)
        self.bio = ctx.texture((n, n), components=4, data=bytes(bio), filter=lin, **cl)
        self.aux = ctx.texture((n, n), components=4, data=bytes(aux), filter=lin, **cl)
        self.biome_shares = ch          # also read on the CPU (ambient3d.py)
        self.trees = trees
        self.water = water
        # the grass mask
        self.mn = mn = int(math.ceil(size / MASK_CELL)) + 2
        self._mask_base = self._static_mask(mn)
        self.mask = ctx.texture((mn, mn), components=1, data=bytes(self._mask_base), filter=lin, **cl)
        self.mask_key = None

    def at(self, chan, x, y):
        """A ground-map value at (x, y) on the CPU: chan "trees", "water" or a biome name (nearest grid point)."""
        n = self.n
        i = min(n - 1, max(0, int(round((x - hills.ORIGIN) / hills.CELL))))
        j = min(n - 1, max(0, int(round((y - hills.ORIGIN) / hills.CELL))))
        v = self.trees if chan == "trees" else self.water if chan == "water" else self.biome_shares.get(chan)
        return min(1.0, v[j * n + i]) if v else 0.0

    def _water_near(self, n):
        """0..1 how near water each grid point is (rivers / lakes, ponds, the Mire's bog pools)."""
        g = self.game
        out = [0.0] * (n * n)
        try:
            import terrain_map as TM
            m = TM.get(g.layout)
        except Exception:       # noqa: BLE001
            m = None
        if m is not None:
            for j in range(n):
                y = hills.ORIGIN + j * hills.CELL
                for i in range(n):
                    e = m.edge_at(hills.ORIGIN + i * hills.CELL, y)
                    if e < 1e8:
                        out[j * n + i] = max(0.0, min(1.0, 1.0 - (e - 20.0) / 220.0))
        pools = [(s.center_x, s.center_y, max(s.width, s.height) / 2) for s in g.layers["over"].ponds]
        pools += [(x, y, r) for x, y, r, _ in getattr(g, "swamp_pools", ())]
        for x, y, r in pools:
            reach = r + 220.0
            i0, i1 = int((x - reach - hills.ORIGIN) // hills.CELL), int((x + reach - hills.ORIGIN) // hills.CELL) + 1
            j0, j1 = int((y - reach - hills.ORIGIN) // hills.CELL), int((y + reach - hills.ORIGIN) // hills.CELL) + 1
            for j in range(max(0, j0), min(n, j1 + 1)):
                for i in range(max(0, i0), min(n, i1 + 1)):
                    d = math.hypot(hills.ORIGIN + i * hills.CELL - x, hills.ORIGIN + j * hills.CELL - y) - r
                    k = j * n + i
                    out[k] = max(out[k], min(1.0, 1.0 - d / 220.0))
        return out

    # ---- grass mask
    def _static_mask(self, mn):
        """Where grass may grow, from things that never change: rivers, roads, cliffs, ponds, bog pools,
        cave mouths."""
        g = self.game
        mask = bytearray(b"\xff" * (mn * mn))
        try:
            import terrain_map as TM
            m = TM.get(g.layout)
        except Exception:       # noqa: BLE001
            m = None
        if m is not None and TM.C == MASK_CELL:
            stop = TM.WATER | TM.ROAD | TM.CLIFF | TM.BRIDGE | TM.FORD
            table = bytes(0 if f & stop else 255 for f in range(256))
            flags = bytes(m.flags).translate(table)
            for j in range(min(mn, m.N)):
                mask[j * mn:j * mn + min(mn, m.N)] = flags[j * m.N:j * m.N + min(mn, m.N)]
        over = g.layers["over"]
        for s in list(over.ponds) + list(over.exits):
            self._clear(mask, mn, s.center_x, s.center_y, max(s.width, s.height) * 0.5 + 6, round_=True)
        for x, y, r, _ in getattr(g, "swamp_pools", ()):
            self._clear(mask, mn, x, y, r + 8, round_=True)
        return mask

    @staticmethod
    def _clear(mask, mn, x, y, r, round_=False, ry=None, val=0):
        ry = r if ry is None else ry
        C = MASK_CELL
        i0, i1 = int((x - r) // C), int((x + r) // C)
        j0, j1 = int((y - ry) // C), int((y + ry) // C)
        for j in range(max(0, j0), min(mn, j1 + 1)):
            for i in range(max(0, i0), min(mn, i1 + 1)):
                if round_ and math.hypot((i + 0.5) * C - x, (j + 0.5) * C - y) > r + C * 0.5:
                    continue
                k = j * mn + i
                if mask[k] > val:
                    mask[k] = val

    def update_mask(self):
        """Clear the grass under buildings and on worn ground (only when they changed)."""
        g = self.game
        over = g.layers["over"]
        worn = {}
        tr = getattr(g, "_terrain", None)
        if tr is not None:
            worn = tr.stage
        key = (getattr(g, "struct_ver", 0), len(over.builds), len(over.huts), len(worn), sum(worn.values()))
        if key == self.mask_key:
            return
        self.mask_key = key
        mn = self.mn
        mask = bytearray(self._mask_base)
        for s in list(over.builds) + list(over.huts):
            self._clear(mask, mn, s.center_x, s.center_y, s.width / 2 + 4, ry=s.height / 2 + 4)
        if worn:
            cell = 48
            for (cx, cy), st in worn.items():
                if st > 0:
                    self._clear(mask, mn, (cx + 0.5) * cell, (cy + 0.5) * cell, cell * 0.45, round_=True,
                                val=(150, 60, 0)[min(3, st) - 1])
        self.mask.write(bytes(mask))
        self._mask_now = mask

    def mask_at(self, x, y):
        """0..1: may grass grow at (x, y)? (the CPU copy of the grass mask)"""
        m = getattr(self, "_mask_now", None) or self._mask_base
        i, j = int(x // MASK_CELL), int(y // MASK_CELL)
        if 0 <= i < self.mn and 0 <= j < self.mn:
            return m[j * self.mn + i] / 255.0
        return 0.0

    def bind(self):
        self.bio.use(BIO_UNIT)
        self.aux.use(AUX_UNIT)
        self.mask.use(MASK_UNIT)

    def uniforms(self):
        return {"gm_map": (hills.ORIGIN, 1.0 / hills.CELL, 1.0 / self.n),
                "gm_mask_map": (1.0 / MASK_CELL, 1.0 / self.mn)}


def ground_map(game):
    """The GroundMap of the game's current world (built on first use, None if there's no world yet)."""
    if not hasattr(game, "layers") or "over" not in game.layers or not hasattr(game, "layout"):
        return None
    key = (getattr(game, "seed", None), id(game.layers["over"]))
    gm = game.__dict__.get("_ground_map")
    if gm is None or gm[0] != key:
        if gm is not None:
            for t in (gm[1].bio, gm[1].aux, gm[1].mask):
                t.delete()
        gm = game._ground_map = (key, GroundMap(game, game.ctx))
    gm[1].update_mask()
    return gm[1]


def apply(prog, gm, on):
    """Point a program's ground-map samplers at their units and give it the map's placement."""
    try:
        prog["gm_bio"] = BIO_UNIT
        prog["gm_aux"] = AUX_UNIT
        prog["gm_mask"] = MASK_UNIT
    except KeyError:
        pass
    prog.set_uniform_safe("gm_on", int(bool(on and gm is not None)))
    if gm is not None:
        for k, v in gm.uniforms().items():
            prog.set_uniform_safe(k, v)


def season_k(game):
    """(autumn, winter) 0..1 for the shaders."""
    s = getattr(game, "season", "spring") if hasattr(game, "day") else "spring"
    return (1.0 if s == "autumn" else 0.0), (1.0 if s == "winter" else 0.0)

