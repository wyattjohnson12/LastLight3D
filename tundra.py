"""
tundra.py - FROSTWOOD TUNDRA: the frozen region of the big map, home of the Frost Wraith. (STUB)

Scope (the agent building this owns): snowy ground tiles + tint, pine / frosted trees (restyle the shared
trees in this biome inside gen_surface, like swamp.py turns trees into swamp trees), ice / snow decor,
tundra-only resources (node_kinds), the cold (player_tick returns extra cold per second; Frost Cloak's
warmth already counts through p.gear("warmth")), deep-snow slowdown (speed), snowfall particles (ambient),
a fog tint, tundra animals / zombies, and the Frost Wraith's lair spot (gen.layout.centres["tundra"]).

Files this agent owns: tundra.py, art_tundra.py (new 2D art), and new SHAPES entries in shapes3d.py for any
new 3D objects (see the how-to guide at the top of shapes3d.py). Items / recipes / nodes go into settings.py's
tables FROM THIS FILE (ITEMS.update(...), NODES.update(...), CRAFT_TABS[...].append(R(...)) then rebuild
RECIPES like swamp.py does) - don't edit settings.py. Read docs/BIOMES.md first.

Rules: generation uses gen.rng ONLY (never the global random); only ADD nodes (gen.add_node); the shared
trees / rocks / bushes already standing here may be restyled (variant, texture) but never moved or removed.
"""
import biomes

NAME = "tundra"


def gen_surface(gen):
    """Worldgen 2+ only. Runs after the shared content and the Mire, before ash / highlands / terrain extras.
    Place things with gen.spot(NAME) + gen.free(p, radius) and gen.add_node(Node(...), gen.over.trees)."""
    return


biomes.register(biomes.Biome(
    NAME, title="Frostwood Tundra", order=20,
    tint=(214, 228, 240),
    density={"tree": 0.55, "bush": 0.25, "pond": 0.6, "hive": 0.0, "decor": 0.6},
    animals={"rabbit": 4, "deer": 3, "boar": 1, "wolf": 4, "bee": 0},
    fog=(200, 215, 235, 26),
    gen_surface=gen_surface,
    # player_tick=lambda game, p, dt: 0.6,     # extra cold per second while standing here
    # speed=lambda game, p: 0.9,               # deep snow
    # ground=lambda rng, x, y: art_tundra.snow(rng.randint(0, 2)),
))
