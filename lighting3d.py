"""
lighting3d.py - one shared lighting + fog library for every shader that draws the 3D world.

What every world shader gets (inject() pastes the GLSL in, like terrain3d.inject does for the hills):
  * Hemisphere ambient: surfaces facing up take a little of the sky's colour, surfaces facing down a
    little of the warm light bouncing off the ground. It replaces the old flat "0.6 + ..." ambient
    numbers, tuned so the daytime look stays the same.
  * Point lights: the nearest MAX_LIGHTS lights (campfires, braziers, torches, your own light, bosses...)
    with their real 3D position, colour and reach. Each fragment adds them up with N.L and the same soft
    falloff the ground's light pools use, so a campfire lights the faces of the walls, creatures and tree
    trunks around it, not just the ground under them.
  * A soft rim light (moonlight at night) so creature silhouettes still read in the dark.
  * Distance fog: from the biome's haze, foggy weather and the time of day (see View3D._lt_frame).

How this fits with fx3d's light map (the half-resolution "multiply" over the frame):
  The light map is a screen-space picture of light pools lying ON THE GROUND. That's exactly right for
  the ground, but for a wall or a creature standing next to a fire it is wrong: their pixels sit over a
  different bit of ground (further away), so they took the light of the wrong spot - and anything lit
  in its own shader would then be darkened a second time by the multiply.
  So the frame is drawn in three stages (LightState.write, called from View3D.draw_world_3d):
    "ground" - the ground and what lies on it: not lit here (lt_amb = 1, no point lights). The light map
               is multiplied over the frame right after these, exactly as before.
    "lit"    - everything standing up (walls, shapes, creatures, cut-outs, smoke): drawn AFTER the
               multiply, so the multiply never touches them and each shader does the whole job itself
               (lt_light): ambient colour of the time of day (lt_amb, the same colour the light map
               starts from) + its point lights, capped at 1 like the light map is - nothing is lit twice,
               and a wall by the fire is lit by the fire, not by the patch of ground behind it on screen.
    "glow"   - additive glows, flames and sparks on top of the night: not lit, and fog fades them to
               black instead of to the fog colour (adding fog colour would brighten the screen).
  The data lives in one uniform buffer (LightBlock) bound to every program, so switching stages or
  updating the lights is one small buffer write - no per-program uniform calls, nothing rebuilt.
"""
from array import array

MAX_LIGHTS = 16
BINDING = 5                 # uniform block binding point (shapes3d uses 3)

# sky / ground-bounce tints for the hemisphere ambient (around 1.0: the ambient's brightness is set by
# each shader's own numbers, these only tint it)
SKY = (1.05, 1.05, 1.09)
GROUND = (0.90, 0.86, 0.80)
FILL_RIM_NIGHT = (0.32, 0.42, 0.72)    # moonlight rim on creatures at night
FILL_RIM_CAVE = (0.42, 0.36, 0.48)     # underground: a dim purple-ish bounce
AIR = (184, 202, 222)                  # plain distance haze when the biome has none of its own
FP_HORIZON = (178, 208, 232)           # first person: the sky colour at the horizon (firstperson.fp_draw_sky)

