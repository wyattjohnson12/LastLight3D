# Biomes, terrain and layers: how to add content to the world

The surface of a new world is a 5600 x 5600 map split into six biomes. Each biome, terrain feature and
extra underground layer lives in **its own module**. The module registers itself with `biomes.py`, and the game
calls its hooks. If you are adding a biome, you should only need to edit your own module, a new
`art_<yours>.py`, and new entries in `shapes3d.SHAPES`.

| Region / feature | Module | Registered name | Order |
|---|---|---|---|
| The Forest (spawn, centre) | `biomes.py` | `forest` | 0 |
| The Mire (swamp) | `swamp.py` | `mire` | 10 |
| Riverlands / Meadow + rivers, bridges, cliffs, roads, trampled ground, farmland | `terrain.py` | `meadow` | 15 |
| Frostwood Tundra (Frost Wraith) | `tundra.py` | `tundra` | 20 |
| The Ashlands (Inferno Colossus) | `ashlands.py` | `ash` | 30 |
| The Stone Highlands (Quake Titan) | `highlands.py` | `highlands` | 40 |
| Crystal Hollows (layer `"deep"`, reached from the cave) | `hollows.py` | `hollows` | 60 |
| Hills (ground height map) | `hills.py` | `hills` | 70 |

## The layout (worldgen 2)

* The map is `biomes.WORLD_SIZES[2]` = **5600 px** square (the old map was 3200). Read the size from
  `game.world_size` or `layer.size`. Don't use `settings.WORLD_SIZE`: that is the legacy size.
* The **forest** is a wobbly disc in the middle, about 1180 px across its radius. Spawn is at the centre.
* The other five sit in a ring of wedges around it, in this order: **tundra, highlands, ash, mire, meadow**.
  The seed rotates the ring. Each wedge covers about 14-23% of the map, and the forest about 14%.
* Borders are warped with noise (`biomes.fbm`), so they're organic. Small exclaves can happen.
* `game.biome_at((x, y))` returns the region name (on other layers it returns the layer name).
  `game.layout.centres[name]` is a spot well inside each region; use it for boss lairs and landmarks.
* `game.biome_weights(pos, radius)` returns `{biome: share}` from 9 samples. It blends things across
  borders, and the ground tint already uses it (`biomes.blend_tint`).
* Legacy worlds (worldgen 1) use `LegacyLayout`: `"mire"` inside the swamp blobs, `"forest"` everywhere else.

## Adding a biome (template: `tundra.py`)

```python
import biomes
from world import Node

NAME = "tundra"

def gen_surface(gen):                       # gen: biomes.Gen
    for _ in range(40):
        p = gen.spot(NAME)                  # random point in this biome (gen.rng)
        if p and gen.free(p, 30):           # clear of nodes, ponds, exits, spawn, rivers/cliffs
            n = gen.add_node(Node("ice_rock", art_tundra.ice_rock(), *p), gen.over.rocks)

biomes.register(biomes.Biome(NAME, title="Frostwood Tundra", order=20, tint=(214, 228, 240),
                             density={"tree": 0.55, "bush": 0.25}, node_kinds=("ice_rock",),
                             gen_surface=gen_surface, player_tick=lambda game, p, dt: 0.6))
```

Items, recipes, node kinds, zombies and bosses go into `settings.py`'s tables **from your module**
(`ITEMS.update`, `NODES.update`, `CRAFT_TABS[...].append(R(...))`, then
`RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]`). `swamp.py` is the worked example. Plug-ins
are imported by `biomes.load_plugins()` in the `biomes.PLUGINS` order. `main.py` calls it right after `swamp`,
before `ui.py` builds the crafting tabs. Add new respawn radii to `base.NODE_RADIUS` from your module if they
aren't 30.

### Every hook (all optional) - `biomes.Biome(...)`

