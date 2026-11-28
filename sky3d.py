"""
sky3d.py - the sky and the far-away land around the map, for the 3D view. Mixed into View3D.

Two things, both cheap:

  * THE SKY (first person on the surface only - the tilted camera looks down and never sees it, and
    underground layers have a ceiling, not a sky). One full-screen pass, drawn after everything that stands
    up, only where nothing was drawn (the depth buffer is still "far away" there). Per pixel it works out
    which way that pixel looks (lighting3d's inverse camera matrix) and paints:
      - a gradient from the horizon up to the zenith, by the time of day (warm dawn, blue day, golden hour,
        orange / purple dusk, deep blue night). The colour right at the horizon is exactly the colour the
        distance fog fades things into (lighting3d.fog_params x the time of day's ambient), so the land
        melts into the sky with no seam - and the biome's haze (ash in the Ashlands, murk over the Mire)
        and foggy / rainy weather tint it the same way;
      - the sun: a disc with a soft glow, in the same direction the world is lit and shadowed from
        (fx3d.sun gives the compass direction; how high it stands follows the time of day), and a warm
        glow along the horizon on its side at dawn and dusk;
      - the moon and twinkling stars at night (they fade out at dawn);
      - soft drifting clouds (noise worked out in the shader), lit by the sun's colour, thicker, darker and
        faster in rain and storms, grey in snow, slow when it's calm, and lit up by lightning flashes.

  * THE FAR LAND (surface only, both cameras). The map is a square; past its edge there used to be nothing,
    so in first person you saw a hard edge and a flat dark plain. Now a ring of low-detail land is built
    once per world all the way round it (seeded from the world seed, so every computer sees the same):
      - the first bit carries on from the map's own edge (same height, about the same colour as the edge
        tiles) and rolls gently away, so the border just looks like more countryside;
      - a band of simple low-poly trees right past the edge (pines, round trees, snowy pines in the
        tundra, dead spikes in the Ashlands, grey snags over the Mire);
      - further out rolling hills, then a ring of mountains (big and snowy behind the Highlands and Tundra,
        dark volcanic rock behind the Ashlands, low behind the Mire).
    It's drawn with the ground (before the light map), lit and fogged by the same lighting3d library as the
    real ground, so at night it goes dark with everything else and far away it fades into the sky colour.

Hooks (view3d.py): sky_land(vl) just before the ground is drawn, sky_dome(vl, dk) after the standing things.
If a shader won't build on some odd graphics card, both quietly switch themselves off (the old flat sky in
firstperson.fp_draw_sky is still drawn underneath, so nothing breaks).
"""
import math
import random
from array import array

from arcade.gl import BufferDescription
from arcade.gl.geometry import quad_2d_fs
from pyglet import gl

import fx3d
import lighting3d
from settings import *

FAR_FP = 16000.0          # first person far plane (view3d.use_world3d): the mountains are a long way off

# ----------------------------------------------------------------- time-of-day colours (0..1)
# Same breakpoints as fx3d._GRADE, so the sky and the light on the land always change together.
_MID_DUSK = (DUSK_START + NIGHT_START) / 2
_MID_DAWN = (DAWN_START + 1) / 2
ZENITH = [
    (0.00, (0.36, 0.47, 0.72)),           # sunrise
    (0.06, (0.33, 0.53, 0.84)),
    (0.13, (0.26, 0.49, 0.86)),           # day
    (DUSK_START - 0.10, (0.26, 0.49, 0.86)),
    (DUSK_START, (0.30, 0.44, 0.74)),     # golden hour
    (_MID_DUSK, (0.24, 0.20, 0.42)),      # dusk: purple
    (NIGHT_START, (0.020, 0.030, 0.090)),  # night: deep blue
    (DAWN_START, (0.020, 0.030, 0.090)),
    (_MID_DAWN, (0.11, 0.10, 0.25)),      # before dawn
    (1.00, (0.36, 0.47, 0.72)),
]
GLOW = [                                  # the warm band along the horizon on the sun's side (colour x strength)
    (0.00, (0.62, 0.34, 0.20)),
    (0.06, (0.22, 0.15, 0.08)),
    (0.13, (0.0, 0.0, 0.0)),
    (DUSK_START - 0.10, (0.0, 0.0, 0.0)),
    (DUSK_START, (0.42, 0.26, 0.10)),
    (_MID_DUSK, (0.75, 0.33, 0.16)),
    (NIGHT_START, (0.10, 0.03, 0.05)),
    (DAWN_START, (0.0, 0.0, 0.0)),
    (_MID_DAWN, (0.30, 0.12, 0.14)),
    (1.00, (0.62, 0.34, 0.20)),
]
SUN_COL = [
    (0.00, (1.00, 0.70, 0.46)),
    (0.06, (1.00, 0.88, 0.72)),
    (0.13, (1.00, 0.97, 0.90)),
    (DUSK_START - 0.10, (1.00, 0.96, 0.88)),
    (DUSK_START, (1.00, 0.80, 0.52)),
    (_MID_DUSK, (1.00, 0.56, 0.30)),
    (NIGHT_START, (0.90, 0.40, 0.25)),
    (DAWN_START, (0.90, 0.40, 0.25)),
    (_MID_DAWN, (1.00, 0.55, 0.40)),
    (1.00, (1.00, 0.70, 0.46)),
]
SUN_MAX_EL = math.radians(62)     # how high the sun climbs at midday
MOON_MAX_EL = math.radians(48)

