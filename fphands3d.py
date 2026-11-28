"""
fphands3d.py - FIRST PERSON: your own arms and hands, holding a real 3D version of what you hold.

Instead of a big flat picture of the item in the corner, first person shows a little low-poly right arm
(sleeve in your jacket colour, with an armour bracer when you wear body armour) holding a small 3D model
of the selected hotbar item. Everything here is built in Python from boxes, prisms and balls when the game
starts - no Blender, no files:

  * tools and weapons are held in the fist (axes, pickaxes, hoe, hammers, swords, spears, the fishing rod),
  * the bow is held out in the left hand with an arrow nocked; the right hand draws the string,
  * the torch has a flickering flame, sheds embers and lights your hands,
  * food, drinks, potions, the spellbook and seeds rest on an open palm,
  * building items are a little block (walls in their own material, everything else wears its icon),
  * anything else is a small card with the item's icon on it.

How it moves (all worked out here each frame from the same state the rest of the game uses, so it works
for online clients too):
  walking bob (stronger when sprinting), sway that lags behind the mouse look, slow breathing when idle,
  a swing for each attack (chop / slash / stab / throw / cast, timed to the item's cooldown), the bow
  drawing between shots, raising food to your mouth when you eat it, a jolt when you get hurt, and
  lowering / raising when you change item.

Drawing: called from view3d.draw_world_3d after the standing things and particles (still in the "lit"
stage of lighting3d.py, so sun, shadows, campfires and your own torch light the arms just like the world).
It uses its own near projection and a tiny slice of the depth range (glDepthRange), so the arms are never
cut by a wall you walk right up to, yet the world's depth values are left alone.

If anything here fails on an odd graphics driver it prints once and firstperson.py goes back to the old
flat picture.
"""
import math
import random
from array import array

from arcade.gl import BufferDescription
from pyglet import gl
from pyglet.math import Mat4

import lighting3d

SKIN = (226, 182, 146)              # the survivor model's skin (tools/blender/models/survivor.py)
WOOD, DARK_WOOD, LEATHER = (138, 96, 58), (96, 64, 38), (112, 76, 46)
STONE, IRON, STEEL = (138, 136, 132), (170, 176, 188), (206, 212, 222)
VSTRIDE = 12                        # x y z  nx ny nz  r g b  u v  kind
KIND_LIT, KIND_GLOW, KIND_TEX, KIND_FLAME = 0.0, 1.0, 2.0, 3.0

R_SHOULDER = (15.0, -21.0, -3.0)    # where the arms come from (camera space: x right, y up, z forward)
L_SHOULDER = (-15.0, -21.0, -3.0)
NEAR, FAR = 0.5, 400.0
DEPTH_SLICE = 0.004                 # the arms' share of the depth range (in front of the whole world)
SCALE = 0.72                        # hands and items are modelled a bit big; this sizes them on screen

# =========================================================================== shaders
VS = """
#version 330
uniform mat4 proj;
uniform mat4 view;
uniform mat4 model;
uniform float time;
in vec3 in_pos;
in vec3 in_nrm;
in vec3 in_col;
in vec2 in_uv;
in float in_kind;
out vec3 v_pos;
out vec3 v_nrm;
out vec3 v_col;
out vec2 v_uv;
out float v_kind;
void main() {
    vec3 p = in_pos;
    if (in_kind > 2.5) {        // flame: flickers and licks, more towards its tip (uv.y = 0 base .. 1 tip)
        float h = in_uv.y;
        p.x += (sin(time * 13.0 + p.y * 0.9) * 0.45 + sin(time * 23.0 + p.z) * 0.2) * h;
        p.z += cos(time * 11.0 + p.y * 0.7) * 0.45 * h;
        p.y += sin(time * 17.0) * 0.6 * h;
    }
    vec4 w = model * vec4(p, 1.0);
    v_pos = w.xyz;
    v_nrm = mat3(model) * in_nrm;
    v_col = in_col;
    v_uv = in_uv;
    v_kind = in_kind;
    gl_Position = proj * view * w;
}
"""

FS = """
#version 330
uniform vec3 light;         // towards the sun
uniform vec4 torch;         // your own torch flame: world position, strength (0 = none)
uniform sampler2D icon;
in vec3 v_pos;
in vec3 v_nrm;
in vec3 v_col;
in vec2 v_uv;
in float v_kind;
out vec4 f_color;
void main() {
    vec3 col = v_col;
    if (v_kind > 1.5 && v_kind < 2.5) {             // an item's icon
        vec4 t = texture(icon, v_uv);
        if (t.a < 0.5) discard;
        col *= t.rgb;
    }
    if (v_kind > 0.5 && (v_kind < 1.5 || v_kind > 2.5)) {    // shines by itself (flames, glowing blades)
        f_color = vec4(col, 1.0);
        return;
    }
    vec3 n = normalize(v_nrm);
    vec3 sun = ((0.62 + 0.08 * n.z) * lt_hemi(n) + 0.5 * max(dot(n, light), 0.0)) * lt_sunlit(v_pos, n);
    vec3 lit = lt_light(v_pos, n);
    if (torch.w > 0.0) {        // the flame right next to your hand
        vec3 d = torch.xyz - v_pos;
        float dist = length(d);
        float f = torch.w * (1.0 - smoothstep(4.0, 60.0, dist));
        lit = min(lit + vec3(0.8, 0.55, 0.3) * f * (0.35 + 0.65 * max(dot(n, d / max(dist, 1e-3)), 0.0)),
                  vec3(1.05, 0.95, 0.82));
    }
    vec3 rgb = col * sun * lit + lt_rimlight(v_pos, n) * (0.3 + col) * 0.6;
    f_color = vec4(lt_fogged(rgb, v_pos), 1.0);
}
"""


# =========================================================================== little maths
def _sub(a, b):
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _add(a, b):
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _mul(a, k):
    return a[0] * k, a[1] * k, a[2] * k


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return a[0] / n, a[1] / n, a[2] / n


def rot(pitch=0.0, yaw=0.0, roll=0.0):
    """3 x 3 rotation (rows) = yaw (about y) * pitch (about x) * roll (about z).
    Camera space is x right, y up, z forward: + pitch leans an item's top forward, + yaw turns its front
    to the right, + roll tips its top to the left."""
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cr, sr = math.cos(roll), math.sin(roll)
    rx = ((1, 0, 0), (0, cp, -sp), (0, sp, cp))
    ry = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    rz = ((cr, -sr, 0), (sr, cr, 0), (0, 0, 1))
    return _mm(ry, _mm(rx, rz))


def _scaled(m, k=None):
    """A rotation that also sizes things by k (default SCALE)."""
    k = SCALE if k is None else k
    return tuple(tuple(v * k for v in row) for row in m)


