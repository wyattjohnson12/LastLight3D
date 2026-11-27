"""
tundra.py - FROSTWOOD TUNDRA: the frozen region of the big map (worldgen 2), home of the Frost Wraith.

What's here:
  * Snow ground, snowdrifts, ice chips and frosted grass; snow-laden PINES (every tree in the tundra is one,
    plus groves of new ones) and stands of WHITEWOOD, a pale silver tree whose wood keeps you warm.
  * Blocks of CLEAR ICE (pickaxe) and glowing FROST CRYSTALS (pickaxe) that give Frost Shards - so the
    Frost Cloak and Frost Spear can be made before the Wraith is beaten.
  * Frozen ponds: in WINTER the ice holds and you can walk (and slide) across them; the rest of the year they
    are icy black water nobody can cross.
  * The cold: the tundra drains warmth fast, day and night (player_tick). Fur / Pelt / Frost Cloaks, the
    Snowfox Hood, a Whitewood Warmer in your pack, campfires, braziers and huts are what keep you alive.
    A HUD hint explains it the first time you walk in.
  * The seasons move the snow line: in winter the snow (and its cold) creeps far out into the
    neighbouring regions, in summer the tundra's edges thaw back. Nothing is moved for it (determinism):
    the snow line is a set of ground overlays placed once from the seed, shown / hidden by season, and
    the cold reads the same distance-to-the-tundra map.
  * Wildlife: snow foxes, snow hares and arctic wolves (tundra only), with snow pelts to make warm gear.
  * The Wraith's Hollow at the heart of the tundra (ice ring, frost crystals). The Frost Wraith draws
    strength from the tundra: it heals while it stands in the snow, so drag the fight out of it.
  * Ambient: falling snow everywhere in the tundra (and past the winter snow line), pale fog.

3D: every new object has a shapes3d.SHAPES entry built with shapes3d's builders (registered here at import):
  "pine" (conifer: trunk + four solid tiers, snowy rims and crown), "whitewood" (canopy_tree, pale bark),
  "ice_rock" (boulder + crystal spikes), "frost_crystal" (glowing crystal_cluster). Tundra pines are ordinary
  "tree" nodes with variants 20-22, picked through shapes3d.VARIANTS["tree"]. Creature 3D models are built in
  Blender: tools/blender/models/tundra.py -> assets/models/snow_fox.glb etc. (docs/MODELS.md).

Rules followed (docs/BIOMES.md): generation uses gen.rng only and only ADDS nodes (shared trees are restyled,
never moved); the cold / spawns / boss regen run on the host; the looks run on every computer.
"""
import math
import random

import arcade

import art
import biomes
import shapes3d
from settings import *
from world import Node

NAME = "tundra"
PINE_TREE = 20               # tree variants 20, 21, 22 are pines (see art_tundra.py)

# --- the cold (warmth per second, before clothes; see main._update_survivor)
TUNDRA_COLD = 4.6            # by day: more than the sun gives back, so bare skin slowly freezes
TUNDRA_NIGHT_COLD = 1.8      # extra at full night
SEASON_COLD = {"spring": 0.0, "summer": -1.6, "autumn": 0.4, "winter": 1.2}
WARMER_SOAK = 1.4            # a Whitewood Warmer in your backpack cancels this much tundra cold
SNOWLINE_COLD = 2.2          # past the winter snow line, outside the tundra (scaled by how deep in you are)
SNOW_SPEED = 0.92            # wading through snow
WINTER_SNOW_SPEED = 0.86
ICE_SPEED = 1.12             # sliding over a frozen pond
WRAITH_REGEN = 2.2           # Frost Wraith health per second while it stands in the tundra

# --- the snow line (px from the tundra's border): how far the snow reaches out, and the summer thaw in
SNOW_REACH = {"winter": 820, "autumn": 380, "spring": 230, "summer": 150}
THAW_REACH = {"summer": 430, "spring": 170}
EDGE = 150                   # overlays this close to the border always show (they soften the tile edges)
REACH_MAX = 840