# clouds per weather: (cover 0..1, darkness 0..1, wind speed)
CLOUDS = {"clear": (0.34, 0.0, 1.0), "rain": (0.86, 0.48, 2.3), "storm": (0.97, 0.75, 4.2),
          "snow": (0.88, 0.20, 0.8), "fog": (0.62, 0.12, 0.3)}
BIOME_CLOUDS = {"ash": (0.20, 0.40), "mire": (0.15, 0.15)}     # extra cover / darkness over these biomes


def _keyed(table, phase):
    """Smoothly blended value of a (phase, colour) table at this time of day (like fx3d.grade)."""
    phase %= 1.0
    for (p0, c0), (p1, c1) in zip(table, table[1:]):
        if p0 <= phase <= p1:
            k = (phase - p0) / (p1 - p0) if p1 > p0 else 0.0
            k = k * k * (3 - 2 * k)
            return tuple(a + (b - a) * k for a, b in zip(c0, c1))
    return table[0][1]


def sun_dir(phase, dk):
    """Unit vector towards the sun. Its compass direction is the one the world is lit and shadowed from
    (fx3d.sun); how high it stands follows the day: on the horizon at sunrise (phase 0) and at nightfall,
    highest at midday, below the horizon at night."""
    if phase >= DAWN_START:
        t = (phase - 1.0) / NIGHT_START
    else:
        t = phase / NIGHT_START
    s = math.sin(math.pi * max(-0.5, min(1.5, t)))
    el = SUN_MAX_EL * math.copysign(abs(s) ** 1.3, s)
    sx, sy, _ = fx3d.sun(phase, dk)
    ax, ay = -sx, -sy
    n = math.hypot(ax, ay)
    if n < 0.05:
        ax, ay, n = 0.0, 1.0, 1.0
    ax, ay = ax / n, ay / n
    return ax * math.cos(el), ay * math.cos(el), math.sin(el)


def moon_dir(phase):
    """The moon rises in the east as night falls and sets in the west at dawn (on the other side of the
    sky from the sun's path)."""
    t = (phase - (NIGHT_START - 0.05)) / (1.0 - NIGHT_START + 0.03)
    s = math.sin(math.pi * max(-0.5, min(1.5, t)))
    el = MOON_MAX_EL * s
    c = math.cos(math.pi * max(0.0, min(1.0, t)))
    ax, ay = c, -0.55
    n = math.hypot(ax, ay)
    return ax / n * math.cos(el), ay / n * math.cos(el), math.sin(el)


# ----------------------------------------------------------------- shaders
SKY_VS = """
#version 330
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 1.0, 1.0); }     // on the far plane: only where nothing was drawn
"""

