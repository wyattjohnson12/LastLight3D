"""
terrain.py - THE MEADOW (Riverlands) region, plus terrain features that cross the whole map:
rivers with bridges, cliffs / ledges, paths / roads, trampled ground and farmland. (STUB)

Scope (the agent building this owns):
  * The "meadow" region: open grassland, flowers, more berry bushes, fewer trees; ground tiles + tint.
  * Rivers: a pure function of the seed + layout (so every computer agrees without sending anything).
    - keepout(layout, x, y)  keeps the shared trees / rocks / ponds out of the water and off roads
      (world.build_world consults it - it must already work when the shared content is generated).
    - blocked(game, x, y, layer) for deep water / cliff faces (players slide along it; main.move_player).
    - water(game, x, y, layer) so you can drink from rivers (hook main.near_pond / drink if you want).
    - bridges: gaps in blocked() + bridge sprites in gen_surface.
    - Zombies and animals collide with L.solid sprites, not blocked(): if they must not cross rivers either,
      put invisible solid sprites along the banks or extend main.step_body (document it if you do).
  * Cliffs / ledges (blocked + art), paths / roads (speed_at > 1 on roads, keepout), trampled ground
    (runtime: worn paths where survivors walk a lot - visual, keep it out of the save unless you add a field)
    and farmland (tilled ground + planting crops: new items / buildings in this file).

Files this agent owns: terrain.py, art_terrain.py, new SHAPES entries in shapes3d.py (see the guide at the top
of shapes3d.py). Items / recipes / nodes go into settings.py's tables from this file. Read docs/BIOMES.md first.

Order: this module generates at order 15, i.e. BEFORE tundra / ash / highlands extras, so their gen.free()
already sees the rivers (gen.free checks keepout / blocked / water).
"""
import biomes

NAME = "meadow"


def gen_surface(gen):
    """Worldgen 2+ only. Bridges, roads, farm plots, meadow flowers... gen.rng only."""
    return


biomes.register(biomes.Biome(
    NAME, title="The Riverlands", order=15,
    tint=(238, 250, 190),
    density={"tree": 0.3, "bush": 1.0, "pond": 1.0, "hive": 1.0, "decor": 1.0, "rock": 0.5, "iron": 0.4},
    animals={"rabbit": 6, "deer": 5, "boar": 2, "wolf": 1, "bee": 5},
    gen_surface=gen_surface,
    # keepout=lambda layout, x, y: river_dist(layout, x, y) < 90,
    # blocked=lambda game, x, y, layer: layer == "over" and river_dist(game.layout, x, y) < 60 and not bridge(...),
    # water=lambda game, x, y, layer: layer == "over" and river_dist(game.layout, x, y) < 140,
    # speed_at=lambda game, p, dx, dy: 1.15 if on_road(game.layout, *p.pos) else 1.0,
))
