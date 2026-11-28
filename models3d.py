"""
models3d.py - real low-poly 3D models for every creature (animals, pets, zombies, bosses, survivors).

The models are built in Blender by tools/blender/ (see docs/MODELS.md) and committed as
assets/models/<name>.glb, so the game never needs Blender. This file:

  * reads each .glb with a tiny pure-Python glTF reader (struct + json, no extra packages),
  * uploads every model to the GPU once,
  * draws all creatures that share a model in ONE instanced draw call. Per instance it sends:
    position, heading, scale, tint (hit flash / chill / poison / fading), walk phase, how fast it
    moves, how hard it attacks, which optional parts are worn and up to five recolours,
  * animates in the vertex shader by each part's ROLE (legs swing, body bobs, head nods, zombie
    arms reach and sway, tails wag, wings flap, bosses breathe, the Frost Wraith floats, a lunge
    when attacking) - nothing is rebuilt on the CPU per frame,
  * also in the shader: survivors swing (wind up, strike with a body twist, follow through) for each
    chop / mine / attack, timed to the held item's cooldown; everything flinches back when hurt; standing
    creatures breathe and look about; zombies limp, hunch and sway as they lurch along,
  * knows where the attachment points (eyes, glowing cores, hands) are at any moment, so the night
    glow of zombie eyes sits on their faces and held items sit in survivors' hands.

Walking state comes from how far each creature moved since the last frame, so it works the same on
the host, on online clients (who only get positions + headings in snapshots) and in split screen.

Mixed into View3D (view3d.py). Setting "creature_models" in lastlight_config.json:
    "on" (default) - models in first person and in the tilted camera
    "fp"           - models in first person only (the tilted camera keeps the painted cut-outs)
    "off"          - the old cut-outs / draped shapes everywhere
"""
import json
import math
import os
import struct
from array import array

from arcade.gl import BufferDescription

import lighting3d
from settings import ITEMS

UNIT = 55.0                 # game pixels per Blender metre
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "assets", "models")

ROLES = {"body": 0, "head": 1, "leg_a": 2, "leg_b": 3, "arm_l": 4, "arm_r": 5, "tail": 6, "wing_l": 7,
         "wing_r": 8, "sleg_a": 9, "sleg_b": 10, "jaw": 11, "still": 12}
MATS = {"c": 0, "glow": 1, "acc1": 2, "acc2": 3, "acc3": 4, "acc4": 5, "acc5": 6}
OPTS = {"armor": 0, "helmet": 1, "cloak": 2, "pet_armor": 3}

# creature kind -> model name. Anything not listed uses the model named like the kind (if there is one).
# New kinds can borrow a model here until they get their own (e.g. "tundra_fox": "wolf").
MODEL_FOR = {}

# colours of worn things (art_gear.py / art_extra.py) - the model parts are recoloured with these
GEAR_COL = {
    "leather_tunic": (150, 100, 56), "iron_armor": (150, 156, 168), "chitin_armor": (104, 146, 58),
    "titan_plate": (104, 90, 76), "leather_cap": (140, 92, 50), "iron_helmet": (160, 166, 178),
    "mire_mask": (84, 100, 54), "fur_cloak": (132, 134, 142), "frost_cloak": (160, 205, 245),
    "pet_leather_armor": (150, 100, 56), "pet_iron_armor": (160, 166, 178),
}
JACKETS = [(58, 104, 112), (150, 62, 58), (96, 120, 58), (176, 138, 52)]     # art.JACKETS
HAIR = [(84, 54, 34), (40, 32, 28), (150, 96, 50), (60, 40, 30)]             # art.HAIR

# how much each zombie model staggers and sways as it walks (other walking zombies: 0.4)
STAGGER = {"walker": 1.0, "drowned": 1.0, "runner": 0.5, "brute": 0.7}

TILT_UP = 1.0               # height stretch in the tilted camera (cut-outs use 1 / cos(pitch))
VSTRIDE = 15               # x y z  nx ny nz  r g b  pivot xyz  role mat opt
ISTRIDE = 35                # see _m3_add()
NO_ACC = (-1.0, -1.0, -1.0)


# =========================================================================== glTF (.glb) reader
_COMP = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _read_glb(path):
    data = open(path, "rb").read()
    magic, _, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError(f"{path} is not a .glb file")
    off, js, binc = 12, None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8:off + 8 + clen]
        off += 8 + clen
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binc = chunk
    return js, binc


def _accessor(js, binc, idx):
    acc = js["accessors"][idx]
    bv = js["bufferViews"][acc["bufferView"]]
    fmt = _COMP[acc["componentType"]]
    n = _NCOMP[acc["type"]]
    size = struct.calcsize(fmt)
    stride = bv.get("byteStride") or size * n
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    cnt = acc["count"]
    if stride == size * n:
        out = list(struct.iter_unpack("<" + fmt * n, binc[base:base + cnt * stride]))
    else:
        out = [struct.unpack_from("<" + fmt * n, binc, base + i * stride) for i in range(cnt)]
    return out if n > 1 else [v[0] for v in out]


