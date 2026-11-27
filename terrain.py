"""
terrain.py - THE RIVERLANDS (the "meadow" region) and the terrain that crosses the whole map:
rivers, fords and bridges, cliffs, roads, worn ground around bases, and farming. Worldgen 2+ only
(old worldgen-1 saves have none of it and play exactly as before).

What's here:
  * The Riverlands: a calm, open starter region - light meadow grass, wildflowers and tall grass
    (3D blade clumps), few trees, plenty of berries, rabbits, deer and DUCKS on the rivers.
  * Rivers (terrain_map.py): three rivers wind through the meadow, around the forest and out across the
    map, plus a lake. Deep water blocks everyone (you slide along the bank) - survivors, zombies and
    animals - so rivers split the map and make riverside bases easy to defend. Shallow FORDS (stepping
    stones, slow wading) every ~800 px, and the dirt roads cross on wooden bridges. Drink from any river
    (E / B, like a pond). Zombies and pets that hit a river head for the nearest ford or bridge.
  * BRIDGE (Build tab): place it over river water to make your own crossing.
  * Cliffs: rock ledges (solid 3D walls) that make natural chokepoints. They never cut a region off: the
    map is flood-filled from the spawn and every bit of dry land is reachable.
  * Roads: worn dirt roads from the spawn to the middle of every region - walk 15% faster on them.
    STONE PATH tiles (Build tab) do the same for your base (20% faster).
  * Fishing: craft a Fishing Rod, swing it at water (river, lake or pond) to cast, wait for the BITE
    (splash + the bobber dips) and swing again to reel it in. Cook Raw Fish at a campfire.
  * Clay: rounded lumps along the river banks. Clay -> Bricks (furnace) -> BRICK WALL (300 health,
    the stone wall has 120).
  * Farming: a Hoe tills grass into a FARM PLOT. Use seeds on it (right-click): Wheat Seeds and Carrot
    Seeds (from tall grass and your harvests) or a Berry Sapling. Crops grow in three stages over about
    two days (faster next to water), then hit them to harvest. Wheat -> Bread, carrots + fish -> River Stew.
  * Worn ground: where survivors walk around their base (and around the Base Flag) the grass slowly wears
    down to dirt. It's saved and sent to everyone in co-op.

Co-op: the land is rebuilt from the seed on every computer (terrain_map.py). Bridges, farm plots, crops
(the growth stage is the building's kind) and stone paths are ordinary buildings, so they are saved and
synced like walls. Fishing bobbers and the worn ground travel as small "bio" events.
"""
import math
import random
from array import array

import arcade

import art
import art_extra
import base
import biomes
import defenses
import terrain_map as TM
from settings import *
from world import Node, Structure

NAME = "meadow"

# =========================================================================== data (added to settings.py's tables)
ROAD_SPEED = 1.15
PATH_SPEED = 1.2
FORD_SPEED = 0.65
WEAR_CELL = 48
WEAR_STEPS = (30.0, 90.0, 200.0)          # seconds of walking for each stage of worn ground
CROPS = {   # crop: (seed item, seconds per growth stage, produce on harvest, stage it goes back to)
    "wheat": ("wheat_seeds", 170.0, {"wheat": 3, "wheat_seeds": 2}, None),
    "carrot": ("carrot_seeds", 130.0, {"carrot": 4, "carrot_seeds": 1}, None),
    "berry": ("berry_sapling", 210.0, {"berries": 4}, 2),
}
SEED_CROP = {v[0]: k for k, v in CROPS.items()}
FLAT_BUILDS = ("bridge", "stone_path", "farm_plot") + tuple(f"{c}_{s}" for c in CROPS for s in (1, 2, 3))

