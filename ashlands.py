"""
ashlands.py - THE ASHLANDS: the volcanic region of the big map, home of the Inferno Colossus. (STUB)

Scope (the agent building this owns): ash / basalt ground tiles + tint, charred trees (restyle the few shared
trees here in gen_surface), lava pools / vents (hazards: use the blocked / water hooks or Hazard objects in
update), obsidian / sulfur resources (node_kinds), heat (player_tick can return NEGATIVE cold = warmth, plus
burn damage near lava), ember particles (ambient), a red-brown haze (fog), ash zombies, and the Inferno
Colossus's lair (gen.layout.centres["ash"]).

Files this agent owns: ashlands.py, art_ash.py (new 2D art), new SHAPES entries in shapes3d.py (see the guide at
the top of shapes3d.py). Items / recipes / nodes are added to settings.py's tables from this file (see swamp.py).
Read docs/BIOMES.md first.

Rules: generation uses gen.rng ONLY; only ADD nodes; restyle shared nodes, never move / remove them.
"""
import biomes

NAME = "ash"


def gen_surface(gen):
    """Worldgen 2+ only. gen.rng, gen.spot(NAME), gen.free(p, r), gen.add_node(...)."""
    return


biomes.register(biomes.Biome(
    NAME, title="The Ashlands", order=30,
    tint=(150, 128, 112),
    density={"tree": 0.12, "bush": 0.05, "pond": 0.0, "hive": 0.0, "decor": 0.3, "rock": 1.0, "iron": 1.0},
    animals={"rabbit": 1, "deer": 0, "boar": 2, "wolf": 2, "bee": 0},
    fog=(90, 45, 25, 30),
    gen_surface=gen_surface,
    # forbid=("bush",),                       # berry bushes never grow back in the ash
    # player_tick=lambda game, p, dt: -0.5,   # warm here (negative cold)
))