def _mat4_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _node_matrix(node):
    if "matrix" in node:
        m = node["matrix"]
        return [[m[j * 4 + i] for j in range(4)] for i in range(4)]
    tx, ty, tz = node.get("translation", (0, 0, 0))
    qx, qy, qz, qw = node.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = node.get("scale", (1, 1, 1))
    r = [[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
         [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
         [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
            [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
            [0, 0, 0, 1]]


def _xf(m, p, w=1.0):
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] * w for i in range(3))


def _game(p):
    """glTF (y up) -> game/Blender axes (z up)."""
    return p[0], -p[2], p[1]


def _srgb(v):
    v = max(0.0, min(1.0, v))
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def _role_of(name, extras):
    r = extras.get("role")
    if r in ROLES:
        return r
    n = name.lower()
    for key, role in (("leg_fl", "leg_a"), ("leg_br", "leg_a"), ("leg_l", "leg_a"), ("leg_fr", "leg_b"),
                      ("leg_bl", "leg_b"), ("leg_r", "leg_b"), ("arm_l", "arm_l"), ("arm_r", "arm_r"),
                      ("wing_l", "wing_l"), ("wing_r", "wing_r"), ("head", "head"), ("tail", "tail"),
                      ("jaw", "jaw")):
        if n.startswith(key):
            return role
    return "body"


class Model:
    """One loaded model: vertex data (game units), attachment points and animation settings."""

    def __init__(self, name, path):
        js, binc = _read_glb(path)
        self.name = name
        scene = js["scenes"][js.get("scene", 0)]
        meta = scene.get("extras", {}).get("ll_model", "{}")
        self.meta = json.loads(meta) if isinstance(meta, str) else dict(meta)
        an = self.meta.get("anim", {})
        self.anim = {k: float(an.get(k, 0.0)) for k in ("stride", "bob", "nod", "breathe", "wag", "flap", "hover",
                                                        "float", "lunge", "sway", "jaw")}
        self.arms = {"swing": 1, "reach": 2}.get(an.get("arms"), 0)
        self.stride_len = float(self.meta.get("stride_len", 1.0)) * UNIT
        mats = []
        for m in js.get("materials", []):
            nm = m.get("name", "")
            kind, _, hexc = nm.partition("_")
            try:
                col = tuple(int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4))
            except ValueError:
                f = m.get("pbrMetallicRoughness", {}).get("baseColorFactor", (0.8, 0.8, 0.8, 1))
                col = tuple(_srgb(c) for c in f[:3])
            mats.append((MATS.get(kind, 0), col))
        verts = []
        self.parts = {}            # part name -> (role id, pivot)
        points = []                # (name, model-space pos, part name)
        nodes = js["nodes"]

        def walk(ni, parent_m, part):
            node = nodes[ni]
            m = _mat4_mul(parent_m, _node_matrix(node))
            name = node.get("name", f"node{ni}")
            extras = node.get("extras", {})
            if "mesh" in node:
                role = ROLES[_role_of(name, extras)]
                opt = OPTS.get(extras.get("opt"), -1) + 1
                piv = tuple(v * UNIT for v in _game(_xf(m, (0, 0, 0))))
                self.parts[name] = (role, piv)
                part = name
                for prim in js["meshes"][node["mesh"]]["primitives"]:
                    at = prim["attributes"]
                    pos = _accessor(js, binc, at["POSITION"])
                    nrm = _accessor(js, binc, at["NORMAL"]) if "NORMAL" in at else [(0, 1, 0)] * len(pos)
                    idx = _accessor(js, binc, prim["indices"]) if "indices" in prim else range(len(pos))
                    mk, col = mats[prim["material"]] if "material" in prim else (0, (0.8, 0.8, 0.8))
                    for i in idx:
                        p = _game(_xf(m, pos[i]))
                        n = _game(_xf(m, nrm[i], 0.0))
                        ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
                        verts.extend((p[0] * UNIT, p[1] * UNIT, p[2] * UNIT, n[0] / ln, n[1] / ln, n[2] / ln,
                                      col[0], col[1], col[2], piv[0], piv[1], piv[2], role, mk, opt))
            elif not node.get("children"):
                p = _game(_xf(m, (0, 0, 0)))
                points.append((name, tuple(v * UNIT for v in p), part))
            for c in node.get("children", []):
                walk(c, m, part)

        ident = [[1 if i == j else 0 for j in range(4)] for i in range(4)]
        for ni in scene["nodes"]:
            walk(ni, ident, None)
        self.verts = array("f", verts)
        self.nverts = len(verts) // VSTRIDE
        self.tris = self.nverts // 3
        # attachment points: name -> (pos, role, pivot, glow colour or None)
        self.points = {}
        for name, p, part in points:
            role, piv = self.parts.get(part, (0, (0.0, 0.0, 0.0)))
            lit = name.startswith("eye") or name.startswith("glow")
            self.points[name] = (p, role, piv, self._glow_near(p, name.startswith("glow")) if lit else None)
        self.top = max((verts[i + 2] for i in range(0, len(verts), VSTRIDE)), default=UNIT)
        # the upper body bends about the hips (swing twist, a flinch, a zombie's hunch): the top of the legs
        legs = [piv[2] for role, piv in self.parts.values() if role in (2, 3)]
        self.legs = bool(legs)
        self.hip = max(legs) if legs else self.top * 0.4
        self.stagger = 0.0          # zombies' uneven gait and sway (set when first drawn as a zombie)
        self.idle_breathe = 0.012 if self.anim["breathe"] == 0 else 0.0     # a little breathing when standing

    def _glow_near(self, p, anywhere=False):
        """Colour of the glowing surface right at point p (eyes, cores), or None."""
        best, col = (1e12 if anywhere else (0.12 * UNIT) ** 2), None
        v = self.verts
        for i in range(0, len(v), VSTRIDE):
            if v[i + 13] != 1:
                continue
            d = (v[i] - p[0]) ** 2 + (v[i + 1] - p[1]) ** 2 + (v[i + 2] - p[2]) ** 2
            if d < best:
                best, col = d, (v[i + 6], v[i + 7], v[i + 8])
        return col


_MODELS = None


def models():
    """{name: Model} for every assets/models/*.glb (loaded once)."""
    global _MODELS
    if _MODELS is None:
        _MODELS = {}
        if os.path.isdir(MODEL_DIR):
            for fn in sorted(os.listdir(MODEL_DIR)):
                if fn.endswith(".glb"):
                    try:
                        _MODELS[fn[:-4]] = Model(fn[:-4], os.path.join(MODEL_DIR, fn))
                    except Exception as e:      # a broken file must never stop the game
                        print("models3d: could not load", fn, e)
    return _MODELS


def model_for(kind):
    ms = models()
    return ms.get(MODEL_FOR.get(kind, kind))


# =========================================================================== animation (shader + Python twin)
# The vertex shader and part_rot()/anim_point() below must do the same maths: the Python twin is
# used to find attachment points (eye glows, hands) on the moving model.
VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform vec4 a0;      // stride, bob, nod, breathe
uniform vec4 a1;      // wag, flap, hover, float
uniform vec4 a2;      // lunge, sway, arms (0 none 1 swing 2 reach), jaw
uniform vec4 a3;      // stagger (zombies), hip height, -, idle breathing
uniform float time;
uniform float up_k;   // stretch heights (tilted camera)
in vec3 in_pos;
in vec3 in_nrm;
in vec3 in_col;
in vec3 in_piv;
in vec3 in_info;      // role, material, optional-part bit + 1
in vec4 i_a;          // x, y, z, heading
in vec4 i_b;          // scale, walk phase (cycles), moving 0..1, attack 0..1
in vec4 i_tint;
in vec4 i_c;          // optional parts shown (bits), seed, -, white flash
in vec3 i_acc1;
in vec3 i_acc2;
in vec3 i_acc3;
in vec3 i_acc4;
in vec3 i_acc5;
in vec4 i_d;          // hurt flinch 0..1, swing 0..1 (survivors; 0 = not swinging), -, -
out vec4 v_col;       // colour (lit in the fragment shader - lighting3d.py)
out vec3 v_pos;       // world position
out vec3 v_nrm;
out float v_glow;     // 1: emissive material (not shaded)
out float v_flash;    // white hit flash

mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c); }
mat3 rotZ(float a) { float c = cos(a), s = sin(a); return mat3(c, s, 0.0, -s, c, 0.0, 0.0, 0.0, 1.0); }
mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c); }