def _mm(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _mv(m, v):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


class Pose:
    """Where a part sits in camera space: rotation m (rows) and position t."""

    def __init__(self, m, t):
        self.m, self.t = m, t

    def at(self, p):
        """A point in the part's own space -> camera space."""
        return _add(_mv(self.m, p), self.t)


# =========================================================================== mesh building
class Mesh:
    """Flat-shaded triangles. Every solid is convex, so each face's normal is simply turned to point away
    from the solid's centre (no worrying about winding order)."""

    def __init__(self):
        self.v = []

    def tri(self, a, b, c, col, kind=KIND_LIT, centre=None, uv=((0, 0), (0, 0), (0, 0)), nrm=None):
        n = nrm or _norm(_cross(_sub(b, a), _sub(c, a)))
        if centre is not None and nrm is None:
            mid = _mul(_add(_add(a, b), c), 1 / 3)
            if _dot(n, _sub(mid, centre)) < 0:
                n = _mul(n, -1)
        r, g, bl = (k / 255 for k in col)
        for p, t in zip((a, b, c), uv):
            self.v.extend((p[0], p[1], p[2], n[0], n[1], n[2], r, g, bl, t[0], t[1], kind))

    def quad(self, a, b, c, d, col, kind=KIND_LIT, centre=None, uv=None):
        uv = uv or ((0, 0), (1, 0), (1, 1), (0, 1))
        self.tri(a, b, c, col, kind, centre, (uv[0], uv[1], uv[2]))
        self.tri(a, c, d, col, kind, centre, (uv[0], uv[2], uv[3]))

    def box(self, c, size, col, kind=KIND_LIT, m=None, tex=False):
        """Box centred on c with size (x, y, z), turned by rotation m. tex: every face wears the icon."""
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        m = m or ((1, 0, 0), (0, 1, 0), (0, 0, 1))

        def P(x, y, z):
            return _add(_mv(m, (x * hx, y * hy, z * hz)), c)
        faces = (((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),        # front (+z)
                 ((1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)),    # back
                 ((1, -1, 1), (1, -1, -1), (1, 1, -1), (1, 1, 1)),        # right
                 ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)),    # left
                 ((-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1)),        # top
                 ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)))    # bottom
        for f in faces:
            pts = [P(*q) for q in f]
            self.quad(*pts, col, KIND_TEX if tex else kind, c)

    def prism(self, p0, p1, r0, r1, col, sides=6, kind=KIND_LIT, twist=0.0, flame=False):
        """A tube from p0 to p1 (radius r0 -> r1; a radius can be (rx, rz) for a flattened one, and 0 makes
        a cone). Capped at both ends."""
        r0 = r0 if isinstance(r0, tuple) else (r0, r0)
        r1 = r1 if isinstance(r1, tuple) else (r1, r1)
        axis = _sub(p1, p0)
        ax = _norm(axis)
        ref = (0.0, 0.0, 1.0) if abs(ax[2]) < 0.9 else (1.0, 0.0, 0.0)
        u = _norm(_cross(ref, ax))
        w = _cross(ax, u)
        if abs(ax[1]) > 0.9:          # along y: keep x / z for the flattened radii (blades)
            u, w = (1.0, 0.0, 0.0), _norm(_cross((1.0, 0.0, 0.0), ax))
        centre = _mul(_add(p0, p1), 0.5)

        def ring(p, r):
            out = []
            for i in range(sides):
                a = twist + math.tau * i / sides
                out.append(_add(p, _add(_mul(u, math.cos(a) * r[0]), _mul(w, math.sin(a) * r[1]))))
            return out
        a, b = ring(p0, r0), ring(p1, r1)
        uv0 = ((0, 0),) * 3                         # flames: uv.y = how high up (0 base .. 1 tip)
        uv1 = ((0, 1),) * 3 if flame else uv0
        for i in range(sides):
            j = (i + 1) % sides
            if flame:
                self.tri(a[i], a[j], b[j], col, kind, centre, ((0, 0), (0, 0), (0, 1)))
                self.tri(a[i], b[j], b[i], col, kind, centre, ((0, 0), (0, 1), (0, 1)))
            else:
                self.quad(a[i], a[j], b[j], b[i], col, kind, centre)
            if max(r0) > 0:
                self.tri(p0, a[i], a[j], col, kind, centre, uv0)
            if max(r1) > 0:
                self.tri(p1, b[j], b[i], col, kind, centre, uv1)

    def ball(self, c, r, col, kind=KIND_LIT, seg=7, rings=4, flame=False):
        """A low-poly ball; r can be (rx, ry, rz) for an egg / a loaf."""
        rx, ry, rz = r if isinstance(r, tuple) else (r, r, r)
        pts = []
        for i in range(rings + 1):
            th = math.pi * i / rings
            row = []
            for j in range(seg):
                ph = math.tau * j / seg + (0.5 * i)
                row.append((c[0] + rx * math.sin(th) * math.cos(ph), c[1] + ry * math.cos(th),
                            c[2] + rz * math.sin(th) * math.sin(ph)))
            pts.append(row)
        for i in range(rings):
            for j in range(seg):
                k = (j + 1) % seg
                a, b, cc, d = pts[i][j], pts[i][k], pts[i + 1][k], pts[i + 1][j]
                if flame:       # uv.y: how high up the flame (the shader licks the top most)
                    def h(p):
                        return 0, max(0.0, (p[1] - c[1]) / ry * 0.5 + 0.5)
                    self.tri(a, b, cc, col, kind, c, (h(a), h(b), h(cc)))
                    self.tri(a, cc, d, col, kind, c, (h(a), h(cc), h(d)))
                else:
                    if i > 0:
                        self.tri(a, b, cc, col, kind, c)
                    if i < rings - 1:
                        self.tri(a, cc, d, col, kind, c)

    def merge(self, other, pose=None):
        """Add another mesh, moved by pose (a Pose in this mesh's space)."""
        v = other.v
        if pose is None:
            self.v.extend(v)
            return
        for i in range(0, len(v), VSTRIDE):
            p = pose.at(v[i:i + 3])
            n = _mv(pose.m, v[i + 3:i + 6])
            self.v.extend((p[0], p[1], p[2], n[0], n[1], n[2]) + tuple(v[i + 6:i + VSTRIDE]))


def _shade(col, k):
    return tuple(max(0, min(255, int(c * k))) for c in col)


# =========================================================================== hands
def fist(skin=SKIN):
    """A right fist round a handle running along y through the origin (knuckles forward, thumb on top)."""
    m = Mesh()
    m.box((0.4, 0.0, -0.5), (4.4, 4.6, 4.6), skin)                   # the fist
    dark = _shade(skin, 0.88)
    for i in range(4):                                                # finger ridges across the front
        m.box((-1.4, 1.6 - i * 1.1, 1.0), (2.2, 1.0, 2.4), dark if i % 2 else skin)
    m.box((-0.6, 2.4, -1.2), (3.2, 1.3, 1.8), skin)                  # thumb over the top
    return m


def palm(skin=SKIN):
    """An open right hand, palm up, with whatever it holds resting on the origin."""
    m = Mesh()
    m.box((0.0, -1.1, -0.6), (5.6, 1.8, 6.0), skin)                  # palm
    dark = _shade(skin, 0.9)
    for i in range(4):                                                # fingers curling up a little
        m.box((-2.1 + i * 1.4, -0.4, 3.0), (1.2, 1.3, 1.8), dark if i % 2 else skin)
    m.box((3.2, 0.0, -0.4), (1.3, 1.4, 3.4), skin)                   # thumb along the side
    return m


WRIST_FIST = (2.0, -0.8, -3.2)       # where the forearm meets the hand (the hand's own space)
WRIST_PALM = (0.5, -1.6, -3.6)


# =========================================================================== the items
def _handle(m, y0, y1, r=0.85, col=WOOD):
    m.prism((0, y0, 0), (0, y1, 0), r, r * 0.92, col, sides=6)