SKY_FS = """
#version 330
uniform vec3 hor;        // horizon colour = what the distance fog fades into (fog x ambient)
uniform vec3 zen;        // zenith colour for the time of day
uniform vec3 glow;       // warm band along the horizon on the sun's side
uniform vec3 sun_d;      // towards the sun
uniform vec3 sun_c;
uniform vec3 moon_d;
uniform float stars;     // 0 by day .. 1 at night
uniform vec4 haze;       // biome haze colour (already x ambient), strength
uniform vec4 cloud;      // cover, darkness, lightning flash, (unused)
uniform vec2 wind;       // cloud drift (grows over time)
uniform vec3 cloud_lit;  // sunny side of the clouds
uniform vec3 cloud_dim;  // shady side
uniform float time;
uniform vec4 map_box;    // the map's ground (x0, y0, x1, y1): below the horizon inside it, leave it be
out vec4 f_color;

float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float hash3(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash2(i), b = hash2(i + vec2(1.0, 0.0)), c = hash2(i + vec2(0.0, 1.0)), d = hash2(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
float fbm(vec2 p, int octaves) {
    float t = 0.0, a = 0.5, norm = 0.0;
    for (int i = 0; i < octaves; i++) {
        t += vnoise(p) * a;
        norm += a;
        p = p * 2.03 + vec2(17.1, 9.2);
        a *= 0.5;
    }
    return t / norm;
}
void main() {
    vec2 ndc = (gl_FragCoord.xy - lt_vp.xy) / lt_vp.zw * 2.0 - 1.0;
    vec4 w = lt_inv * vec4(ndc, 1.0, 1.0);
    vec3 d = normalize(w.xyz / w.w - lt_eye.xyz);
    float e = d.z;
    if (e < 0.0) {
        // looking down past the land: the ground plane far away, all in haze. On flat old worlds the
        // map's own ground isn't in the depth buffer, so leave the inside of the map alone.
        float t = -lt_eye.z / min(e, -1e-4);
        vec2 g = lt_eye.xy + d.xy * t;
        if (g.x > map_box.x && g.y > map_box.y && g.x < map_box.z && g.y < map_box.w) discard;
        f_color = vec4(hor, 1.0);
        return;
    }
    // the gradient: horizon colour low down, the zenith colour higher up
    float up = pow(e, 0.55);
    vec3 c = mix(hor, zen, smoothstep(0.0, 1.0, up));
    // the warm glow on the sun's side at dawn and dusk (low and wide)
    vec2 sd = normalize(sun_d.xy + vec2(1e-5));
    float side = 0.5 + 0.5 * dot(normalize(d.xy + vec2(1e-5)), sd);
    c += glow * (side * side * side) * exp(-e * 5.0);
    // the biome's haze: strongest low down
    c = mix(c, haze.rgb, haze.a * (1.0 - 0.55 * up));
    // stars and moon (behind the clouds)
    float hz = smoothstep(0.0, 0.22, e);
    if (stars > 0.0) {
        vec3 q = d * 170.0;
        vec3 cell = floor(q);
        float h = hash3(cell);
        if (h > 0.965) {
            vec3 sp = cell + 0.25 + 0.5 * vec3(hash3(cell + 3.1), hash3(cell + 7.7), hash3(cell + 1.3));
            float r = length(q - normalize(sp) * 170.0);
            float tw = 0.65 + 0.35 * sin(time * (1.5 + 3.0 * hash3(cell + 9.4)) + h * 60.0);
            float b = (h - 0.965) / 0.035;
            c += vec3(0.85, 0.9, 1.0) * (1.0 - smoothstep(0.0, 0.32, r)) * tw * (0.35 + 0.9 * b * b) * stars * hz;
        }
    }
    if (moon_d.z > -0.08) {
        float mu = dot(d, moon_d);
        float r = 0.030;
        float disc = smoothstep(cos(r), cos(r * 0.9), mu);
        vec3 lo = moon_d.z > 0.9 ? vec3(1.0, 0.0, 0.0) : normalize(cross(moon_d, vec3(0.0, 0.0, 1.0)));
        vec3 hi = cross(lo, moon_d);
        vec2 mp = vec2(dot(d, lo), dot(d, hi)) / r;            // -1..1 across the disc
        float maria = 0.78 + 0.22 * smoothstep(0.35, 0.65, vnoise(mp * 2.3 + 4.0));
        c = mix(c, vec3(0.86, 0.89, 0.98) * maria, disc * stars);
        c += vec3(0.30, 0.36, 0.55) * pow(max(mu, 0.0), 900.0) * 0.5 * stars;
        c += vec3(0.20, 0.24, 0.40) * pow(max(mu, 0.0), 60.0) * 0.12 * stars;
    }
    // the sun: a disc with a soft glow (fades as it sinks below the horizon)
    float mu = dot(d, sun_d);
    float vis = smoothstep(-0.06, 0.02, sun_d.z);
    float rs = 0.024;
    float sdisc = smoothstep(cos(rs), cos(rs * 0.8), mu);
    float sglow = pow(max(mu, 0.0), 350.0) * 0.55 + pow(max(mu, 0.0), 24.0) * 0.20 + pow(max(mu, 0.0), 4.0) * 0.06;
    // clouds: noise on a high flat layer, drifting with the wind; thinner towards the horizon
    float a = 0.0;
    vec3 cc = vec3(0.0);
    if (cloud.x > 0.01) {
        vec2 cp = d.xy / (e + 0.10) * 1.5 + wind;
        float n = fbm(cp, 5);
        float th = mix(0.74, 0.16, cloud.x);
        a = smoothstep(th, th + 0.20, n) * smoothstep(0.0, 0.16, e);
        if (a > 0.001) {
            float n2 = fbm(cp + sd * 0.10, 3);          // a step towards the sun: thicker there = shaded
            float lit = clamp(0.62 + (n - n2) * 6.0, 0.0, 1.0);
            lit = mix(lit, 0.45, cloud.y * 0.6);
            cc = mix(cloud_dim, cloud_lit, lit);
            cc += sun_c * pow(max(mu, 0.0), 12.0) * (1.0 - a) * 0.5 * vis * (1.0 - cloud.y);   // bright rims near the sun
            cc = mix(cc, hor, (1.0 - up) * 0.55);                 // far clouds sink into the haze
            cc += vec3(0.75, 0.8, 1.0) * cloud.z * (0.5 + 0.5 * lit);    // lightning
            a *= mix(0.92, 1.0, cloud.y);
        }
    }
    float shine = 1.0 - a;
    c += sun_c * sglow * vis * (0.35 + 0.65 * shine) * (1.0 - 0.7 * cloud.y);
    c = mix(c, cc, a);
    c = mix(c, sun_c * 1.25 + 0.15, sdisc * vis * shine * shine * (1.0 - 0.8 * cloud.y));
    f_color = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""

LAND_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec3 in_nrm;
in vec3 in_col;
out vec3 v_pos;
out vec3 v_nrm;
out vec3 v_col;
void main() {
    v_pos = in_pos;
    v_nrm = in_nrm;
    v_col = in_col;
    gl_Position = window.projection * window.view * vec4(in_pos, 1.0);
}
"""

