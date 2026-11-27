"""
world.py - the things that live in the world, and the code that builds the world.

The layers are "over" (the surface), "cave" (underground) and any registered by plug-ins (biomes.register_layer
appends to LAYERS, e.g. "deep"). Every layer has its own
sprite lists, so zombies, walls and rocks in the cave never touch the surface and vice versa.
The world is generated from a seed, so every co-op player builds the exact same map. Worldgen 1 (old saves)
is the original 3200 map; worldgen 2 is the big six-biome map. See docs/BIOMES.md.
"""
import math
import random

import arcade

import art
import art_bees
import art_extra
from settings import *

LAYERS = ["over", "cave"]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# =========================================================================== sprites
class Node(arcade.Sprite):
    """A harvestable resource: tree, rock, bush or ore."""

    def __init__(self, kind, texture, x, y, layer="over"):
        super().__init__(texture, center_x=x, center_y=y)
        self.kind = kind
        self.layer = layer
        self.base = (x, y)
        self.hp = NODES[kind]["hp"]
        self.state = "full"     # full | stump | empty | gone
        self.timer = 0.0
        self.shake = 0.0
        self.variant = 0
        self.base_angle = 0.0
        self.idx = 0
        self.hive = None        # trees: the beehive hanging in it (if any)
        self.tree = None        # beehives: the tree they hang in


class Structure(arcade.Sprite):
    def __init__(self, kind, x, y, sid=0, layer="over"):
        super().__init__(art.icon(kind), center_x=x, center_y=y)
        self.kind = kind
        self.sid = sid
        self.layer = layer
        self.hp = self.max_hp = ITEMS[kind]["hp"]
        self.extras = []        # flame / glow sprites that belong to a fire
        self.flash = 0.0
        self.lit = True         # fires can be put out by the Frost Wraith
        self.out_t = 0.0


class Shot:
    """Something a survivor fired or threw: an arrow, or a fire pot arcing through the air.
    It flies in a straight line along the ground (vx, vy) for T seconds; t counts up to T."""

    def __init__(self, kind, x, y, vx, vy, T, dmg=0.0, owner=-1, layer="over"):
        self.kind, self.x, self.y, self.vx, self.vy = kind, x, y, vx, vy
        self.t, self.T = 0.0, T
        self.dmg, self.owner, self.layer = dmg, owner, layer
        self.done = False

    @property
    def height(self):
        """How high above the ground it is: arrows fly flat, pots go up and come down."""
        if self.kind == "arrow":
            return 26.0
        k = min(1.0, self.t / self.T)
        return 22.0 + 150.0 * 4 * k * (1 - k)


class Zombie(arcade.Sprite):
    """Every hostile non-boss: zombies, broodlings, cave crawlers and golems."""

    def __init__(self, kind, x, y, zid=0, layer="over"):
        tex = art.zombie(kind) if kind in ("walker", "runner", "brute") else art_extra.enemy(kind)
        super().__init__(tex, center_x=x, center_y=y)
        self.kind = kind
        self.zid = zid
        self.layer = layer
        hp, speed, dmg, every = ZOMBIES[kind]
        self.hp = self.max_hp = hp
        self.speed = speed * random.uniform(0.9, 1.1)
        self.damage, self.attack_every = dmg, every
        self.attack_cd = 0.0
        self.flash = 0.0
        self.trap_cd = 0.0
        self.snared = 0.0        # held by a bear trap
        self.wobble = random.uniform(0, 10)
        self.radius = {"brute": 26, "golem": 28, "broodling": 12}.get(kind, 18)
        self.detour = 0.0
        self.detour_dir = (0.0, 0.0)
        self.eye = None
        self.heading = 0.0
        self.burn = 0.0          # ember blade
        self.chill = 0.0         # frost spear
        self.target = (x, y)     # client side: where the host says it is


class Animal(arcade.Sprite):
    def __init__(self, kind, x, y, aid=0):
        super().__init__(art_extra.animal(kind), center_x=x, center_y=y)
        self.kind = kind
        self.aid = aid
        self.info = ANIMALS[kind]
        self.hp = self.max_hp = self.info["hp"]
        self.owner = -1          # player id when tamed
        self.mode = "follow"     # pets: follow | work | stay
        self.heading = random.uniform(0, math.tau)
        self.wander_t = 0.0
        self.aggro = None        # player it's angry at
        self.aggro_t = 0.0
        self.attack_cd = 0.0
        self.flash = 0.0
        self.carry = {}          # what a working pet is hauling home
        self.job_t = 0.0
        self.goal = None
        self.detour = 0.0
        self.detour_dir = (0.0, 0.0)
        self.moving = False
        self.target = (x, y)
        self.layer = "over"
        self.hive = None         # wild bees: the beehive they buzz around
        self.name = ""           # pets: what their tamer called them
        self.armor = None        # pets: pet armor item they're wearing

    @property
    def pet(self):
        return self.owner >= 0

    @property
    def carrying(self):
        return sum(self.carry.values())