def _axe(head, edge):
    m = Mesh()
    _handle(m, -4, 22)
    m.box((0, 19.5, 1.0), (1.6, 4.4, 3.6), head)                     # the head
    m.box((0, 19.5, 4.2), (0.7, 6.4, 2.8), edge)                     # the blade
    m.box((0, 19.5, -1.4), (1.4, 2.6, 1.6), _shade(head, 0.8))      # the back
    m.box((0, 16.5, 0), (2.0, 1.4, 2.0), LEATHER)                     # binding
    return m


def _pick(head, tip):
    m = Mesh()
    _handle(m, -4, 21)
    m.box((0, 20.0, 0), (2.4, 3.0, 2.6), head)
    m.prism((0, 20.0, 1.0), (0, 18.0, 9.0), (1.2, 1.0), (0.2, 0.2), tip, sides=4)
    m.prism((0, 20.0, -1.0), (0, 18.4, -7.0), (1.2, 1.0), (0.2, 0.2), head, sides=4)
    return m


def _hoe():
    m = Mesh()
    _handle(m, -4, 24)
    m.box((0, 23.5, 1.4), (1.6, 1.8, 2.8), IRON)
    m.box((0, 21.8, 3.6), (4.6, 4.0, 0.6), IRON)
    return m


def _hammer(head, size=1.0, core=None, length=16):
    m = Mesh()
    _handle(m, -4, length, 0.85 * min(size, 1.3))
    m.box((0, length - 1.2 * size, 0), (3.2 * size, 3.4 * size, 7.5 * size), head)
    m.box((0, length - 1.2 * size, 3.9 * size), (2.6 * size, 2.8 * size, 0.6), _shade(head, 1.2))
    if core:
        m.box((0, length - 1.2 * size, 0), (3.4 * size, 1.0 * size, 2.0 * size), core, KIND_GLOW)
    return m


def _club():
    m = Mesh()
    m.prism((0, -4, 0), (0, 20, 0), 0.9, 2.6, WOOD, sides=7)
    for y, a in ((9, 0.4), (13, 2.2), (17, 4.1)):
        m.box((math.cos(a) * 2.0, y, math.sin(a) * 2.0), (1.0, 1.0, 1.0), DARK_WOOD)
    return m


def _spear(tip, glow=False, shaft=WOOD):
    m = Mesh()
    m.prism((0, -12, 0), (0, 34, 0), 0.7, 0.65, shaft, sides=6)
    m.prism((0, 33, 0), (0, 35.5, 0), 1.0, 1.0, LEATHER, sides=6)
    m.prism((0, 35, 0), (0, 37, 0), (0.6, 1.5), (0.7, 1.9), tip, sides=4, kind=KIND_GLOW if glow else KIND_LIT)
    m.prism((0, 37, 0), (0, 43, 0), (0.7, 1.9), 0.0, tip, sides=4, kind=KIND_GLOW if glow else KIND_LIT)
    return m


def _sword(blade, guard=IRON, grip=LEATHER, glow=False, length=19):
    m = Mesh()
    k = KIND_GLOW if glow else KIND_LIT
    m.prism((0, -3.2, 0), (0, 3.0, 0), 0.8, 0.8, grip, sides=6)
    m.ball((0, -3.8, 0), 1.1, guard, seg=6, rings=3)
    m.box((0, 3.6, 0), (1.5, 1.2, 7.2), guard)
    m.prism((0, 4.2, 0), (0, 4.2 + length, 0), (0.45, 1.5), (0.45, 1.35), blade, sides=4, kind=k)
    m.prism((0, 4.2 + length, 0), (0, 8.2 + length, 0), (0.45, 1.35), 0.0, blade, sides=4, kind=k)
    return m


def _fang():
    m = Mesh()
    m.prism((0, -3.2, 0), (0, 3.0, 0), 0.9, 0.9, (70, 82, 50), sides=6)
    m.box((0, 3.4, 0), (2.0, 1.2, 4.4), (96, 128, 60))
    pts = [(0, 4 + i * 3.6, -0.25 * i * i) for i in range(7)]
    for i in range(6):
        r0, r1 = 1.7 * (1 - i / 6) + 0.2, 1.7 * (1 - (i + 1) / 6) + 0.05
        m.prism(pts[i], pts[i + 1], (0.6, r0), (0.6, r1), (226, 236, 206), sides=4)
    return m


def _whip():
    m = Mesh()
    m.prism((0, -3.5, 0), (0, 4, 0), 0.9, 0.9, (84, 60, 40), sides=6)
    p = (0.0, 4.0, 0.0)
    for i in range(10):                 # a thorny vine curling forward
        q = (math.sin(i * 0.8) * 2.0, 4 + (i + 1) * 2.6, (i + 1) * 0.9 - 0.06 * (i + 1) ** 2)
        m.prism(p, q, 0.75 - i * 0.05, 0.7 - i * 0.05, (70, 112, 48), sides=5)
        m.prism(q, _add(q, (1.2, 0.6, 0.4)), 0.35, 0.0, (196, 210, 150), sides=3)
        p = q
    return m


def _rod():
    m = Mesh()
    m.prism((0, -4, 0), (0, 40, 0), 0.75, 0.22, DARK_WOOD, sides=5)
    m.prism((0, -2, 0), (0, 4, 0), 0.95, 0.95, LEATHER, sides=6)
    m.prism((1.4, 1.0, 0), (2.8, 1.0, 0), 1.6, 1.6, IRON, sides=7)          # the reel
    m.prism((0, 40, 0), (0.6, 30, 1.0), 0.08, 0.08, (230, 230, 230), sides=3)   # line
    m.ball((0.6, 29.5, 1.0), 0.9, (220, 50, 40), seg=6, rings=3)          # bobber
    return m


def _torch():
    m = Mesh()
    m.prism((0, -7, 0), (0, 14, 0), 0.85, 1.0, WOOD, sides=6)
    m.prism((0, 12, 0), (0, 17, 0), 1.7, 1.9, (70, 52, 36), sides=6)
    m.prism((0, 13.5, 0), (0, 14.5, 0), 2.0, 2.0, (120, 96, 60), sides=6)
    flame(m, (0, 16.5, 0), 1.0)
    return m


def flame(m, base, k):
    """A flickering flame on top of base (the shader licks it about)."""
    bx, by, bz = base
    m.ball((bx, by + 2.4 * k, bz), (1.9 * k, 2.6 * k, 1.9 * k), (255, 150, 40), KIND_FLAME, seg=7, rings=4,
           flame=True)
    m.prism((bx, by + 3.2 * k, bz), (bx, by + 8.5 * k, bz), 1.7 * k, 0.0, (255, 196, 70), sides=6,
            kind=KIND_FLAME, flame=True)
    m.ball((bx, by + 2.6 * k, bz), (1.1 * k, 1.8 * k, 1.1 * k), (255, 240, 180), KIND_FLAME, seg=6, rings=3,
           flame=True)


def _book():
    m = Mesh()
    m.box((0, 0.9, 0), (6.4, 1.8, 7.6), (96, 54, 128))
    m.box((0.35, 0.9, 0), (5.6, 1.3, 7.0), (240, 232, 210))
    m.box((-3.0, 0.9, 0), (0.7, 2.0, 7.7), (70, 40, 100))
    m.box((0.4, 1.85, 0), (2.0, 0.2, 2.0), (250, 210, 90), KIND_GLOW)      # the rune on the cover
    return m