ITEMS.update({
    "whitewood": {"name": "Whitewood", "kind": "material",
                  "desc": "Pale wood from the Frostwood Tundra. Burns slow and warm: Whitewood Warmers and cloaks."},
    "snow_pelt": {"name": "Snow Pelt", "kind": "material",
                  "desc": "Thick white fur from snow foxes and hares. The warmest clothing there is."},
    "clear_ice": {"name": "Clear Ice", "kind": "material",
                  "desc": "Cut from ice blocks in the tundra (pickaxe). Melt it at a campfire for water."},
    "snowfox_hood": {"name": "Snowfox Hood", "kind": "armor", "slot": "head", "armor": 2, "warmth": 4,
                     "desc": "Armor 2, warmth 4. Ears and all."},
    "pelt_cloak": {"name": "Pelt Cloak", "kind": "armor", "slot": "cloak", "armor": 2, "warmth": 10,
                   "desc": "Armor 2, warmth 10. Snow pelts stitched over whitewood toggles - between the Fur and "
                           "the Frost Cloak."},
    "hand_warmer": {"name": "Whitewood Warmer", "kind": "material",
                    "desc": "A smouldering whitewood ember in a leather pouch. Keep one in your backpack: the tundra "
                            "cold (and the winter snow line) bites much less."},
})
NODES.update({
    "whitewood": {"gives": "whitewood", "hp": 5, "regrow": 200},
    "ice_rock": {"gives": "clear_ice", "hp": 4, "regrow": 150, "needs": "pickaxe"},
    "frost_crystal": {"gives": "frost_shard", "hp": 2, "regrow": 420, "needs": "pickaxe"},
})
for _tool, _k in (("axe", 2), ("iron_axe", 3)):
    ITEMS[_tool].setdefault("harvest", {})["whitewood"] = _k
for _tool, _k in (("pickaxe", 2), ("iron_pickaxe", 3)):
    ITEMS[_tool].setdefault("harvest", {})["ice_rock"] = _k
ANIMALS.update({
    "snow_fox": {"hp": 5, "speed": 190, "temper": "flee", "drops": {"meat": 1, "snow_pelt": 2},
                 "tame": "meat", "chance": 0.4, "job": "forager", "dmg": 0, "home": NAME,
                 "desc": "Forager: picks berries & fiber from bushes and hauls them home."},
    "snow_hare": {"hp": 2, "speed": 180, "temper": "flee", "drops": {"meat": 1, "snow_pelt": 1},
                  "tame": "berries", "chance": 0.6, "job": "forager", "dmg": 0, "home": NAME,
                  "desc": "Forager: picks berries & fiber from bushes and hauls them home."},
    "arctic_wolf": {"hp": 16, "speed": 172, "temper": "defend", "drops": {"meat": 2, "fur": 3},
                    "tame": "meat", "chance": 0.22, "job": "guard", "dmg": 8, "home": NAME,
                    "desc": "Guard: fights zombies next to you (or around your base). Tougher than a wolf."},
})

CRAFT_TABS["Armor"].append(R("snowfox_hood", {"snow_pelt": 3, "leather": 1, "fiber": 2}, "workbench"))
CRAFT_TABS["Armor"].append(R("pelt_cloak", {"snow_pelt": 5, "fur": 2, "whitewood": 2}, "workbench"))
CRAFT_TABS["Supplies"].append(R("hand_warmer", {"whitewood": 3, "leather": 1, "coal": 1}, "campfire"))
CRAFT_TABS["Supplies"].append(R("water", {"clear_ice": 1}, "campfire", n=2))
CRAFT_TABS["Build"].append(R("campfire", {"whitewood": 3, "stone": 3}))      # whitewood burns well
RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]   # same list object, crafting indexes in tab order

import art_tundra  # noqa: E402  (after the tables: registers the new art)

# =========================================================================== 3D shapes (shapes3d.SHAPES entries)
S3 = shapes3d
# A snow-laden pine: bark trunk and four solid drooping cone tiers. The picture (art_tundra.pine) is painted in
# zones by distance from the centre, so every tier picks up a white snowy rim, dark needles above it and the
# white crown at the tip; it is opaque everywhere the tiers sample it and Fill()ed anyway: never see-through.
S3.SHAPES["pine"] = S3.conifer(tiers=4, height=3.35, radius=0.95, trunk=0.55, needles=S3.Fill(0.5, 0.2),
                               bark=(92, 64, 44), sway=0.05)
