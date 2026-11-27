"""
biomes.py - the region layout of the surface, the biome registry, and every plug-in hook that biome /
terrain / layer modules use. Read docs/BIOMES.md first.

The big rules (details in docs/BIOMES.md):
  * Worlds are generated from a seed on EVERY computer (solo, co-op host, co-op clients), and saves only
    store the seed + what changed. So generation must be deterministic: never use the global `random`
    module (or time, dict order of sets, id()...) while generating. Every module gets its own stream:
    gen.rng == random.Random(f"{seed}:{module name}").
  * Nodes are numbered by their place in game.nodes. Every module's nodes are recorded as a "span"
    (game.node_spans) and saved, so a save made before a module changed still lines up for the others.
  * Worldgen versions: 1 = the original 3200 x 3200 map (forest + the Mire). Saves without a "worldgen"
    field are version 1 and are rebuilt with the exact legacy code. 2 = the big map with six biomes.

Usage from a plug-in module (see tundra.py for a template):

    import biomes
    biomes.register(biomes.Biome("tundra", title="Frostwood Tundra", tint=(...), gen_surface=_gen, ...))
"""
import importlib
import math
import random
import zlib

from settings import *

# =========================================================================== world-gen versions
LEGACY = 1                   # the original map: 3200 x 3200, forest + Mire (saves without "worldgen")
CURRENT = 2                  # new worlds: the big six-biome map
WORLDGEN = CURRENT           # what a brand new game uses
WORLD_SIZES = {1: 3200, 2: 5600}
LEGACY_SIZE = WORLD_SIZES[LEGACY]

# The plug-in modules, imported in THIS order by load_plugins() (main.py calls it right after swamp.py, so
# their items / recipes are in settings.py's tables before ui.py builds the crafting tabs).
PLUGINS = ["tundra", "ashlands", "highlands", "terrain", "hollows", "hills"]

# The five outer regions, going round the forest in this order (the ring is rotated by the seed).
RING = ["tundra", "highlands", "ash", "mire", "meadow"]
REGIONS = ["forest"] + RING


def world_size(version):
    return WORLD_SIZES.get(int(version), WORLD_SIZES[CURRENT])


def area_scale(version):
    """How much bigger this world's surface is than the legacy one (counts of things scale with it)."""
    return (world_size(version) / LEGACY_SIZE) ** 2