def _pot():
    m = Mesh()
    m.ball((0, 3.0, 0), 3.0, (176, 96, 60), seg=8, rings=5)
    m.prism((0, 5.4, 0), (0, 6.6, 0), 1.3, 1.5, (150, 80, 50), sides=7)
    m.prism((0, 6.6, 0), (0.6, 8.2, 0.3), 0.3, 0.25, (220, 210, 180), sides=4)
    m.ball((0.6, 8.6, 0.3), (0.7, 0.9, 0.7), (255, 170, 50), KIND_FLAME, seg=5, rings=3, flame=True)
    return m


def _bow(limb):
    """The bow in the LEFT hand: grip on the origin, limbs along y, curving away from you (+z) at the
    tips; the string runs between the tips (TIPS) on the near side."""
    m = Mesh()
    pts = []
    for i in range(9):
        a = (i / 8) * 2 - 1
        pts.append((0.0, a * 15.0, 2.0 - 3.2 * a * a + 1.4 * a ** 4))
    for i in range(8):
        r = 0.9 if 2 <= i <= 5 else 0.7
        m.prism(pts[i], pts[i + 1], (0.7, r + 0.15), (0.7, r), limb, sides=5)
    m.prism((0, -2.6, 1.8), (0, 2.6, 1.8), 1.1, 1.1, LEATHER, sides=6)
    m.merge(fist(), Pose(rot(roll=math.pi), (0.3, 0, 1.6)))
    return m


BOW_TIPS = ((0.0, 15.0, 0.2), (0.0, -15.0, 0.2))
NOCK_Y = 2.8                    # the arrow rests just above the hand holding the bow


def _arrow():
    """Along +z from the nock (origin)."""
    m = Mesh()
    m.prism((0, 0, 0), (0, 0, 27), 0.35, 0.35, (196, 160, 110), sides=4)
    m.prism((0, 0, 27), (0, 0, 30.5), (0.4, 1.1), 0.0, (150, 150, 158), sides=4)
    for a in (0, 2.1, 4.2):
        d = (math.cos(a) * 1.3, math.sin(a) * 1.3, 0)
        m.quad((0, 0, 1.0), _add(d, (0, 0, 1.6)), _add(d, (0, 0, 5)), (0, 0, 5.5), (230, 230, 225))
    return m


# --------------------------------------------------------------------- things held on the palm
def _berries():
    m = Mesh()
    for x, y, z in ((0, 1.2, 0), (1.9, 1.1, 0.6), (-1.7, 1.1, 0.8), (0.4, 1.1, 2.0), (0.6, 2.8, 0.7),
                    (-0.6, 1.1, -1.6)):
        m.ball((x, y, z), 1.25, (196, 34, 48), seg=6, rings=3)
    m.box((0.4, 3.9, 0.6), (2.6, 0.3, 1.2), (70, 140, 60))
    return m


def _flask(body, neck=(120, 90, 60), glass=False, cork=(176, 140, 96)):
    m = Mesh()
    k = KIND_LIT
    m.prism((0, 0, 0), (0, 5.0, 0), 2.6, 2.4, body, sides=8, kind=k)
    m.prism((0, 5.0, 0), (0, 6.4, 0), 2.4, 1.0, body, sides=8, kind=k)
    m.prism((0, 6.4, 0), (0, 8.0, 0), 0.9, 0.9, neck, sides=6)
    m.prism((0, 8.0, 0), (0, 8.9, 0), 1.0, 0.9, cork, sides=6)
    if glass:
        m.box((0, 2.5, 2.3), (2.0, 3.0, 0.4), _shade(body, 1.5), KIND_GLOW)    # the potion shining through
    return m


def _meat(col, bone=True):
    m = Mesh()
    m.ball((0, 1.8, 0.4), (3.0, 1.8, 2.4), col, seg=7, rings=4)
    m.ball((-0.8, 2.6, 0.0), (1.6, 1.0, 1.4), _shade(col, 1.15), seg=6, rings=3)
    if bone:
        m.prism((1.8, 1.6, -1.0), (4.6, 1.8, -2.6), 0.55, 0.5, (236, 228, 210), sides=5)
        m.ball((4.8, 1.8, -2.7), 0.9, (236, 228, 210), seg=5, rings=3)
    return m


def _fish(col):
    m = Mesh()
    m.ball((0, 1.5, 0), (1.3, 1.6, 4.0), col, seg=7, rings=4)
    m.tri((0, 1.5, -3.4), (0, 3.4, -6.0), (0, -0.4, -6.0), _shade(col, 0.85), nrm=(1, 0, 0))
    m.tri((0, 1.5, -3.4), (0, -0.4, -6.0), (0, 3.4, -6.0), _shade(col, 0.85), nrm=(-1, 0, 0))
    m.ball((0.9, 2.0, 2.6), 0.35, (20, 20, 20), seg=4, rings=2)
    return m


def _bowl(top):
    m = Mesh()
    m.prism((0, 0, 0), (0, 2.6, 0), 2.4, 3.6, (126, 84, 50), sides=9)
    m.prism((0, 2.5, 0), (0, 2.7, 0), 3.2, 3.2, top, sides=9)
    for x, z in ((1.0, 0.5), (-0.9, -0.7), (0.3, -1.4)):
        m.ball((x, 2.8, z), 0.6, _shade(top, 1.3), seg=5, rings=2)
    return m


def _jar(col, lid=(176, 140, 96), glow=False):
    m = Mesh()
    m.prism((0, 0, 0), (0, 4.4, 0), 2.6, 2.6, col, sides=8, kind=KIND_GLOW if glow else KIND_LIT)
    m.prism((0, 4.4, 0), (0, 5.4, 0), 2.0, 2.0, lid, sides=8)
    return m


def _bread():
    m = Mesh()
    m.ball((0, 1.8, 0), (2.6, 1.8, 4.2), (204, 150, 84), seg=7, rings=4)
    for z in (-1.6, 0, 1.6):
        m.box((0, 3.4, z), (2.0, 0.3, 0.5), (236, 200, 140))
    return m


def _carrot():
    m = Mesh()
    m.prism((0, 1.4, -2.6), (0, 1.0, 4.8), 1.4, 0.0, (236, 120, 36), sides=6)
    for a in (-0.5, 0, 0.5):
        m.prism((0, 1.4, -2.6), (math.sin(a) * 1.6, 3.6, -4.0), 0.35, 0.1, (80, 150, 60), sides=3)
    return m


def _bandage():
    m = Mesh()
    m.prism((-2.6, 1.8, 0), (2.6, 1.8, 0), 1.8, 1.8, (240, 236, 226), sides=8)
    m.prism((2.5, 1.8, 0), (2.7, 1.8, 0), 0.8, 0.8, (200, 196, 186), sides=8)
    return m


def _medkit():
    m = Mesh()
    m.box((0, 1.6, 0), (5.4, 3.2, 4.2), (236, 236, 240))
    m.box((0, 1.6, 2.15), (3.0, 0.9, 0.2), (210, 50, 50))
    m.box((0, 1.6, 2.15), (0.9, 2.4, 0.2), (210, 50, 50))
    m.prism((0, 3.2, 0), (0, 5.0, 0), 0.9, 0.0, (150, 220, 255), sides=5, kind=KIND_GLOW)
    return m


def _cup(col):
    m = Mesh()
    m.prism((0, 0, 0), (0, 3.6, 0), 1.9, 2.3, (220, 214, 204), sides=8)
    m.prism((0, 3.4, 0), (0, 3.6, 0), 2.0, 2.0, col, sides=8)
    m.prism((2.2, 1.0, 0), (2.9, 2.8, 0), 0.4, 0.4, (220, 214, 204), sides=4)
    return m