| Hook | Signature | Runs on | Called from |
|---|---|---|---|
| `gen_surface` | `(gen)` | every computer | `biomes.generate` (after shared content + Mire) |
| `gen_layers` | `(gen)` | every computer | `biomes.generate` (after all `gen_surface`) |
| `ground` | `(rng, x, y) -> texture or None` | every computer | `world._build_v2` per 256 px tile |
| `decor` | `(rng, x, y) -> texture, None (default tuft) or False (none)` | every computer | `world._build_v2` |
| `keepout` | `(layout, x, y) -> bool` | every computer | `world._build_v2` spot picking, `gen.free` |
| `tint` | `(r, g, b)` multiplied into ground tiles, blended at borders | | `world._build_v2` |
| `density` | `{"tree"/"rock"/"bush"/"iron"/"pond"/"hive"/"decor"/"cave": 0..1}` share of the shared content | | `world._build_v2` |
| `node_kinds` | kinds that only grow / respawn here | host | `base.spot_ok`, `node_spot_candidate` |
| `forbid` | kinds that never respawn here | host | `base.spot_ok` |
| `sample` | `(game, rng) -> (x, y)` random point here for respawns | host | `node_spot_candidate` |
| `respawn_variant` | `(game, node, x, y) -> (variant, base_angle) or None` | host | `base.respawn_node` |
| `zombie` | `(game, kind, x, y) -> kind` swap a spawning night zombie | host | `main.spawn_zombie` |
| `animals` | `{"rabbit": 5, ...}` wild animal weights here | host | `main.spawn_animal` |
| `update` | `(game, dt)` every frame while playing | host / solo | `main.on_update` |
| `player_tick` | `(game, p, dt) -> extra cold per second` (negative = warming); deal hazard damage here | host / solo | `main._update_survivor` |
| `speed` | `(game, p) -> multiplier` while p stands in this biome | the computer moving p | `main.move_player` |
| `fog` | `(r, g, b, a)` screen haze while the viewer is here (blended) | every computer | `weather.draw_weather_3d` |
| `ambient` | `(game, dt, x, y)` particles / sounds where the viewer is | every computer | `main.on_update` |
| `height` | `(game, x, y) -> px` (summed over modules) | every computer | `game.ground_height` |
| `blocked` | `(game, x, y, layer) -> bool` nobody walks here | every computer | `main.move_player`, `base.spot_ok`, `gen.free` |
| `water` | `(game, x, y, layer) -> bool` | every computer | `base.spot_ok`, `gen.free` (wire drinking in yourself) |
| `speed_at` | `(game, p, dx, dy) -> multiplier` (slopes, roads) | the computer moving p | `main.move_player` |
| `order` | generation order. Fixed: never renumber a released module | | |
| `region` | `True` if `biome_at` can return it (`False` for terrain / hills / hollows) | | |
| `legacy` | also runs on worldgen 1 worlds (see save rules) | | |