# =========================================================================== registry
class Biome:
    """One plug-in: a region of the map (region=True) or a feature that isn't a place (terrain, hills,
    hollows: region=False). Every hook is optional. `game` is the LastLight window; `gen` is a Gen.

    Generation (runs on every computer, must be deterministic, use gen.rng only):
      gen_surface(gen)              add surface content, after the legacy content and the Mire
      gen_layers(gen)               fill extra layers (e.g. the "deep" Crystal Hollows), after every gen_surface
      ground(rng, x, y)             texture for the 256px ground tile centred at (x, y) (None = grass).
                                    rng = this biome's own ground stream. Runs inside world.build_world.
      decor(rng, x, y)              texture for a ground tuft at (x, y) (None = the default tufts/pebbles,
                                    False = nothing there). rng = this biome's own decor stream.
      keepout(layout, x, y)         -> True where the shared content (trees, rocks, ponds...) must NOT be put
                                    (rivers, roads, cliffs). Pure function of layout.seed / position.
      tint                          (r, g, b) multiplied into the ground tiles of this biome (blended at borders)
      density                       {"tree": 0.4, "bush": 0.0, "pond": 1.0, "rock": 1.0, "iron": 1.0, "hive": 1.0,
                                    "cave": 1.0, "decor": 1.0}: how much of the shared content (world._build_v2)
                                    lands in this biome (0..1, default 1)
    Resources:
      node_kinds                    node kinds that ONLY grow (and respawn) in this biome, e.g. ("reeds", "glowcap")
      forbid                        node kinds that never respawn in this biome
      respawn_variant(game, n, x, y) -> (variant, base_angle) or None   look of a node growing back here
      sample(game, rng)            -> (x, y) a random point in this biome (default: rejection sampling)
    Spawns (host / solo):
      zombie(game, kind, x, y)      -> kind   swap a night zombie that spawns here (e.g. walker -> drowned)
      animals                       {"rabbit": 5, ...} wild animal weights here (None = the forest's)
      update(game, dt)              every frame while playing (host / solo): spawn things, run hazards
    Survivors:
      player_tick(game, p, dt)      -> extra cold per second (host / solo, p is in this biome on the surface)
      speed(game, p)                -> walking speed multiplier (runs on the computer that moves p)
    Looks (every computer, visual only - the global random is fine here):
      fog                           (r, g, b, a) screen haze while the viewer stands in this biome
      ambient(game, dt, x, y)       every frame on every computer while the viewer is in this biome (particles)
      visuals(game, dt)             every frame on every computer, wherever the viewer is (seasonal looks,
                                    effects that reach past the biome's border). Visual / shared-world only.
    Terrain (every computer, must be pure functions of the world):
      height(game, x, y)            -> ground height in px (summed over all modules; 0 = flat)
      blocked(game, x, y, layer)    -> True if nobody can walk there (cliff faces, deep water)
      water(game, x, y, layer)      -> True if that's water you could drink / swim in
      speed_at(game, p, dx, dy)     -> multiplier for walking from p.pos in direction (dx, dy) (hills)
    Other:
      order                         generation order (lower first). FIXED - never renumber a released one.
      legacy                        also runs on worldgen 1 worlds (only ever ADD nodes then)
    """

    HOOKS = ("gen_surface", "gen_layers", "ground", "decor", "keepout", "respawn_variant", "sample", "zombie", "update",
             "player_tick", "speed", "ambient", "visuals", "height", "blocked", "water", "speed_at")

    def __init__(self, name, title="", order=100, region=True, legacy=False, tint=(255, 255, 255), density=None,
                 node_kinds=(), forbid=(), animals=None, fog=None, **hooks):
        self.name, self.title = name, title or name.title()
        self.order, self.region, self.legacy = order, region, legacy
        self.tint, self.density = tuple(tint), dict(density or {})
        self.node_kinds, self.forbid = tuple(node_kinds), tuple(forbid)
        self.animals, self.fog = animals, fog
        for h in self.HOOKS:
            setattr(self, h, hooks.pop(h, None))
        if hooks:
            raise TypeError(f"Biome {name}: unknown hooks {sorted(hooks)}")

    def dens(self, kind):
        return self.density.get(kind, 1.0)


class LayerInfo:
    """A level of the world besides the surface. Register with register_layer() at import time.
      size                  map size in px (square)
      enter / leave         messages when someone climbs in / out
      cold                  warmth lost per second down here (before clothes)
      dark                  how dark it is (0..1; the cave is 0.93)
      zombie(game, roll)    -> the kind of enemy that spawns here (roll = random 0..1)
      depth                 0 = surface, 1 = cave, 2+ = deeper (messages: going down shows `enter`)
      legacy                created for worldgen 1 worlds too (empty unless a gen_layers hook fills it)
    """

    def __init__(self, name, size, enter="", leave="", cold=CAVE_COLD_PER_SEC, dark=0.93, zombie=None, legacy=True,
                 depth=2):
        self.name, self.size, self.enter, self.leave, self.depth = name, size, enter, leave, depth
        self.cold, self.dark, self.zombie, self.legacy = cold, dark, zombie, legacy


BIOMES = {}                  # name -> Biome (every registered module)
LAYER_INFO = {
    "over": LayerInfo("over", LEGACY_SIZE, "", "", 0.0, 0.0, depth=0),
    "cave": LayerInfo("cave", CAVE_SIZE, "UNDERGROUND. It's cold and dark - bring a torch. Ore and crystal down here!",
                      "Back to the surface.", CAVE_COLD_PER_SEC, 0.93,
                      lambda game, roll: "golem" if roll < 0.18 + 0.02 * game.day else "crawler", depth=1),
}
_cache = {}