class Boss(arcade.Sprite):
    def __init__(self, kind, x, y, bid=0, cycle=0):
        super().__init__(art_extra.boss(kind), center_x=x, center_y=y)
        self.kind = kind
        self.bid = bid
        self.info = BOSSES[kind]
        self.hp = self.max_hp = self.info["hp"] * (1 + 0.6 * cycle)
        self.speed = self.info["speed"]
        self.damage = self.info["damage"] * (1 + 0.25 * cycle)
        self.radius = self.info["radius"]
        self.heading = 0.0
        self.flash = 0.0
        self.attack_cd = 1.0
        self.timers = {"a": 4.0, "b": 2.5, "c": 6.0, "trail": 0.0}
        self.state = "walk"      # walk | windup | charge | blink
        self.snared = 0.0        # held by a bear trap
        self.state_t = 0.0
        self.charge_dir = (0.0, 0.0)
        self.wobble = 0.0
        self.layer = "over"
        self.target = (x, y)


class Hazard:
    """Boss attacks the players can see coming: telegraph first (tele), then it hits."""

    def __init__(self, kind, x, y, r, tele=0.0, life=0.0, dmg=0.0, vx=0.0, vy=0.0, a=0.0, ln=0.0, owner=None):
        self.kind, self.x, self.y, self.r = kind, x, y, r
        self.tele, self.t, self.dmg = tele, life, dmg
        self.vx, self.vy, self.a, self.ln = vx, vy, a, ln
        self.owner = owner
        self.tick = 0.0
        self.done = False
        self.layer = "over"


class Layer:
    """All the sprite lists for one level of the world."""

    def __init__(self, name, size):
        self.name, self.size = name, size
        sh = dict(use_spatial_hash=True)
        self.ground = arcade.SpriteList(**sh)
        self.decor = arcade.SpriteList(**sh)
        self.walls = arcade.SpriteList(**sh)      # cave walls (drawn on top)
        self.ponds = arcade.SpriteList(**sh)
        self.exits = arcade.SpriteList(**sh)      # cave entrances / ladders
        self.traps = arcade.SpriteList(**sh)
        self.bushes = arcade.SpriteList(**sh)
        self.rocks = arcade.SpriteList(**sh)      # rocks and ores
        self.trees = arcade.SpriteList(**sh)
        self.builds = arcade.SpriteList(**sh)     # walls, fires, benches, bins...
        self.huts = arcade.SpriteList(**sh)
        self.solid = arcade.SpriteList(**sh)      # blocks players, zombies and animals
        self.flames = arcade.SpriteList()
        self.glows = arcade.SpriteList()
        self.zombies = arcade.SpriteList()
        self.eyes = arcade.SpriteList()
        self.animals = arcade.SpriteList()
        self.bosses = arcade.SpriteList()
        self.spawn_timer = 3.0

    def node_lists(self):
        return (self.trees, self.rocks, self.bushes)


# =========================================================================== generation
def build_world(seed, worldgen=1, layout=None):
    """Returns (layers, nodes, links). links = [(surface_pos, cave_pos), ...] for the cave entrances.
    worldgen 1 = the original map (old saves); 2+ = the big biome map (needs the biomes.Layout).
    Extra registered layers (biomes.register_layer) are created empty here; their module fills them.
    The Mire and every plug-in's content are added afterwards by main.setup() (swamp.py, biomes.generate)."""
    import biomes
    if int(worldgen) == biomes.LEGACY:
        layers, nodes, links = _build_legacy(seed)
    else:
        layers, nodes, links = _build_v2(seed, layout or biomes.make_layout(seed, worldgen))
    for name in LAYERS:
        if name not in layers:
            info = biomes.LAYER_INFO.get(name)
            layers[name] = Layer(name, info.size if info else CAVE_SIZE)
    return layers, nodes, links