# whitewood: a tall pale trunk and a closed crown of frosted leaf blobs
S3.SHAPES["whitewood"] = S3.canopy_tree(trunk=2.1, crown=(2.35, 0.6), blobs=4, leaves=S3.Fill(0.5, 0.3),
                                        bark=(214, 218, 224), seed=5700, sway=0.08)
# a block of ice with crystal spikes growing out of it
S3.SHAPES["ice_rock"] = S3.Shape(S3.boulder(height=0.75, lump=0.3, sides=6).parts +
                                 S3.crystal_cluster(n=4, height=1.9, color=(176, 222, 246), glow=0.12, seed=5800,
                                                    spread=0.35).parts, foot=(0.85, 0.85), turn=0.3, cut=0.25)
# frost crystal: a glowing cluster of five-sided spikes (plus a light pool sprite on the ground, see below)
S3.SHAPES["frost_crystal"] = S3.crystal_cluster(n=5, height=2.3, color=(150, 226, 255), glow=0.6, seed=21)
# tundra pines are "tree" nodes with variants 20-22: chain the tree picker
_tree_pick = S3.VARIANTS.get("tree", lambda s: "tree")
S3.VARIANTS["tree"] = lambda s: "pine" if PINE_TREE <= s.variant < PINE_TREE + 3 else _tree_pick(s)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


# =========================================================================== the snow line map (pure, cached)
_RADII = (60, 130, 210, 300, 400, 510, 630, 760, REACH_MAX)
_ANGLES = [(math.cos(k * math.tau / 12), math.sin(k * math.tau / 12)) for k in range(12)]


def _edge_dist(layout, x, y):
    """Signed distance to the tundra's border: > 0 outside (how far the tundra is), < 0 inside (how far the
    edge is). None if further than REACH_MAX. A pure function of the layout (same on every computer)."""
    inside = layout.biome_at(x, y) == NAME
    for r in _RADII:
        for cx, cy in _ANGLES:
            if (layout.biome_at(x + cx * r, y + cy * r) == NAME) != inside:
                return -r if inside else r
    return None