LAND_FS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 v_pos;
in vec3 v_nrm;
in vec3 v_col;
out vec4 f_color;
float lhash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float lnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(lhash(i), lhash(i + vec2(1.0, 0.0)), f.x), mix(lhash(i + vec2(0.0, 1.0)), lhash(i + vec2(1.0, 1.0)), f.x), f.y);
}
void main() {
    vec3 n = normalize(v_nrm);
    vec3 L = lt_sun.xyz;
    // the same shading as the real ground (terrain3d.py), so the edge of the map doesn't show
    float shade = clamp(1.0 + 1.15 * (dot(n, L) - L.z), 0.55, 1.2);
    vec3 rgb = v_col * shade * lt_hemi(n) / lt_sky.rgb;
    // a little mottling so the plain colour reads as grass / rock / snow from close by
    rgb *= 0.92 + 0.10 * lnoise(v_pos.xy / 70.0) + 0.06 * lnoise(v_pos.xy / 23.0);
    f_color = vec4(lt_fogged(rgb, v_pos), 1.0);
}
"""

# ----------------------------------------------------------------- the far land: per-biome looks
# ground colour, rock colour, snow (1 = snow on the high parts), gentle roll, hill height, mountain height,
# tree style, tree colour, trees per 10 000 px2
LAND = {
    "forest":    ((0.31, 0.45, 0.20), (0.44, 0.46, 0.50), 1, 40, 340, 1250, "mixed", (0.20, 0.36, 0.16), 1.3),
    "meadow":    ((0.42, 0.54, 0.24), (0.47, 0.49, 0.50), 1, 30, 260, 1000, "round", (0.27, 0.43, 0.17), 0.6),
    "tundra":    ((0.86, 0.89, 0.93), (0.52, 0.57, 0.65), 2, 50, 420, 1750, "snowpine", (0.17, 0.29, 0.23), 0.9),
    "highlands": ((0.44, 0.49, 0.37), (0.50, 0.50, 0.52), 1, 70, 560, 1950, "pine", (0.19, 0.31, 0.20), 0.5),
    "ash":       ((0.20, 0.18, 0.17), (0.23, 0.20, 0.19), 0, 50, 380, 1500, "dead", (0.13, 0.11, 0.10), 0.6),
    "mire":      ((0.27, 0.31, 0.20), (0.36, 0.39, 0.33), 0, 10, 110, 650, "snag", (0.20, 0.27, 0.17), 0.8),
}
SNOW = (0.92, 0.94, 0.97)
RINGS = (-56.0, 0.0, 50.0, 120.0, 220.0, 360.0, 540.0, 780.0, 1080.0, 1450.0, 1900.0, 2450.0, 3100.0,
         3850.0, 4700.0, 5600.0, 6600.0)
STEPS = 288               # vertices round each ring
TREE_BAND = (30.0, 820.0)


def _smooth(e0, e1, x):
    t = (x - e0) / (e1 - e0)
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return t * t * (3 - 2 * t)


def _ray_box(ux, uy, R, d):
    """Distance from the centre along (ux, uy) to the map's square (half size R) grown by d
    (rounded corners, so the rings far out become smooth)."""
    a, b = abs(ux), abs(uy)
    big = max(a, b)
    r = (R + d) / big
    if d <= 0 or r * min(a, b) <= R:
        return r
    s = a + b
    return R * s + math.sqrt(max(0.0, R * R * s * s - 2 * R * R + d * d))


def _tex_mean(tex, cache):
    key = id(tex)
    if key not in cache:
        try:
            im = tex.image.convert("RGBA").resize((1, 1))
            r, g, b, _ = im.getpixel((0, 0))
            cache[key] = (r / 255, g / 255, b / 255)
        except Exception:      # noqa: BLE001 - odd texture: plain grass
            cache[key] = (0.33, 0.48, 0.22)
    return cache[key]


def build_land(game):
    """The far land round the map: (vertex floats [x y z nx ny nz r g b ...], map box). Pure function of the
    world (seed, layout, ground tiles, heights), built once."""
    import biomes
    size = game.world_size
    lo = -128.0
    hi = float((size + 255) // 256 * 256 + 128)
    cx = cy = (lo + hi) / 2
    R = (hi - lo) / 2
    seed = getattr(game, "seed", 1)
    s = biomes.seed_int(seed, "farland")
    fbm = biomes.fbm
    grid = game.hill_grid("over") if hasattr(game, "hill_grid") else None
    lay = game.layout
    over = game.layers["over"]

    # the colour of the map's edge tiles (their texture's average x their tint), for the first strip
    tiles = {}
    for t in over.ground:          # the plain tiles come first; cracks, pools and patches are added later
        i, j = int(round(t.center_x / 256)), int(round(t.center_y / 256))
        if abs(t.center_x - i * 256) < 1 and abs(t.center_y - j * 256) < 1:
            tiles.setdefault((i, j), t)
    nmax = int((hi - 128) // 256)
    cache = {}

    def edge_col(x, y):
        i = max(0, min(nmax, int(round(x / 256))))
        j = max(0, min(nmax, int(round(y / 256))))
        t = tiles.get((i, j))
        if t is None:
            return None
        m = _tex_mean(t.texture, cache)
        tint = t.color
        return tuple(m[k] * tint[k] / 255 for k in range(3))

    # per direction round the map: the biome mix there and the edge colour / height
    looks = []
    for i in range(STEPS):
        a = math.tau * i / STEPS
        ux, uy = math.cos(a), math.sin(a)
        r = _ray_box(ux, uy, R, 0.0)
        ex, ey = cx + ux * r, cy + uy * r
        px, py = min(max(ex, 1.0), size - 1.0), min(max(ey, 1.0), size - 1.0)
        w = biomes.weights_at(lay, px, py, 520)
        mix = [0.0] * 10
        cols = [[0.0] * 3 for _ in range(3)]
        tree_w = {}
        for name, k in w.items():
            v = LAND.get(name, LAND["forest"])
            for c in range(3):
                cols[0][c] += v[0][c] * k
                cols[1][c] += v[1][c] * k
                cols[2][c] += v[7][c] * k
            mix[0] += v[2] * k
            mix[1] += v[3] * k
            mix[2] += v[4] * k
            mix[3] += v[5] * k
            mix[4] += v[8] * k
            tree_w[v[6]] = tree_w.get(v[6], 0.0) + k
        ec = edge_col(px, py)
        eh = grid.at(ex, ey) if grid is not None else 0.0
        looks.append((ux, uy, mix, cols, tree_w, ec, eh))
    # soften the edge colour along the border (tiles are 256 px squares)
    ecs = []
    for i in range(STEPS):
        acc, n = [0.0, 0.0, 0.0], 0
        for j in range(-3, 4):
            ec = looks[(i + j) % STEPS][5]
            if ec is not None:
                for c in range(3):
                    acc[c] += ec[c]
                n += 1
        ecs.append(tuple(v / n for v in acc) if n else looks[i][3][0])

    def height(x, y, d, lk, eh):
        mix = lk[2]
        roll = mix[1] * (fbm(s, x / 650.0, y / 650.0, 3) - 0.35)
        z = eh + (roll - eh) * _smooth(0.0, 520.0, d)
        z += mix[2] * _smooth(380.0, 2300.0, d) * fbm(s + 11, x / 1400.0, y / 1400.0, 3)
        n = fbm(s + 23, x / 2300.0, y / 2300.0, 4)
        ridge = 1.0 - abs(2.0 * n - 1.0)
        far = _smooth(1900.0, 4300.0, d) * (1.0 - 0.45 * _smooth(5200.0, 6600.0, d))
        z += mix[3] * far * (0.25 + 0.75 * ridge * ridge)
        return z

    # ---- the land: a grid of STEPS x len(RINGS) points
    pts = []
    for lk, ec in zip(looks, ecs):
        ux, uy = lk[0], lk[1]
        row = []
        for d in RINGS:
            r = _ray_box(ux, uy, R, d)
            x, y = cx + ux * r, cy + uy * r
            z = height(x, y, max(d, 0.0), lk, lk[6]) - (6.0 if d < 0 else 0.0)
            row.append((x, y, z, d))
        pts.append(row)
    nr = len(RINGS)
    # smooth normals from the neighbours
    nrm = []
    for i in range(STEPS):
        rown = []
        for k in range(nr):
            a = pts[(i + 1) % STEPS][k]
            b = pts[(i - 1) % STEPS][k]
            c = pts[i][min(nr - 1, k + 1)]
            e = pts[i][max(0, k - 1)]
            t1 = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
            t2 = (c[0] - e[0], c[1] - e[1], c[2] - e[2])
            nx, ny, nz = t1[1] * t2[2] - t1[2] * t2[1], t1[2] * t2[0] - t1[0] * t2[2], t1[0] * t2[1] - t1[1] * t2[0]
            if nz < 0:
                nx, ny, nz = -nx, -ny, -nz
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            rown.append((nx / ln, ny / ln, nz / ln))
        nrm.append(rown)

    def colour(i, k):
        x, y, z, d = pts[i][k]
        lk = looks[i]
        ground, rock = lk[3][0], lk[3][1]
        base = ecs[i]
        g = tuple(base[c] + (ground[c] - base[c]) * _smooth(0.0, 900.0, d) for c in range(3))
        slope = 1.0 - nrm[i][k][2]
        rk = max(_smooth(250.0, 900.0, z - lk[6]), _smooth(0.10, 0.35, slope)) * _smooth(300.0, 1500.0, d)
        col = tuple(g[c] + (rock[c] - g[c]) * rk for c in range(3))
        snow = lk[2][0]
        if snow > 0.05:
            line = 1050.0 if snow < 1.5 else 520.0
            sk = _smooth(line, line + 220.0, z + 160.0 * (biomes.noise(s + 5, x / 300.0, y / 300.0) - 0.5))
            sk *= min(1.0, snow) * (1.0 - 0.6 * _smooth(0.35, 0.6, slope))
            col = tuple(col[c] + (SNOW[c] - col[c]) * sk for c in range(3))
        return col

    data = array("f")

    def vert(i, k):
        x, y, z, _ = pts[i][k]
        data.extend((x, y, z) + nrm[i][k] + colour(i, k))

    for i in range(STEPS):
        j = (i + 1) % STEPS
        for k in range(nr - 1):
            vert(i, k), vert(j, k), vert(j, k + 1)
            vert(i, k), vert(j, k + 1), vert(i, k + 1)
    # the outer rim: drop straight down so nothing peeks under the last ring
    for i in range(STEPS):
        j = (i + 1) % STEPS
        a, b = pts[i][-1], pts[j][-1]
        for p in ((a[0], a[1], a[2]), (b[0], b[1], b[2]), (b[0], b[1], -400.0),
                  (a[0], a[1], a[2]), (b[0], b[1], -400.0), (a[0], a[1], -400.0)):
            data.extend(p + nrm[i][-1] + colour(i, nr - 1))

    # ---- trees in a band just past the edge
    rnd = random.Random(f"{seed}:farland-trees")
    perim = 8 * R
    band = TREE_BAND[1] - TREE_BAND[0]
    avg = sum(lk[2][4] for lk in looks) / STEPS
    count = int(perim * band / 10000 * avg * 2.2)
    for _ in range(count):
        f = rnd.random() * STEPS
        i = int(f) % STEPS
        lk = looks[i]
        if rnd.random() * avg * 1.2 > lk[2][4]:
            continue
        d = TREE_BAND[0] + band * (rnd.random() ** 1.25)
        a = math.tau * f / STEPS
        ux, uy = math.cos(a), math.sin(a)
        r = _ray_box(ux, uy, R, d)
        x, y = cx + ux * r, cy + uy * r
        if rnd.random() > _smooth(0.36, 0.66, fbm(s + 31, x / 420.0, y / 420.0, 2)):
            continue                 # trees grow in clumps, with open glades between
        z = height(x, y, d, lk, lk[6]) - 10.0
        styles = lk[4]
        pick, acc = rnd.random() * sum(styles.values()), 0.0
        style = "mixed"
        for name, wv in styles.items():
            acc += wv
            if pick <= acc:
                style = name
                break
        if style == "mixed":
            style = "pine" if rnd.random() < 0.45 else "round"
        tc = lk[3][2]
        v = 0.8 + 0.4 * rnd.random()
        col = tuple(min(1.0, c * v) for c in tc)
        _tree(data, rnd, style, x, y, z, col)
    return data, (lo, lo, hi, hi)


def _tri(data, a, b, c, col):
    """One flat-shaded triangle (its own face normal, facing up / out)."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    n = (nx / ln, ny / ln, nz / ln)
    for p in (a, b, c):
        data.extend(tuple(p) + n + col)