// A survivor's swing (chop / mine / attack), k = 0..1 through it: wind up, strike, follow through, back.
// x = right arm angle, y = body twist, z = body lean. Mirrored by swing_curve() in Python.
vec3 swing(float k) {
    if (k <= 0.0) return vec3(0.0);
    float up = smoothstep(0.0, 0.3, k), down = smoothstep(0.3, 0.52, k), back = 1.0 - smoothstep(0.65, 1.0, k);
    return vec3(mix(mix(0.0, -2.7, up), -0.55, down), mix(mix(0.0, -0.45, up), 0.35, down),
                0.18 * down - 0.06 * up * (1.0 - down)) * back;
}

void main() {
    int opt = int(in_info.z + 0.5) - 1;
    if (opt >= 0 && ((int(i_c.x + 0.5) >> opt) & 1) == 0) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0); v_col = vec4(0.0);
        v_pos = vec3(0.0); v_nrm = vec3(0.0, 0.0, 1.0); v_glow = 0.0; v_flash = 0.0;
        return;
    }
    int role = int(in_info.x + 0.5);
    float ph = i_b.y * 6.2831853;
    float mv = i_b.z, at = i_b.w, seed = i_c.y;
    float stg = a3.x, fl = i_d.x;
    ph += stg * 0.55 * sin(ph);     // zombies limp: one step quick, the next dragged
    vec3 swg = swing(i_d.y);
    float sw = sin(ph);
    mat3 R = mat3(1.0);
    if (role == 2) R = rotY(a0.x * mv * sw);
    else if (role == 3) R = rotY(-a0.x * mv * sw);
    else if (role == 9) R = rotZ(a0.x * 0.6 * mv * sw);
    else if (role == 10) R = rotZ(-a0.x * 0.6 * mv * sw);
    else if (role == 1) {           // nod, plus looking about now and then when standing (zombies loll)
        float look = (1.0 - mv) * 0.3 * sin(time * 0.41 + seed * 2.3) * sin(time * 0.17 + seed);
        R = rotZ(look) * rotX(stg * 0.2 * sin(time * 0.7 + seed) + 0.25 * fl * sin(seed * 5.0))
            * rotY(a0.z * (mv * sin(ph * 2.0) + 0.35 * sin(time * 1.3 + seed)) + 0.3 * at - 0.35 * fl);
    }
    else if (role == 6) R = rotZ(a1.x * sin(time * (3.0 + 7.0 * mv) + seed));
    else if (role == 7) R = rotX(-a1.y * 0.7 * sin(time * 38.0 + seed));
    else if (role == 8) R = rotX(a1.y * 0.7 * sin(time * 38.0 + seed));
    else if (role == 11) R = rotY(a2.w * at + 0.05 * (1.0 + sin(time * 2.0 + seed)));
    else if (role == 4 || role == 5) {
        float side = role == 4 ? 1.0 : -1.0;
        float a;
        if (a2.z > 1.5) a = a2.y * sin(ph + side * 1.2) * (0.3 + mv) * 0.6 - 0.7 * at
                            + 0.04 * sin(time * 1.7 + seed + side);
        else if (a2.z > 0.5) a = -a0.x * 0.8 * mv * sw * side
                                 - (role == 5 ? (i_d.y > 0.0 ? -swg.x : 1.9 * at) : 0.5 * sin(3.14159 * i_d.y));
        else a = 0.08 * sin(time * 1.5 + seed + side) - 0.5 * at;
        R = rotY(a);
    }
    vec3 p = in_piv + R * (in_pos - in_piv);
    vec3 n = R * in_nrm;
    if (role != 2 && role != 3 && role != 9 && role != 10 && role != 12) {
        // the upper body about the hips: swing twist, flinching back when hurt, zombies' hunch and sway
        float lean = swg.z - 0.32 * fl + stg * (0.06 + 0.14 * mv + 0.06 * mv * sin(ph * 2.0));
        float roll = stg * (0.13 * sin(ph) * (0.35 + mv) + 0.05 * sin(time * 0.8 + seed)) + 0.1 * fl * sin(seed * 7.0);
        mat3 B = rotZ(swg.y) * rotY(lean) * rotX(roll);
        vec3 hip = vec3(0.0, 0.0, a3.y);
        p = hip + B * (p - hip);
        n = B * n;
    }
    if (role != 12) {
        float br = (a0.w + a3.w * (1.0 - mv)) * sin(time * 2.0 + seed);
        p.xy *= 1.0 + br;
        p.z *= 1.0 + br * 0.6;
        p.z += a0.y * mv * abs(sw) + a1.z + a1.w * sin(time * 2.2 + seed);
        p.x += a2.x * at - 4.0 * fl;
    }
    float s = i_b.x;
    mat3 H = rotZ(i_a.w);
    vec3 w = H * p * s + i_a.xyz;
    w.z *= up_k;
    n = normalize(H * n);
    gl_Position = window.projection * window.view * vec4(w, 1.0);
    int mk = int(in_info.y + 0.5);
    vec3 col = in_col;
    vec3 acc = mk == 2 ? i_acc1 : mk == 3 ? i_acc2 : mk == 4 ? i_acc3 : mk == 5 ? i_acc4 : mk == 6 ? i_acc5 : vec3(-1.0);
    if (acc.r >= 0.0) col = acc;
    v_col = vec4(col * i_tint.rgb, i_tint.a);
    v_pos = w;
    v_nrm = n;
    v_glow = mk == 1 ? 1.0 : 0.0;
    v_flash = i_c.w;
}
"""

# Lit per pixel (lighting3d.py is pasted in when the program is built): the sun as before, a sky / ground
# hemisphere instead of a flat ambient, the night's point lights (fires, torches) and a moonlight rim.
FS = """
#version 330
uniform vec3 light;   // towards the sun
in vec4 v_col;
in vec3 v_pos;
in vec3 v_nrm;
in float v_glow;
in float v_flash;
out vec4 f_color;
void main() {
    if (v_col.a <= 0.01) discard;
    vec3 n = normalize(v_nrm);
    vec3 rgb;
    if (v_glow > 0.5) {
        rgb = v_col.rgb * 1.15 * lt_light(v_pos, vec3(0.0));
    } else {
        vec3 sun = ((0.6 + 0.08 * n.z) * lt_hemi(n) + 0.5 * max(dot(n, light), 0.0)) * lt_sunlit(v_pos, n);
        rgb = v_col.rgb * sun * lt_light(v_pos, n) + lt_rimlight(v_pos, n) * (0.35 + v_col.rgb);
    }
    rgb += vec3(0.45) * v_flash;
    f_color = vec4(lt_fogged(rgb, v_pos), v_col.a);
}
"""


# The shadow pass (shadows3d.py): the same vertex shader seen from the sun, writing only depth.
SHADOW_FS = """
#version 330
in vec4 v_col;
void main() {
    if (v_col.a <= 0.01) discard;
}
"""


def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def _mm(a, b):
    return tuple(tuple(a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] for j in range(3)) for i in range(3))


def _mv(m, v):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2], m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


def _smooth(e0, e1, x):
    k = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return k * k * (3 - 2 * k)


def swing_curve(k):
    """A survivor's swing, k = 0..1 through it: (right arm angle, body twist, body lean). Mirrors swing() in VS."""
    if k <= 0:
        return 0.0, 0.0, 0.0
    up, down, back = _smooth(0.0, 0.3, k), _smooth(0.3, 0.52, k), 1.0 - _smooth(0.65, 1.0, k)
    arm = (0.0 + (-2.7 - 0.0) * up) * (1 - down) + -0.55 * down
    twist = (-0.45 * up) * (1 - down) + 0.35 * down
    lean = 0.18 * down - 0.06 * up * (1 - down)
    return arm * back, twist * back, lean * back