def register(b):
    BIOMES[b.name] = b
    _cache.clear()
    return b


def register_layer(info):
    """Add a layer ("deep", ...). Appends to world.LAYERS (its index is its network / save id), so plug-ins
    must always be imported in the PLUGINS order."""
    import world
    LAYER_INFO[info.name] = info
    if info.name not in world.LAYERS:
        world.LAYERS.append(info.name)
    return info


def ordered():
    """Every registered module in generation order (fixed: order, then name)."""
    if "ordered" not in _cache:
        _cache["ordered"] = sorted(BIOMES.values(), key=lambda b: (b.order, b.name))
    return _cache["ordered"]


def with_hook(hook):
    key = "hook:" + hook
    if key not in _cache:
        _cache[key] = [b for b in ordered() if getattr(b, hook) is not None]
    return _cache[key]


def get(name):
    return BIOMES.get(name) or BIOMES["forest"]


_loaded = False


def load_plugins():
    """Import every plug-in module (they register themselves). Safe to call more than once."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for mod in PLUGINS:
        importlib.import_module(mod)


def keepout(layout, x, y):
    """Does any module (rivers, roads, cliffs...) want this surface spot kept free of shared content?"""
    return any(b.keepout(layout, x, y) for b in with_hook("keepout"))


def underground(layer):
    return layer != "over"


def depth(layer):
    info = LAYER_INFO.get(layer)
    return info.depth if info else 2


# =========================================================================== noise (deterministic, no numpy)
def _h(s, ix, iy):
    h = (ix * 374761393 + iy * 668265263 + s * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def noise(s, x, y):
    """Smooth value noise in 0..1 with features about 1 unit apart."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _h(s, ix, iy), _h(s, ix + 1, iy)
    c, d = _h(s, ix, iy + 1), _h(s, ix + 1, iy + 1)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def fbm(s, x, y, octaves=3):
    tot, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        tot += noise(s + o * 101, x, y) * amp
        norm += amp
        amp *= 0.5
        x, y = x * 2.03, y * 2.03
    return tot / norm


def seed_int(seed, name):
    return zlib.crc32(f"{seed}:{name}".encode()) & 0x7FFFFFFF


# =========================================================================== layouts
class Layout:
    """Worldgen 2: the forest in the middle (spawn), five regions in a ring of wedges around it.
    Borders wobble with noise so they look natural."""

    version = CURRENT

    def __init__(self, seed, size):
        self.seed, self.size = seed, size
        self.centre = (size / 2, size / 2)
        rng = random.Random(f"{seed}:layout")
        self.rot = rng.uniform(0, math.tau)
        self.ring = list(RING)
        self.wedge = math.tau / len(self.ring)
        self.forest_r = size * 0.21           # ~1180 px: the old map's whole spawn area and then some
        self.s_ang = seed_int(seed, "layout-angle")
        self.s_rad = seed_int(seed, "layout-radius")
        # a spot well inside each outer region (wedge middle, ~2/3 of the way out): lairs, landmarks
        self.centres = {"forest": self.centre}
        for i, name in enumerate(self.ring):
            a = self.rot + (i + 0.5) * self.wedge
            d = size * 0.36
            self.centres[name] = (self.centre[0] + math.cos(a) * d, self.centre[1] + math.sin(a) * d)

    def biome_at(self, x, y):
        cx, cy = self.centre
        dx, dy = x - cx, y - cy
        r = math.hypot(dx, dy)
        wob = fbm(self.s_rad, x / 700.0, y / 700.0) - 0.5
        if r < self.forest_r * (1.0 + 0.55 * wob):
            return "forest"
        ang = math.atan2(dy, dx) + (fbm(self.s_ang, x / 1100.0, y / 1100.0) - 0.5) * 1.1
        i = int(((ang - self.rot) % math.tau) / self.wedge) % len(self.ring)
        return self.ring[i]