`gen` (a `biomes.Gen`) gives you `gen.rng`, `gen.seed`, `gen.size`, `gen.layout`, `gen.layers`, `gen.over`,
`gen.cave`, `gen.nodes`, `gen.game`, `gen.scale` (area relative to the old map), `gen.biome_at(p)`,
`gen.spot(biome)`, `gen.free(p, radius, layer)` (uses a lookup grid, so it's fast) and
`gen.add_node(node, list, layer)`.

## Determinism rules (must read)

The world is **never sent over the network or saved**. Every computer rebuilds it from the seed: the solo
player, the co-op host, every co-op client, and every load of a save. So:

1. **During generation, use `gen.rng` only.** It is `random.Random(f"{seed}:{module name}")`. Don't use the
   global `random`, `time`, `id()`, set iteration order or `hash()` of strings (that one is randomised per process).
   `biomes.noise` / `biomes.fbm` / `biomes.seed_int` are deterministic.
2. Each module has its own stream, so adding, removing or changing one module never changes another module's
   random numbers. The shared content in `world._build_v2` uses a separate stream per item for the same reason.
3. Hooks run in a **fixed order**: `order`, then name. All `gen_surface` hooks run first, then all `gen_layers`.
4. **Only add nodes.** Node indices (`n.idx`, their place in `game.nodes`) are how saves and co-op
   snapshots refer to nodes. You may restyle shared nodes in your biome (variant / texture, as `swamp.py`
   does with trees). Don't move, remove or reorder them.
5. Terrain functions (`height`, `blocked`, `water`, `keepout`, `speed_at`) must be pure functions of the seed,
   layout and position, cheap, and identical on every computer. Cache a grid if they are expensive.
6. Runtime randomness (spawns, particles) is host-side or visual-only, so the global `random` is fine there.

`python3 test_worldgen.py` checks determinism, the legacy fingerprints and save round-trips. Run it, along
with `python3 test_base.py` and `python3 tools/coop_test.py`.

## Save compatibility rules

* Saves store `"worldgen"` (the version) and `"spans"` (`{module: [first node index, count]}`).
  **A save without `"worldgen"` is worldgen 1.** It is rebuilt by `world._build_legacy` + the legacy branch of
  `Swamp.build_swamp`, exactly as before. Never change those two code paths.
  `test_worldgen.py` pins their output with fingerprints.
* Worldgen 2 is **frozen once released**. If you change the shared generation (`world._build_v2`, the layout,
  the Mire's v2 branch), add worldgen 3 and keep 2 for its saves: `biomes.WORLD_SIZES`, `make_layout`,
  `build_world`. During development (before release) you may tune freely.
* A module that changes its **own** node count only breaks its own saved nodes. Loading remaps every other
  module's node indices through the spans (`biomes.remap_index`), and the changed module's nodes beyond its new
  count are dropped.
* `legacy=True` modules also run on old worlds. They may only append nodes, and must sort after every other
  `legacy=True` module that existed when the save was made. Prefer `legacy=False` unless old worlds really need it.
* New save fields: add them with `data.get(..., default)` so older saves still load.

## Co-op rules

* The host is authoritative for anything that changes: node states, moved nodes, zombies, animals, bosses,
  hazards, damage, buildings, weather. Hooks marked "host" above only run on the host (or in solo).
* Clients regenerate the map from the seed. The host's `"world"` message carries `seed` and `wg`
  (worldgen). A host without `wg` is an old version, so its clients use the legacy map.
* `speed` and `speed_at` run on the computer that moves the player (clients move themselves), so they must
  only read the shared, deterministic world. `fog`, `ambient` and `height` run everywhere and are visual
  (plus movement for height).
* Layers are sent as their index in `world.LAYERS`. Register extra layers at import time with
  `biomes.register_layer` (in `PLUGINS` order), so every computer has the same list.

## Extra layers (the Crystal Hollows)

`biomes.register_layer(biomes.LayerInfo("deep", size, enter=..., leave=..., cold=..., dark=..., zombie=..., depth=2))`
appends to `world.LAYERS`. `world.build_world` then creates an empty `Layer` for it in every world. Fill it in a
`gen_layers` hook: floor sprites in `L.ground`, walls in `L.walls` + `L.solid` (view3d draws any non-surface
layer's walls as 3D blocks, on `CAVE_CELL` cells), and nodes with
`gen.add_node(Node(kind, tex, x, y, layer="deep"), L.rocks, layer="deep")`. Link it with exit sprites in both
layers' `.exits` plus `game.add_portal("cave", cave_pos, "deep", deep_pos)`. `main.travel` uses
`game.portals` (the old `links` are portals too).

Layer-generic code already handles any layer: `main.travel` / `set_layer`, underground zombie spawning, cold
(`LayerInfo.cold`), darkness (`LayerInfo.dark`, used by view3d), base.py respawns, cave-wall rendering, the
`ui.py` / `firstperson.py` underground looks, net sync (layer index) and saves.

**Still assumes `"cave"`** (change it when you need to): `fx3d.py` (`vl == "cave"` for the cave ambient light
and exit glow). Another agent is editing `fx3d.py` right now, so change it after that lands. Pets, animals,
bosses and weather are surface-only (`"over"`) by design.

## 3D objects

Anything new that stands in the world (trees, crystals, rocks, lava vents, bridges) is drawn in 3D through
**`shapes3d.py`'s `SHAPES` table**. A node / building whose `.kind` has a `SHAPES` entry is drawn as that
shape, with its 2D picture draped on it. Anything without one is a flat standing cut-out. Read the
how-to guide at the top of `shapes3d.py` before adding entries (tree canopies, foliage, glowing mushrooms,
blade clumps, ...). Another agent is writing it right now. Add new entries; don't change existing ones.

## File ownership (parallel work)

| Agent | Owns | Touches elsewhere (small, clearly marked) |
|---|---|---|
| Tundra | `tundra.py`, `art_tundra.py` | `shapes3d.SHAPES` entries; Frost Wraith lair/behaviour hooks in `main.py` only if needed |
| Ashlands | `ashlands.py`, `art_ash.py` | `shapes3d.SHAPES` entries |
| Highlands | `highlands.py`, `art_highlands.py` | `shapes3d.SHAPES` entries |
| Terrain / Meadow | `terrain.py`, `art_terrain.py` | `shapes3d.SHAPES`; drinking from rivers in `main.near_pond`; `main.step_body` if rivers must block zombies |
| Hollows | `hollows.py`, `art_hollows.py` | `shapes3d.SHAPES`; `fx3d.py` `"cave"` checks |
| Hills | `hills.py` | height in `view3d.py` shaders, `firstperson.py` eye height, `defenses.py` turret range |

Nobody but the owner of `biomes.py` changes the layout, `world._build_v2` or the hook plumbing. If you need
a new hook, add it in `biomes.Biome.HOOKS` + one `BiomeWorld` method + one call site, and note it here.