def part_rot(role, A, arms, ph, mv, at, t, seed, stg=0.0, fl=0.0, k=0.0):
    """The rotation (3 x 3 rows) the shader turns a part of this role by about its pivot, or None.
    Mirrors VS above (ph already has the zombies' limp in it)."""
    sw = math.sin(ph)
    if role == 2:
        return _ry(A["stride"] * mv * sw)
    if role == 3:
        return _ry(-A["stride"] * mv * sw)
    if role == 9:
        return _rz(A["stride"] * 0.6 * mv * sw)
    if role == 10:
        return _rz(-A["stride"] * 0.6 * mv * sw)
    if role == 1:
        look = (1 - mv) * 0.3 * math.sin(t * 0.41 + seed * 2.3) * math.sin(t * 0.17 + seed)
        return _mm(_mm(_rz(look), _rx(stg * 0.2 * math.sin(t * 0.7 + seed) + 0.25 * fl * math.sin(seed * 5.0))),
                   _ry(A["nod"] * (mv * math.sin(ph * 2) + 0.35 * math.sin(t * 1.3 + seed)) + 0.3 * at - 0.35 * fl))
    if role == 6:
        return _rz(A["wag"] * math.sin(t * (3 + 7 * mv) + seed))
    if role == 11:
        return _ry(A["jaw"] * at + 0.05 * (1 + math.sin(t * 2 + seed)))
    if role in (4, 5):
        side = 1.0 if role == 4 else -1.0
        if arms == 2:
            a = A["sway"] * math.sin(ph + side * 1.2) * (0.3 + mv) * 0.6 - 0.7 * at + 0.04 * math.sin(
                t * 1.7 + seed + side)
        elif arms == 1:
            if role == 5:
                extra = -swing_curve(k)[0] if k > 0 else 1.9 * at
            else:
                extra = 0.5 * math.sin(math.pi * k)
            a = -A["stride"] * 0.8 * mv * sw * side - extra
        else:
            a = 0.08 * math.sin(t * 1.5 + seed + side) - 0.5 * at
        return _ry(a)
    return None