GLSL = """
layout (std140) uniform LightBlock {
    mat4 lt_inv;        // inverse of projection * view (fragment -> world position)
    vec4 lt_vp;         // viewport x, y, w, h
    vec4 lt_eye;        // camera position ; number of point lights
    vec4 lt_amb;        // ambient colour of this stage (1 = leave it to the light map)
    vec4 lt_sky;        // hemisphere: from above
    vec4 lt_gnd;        // hemisphere: from below
    vec4 lt_sun;        // direction towards the sun
    vec4 lt_fill;       // soft fill from behind the camera (walls)
    vec4 lt_rim;        // rim light colour * strength
    vec4 lt_fog;        // fog colour (already darkened for the stage)
    vec4 lt_fogk;       // start distance, 1 / length, most fog, 0
    vec4 lt_pos[%N%];   // point lights: x, y, z, reach
    vec4 lt_col[%N%];   // colour * strength, wrap (0 = facing matters, 1 = lights all round)
};
vec3 lt_hemi(vec3 n) {
    return mix(lt_gnd.rgb, lt_sky.rgb, 0.5 + 0.5 * n.z);
}
// point lights at p. n = surface normal, or vec3(0) for flat cut-outs / particles (lit all round)
vec3 lt_points(vec3 p, vec3 n) {
    vec3 acc = vec3(0.0);
    int cnt = int(lt_eye.w);
    bool omni = dot(n, n) < 0.01;
    for (int i = 0; i < cnt; i++) {
        vec3 d = lt_pos[i].xyz - p;
        float r = lt_pos[i].w;
        float d2 = dot(d, d);
        if (d2 >= r * r) continue;
        float dist = sqrt(d2);
        float f = 1.0 - smoothstep(0.3, 1.0, dist / r);      // the same falloff as the ground's light pools
        float w = omni ? 1.0 : lt_col[i].w;
        float nl = omni ? 1.0 : max(dot(n, d / max(dist, 1e-3)), 0.0);
        acc += lt_col[i].rgb * f * (w + (1.0 - w) * nl);
    }
    return acc;
}
// what the light map does for the ground, done for a standing surface: the time of day's ambient plus the
// point lights, topped out at plain daylight (1.0) - so a wall by the fire looks the way it does at noon,
// never brighter, and in the "ground" stage this is exactly 1 (no change: the light map does the job)
vec3 lt_light(vec3 p, vec3 n) {
    return min(lt_amb.rgb + lt_points(p, n), vec3(1.0));
}
vec3 lt_rimlight(vec3 p, vec3 n) {
    vec3 v = normalize(lt_eye.xyz - p);
    float k = 1.0 - max(dot(n, v), 0.0);
    return lt_rim.rgb * (k * k * k) * (0.6 + 0.4 * max(n.z, 0.0));
}
float lt_fog_k(vec3 p) {
    float d = length(p - lt_eye.xyz) - lt_fogk.x;
    if (d <= 0.0) return 0.0;
    return lt_fogk.z * (1.0 - exp(-d * lt_fogk.y));
}
vec3 lt_fogged(vec3 c, vec3 p) { return mix(c, lt_fog.rgb, lt_fog_k(p)); }
"""

# fragment shaders only: where is this pixel in the world? (from the depth buffer value - so geometry
# shaders that are already full of outputs, like shapes3d's, don't need to pass the position down)
FRAG = """
vec3 lt_world() {
    vec2 ndc = (gl_FragCoord.xy - lt_vp.xy) / lt_vp.zw * 2.0 - 1.0;
    vec4 w = lt_inv * vec4(ndc, gl_FragCoord.z * 2.0 - 1.0, 1.0);
    return w.xyz / w.w;
}
// a face normal from the screen-space change of the position (flat, low-poly look), facing the camera
vec3 lt_face(vec3 p) {
    vec3 n = normalize(cross(dFdx(p), dFdy(p)));
    return dot(n, lt_eye.xyz - p) < 0.0 ? -n : n;
}
"""


def glsl(frag=False):
    src = GLSL.replace("%N%", str(MAX_LIGHTS))
    return src + FRAG if frag else src


def inject(src, frag=False):
    """Add the lighting library to a shader source (after the WindowBlock line, else after #version)."""
    if "vec3 lt_points(" in src:
        return src
    key = "uniform WindowBlock" if "uniform WindowBlock" in src else "#version"
    at = src.index("\n", src.index(key)) + 1
    return src[:at] + glsl(frag) + src[at:]


def bind(prog):
    """Point a program's LightBlock at our buffer's binding (no-op if the program doesn't use it)."""
    try:
        prog["LightBlock"] = BINDING
    except KeyError:
        pass


# ----------------------------------------------------------------- the buffer
FLOATS = 16 + 4 * 10 + 8 * MAX_LIGHTS