def reach(game, pos):
    """_edge_dist on a 100 px grid, cached per world."""
    lay = game.layout
    cache = getattr(game, "_tundra_reach", None)
    if cache is None or cache[0] is not lay:
        cache = game._tundra_reach = (lay, {})
    key = (int(pos[0] // 100), int(pos[1] // 100))
    got = cache[1].get(key, 0)
    if got == 0:
        got = cache[1][key] = _edge_dist(lay, key[0] * 100 + 50, key[1] * 100 + 50)
    return got


def snow_depth(game, pos):
    """How snowy a surface spot is right now (0..1), with the season's snow line: 1 deep in the tundra,
    fading out past the border in winter, thawing in at the edges in summer."""
    d = reach(game, pos)
    season = game.season
    if d is None:
        return 1.0 if game.biome_at(pos) == NAME else 0.0
    if d < 0:
        t = THAW_REACH.get(season)
        return 1.0 if not t else _clamp(0.25 + 0.75 * (-d) / t)
    return _clamp((SNOW_REACH[season] - d) / 300.0)


# =========================================================================== generation (every computer)
def _state(game):
    st = getattr(game, "tundra", None)
    if st is None or st.get("layout") is not game.layout:
        st = game.tundra = {"layout": game.layout, "season": None, "told": False, "line": [], "thaw": [],
                            "ponds": [], "tall": [], "snow_t": 0.0, "regen_told": False}
    return st


def _make_pine(n, v):
    n.variant = v
    n.angle = n.base_angle = 0.0
    if n.state == "full":
        n.texture = art.tree(v)


def gen_surface(gen):
    import base
    base.NODE_RADIUS.update({"whitewood": 40, "ice_rock": 30, "frost_crystal": 20})
    g, r, over, lay = gen.game, gen.rng, gen.over, gen.layout
    st = _state(g)
    k = gen.scale / 3.0          # 1.0 on the 5600 map

    # every tree already standing here becomes a snow-laden pine (same nodes, new look)
    for n in over.trees:
        if n.kind == "tree" and gen.biome_at(n.base) == NAME:
            _make_pine(n, PINE_TREE + n.idx % 3)

    # the Wraith's Hollow: a frost scar, a ring of ice blocks and frost crystals in the middle
    lair = lay.centres[NAME]
    s = arcade.Sprite(art_tundra.lair(), center_x=lair[0], center_y=lair[1])
    over.ground.append(s)
    st["lair"] = lair
    for i in range(9):
        a = i / 9 * math.tau + r.uniform(-0.15, 0.15)
        p = (lair[0] + math.cos(a) * r.uniform(160, 190), lair[1] + math.sin(a) * r.uniform(160, 190))
        if gen.free(p, 28, gap=8):
            gen.add_node(Node("ice_rock", art_tundra.ice_rock(i % 2), *p), over.rocks)
    for i in range(5):
        a = i / 5 * math.tau + 0.3
        p = (lair[0] + math.cos(a) * 80, lair[1] + math.sin(a) * 80)
        if gen.free(p, 18, gap=8):
            gen.add_node(Node("frost_crystal", art_tundra.frost_crystal(), *p), over.rocks)

    def grove(count, spread, kind, rad, lst, make, groves):
        centres = [p for p in (gen.spot(NAME, 250) for _ in range(groves)) if p]
        placed = 0
        for _ in range(count * 6):
            if placed >= count or not centres:
                break
            cx, cy = r.choice(centres)
            p = (cx + r.gauss(0, spread), cy + r.gauss(0, spread))
            if gen.biome_at(p) != NAME or not gen.free(p, rad):
                continue
            placed += 1
            make(gen.add_node(Node(kind, art.tree(PINE_TREE) if kind == "tree" else make.tex(), *p), lst))

    def pine(n):
        _make_pine(n, PINE_TREE + r.randint(0, 2))

    def ww(n):
        st["tall"].append(n)
    ww.tex = art_tundra.whitewood
    grove(int(130 * k), 240, "tree", 44, over.trees, pine, int(12 * k))     # the Frostwood: pine groves
    grove(int(32 * k), 160, "whitewood", 40, over.rocks, ww, int(5 * k))      # whitewood stands

    for kind, count, rad in (("ice_rock", int(34 * k), 30), ("frost_crystal", int(10 * k), 20)):
        placed = 0
        for _ in range(count * 6):
            if placed >= count:
                break
            p = gen.spot(NAME)
            if p and gen.free(p, rad):
                placed += 1
                tex = art_tundra.ice_rock(r.randint(0, 1)) if kind == "ice_rock" else art_tundra.frost_crystal()
                gen.add_node(Node(kind, tex, *p), over.rocks)

    # extra snowdrifts (the shared decor already has some, from the decor hook)
    for _ in range(int(160 * k)):
        p = gen.spot(NAME)
        if p:
            d = arcade.Sprite(art_tundra.decor(r.randint(0, 2)), center_x=p[0], center_y=p[1])
            d.angle = r.choice((0, 0, 180)) + r.uniform(-20, 20)
            d.scale = r.uniform(0.9, 1.5)
            over.decor.append(d)

    # the seasonal snow line: soft snow patches outside the border, thaw patches inside it
    size = gen.size
    step = 190
    for gx in range(step // 2, size, step):
        for gy in range(step // 2, size, step):
            x, y = gx + r.uniform(-50, 50), gy + r.uniform(-50, 50)
            v = r.randint(0, 2)
            ang = r.uniform(0, 360)
            w = biomes.weights_at(lay, x, y, REACH_MAX)
            if NAME not in w or (w.get(NAME, 0) > 0.99 and lay.biome_at(x, y) == NAME and
                                 biomes.weights_at(lay, x, y, 430).get(NAME, 0) > 0.99):
                continue
            d = _edge_dist(lay, x, y)
            if d is None or d < -THAW_REACH["summer"]:
                continue
            tex = art_tundra.snow_patch(v) if d > 0 else art_tundra.thaw_patch(v)
            sp = arcade.Sprite(tex, center_x=x, center_y=y)
            sp.scale = 0.95 if d > 0 else 0.7
            sp.angle = ang
            sp.alpha = 0
            sp.visible = False
            over.ground.append(sp)
            st["line" if d > 0 else "thaw"].append((sp, abs(d)))

    # tundra ponds freeze in winter (texture + whether they block are set by season in visuals())
    for i, s in enumerate(over.ponds):
        if gen.biome_at(s.position) == NAME:
            st["ponds"].append((s, i % 3))


def _ground(rng, x, y):
    return art_tundra.ground(rng.randint(0, 2))


def _decor(rng, x, y):
    roll = rng.random()
    if roll < 0.45:
        return art_tundra.decor(rng.randint(0, 2))      # drifts
    if roll < 0.62:
        return art_tundra.decor(3)                      # ice chips
    if roll < 0.9:
        return art_tundra.decor(4)                      # frosted grass
    return art_tundra.decor(5)                          # tracks


def _respawn(game, n, x, y):
    if n.kind == "tree":
        return PINE_TREE + random.randint(0, 2), 0.0
    return None


# =========================================================================== survivors (host / solo)
def _warmer(p):
    return p.inv.get("hand_warmer", 0) > 0


def player_tick(game, p, dt):
    """Extra cold per second while p stands in the tundra (clothes are taken off afterwards)."""
    season = game.season
    cold = TUNDRA_COLD + TUNDRA_NIGHT_COLD * game.darkness + SEASON_COLD.get(season, 0.0)
    if season in THAW_REACH:             # the thawing edges in summer / spring are milder
        cold *= 0.4 + 0.6 * snow_depth(game, p.pos)
    if _warmer(p):
        cold -= WARMER_SOAK
    return max(0.0, cold)


def _ponds_frozen(game):
    return game.season == "winter"


def _pond_hit(s, pos, k=1.0):
    dx, dy = pos[0] - s.center_x, pos[1] - s.center_y
    return (dx / (92 * k)) ** 2 + (dy / (60 * k)) ** 2 < 1.0


def speed(game, p):
    """Runs on the computer that moves p. Deep snow slows you; frozen ponds are slippery-fast. If the ice
    melted under you, you scramble out to the shore."""
    st = getattr(game, "tundra", None)
    frozen = _ponds_frozen(game)
    if st:
        for s, _ in st["ponds"]:
            if abs(p.pos[0] - s.center_x) > 120 or abs(p.pos[1] - s.center_y) > 90:
                continue
            if _pond_hit(s, p.pos, 1.15):
                if frozen:
                    return ICE_SPEED
                dx, dy = p.pos[0] - s.center_x, p.pos[1] - s.center_y
                a = math.atan2(dy / 60, dx / 92) if (dx or dy) else 0.0
                p.sprite.center_x = s.center_x + math.cos(a) * 92 * 1.45
                p.sprite.center_y = s.center_y + math.sin(a) * 60 * 1.6
                if p is game.me:
                    game.message, game.message_t = "The ice gave way - you scramble out of the freezing water!", 3
                break
    return WINTER_SNOW_SPEED if game.season == "winter" else SNOW_SPEED


def update(game, dt):
    """Host / solo every frame: the winter snow line chills people outside the tundra, and the Frost Wraith
    heals while it stands in the snow."""
    st = getattr(game, "tundra", None)
    if st is None:
        return
    season = game.season
    for p in game.alive_players("over"):
        if game.biome_at(p.pos) == NAME or p.in_hut is not None or game.near_fire(p.pos, "over"):
            continue
        d = reach(game, p.pos)
        if d is None or d <= 0 or d > SNOW_REACH[season]:
            continue
        k = snow_depth(game, p.pos)
        if k <= 0:
            continue
        cold = SNOWLINE_COLD * k * (0.6 + 0.4 * game.darkness) - p.gear("warmth") * WARMTH_PER_GEAR_POINT * 0.5
        if _warmer(p):
            cold -= WARMER_SOAK * k
        if cold > 0:
            p.warmth = max(0.0, p.warmth - cold * dt)
    for b in game.over.bosses:
        if b.kind != "wraith" or b.state == "flee" or b.hp >= b.max_hp or game.biome_at(b.position) != NAME:
            continue
        b.hp = min(b.max_hp, b.hp + WRAITH_REGEN * b.max_hp / b.info["hp"] * dt)
        if random.random() < dt * 3:
            game.burst(b.center_x, b.center_y, (200, 236, 255), 4, 80, 3, 0.7, layer="over")
        if not st["regen_told"]:
            st["regen_told"] = True
            game.say(f"{b.info['name']} draws strength from the tundra - it HEALS in the snow! "
                     "Lure it out of the Frostwood.", 5)


# =========================================================================== looks (every computer)
def _apply_season(game, st, season):
    st["season"] = season
    R = SNOW_REACH[season]
    for sp, d in st["line"]:
        a = 230 if d <= EDGE else (0 if d > R else int(255 * _clamp(0.35 + (R - d) / 260)))
        sp.alpha = a
        sp.visible = a > 0
    T = THAW_REACH.get(season, 0)
    for sp, d in st["thaw"]:
        a = 0 if d > T else int(235 * _clamp(0.3 + (T - d) / 220))
        sp.alpha = a
        sp.visible = a > 0
    frozen = season == "winter"
    solid = game.over.solid
    for s, i in st["ponds"]:
        s.texture = art_tundra.pond(i, frozen)
        if frozen and solid in s.sprite_lists:
            solid.remove(s)                  # the ice holds: walk across
        elif not frozen and solid not in s.sprite_lists:
            solid.append(s)


def _flakes(game, x, y, n, spread=650):
    if not hasattr(game, "_fx_pool"):
        return
    rnd = random.random
    for _ in range(n):
        game.fx_spawn("over", x + (rnd() - 0.5) * 2 * spread, y + (rnd() - 0.35) * 1.6 * spread,
                      140 + rnd() * 200, 10 + rnd() * 14, (rnd() - 0.5) * 8, -38 - rnd() * 22, 5.5 + rnd() * 2,
                      2.2 + rnd() * 1.8, (246, 250, 255), 0.95)


def visuals(game, dt):
    """Every frame on every computer: the season's snow line and frozen ponds, whitewood see-through in the
    tilted view, and snowfall past the winter snow line."""
    st = getattr(game, "tundra", None)
    if st is None or getattr(game, "worldgen", 1) == biomes.LEGACY:
        return
    if st["season"] != game.season:
        _apply_season(game, st, game.season)
    if game.view_layer != "over":
        return
    vx, vy = game.view_pos()
    fp = game.fp_on()
    for n in st["tall"]:
        want = 255
        if not fp and n.state == "full" and 0 < vy - n.center_y < 170 and abs(n.center_x - vx) < 70:
            want = 120
        if n.alpha != want:
            n.alpha = want
    if game.biome_at((vx, vy)) != NAME and game.season == "winter":
        k = snow_depth(game, (vx, vy))
        if k > 0:
            st["snow_t"] -= dt * 30 * k
            while st["snow_t"] < 0:
                st["snow_t"] += 1
                _flakes(game, vx, vy, 1)


def ambient(game, dt, x, y):
    """Every computer, while the viewer stands in the tundra: falling snow and the welcome hint."""
    st = getattr(game, "tundra", None)
    if st is None:
        return
    me = game.me
    if me and me.alive and me.layer == "over" and not st["told"] and game.biome_at(me.pos) == NAME:
        st["told"] = True
        game.message, game.message_t = ("FROSTWOOD TUNDRA: the cold drains your warmth FAST, even by day. Wear a Fur "
                                        "or Pelt Cloak, keep a fire close. Chop pines & Whitewood, mine ice and "
                                        "Frost Crystals. Ponds only freeze in winter.", 8)
    rate = 34 if game.season == "winter" else 24 if game.season != "summer" else 14
    st["snow_t"] -= dt * rate
    while st["snow_t"] < 0:
        st["snow_t"] += 1
        _flakes(game, x, y, 1)


biomes.register(biomes.Biome(
    NAME, title="Frostwood Tundra", order=20,
    tint=(232, 240, 250),
    density={"tree": 0.5, "bush": 0.18, "pond": 0.6, "hive": 0.0, "decor": 0.7},
    node_kinds=("whitewood", "ice_rock", "frost_crystal"),
    animals={"rabbit": 0, "deer": 1, "boar": 0, "wolf": 1, "bee": 0, "snow_fox": 4, "snow_hare": 4, "arctic_wolf": 2},
    fog=(214, 226, 242, 40),
    gen_surface=gen_surface, ground=_ground, decor=_decor, respawn_variant=_respawn,
    player_tick=player_tick, speed=speed, update=update, visuals=visuals, ambient=ambient,
))