def anim_point(model, point, inst, t, up_k=1.0):
    """World position of attachment `point` on a model drawn with instance tuple `inst`
    (x, y, z, heading, scale, phase, move, attack, seed[, flinch, swing])."""
    x, y, z, hd, sc, phase, mv, at, seed = inst[:9]
    fl, k = (inst[9], inst[10]) if len(inst) > 10 else (0.0, 0.0)
    stg = model.stagger
    p, role, piv, _ = model.points[point]
    ph = phase * math.tau
    ph += stg * 0.55 * math.sin(ph)
    R = part_rot(role, model.anim, model.arms, ph, mv, at, t, seed, stg, fl, k)
    q = (p[0] - piv[0], p[1] - piv[1], p[2] - piv[2])
    if R is not None:
        q = _mv(R, q)
    px, py, pz = q[0] + piv[0], q[1] + piv[1], q[2] + piv[2]
    A = model.anim
    if role not in (2, 3, 9, 10, 12):
        _, twist, lean = swing_curve(k)
        lean += -0.32 * fl + stg * (0.06 + 0.14 * mv + 0.06 * mv * math.sin(ph * 2))
        roll = stg * (0.13 * math.sin(ph) * (0.35 + mv) + 0.05 * math.sin(t * 0.8 + seed)) + 0.1 * fl * math.sin(seed * 7)
        B = _mm(_mm(_rz(twist), _ry(lean)), _rx(roll))
        hz = model.hip
        px, py, pz = _mv(B, (px, py, pz - hz))
        pz += hz
    if role != 12:
        br = (A["breathe"] + model.idle_breathe * (1 - mv)) * math.sin(t * 2 + seed)
        px *= 1 + br
        py *= 1 + br
        pz *= 1 + br * 0.6
        pz += A["bob"] * UNIT * mv * abs(math.sin(ph)) + A["hover"] * UNIT + A["float"] * UNIT * math.sin(t * 2.2 + seed)
        px += A["lunge"] * UNIT * at - 4.0 * fl
    c, s = math.cos(hd), math.sin(hd)
    return x + (c * px - s * py) * sc, y + (s * px + c * py) * sc, (z + pz * sc) * up_k


