"""
hollows.py - THE CRYSTAL HOLLOWS: a third, deeper underground layer ("deep"), reached from the cave.

What's here (art in art_hollows.py, creature models in tools/blender/models/hollows.py):
  * The way down. Each new world (worldgen 2) has two plugged shafts in the cave: a timber headframe over a
    hole, the hole jammed with crystal-hard rubble. Break the rubble with an IRON pickaxe (or better) and
    the shaft stays open for good; climb down with E. Ladders in the Hollows lead back up.
  * The Hollows: big caverns of blue-violet rock lit by glowing crystal clusters (emissive 3D crystals and
    coloured light pools), stalagmites, drifting bioluminescent motes and a cool haze - pleasant to explore
    after the pitch-dark cave. Still cold, and the dark spawns are tougher than the cave's.
  * Resources: plenty of cave crystal, iron and coal, and rare STARSTONE veins (deep inside, far from the
    ladders). Starstone makes the end-game kit: the Starstone Pickaxe (fastest mining there is), the
    Starstone Helm (armor 6, the best helmet) and the Starforged Blade (upgrades the Ember Blade).
  * Creatures: Shard Crawlers (crystal-backed spiders), Hollow Bats (fast, weak, flying) and Geode Golems
    (huge, slow, hit hard; drop crystal and sometimes starstone).
  * The regular cave gets faint glowing fungus along its walls (every world, old ones too: they're plain
    sprites, not nodes) and a little more ambient light in first person, so it's playable but still spooky.

Determinism / saves (docs/BIOMES.md): generation only uses gen.rng. The deep layer's nodes and the shaft
plugs are added with gen.add_node (worldgen 2 only: old worlds' node lists stay bit-for-bit the same).
Crystal clusters, stalagmites, the headframes and the fungus are `Deco` sprites: drawn like nodes (3D shapes
by kind) but never mined, saved or synced - every computer rebuilds them from the seed. The shaft plugs are
ordinary nodes, so their broken state is saved and sent to co-op clients like any mined rock; their regrow
time is effectively forever. Which layer a survivor is on ("deep" too) is already saved by savegame.py.
"""
import math
import random

import arcade

import art
import art_extra
import art_hollows
import base
import biomes
import fx3d
import shapes3d as S3
from settings import *
from world import Node

NAME = "hollows"
LAYER = "deep"
SHAFTS = 2                       # plugged shafts down from the cave (per worldgen-2 world)
NEVER = 10 ** 9                  # "regrow" time of a broken shaft plug: it stays open
LIGHT = (0.22, 0.25, 0.36)       # the Hollows' ambient light (the cave's is 0.12, 0.11, 0.16)
CAVE_LIGHT = (0.13, 0.12, 0.17)  # the cave: a hair brighter than before, plus the fungus pools
WALL_COL = (74, 78, 108)         # the deep rock's 3D wall sides

