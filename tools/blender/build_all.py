"""
build_all.py - rebuild every creature model into assets/models/<name>.glb.

    blender --background --factory-startup --python tools/blender/build_all.py
    blender --background --factory-startup --python tools/blender/build_all.py -- wolf titan   # just some

Every module in tools/blender/models/ has a MODELS dict {name: function returning a lowpoly.Model}.
The game never needs Blender: the .glb files are committed and read by models3d.py.
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models")
for p in (HERE, os.path.join(HERE, "models")):
    if p not in sys.path:
        sys.path.insert(0, p)


def all_models():
    """{name: builder} from every module in tools/blender/models/ (sorted by file name)."""
    found = {}
    for fn in sorted(os.listdir(os.path.join(HERE, "models"))):
        if fn.endswith(".py") and not fn.startswith("_"):
            mod = importlib.import_module(fn[:-3])
            importlib.reload(mod)
            found.update(getattr(mod, "MODELS", {}))
    return found


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    models = all_models()
    names = [n for n in models if not args or n in args]
    missing = [a for a in args if a not in models]
    if missing:
        print("unknown model(s):", ", ".join(missing), "- known:", ", ".join(models))
    report = []
    for name in names:
        M = models[name]()
        tris = M.finish()
        M.export(os.path.join(OUT, name + ".glb"))
        report.append((name, tris, len(M.parts)))
        print(f"built {name:<12} {tris:5d} tris  {len(M.parts):2d} parts")
    print("\nMODEL        TRIS  PARTS")
    for name, tris, parts in report:
        print(f"{name:<12} {tris:5d}  {parts:3d}")
    print(f"{len(report)} models -> {OUT}")


main()