def _cone(data, x, y, z0, z1, r, sides, col, rot, top_col=None, lean=(0.0, 0.0)):
    """A cone from a ring of radius r at height z0 up to a point at z1 (moved sideways by `lean`)."""
    top = (x + lean[0], y + lean[1], z1)
    ring = [(x + math.cos(rot + math.tau * k / sides) * r, y + math.sin(rot + math.tau * k / sides) * r, z0)
            for k in range(sides)]
    for k in range(sides):
        a, b = ring[k], ring[(k + 1) % sides]
        if z1 < z0:
            a, b = b, a          # a cone hanging down: keep its faces' normals pointing out
        shade = 0.88 + 0.24 * ((k * 7) % sides) / sides
        _tri(data, a, b, top, tuple(min(1.0, c * shade) for c in (top_col or col)))


def _drum(data, x, y, z0, z1, r, sides, col, rot):
    """The upright sides of a short prism (the middle of a round crown)."""
    ring = [(math.cos(rot + math.tau * k / sides) * r, math.sin(rot + math.tau * k / sides) * r)
            for k in range(sides)]
    for k in range(sides):
        (ax, ay), (bx, by) = ring[k], ring[(k + 1) % sides]
        a0, b0, a1, b1 = (x + ax, y + ay, z0), (x + bx, y + by, z0), (x + ax, y + ay, z1), (x + bx, y + by, z1)
        shade = 0.88 + 0.24 * ((k * 7) % sides) / sides
        c = tuple(min(1.0, v * shade) for v in col)
        _tri(data, a0, b0, b1, c)
        _tri(data, a0, b1, a1, c)


