"""
highlands.py - THE STONE HIGHLANDS: rocky upland region of the big map, home of the Quake Titan. (STUB)

Scope (the agent building this owns): stony ground tiles + tint, boulders / standing stones / scree decor,
more rock & iron (add extra nodes in gen_surface), highland-only ore (node_kinds), wind (ambient), a grey
haze (fog), mountain goats or similar (animals), and the Quake Titan's lair (gen.layout.centres["highlands"]).
The actual HEIGHT of the ground is hills.py's job (it can read biome_at to make the highlands higher);
cliffs / ledges are terrain.py's. Coordinate through the hooks, not by editing each other's files.

Files this agent owns: highlands.py, art_highlands.py (new 2D art), new SHAPES entries in shapes3d.py (see the
guide at the top of shapes3d.py). Items / recipes / nodes go into settings.py's tables from this file.
Read docs/BIOMES.md first.

Rules: generation uses gen.rng ONLY; only ADD nodes; restyle shared nodes, never move / remove them.
"""
import biomes

NAME = "highlands"


def gen_surface(gen):
    """Worldgen 2+ only. gen.rng, gen.spot(NAME), gen.free(p, r), gen.add_node(...)."""
    return


biomes.register(biomes.Biome(
    NAME, title="The Stone Highlands", order=40,
    tint=(186, 190, 170),
    density={"tree": 0.35, "bush": 0.4, "pond": 0.5, "hive": 0.3, "decor": 0.7, "rock": 1.0, "iron": 1.0},
    animals={"rabbit": 3, "deer": 2, "boar": 2, "wolf": 3, "bee": 1},
    fog=(170, 175, 185, 18),
    gen_surface=gen_surface,
))