# --------------------------------------------------------------------------- items, recipes, nodes, enemies
ITEMS.update({
    "starstone": {"name": "Starstone", "kind": "material",
                  "desc": "A shard of fallen star from deep in the Crystal Hollows. Needs an iron pickaxe. "
                          "The best gear there is is made from it."},
    "starstone_pickaxe": {"name": "Starstone Pickaxe", "kind": "tool", "damage": 4, "reach": 62, "cooldown": 0.3,
                          "harvest": {"rock": 4, "iron": 3, "coal": 3, "crystal": 2, "starstone": 2, "sealed_shaft": 3},
                          "desc": "The fastest pickaxe: 4x stone, 3x ore, double crystal and starstone, quick swings."},
    "starstone_helm": {"name": "Starstone Helm", "kind": "armor", "slot": "head", "armor": 6, "warmth": 2,
                       "desc": "Armor 6, warmth 2: the toughest helmet (but no spore filter like the Mire Mask)."},
    "star_blade": {"name": "Starforged Blade", "kind": "weapon", "damage": 15, "reach": 80, "cooldown": 0.32,
                   "burn": 1, "desc": "Your Ember Blade, reforged with starstone: 15 damage, quick, longer reach, "
                                      "sets enemies on fire. The best blade there is."},
})
NODES.update({
    "starstone": {"gives": "starstone", "hp": 16, "regrow": 420, "needs": "iron_pickaxe",
                  "hard": "Starstone is too hard - you need an IRON pickaxe (or better)."},
    "sealed_shaft": {"gives": "stone", "hp": 14, "regrow": NEVER, "needs": "iron_pickaxe",
                     "hard": "Crystal-hard rubble plugs this shaft. Break it with an IRON pickaxe."},
})
PICK_TIER["starstone_pickaxe"] = 3
base.NODE_RADIUS.update({"starstone": 34, "sealed_shaft": 34})
ZOMBIES.update({
    #                 hp  speed damage attack_every
    "shard_crawler": (9, 150, 10, 0.75),     # the cave crawler is (5, 140, 7, 0.8)
    "hollow_bat": (4, 190, 6, 0.6),
    "geode_golem": (48, 50, 26, 1.5),        # the cave golem is (30, 46, 20, 1.5)
})
CRAFT_TABS["Tools"].append(R("starstone_pickaxe", {"wood": 2, "iron_ingot": 2, "starstone": 3}, "workbench"))
CRAFT_TABS["Tools"].append(R("star_blade", {"ember_blade": 1, "starstone": 4, "crystal": 3}, "workbench"))
CRAFT_TABS["Armor"].append(R("starstone_helm", {"starstone": 3, "iron_ingot": 2, "leather": 1}, "workbench"))
RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]   # same list object, crafting indexes in tab order

fx3d.STONY.update({"shard_crawler", "geode_golem"})
fx3d.GATHER_COL.update({"starstone": (220, 210, 255), "sealed_shaft": (120, 150, 190)})
fx3d.SPARKLE.update({"starstone", "sealed_shaft"})


def _drop_crawler(game, by, z, roll):
    if roll < 0.45:
        game.give(by, "crystal", 1, z.position)
    elif roll < 0.75:
        game.give(by, "coal", 1, z.position)


def _drop_bat(game, by, z, roll):
    if roll < 0.45:
        game.give(by, "meat", 1, z.position)
    elif roll < 0.6:
        game.give(by, "hide", 1, z.position)


def _drop_golem(game, by, z, roll):
    game.give(by, "crystal", 2, z.position)
    game.give(by, "iron_ore", 2)
    if roll < 0.3:
        game.give(by, "starstone", 1)


biomes.ZOMBIE_DROPS.update({"shard_crawler": _drop_crawler, "hollow_bat": _drop_bat, "geode_golem": _drop_golem})


# --------------------------------------------------------------------------- 3D shapes (shapes3d.py guide)
def _spike(at, size, tilt=0.0, roll=0.0, color=(225, 215, 255), glow=0.85, sides=5):
    rings = [(1.0, 0.0, 0.8, 0.8), (0.9, 0.3, 0.75, 0.95), (0.45, 0.72, 0.5, 1.15), (0.0, 1.0, 0.0, 1.3)]
    return S3.Part(rings, at=at, size=size, tilt=tilt, roll=roll, sides=sides, jitter=0.2, color=color, glow=glow)


def _stalagmite():
    rings = [(1.0, 0.0, 0.9, 0.62), (0.72, 0.7, 0.7, 0.8), (0.42, 1.7, 0.45, 0.92), (0.16, 2.6, 0.2, 1.0),
             (0.0, 3.0, 0.0, 1.05)]
    return S3.Shape([S3.Part(rings, sides=7, jitter=0.22),
                     S3.Part(S3.cone(1.0, 1.0), at=(0.55, 0.3, 0.0), size=(0.36, 0.36, 1.25), tilt=0.22, roll=0.12,
                             sides=5, jitter=0.2),
                     S3.Part(S3.cone(1.0, 1.0), at=(-0.4, -0.45, 0.0), size=(0.3, 0.3, 0.8), tilt=-0.18, roll=-0.2,
                             sides=5, jitter=0.2)], foot=(0.9, 0.9), turn=0.4, cut=0.2)