def _tree(data, rnd, style, x, y, z, col):
    """One low-poly tree (a handful of triangles)."""
    rot = rnd.random() * math.tau
    trunk = (0.30, 0.22, 0.15)
    if style in ("pine", "snowpine"):
        h = 150 + rnd.random() * 130
        r = h * (0.26 + 0.06 * rnd.random())
        _cone(data, x, y, z, z + h * 0.35, 7, 4, trunk, rot)
        _cone(data, x, y, z + h * 0.18, z + h * 0.72, r, 6, col, rot)
        top = SNOW if style == "snowpine" else col
        _cone(data, x, y, z + h * 0.45, z + h, r * 0.68, 6, top if style == "snowpine" else col, rot + 0.5)
    elif style == "round":
        h = 120 + rnd.random() * 100
        r = h * (0.27 + 0.07 * rnd.random())
        _cone(data, x, y, z, z + h * 0.5, 8, 4, trunk, rot)
        # crown: a short six-sided drum with a cone on top and one underneath - a rounded lump
        lo_z, hi_z = z + h * 0.52, z + h * 0.74
        _cone(data, x, y, lo_z, z + h * 0.30, r, 6, tuple(c * 0.78 for c in col), rot)
        _drum(data, x, y, lo_z, hi_z, r, 6, col, rot)
        _cone(data, x, y, hi_z, z + h, r, 6, col, rot)
    elif style == "dead":   # a burnt tree: a bare trunk with a few crooked branches reaching out
        h = 80 + rnd.random() * 90
        _cone(data, x, y, z, z + h, 8 + rnd.random() * 4, 4, col, rot, lean=(rnd.random() * 16 - 8, 0.0))
        for _ in range(3):
            a = rnd.random() * math.tau
            bz = z + h * (0.35 + 0.4 * rnd.random())
            reach = h * (0.3 + 0.2 * rnd.random())
            _cone(data, x, y, bz, bz + h * 0.32, 4, 3, col, a, lean=(math.cos(a) * reach, math.sin(a) * reach))
    else:   # "snag": a swamp tree - a leaning grey trunk under a wide, flat, dark canopy
        h = 110 + rnd.random() * 90
        r = h * (0.34 + 0.1 * rnd.random())
        lx, ly = rnd.random() * 30 - 15, rnd.random() * 30 - 15
        _cone(data, x, y, z, z + h * 0.8, 10, 4, (0.32, 0.31, 0.27), rot, lean=(lx, ly))
        cx, cy = x + lx * 0.8, y + ly * 0.8
        lo_z, hi_z = z + h * 0.7, z + h * 0.8
        _cone(data, cx, cy, lo_z, z + h * 0.6, r, 6, tuple(c * 0.75 for c in col), rot)
        _drum(data, cx, cy, lo_z, hi_z, r, 6, col, rot)
        _cone(data, cx, cy, hi_z, z + h, r, 6, col, rot)


