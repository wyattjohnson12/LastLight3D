"""
tools/shots.py - headless screenshots of the 3D view, for checking graphics changes without playing.

    xvfb-run -a -s "-screen 0 1600x1000x24" python3 tools/shots.py OUTDIR TAG [--only day,night,...]

Starts a real game (hidden window, temp config/saves - your real ones are not touched) with a fixed seed,
builds a small test scene next to the survivor (a lit campfire, a few wood / stone walls, a brazier, a
torch-lit lantern), then saves one PNG per view:

    TAG_day.png  TAG_dusk.png  TAG_night.png       tilted camera
    TAG_fp_day.png  TAG_fp_night.png               first person
    TAG_sheet.png                                  all of the above on one contact sheet

Software OpenGL (llvmpipe) works fine; it's just slow (~1 s a frame). MSAA isn't available under Xvfb.
"""
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

VIEWS = ("day", "dusk", "night", "fp_day", "fp_night")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out, tag = os.path.abspath(args[0]), args[1]
    only = VIEWS
    if "--only" in sys.argv:
        only = tuple(sys.argv[sys.argv.index("--only") + 1].split(","))
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp()
    os.chdir(tmp)
    random.seed(7)
    import arcade
    import main as game_main
    import progress
    import savegame
    from settings import DAY_CYCLE_SECONDS, DUSK_START, NIGHT_START
    game_main.CONFIG = os.path.join(tmp, "config.json")
    progress.ACH_FILE = os.path.join(tmp, "achievements.json")
    savegame.SAVE_DIR = os.path.join(tmp, "saves")
    g = game_main.LastLight()
    g.my_name = "Shot"
    g.start_host(None)
    g.end_intro()
    g.intro = None
    me = g.me.sprite
    x, y = me.center_x, me.center_y
    # a little test base: walls, a lit campfire, a brazier and a lantern near the survivor
    for i, kind in enumerate(("wood_wall", "wood_wall", "stone_wall", "stone_wall", "iron_wall")):
        try:
            g.add_structure(kind, x - 160 + i * 64, y + 150)
        except Exception as e:          # noqa: BLE001 - a missing kind shouldn't stop the shots
            print("shots: no", kind, e)
    for kind, dx, dy in (("campfire", 120, 40), ("brazier", -170, 40), ("lantern", 40, -120)):
        try:
            s = g.add_structure(kind, x + dx, y + dy)
            if s is not None and hasattr(s, "fuel"):
                s.fuel = max(getattr(s, "fuel", 0), 999)
        except Exception as e:          # noqa: BLE001
            print("shots: no", kind, e)
    for _ in range(20):
        g.dispatch_events()
        g.on_update(1 / 30)
    phases = {"day": 0.25, "dusk": (DUSK_START + NIGHT_START) / 2, "night": NIGHT_START + 0.05}
    files = []
    for view in only:
        fp = view.startswith("fp_")
        g.fp_want = fp
        g.fp_yaw = 1.2
        g.clock = phases[view.replace("fp_", "")] * DAY_CYCLE_SECONDS
        for _ in range(6):
            g.dispatch_events()
            g.on_update(1 / 30)
        g.clear()
        g.on_draw()
        path = os.path.join(out, f"{tag}_{view}.png")
        arcade.get_image(0, 0, *g.get_size()).save(path)
        files.append(path)
        print("saved", path)
    try:
        from PIL import Image
        ims = [Image.open(f) for f in files]
        w, h = ims[0].size
        cols = 2
        sheet = Image.new("RGB", (w * cols // 2, h * ((len(ims) + cols - 1) // cols) // 2))
        for i, im in enumerate(ims):
            sheet.paste(im.resize((w // 2, h // 2)), ((i % cols) * w // 2, (i // cols) * h // 2))
        sheet.save(os.path.join(out, f"{tag}_sheet.png"))
    except Exception as e:              # noqa: BLE001
        print("shots: no contact sheet:", e)


if __name__ == "__main__":
    main()