ITEMS.update({
    "clay": {"name": "Clay", "kind": "material", "desc": "Dug from lumps on river banks. Fire it into bricks in a furnace."},
    "brick": {"name": "Brick", "kind": "material", "desc": "Fired clay. Brick walls are the sturdiest you can build "
                                                         "before iron."},
    "feather": {"name": "Feather", "kind": "material", "desc": "From ducks. Fletch better arrows with it."},
    "raw_fish": {"name": "Raw Fish", "kind": "food", "hunger": 8, "health": -2,
                 "desc": "Caught with a Fishing Rod. Cook it at a campfire."},
    "cooked_fish": {"name": "Cooked Fish", "kind": "food", "hunger": 38, "health": 10, "desc": "+38 hunger, +10 health."},
    "wheat": {"name": "Wheat", "kind": "material", "desc": "Grown on a farm plot. Bake 3 into bread at a campfire."},
    "bread": {"name": "Bread", "kind": "food", "hunger": 55, "energy": 10, "desc": "+55 hunger, +10 energy. Keeps you going."},
    "carrot": {"name": "Carrot", "kind": "food", "hunger": 14, "thirst": 4, "health": 2,
               "desc": "Crunchy. +14 hunger. Goes in River Stew."},
    "river_stew": {"name": "River Stew", "kind": "food", "hunger": 65, "health": 18, "thirst": 10,
                   "desc": "Fish, carrots and water from a campfire. +65 hunger, +18 health, +10 thirst."},
    "wheat_seeds": {"name": "Wheat Seeds", "kind": "seed", "desc": "Right-click next to a farm plot to plant. "
                                                                   "Found in tall grass."},
    "carrot_seeds": {"name": "Carrot Seeds", "kind": "seed", "desc": "Right-click next to a farm plot to plant. "
                                                                     "Sometimes found in tall grass."},
    "berry_sapling": {"name": "Berry Sapling", "kind": "seed", "desc": "Plant on a farm plot: grows into a berry "
                                                                       "bush you can pick again and again."},
    "fishing_rod": {"name": "Fishing Rod", "kind": "tool", "damage": 1, "reach": 54, "cooldown": 0.5, "fish": 1,
                    "desc": "Swing at water to cast. When the bobber dips (a BITE!) swing again to reel it in."},
    "hoe": {"name": "Hoe", "kind": "tool", "damage": 1.5, "reach": 56, "cooldown": 0.45, "till": 1,
            "desc": "Swing at grass to till a farm plot. Plant seeds on it, harvest with any swing."},
    "brick_wall": {"name": "Brick Wall", "kind": "build", "hp": 300,
                   "desc": "Sturdy wall: 300 health (stone has 120, iron 700)."},
    "bridge": {"name": "Bridge", "kind": "build", "hp": 150,
               "desc": "Place it over river water to walk across. Zombies use it too - it's a chokepoint!"},
    "stone_path": {"name": "Stone Path", "kind": "build", "hp": 80,
                   "desc": "Paving for your base: walk 20% faster on it. Doesn't block anyone."},
    "farm_plot": {"name": "Farm Plot", "kind": "crop", "hp": 40, "desc": "Tilled soil. Plant seeds here."},
})
for _c, _n in (("wheat", "Wheat"), ("carrot", "Carrots"), ("berry", "Berry Bush")):
    for _s, _w in ((1, "sprouting"), (2, "growing"), (3, "ripe")):
        ITEMS[f"{_c}_{_s}"] = {"name": f"{_n} ({_w})", "kind": "crop", "hp": 40, "desc": f"{_n}, {_w}."}
ITEMS["pickaxe"].setdefault("harvest", {})["clay"] = 2
ITEMS["iron_pickaxe"].setdefault("harvest", {})["clay"] = 3
NODES.update({
    "clay": {"gives": "clay", "hp": 3, "regrow": 150},
    "river_reeds": {"gives": "reeds", "hp": 2, "regrow": 80},
    "tall_grass": {"gives": "fiber", "hp": 1, "regrow": 70},
})
base.NODE_RADIUS.update({"clay": 24, "river_reeds": 16, "tall_grass": 18})
ANIMALS["duck"] = {"hp": 3, "speed": 120, "temper": "flee", "drops": {"meat": 1, "feather": 2}, "swims": True,
                   "tame": None, "chance": 0, "job": None, "dmg": 0, "desc": ""}
defenses.WALK_THROUGH = tuple(defenses.WALK_THROUGH) + FLAT_BUILDS     # nobody bumps into these

CRAFT_TABS["Tools"].append(R("fishing_rod", {"wood": 3, "fiber": 4}))
CRAFT_TABS["Tools"].append(R("hoe", {"wood": 3, "stone": 2}))
CRAFT_TABS["Build"].append(R("bridge", {"wood": 6, "fiber": 2}))
CRAFT_TABS["Build"].append(R("stone_path", {"stone": 2}, n=2))
CRAFT_TABS["Build"].append(R("brick_wall", {"brick": 4, "stone": 1}, "workbench"))
CRAFT_TABS["Supplies"].append(R("brick", {"clay": 2, "wood": 1}, "furnace", n=2))
CRAFT_TABS["Supplies"].append(R("cooked_fish", {"raw_fish": 1}, "campfire"))
CRAFT_TABS["Supplies"].append(R("bread", {"wheat": 3}, "campfire"))
CRAFT_TABS["Supplies"].append(R("river_stew", {"raw_fish": 1, "carrot": 2, "water": 1}, "campfire"))
CRAFT_TABS["Supplies"].append(R("berry_sapling", {"berries": 3, "fiber": 1}))
CRAFT_TABS["Supplies"].append(R("arrows", {"wood": 2, "stone": 1, "feather": 1}, n=10))
RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]   # same list object, crafting indexes in tab order

import art_terrain  # noqa: E402  (after the tables: registers the new art and 3D shapes)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def tmap(game):
    """The TerrainMap of this game's world (None on legacy worlds)."""
    lay = getattr(game, "layout", None)
    return TM.get(lay) if lay is not None else None


class Deco(arcade.Sprite):
    """Something drawn as a 3D shape that isn't a resource: grass and flower clumps, road bridges, stones."""

    def __init__(self, kind, tex, x, y, variant=0, scale=1.0, angle=0.0):
        super().__init__(tex, center_x=x, center_y=y, scale=scale, angle=angle)
        self.kind, self.variant = kind, variant