def _pouch(col=(150, 116, 70)):
    m = Mesh()
    m.ball((0, 1.8, 0), (2.4, 1.9, 2.4), col, seg=7, rings=4)
    m.prism((0, 3.3, 0), (0, 4.4, 0), 0.9, 1.3, _shade(col, 0.85), sides=6)
    m.prism((-1.2, 3.6, 0), (1.2, 3.6, 0), 0.25, 0.25, (220, 200, 150), sides=4)
    return m


WALL_COL = {"wood_wall": (132, 90, 52), "stone_wall": (140, 140, 144), "iron_wall": (166, 172, 184),
            "brick_wall": (164, 84, 62), "stone_path": (150, 146, 136), "bridge": (132, 96, 60)}


def _block(col):
    m = Mesh()
    m.box((0, 2.4, 0), (4.8, 4.8, 4.8), col)
    dark = _shade(col, 0.75)
    for y in (1.2, 3.6):                    # a hint of courses / planks
        m.box((0, y, 2.42), (4.6, 0.22, 0.05), dark)
        m.box((2.42, y, 0), (0.05, 0.22, 4.6), dark)
    return m


def _icon_block():
    m = Mesh()
    m.box((0, 2.4, 0), (4.8, 4.8, 4.8), (255, 255, 255), tex=True)
    return m


def _card():
    m = Mesh()
    m.box((0, 4.2, 0), (8.6, 8.6, 0.5), (236, 228, 206))
    m.quad((-3.9, 0.3, 0.27), (3.9, 0.3, 0.27), (3.9, 8.1, 0.27), (-3.9, 8.1, 0.27), (255, 255, 255), KIND_TEX,
           uv=((0, 0), (1, 0), (1, 1), (0, 1)))
    m.quad((3.9, 0.3, -0.27), (-3.9, 0.3, -0.27), (-3.9, 8.1, -0.27), (3.9, 8.1, -0.27), (255, 255, 255),
           KIND_TEX, uv=((0, 0), (1, 0), (1, 1), (0, 1)))
    return m


# item -> (style, mesh maker). Styles say how it's held and how it swings:
#   chop   - fist, swung overhead and down (axes, pickaxes, hoe, hammers, club)
#   slash  - fist, swept across from the right (swords, fang, whip, torch)
#   stab   - fist, thrust forward (spears)
#   bow    - held out in the left hand, the right hand draws
#   cast   - fist, a flick forward (fishing rod)
#   throw  - palm, wound back and thrown (fire pot)
#   book   - palm, pushed forward (spellbook)
#   eat / drink - palm, raised to your mouth when you use it
#   block  - palm (building items), a little push when you place it
#   card   - pinched (anything else)
ITEM_MESH = {
    "axe": ("chop", lambda: _axe(STONE, (176, 174, 168))),
    "iron_axe": ("chop", lambda: _axe(IRON, STEEL)),
    "pickaxe": ("chop", lambda: _pick(STONE, (160, 158, 150))),
    "iron_pickaxe": ("chop", lambda: _pick(IRON, STEEL)),
    "starstone_pickaxe": ("chop", lambda: _pick((96, 90, 150), (190, 200, 255))),
    "hoe": ("chop", _hoe),
    "repair_hammer": ("chop", lambda: _hammer(IRON)),
    "titan_hammer": ("chop", lambda: _hammer((104, 90, 76), 1.5, (255, 140, 50), 20)),
    "club": ("chop", _club),
    "iron_sword": ("slash", lambda: _sword(STEEL)),
    "ember_blade": ("slash", lambda: _sword((255, 120, 40), (60, 48, 50), glow=True)),
    "star_blade": ("slash", lambda: _sword((210, 226, 255), (220, 190, 90), glow=True, length=21)),
    "brood_fang": ("slash", _fang),
    "thornroot_whip": ("slash", _whip),
    "torch": ("torch", _torch),
    "spear": ("stab", lambda: _spear((150, 148, 142))),
    "frost_spear": ("stab", lambda: _spear((170, 220, 255), glow=True, shaft=(200, 220, 236))),
    "bow": ("bow", lambda: _bow(WOOD)),
    "horn_bow": ("bow", lambda: _bow((224, 210, 180))),
    "fishing_rod": ("cast", _rod),
    "fire_pot": ("throw", _pot),
    "spellbook": ("book", _book),
    "berries": ("eat", _berries),
    "meat": ("eat", lambda: _meat((200, 70, 70))),
    "cooked_meat": ("eat", lambda: _meat((140, 80, 44))),
    "raw_fish": ("eat", lambda: _fish((150, 170, 180))),
    "cooked_fish": ("eat", lambda: _fish((196, 132, 70))),
    "bread": ("eat", _bread),
    "carrot": ("eat", _carrot),
    "stew": ("eat", lambda: _bowl((150, 64, 70))),
    "river_stew": ("eat", lambda: _bowl((176, 120, 60))),
    "honey": ("eat", lambda: _jar((236, 170, 40))),
    "honey_salve": ("eat", lambda: _jar((240, 196, 90), (200, 200, 210))),
    "bandage": ("eat", _bandage),
    "medkit": ("eat", _medkit),
    "water": ("drink", lambda: _flask((110, 150, 196))),
    "swamp_tonic": ("drink", lambda: _flask((90, 150, 70), glass=True)),
    "heather_tea": ("drink", lambda: _cup((150, 100, 150))),
}
for _k, _c in WALL_COL.items():
    ITEM_MESH[_k] = ("block", (lambda c: lambda: _block(c))(_c))


def item_style(item, kind):
    """(style, mesh maker, uses the icon texture) for an item and its ITEMS kind."""
    if item in ITEM_MESH:
        style, mk = ITEM_MESH[item]
        return style, mk, False
    if kind == "food":
        return "eat", _card, True
    if kind == "seed":
        return "eat", _pouch, False
    if kind == "build":
        return "block", _icon_block, True
    return "card", _card, True


# rest pose per style: (x, y, z, pitch, yaw, roll) of the right hand's grip in camera space
REST = {
    "chop": (9.5, -8.5, 21.0, 0.38, -0.55, 0.30),
    "slash": (9.5, -8.0, 21.0, 0.50, 1.15, 0.30),
    "torch": (9.5, -8.5, 21.0, 0.18, -0.2, 0.22),
    "stab": (8.0, -7.0, 19.0, 1.15, -0.05, 0.08),
    "cast": (9.5, -8.5, 20.0, 0.55, -0.15, 0.25),
    "throw": (8.0, -6.5, 17.0, -0.15, 0.0, -0.1),
    "book": (7.0, -6.5, 17.0, -0.55, -0.2, -0.1),
    "eat": (7.5, -6.5, 17.0, -0.2, -0.2, -0.1),
    "drink": (7.5, -6.5, 17.0, -0.2, -0.2, -0.1),
    "block": (7.5, -6.5, 17.0, -0.2, -0.45, -0.1),
    "card": (8.0, -7.5, 18.0, 0.05, -0.3, 0.15),
    "bow": (-2.4, -3.0, 30.0, -0.36, -0.40, -0.12),       # the LEFT hand's grip on the bow
}
PALM_STYLES = ("throw", "book", "eat", "drink", "block")


def _ease(k):
    k = max(0.0, min(1.0, k))
    return k * k * (3 - 2 * k)


