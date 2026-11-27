"""
preview.py - render a contact sheet of the built models (front / side / three-quarter views).

    blender --background --factory-startup --python tools/blender/preview.py -- OUT.png [name ...] [--gear]

(--gear also shows the optional parts: survivor armor / helmet / cloak and pet armor.)

Reads assets/models/*.glb (run build_all.py first), so what you see is exactly what the game loads.
Each model is scaled to fit its cell; the label shows its name and triangle count.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "assets", "models")
VIEWS = (("front", -90), ("3/4", -40), ("side", 0), ("back 3/4", 140))
CELL = 1.25
PER_ROW = 2
GEAR = False


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("grp", None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
        if o.get("opt") and not GEAR:          # optional parts (worn gear, pet armor) hidden unless --gear
            o.hide_render = True
    meta = json.loads(bpy.context.scene.get("ll_model", "{}") or "{}")
    return root, new, meta


def bounds(objs):
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def label(text, loc, size=0.09):
    cu = bpy.data.curves.new("lbl", "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new("lbl", cu)
    ob.location = loc
    ob.rotation_euler = (math.radians(90), 0, 0)
    m = bpy.data.materials.new("lbl")
    m.diffuse_color = (0.05, 0.05, 0.06, 1)
    cu.materials.append(m)
    bpy.context.scene.collection.objects.link(ob)


def main():
    global GEAR
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    GEAR = "--gear" in args
    args = [a for a in args if a != "--gear"]
    out = args[0] if args else os.path.join(ROOT, "docs", "models_sheet.png")
    want = args[1:]
    files = sorted(f for f in os.listdir(SRC) if f.endswith(".glb"))
    names = [f[:-4] for f in files if not want or f[:-4] in want]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    rows = (len(names) + PER_ROW - 1) // PER_ROW
    ncol = PER_ROW * len(VIEWS)
    for i, name in enumerate(names):
        r, cgrp = divmod(i, PER_ROW)
        tris = 0
        for v, (vname, yaw) in enumerate(VIEWS):
            root, objs, meta = import_glb(os.path.join(SRC, name + ".glb"))
            tris = meta.get("tris", 0)
            bpy.context.view_layer.update()
            lo, hi = bounds(objs)
            size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, 1e-3)
            k = 1.0 / size
            col = cgrp * len(VIEWS) + v
            cx = (col + 0.5) * CELL + cgrp * 0.3
            cz = -(r + 0.5) * CELL * 1.05
            root.scale = (k, k, k)
            root.rotation_euler = (0, 0, math.radians(yaw))
            ctr = (lo + hi) / 2
            off = Vector((ctr.x, ctr.y, lo.z)) * k
            rot = root.rotation_euler.to_matrix()
            root.location = Vector((cx, 0, cz - 0.42)) - rot @ off
        gx = (cgrp * len(VIEWS) + len(VIEWS) / 2) * CELL + cgrp * 0.3
        label(f"{name}  ({tris} tris)", (gx, -1.0, -(r + 0.5) * CELL * 1.05 - 0.6))
    for v, (vname, _) in enumerate(VIEWS * PER_ROW):
        label(vname, ((v + 0.5) * CELL + (v // len(VIEWS)) * 0.3, -1.0, 0.05), 0.07)
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    w = ncol * CELL + 0.3 * (PER_ROW - 1)
    h = rows * CELL * 1.05 + 0.3
    cam_d.ortho_scale = max(w, h)
    cam = bpy.data.objects.new("cam", cam_d)
    cam.location = (w / 2, -10, -h / 2 + 0.15)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_cavity = False
    sc.display.shading.show_object_outline = True
    sc.render.resolution_x = 2200
    sc.render.resolution_y = int(2200 * h / w)
    if h > w:
        sc.render.resolution_y, sc.render.resolution_x = 2200, int(2200 * w / h)
    world = bpy.data.worlds.new("w")
    sc.world = world
    world.color = (0.82, 0.84, 0.86)
    sc.display.shading.background_type = "WORLD"
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("contact sheet ->", out)


main()
