"""
lowpoly.py - helpers for building Last Light's chunky low-poly creature models in Blender (bpy).

Runs INSIDE Blender (imported by build_all.py / preview.py). Nothing in the game imports this.

Conventions (see docs/MODELS.md):
  * 1 Blender unit = 1 metre. The game multiplies by models3d.UNIT (55 game pixels per metre).
  * The creature faces +X, its left is +Y, up is +Z, feet on Z = 0, centred on X = Y = 0.
  * A model is a set of named PARTS. Each part is one mesh object whose origin is its PIVOT
    (shoulder, hip, neck, tail root...). The game animates parts by their ROLE (body, head, leg_a,
    leg_b, arm_l, arm_r, tail, wing_l, wing_r, sleg_a, sleg_b, jaw, still) in the vertex shader.
  * Colours are flat materials named "<kind>_<rrggbb>" (sRGB hex):
        c_      plain colour (lit by the sun)
        glow_   unlit / emissive (eyes, lava, crystals)
        acc1_ .. acc4_  recolourable by the game per instance (jacket, helmet, armor, cloak...)
    The hex in the name is what the game uses; the material colour is set to match for previews.
  * Attachment points are empties ("eye_l", "eye_r", "hand_r", "glow_core"...), parented to a part
    so they follow its animation.
  * Optional parts (survivor helmet / armor / cloak, pet armor) carry opt="name": the game only
    shows them when that instance has the matching flag set.
"""
import json
import math
import os
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

ROLES = ("body", "head", "leg_a", "leg_b", "arm_l", "arm_r", "tail", "wing_l", "wing_r", "sleg_a", "sleg_b",
         "jaw", "still")


