"""
hills.py - REAL HILLS: a ground height map for the surface. (STUB)

Scope (the agent building this owns):
  * height(game, x, y) below: the ground height in px at any surface point. A pure, smooth function of the
    seed / layout (game.layout, biomes.fbm / biomes.noise), so every computer agrees. It returns 0 for now;
    flatten it near the spawn (game.layout.centre) and under bases if you like, and make the Stone Highlands
    (game.biome_at(...) == "highlands") the highest ground. game.ground_height(x, y) sums every module's height.
  * The 3D view: lift ground tiles, decor, nodes, buildings, creatures and shadows by the height (view3d.py's
    shaders - you own the height-related changes in view3d.py; keep them in one clearly marked place) and the
    first-person eye height (firstperson.py).
  * Slower walking uphill / faster downhill: speed_at(game, p, dx, dy) (main.move_player multiplies it in).
  * Turrets see farther from high ground: defenses.py's range check (use game.ground_height).
  * Cave / deep layers stay flat (only "over" has height).

Files this agent owns: hills.py, the height parts of view3d.py / firstperson.py / defenses.py.
Read docs/BIOMES.md first. Keep heights deterministic (no global random) and cheap (called a lot: cache a grid).
"""
import biomes

NAME = "hills"


def height(game, x, y):
    """Ground height (px) at surface point (x, y). 0 = flat (the whole map, for now)."""
    return 0.0


biomes.register(biomes.Biome(
    NAME, title="Hills", order=70, region=False, legacy=False,
    height=height,
    # speed_at=lambda game, p, dx, dy: 1.0,   # uphill slower: compare height ahead vs here
))