def _keys(k, frames):
    """Blend a list of (time 0..1, (dx, dy, dz, dpitch, dyaw, droll)) keyframes at time k."""
    if k <= frames[0][0]:
        return frames[0][1]
    for (t0, a), (t1, b) in zip(frames, frames[1:]):
        if k <= t1:
            e = _ease((k - t0) / max(1e-4, t1 - t0))
            return tuple(x + (y - x) * e for x, y in zip(a, b))
    return frames[-1][1]


Z6 = (0.0,) * 6
SWINGS = {      # offsets from the rest pose through a swing
    "chop": [(0.0, Z6), (0.22, (1.5, 3.5, -1.5, -0.6, 0.1, -0.1)), (0.48, (-5.0, -2.5, 3.5, 1.1, -0.1, 0.25)),
             (0.58, (-4.6, -2.0, 3.2, 1.0, -0.1, 0.22)), (1.0, Z6)],
    "slash": [(0.0, Z6), (0.2, (4.0, 4.0, -2.0, -0.3, 0.35, -0.7)), (0.5, (-14.0, -5.0, 4.0, 0.5, -1.2, 0.9)),
              (0.6, (-13.0, -5.5, 3.5, 0.45, -1.1, 0.85)), (1.0, Z6)],
    "torch": [(0.0, Z6), (0.2, (3.0, 2.5, -2.0, -0.2, 0.25, -0.4)), (0.5, (-9.0, -3.0, 3.0, 0.4, -0.6, 0.6)),
              (1.0, Z6)],
    "stab": [(0.0, Z6), (0.25, (0.5, -1.0, -6.0, 0.05, 0.0, 0.0)), (0.45, (-3.5, 2.0, 12.0, -0.05, 0.05, 0.0)),
             (0.6, (-3.0, 1.6, 10.5, 0.0, 0.05, 0.0)), (1.0, Z6)],
    "cast": [(0.0, Z6), (0.3, (1.0, 4.0, -3.0, -0.8, 0.0, 0.0)), (0.55, (-1.0, -2.0, 4.0, 0.7, 0.0, 0.1)),
             (1.0, Z6)],
    "throw": [(0.0, Z6), (0.35, (3.0, 6.0, -5.0, -0.5, 0.0, 0.3)), (0.6, (-3.0, 0.0, 10.0, 0.6, 0.0, -0.2)),
              (1.0, Z6)],
    "book": [(0.0, Z6), (0.3, (-2.0, 2.0, 6.0, -0.2, 0.0, 0.0)), (0.5, (-2.0, 2.5, 7.0, -0.25, 0.0, 0.0)),
             (1.0, Z6)],
    "block": [(0.0, Z6), (0.35, (-2.0, -1.0, 6.0, 0.4, 0.0, 0.0)), (1.0, Z6)],
    "card": [(0.0, Z6), (0.35, (-2.0, 1.0, 5.0, 0.3, 0.0, 0.0)), (1.0, Z6)],
}
for _s in ("eat", "drink"):
    SWINGS[_s] = SWINGS["card"]
RAISE = {   # eating / drinking: the hand comes up to your mouth
    "eat": [(0.0, Z6), (0.3, (-5.5, 3.6, -2.5, 0.45, 0.3, 0.2)), (0.45, (-5.5, 3.0, -3.0, 0.55, 0.3, 0.25)),
            (0.6, (-5.5, 3.7, -2.5, 0.45, 0.3, 0.2)), (0.75, (-5.5, 3.0, -3.0, 0.55, 0.3, 0.25)), (1.0, Z6)],
    "drink": [(0.0, Z6), (0.3, (-5.5, 3.5, -2.0, -1.1, 0.2, 0.0)), (0.75, (-5.5, 4.0, -2.0, -1.4, 0.2, 0.0)),
              (1.0, Z6)],
}