# =========================================================================== per-game runtime state
class Runtime:
    def __init__(self, game):
        self.key = (game.seed, id(game.nodes))
        self.m = tmap(game)
        self.deco = arcade.SpriteList()          # meadow grass + wildflower clumps, ford stones, rubble
        self.wbridges = arcade.SpriteList()      # the road bridges
        self.worn = arcade.SpriteList()          # worn-ground patches
        self.worn_spr = {}                       # cell -> sprite
        self.wear = {}                           # host: cell -> seconds of wear
        self.stage = {}                          # every computer: cell -> 0..3
        self.cell_sets_ver = None
        self.bridge_cells = set()                # 20px cells covered by built bridges
        self.path_cells = set()                  # ...and by stone paths
        self.bridge_spots = []
        self.casts = {}                          # host: pid -> {"x","y","t","bite"}
        self.bobbers = {}                        # every computer: pid -> [x, y, bite, t]
        self.leaps = []                          # caught / jumping fish: [kind, x0, y0, x1, y1, t, T]
        self.fish = []                           # visual fish swimming near the viewer
        self.frogs = []
        self.tick = 0.0
        self.seen_players = set()
        self.ducks_seen = set()
        self.geo = None                          # GPU geometry (rivers / roads / cliffs)
        self.vis_t = None
        self.told = False


def rt(game):
    r = getattr(game, "_terrain", None)
    if r is None or r.key != (game.seed, id(game.nodes)):
        r = game._terrain = Runtime(game)
    return r


def _active(game, layer="over"):
    return layer == "over" and getattr(game, "worldgen", 1) != biomes.LEGACY and getattr(game, "layout", None) is not None