# ----------------------------------------------------------------------------- colours
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(rgb, kind="c"):
    """A flat material for an sRGB colour (0-255). kind: c | glow | acc1 | acc2 | acc3 | acc4."""
    r, g, b = (int(max(0, min(255, round(v)))) for v in rgb)
    name = f"{kind}_{r:02x}{g:02x}{b:02x}"
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        col = (_lin(r), _lin(g), _lin(b), 1.0)
        m.diffuse_color = col
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = col
            bsdf.inputs["Roughness"].default_value = 0.9
            if kind == "glow":
                for key in ("Emission Color", "Emission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = col
                        break
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = 1.0
    return m


def shade(rgb, f):
    return tuple(max(0, min(255, v * f)) for v in rgb)


def glow(rgb):
    return mat(rgb, "glow")


# ----------------------------------------------------------------------------- parts
def _rot(rot):
    if rot is None:
        return Matrix.Identity(4)
    return Euler(tuple(math.radians(a) for a in rot), "XYZ").to_matrix().to_4x4()


class Part:
    """One animated piece of a model. Add primitives in MODEL space (metres); the part's origin
    becomes `pivot` when the model is finished."""

    def __init__(self, model, name, pivot, role=None, opt=None):
        self.model, self.name = model, name
        self.pivot = Vector(pivot)
        self.role = role
        self.opt = opt
        self.bm = bmesh.new()
        self.mats = []

    # -- internals
    def _mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _place(self, verts, m, mtx, jitter=0.0, seed=0):
        bmesh.ops.transform(self.bm, matrix=mtx, verts=verts)
        if jitter:
            rnd = random.Random(seed)
            for v in verts:
                v.co += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * jitter
        mi = self._mi(m)
        faces = {f for v in verts for f in v.link_faces}
        for f in faces:
            f.material_index = mi
            f.smooth = False
        return self

    # -- primitives (centre c, sizes in metres, rot = Euler degrees XYZ)
    def box(self, c, size, m, rot=None, taper=1.0, taper_y=None, jitter=0.0, seed=0):
        """Box of full size (sx, sy, sz). taper scales the top face (x, and y unless taper_y given)."""
        res = bmesh.ops.create_cube(self.bm, size=1.0)
        vs = res["verts"]
        ty = taper if taper_y is None else taper_y
        for v in vs:
            if v.co.z > 0:
                v.co.x *= taper
                v.co.y *= ty
        sc = Matrix.Diagonal((size[0], size[1], size[2], 1.0))
        return self._place(vs, m, Matrix.Translation(c) @ _rot(rot) @ sc, jitter, seed)

    def ball(self, c, r, m, segs=8, rings=5, rot=None, jitter=0.0, seed=0):
        """Ellipsoid with radii r (rx, ry, rz) or a single radius."""
        if not isinstance(r, (tuple, list)):
            r = (r, r, r)
        res = bmesh.ops.create_uvsphere(self.bm, u_segments=segs, v_segments=rings, radius=1.0)
        sc = Matrix.Diagonal((r[0], r[1], r[2], 1.0))
        return self._place(res["verts"], m, Matrix.Translation(c) @ _rot(rot) @ sc, jitter, seed)

    def rock(self, c, r, m, sub=1, rot=None, jitter=0.12, seed=0):
        """Faceted lumpy boulder (icosphere). jitter is a share of the radius."""
        if not isinstance(r, (tuple, list)):
            r = (r, r, r)
        res = bmesh.ops.create_icosphere(self.bm, subdivisions=sub, radius=1.0)
        vs = res["verts"]
        rnd = random.Random(seed)
        for v in vs:
            v.co *= 1.0 + rnd.uniform(-jitter, jitter)
        sc = Matrix.Diagonal((r[0], r[1], r[2], 1.0))
        return self._place(vs, m, Matrix.Translation(c) @ _rot(rot) @ sc)

    def cyl(self, c, r, depth, m, segs=6, r2=None, rot=None, caps=True):
        """Upright cylinder / cone (r at the bottom, r2 at the top), centred on c."""
        res = bmesh.ops.create_cone(self.bm, cap_ends=caps, cap_tris=False, segments=segs, radius1=r,
                                    radius2=r if r2 is None else r2, depth=depth)
        return self._place(res["verts"], m, Matrix.Translation(c) @ _rot(rot))

    def limb(self, a, b, r1, r2, m, segs=5, caps=True, flat=1.0):
        """Tapered cylinder from point a (radius r1) to point b (radius r2). r2 = 0 makes a spike/horn.
        flat < 1 squashes it sideways (ears, fins)."""
        a, b = Vector(a), Vector(b)
        d = b - a
        ln = d.length
        if ln < 1e-6:
            return self
        res = bmesh.ops.create_cone(self.bm, cap_ends=caps, cap_tris=False, segments=segs, radius1=r1,
                                    radius2=max(r2, 0.0), depth=ln)
        q = Vector((0, 0, 1)).rotation_difference(d.normalized())
        sc = Matrix.Diagonal((1.0, flat, 1.0, 1.0))
        mtx = Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4() @ sc
        return self._place(res["verts"], m, mtx)

    def tri(self, pts, m, thick=0.02):
        """A flat polygon (wings, fins, cloak flaps) given as model-space points, made two-sided by
        giving it a little thickness along its normal."""
        pts = [Vector(p) for p in pts]
        n = (pts[1] - pts[0]).cross(pts[2] - pts[0]).normalized() * (thick / 2)
        top = [self.bm.verts.new(p + n) for p in pts]
        bot = [self.bm.verts.new(p - n) for p in pts]
        fs = [self.bm.faces.new(top), self.bm.faces.new(list(reversed(bot)))]
        k = len(pts)
        for i in range(k):
            j = (i + 1) % k
            fs.append(self.bm.faces.new((top[j], top[i], bot[i], bot[j])))
        mi = self._mi(m)
        for f in fs:
            f.material_index = mi
            f.smooth = False
        bmesh.ops.recalc_face_normals(self.bm, faces=fs)
        return self

    def mirror_y(self):
        """Copy everything in this part to the other side (y -> -y)."""
        geom = self.bm.verts[:] + self.bm.edges[:] + self.bm.faces[:]
        res = bmesh.ops.duplicate(self.bm, geom=geom)
        vs = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.scale(self.bm, vec=(1, -1, 1), verts=vs)
        fs = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
        bmesh.ops.reverse_faces(self.bm, faces=fs)
        return self


class Model:
    """A creature model under construction. `meta` goes into the GLB (scene extras) for the game:
        anim: {stride, bob, nod, breathe, wag, flap, hover, float, lunge, arms ('swing' | 'reach' | 'none')}
        stride_len: metres travelled per full walk cycle
    """

    def __init__(self, name, meta=None):
        self.name = name
        self.meta = dict(meta or {})
        self.parts = []
        self.points = []
        bpy.ops.wm.read_factory_settings(use_empty=True)

    def part(self, name, pivot=(0, 0, 0), role=None, opt=None):
        p = Part(self, name, pivot, role, opt)
        self.parts.append(p)
        return p

    def attach(self, name, loc, part=None):
        """An attachment point (glow, held item, effect spot) that follows `part`'s animation."""
        self.points.append((name, Vector(loc), part))

    # -- build the Blender objects
    def finish(self):
        col = bpy.context.scene.collection
        objs = {}
        tris = 0
        for p in self.parts:
            me = bpy.data.meshes.new(p.name)
            bmesh.ops.translate(p.bm, vec=-p.pivot, verts=p.bm.verts)
            bmesh.ops.remove_doubles(p.bm, verts=p.bm.verts, dist=1e-5)
            p.bm.to_mesh(me)
            p.bm.free()
            for m in p.mats:
                me.materials.append(m)
            for poly in me.polygons:
                poly.use_smooth = False
                tris += len(poly.vertices) - 2
            ob = bpy.data.objects.new(p.name, me)
            ob.location = p.pivot
            if p.role:
                ob["role"] = p.role
            if p.opt:
                ob["opt"] = p.opt
            col.objects.link(ob)
            objs[p.name] = ob
        for name, loc, part in self.points:
            e = bpy.data.objects.new(name, None)
            e.empty_display_type = "PLAIN_AXES"
            e.empty_display_size = 0.05
            col.objects.link(e)
            if part and part in objs:
                e.parent = objs[part]
                e.location = loc - objs[part].location
            else:
                e.location = loc
        self.meta["tris"] = tris
        bpy.context.scene["ll_model"] = json.dumps(self.meta)
        return tris

    def export(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_extras=True, export_yup=True,
                                  export_apply=True, export_materials="EXPORT", export_normals=True,
                                  export_texcoords=False, export_animations=False, export_cameras=False,
                                  export_lights=False)


# ----------------------------------------------------------------------------- reusable body bits
def quad_legs(M, x_front, x_back, half_w, hip_z, r_top, r_foot, m, foot=None, hoof_m=None, knee=0.0):
    """Four legs as parts leg_fl / leg_fr / leg_bl / leg_br (fl+br swing together, fr+bl opposite)."""
    for nm, x, side in (("leg_fl", x_front, 1), ("leg_fr", x_front, -1), ("leg_bl", x_back, 1),
                        ("leg_br", x_back, -1)):
        role = "leg_a" if nm in ("leg_fl", "leg_br") else "leg_b"
        y = side * half_w
        leg = M.part(nm, (x, y, hip_z), role)
        mid = (x + knee, y, hip_z * 0.45)
        leg.limb((x, y, hip_z), mid, r_top, r_top * 0.75, m, segs=5)
        leg.limb(mid, (x, y, 0.0 + (foot or 0.0)), r_top * 0.75, r_foot, m, segs=5)
        if hoof_m is not None:
            leg.cyl((x, y, 0.03), r_foot * 1.15, 0.06, hoof_m, segs=5)
    return M


def eyes(part, x, y, z, r, m, pupil=None, attach=True, M=None, prefix="eye"):
    """A pair of eyes on a face at (x, +-y, z) and their attachment points (eye_l / eye_r)."""
    for side, nm in ((1, "l"), (-1, "r")):
        part.ball((x, side * y, z), r, m, segs=6, rings=4)
        if pupil is not None:
            part.ball((x + r * 0.7, side * y, z), r * 0.45, pupil, segs=5, rings=3)
        if attach and M is not None:
            M.attach(f"{prefix}_{nm}", (x + r * 0.8, side * y, z), part.name)


def humanoid(M, skin, shirt, pants, boots, height=1.8, bulk=1.0, lean=0.0, arms="swing", head_r=0.14,
             eye_m=None, eye_r=0.022, hand_r=0.055, shirt_m=None, legs_m=None, sleeve_m=None):
    """Upright two-legged body: parts body, head, arm_l, arm_r, leg_l (leg_a), leg_r (leg_b).
    arms = "swing" (hang at the sides) or "reach" (held out in front, zombie style).
    lean = forward hunch in degrees. Returns a dict of the parts and key points."""
    s, w = height / 1.8, bulk
    hip = 0.9 * s
    tl = math.tan(math.radians(lean))

    def fx(z):                              # forward shift of the hunched upper body at height z
        return (z - hip) * tl

    sm = shirt_m or mat(shirt)
    lm = legs_m or mat(pants)
    am = sleeve_m or sm
    body = M.part("body", (0, 0, hip), "body")
    body.box((0.0, 0, hip + 0.06 * s), (0.24 * w, 0.36 * w, 0.2 * s), lm)                       # hips
    zc = hip + 0.33 * s
    body.box((fx(zc), 0, zc), (0.26 * w, 0.44 * w, 0.5 * s), sm, taper=1.0, taper_y=1.18, rot=(0, lean, 0))
    neck = (fx(hip + 0.6 * s), 0, hip + 0.6 * s)
    body.cyl((neck[0], 0, neck[2] + 0.02 * s), 0.06 * s * min(w, 1.3), 0.1 * s, mat(skin), segs=5)
    head = M.part("head", neck, "head")
    hc = (neck[0] + 0.03 * s + fx(hip + 0.75 * s) - fx(hip + 0.6 * s), 0, neck[2] + 0.17 * s)
    head.ball(hc, (head_r * s * 1.05, head_r * s, head_r * s * 1.12), mat(skin), segs=7, rings=5)
    if eye_m is not None:
        eyes(head, hc[0] + head_r * s * 0.92, head_r * s * 0.42, hc[2] + head_r * s * 0.15, eye_r * s, eye_m, M=M)
    sh_z = hip + 0.52 * s
    out = {"body": body, "head": head, "head_c": hc, "neck": neck, "s": s, "w": w, "hip": hip, "fx": fx}
    for side, nm in ((1, "arm_l"), (-1, "arm_r")):
        sh = (fx(sh_z), side * 0.27 * w, sh_z)
        arm = M.part(nm, sh, nm)
        if arms == "reach":
            elbow = (sh[0] + 0.3 * s, side * 0.26 * w, sh_z - 0.03 * s)
            hand = (sh[0] + 0.58 * s, side * 0.24 * w, sh_z - 0.05 * s)
        else:
            elbow = (sh[0] + 0.02 * s, side * 0.31 * w, sh_z - 0.3 * s)
            hand = (sh[0] + 0.06 * s, side * 0.32 * w, sh_z - 0.58 * s)
        arm.limb(sh, elbow, 0.07 * w * s, 0.06 * w * s, am, segs=5)
        arm.limb(elbow, hand, 0.058 * w * s, 0.05 * w * s, mat(skin) if arms == "reach" else am, segs=5)
        arm.ball(hand, hand_r * w * s, mat(skin), segs=6, rings=4)
        M.attach("hand_l" if side > 0 else "hand_r", hand, nm)
        out[nm] = arm
        out["hand_" + nm[-1]] = hand
        out["shoulder_" + nm[-1]] = sh
    for side, nm, role in ((1, "leg_l", "leg_a"), (-1, "leg_r", "leg_b")):
        y = side * 0.11 * w
        leg = M.part(nm, (0, y, hip), role)
        leg.limb((0, y, hip), (0.02 * s, y, hip * 0.5), 0.09 * w * s, 0.075 * w * s, lm, segs=5)
        leg.limb((0.02 * s, y, hip * 0.5), (0, y, 0.08 * s), 0.075 * w * s, 0.065 * w * s, lm, segs=5)
        leg.box((0.05 * s, y, 0.05 * s), (0.26 * s * min(w, 1.2), 0.13 * w * s, 0.1 * s), mat(boots))
        out[nm] = leg
    return out