# =========================================================================== state + drawing
class Hands:
    """One survivor's first person arms: GPU bits, cached meshes and the animation state."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.prog = ctx.program(vertex_shader=VS, fragment_shader=lighting3d.inject(FS, frag=True))
        lighting3d.bind(self.prog)
        self.prog["icon"] = 0
        self.geos = {}              # key -> geometry
        self.icons = {}             # item -> texture
        self.t = None               # last flame_t seen
        self.item = None
        self.switch = 1.0           # 0 -> 1: raising a newly picked item
        self.prev_item = None
        self.swing_t = -1.0         # time into the current swing (-1 = none)
        self.swing_len = 0.4
        self.last_swing = 0.0
        self.eat_t = -1.0
        self.eat_item = None
        self.counts = (None, 0)
        self.hurt_t = -1.0
        self.last_hurt = 0.0
        self.walk = 0.0             # walk cycle (radians)
        self.move = 0.0             # 0..1 how much you're walking
        self.run = 0.0              # 0..1 sprinting
        self.pos = None
        self.look = None            # (yaw, pitch) last frame
        self.sway = [0.0, 0.0]      # smoothed look speed
        self.draw_k = 0.0           # bow: how far the string is drawn
        self.ember_t = 0.0

    # ------------------------------------------------------------------ meshes
    def geo(self, key, make):
        g = self.geos.get(key)
        if g is None:
            m = make()
            data = array("f", m.v)
            buf = self.ctx.buffer(data=data)
            g = self.geos[key] = (self.ctx.geometry(
                [BufferDescription(buf, "3f 3f 3f 2f 1f", ["in_pos", "in_nrm", "in_col", "in_uv", "in_kind"])],
                mode=self.ctx.TRIANGLES), len(m.v) // VSTRIDE)
        return g

    def icon(self, item):
        tex = self.icons.get(item)
        if tex is None:
            try:
                import art
                img = art.icon(item).image.convert("RGBA").transpose(1)      # (flip: GL's rows go up)
            except Exception:       # noqa: BLE001 - no icon: a plain card
                from PIL import Image
                img = Image.new("RGBA", (8, 8), (200, 190, 170, 255))
            tex = self.ctx.texture(img.size, components=4, data=img.tobytes())
            tex.filter = (gl.GL_LINEAR, gl.GL_LINEAR)
            self.icons[item] = tex
        return tex

    def item_geo(self, item, kind):
        style, make, tex = item_style(item, kind)

        def build():
            m = Mesh()
            if style == "bow":
                return make()
            hand = palm() if style in PALM_STYLES else fist()
            if style == "card":
                m.merge(make(), Pose(rot(), (-0.6, 1.6, 1.2)))
            else:
                m.merge(make())
            m.merge(hand)
            return m
        return style, self.geo(("item", item), build), tex

    @staticmethod
    def sleeve(sleeve, bracer):
        """A forearm along +z from the wrist (z = 0) to the shoulder (z = 1), radius in game pixels."""
        def make():
            m = Mesh()
            m.prism((0, 0, 0.0), (0, 0, 1.0), 2.2, 3.3, sleeve, sides=7)
            m.prism((0, 0, -0.01), (0, 0, 0.07), 2.5, 2.55, _shade(sleeve, 0.72), sides=7)     # cuff
            if bracer:
                m.prism((0, 0, 0.07), (0, 0, 0.42), 2.65, 3.0, bracer, sides=7)
                m.prism((0, 0, 0.07), (0, 0, 0.1), 2.8, 2.8, _shade(bracer, 0.75), sides=7)
            return m
        return make

    # ------------------------------------------------------------------ animation state
    def update(self, game, me, item):
        t = game.flame_t
        dt = 0.0 if self.t is None else max(0.0, min(0.1, t - self.t))
        self.t = t
        if item != self.item:
            if self.eat_t < 0 or self.eat_item is None:
                self.switch = 0.0 if self.item is not None or item is not None else 1.0
            self.prev_item, self.item = self.item, item
            self.swing_t = -1.0
        self.switch = min(1.0, self.switch + dt / 0.28)
        # an attack just started: me.swing jumps back up to 0.2 (on the host and for online clients alike)
        sw = getattr(me, "swing", 0.0)
        if sw > self.last_swing + 0.05:
            import settings
            info = settings.ITEMS.get(item or "", {})
            self.swing_len = max(0.26, min(0.62, info.get("cooldown", 0.45) * 0.95))
            self.swing_t = 0.0
        self.last_swing = sw
        if self.swing_t >= 0:
            self.swing_t += dt
            if self.swing_t > self.swing_len:
                self.swing_t = -1.0
        # eating / drinking: the held food's count went down
        n = (me.inv or {}).get(item, 0) if item else 0
        if item and self.counts[0] == item and n < self.counts[1]:
            self.eat_t, self.eat_item = 0.0, item
        self.counts = (item, n)
        if self.eat_t >= 0:
            self.eat_t += dt
            if self.eat_t > 0.75:
                self.eat_t, self.eat_item = -1.0, None
        # hurt: a jolt
        hu = getattr(me, "hurt", 0.0)
        if hu > self.last_hurt + 0.05:
            self.hurt_t = 0.0
        self.last_hurt = hu
        if self.hurt_t >= 0:
            self.hurt_t += dt
            if self.hurt_t > 0.35:
                self.hurt_t = -1.0
        # walking: by how far you really moved (works for online clients too)
        x, y = me.sprite.center_x, me.sprite.center_y
        if self.pos is not None and dt > 0:
            d = math.hypot(x - self.pos[0], y - self.pos[1])
            if d > 80:
                d = 0.0
            speed = d / dt
            want = min(1.0, speed / 90.0)
            self.move += (want - self.move) * min(1.0, dt * 8)
            self.walk += d * 0.085
            runk = 1.0 if (getattr(me, "sprinting", False) and speed > 40) else 0.0
            self.run += (runk - self.run) * min(1.0, dt * 6)
        self.pos = (x, y)
        # sway: the hands lag behind where you look
        look = (game.fp_yaw, game.fp_pitch)
        if self.look is not None and dt > 0:
            dyaw = (look[0] - self.look[0] + math.pi) % math.tau - math.pi
            dp = look[1] - self.look[1]
            k = min(1.0, dt * 10)
            self.sway[0] += (max(-6.0, min(6.0, dyaw / dt)) - self.sway[0]) * k
            self.sway[1] += (max(-6.0, min(6.0, dp / dt)) - self.sway[1]) * k
        self.look = look
        # bow: the string comes back while you hold attack, snaps forward on each shot
        if self.swing_t >= 0 and self.swing_t < 0.08:
            self.draw_k = 0.0
        else:
            want = 1.0 if getattr(me, "attacking", False) else 0.25
            self.draw_k += (want - self.draw_k) * min(1.0, dt * (3.2 if want > self.draw_k else 6.0))
        return dt

    def offsets(self, style, t):
        """(dx, dy, dz, dpitch, dyaw, droll) for this frame's motion on top of the rest pose."""
        o = [0.0] * 6
        # walking bob (a figure of eight), stronger when sprinting
        amp = self.move * (1.0 + 1.3 * self.run)
        w = self.walk
        o[0] += math.sin(w) * 0.9 * amp
        o[1] += -abs(math.cos(w)) * 1.0 * amp + 0.5 * amp
        o[3] += math.sin(w * 2) * 0.03 * amp + 0.12 * self.run
        o[5] += math.sin(w) * 0.04 * amp
        o[2] -= 1.2 * self.run
        # idle breathing
        o[1] += math.sin(t * 1.7) * 0.35
        o[3] += math.sin(t * 1.7 + 0.6) * 0.012
        # sway behind the mouse
        o[0] -= self.sway[0] * -0.55
        o[1] -= self.sway[1] * 0.55
        o[4] += self.sway[0] * 0.03
        o[3] -= self.sway[1] * 0.025
        # the swing
        if self.swing_t >= 0 and style in SWINGS:
            k = self.swing_t / self.swing_len
            o = [a + b for a, b in zip(o, _keys(k, SWINGS[style]))]
        # eating / drinking
        if self.eat_t >= 0:
            k = self.eat_t / 0.75
            o = [a + b for a, b in zip(o, _keys(k, RAISE["drink" if style == "drink" else "eat"]))]
        # hurt: a sharp shove down and sideways, wobbling out
        if self.hurt_t >= 0:
            k = self.hurt_t / 0.35
            j = math.sin(k * math.pi) * (1 - k * 0.4)
            o[0] += -2.5 * j
            o[1] += -3.5 * j
            o[2] += -2.0 * j
            o[5] += 0.25 * j * math.sin(self.hurt_t * 40)
            o[3] += -0.2 * j
        # changing item: lowered out of view and raised again
        lo = 1.0 - _ease(self.switch)
        o[1] -= 16.0 * lo
        o[3] -= 0.6 * lo
        return o

    # ------------------------------------------------------------------ the frame
    def draw(self, game, L, vl, dk):
        me = game.me
        raw = me.hotbar[me.selected] if 0 <= me.selected < len(me.hotbar) else None
        item = raw if raw and (me.inv or {}).get(raw, 0) > 0 else None
        self.update(game, me, item)
        shown = item
        if self.eat_t >= 0 and self.eat_item:
            shown = self.eat_item          # keep showing the last bite while it goes to your mouth
        import settings
        kind = settings.ITEMS.get(shown, {}).get("kind", "") if shown else ""
        t = game.flame_t
        (ex, ey, ez), f, r, u, _, vw, vh = game._basis()
        cam = (r, u, f)

        def to_world(p):
            return (ex + r[0] * p[0] + u[0] * p[1] + f[0] * p[2],
                    ey + r[1] * p[0] + u[1] * p[1] + f[1] * p[2],
                    ez + r[2] * p[0] + u[2] * p[1] + f[2] * p[2])

        def model(pose, stretch=None):
            """Pose (camera space) -> a column-major world matrix. stretch: scale of the z column."""
            m = pose.m
            cols = []
            for j in range(3):
                c = (m[0][j], m[1][j], m[2][j])
                if stretch is not None and j == 2:
                    c = _mul(c, stretch)
                cols.append(tuple(cam[0][i] * c[0] + cam[1][i] * c[1] + cam[2][i] * c[2] for i in range(3)))
            w = to_world(pose.t)
            return (cols[0] + (0.0,) + cols[1] + (0.0,) + cols[2] + (0.0,) + w + (1.0,))

        ctx = self.ctx
        prog = self.prog
        sx, sy = game._progs3d[1]["sun"]
        lx, ly, lz = -sx, -sy, 1.4
        ln = math.sqrt(lx * lx + ly * ly + lz * lz)
        prog["light"] = (lx / ln, ly / ln, lz / ln)
        prog["time"] = float(t % 1000.0)
        import firstperson
        prog["proj"] = Mat4.perspective_projection(vw / max(1, vh), NEAR, FAR, firstperson.FP_FOV_DEG)
        prog["view"] = game.view
        prog["torch"] = (0.0, 0.0, 0.0, 0.0)
        eq = getattr(me, "equip", {}) or {}
        import models3d
        jacket = models3d.JACKETS[me.id % 4]
        armour = eq.get("body")
        bracer = models3d.GEAR_COL.get(armour, (150, 150, 150)) if armour else None
        sleeve_key = ("sleeve", jacket, bracer)
        sleeve_geo = self.geo(sleeve_key, self.sleeve(jacket, bracer))
        draws = []          # (geometry, model matrix, icon texture or None)

        def arm(hand_pose, wrist, shoulder):
            w = hand_pose.at(wrist)
            s = shoulder
            d = _sub(s, w)
            ln = math.sqrt(_dot(d, d)) or 1.0
            z = _mul(d, 1 / ln)
            x = _norm(_cross((0.0, 1.0, 0.0), z))
            y = _cross(z, x)
            x, y = _mul(x, SCALE), _mul(y, SCALE)
            m = ((x[0], y[0], z[0]), (x[1], y[1], z[1]), (x[2], y[2], z[2]))
            draws.append((sleeve_geo, model(Pose(m, w), ln), None))

        style = "card"
        o = None
        if shown:
            style, geo, tex = self.item_geo(shown, kind)
            o = self.offsets(style, t)
            bx, by, bz, bp, byw, br = REST[style]
            pose = Pose(_scaled(rot(bp + o[3], byw + o[4], br + o[5])), (bx + o[0], by + o[1], bz + o[2]))
            draws.append((geo, model(pose), self.icon(shown) if tex else None))
            if style == "bow":
                right = self.bow_parts(draws, pose, model, me)
                arm(pose, (-0.6, -0.8, -1.6), L_SHOULDER)
                arm(right, WRIST_FIST, R_SHOULDER)
            else:
                arm(pose, WRIST_PALM if style in PALM_STYLES else WRIST_FIST, R_SHOULDER)
            if style == "torch":
                tip = to_world(pose.at((0.0, 19.5, 0.0)))
                prog["torch"] = tip + ((1.0 + 0.08 * math.sin(t * 13) + 0.05 * math.sin(t * 29)),)
                self.embers(game, vl, tip)
        else:
            # empty hands: a relaxed fist at the bottom of the view, swinging a punch on attack
            o = self.offsets("chop", t)
            pose = Pose(_scaled(rot(0.2 + o[3] * 0.5, -0.3 + o[4], 0.6 + o[5])),
                        (10.0 + o[0], -12.0 + o[1], 18.0 + o[2]))
            if self.swing_t >= 0:
                k = math.sin(min(1.0, self.swing_t / self.swing_len) * math.pi)
                pose.t = _add(pose.t, (-5.0 * k, 3.0 * k, 9.0 * k))
            draws.append((self.geo(("fist",), fist), model(pose), None))
            arm(pose, WRIST_FIST, R_SHOULDER)

        # ---- draw: in front of the whole world, without touching its depth values
        gl.glDepthRange(0.0, DEPTH_SLICE)
        ctx.enable(ctx.DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LEQUAL)
        gl.glDepthMask(gl.GL_TRUE)
        ctx.disable(ctx.BLEND)
        try:
            for g, mm, tex in draws:
                if tex is not None:
                    tex.use(0)
                prog["model"] = mm
                g[0].render(prog, vertices=g[1])
        finally:
            gl.glDepthRange(0.0, 1.0)
            ctx.enable(ctx.BLEND)

    def bow_parts(self, draws, bow_pose, model, me):
        """The string, the right hand drawing it and the arrow (if you have any)."""
        k = self.draw_k
        pull = 3.0 + 15.0 * k
        nock = (0.0, NOCK_Y, -0.1 - pull)
        a, b = BOW_TIPS
        for tip in (a, b):              # the two halves of the string
            p0, p1 = bow_pose.at(tip), bow_pose.at(nock)
            d = _sub(p1, p0)
            ln = math.sqrt(_dot(d, d)) or 1.0
            z = _mul(d, 1 / ln)
            x = _norm(_cross((0.0, 1.0, 0.0), z)) if abs(z[1]) < 0.95 else _norm(_cross((1.0, 0.0, 0.0), z))
            y = _cross(z, x)
            x, y = _mul(x, SCALE), _mul(y, SCALE)
            m = ((x[0], y[0], z[0]), (x[1], y[1], z[1]), (x[2], y[2], z[2]))
            draws.append((self.geo(("string",), _string), model(Pose(m, p0), ln), None))
        hand = Pose(_mm(bow_pose.m, _scaled(rot(roll=-1.3), 0.9)), bow_pose.at((0.4, NOCK_Y - 0.6, -pull - 1.6)))
        draws.append((self.geo(("fist",), fist), model(hand), None))
        arrows = (me.inv or {}).get("arrows", 0)
        if arrows > 0 and not (0 <= self.swing_t < 0.12):
            ap = Pose(bow_pose.m, bow_pose.at((0.9, NOCK_Y, -0.1 - pull)))
            draws.append((self.geo(("arrow",), _arrow), model(ap), None))
        return hand

    def embers(self, game, vl, tip):
        """Your torch sheds embers and a wisp of smoke into the world (fx3d.py particles)."""
        t = game.flame_t
        if t - self.ember_t < 0.06:
            return
        self.ember_t = t
        x, y, z = tip
        z -= game.ground_z(x, y)
        rnd = random.random
        game.fx_spawn(vl, x + (rnd() - 0.5) * 1.5, y + (rnd() - 0.5) * 1.5, z + 3.0, (rnd() - 0.5) * 8,
                      (rnd() - 0.5) * 8, 18 + rnd() * 18, 0.5 + rnd() * 0.5, 0.14 + rnd() * 0.12,
                      (255, 170 + int(rnd() * 60), 70), 1.0, grav=-6, drag=1.5, add=True)
        if rnd() < 0.3:
            game.fx_spawn(vl, x, y, z + 6.0, (rnd() - 0.5) * 4, (rnd() - 0.5) * 4, 14, 1.1, 0.6,
                          (90, 84, 80), 0.2, drag=1.0, grow=2.5)


def _string():
    m = Mesh()
    m.prism((0, 0, 0), (0, 0, 1), 0.16, 0.16, (236, 230, 214), sides=3)
    return m


# =========================================================================== the hook
_FAILED = False


def draw(game, L, vl, dk):
    """view3d.draw_world_3d's hook (first person only): draw your arms and what they hold. Call with the
    3D camera on, in the "lit" lighting stage. Returns True when drawn (firstperson.py then skips the old
    flat picture)."""
    global _FAILED
    if _FAILED:
        return False
    me = getattr(game, "me", None)
    if me is None or not me.alive or game.ui_open:
        return False
    try:
        h = game.__dict__.get("_fp_hands")
        if h is None:
            h = game._fp_hands = Hands(game.ctx)
        h.draw(game, L, vl, dk)
        game._fp_hands_frame = game.flame_t
        return True
    except Exception as e:      # noqa: BLE001 - never let an extra stop the game
        _FAILED = True
        print("fphands3d: first person hands turned off:", e)
        gl.glDepthRange(0.0, 1.0)
        return False


def drawn_this_frame(game):
    """True when the 3D arms were drawn this frame (so the old flat item picture isn't needed)."""
    return not _FAILED and game.__dict__.get("_fp_hands_frame") == game.flame_t