def _starstone():
    rock = S3.boulder(height=0.95, lump=0.22).parts[0]
    parts = [rock, _spike((0.0, 0.0, 0.5), (0.3, 0.3, 1.5)),
             _spike((0.3, 0.2, 0.45), (0.18, 0.18, 0.9), tilt=0.5, roll=0.35),
             _spike((-0.25, 0.25, 0.4), (0.16, 0.16, 0.8), tilt=-0.45, roll=0.4),
             _spike((0.05, -0.32, 0.42), (0.17, 0.17, 0.85), tilt=0.1, roll=-0.55)]
    return S3.Shape(parts, foot=(0.88, 0.86), turn=0.3, cut=0.25)


def _headframe():
    """The shaft: a square timber collar round the hole, two posts, a crossbeam and a rope down the middle."""
    wood, dark, rope = (122, 86, 52), (88, 60, 36), (190, 170, 120)
    BX, BP = S3.BOX, S3.BOXPIC
    collar = S3.Part([(1.0, 0.0, BP, 0.6), (1.0, 0.3, BP, 0.85), (0.7, 0.3, 0.55, 0.95), (0.7, 0.04, 0.55, 0.5)],
                     sides=4)
    parts = [collar]
    for side in (1, -1):
        parts.append(S3.Part(S3.tube(0.08, 0.07, 2.0, caps=True), at=(0.0, side * 0.82, 0.0), color=wood, sides=5))
        parts.append(S3.Part(S3.tube(0.05, 0.05, 0.9, caps=True), at=(0.0, side * 0.82, 0.25), tilt=0.0,
                             roll=side * 0.55, color=dark, sides=4))               # braces
    parts.append(S3.Part(S3.tube(0.08, 0.08, 1.9, caps=True), at=(0.0, -0.95, 1.95), roll=math.pi / 2,
                         color=dark, sides=5))                                     # crossbeam (along +y)
    parts.append(S3.Part(S3.tube(0.22, 0.22, 0.16, caps=True), at=(0.0, -0.08, 1.82), roll=math.pi / 2,
                         color=wood, sides=8))                                     # pulley wheel
    parts.append(S3.Part(S3.tube(0.02, 0.02, 1.6), at=(0.0, 0.0, 0.25), color=rope, sides=3))
    return S3.Shape(parts, foot=(BX * 0.75, BX * 0.75), turn=math.pi / 4, cut=0.1)


S3.SHAPES.update({
    "glow_spire": S3.crystal_cluster(n=6, height=2.4, glow=0.75, seed=61, spread=0.5, sides=6),
    "glow_spire_b": S3.crystal_cluster(n=4, height=3.0, glow=0.75, seed=67, spread=0.42, sides=6),
    "stalagmite": _stalagmite(),
    "glow_fungus": S3.mushroom_cluster(cap=(110, 215, 225), glow=0.55, sides=6),
    "starstone": _starstone(),
    "sealed_shaft": S3.boulder(height=0.85, lump=0.32, sides=8),
    "shaft_frame": _headframe(),
})
S3.VARIANTS["glow_spire"] = lambda s: "glow_spire_b" if s.variant % 2 else "glow_spire"


class Deco(arcade.Sprite):
    """Scenery drawn like a node (a 3D shape picked by .kind) that is NOT a node: never mined, saved or
    synced. It lives in L.rocks (so view3d draws it) with state "deco", which every node loop skips."""

    def __init__(self, kind, tex, x, y, layer, scale=1.0, angle=0.0, variant=0):
        super().__init__(tex, scale=scale, center_x=x, center_y=y)
        self.kind, self.layer, self.base, self.variant = kind, layer, (x, y), variant
        self.state, self.shake, self.hp, self.timer, self.idx = "deco", 0.0, 0, 0.0, -1
        self.base_angle = self.angle = angle
        self.hive = self.tree = None