def _cells_from_structs(game):
    """Cells covered by built bridges / stone paths (rebuilt when buildings change)."""
    r = rt(game)
    ver = getattr(game, "struct_ver", 0)
    if r.cell_sets_ver == ver:
        return r
    r.cell_sets_ver = ver
    r.bridge_cells, r.path_cells, r.bridge_spots = set(), set(), []
    C = TM.C
    for s in getattr(game, "structs", {}).values():
        if s.layer != "over" or s.kind not in ("bridge", "stone_path"):
            continue
        half = 40 if s.kind == "bridge" else 20
        cells = r.bridge_cells if s.kind == "bridge" else r.path_cells
        for ix in range(int((s.center_x - half + 1) // C), int((s.center_x + half - 1) // C) + 1):
            for iy in range(int((s.center_y - half + 1) // C), int((s.center_y + half - 1) // C) + 1):
                cells.add((ix, iy))
        if s.kind == "bridge":
            r.bridge_spots.append((s.center_x, s.center_y))
    return r


# =========================================================================== terrain hooks (pure functions)
def keepout(layout, x, y):
    m = TM.get(layout)
    return bool(m and m.cell(x, y) & TM.KEEP)


def blocked(game, x, y, layer):
    if not _active(game, layer):
        return False
    m = tmap(game)
    f = m.cell(x, y)
    if f & TM.CLIFF:
        return True
    if f & TM.DEEP and not f & TM.BRIDGE:
        r = _cells_from_structs(game)
        return (int(x // TM.C), int(y // TM.C)) not in r.bridge_cells
    return False


def water(game, x, y, layer):
    return _active(game, layer) and bool(tmap(game).cell(x, y) & TM.WATER)


def speed_at(game, p, dx, dy):
    if p.layer != "over" or not _active(game):
        return 1.0
    x, y = p.pos
    f = tmap(game).cell(x, y)
    if f & TM.FORD:
        return FORD_SPEED
    if (int(x // TM.C), int(y // TM.C)) in _cells_from_structs(game).path_cells:
        return PATH_SPEED
    if f & (TM.ROAD | TM.BRIDGE):
        return ROAD_SPEED
    return 1.0


def detour(game, s, mvx, mvy):
    """A zombie / animal / pet ran into a river: head for the ford or bridge that best fits where it's going."""
    if not _active(game, getattr(s, "layer", "over")):
        return None
    m = tmap(game)
    x, y = s.center_x, s.center_y
    if not (m.cell(x + mvx * 6, y + mvy * 6) & TM.WATER or m.edge_at(x, y) < 40):
        return None                       # a cliff: the usual sidestep works
    n = math.hypot(mvx, mvy) or 1.0
    gx, gy = x + mvx / n * 700, y + mvy / n * 700
    best = None
    for cx, cy in m.crossings + _cells_from_structs(game).bridge_spots:
        d = math.hypot(cx - x, cy - y)
        if d > 1800 or d < 12:
            continue
        cost = d + math.hypot(gx - cx, gy - cy)
        if best is None or cost < best[0]:
            best = (cost, cx, cy, d)
    if best is None:
        return None
    _, cx, cy, d = best
    return (cx - x) / d, (cy - y) / d


def _ground(rng, x, y):
    return art_terrain.meadow_ground(rng.randint(0, 2))


def _decor(rng, x, y):
    return art_terrain.petals(rng.randint(0, 2)) if rng.random() < 0.4 else None


def build_ok(game, item, x, y, layer):
    if not _active(game, layer):
        return None
    m = tmap(game)
    f = m.cell(x, y)
    if item == "bridge":
        if not (f & TM.WATER) or f & TM.BRIDGE:
            return False
        return not any(_dist((x, y), q) < 60 for q in _cells_from_structs(game).bridge_spots)
    if f & (TM.CLIFF | TM.BRIDGE) or game.terrain_water(x, y, layer):
        return False
    return None


# =========================================================================== generation (worldgen 2+, gen.rng only)
def _free(gen, p, rad):
    """gen.free without the keepout check (banks are kept out of the shared content, but they're where
    clay and reeds belong)."""
    g = gen.game
    x, y = p
    if not (80 < x < gen.size - 80 and 80 < y < gen.size - 80):
        return False
    if _dist(p, gen.layout.centre) < 220:
        return False
    m = TM.get(gen.layout)
    if m.cell(x, y) & (TM.WATER | TM.CLIFF | TM.ROAD | TM.BRIDGE) or m.edge_at(x, y) < 6:
        return False
    for s in list(gen.over.ponds) + list(gen.over.exits):
        if _dist(p, s.position) < rad + 110:
            return False
    cells = gen._grid()
    for gx in range(int((x - rad - 90) // 128), int((x + rad + 90) // 128) + 1):
        for gy in range(int((y - rad - 90) // 128), int((y + rad + 90) // 128) + 1):
            for n in cells.get(("over", gx, gy), ()):
                if _dist(n.base, p) < rad + 26:
                    return False
    return True


def _bank_spot(gen, m, rng, off=(10, 28)):
    rv = rng.choice(m.rivers)
    i = rng.randrange(len(rv.pts))
    p = rv.pts[i]
    dx, dy = TM._dir_at(rv.pts, i)
    side = rng.choice((-1, 1))
    d = rv.hw[i] + rng.uniform(*off)
    return p[0] - dy * d * side, p[1] + dx * d * side


def gen_surface(gen):
    g = gen.game
    m = TM.get(gen.layout)
    if m is None:
        return
    rng = gen.rng
    r = rt(g)
    # --- resources: clay and reeds on the banks, tall grass in the meadow
    for kind, count, rad, off in (("clay", 80, 22, (14, 30)), ("river_reeds", 150, 14, (2, 22))):
        placed = 0
        for _ in range(count * 6):
            if placed >= count:
                break
            p = _bank_spot(gen, m, rng, off)
            if gen.biome_at(p) not in ("meadow", "forest", "mire") and rng.random() < 0.6:
                continue
            if not _free(gen, p, rad):
                continue
            if kind == "clay":
                n = gen.add_node(Node("clay", art_terrain.clay(), *p), gen.over.rocks)
                n.angle = n.base_angle = rng.uniform(0, 360)
            else:
                gen.add_node(Node("river_reeds", art_terrain.river_reeds(), *p), gen.over.bushes)
            placed += 1
    placed = 0
    for _ in range(90 * 6):
        if placed >= 90:
            break
        p = gen.spot(NAME)
        if p and gen.free(p, 20):
            gen.add_node(Node("tall_grass", art_terrain.tall_grass(), *p), gen.over.bushes)
            placed += 1
    # --- looks only (not nodes): grass & flower clumps, stones in the fords, road bridges, cliff rubble
    _gen_looks(gen, m, r)


def _gen_looks(gen, m, r):
    rng = random.Random(f"{gen.seed}:meadow:looks")      # visual only: its own stream, so it never shifts nodes
    S = gen.size
    want = {"meadow": 900, "forest": 140}
    for name, count in want.items():
        for _ in range(count):
            p = gen.spot(name, tries=12)
            if p is None or m.cell(*p) & (TM.WATER | TM.ROAD | TM.CLIFF | TM.BRIDGE):
                continue
            if rng.random() < 0.45:
                v = rng.randrange(len(art_terrain.FLOWER_COLS))
                r.deco.append(Deco("wildflower", art_terrain.wildflower(v), *p, variant=v, scale=rng.uniform(0.8, 1.2)))
            else:
                r.deco.append(Deco("meadow_grass", art_terrain.deco_grass(), *p, scale=rng.uniform(0.8, 1.3)))
    for x, y, ang, hw in m.fords:          # stepping stones across each ford
        dx, dy = math.cos(ang), math.sin(ang)
        k = -hw - 6
        while k < hw + 6:
            for lane in (-14, 14):
                if rng.random() < 0.75:
                    px = x - dy * k + dx * (lane + rng.uniform(-6, 6))
                    py = y + dx * k + dy * (lane + rng.uniform(-6, 6))
                    v = rng.randint(0, 3)
                    s = Deco("ford_stone", art.rock(v), px, py, v, scale=rng.uniform(0.32, 0.45),
                             angle=rng.uniform(0, 360))
                    r.deco.append(s)
            k += rng.uniform(22, 30)
    for x, y, ang, L, w in m.bridges:
        s = Deco("world_bridge", art_terrain.bridge(), x, y)
        s.width, s.height = L, w
        s.angle = -math.degrees(ang)
        r.wbridges.append(s)
    for pts, thick, cells in m.cliffs:     # loose boulders at the foot of the cliffs
        for a, b in zip(pts[::2], pts[2::2]):
            if rng.random() < 0.7:
                dx, dy = b[0] - a[0], b[1] - a[1]
                n = math.hypot(dx, dy) or 1
                side = rng.choice((-1, 1))
                px = a[0] - dy / n * (thick / 2 + 14) * side
                py = a[1] + dx / n * (thick / 2 + 14) * side
                if not m.cell(px, py) & TM.CLIFF:
                    v = rng.randint(0, 3)
                    r.deco.append(Deco("ford_stone", art.rock(v), px, py, v, scale=rng.uniform(0.4, 0.65),
                                       angle=rng.uniform(0, 360)))


def _sample(game, rng):
    """Where meadow-only things (clay, reeds, tall grass) grow back: near a river bank, or in the meadow."""
    m = tmap(game)
    if m is None:
        return None
    if rng.random() < 0.6:
        rv = rng.choice(m.rivers)
        i = rng.randrange(len(rv.pts))
        p, (dx, dy) = rv.pts[i], TM._dir_at(rv.pts, i)
        side = rng.choice((-1, 1))
        d = rv.hw[i] + rng.uniform(8, 30)
        q = (p[0] - dy * d * side, p[1] + dx * d * side)
        if game.biome_at(q) == NAME:
            return q
    for _ in range(30):
        q = (rng.uniform(100, game.world_size - 100), rng.uniform(100, game.world_size - 100))
        if game.biome_at(q) == NAME:
            return q
    return None


# =========================================================================== gameplay (host / solo)
def _in_front(p, pos, reach, cone=0.3):
    dx, dy = pos[0] - p.pos[0], pos[1] - p.pos[1]
    d = math.hypot(dx, dy)
    if d > reach:
        return False
    return d < 16 or (dx * math.cos(p.face) + dy * math.sin(p.face)) / d > cone


def _crop_of(kind):
    c, _, s = kind.partition("_")
    return (c, int(s)) if c in CROPS and s.isdigit() else (None, 0)


def swing(game, p, item, w):
    if p.layer != "over" or not _active(game):
        return False
    L = game.over
    enemies = any(_dist(z.position, p.pos) < 110 for z in L.zombies) or \
        any(_dist(b.position, p.pos) < 160 for b in L.bosses)
    # reel in / cast a fishing line
    if item == "fishing_rod":
        return _fish_swing(game, p)
    if enemies:
        return False
    # pick a ripe crop in front (any tool or bare hands)
    for s in list(game.structs.values()):
        crop, stage = _crop_of(s.kind)
        if crop and stage == 3 and s.layer == "over" and _in_front(p, s.position, w["reach"] + 30):
            _harvest_crop(game, p, s, crop)
            return True
    # tall grass: fiber, and sometimes seeds
    nodes = [n for n in L.bushes if n.kind == "tall_grass" and n.state == "full"
             and _in_front(p, n.position, w["reach"] + 34, 0.2)]
    if nodes:
        n = min(nodes, key=lambda n: _dist(n.position, p.pos))
        got = game.harvest(n, 1)
        got["fiber"] = got.get("fiber", 0) + 1
        roll = random.random()
        if roll < 0.4:
            got["wheat_seeds"] = 1
        elif roll < 0.6:
            got["carrot_seeds"] = 1
        game.stat(p, "gathered", sum(got.values()))
        for k, v in got.items():
            game.give(p, k, v, n.position if k == "fiber" else None)
        return True
    if item == "hoe":
        return _till(game, p)
    return False


def _till(game, p):
    tx = p.pos[0] + math.cos(p.face) * 52
    ty = p.pos[1] + math.sin(p.face) * 52
    x, y = math.floor(tx / GRID + 0.5) * GRID, math.floor(ty / GRID + 0.5) * GRID
    for s in game.structs.values():
        if s.layer == "over" and abs(s.center_x - x) < 36 and abs(s.center_y - y) < 36:
            crop, stage = _crop_of(s.kind)
            if s.kind == "farm_plot":
                game.say("Already tilled - right-click with seeds (or a berry sapling) to plant.", 2, to=p)
            elif crop:
                need = CROPS[crop][1]
                game.say(f"{ITEMS[s.kind]['name']} - {int(100 * min(1, s.out_t / need))}% to the next stage.",
                         2, to=p)
            return True
    m = tmap(game)
    L = game.over
    f = m.cell(x, y)
    probe = arcade.SpriteSolidColor(36, 36, center_x=x, center_y=y)
    bad = f & (TM.WATER | TM.CLIFF | TM.ROAD | TM.BRIDGE) or game.terrain_water(x, y) or \
        arcade.check_for_collision_with_lists(probe, [L.solid, L.huts, L.traps, L.exits, L.ponds]) or \
        (game.in_swamp((x, y)) and game.in_bog_pool((x, y)))
    if bad:
        game.say("You can't till here - find open grass.", 1.5, to=p)
        game.play("error", 0.2, to=p)
        return True
    game.add_structure("farm_plot", x, y)
    game.burst(x, y, (120, 88, 56), 10, 90, layer="over")
    game.play("mine", 0.25, at=(x, y), layer="over")
    if not getattr(p, "told_farm", False):
        p.told_farm = True
        game.say("Farm plot! Right-click with Wheat / Carrot Seeds or a Berry Sapling to plant it.", 4, to=p)
    return True


def _replace(game, s, kind):
    x, y = s.center_x, s.center_y
    game.remove_structure(s)
    n = game.add_structure(kind, x, y)
    n.out_t = 0.0
    return n


def _harvest_crop(game, p, s, crop):
    seed, _, produce, back = CROPS[crop]
    for k, v in produce.items():
        game.give(p, k, v, s.position if k != seed else None)
    game.stat(p, "gathered", sum(produce.values()))
    game.burst(s.center_x, s.center_y, (226, 190, 96) if crop == "wheat" else (120, 170, 70), 12, 100, layer="over")
    game.play("pickup", 0.3, at=s.position, layer="over")
    _replace(game, s, f"{crop}_{back}" if back else "farm_plot")


def use(game, p, item):
    """Right-click with seeds: plant them on the nearest free farm plot in front of you."""
    crop = SEED_CROP.get(item)
    if crop is None or p.layer != "over":
        return False
    plots = [s for s in game.structs.values() if s.kind == "farm_plot" and s.layer == "over"
             and _dist(s.position, p.pos) < 110]
    if not plots:
        game.say("Plant on a FARM PLOT: swing a Hoe at open grass to till one.", 2.5, to=p)
        game.play("error", 0.2, to=p)
        return True
    fx, fy = math.cos(p.face), math.sin(p.face)
    s = min(plots, key=lambda s: _dist(s.position, p.pos) - 30 * ((s.center_x - p.pos[0]) * fx + (s.center_y - p.pos[1]) * fy)
            / max(1.0, _dist(s.position, p.pos)))
    if not game.take(p, item):
        return True
    _replace(game, s, f"{crop}_1")
    game.burst(s.center_x, s.center_y, (110, 160, 64), 8, 70, layer="over")
    game.play("place", 0.25, at=s.position, layer="over")
    game.say(f"Planted {ITEMS[item]['name'].lower()}. Crops grow over about two days - faster near water.", 3, to=p)
    return True


def _grow(game, step):
    for s in list(game.structs.values()):
        crop, stage = _crop_of(s.kind)
        if not crop or stage >= 3 or s.layer != "over":
            continue
        k = 1.0
        if game.water_near(s.position, 200):
            k *= 1.3
        if getattr(game, "weather", "clear") in ("rain", "storm"):
            k *= 1.25
        s.out_t += step * k
        if s.out_t >= CROPS[crop][1]:
            n = _replace(game, s, f"{crop}_{stage + 1}")
            if stage + 1 == 3:
                game.burst(n.center_x, n.center_y, (250, 230, 120), 8, 60, layer="over")


# --------------------------------------------------------------------------- fishing
def _water_spot(game, p):
    """Where a cast from p lands: the first water 70..190 px in front (river, lake or pond)."""
    fx, fy = math.cos(p.face), math.sin(p.face)
    for d in range(70, 200, 15):
        x, y = p.pos[0] + fx * d, p.pos[1] + fy * d
        if game.terrain_water(x, y, "over") and not tmap(game).cell(x, y) & TM.BRIDGE:
            return x, y, True
        for s in game.over.ponds:
            if _dist((x, y), s.position) < 62:
                return x, y, False
    return None


def _fish_swing(game, p):
    r = rt(game)
    c = r.casts.get(p.id)
    if c is not None:
        if c["bite"] > 0:
            _catch(game, p, c)
        else:
            game.say("Reeled in - nothing yet. Wait for the bite (the bobber dips), then swing!", 2, to=p)
            _uncast(game, p.id)
        return True
    spot = _water_spot(game, p)
    if spot is None:
        game.say("Swing the rod at water (a river, lake or pond) to cast.", 1.6, to=p)
        return True
    x, y, river = spot
    meadow = game.biome_at((x, y)) == NAME
    c = r.casts[p.id] = {"x": x, "y": y, "t": random.uniform(2.5, 7.0) * (0.7 if meadow else 1.0), "bite": 0.0,
                         "river": river}
    game.play("place", 0.2, at=(x, y), layer="over")
    if game.biome_emit(NAME, ["cast", p.id, round(x, 1), round(y, 1)]):
        _ev_cast(game, p.id, x, y)
    return True


def _uncast(game, pid):
    rt(game).casts.pop(pid, None)
    if game.biome_emit(NAME, ["uncast", pid]):
        rt(game).bobbers.pop(pid, None)


def _catch(game, p, c):
    roll = random.random()
    kind = "fish_gold" if roll < 0.08 else "fish_perch" if roll < 0.4 else "fish"
    n = 3 if kind == "fish_gold" else 2 if (game.biome_at((c["x"], c["y"])) == NAME and random.random() < 0.3) else 1
    game.give(p, "raw_fish", n, (c["x"], c["y"]))
    game.stat(p, "gathered", n)
    game.play("pickup", 0.35, to=p)
    game.say({"fish_gold": "A GOLDEN CARP! (3 fish)", "fish_perch": "Caught a perch!"}.get(kind, "Caught a trout!")
             + ("  Cook it at a campfire." if not getattr(p, "told_fish", False) else ""), 2.5, to=p)
    p.told_fish = True
    game.burst(c["x"], c["y"], (170, 220, 250), 14, 120, layer="over")
    r = rt(game)
    r.casts.pop(p.id, None)
    if game.biome_emit(NAME, ["catch", p.id, kind, round(c["x"], 1), round(c["y"], 1), round(p.pos[0], 1),
                              round(p.pos[1], 1)]):
        _ev_catch(game, p.id, kind, c["x"], c["y"], p.pos[0], p.pos[1])


def _update_casts(game, dt):
    r = rt(game)
    for pid, c in list(r.casts.items()):
        p = game.players.get(pid)
        if p is None or not p.alive or p.layer != "over" or p.hotbar[p.selected] != "fishing_rod" or \
                _dist(p.pos, (c["x"], c["y"])) > 280:
            _uncast(game, pid)
            continue
        if c["bite"] > 0:
            c["bite"] -= dt
            if c["bite"] <= 0:
                c["t"] = random.uniform(3.0, 7.0)
                game.say("It got away... wait for the next bite.", 1.6, to=p)
                if game.biome_emit(NAME, ["bite", pid, 0]):
                    _ev_bite(game, pid, 0)
            continue
        c["t"] -= dt
        if c["t"] <= 0:
            c["bite"] = 1.4
            game.say("A BITE! Swing now!", 1.4, to=p)
            game.play("drink", 0.4, at=(c["x"], c["y"]), layer="over")
            game.burst(c["x"], c["y"], (200, 230, 255), 8, 70, layer="over")
            game.rumble(0.5, 0.2, to=p)
            if game.biome_emit(NAME, ["bite", pid, 1]):
                _ev_bite(game, pid, 1)


# --- visual side of the events (every computer)
def _ev_cast(game, pid, x, y):
    rt(game).bobbers[pid] = [x, y, 0, 0.0]


def _ev_bite(game, pid, on):
    b = rt(game).bobbers.get(pid)
    if b:
        b[2] = int(on)


def _ev_catch(game, pid, kind, x, y, px, py):
    r = rt(game)
    r.bobbers.pop(pid, None)
    r.leaps.append([kind, x, y, px, py, 0.0, 0.7])


# --------------------------------------------------------------------------- worn ground
def _update_wear(game, step):
    r = rt(game)
    m = r.m
    changed = []

    def add(cell, v):
        x, y = (cell[0] + 0.5) * WEAR_CELL, (cell[1] + 0.5) * WEAR_CELL
        if m.cell(x, y) & (TM.WATER | TM.ROAD | TM.CLIFF):
            return
        w = r.wear.get(cell, 0.0) + v
        r.wear[cell] = w
        st = sum(1 for t in WEAR_STEPS if w >= t)
        if st != r.stage.get(cell, 0):
            r.stage[cell] = st
            changed.append([cell[0], cell[1], st])

    for p in game.alive_players("over"):
        if not game.in_base(p.pos):
            continue
        moving = (p.move[0] or p.move[1]) and not p.resting
        c = (int(p.pos[0] // WEAR_CELL), int(p.pos[1] // WEAR_CELL))
        add(c, step * (1.0 if moving else 0.35))
    flag = game.base_flag()
    if flag is not None and flag.layer == "over":
        fc = (int(flag.center_x // WEAR_CELL), int(flag.center_y // WEAR_CELL))
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                d = math.hypot(dx, dy)
                if d <= 2.3:
                    add((fc[0] + dx, fc[1] + dy), step * (0.5 if d < 1.5 else 0.2))
    if changed:
        _apply_wear(game, changed)
        game.biome_emit(NAME, ["wear", changed])


def _apply_wear(game, rows):
    r = rt(game)
    for cx, cy, st in rows:
        cell = (int(cx), int(cy))
        r.stage[cell] = int(st)
        spr = r.worn_spr.get(cell)
        if st <= 0:
            if spr is not None:
                spr.remove_from_sprite_lists()
                r.worn_spr.pop(cell, None)
            continue
        if spr is None:
            rnd = random.Random(cell[0] * 7919 + cell[1])
            spr = arcade.Sprite(art_terrain.dirt(rnd.randint(0, 2)), center_x=(cell[0] + 0.5) * WEAR_CELL,
                                center_y=(cell[1] + 0.5) * WEAR_CELL, angle=rnd.uniform(0, 360))
            spr.scale = 0.85 + 0.15 * rnd.random()
            r.worn.append(spr)
            r.worn_spr[cell] = spr
        spr.alpha = (0, 110, 175, 235)[min(3, int(st))]


def _wear_rows(game):
    return [[c[0], c[1], s] for c, s in rt(game).stage.items() if s > 0]


# --------------------------------------------------------------------------- ducks
def _update_ducks(game):
    r = rt(game)
    m = r.m
    for a in list(game.over.animals):
        if a.kind != "duck" or a.pet:
            continue
        if a.aid not in r.ducks_seen:           # a new duck: it belongs on the water
            r.ducks_seen.add(a.aid)
            spot = _near_water(m, a.position, 900)
            if spot is None:
                game.amap.pop(a.aid, None)
                a.remove_from_sprite_lists()
                continue
            if _dist(spot, a.position) > 120:
                a.position = spot
        if m.edge_at(a.center_x, a.center_y) > 90 and random.random() < 0.3:
            spot = _near_water(m, a.position, 600)
            if spot:
                a.heading = math.atan2(spot[1] - a.center_y, spot[0] - a.center_x)
                a.goal = "walk"
                a.wander_t = 2.5


def _near_water(m, pos, radius):
    best = None
    for rv in m.rivers:
        for q in rv.pts[::3]:
            d = _dist(pos, q)
            if d < radius and (best is None or d < best[0]):
                best = (d, q)
    return best[1] if best else None


# --------------------------------------------------------------------------- the per-frame hook
def update(game, dt):
    if not _active(game):
        return
    r = rt(game)
    _update_casts(game, dt)
    r.tick -= dt
    if r.tick > 0:
        return
    r.tick = 1.0
    _grow(game, 1.0)
    _update_wear(game, 1.0)
    _update_ducks(game)
    now = set(game.players)
    for pid in now - r.seen_players:          # someone joined: send them the worn ground so far
        p = game.players[pid]
        if p.conn is not None and r.stage:
            game.biome_emit(NAME, ["wear", _wear_rows(game)], to=p)
    r.seen_players = now


def event(game, ev):
    k = ev[2]
    if k == "wear":
        _apply_wear(game, ev[3])
    elif k == "cast":
        _ev_cast(game, ev[3], ev[4], ev[5])
    elif k == "uncast":
        rt(game).bobbers.pop(ev[3], None)
    elif k == "bite":
        _ev_bite(game, ev[3], ev[4])
    elif k == "catch":
        _ev_catch(game, *ev[3:9])


def save(game):
    if not _active(game):
        return None
    return {"wear": [[c[0], c[1], round(v, 1)] for c, v in rt(game).wear.items() if v >= 1.0]}


def load(game, data):
    if not data or not _active(game):
        return
    r = rt(game)
    rows = []
    for cx, cy, v in data.get("wear", []):
        cell = (int(cx), int(cy))
        r.wear[cell] = float(v)
        rows.append([cell[0], cell[1], sum(1 for t in WEAR_STEPS if v >= t)])
    _apply_wear(game, rows)


def ambient(game, dt, x, y):
    r = rt(game)
    if not r.told and game.state == "playing" and game.me and game.me.alive:
        r.told = True
        game.message, game.message_t = ("THE RIVERLANDS: calm meadows and wide rivers. Cross at fords and bridges, "
                                        "fish, dig clay on the banks, farm with a hoe.", 7)
    if random.random() < dt * 3 and game.darkness < 0.4:     # butterflies
        a = random.uniform(0, math.tau)
        d = random.uniform(60, 300)
        px, py = x + math.cos(a) * d, y + math.sin(a) * d
        game._burst(px, py, random.choice(((250, 240, 150), (250, 190, 230), (200, 220, 255))), 1, 18, 3.0, 1.4, "over")


import terrain_draw  # noqa: E402  (the 3D drawing: rivers, roads, cliffs, bridges, crops, fish)

biomes.register(biomes.Biome(
    NAME, title="The Riverlands", order=15,
    tint=(238, 250, 190),
    density={"tree": 0.3, "bush": 1.0, "pond": 1.0, "hive": 1.0, "decor": 1.0, "rock": 0.5, "iron": 0.4},
    node_kinds=("clay", "river_reeds", "tall_grass"),
    animals={"rabbit": 6, "deer": 5, "boar": 2, "wolf": 1, "bee": 5, "duck": 6},
    gen_surface=gen_surface, ground=_ground, decor=_decor, sample=_sample,
    keepout=keepout, blocked=blocked, water=water, speed_at=speed_at, detour=detour,
    swing=swing, use=use, build_ok=build_ok, update=update, ambient=ambient,
    save=save, load=load, event=event, draw3d=terrain_draw.draw3d,
))