# =========================================================================== the mixin
class CreatureModels:
    """Mixed into View3D. Call models3d_draw() where creatures are drawn."""

    def models3d_mode(self, fp):
        """True when creatures should be drawn as 3D models in this view."""
        cfg = getattr(self, "cfg", {}) or {}
        mode = cfg.get("creature_models", "on")
        if mode == "off" or not models():
            return False
        return fp or mode == "on"

    def models3d_creatures(self, L, fp):
        """view3d.py's hook: every creature as a model, held items in hands, and the old cut-outs /
        draped bodies only for kinds that have no model yet."""
        cfg = getattr(self, "cfg", {}) or {}
        up = 1.0 if fp else float(cfg.get("creature_models_up", TILT_UP))
        done = self.models3d_draw(L, fp, up)
        self.models3d_held(self.stand)
        for lst, shape in ((L.animals, "body"), (L.zombies, "person"), (L.bosses, "boss"),
                           (self.player_list, "person")):
            if all(id(s) in done or not s.visible for s in lst):
                continue
            hidden = [s for s in lst if s.visible and id(s) in done]
            for s in hidden:
                s.visible = False
            if fp:
                self.mesh(lst, shape)
            else:
                self.stand(lst)
            for s in hidden:
                s.visible = True

    def _m3_init(self):
        if getattr(self, "_m3_prog", None):
            return
        ctx = self.ctx
        self._m3_prog = ctx.program(vertex_shader=VS, fragment_shader=lighting3d.inject(FS, frag=True))
        lighting3d.bind(self._m3_prog)
        self._m3_gpu = {}           # model name -> [geometry, instance buffer, capacity]
        self._m3_frame = {}         # model name -> list of instance floats (this view)
        self._m3_spots = []         # (model, point, inst) glows to light at night

    def _m3_geo(self, m, n):
        g = self._m3_gpu.get(m.name)
        if g is None or g[2] < n:
            cap = max(16, 1 << (n - 1).bit_length())
            ctx = self.ctx
            if g is None:
                vbo = ctx.buffer(data=m.verts)
            else:
                vbo = g[3]
            ibo = ctx.buffer(reserve=cap * ISTRIDE * 4)
            geo = ctx.geometry([
                BufferDescription(vbo, "3f 3f 3f 3f 3f", ["in_pos", "in_nrm", "in_col", "in_piv", "in_info"]),
                BufferDescription(ibo, "4f 4f 4f 4f 3f 3f 3f 3f 3f 4f",
                                  ["i_a", "i_b", "i_tint", "i_c", "i_acc1", "i_acc2", "i_acc3", "i_acc4", "i_acc5",
                                   "i_d"],
                                  instanced=True)], mode=ctx.TRIANGLES)
            g = self._m3_gpu[m.name] = [geo, ibo, cap, vbo]
        return g

    # ------------------------------------------------------------------ per creature state
    def _m3_motion(self, obj, x, y, m, scale, hurt=0.0, health=None, swing=None, swing_len=0.4):
        """Walk phase (by distance moved) and a smoothed 'moving' amount, once per game frame. Also:
        hurt  - anything that goes up when it's hit (hit flash, survivor's hurt timer): a flinch starts,
        health - survivors: a drop in health starts a flinch too (online clients only see health),
        swing - a survivor's swing timer (Survivor.swing jumps up on each attack): a swing animation starts
                that lasts swing_len seconds."""
        t = self.flame_t
        st = obj.__dict__.get("_m3")
        if st is None:
            st = obj.__dict__["_m3"] = [x, y, t, (id(obj) % 997) / 997.0, 0.0, None, 0.0, (id(obj) % 631) * 0.1,
                                        0.0, hurt, -1.0, swing_len, swing or 0.0, health]
        if st[2] != t:
            dt0 = max(0.0, t - st[2])
            st[8] = max(0.0, st[8] - dt0 * 4.0)       # the flinch eases off (~1/4 s)
            if hurt > st[9] + 0.01 or (health is not None and st[13] is not None and health < st[13] - 1.5):
                st[8] = 1.0
            st[9], st[13] = hurt, health
            if swing is not None:
                if swing > st[12] + 0.05:
                    st[10], st[11] = t, swing_len
                st[12] = swing
            dt = max(1e-4, t - st[2])
            d = math.hypot(x - st[0], y - st[1])
            if d > 120:           # teleported / respawned
                d = 0.0
            st[3] = (st[3] + d / max(1.0, m.stride_len * scale)) % 1.0
            want = min(1.0, d / dt / 55.0)
            st[4] += (want - st[4]) * min(1.0, dt * 9)
            st[0], st[1], st[2] = x, y, t
            st[6] = max(0.0, st[6] - dt * 3.5)        # attack lunge fades
        return st

    def _m3_attack(self, st, obj, cd, near_target=False):
        """Attack amount 0..1: a lunge when the attack cooldown restarts (host), or - for online
        clients, who don't get cooldowns - a gnash while touching a survivor."""
        if cd is not None and self.sim:
            if st[5] is None:          # first sight: no lunge for a cooldown we didn't see start
                st[5] = cd
            if cd > st[5] + 0.05:
                st[6] = 1.0
            st[5] = cd
        elif near_target:
            k = math.sin(self.flame_t * 5.0 + st[7])
            st[6] = max(st[6], k * k * k * k if k > 0 else 0.0)
        return st[6]

    def _m3_add(self, kind, obj, x, y, heading, scale, color, alpha, flash=0.0, flags=0, acc=None, attack_cd=None,
                near=False, z=0.0, extra_attack=0.0, hurt=0.0, health=None, swing=None, swing_len=0.4, flinch_k=1.0):
        m = model_for(kind)
        if m is None:
            return None
        st = self._m3_motion(obj, x, y, m, scale, hurt, health, swing, swing_len)
        at = max(self._m3_attack(st, obj, attack_cd, near), extra_attack)
        f = st[8]
        fl = f * f * (3 - 2 * f) * flinch_k
        k = (self.flame_t - st[10]) / st[11] if st[10] >= 0 else 1.0
        k = k if 0.0 <= k < 1.0 else 0.0
        inst = (x, y, z, heading, scale, st[3], st[4], at, st[7], fl, k)
        r, g, b = color[:3]
        a = (alpha if alpha is not None else 255) / 255
        acc = list(acc or ())
        acc += [NO_ACC] * (5 - len(acc))
        row = [x, y, z, heading, scale, st[3], st[4], at, r / 255, g / 255, b / 255, a,
               float(flags), st[7], 0.0, flash]
        for c in acc:
            row.extend(c if c[0] < 0 else (c[0] / 255, c[1] / 255, c[2] / 255))
        row.extend((fl, k, 0.0, 0.0))
        self._m3_frame.setdefault(m.name, []).extend(row)
        for name, (_, _, _, gcol) in m.points.items():
            if gcol is not None and (name.startswith("eye") or name.startswith("glow")):
                self._m3_spots.append((m, name, inst, gcol, a))
        return m, inst

    # ------------------------------------------------------------------ the frame
    def models3d_draw(self, L, fp, up_k=1.0):
        """Draw every animal, zombie, boss and survivor of layer L as a 3D model. Sprites whose kind
        has no model are left for the old drawing (returned as a set of ids to skip there: everything
        else). Call with the 3D camera on and depth testing enabled."""
        self._m3_init()
        self._m3_frame = {}
        self._m3_spots = []
        self._m3_hands = []
        self._m3_up = up_k
        done = set()
        near_r = 40
        sim = self.sim
        players = [p.sprite for p in self.players.values() if p.alive and p.layer == L.name] if not sim else []

        def touching(s, r):
            return any(abs(q.center_x - s.center_x) < r and abs(q.center_y - s.center_y) < r for q in players)

        for a in L.animals:
            if not a.visible:
                continue
            flags = 0
            acc = None
            if a.pet and a.armor:
                flags = 1 << OPTS["pet_armor"]
                acc = [GEAR_COL.get(a.armor, (150, 150, 150))]
            if self._m3_add(a.kind, a, a.center_x, a.center_y, a.heading, a.scale_x, a.color, a.alpha,
                            0.5 if a.flash > 0 else 0.0, flags, acc, getattr(a, "attack_cd", None),
                            touching(a, 34) if players else False, hurt=float(a.flash > 0)):
                done.add(id(a))
        for zb in L.zombies:
            if not zb.visible:
                continue
            m = model_for(zb.kind)
            if m is not None and not m.stagger and m.arms == 2 and m.legs:
                m.stagger = STAGGER.get(m.name, 0.4)       # walking dead stagger and lurch
            if self._m3_add(zb.kind, zb, zb.center_x, zb.center_y, zb.heading, zb.scale_x, zb.color, zb.alpha,
                            0.5 if zb.flash > 0 else 0.0, 0, None, zb.attack_cd,
                            touching(zb, zb.radius + near_r) if players else False, hurt=float(zb.flash > 0)):
                done.add(id(zb))
        for b in L.bosses:
            if not b.visible:
                continue
            st_k = {"windup": 0.7, "charge": 1.0}.get(getattr(b, "state", ""), 0.0)
            if self._m3_add(b.kind, b, b.center_x, b.center_y, b.heading, b.scale_x, b.color, b.alpha,
                            0.5 if b.flash > 0 else 0.0, 0, None, b.attack_cd,
                            touching(b, b.radius + near_r) if players else False, extra_attack=st_k,
                            hurt=float(b.flash > 0), flinch_k=0.45):
                done.add(id(b))
        for p in self.players.values():
            s = p.sprite
            if not s.visible or p.layer != L.name:
                continue
            eq = getattr(p, "equip", {}) or {}
            flags = 0
            acc = [JACKETS[p.id % 4], HAIR[p.id % 4], NO_ACC, NO_ACC, NO_ACC]
            for slot, bit, i in (("body", "armor", 2), ("head", "helmet", 3), ("cloak", "cloak", 4)):
                it = eq.get(slot)
                if it:
                    flags |= 1 << OPTS[bit]
                    acc[i] = GEAR_COL.get(it, (150, 150, 150))
            sw = min(1.0, p.swing / 0.2) if getattr(p, "swing", 0) > 0 else 0.0
            col = (255, 140, 140) if getattr(p, "hurt", 0) > 0 else s.color
            # a chop / mine / attack swing timed to the held item's cooldown (online clients know what
            # everyone holds); bows keep the old "arm up to aim"
            item = p.hotbar[p.selected] if 0 <= p.selected < len(p.hotbar) else None
            info = ITEMS.get(item or "", {})
            ranged = bool(info.get("ranged"))
            got = self._m3_add("survivor", s, s.center_x, s.center_y, p.face, 1.0, col, s.alpha, 0.0, flags, acc,
                               extra_attack=sw if ranged else 0.0, hurt=getattr(p, "hurt", 0.0),
                               health=getattr(p, "health", None), swing=None if ranged else getattr(p, "swing", 0.0),
                               swing_len=max(0.26, min(0.62, info.get("cooldown", 0.45) * 0.95)))
            if got:
                done.add(id(s))
                self._m3_hands.append((p, got))
        self._m3_render()
        return done

    def _m3_render(self):
        prog = self._m3_prog
        ms = models()
        sx, sy = self._progs3d[1]["sun"]
        lx, ly, lz = -sx, -sy, 1.4
        ln = math.sqrt(lx * lx + ly * ly + lz * lz)
        prog.set_uniform_safe("light", (lx / ln, ly / ln, lz / ln))     # (not in the shadow program)
        prog["time"] = float(self.flame_t % 1000.0)
        prog["up_k"] = float(self._m3_up)
        ctx = self.ctx
        ctx.enable(ctx.BLEND)
        for name, rows in self._m3_frame.items():
            m = ms[name]
            n = len(rows) // ISTRIDE
            geo, ibo, cap, _ = self._m3_geo(m, n)
            ibo.orphan()
            data = array("f", rows)
            ibo.write(data)
            A = m.anim
            prog["a0"] = (A["stride"], A["bob"] * UNIT, A["nod"], A["breathe"])
            prog["a1"] = (A["wag"], A["flap"], A["hover"] * UNIT, A["float"] * UNIT)
            prog["a2"] = (A["lunge"] * UNIT, A["sway"], float(m.arms), A["jaw"])
            prog["a3"] = (m.stagger, m.hip, 0.0, m.idle_breathe)
            geo.render(prog, instances=n)

    def models3d_held(self, stand):
        """Put each survivor's held item (weapon, tool, torch) in their model's right hand.
        `stand(list, ...)` is View3D.stand. Call right after models3d_draw."""
        if not self._m3_hands:
            return
        t = self.flame_t
        up = self._progs3d[1]["up_scale"] or 1.0
        moved = []
        for p, (m, inst) in self._m3_hands:
            h = p.held
            if not h.visible or "hand_r" not in m.points:
                continue
            hx, hy, hz = anim_point(m, "hand_r", inst, t, self._m3_up)
            moved.append((h, h.center_x, h.center_y, h.depth))
            h.center_x, h.center_y = hx, hy
            h.depth = max(0.0, hz / up - h.height * 0.35)
        if moved:
            stand(self.held_list, nudge=0)
        for h, x, y, d in moved:
            h.center_x, h.center_y, h.depth = x, y, d

    def models3d_glows(self, dk):
        """Night glow on every eye / glowing core attachment point (additive, after the lighting)."""
        if not self._m3_spots or dk <= 0:
            return
        t = self.flame_t
        out = []
        for m, name, inst, col, a in self._m3_spots:
            x, y, z = anim_point(m, name, inst, t, self._m3_up)
            big = name.startswith("glow")
            size = (0.35 if big else 0.09) * UNIT * inst[4] * (0.85 + 0.15 * math.sin(t * 3 + inst[8]))
            out.extend((x, y, z, size, col[0], col[1], col[2], (0.55 if big else 0.95) * dk * a))
        ctx = self.ctx
        from pyglet import gl
        gl.glDepthMask(gl.GL_FALSE)
        self._fx_points(2, array("f", out), blend=(ctx.SRC_ALPHA, ctx.ONE), hot=0.6)
        gl.glDepthMask(gl.GL_TRUE)
