"""
hollows.py - THE CRYSTAL HOLLOWS: a third, deeper underground layer ("deep") reached from the cave. (STUB)

Scope (the agent building this owns): carving the "deep" layer (cave-like cells: put floor sprites in
L.ground and wall sprites in L.walls + L.solid, exactly like world._build_cave, and view3d draws them as
3D blocks automatically for any non-"over" layer), ladders down from the cave (exit sprites in both
layers' .exits + game.add_portal("cave", pos_in_cave, "deep", pos_in_deep)), glowing crystal formations,
deep-only ores (gen.add_node(Node(kind, tex, x, y, layer="deep"), L.rocks, layer="deep")), deep enemies
(LAYER_INFO zombie hook), its own cold / darkness (LayerInfo cold / dark), and crystal light.

How layers work: register_layer() below appends "deep" to world.LAYERS at import time, so every world has an
(empty) "deep" Layer and the layer index for the network / saves is stable. Layer-generic code: main.travel
(portals), set_layer, underground spawning + cold, base.py respawns, view3d walls, ui / firstperson. Code that
STILL assumes "cave" (needs a touch if the Hollows should look like the cave): fx3d.py (`vl == "cave"` for the
cave ambient light and exit glow - fx3d.py is being edited by another agent right now: change it after that
lands), pets only live on the surface ("over").

Files this agent owns: hollows.py, art_hollows.py, new SHAPES entries in shapes3d.py (see the guide at the top
of shapes3d.py). Read docs/BIOMES.md first.

Should old (worldgen 1) saves get the Hollows? Set legacy=True on the Biome below if so - then ONLY ADD nodes
(they go at the end of the node list, so old saves still line up) and keep the cave itself unchanged: the
ladder down must sit on an existing open cave cell (pick one deterministically with gen.rng).
"""
import biomes
from settings import CAVE_SIZE

NAME = "hollows"
LAYER = "deep"

biomes.register_layer(biomes.LayerInfo(
    LAYER, CAVE_SIZE, depth=2,
    enter="THE CRYSTAL HOLLOWS. Deeper, colder, stranger.", leave="Back up to the cave.",
    cold=1.1, dark=0.95,
    zombie=lambda game, roll: "golem" if roll < 0.35 else "crawler",
))


def gen_layers(gen):
    """Runs after every gen_surface hook. Carve gen.layers["deep"], add its nodes and the portal(s)."""
    return


biomes.register(biomes.Biome(NAME, title="The Crystal Hollows", order=60, region=False, gen_layers=gen_layers))