class LegacyLayout:
    """Worldgen 1: everything is forest except the Mire (swamp.py's blobs)."""

    version = LEGACY

    def __init__(self, seed, size, game=None):
        self.seed, self.size, self.game = seed, size, game
        self.centre = (size / 2, size / 2)
        self.ring = []
        self.centres = {"forest": self.centre}

    def biome_at(self, x, y):
        g = self.game
        if g is not None and g.in_swamp((x, y)):
            return "mire"
        return "forest"


def make_layout(seed, version, game=None):
    size = world_size(version)
    return LegacyLayout(seed, size, game) if int(version) == LEGACY else Layout(seed, size)


def weights_at(layout, x, y, radius=170):
    """{biome: share} from 9 samples around (x, y) - smooth blending at borders (ground tint etc.)."""
    out = {}
    pts = [(0, 0)] + [(math.cos(a) * radius, math.sin(a) * radius) for a in (i * math.tau / 8 for i in range(8))]
    for ox, oy in pts:
        b = layout.biome_at(x + ox, y + oy)
        out[b] = out.get(b, 0) + 1 / len(pts)
    return out


def blend_tint(layout, x, y, radius=170):
    w = weights_at(layout, x, y, radius)
    col = [0.0, 0.0, 0.0]
    for name, k in w.items():
        t = get(name).tint
        for i in range(3):
            col[i] += t[i] * k
    return tuple(int(round(c)) for c in col)