def _build_v2(seed, layout):
    """Worldgen 2: the big map. The shared content (grass, tufts, ponds, cave entrances, trees, rocks, bushes,
    iron, beehives) spreads over every biome, thinned by each biome's `density`. Every item draws from its own
    random stream, so one biome's settings only change things near that biome. FROZEN once released:
    changing anything here needs a new worldgen version (keep this one for its saves)."""
    import biomes
    size = layout.size
    k = biomes.area_scale(2)
    over = Layer("over", size)
    cave = Layer("cave", CAVE_SIZE)
    nodes = []
    here = lambda p: biomes.get(layout.biome_at(p[0], p[1]))

    # ground tiles: the biome's own texture (or grass), tinted with the biomes around it
    gs = biomes.seed_int(seed, "ground")
    grounds = {}
    for gx in range(0, size + 256, 256):
        for gy in range(0, size + 256, 256):
            b = here((gx, gy))
            tex = None
            if b.ground is not None:
                rr = grounds.setdefault(b.name, random.Random(f"{seed}:{b.name}:ground"))
                tex = b.ground(rr, gx, gy)
            if tex is None:
                tex = art.grass(int(biomes._h(gs, gx, gy) * 2.999))
            s = arcade.Sprite(tex, center_x=gx, center_y=gy)
            s.color = biomes.blend_tint(layout, gx, gy, 200)
            over.ground.append(s)
    rd = random.Random(f"{seed}:decor")
    decors = {}
    for _ in range(int(900 * k)):
        p = (rd.uniform(0, size), rd.uniform(0, size))
        roll, tuft, v = rd.random(), rd.random() < 0.8, rd.randint(0, 3)
        b = here(p)
        if roll >= b.dens("decor"):
            continue
        t = None
        if b.decor is not None:
            t = b.decor(decors.setdefault(b.name, random.Random(f"{seed}:{b.name}:decor")), p[0], p[1])
            if t is False:
                continue
        if t is None:
            t = art.tuft(v) if tuft else art.pebbles(v % 3)
        over.decor.append(arcade.Sprite(t, center_x=p[0], center_y=p[1]))

    centre = layout.centre
    taken = {}           # 256px grid cell -> [(pos, radius)] (radii are at most 120, so neighbours suffice)

    def take(p, radius):
        taken.setdefault((int(p[0] // 256), int(p[1] // 256)), []).append((p, radius))

    def clear_of(p, radius):
        cx, cy = int(p[0] // 256), int(p[1] // 256)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for q, qr in taken.get((gx, gy), ()):
                    if dist(p, q) <= radius + qr:
                        return False
        return True

    def spot(ri, kind, radius, clear=170):
        for i in range(60):
            p = (ri.uniform(80, size - 80), ri.uniform(80, size - 80))
            if ri.random() >= here(p).dens(kind):
                return None                        # this biome doesn't want one: skip it
            if dist(p, centre) < clear + radius or biomes.keepout(layout, p[0], p[1]):
                continue
            if clear_of(p, radius):
                take(p, radius)
                return p
        return None

    def item_rng(kind, i):
        return random.Random(f"{seed}:world:{kind}:{i}")

    for i in range(int(POND_COUNT * k)):
        ri = item_rng("pond", i)
        if i == 0:   # one pond is always a short walk from spawn
            a = ri.uniform(0, math.tau)
            p = (centre[0] + math.cos(a) * 360, centre[1] + math.sin(a) * 300)
            take(p, 120)
        else:
            p = spot(ri, "pond", 120, 380)
        if p:
            s = arcade.Sprite(art.pond(i % 3), center_x=p[0], center_y=p[1])
            over.ponds.append(s)
            over.solid.append(s)

    surface_links = []
    for i in range(CAVE_ENTRANCES_V2):
        p = spot(item_rng("cave", i), "cave", 80, 650)
        if p:
            surface_links.append(p)
            over.exits.append(arcade.Sprite(art_extra.cave_entrance(), center_x=p[0], center_y=p[1]))

    def add_node(layer, n, lst):
        n.idx = len(nodes)
        nodes.append(n)
        lst.append(n)
        layer.solid.append(n)

    for kind, count, rad in (("tree", TREE_COUNT, 46), ("rock", ROCK_COUNT, 34), ("bush", BUSH_COUNT, 28),
                             ("iron", IRON_COUNT, 34)):
        for i in range(int(count * k)):
            ri = item_rng(kind, i)
            p = spot(ri, kind, rad, 170 if kind != "iron" else 500)
            if not p:
                continue
            if kind == "tree":
                v = ri.randint(0, 2)
                n = Node("tree", art.tree(v), *p)
                n.variant = v
                n.angle = n.base_angle = ri.uniform(0, 360)
                add_node(over, n, over.trees)
            elif kind == "rock":
                v = ri.randint(0, 3)
                n = Node("rock", art.rock(v), *p)
                n.variant = v
                add_node(over, n, over.rocks)
            elif kind == "iron":
                add_node(over, Node("iron", art_extra.ore("iron"), *p), over.rocks)
            else:
                add_node(over, Node("bush", art.bush(True), *p), over.bushes)

    hr = random.Random(f"{seed}:hives")
    trees = [t for t in over.trees if t.kind == "tree" and here(t.position).dens("hive") > 0]
    for t in hr.sample(trees, min(int(HIVE_COUNT * k * 0.8), len(trees))):
        a = hr.uniform(0, math.tau)
        h = Node("hive", art_bees.hive(True), t.center_x + math.cos(a) * 24, t.center_y + math.sin(a) * 24)
        h.tree, t.hive = t, h
        h.idx = len(nodes)
        nodes.append(h)
        over.trees.append(h)

    links = _build_cave(random.Random(f"{seed}:cave"), cave, surface_links, add_node)
    for n in nodes:
        n.layer = "over" if n.layer != "cave" else "cave"
    return {"over": over, "cave": cave}, nodes, links


def _build_legacy(seed):
    """Worldgen 1 (saves without a "worldgen" field): the original 3200 map. NEVER change this function -
    old saves are rebuilt from it and their node numbers must line up exactly.
    Returns (layers, nodes, links). links = [(surface_pos, cave_pos), ...] for the cave entrances."""
    r = random.Random(seed)
    over = Layer("over", WORLD_SIZE)
    cave = Layer("cave", CAVE_SIZE)
    nodes = []

    for gx in range(0, WORLD_SIZE + 256, 256):
        for gy in range(0, WORLD_SIZE + 256, 256):
            over.ground.append(arcade.Sprite(art.grass(r.randint(0, 2)), center_x=gx, center_y=gy))
    for _ in range(900):
        t = art.tuft(r.randint(0, 3)) if r.random() < 0.8 else art.pebbles(r.randint(0, 2))
        over.decor.append(arcade.Sprite(t, center_x=r.uniform(0, WORLD_SIZE), center_y=r.uniform(0, WORLD_SIZE)))

    centre = (WORLD_SIZE / 2, WORLD_SIZE / 2)
    taken = []

    def spot(radius, clear=170):
        for _ in range(60):
            p = (r.uniform(80, WORLD_SIZE - 80), r.uniform(80, WORLD_SIZE - 80))
            if dist(p, centre) < clear + radius:
                continue
            if all(dist(p, q) > radius + qr for q, qr in taken):
                taken.append((p, radius))
                return p
        return None

    for i in range(POND_COUNT):
        if i == 0:   # one pond is always a short walk from spawn
            a = r.uniform(0, math.tau)
            p = (centre[0] + math.cos(a) * 360, centre[1] + math.sin(a) * 300)
            taken.append((p, 120))
        else:
            p = spot(120, 380)
        if p:
            s = arcade.Sprite(art.pond(i % 3), center_x=p[0], center_y=p[1])
            over.ponds.append(s)
            over.solid.append(s)

    # cave entrances: far enough from spawn that finding one is an adventure
    surface_links = []
    for i in range(CAVE_ENTRANCES):
        p = spot(80, 650)
        if p:
            surface_links.append(p)
            over.exits.append(arcade.Sprite(art_extra.cave_entrance(), center_x=p[0], center_y=p[1]))

    def add_node(layer, n, lst):
        n.idx = len(nodes)
        nodes.append(n)
        lst.append(n)
        layer.solid.append(n)

    for kind, count, rad in (("tree", TREE_COUNT, 46), ("rock", ROCK_COUNT, 34), ("bush", BUSH_COUNT, 28),
                             ("iron", IRON_COUNT, 34)):
        for _ in range(count):
            p = spot(rad, 170 if kind != "iron" else 500)
            if not p:
                continue
            if kind == "tree":
                v = r.randint(0, 2)
                n = Node("tree", art.tree(v), *p)
                n.variant = v
                n.angle = n.base_angle = r.uniform(0, 360)
                add_node(over, n, over.trees)
            elif kind == "rock":
                v = r.randint(0, 3)
                n = Node("rock", art.rock(v), *p)
                n.variant = v
                add_node(over, n, over.rocks)
            elif kind == "iron":
                n = Node("iron", art_extra.ore("iron"), *p)
                add_node(over, n, over.rocks)
            else:
                add_node(over, Node("bush", art.bush(True), *p), over.bushes)

    # beehives hang in some of the trees. They share the trees list so they draw on top of the
    # leaves, but they don't block anything. Own random stream so the rest of the map is unchanged.
    hr = random.Random(seed * 7 + 3)
    trees = [t for t in over.trees if t.kind == "tree"]
    for t in hr.sample(trees, min(HIVE_COUNT, len(trees))):
        a = hr.uniform(0, math.tau)
        h = Node("hive", art_bees.hive(True), t.center_x + math.cos(a) * 24, t.center_y + math.sin(a) * 24)
        h.tree, t.hive = t, h
        h.idx = len(nodes)
        nodes.append(h)
        over.trees.append(h)

    # ---------------------------------------------------------------- the cave
    links = _build_cave(r, cave, surface_links, add_node)
    for n in nodes:
        n.layer = "over" if n.layer != "cave" else "cave"
    return {"over": over, "cave": cave}, nodes, links


def _build_cave(r, cave, surface_links, add_node):
    """The cave (same for every worldgen so far). Uses the caller's random stream `r`. Returns the links."""
    N = CAVE_SIZE // CAVE_CELL
    wall = [[r.random() < 0.46 or x in (0, N - 1) or y in (0, N - 1) for y in range(N)] for x in range(N)]
    for _ in range(4):   # cellular automata smoothing -> natural looking caverns
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
    cave_links = []
    for i in range(len(surface_links)):
        a = i / max(1, len(surface_links)) * math.tau + r.uniform(-0.3, 0.3)
        cx, cy = mid + math.cos(a) * N * 0.32, mid + math.sin(a) * N * 0.32
        cave_links.append((cx, cy))
        carve(cx, cy, 3.2)
    carve(mid, mid, 4.5)
    for cx, cy in cave_links:   # winding tunnels from each ladder to the central cavern
        x, y = cx, cy
        for _ in range(400):
            dx, dy = mid - x, mid - y
            d = math.hypot(dx, dy)
            if d < 2:
                break
            x += dx / d * 0.7 + r.uniform(-0.6, 0.6)
            y += dy / d * 0.7 + r.uniform(-0.6, 0.6)
            carve(x, y, 1.6)
    # drop pockets you could never reach
    start = (int(cave_links[0][0]), int(cave_links[0][1])) if cave_links else (int(mid), int(mid))
    seen = {start}
    stack = [start]
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

    C = CAVE_CELL
    open_cells = []
    for x in range(N):
        for y in range(N):
            px, py = x * C + C / 2, y * C + C / 2
            if not wall[x][y]:
                cave.ground.append(arcade.Sprite(art_extra.cave_floor(r.randint(0, 2)), center_x=px, center_y=py))
                open_cells.append((x, y))
            elif any(0 <= x + dx < N and 0 <= y + dy < N and not wall[x + dx][y + dy]
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                w = arcade.Sprite(art_extra.cave_wall(r.randint(0, 2)), center_x=px, center_y=py)
                cave.walls.append(w)
                cave.solid.append(w)
    links = []
    for (sx, sy), (cx, cy) in zip(surface_links, cave_links):
        cp = (int(cx) * C + C / 2, int(cy) * C + C / 2)
        links.append(((sx, sy), cp))
        cave.exits.append(arcade.Sprite(art_extra.ladder(), center_x=cp[0], center_y=cp[1]))

    # ores in roomy spots; crystal hides deep (far from the ladders)
    roomy = [c for c in open_cells if all(not wall[c[0] + dx][c[1] + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
    r.shuffle(roomy)
    used = set()
    ladders = [cp for _, cp in links]
    for kind, count in (("crystal", CAVE_CRYSTAL), ("iron", CAVE_IRON), ("coal", CAVE_COAL), ("cave_rock", CAVE_ROCKS)):
        placed = 0
        for cx, cy in roomy:
            if placed >= count:
                break
            if (cx, cy) in used or any((cx + dx, cy + dy) in used for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                continue
            p = (cx * C + C / 2 + r.uniform(-8, 8), cy * C + C / 2 + r.uniform(-8, 8))
            near = min((dist(p, q) for q in ladders), default=9999)
            if near < 160 or (kind == "crystal" and near < 650):
                continue
            used.add((cx, cy))
            node_kind = "rock" if kind == "cave_rock" else kind
            n = Node(node_kind, art_extra.ore(kind), *p, layer="cave")
            add_node(cave, n, cave.rocks)
            placed += 1
    return links