# =========================================================================== the mixin
class Sky3D:
    """Sky dome + far land. Mixed into View3D."""

    _sky_broken = False
    _sky_wind = (0.0, 0.0)
    _sky_t = None

    def _sky_init(self):
        if self._sky_broken:
            return False
        if getattr(self, "_sky_prog", None) is not None:
            return True
        try:
            ctx = self.ctx
            self._sky_prog = ctx.program(vertex_shader=SKY_VS, fragment_shader=lighting3d.inject(SKY_FS, frag=True))
            self._land_prog = ctx.program(vertex_shader=LAND_VS,
                                          fragment_shader=lighting3d.inject(LAND_FS, frag=True))
            for p in (self._sky_prog, self._land_prog):
                lighting3d.bind(p)
            self._sky_quad = quad_2d_fs()
            self._land_key = None
            self._land_geo = None
            return True
        except Exception as e:      # noqa: BLE001 - never let a graphics extra stop the game
            print("Sky switched off - this graphics card didn't like it:", e)
            self._sky_broken = True
            self._sky_prog = None
            return False

    def _land(self):
        """The far land's geometry for this world (built once, rebuilt for a new world)."""
        over = self.layers.get("over") if hasattr(self, "layers") else None
        if over is None or not hasattr(self, "layout"):
            return None
        key = (getattr(self, "seed", None), self.world_size, getattr(self, "worldgen", None), id(over),
               len(over.ground))
        if self._land_key != key:
            self._land_key = key
            self._land_geo = None
            data, box = build_land(self)
            ctx = self.ctx
            buf = ctx.buffer(data=data)
            self._land_geo = ctx.geometry([BufferDescription(buf, "3f 3f 3f", ["in_pos", "in_nrm", "in_col"])],
                                          mode=ctx.TRIANGLES)
            self._land_n = len(data) // 9
            self._land_box = box
        return self._land_geo

    # ------------------------------------------------------------------ hooks (view3d.draw_world_3d)
    def sky_land(self, vl):
        """The far land round the map: call with the 3D camera on and the "ground" lighting stage written,
        just before the ground tiles (they depth-test against it on the hills)."""
        if vl != "over" or not self._sky_init():
            return
        try:
            geo = self._land()
            if geo is None:
                return
            ctx = self.ctx
            ctx.enable(ctx.DEPTH_TEST)
            gl.glDepthFunc(gl.GL_LEQUAL)
            gl.glDepthMask(gl.GL_TRUE)
            geo.render(self._land_prog, vertices=self._land_n)
            ctx.disable(ctx.DEPTH_TEST)
        except Exception as e:      # noqa: BLE001
            print("Far land switched off:", e)
            self._sky_broken = True

    def sky_dome(self, vl, dk):
        """The sky (first person on the surface): call after everything that stands up, before the
        see-through things (smoke, build preview) - with the 3D camera on. Fills only empty pixels."""
        if vl != "over" or not self.fp_on() or not self._sky_init():
            return
        try:
            self.use_world3d()
            self._sky_uniforms(dk)
            ctx = self.ctx
            ctx.enable(ctx.DEPTH_TEST)
            gl.glDepthFunc(gl.GL_LEQUAL)
            gl.glDepthMask(gl.GL_FALSE)
            self._sky_quad.render(self._sky_prog)
            gl.glDepthMask(gl.GL_TRUE)
        except Exception as e:      # noqa: BLE001
            print("Sky switched off:", e)
            self._sky_broken = True
            gl.glDepthMask(gl.GL_TRUE)

    def sky_sun_screen(self, dk):
        """Where the sun is on this view's screen, as (u, v, weight) - u, v in 0..1 across the view (may be
        well off it) and weight 0..1 for how much the camera faces it. post3d's daytime grade warms that side
        a little. The tilted camera looks down and away from the sun, so it gets (almost) nothing."""
        try:
            sd = sun_dir(self.phase, dk)
            _, f, r, u, d, vw, vh = self._basis()
        except Exception:      # noqa: BLE001
            return 0.5, 2.0, 0.0
        zc = sum(a * b for a, b in zip(sd, f))
        if zc <= 0.05 or sd[2] < -0.05:
            return 0.5, 2.0, 0.0
        xc = sum(a * b for a, b in zip(sd, r))
        yc = sum(a * b for a, b in zip(sd, u))
        su = max(-1.5, min(2.5, 0.5 + xc * d / zc / vw))
        sv = max(-1.5, min(2.5, 0.5 + yc * d / zc / vh))
        w = min(1.0, zc * 1.5) * min(1.0, (sd[2] + 0.05) * 8)
        return su, sv, w

    # ------------------------------------------------------------------ per frame
    def sky_colours(self, dk):
        """(horizon, zenith) colours of the sky right now - the horizon is exactly the distance fog's colour."""
        st = self._lt
        amb = st.amb
        hor = tuple(f * a for f, a in zip(st.fog, amb))
        phase = self.phase
        zen = _keyed(ZENITH, phase)
        gloom = getattr(self, "boss_gloom", 0.0)
        if gloom > 0:            # lairs.py: a boss out by day drags the night sky in with it
            zen = tuple(a + (b - a) * gloom for a, b in zip(zen, ZENITH[6][1]))
        return hor, zen

    def _sky_uniforms(self, dk):
        p = self._sky_prog
        phase = self.phase
        hor, zen = self.sky_colours(dk)
        kind = getattr(self, "weather_shown", "clear") or "clear"
        wk = getattr(self, "weather_k", 0.0)
        c0 = CLOUDS["clear"]
        c1 = CLOUDS.get(kind, c0)
        cover, dark, speed = (a + (b - a) * wk for a, b in zip(c0, c1))
        if getattr(self, "season", "") == "winter":
            cover = min(1.0, cover + 0.08)
        # biome: the haze (ash, murk) tints the sky and thickens the clouds
        haze = self.biome_fog() if hasattr(self, "layout") else None
        hz = (0.0, 0.0, 0.0, 0.0)
        if haze:
            k = min(0.45, haze[3] / 255 * 2.6)
            amb = self._lt.amb
            hz = tuple(c / 255 * a for c, a in zip(haze[:3], amb)) + (k,)
            here = self.biome_at(self.view_pos()) if hasattr(self, "biome_at") else ""
            more = BIOME_CLOUDS.get(here)
            if more:
                cover = min(1.0, cover + more[0])
                dark = min(1.0, dark + more[1])
        # overcast: the blue drains out of the sky
        over = _smooth(0.55, 0.95, cover)
        lum = sum(zen) / 3
        grey = (lum * 0.95, lum * 0.98, lum * 1.05)
        zen = tuple(a + (b - a) * over * 0.85 for a, b in zip(zen, grey))
        zen = tuple(c * (1 - 0.45 * dark) for c in zen)
        glow = tuple(c * (1 - 0.8 * over) for c in _keyed(GLOW, phase))
        sun_c = _keyed(SUN_COL, phase)
        sd = sun_dir(phase, dk)
        night = max(0.0, min(1.0, dk))
        # clouds: lit by the sun's colour by day, by the moon (dim blue) at night
        day = 1.0 - night
        amb = self._lt.amb
        lit_day = tuple(min(1.0, s * 0.95 + 0.08) for s in sun_c)
        lit = tuple((l * day + m * night) * (1 - 0.55 * dark) for l, m in zip(lit_day, (0.16, 0.18, 0.28)))
        dim = tuple((0.55 * h + 0.35 * z + 0.06) * (1 - 0.5 * dark) for h, z in zip(hor, zen))
        dim = tuple(d * (0.55 + 0.45 * a) for d, a in zip(dim, amb))
        # wind: the clouds' drift, added up frame by frame so a change of weather never makes them jump
        t = getattr(self, "flame_t", 0.0)
        if self._sky_t is None or t < self._sky_t:
            self._sky_t = t
        dt = min(0.1, t - self._sky_t)
        self._sky_t = t
        wx, wy = self._sky_wind
        self._sky_wind = (wx + 0.012 * speed * dt, wy + 0.005 * speed * dt)
        flash = getattr(self, "weather_flash", 0.0) if kind == "storm" else 0.0
        p["hor"] = hor
        p["zen"] = zen
        p["glow"] = glow
        p["sun_d"] = sd
        p["sun_c"] = sun_c
        p["moon_d"] = moon_dir(phase)
        p["stars"] = night * (1 - 0.85 * over)
        p["haze"] = hz
        p["cloud"] = (cover, dark, min(1.0, flash) * 0.8, night)
        p["wind"] = self._sky_wind
        p["cloud_lit"] = lit
        p["cloud_dim"] = dim
        p["time"] = t % 1000.0
        box = getattr(self, "_land_box", None) or (-128.0, -128.0, self.world_size + 128.0, self.world_size + 128.0)
        p["map_box"] = box