class LightState:
    """The per-frame values of the LightBlock, and the GPU buffer they go into."""

    def __init__(self, ctx):
        self.buf = ctx.buffer(reserve=FLOATS * 4)
        self.data = array("f", bytes(FLOATS * 4))
        self.inv = (1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0)
        self.vp = (0.0, 0.0, 1.0, 1.0)
        self.eye = (0.0, 0.0, 0.0)
        self.amb = (1.0, 1.0, 1.0)
        self.sun = (0.0, 0.24, 0.97)
        self.fill = (0.0, -0.96, 0.29)
        self.rim = (0.0, 0.0, 0.0)
        self.fog = (0.7, 0.78, 0.86)
        self.fogk = (0.0, 0.0, 0.0)
        self.lights = []            # [(x, y, z, reach, r, g, b, wrap)]

    def write(self, stage):
        """Upload for one stage of the frame: "ground", "lit" or "glow" (see the module docstring)."""
        d = self.data
        d[0:16] = array("f", self.inv)
        lit = stage == "lit"
        amb = self.amb if lit else (1.0, 1.0, 1.0)
        n = len(self.lights) if lit else 0
        fog = (0.0, 0.0, 0.0) if stage == "glow" else tuple(c * a for c, a in zip(self.fog, amb))
        rows = (self.vp, self.eye + (float(n),), amb + (1.0,), SKY + (1.0,), GROUND + (1.0,), self.sun + (0.0,),
                self.fill + (0.0,), (self.rim if lit else (0.0, 0.0, 0.0)) + (0.0,), fog + (1.0,), self.fogk + (0.0,))
        i = 16
        for r in rows:
            d[i:i + 4] = array("f", r)
            i += 4
        for k in range(MAX_LIGHTS):
            if k < n:
                x, y, z, reach, r, g, b, w = self.lights[k]
                d[i + 4 * k:i + 4 * k + 4] = array("f", (x, y, z, reach))
                d[i + 4 * MAX_LIGHTS + 4 * k:i + 4 * MAX_LIGHTS + 4 * k + 4] = array("f", (r, g, b, w))
        self.buf.write(d)
        self.buf.bind_to_uniform_block(BINDING)


def pick_lights(data, centre, ground_z=None, own=None, gain=1.0):
    """fx3d.fx_light_data's list (x, y, height, reach, r, g, b, a per light) -> the nearest MAX_LIGHTS
    point lights (x, y, z, reach, r, g, b, wrap). own: (x, y) of the viewer's own light - it lights all
    round (wrap), so your survivor and whatever is right next to you are never black on the dark side."""
    cx, cy = centre
    out = []
    for i in range(0, len(data) - 7, 8):
        x, y, h, reach, r, g, b, a = data[i:i + 8]
        if a <= 0.01 or reach <= 1:
            continue
        mine = own is not None and abs(x - own[0]) < 1 and abs(y - own[1]) < 1
        z = h + (ground_z(x, y) if ground_z else 0.0)
        k = a * gain
        out.append(((x - cx) ** 2 + (y - cy) ** 2 - reach * reach, (x, y, z, reach, r * k, g * k, b * k,
                                                                      0.8 if mine else 0.3)))
    out.sort(key=lambda e: e[0])
    return [e[1] for e in out[:MAX_LIGHTS]]


def fog_params(fp, focus, haze, fog_k, rain_k, horizon=None):
    """(colour 0..1, (start, 1/length, most)) for the distance fog.
    haze: the biome's (r, g, b, a) haze or None; fog_k: how foggy the weather is (0..1); rain_k: rain/storm.
    fp: first person (the far distance goes out to the horizon) or the tilted camera (looks down: only the
    top of the screen is far away; focus = how far the camera is from the spot it looks at). horizon: first person sky colour near the horizon (fog blends into it)."""
    col = [c / 255 for c in AIR]
    amount = 0.16                                   # plain air: a touch of depth at the far edge
    if haze:
        k = min(1.0, haze[3] / 60)
        col = [a + (b / 255 - a) * k for a, b in zip(col, haze[:3])]
        amount += haze[3] / 255 * 2.4
    if fp and horizon is not None:
        col = [a + (b / 255 - a) * 0.6 for a, b in zip(col, horizon)]
    if fog_k > 0:
        col = [a + (b - a) * fog_k for a, b in zip(col, (0.76, 0.78, 0.82))]
        amount += 0.6 * fog_k
    if rain_k > 0:
        col = [a + (b - a) * 0.4 * rain_k for a, b in zip(col, (0.42, 0.48, 0.56))]
        amount += 0.12 * rain_k
    if fp:
        start = 140.0 * (1 - 0.6 * fog_k)
        length = 2600.0 * (1 - 0.72 * fog_k) / (1 + 0.6 * rain_k)
        most = min(0.97, 0.78 + amount * 0.6)
    else:
        start = focus * (0.8 - 0.45 * fog_k)
        length = 900.0 * (1 - 0.55 * fog_k)
        most = min(0.85, amount)
    return tuple(col), (start, 1.0 / max(1.0, length), most)