class Glow(arcade.Sprite):
    """A pool of coloured light on the floor (fx3d reads .light = (r, g, b, strength))."""

    def __init__(self, x, y, r, col, strength):
        super().__init__(art.glow(r, col), center_x=x, center_y=y)
        self.light = (col[0] / 255, col[1] / 255, col[2] / 255, strength)


# --------------------------------------------------------------------------- generation helpers
def _cells(L):
    C = CAVE_CELL
    cell = lambda s: (int(s.center_x // C), int(s.center_y // C))
    return {cell(s) for s in L.ground}


def _centre(c):
    return c[0] * CAVE_CELL + CAVE_CELL / 2, c[1] * CAVE_CELL + CAVE_CELL / 2


def _roomy(open_cells, c, r=1):
    return all((c[0] + dx, c[1] + dy) in open_cells for dx in range(-r, r + 1) for dy in range(-r, r + 1))


def _wall_side(open_cells, c):
    """Direction (dx, dy) towards a neighbouring wall, or None if it has none."""
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (c[0] + dx, c[1] + dy) not in open_cells:
            return dx, dy
    return None


def _cave_fungus(gen):
    """Faint glowing fungus along the cave walls: a few teal light pools so first person isn't pitch black."""
    r, cave = gen.rng, gen.cave
    open_cells = _cells(cave)
    edge = sorted(c for c in open_cells if _wall_side(open_cells, c))
    r.shuffle(edge)
    exits = [e.position for e in cave.exits]
    spots = []
    for c in edge:
        if len(spots) >= 46:
            break
        x, y = _centre(c)
        if any(math.hypot(x - ex, y - ey) < 150 for ex, ey in exits):
            continue
        if any(math.hypot(x - sx, y - sy) < 260 for sx, sy in spots):
            continue
        dx, dy = _wall_side(open_cells, c)
        x, y = x + dx * 18, y + dy * 18                  # tucked against the wall
        spots.append((x, y))
        for k in range(r.randint(1, 3)):
            fx, fy = x + r.uniform(-14, 14), y + r.uniform(-14, 14)
            cave.rocks.append(Deco("glow_fungus", art_hollows.fungus(), fx, fy, "cave", r.uniform(1.3, 2.0),
                                   r.uniform(0, 360)))
        cave.glows.append(Glow(x, y, 56, (90, 220, 200), 0.6))
    gen.game.hollows_fungus = spots


def _carve_deep(gen, arrivals):
    """Cellular-automata caverns like the cave's, roomier, with a great hall in the middle."""
    r = gen.rng
    N = gen.layers[LAYER].size // CAVE_CELL
    wall = [[r.random() < 0.44 or x in (0, N - 1) or y in (0, N - 1) for y in range(N)] for x in range(N)]
    for _ in range(4):
        nw = [[False] * N for _ in range(N)]
        for x in range(N):
            for y in range(N):
                if x in (0, N - 1) or y in (0, N - 1):
                    nw[x][y] = True
                    continue
                c = sum(wall[x + dx][y + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
                nw[x][y] = c >= 5 or (c >= 4 and wall[x][y])
        wall = nw

    def carve(cx, cy, rad):
        for x in range(max(1, int(cx - rad)), min(N - 1, int(cx + rad) + 1)):
            for y in range(max(1, int(cy - rad)), min(N - 1, int(cy + rad) + 1)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= rad * rad:
                    wall[x][y] = False

    mid = N / 2
    halls = [(mid, mid, 5.5)]
    for _ in range(4):
        a, d = r.uniform(0, math.tau), r.uniform(0.18, 0.34) * N
        halls.append((mid + math.cos(a) * d, mid + math.sin(a) * d, r.uniform(2.8, 4.2)))
    for cx, cy, rad in halls:
        carve(cx, cy, rad)
    for cx, cy in arrivals:
        carve(cx, cy, 3.4)
    for cx, cy in list(arrivals) + [(h[0], h[1]) for h in halls[1:]]:    # winding tunnels to the great hall
        x, y = cx, cy
        for _ in range(500):
            dx, dy = mid - x, mid - y
            d = math.hypot(dx, dy)
            if d < 2:
                break
            x += dx / d * 0.7 + r.uniform(-0.6, 0.6)
            y += dy / d * 0.7 + r.uniform(-0.6, 0.6)
            carve(x, y, 1.8)
    start = (int(arrivals[0][0]), int(arrivals[0][1]))
    seen, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < N and 0 <= ny < N and not wall[nx][ny] and (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    for x in range(N):
        for y in range(N):
            if not wall[x][y] and (x, y) not in seen:
                wall[x][y] = True
    return wall, N, halls


def _pick_shafts(gen):
    """Roomy cave cells far from the ladders (and each other) for the shafts down."""
    r, cave = gen.rng, gen.cave
    open_cells = _cells(cave)
    cand = sorted(c for c in open_cells if _roomy(open_cells, c))
    r.shuffle(cand)
    exits = [e.position for e in cave.exits]
    got = []
    for c in cand:
        if len(got) >= SHAFTS:
            break
        p = _centre(c)
        if min((math.hypot(p[0] - ex, p[1] - ey) for ex, ey in exits), default=9999) < 600:
            continue
        if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 900 for q in got):
            continue
        if not gen.free(p, 50, "cave"):
            continue
        got.append(p)
    return got


def gen_layers(gen):
    """Every world: the cave's glowing fungus. Worldgen 2+: the shafts and the whole Crystal Hollows."""
    game = gen.game
    game.hollows_seals, game.hollows_descents, game.hollows_clusters = [], [], []
    _cave_fungus(gen)
    if gen.version == biomes.LEGACY:
        return                       # old saves: their node lists must stay exactly as they were
    r = gen.rng
    D = gen.layers[LAYER]
    D.wall_col = WALL_COL
    shafts = _pick_shafts(gen)
    if not shafts:
        return
    N = D.size // CAVE_CELL
    arrivals = []
    for i in range(len(shafts)):
        a = i / len(shafts) * math.tau + r.uniform(-0.4, 0.4)
        arrivals.append((N / 2 + math.cos(a) * N * 0.33, N / 2 + math.sin(a) * N * 0.33))
    wall, N, halls = _carve_deep(gen, arrivals)
    C = CAVE_CELL
    open_cells = set()
    for x in range(N):
        for y in range(N):
            px, py = x * C + C / 2, y * C + C / 2
            if not wall[x][y]:
                D.ground.append(arcade.Sprite(art_hollows.floor(r.randint(0, 2)), center_x=px, center_y=py))
                open_cells.add((x, y))
            elif any(0 <= x + dx < N and 0 <= y + dy < N and not wall[x + dx][y + dy]
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                w = arcade.Sprite(art_hollows.wall(r.randint(0, 2)), center_x=px, center_y=py)
                D.walls.append(w)
                D.solid.append(w)

    # ---- the shafts: plug + headframe + hole in the cave, a ladder in the Hollows, a portal between them
    for (sx, sy), (ax, ay) in zip(shafts, arrivals):
        dp = _centre((int(ax), int(ay)))
        cave = gen.cave
        cave.decor.append(arcade.Sprite(art_hollows.hole(), center_x=sx, center_y=sy))
        cave.rocks.append(Deco("shaft_frame", art_hollows.rim(), sx, sy, "cave", 1.0, r.choice((0, 90))))
        cave.exits.append(arcade.Sprite(art_hollows.shaft_exit(), center_x=sx, center_y=sy))
        cave.glows.append(Glow(sx, sy, 70, (110, 180, 255), 0.6))     # cold crystal light rising from below
        seal = gen.add_node(Node("sealed_shaft", art_hollows.seal(), sx, sy, layer="cave"), cave.rocks, layer="cave")
        seal.timer = NEVER
        D.exits.append(arcade.Sprite(art_extra.ladder(), center_x=dp[0], center_y=dp[1]))
        game.add_portal("cave", (sx, sy), LAYER, dp)
        game.hollows_seals.append(seal)
        game.hollows_descents.append(((sx, sy), dp))
    ladders = [dp for _, dp in game.hollows_descents]

    # ---- ores (real nodes): roomy cells, starstone deep inside
    roomy = sorted(c for c in open_cells if _roomy(open_cells, c))
    r.shuffle(roomy)
    used = set()

    def take(c):
        if c in used or any((c[0] + dx, c[1] + dy) in used for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            return False
        used.add(c)
        return True

    for kind, count, near in (("starstone", 8, 750), ("crystal", 22, 300), ("iron", 14, 200), ("coal", 10, 200)):
        placed = 0
        for c in roomy:
            if placed >= count:
                break
            p = (_centre(c)[0] + r.uniform(-8, 8), _centre(c)[1] + r.uniform(-8, 8))
            if min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in ladders) < near or not take(c):
                continue
            tex = art_hollows.starstone() if kind == "starstone" else art_extra.ore(kind)
            gen.add_node(Node(kind, tex, *p, layer=LAYER), D.rocks, layer=LAYER)
            placed += 1

    # ---- glowing crystal clusters (scenery + the Hollows' light)
    clusters = []
    for c in roomy:
        if len(clusters) >= 46:
            break
        p = (_centre(c)[0] + r.uniform(-12, 12), _centre(c)[1] + r.uniform(-12, 12))
        if min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in ladders) < 140:
            continue
        if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 200 for q, _ in clusters) or not take(c):
            continue
        pal = r.randrange(len(art_hollows.PALETTES))
        clusters.append((p, pal))
    gx, gy = _centre((int(N / 2), int(N / 2)))          # the great hall's heart crystal
    if (int(N / 2), int(N / 2)) in open_cells:
        clusters.append(((gx, gy), 1))
    for i, (p, pal) in enumerate(clusters):
        big = i == len(clusters) - 1 and p == (gx, gy)
        scale = 2.6 if big else r.uniform(1.1, 1.9)
        s = Deco("glow_spire", art_hollows.spire(pal), p[0], p[1], LAYER, scale, r.uniform(0, 360), r.randint(0, 1))
        D.rocks.append(s)
        D.solid.append(s)
        col = art_hollows.PALETTES[pal][1]
        D.glows.append(Glow(p[0], p[1], int(70 + 30 * scale), col, 0.75))
        game.hollows_clusters.append((p[0], p[1], col))

    # ---- stalagmites against the walls, a few out in the open
    edge = sorted(c for c in open_cells if _wall_side(open_cells, c) and c not in used)
    r.shuffle(edge)
    placed = 0
    for c in edge:
        if placed >= 70:
            break
        p = _centre(c)
        if min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in ladders) < 120:
            continue
        dx, dy = _wall_side(open_cells, c)
        sc = r.uniform(0.8, 1.5)
        s = Deco("stalagmite", art_hollows.stalagmite(r.randint(0, 2)), p[0] + dx * 14, p[1] + dy * 14, LAYER, sc,
                 r.uniform(0, 360))
        D.rocks.append(s)
        if sc > 1.1:
            D.solid.append(s)
        placed += 1


# --------------------------------------------------------------------------- runtime
def _lock(game, layer, pos):
    """The shaft can't be climbed while its plug is still there."""
    if layer != "cave":
        return None
    for seal in getattr(game, "hollows_seals", ()):
        if seal.state == "full" and math.hypot(seal.base[0] - pos[0], seal.base[1] - pos[1]) < 5:
            return "Crystal-hard rubble plugs this shaft. Break it with an IRON pickaxe to climb down."
    return None


biomes.PORTAL_LOCKS.append(_lock)


def _update(game, dt):
    """Host / solo: announce a shaft breaking open; give the big Hollows creatures their size."""
    for seal in getattr(game, "hollows_seals", ()):
        was = seal.__dict__.get("_open_seen")
        now = seal.state != "full"
        if was is None:
            seal._open_seen = now
        elif now and not was:
            seal._open_seen = True
            x, y = seal.base
            game.burst(x, y, (150, 210, 255), 30, 220, 4, 0.9, layer="cave")
            game.ring(x, y, 20, 160, 0.6, (150, 210, 255), layer="cave")
            game.shake(4, 0.3, "cave")
            for p in game.players.values():
                if p.layer == "cave":
                    game.say("The shaft is open! Cold crystal light rises from below - "
                             "climb down into THE CRYSTAL HOLLOWS.", 5, to=p)
        elif not now:
            seal._open_seen = False
    D = game.layers.get(LAYER)
    if D is not None:
        for z in D.zombies:
            want = 30 if z.kind == "geode_golem" else 14 if z.kind == "hollow_bat" else None
            if want and z.radius != want:
                z.radius = want


MOTES = [(120, 220, 255), (190, 150, 255), (120, 255, 210), (255, 160, 230)]


def _deep_ambient(game, dt, x, y):
    """Every computer: drifting bioluminescent motes, and sparkles around the crystal clusters."""
    if not getattr(game, "_fx_pool", None):
        return
    rnd = random.random
    for _ in range(int(dt * 16 + rnd())):
        a, d = rnd() * math.tau, 40 + rnd() * 620
        game.fx_spawn(LAYER, x + math.cos(a) * d, y + math.sin(a) * d, 8 + rnd() * 100, (rnd() - 0.5) * 16,
                      (rnd() - 0.5) * 16, 3 + rnd() * 7, 3.5 + rnd() * 3, 1.0 + rnd() * 1.4, random.choice(MOTES),
                      0.85, -1.5, 0.2, 0, True)
    near = [c for c in getattr(game, "hollows_clusters", ()) if abs(c[0] - x) < 760 and abs(c[1] - y) < 680]
    for cx, cy, col in near:
        if rnd() < dt * 2.5:
            game.fx_spawn(LAYER, cx + (rnd() - 0.5) * 50, cy + (rnd() - 0.5) * 50, 20 + rnd() * 70, 0, 0,
                          6 + rnd() * 10, 1.2 + rnd(), 1.6 + rnd(), col, 1.0, 0, 0.5, 0, True)


def _cave_ambient(game, dt, x, y):
    """Every computer: now and then a glowing spore drifts up from the cave fungus."""
    if not getattr(game, "_fx_pool", None):
        return
    rnd = random.random
    for fx, fy in getattr(game, "hollows_fungus", ()):
        if abs(fx - x) < 700 and abs(fy - y) < 640 and rnd() < dt * 1.2:
            game.fx_spawn("cave", fx + (rnd() - 0.5) * 30, fy + (rnd() - 0.5) * 30, 6, (rnd() - 0.5) * 6,
                          (rnd() - 0.5) * 6, 10 + rnd() * 8, 3 + rnd() * 2, 1.2, (120, 240, 210), 0.8, -1, 0.3, 0, True)


def _deep_zombie(game, roll):
    if roll < 0.34:
        return "hollow_bat"
    if roll < 0.34 + min(0.3, 0.12 + 0.015 * game.day):
        return "geode_golem"
    return "shard_crawler"


biomes.register_layer(biomes.LayerInfo(
    LAYER, CAVE_SIZE, depth=2, title="into the Crystal Hollows",
    enter="THE CRYSTAL HOLLOWS. Glowing crystal everywhere - and things that hunt by its light. Look for starstone.",
    leave="Back up to the cave.",
    cold=1.1, dark=0.9, light=LIGHT, sky=(12, 16, 32), fog=(70, 110, 170, 26),
    zombie=_deep_zombie, ambient=_deep_ambient,
))
_cave = biomes.LAYER_INFO["cave"]
_cave.light, _cave.ambient = CAVE_LIGHT, _cave_ambient

# legacy=True so OLD worlds get the cave fungus too; on worldgen 1 gen_layers adds no nodes (see above)
biomes.register(biomes.Biome(NAME, title="The Crystal Hollows", order=60, region=False, legacy=True,
                             gen_layers=gen_layers, update=_update))