# =========================================================================== generation
class Gen:
    """What a generation hook gets. Everything here is deterministic."""

    def __init__(self, game, module):
        self.game = game
        self.name = module
        self.seed = game.seed
        self.version = game.worldgen
        self.size = game.world_size
        self.layout = game.layout
        self.layers = game.layers
        self.over = game.layers["over"]
        self.cave = game.layers["cave"]
        self.nodes = game.nodes
        self.rng = random.Random(f"{self.seed}:{module}")
        self.scale = area_scale(self.version)

    def biome_at(self, p):
        return self.layout.biome_at(p[0], p[1])

    def add_node(self, n, lst, layer="over"):
        """Append a Node: gives it the next index, puts it in `lst` (e.g. L.trees) and makes it solid."""
        L = self.layers[layer]
        n.layer = layer
        n.idx = len(self.nodes)
        self.nodes.append(n)
        lst.append(n)
        L.solid.append(n)
        return n

    def spot(self, biome=None, margin=100, tries=80):
        """A random point (in `biome` if given). None if it couldn't find one."""
        r, s = self.rng, self.size
        for _ in range(tries):
            p = (r.uniform(margin, s - margin), r.uniform(margin, s - margin))
            if biome is None or self.biome_at(p) == biome:
                return p
        return None

    def free(self, p, rad, layer="over", gap=26):
        """Nothing in the way: no node, pond or exit within rad, clear of the spawn circle."""
        L = self.layers[layer]
        x, y = p
        if not (60 + rad < x < L.size - 60 - rad and 60 + rad < y < L.size - 60 - rad):
            return False
        if layer == "over":
            if math.hypot(x - self.layout.centre[0], y - self.layout.centre[1]) < 170 + rad:
                return False
            if keepout(self.layout, x, y):
                return False
        if self.game.terrain_blocked(x, y, layer) or self.game.terrain_water(x, y, layer):
            return False
        for s in list(L.ponds) + list(L.exits):
            if math.hypot(s.center_x - x, s.center_y - y) < rad + 130:
                return False
        cells = self._grid()
        reach = rad + gap + 60          # + the biggest node radius
        c0x, c1x = int((x - reach) // 128), int((x + reach) // 128)
        c0y, c1y = int((y - reach) // 128), int((y + reach) // 128)
        for gx in range(c0x, c1x + 1):
            for gy in range(c0y, c1y + 1):
                for n in cells.get((layer, gx, gy), ()):
                    if math.hypot(n.base[0] - x, n.base[1] - y) < rad + gap:
                        return False
        return True

    def _grid(self):
        """A lookup grid of every node (kept up to date as hooks add nodes)."""
        g = self.game
        grid = getattr(g, "_gen_grid", None)
        if grid is None or grid[0] is not self.nodes:
            grid = g._gen_grid = [self.nodes, 0, {}]
        cells = grid[2]
        for n in self.nodes[grid[1]:]:
            cells.setdefault((n.layer, int(n.base[0] // 128), int(n.base[1] // 128)), []).append(n)
        grid[1] = len(self.nodes)
        return cells


def generate(game):
    """Run every module's gen_surface, then every gen_layers, in the fixed order. Records node spans."""
    legacy = game.worldgen == LEGACY
    for hook in ("gen_surface", "gen_layers"):
        for b in with_hook(hook):
            if legacy and not b.legacy:
                continue
            start = len(game.nodes)
            getattr(b, hook)(Gen(game, b.name))
            if len(game.nodes) > start:
                key = b.name if hook == "gen_surface" else b.name + ":layers"
                game.node_spans[key] = [start, len(game.nodes) - start]


def remap_index(saved_spans, now_spans):
    """A save's node index -> today's index (or None if that node doesn't exist any more).
    Saves without spans (and saves whose spans match) map 1:1."""
    if not saved_spans or saved_spans == now_spans:
        return lambda i: i
    table = []
    for key, (start, count) in saved_spans.items():
        if key in now_spans:
            ns, nc = now_spans[key]
            table.append((int(start), int(count), ns, nc))

    def f(i):
        for start, count, ns, nc in table:
            if start <= i < start + count:
                loc = i - start
                return ns + loc if loc < nc else None
        return None
    return f


# =========================================================================== the game-side mixin
class BiomeWorld:
    """Mixed into the game window. Every call site in main.py / base.py / weather.py goes through these."""

    def biome_at(self, pos, layer="over"):
        if layer != "over":
            return layer
        return self.layout.biome_at(pos[0], pos[1])

    def biome_weights(self, pos, radius=170):
        return weights_at(self.layout, pos[0], pos[1], radius)

    # --- terrain
    def ground_height(self, x, y):
        hs = with_hook("height")
        if not hs:
            return 0.0
        return sum(b.height(self, x, y) for b in hs)

    def terrain_blocked(self, x, y, layer="over"):
        return any(b.blocked(self, x, y, layer) for b in with_hook("blocked"))

    def terrain_water(self, x, y, layer="over"):
        return any(b.water(self, x, y, layer) for b in with_hook("water"))

    # --- survivors
    def biome_speed(self, p):
        """Walking speed multiplier from the biome under p and the terrain (runs where p is moved)."""
        k = 1.0
        if p.layer == "over":
            b = get(self.biome_at(p.pos))
            if b.speed is not None:
                k *= b.speed(self, p)
        for b in with_hook("speed_at"):
            k *= b.speed_at(self, p, p.move[0], p.move[1])
        return k

    def biome_survivor(self, p, dt):
        """Host / solo: extra cold per second for p from where they stand (and any biome hazards)."""
        if p.layer != "over":
            return 0.0
        b = get(self.biome_at(p.pos))
        return b.player_tick(self, p, dt) or 0.0 if b.player_tick is not None else 0.0

    def biome_update(self, dt):
        """Host / solo, every frame while playing."""
        for b in with_hook("update"):
            if self.worldgen == LEGACY and not b.legacy:
                continue
            b.update(self, dt)

    def biome_ambient(self, dt):
        """Every computer, every frame: every module's `visuals`, then the viewer's biome particles."""
        for b in with_hook("visuals"):
            if self.worldgen == LEGACY and not b.legacy:
                continue
            b.visuals(self, dt)
        if self.view_layer != "over":
            return
        x, y = self.view_pos()
        b = get(self.biome_at((x, y)))
        if b.ambient is not None:
            b.ambient(self, dt, x, y)

    def biome_fog(self):
        """(r, g, b, a) haze for where the viewer stands, blended over the borders; None = none."""
        if self.view_layer != "over":
            return None
        w = self.biome_weights(self.view_pos(), 260)
        col, a = [0.0, 0.0, 0.0], 0.0
        for name, k in w.items():
            f = get(name).fog
            if f:
                a += f[3] * k
                for i in range(3):
                    col[i] += f[i] * f[3] * k
        if a <= 0:
            return None
        return tuple(int(c / a) for c in col) + (int(a),)

    # --- spawns
    def biome_zombie_kind(self, kind, x, y, layer):
        if layer != "over":
            return kind
        b = get(self.biome_at((x, y)))
        return b.zombie(self, kind, x, y) if b.zombie is not None else kind

    def layer_zombie_kind(self, layer, roll=None):
        info = LAYER_INFO.get(layer)
        if info is None or info.zombie is None:
            return "crawler"
        return info.zombie(self, random.random() if roll is None else roll)

    def animal_weights(self, pos):
        """{kind: weight} for a wild animal spawning at pos. Animals with a "home" biome in settings.ANIMALS
        (e.g. the tundra's snow foxes) never spawn anywhere else unless that biome lists them."""
        b = get(self.biome_at(pos))
        w = b.animals if b.animals is not None else get("forest").animals
        homed = [k for k, v in ANIMALS.items() if v.get("home") and k not in w]
        if homed:
            w = dict(w)
            for k in homed:
                w[k] = 0
        return w

    # --- resources
    def node_allowed(self, kind, p):
        """May a `kind` node (re)grow at surface point p? Biome-exclusive kinds only in their biome,
        and nothing a biome forbids."""
        here = self.biome_at(p)
        homes = [b.name for b in BIOMES.values() if kind in b.node_kinds]
        if homes and here not in homes:
            return False
        return kind not in get(here).forbid

    def node_spot_candidate(self, kind, rng):
        """Surface candidate spot for a respawning `kind` node (None = no idea)."""
        homes = [b for b in ordered() if kind in b.node_kinds]
        size = self.layers["over"].size
        if not homes:
            return rng.uniform(100, size - 100), rng.uniform(100, size - 100)
        b = rng.choice(homes)
        if b.sample is not None:
            return b.sample(self, rng)
        for _ in range(30):
            p = (rng.uniform(100, size - 100), rng.uniform(100, size - 100))
            if self.biome_at(p) == b.name:
                return p
        return None

    def node_respawn_look(self, n, x, y):
        """(variant, base_angle) for a node growing back at (x, y), or None to keep its look."""
        b = get(self.biome_at((x, y)))
        if b.respawn_variant is not None:
            got = b.respawn_variant(self, n, x, y)
            if got is not None:
                return got
        if n.kind == "tree":
            return random.randint(0, 2), random.uniform(0, 360)
        return None

    # --- layers & portals
    def add_portal(self, layer_a, pos_a, layer_b, pos_b):
        """Link two exits (the exit sprites themselves go in each layer's .exits list)."""
        self.portals.append((layer_a, tuple(pos_a), layer_b, tuple(pos_b)))

    def portal_from(self, layer, pos):
        """The far end of the portal at (layer, pos): (layer, pos) or None."""
        for la, pa, lb, pb in self.portals:
            if la == layer and math.hypot(pa[0] - pos[0], pa[1] - pos[1]) < 5:
                return lb, pb
            if lb == layer and math.hypot(pb[0] - pos[0], pb[1] - pos[1]) < 5:
                return la, pa
        return None

    def layer_cold(self, layer):
        info = LAYER_INFO.get(layer)
        return info.cold if info else CAVE_COLD_PER_SEC

    def layer_dark(self, layer):
        info = LAYER_INFO.get(layer)
        return info.dark if info else 0.93


# =========================================================================== the built-in biome: the forest
register(Biome(
    "forest", title="The Forest", order=0, legacy=True,
    animals={"rabbit": 5, "deer": 3, "boar": 3, "wolf": 2, "bee": 4},
))
