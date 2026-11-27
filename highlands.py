"""
highlands.py - THE STONE HIGHLANDS: the rocky upland region of the big map, home of the Quake Titan.

What's here (worldgen 2 only - old saves are untouched):
  * Scree and gravel ground with wiry grass and heather tufts, a grey haze and a cold wind (a little extra
    chill, worse at night).
  * Boulder fields: big faceted BOULDERS (lots of stone, need a pickaxe), extra rocks and iron, few trees -
    and those are wind-bent highland pines, all leaning the same way (the wind of this world).
  * HEATHER: low purple shrubs. Heather Tea, the Highland Wool Cloak, and goats are tamed with it.
  * PLATEAUS: raised rocky tablelands ringed by cliff ledges (solid 3D rock walls), reached by ramps.
    height() lifts them (summed with hills.py), blocked() stops you walking up the cliff faces.
  * MOUNTAIN GOATS: butt back when attacked; drop meat, Goat Wool and Goat Horn; tame them with heather
    (haulers). 3D model: tools/blender/models/highlands.py -> assets/models/goat.glb.
  * QUAKES: every couple of minutes someone spends up here the ground trembles (screen shake, dust), then
    boulders break loose: some ROLL down at you (dodge them - they hurt), some fall out of the sky (red
    circles). Rolling boulders that come to rest stay as new boulders you can mine.
  * The TITAN'S CROWN: a ring of rune-carved standing stones around game.layout.centres["highlands"].

Co-op: quakes, rolling boulders and settling boulders run on the host. Rolling boulders travel in the normal
hazard snapshot (kind "hl_roll", clients move them with vx / vy), settled boulders are a pool of nodes made
at generation (they start "gone") that the host moves with base.place_node, so they reach clients through
the usual "nm" / "n" rows and are saved like any moved node. Ledges, plateaus and standing stones are pure
functions of the seed, rebuilt on every computer.
"""
import math
import random

import arcade

import art
import base
import biomes
import shapes3d as S3
from settings import *
from world import Hazard, Node

NAME = "highlands"
HL_TREE = 40                 # tree variants 40..42 are highland pines (art_highlands.py)
PLATEAU_H = 40               # how much higher a plateau is (px, added to hills.py's height)
RAMP_LEN = 150               # how long a ramp up onto a plateau is
RAMP_W = 120                 # ...and how wide
QUAKE_FIRST = (45, 80)       # seconds someone spends in the highlands before the first quake
QUAKE_EVERY = (85, 150)      # ...and between quakes
RUMBLE = 2.2                 # the warning tremor before the boulders come loose
ROLL_R = 30                  # rolling boulder radius
ROLL_DMG = 16
POOL = 24                    # boulders that quakes can leave lying around (nodes made at generation)

# =========================================================================== data (added to settings.py's tables)
ITEMS.update({
    "wool": {"name": "Goat Wool", "kind": "material",
             "desc": "From mountain goats in the Stone Highlands. Thick and warm: the best cloak short of frost."},
    "goat_horn": {"name": "Goat Horn", "kind": "material", "desc": "Curved and springy. Makes a powerful bow."},
    "heather": {"name": "Heather", "kind": "material",
                "desc": "Tough purple shrub of the highlands. Tea, cloaks - and goats love it (taming)."},
    "heather_tea": {"name": "Heather Tea", "kind": "food", "thirst": 30, "energy": 30, "health": 10,
                    "desc": "Brewed at a campfire. +30 thirst, +30 energy, +10 health."},
    "wool_cloak": {"name": "Highland Wool Cloak", "kind": "armor", "slot": "cloak", "armor": 1, "warmth": 10,
                   "desc": "Warmth 10, armor 1. Heather-dyed goat wool: warmer than fur, only the Frost Cloak beats it."},
    "horn_bow": {"name": "Horn Bow", "kind": "weapon", "damage": 7.5, "reach": 640, "cooldown": 0.6, "ranged": 1,
                 "desc": "Shoots where you aim, 7.5 damage and longer range than the Hunting Bow. Uses Arrows."},
})
NODES.update({
    "boulder": {"gives": "stone", "hp": 12, "regrow": 150, "needs": "pickaxe"},
    "heather": {"gives": "heather", "hp": 1, "regrow": 80},
})
for _tool, _k in (("pickaxe", 2), ("iron_pickaxe", 3)):
    ITEMS[_tool].setdefault("harvest", {})["boulder"] = _k
ANIMALS["goat"] = {"hp": 9, "speed": 185, "temper": "defend", "drops": {"meat": 2, "wool": 2, "goat_horn": 1},
                   "tame": "heather", "chance": 0.4, "job": "hauler", "dmg": 7,
                   "desc": "Hauler: sure-footed - chops trees and breaks rocks, carries wood & stone home."}
base.NODE_RADIUS.update({"boulder": 44, "heather": 18})

CRAFT_TABS["Tools"].append(R("horn_bow", {"goat_horn": 2, "wood": 3, "fiber": 4}, "workbench"))
CRAFT_TABS["Armor"].append(R("wool_cloak", {"wool": 5, "leather": 1, "heather": 2}, "workbench"))
CRAFT_TABS["Supplies"].append(R("heather_tea", {"heather": 2, "water": 1}, "campfire"))
RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]   # same list object, crafting indexes in tab order

import art_highlands  # noqa: E402  (after the tables: registers the new art)

try:     # the worn cloak's colour on the 3D survivor model
    import models3d
    models3d.GEAR_COL.setdefault("wool_cloak", (198, 186, 160))
except Exception:      # pragma: no cover - models are optional
    pass

# =========================================================================== 3D shapes (shapes3d.py guide)
_P = S3.Part
S3.SHAPES["boulder"] = S3.boulder(height=1.3, lump=0.3, sides=7, foot=(0.92, 0.9), turn=0.2)
# cliff-ledge chunk: a squat faceted block with a flat, grassy top (the plateau rims)
S3.SHAPES["hl_ledge"] = S3.Shape([_P([(1.0, 0.0, 0.86, 0.58), (1.05, 0.7, 0.9, 0.74), (0.98, 1.32, 0.86, 0.9),
                                       (0.8, 1.52, 0.68, 1.0), (0.0, 1.6, 0.0, 1.06)], sides=6, jitter=0.18)],
                                 foot=(0.96, 0.96), turn=0.3, cut=0.1)
# a tall standing stone (a flattened slab) with a band of glowing Titan runes
S3.SHAPES["menhir"] = S3.Shape([_P([(1.0, 0.0, 0.9, 0.58), (1.02, 1.1, 0.9, 0.74), (0.92, 2.3, 0.86, 0.9),
                                    (0.62, 2.9, 0.6, 1.0), (0.0, 3.06, 0.0, 1.06)], sides=6, jitter=0.1),
                                _P(S3.tube(1.04, 0.99, 0.14, z0=1.75), color=(240, 150, 70), sides=6, glow=0.7)],
                               foot=(0.82, 0.52), turn=0.2, cut=0.1)
S3.SHAPES["heather"] = S3.dome_bush(height=0.95, sides=8, lump=0.2, sway=0.08)


def _pine_shape():
    """Wind-bent pine: the trunk leans downwind (+x, the picture's right), the crown is a flat, swept
    cushion of overlapping filled blobs (solid from every side)."""
    lean = 0.3
    tl = 2.05
    top = (math.sin(lean) * tl, 0.0, math.cos(lean) * tl)
    needles = S3.Fill(0.62, 0.5)
    bark = (92, 70, 52)
    parts = [_P(S3.tube(0.16, 0.07, tl, shade=(0.7, 0.95)), tilt=lean, color=bark, sides=6),
             _P(S3.tube(0.05, 0.02, 0.8), at=(top[0] * 0.55, 0, top[2] * 0.6), tilt=1.2, color=bark, sides=4),
             _P(S3.ball(4), at=(top[0], 0.0, top[2]), size=(0.95, 0.72, 0.36), color=needles, sides=7, jitter=0.16,
                sway=0.06),
             _P(S3.ball(3), at=(top[0] + 0.55, 0.05, top[2] - 0.18), size=(0.62, 0.52, 0.28), color=needles, sides=6,
                jitter=0.18, sway=0.08),
             _P(S3.ball(3), at=(top[0] - 0.1, -0.1, top[2] + 0.26), size=(0.6, 0.5, 0.26), color=needles, sides=6,
                jitter=0.16, sway=0.06),
             _P(S3.ball(3), at=(top[0] * 0.5 + 0.25, 0.18, top[2] * 0.66), size=(0.52, 0.42, 0.24), color=needles,
                sides=6, jitter=0.16, sway=0.05, detail=True)]
    return S3.Shape(parts, alt=S3._stump(bark), foot=(0.9, 0.9))


S3.SHAPES["hl_tree"] = _pine_shape()
_prev_variant = S3.VARIANTS.get("tree", lambda s: "tree")
S3.VARIANTS["tree"] = lambda s: "hl_tree" if HL_TREE <= s.variant < HL_TREE + 3 else _prev_variant(s)


# =========================================================================== goats only live up here
def _no_goats(b):
    if b.animals is not None and b.name != NAME:
        b.animals.setdefault("goat", 0)


for _b in list(biomes.BIOMES.values()):
    _no_goats(_b)
_prev_register = biomes.register


def _register(b):        # modules registered after this one (terrain, hollows, hills) get "goat": 0 too
    _no_goats(b)
    return _prev_register(b)


biomes.register = _register


# =========================================================================== terrain: plateaus (pure functions)
class Plateau:
    def __init__(self, x, y, r0, harm, ramps):
        self.x, self.y, self.r0 = x, y, r0
        self.harm = harm                     # [(amplitude, frequency, phase)]
        self.ramps = ramps                   # ramp directions (radians)
        self.rmax = r0 * (1 + sum(a for a, _, _ in harm))

    def radius(self, th):
        return self.r0 * (1 + sum(a * math.sin(f * th + p) for a, f, p in self.harm))

    def ramp_at(self, th, r, pad=0.0):
        """Index of the ramp at angle th (radius r), or -1."""
        hw = (RAMP_W / 2 + pad) / max(r, 1.0)
        for i, a in enumerate(self.ramps):
            if abs((th - a + math.pi) % math.tau - math.pi) < hw:
                return i
        return -1


_PLAT = {}


def plateaus(layout):
    """The plateaus of a world: a pure function of its seed and layout (cached)."""
    key = (layout.seed, layout.size, getattr(layout, "version", 2))
    got = _PLAT.get(key)
    if got is not None:
        return got
    _PLAT[key] = []          # (re-entry while computing sees none)
    out = []
    centres = getattr(layout, "centres", {})
    if getattr(layout, "version", 2) == biomes.LEGACY or NAME not in centres:
        return out
    rng = random.Random(f"{layout.seed}:highlands:plateaus")
    lair = centres[NAME]
    S = layout.size
    others = [b for b in biomes.with_hook("keepout") if b.name != NAME]
    for _ in range(400):
        if len(out) >= 6:
            break
        x, y = rng.uniform(400, S - 400), rng.uniform(400, S - 400)
        r0 = rng.uniform(190, 280)
        harm = [(rng.uniform(0.05, 0.12), 2, rng.uniform(0, math.tau)),
                (rng.uniform(0.03, 0.08), 3, rng.uniform(0, math.tau)),
                (rng.uniform(0.0, 0.04), 5, rng.uniform(0, math.tau))]
        a0 = rng.uniform(0, math.tau)
        ramps = [a0, a0 + rng.uniform(2.3, 3.9)]
        if layout.biome_at(x, y) != NAME:
            continue
        if math.hypot(x - lair[0], y - lair[1]) < r0 + 450:
            continue
        if any(math.hypot(x - p.x, y - p.y) < r0 + p.r0 + 240 for p in out):
            continue
        ok = True
        for k in range(16):
            th = k / 16 * math.tau
            for rr in (r0 * 0.6, r0 * 1.3 + 40):
                px, py = x + math.cos(th) * rr, y + math.sin(th) * rr
                if not (150 < px < S - 150 and 150 < py < S - 150) or layout.biome_at(px, py) != NAME or \
                        any(b.keepout(layout, px, py) for b in others):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            out.append(Plateau(x, y, r0, harm, ramps))
    _PLAT[key] = out
    return out


def _near(layout, x, y, pad):
    for p in plateaus(layout):
        if abs(x - p.x) < p.rmax + pad and abs(y - p.y) < p.rmax + pad:
            yield p


def _v2(game):
    return getattr(game, "worldgen", 1) != biomes.LEGACY


def height(game, x, y):
    """A plateau's top is PLATEAU_H higher; its ramps slope down to the ground around it."""
    if not _v2(game):
        return 0.0
    for p in _near(game.layout, x, y, RAMP_LEN):
        dx, dy = x - p.x, y - p.y
        d = math.hypot(dx, dy)
        th = math.atan2(dy, dx)
        r = p.radius(th)
        if d <= r:
            return float(PLATEAU_H)
        if d < r + RAMP_LEN and p.ramp_at(th, r) >= 0:
            k = (d - r) / RAMP_LEN
            return PLATEAU_H * (1 - k * k * (3 - 2 * k))
    return 0.0


def blocked(game, x, y, layer):
    """The cliff faces around a plateau (not where the ramps are)."""
    if layer != "over" or not _v2(game):
        return False
    for p in _near(game.layout, x, y, 30):
        dx, dy = x - p.x, y - p.y
        d = math.hypot(dx, dy)
        th = math.atan2(dy, dx)
        r = p.radius(th)
        if r - 8 < d < r + 20 and p.ramp_at(th, r) < 0:
            return True
    return False


def keepout(layout, x, y):
    """Keep the shared trees / rocks / ponds / caves off the plateau rims and ramps, and out of the Titan's Crown."""
    if getattr(layout, "version", 2) == biomes.LEGACY:
        return False
    lair = layout.centres.get(NAME)
    if lair and abs(x - lair[0]) < 260 and abs(y - lair[1]) < 260 and math.hypot(x - lair[0], y - lair[1]) < 260:
        return True
    for p in _near(layout, x, y, RAMP_LEN + 40):
        dx, dy = x - p.x, y - p.y
        d = math.hypot(dx, dy)
        th = math.atan2(dy, dx)
        r = p.radius(th)
        if r - 45 < d < r + 60:
            return True
        if r <= d < r + RAMP_LEN + 30 and p.ramp_at(th, r, 40) >= 0:
            return True
    return False


def wind_angle(layout):
    """The direction the wind blows in this world (radians): the pines all lean that way."""
    return (biomes.seed_int(layout.seed, "highlands-wind") % 6283) / 1000.0


# =========================================================================== generation
class State:
    """Per-world highland state (game.hl). Made by gen_surface on every computer."""

    def __init__(self, game):
        self.nodes = game.nodes              # which world this belongs to
        self.ledges = arcade.SpriteList()
        self.stones = arcade.SpriteList()
        self.pool = []
        self.pool_ids = set()
        self.rolls = []                      # host: rolling boulders (Hazards)
        self.roll_list = arcade.SpriteList() # every computer: sprites drawing them
        self.quake_t = random.uniform(*QUAKE_FIRST)
        self.phase = None
        self.phase_t = 0.0
        self.dust_t = 0.0
        self.strip_t = 0.0
        self.trail_t = 0.0
        self.told = False


def _state(game):
    st = getattr(game, "hl", None)
    return st if st is not None and st.nodes is game.nodes else None


def gen_surface(gen):
    g, rng, over = gen.game, gen.rng, gen.over
    st = g.hl = State(g)
    wind = wind_angle(gen.layout)
    wind_deg = -math.degrees(wind)

    # the few trees standing up here become wind-bent pines (same nodes, new look)
    for n in over.trees:
        if n.kind == "tree" and gen.biome_at(n.position) == NAME:
            n.variant = HL_TREE + n.idx % 3
            n.angle = n.base_angle = wind_deg + (n.idx % 7 - 3) * 3.0
            if n.state == "full":
                n.texture = art.tree(n.variant)

    # plateaus: a tableland patch on top, cliff-ledge chunks round the rim (solid, drawn in 3D), scree on the ramps
    for p in plateaus(gen.layout):
        top = arcade.Sprite(art_highlands.plateau_top(), center_x=p.x, center_y=p.y)
        top.scale = p.r0 * 2.25 / 512
        top.angle = rng.uniform(0, 360)
        over.ground.append(top)
        th = 0.0
        while th < math.tau:
            r = p.radius(th)
            step = rng.uniform(26, 34) / r
            if p.ramp_at(th, r, 10) < 0:
                d = r + 8 + rng.uniform(-3, 3)
                s = arcade.Sprite(art_highlands.ledge(rng.randint(0, 3)), center_x=p.x + math.cos(th) * d,
                                  center_y=p.y + math.sin(th) * d)
                s.scale = rng.uniform(0.74, 0.92)
                s.angle = rng.uniform(0, 360)
                st.ledges.append(s)
                over.solid.append(s)
            th += step
        for a in p.ramps:
            r = p.radius(a)
            fan = arcade.Sprite(art_highlands.scree_fan(), center_x=p.x + math.cos(a) * (r + RAMP_LEN * 0.45),
                                center_y=p.y + math.sin(a) * (r + RAMP_LEN * 0.45))
            fan.scale = (RAMP_LEN + 40) / 256
            over.ground.append(fan)

    # the Titan's Crown: a ring of rune stones round the lair
    lair = gen.layout.centres[NAME]
    ring = arcade.Sprite(art_highlands.stone_circle(), center_x=lair[0], center_y=lair[1])
    ring.scale = 470 / 512
    over.ground.append(ring)
    for k in range(9):
        a = k / 9 * math.tau + rng.uniform(-0.08, 0.08)
        s = arcade.Sprite(art_highlands.menhir(k), center_x=lair[0] + math.cos(a) * 180,
                          center_y=lair[1] + math.sin(a) * 180)
        s.scale = rng.uniform(1.05, 1.3)
        s.angle = -math.degrees(a) + 90 + rng.uniform(-10, 10)     # broad side facing the middle
        st.stones.append(s)
        over.solid.append(s)

    def scatter(count, rad, make):
        placed = 0
        for _ in range(count * 6):
            if placed >= count:
                break
            p = gen.spot(NAME)
            if p and gen.free(p, rad):
                make(p)
                placed += 1

    def boulder(p):
        v = rng.randint(0, 2)
        n = Node("boulder", art_highlands.boulder(v), *p)
        n.variant = v
        n.angle = n.base_angle = rng.uniform(0, 360)
        gen.add_node(n, over.rocks)

    def rock(p):
        v = rng.randint(0, 3)
        n = Node("rock", art.rock(v), *p)
        n.variant = v
        gen.add_node(n, over.rocks)

    import art_extra
    scatter(70, 44, boulder)
    scatter(40, 34, rock)
    scatter(14, 34, lambda p: gen.add_node(Node("iron", art_extra.ore("iron"), *p), over.rocks))
    scatter(70, 18, lambda p: gen.add_node(Node("heather", art_highlands.heather(), *p), over.bushes))

    # the quake pool: boulders that start out of the world ("gone") and get put down where quakes leave them
    for i in range(POOL):
        n = Node("boulder", art_highlands.boulder(i % 3), lair[0], lair[1])
        n.variant = i % 3
        n.scale = 0.78
        n.angle = n.base_angle = rng.uniform(0, 360)
        gen.add_node(n, over.rocks)
        n.state = "gone"
        n.visible = False
        over.solid.remove(n)
        st.pool.append(n)
    st.pool_ids = {id(n) for n in st.pool}


def _respawn(game, n, x, y):
    if n.kind == "tree":
        return HL_TREE + random.randint(0, 2), -math.degrees(wind_angle(game.layout)) + random.uniform(-9, 9)
    return None


# =========================================================================== quakes (host / solo)
def _shake_for(game, p, mag, dur):
    if game._emit(["shk", mag, dur, "over"], p):
        game._shake(mag, dur, "over")


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def update(game, dt):
    st = _state(game)
    if st is None:
        return
    st.strip_t -= dt
    if st.strip_t <= 0:          # quake boulders don't regrow elsewhere: mined out, they go back to the pool
        st.strip_t = 1.0
        if any(id(it[1]) in st.pool_ids for it in game.regrow):
            game.regrow[:] = [it for it in game.regrow if id(it[1]) not in st.pool_ids]
    _roll(game, st, dt)
    here = [p for p in game.alive_players("over") if game.biome_at(p.pos) == NAME]
    if st.phase is None:
        if here and not game.cut and game.state == "playing":
            st.quake_t -= dt
            if st.quake_t <= 0:
                st.phase, st.phase_t, st.dust_t = "rumble", RUMBLE, 0.0
                for p in here:
                    _shake_for(game, p, 3, RUMBLE)
                    game.rumble(0.3, RUMBLE, to=p)
                    game.say("The ground trembles... a QUAKE! Watch the slopes for falling rock.", 3, to=p)
                    game.play("boom", 0.18, to=p)
        return
    st.phase_t -= dt
    st.dust_t -= dt
    if st.dust_t <= 0:
        st.dust_t = 0.3
        game.fx_layer = "over"
        for p in here:
            a, d = random.uniform(0, math.tau), random.uniform(60, 300)
            game.burst(p.pos[0] + math.cos(a) * d, p.pos[1] + math.sin(a) * d, (150, 140, 120), 6, 70, 5, 1.0,
                       layer="over")
    if st.phase_t <= 0:
        st.phase = None
        st.quake_t = random.uniform(*QUAKE_EVERY)
        _shock(game, st, here)


def _shock(game, st, here):
    game.fx_layer = "over"
    for p in here:
        _shake_for(game, p, 10, 1.1)
        game.rumble(0.9, 0.6, to=p)
        game.play("boom", 0.5, at=p.pos, layer="over")
        game.say("ROCKFALL! Boulders are breaking loose - get clear!", 3, to=p)
        for _ in range(2 + (random.random() < 0.5)):
            _spawn_roll(game, st, p)
        for _ in range(random.randint(1, 2)):
            a, d = random.uniform(0, math.tau), random.uniform(80, 230)
            x = max(100, min(game.world_size - 100, p.pos[0] + math.cos(a) * d))
            y = max(100, min(game.world_size - 100, p.pos[1] + math.sin(a) * d))
            game.hazards.append(Hazard("boulder", x, y, 56, tele=random.uniform(1.0, 1.6), dmg=12))


def _spawn_roll(game, st, p):
    """A boulder breaks loose from a crag, ledge or boulder above p and rolls down at them."""
    px, py = p.pos
    srcs = [s.position for s in st.ledges if 220 < _dist(s.position, p.pos) < 520]
    srcs += [n.position for n in game.over.rocks if n.kind == "boulder" and n.state == "full"
             and abs(n.center_x - px) < 520 and abs(n.center_y - py) < 520 and 220 < _dist(n.position, p.pos) < 520]
    if srcs:
        sx, sy = random.choice(srcs)
        a = math.atan2(py - sy, px - sx)
        sx, sy = sx + math.cos(a) * 60, sy + math.sin(a) * 60
    else:
        a0 = random.uniform(0, math.tau)
        sx, sy = px + math.cos(a0) * 380, py + math.sin(a0) * 380
    S = game.world_size
    sx, sy = max(80, min(S - 80, sx)), max(80, min(S - 80, sy))
    a = math.atan2(py - sy, px - sx) + random.uniform(-0.3, 0.3)
    sp = random.uniform(210, 260)
    T = (_dist((sx, sy), p.pos) + random.uniform(160, 300)) / sp
    h = Hazard("hl_roll", sx, sy, ROLL_R, life=T, dmg=ROLL_DMG, vx=math.cos(a) * sp, vy=math.sin(a) * sp)
    h.hit, h.age = set(), 0.0
    st.rolls.append(h)
    game.burst(sx, sy, (150, 140, 120), 14, 140, 5, 0.9, layer="over")


def _roll(game, st, dt):
    over = game.over
    alive = game.alive_players("over")
    S = game.world_size
    for h in list(st.rolls):
        h.age += dt
        h.x += h.vx * dt
        h.y += h.vy * dt
        h.t -= dt
        sp = math.hypot(h.vx, h.vy) or 1.0
        ux, uy = h.vx / sp, h.vy / sp
        stop = h.t <= 0
        fx, fy = h.x + ux * h.r, h.y + uy * h.r
        if not stop and h.age > 0.35:
            if not (60 < fx < S - 60 and 60 < fy < S - 60) or game.terrain_blocked(fx, fy, "over"):
                stop = True
            else:
                for s in arcade.get_sprites_at_point((fx, fy), over.solid):
                    if s in game.structs.values():
                        game.damage_structure(s, 30)
                    stop = True
                    break
        for p in alive:
            if p.id not in h.hit and _dist(p.pos, (h.x, h.y)) < h.r + 16:
                h.hit.add(p.id)
                game.hurt_player(p, h.dmg)
                game.say("Flattened by a rolling boulder!", 1.5, to=p)
                game.burst(p.pos[0], p.pos[1], (150, 140, 120), 10, 160, 4, 0.6, layer="over")
        for z in list(over.zombies):
            if ("z", z.zid) not in h.hit and _dist(z.position, (h.x, h.y)) < h.r + z.radius:
                h.hit.add(("z", z.zid))
                game.hit_enemy(z, 12, None, ux, uy)
        for a in list(over.animals):
            if ("a", a.aid) not in h.hit and _dist(a.position, (h.x, h.y)) < h.r + 16:
                h.hit.add(("a", a.aid))
                game.hit_animal(a, 6, None, ux, uy)
        if stop:
            st.rolls.remove(h)
            _settle(game, st, h)
    for h in st.rolls:           # keep them in the hazard snapshot (the hazard loop drops unknown kinds each frame)
        h.done = False
        if h not in game.hazards:
            game.hazards.append(h)


def _settle(game, st, h):
    """A rolling boulder stops: it stays as a mineable boulder (from the pool) if there's room, else it shatters."""
    h.done = True
    if h in game.hazards:
        game.hazards.remove(h)
    x, y = h.x, h.y
    L = game.over
    game.fx_layer = "over"
    n = next((q for q in st.pool if q.state == "gone"), None)
    ok = n is not None and 100 < x < game.world_size - 100 and 100 < y < game.world_size - 100
    ok = ok and not game.in_base((x, y), "over", pad=40) and not game.terrain_blocked(x, y, "over") \
        and not game.terrain_water(x, y, "over") and all(_dist(p.pos, (x, y)) > 50 for p in game.players.values())
    if ok:           # room for it? (back up along its path a little if it stopped against something)
        sp = math.hypot(h.vx, h.vy) or 1.0
        lists = [L.solid, L.builds, L.huts, L.exits, L.ponds, L.traps, L.bushes]
        ok = False
        for k in range(8):
            px, py = x - h.vx / sp * 12 * k, y - h.vy / sp * 12 * k
            probe = arcade.SpriteSolidColor(50, 50, center_x=px, center_y=py)
            if not arcade.check_for_collision_with_lists(probe, lists) and not game.terrain_blocked(px, py, "over"):
                ok, x, y = True, px, py
                break
    if ok:
        game.place_node(n, x, y, n.variant)
        n.hp = NODES["boulder"]["hp"]
        n.timer = 0.0
        game.set_node_state(n, "full")
        game.nodes_ver += 1
        game.burst(x, y, (150, 140, 120), 12, 110, 5, 0.8, layer="over")
        game.play("mine", 0.3, at=(x, y), layer="over")
    else:
        game.burst(x, y, (140, 136, 126), 20, 200, 5, 0.7, layer="over")
        game.ring(x, y, 10, 60, 0.35, (170, 160, 140), layer="over")
        game.play("boom", 0.25, at=(x, y), layer="over")


_prev_fix_queue = base.Base.fix_respawn_queue


def _fix_respawn_queue(self):
    """After loading, base.py queues every "gone" node to grow back - but the quake pool stays out of the world."""
    _prev_fix_queue(self)
    st = _state(self)
    if st is not None:
        self.regrow[:] = [it for it in self.regrow if id(it[1]) not in st.pool_ids]


base.Base.fix_respawn_queue = _fix_respawn_queue


# =========================================================================== every computer
def player_tick(game, p, dt):
    """The highland wind: a little chill by day (the sun wins), more at night."""
    return 0.2 + 0.5 * game.darkness


def ambient(game, dt, x, y):
    st = _state(game)
    if st is None:
        return
    me = game.me
    if not st.told and me and me.alive and me.layer == "over" and game.state == "playing" and \
            game.biome_at(me.pos) == NAME:
        st.told = True
        game.message, game.message_t = ("THE STONE HIGHLANDS: boulders, iron, heather, goats. "
                                        "When the ground shakes, dodge the rolling rocks!", 7)
    st.trail_t -= dt
    if st.trail_t <= 0:
        st.trail_t = 0.06
        for h in game.hazards:
            if h.kind == "hl_roll":
                game._burst(h.x - h.vx * 0.08, h.y - h.vy * 0.08, (150, 140, 122), 2, 50, 5, 0.7, "over")


def draw3d(game, L, vl, stage="props"):
    if stage != "props":
        return
    if vl != "over":
        return
    st = _state(game)
    if st is None:
        return
    game.mesh(st.ledges, "hl_ledge")
    game.mesh(st.stones, "menhir")
    rolls = [h for h in game.hazards if h.kind == "hl_roll"]
    lst = st.roll_list
    while len(lst) < len(rolls):
        s = arcade.Sprite(art_highlands.boulder(len(lst)))
        s.scale = 0.78
        lst.append(s)
    while len(lst) > len(rolls):
        lst.pop()
    for s, h in zip(lst, rolls):
        s.position = (h.x, h.y)
        s.angle = (h.x + h.y) * 0.9 % 360         # tumbling
    if rolls:
        game.mesh(lst, "boulder")


def debug_spot(game):
    """A good screenshot spot: next to the first plateau's ramp (tools / tests)."""
    ps = plateaus(game.layout)
    if not ps:
        return game.layout.centres[NAME]
    for p in ps:
        for a in p.ramps:
            r = p.radius(a)
            q = (p.x + math.cos(a) * (r + RAMP_LEN + 60), p.y + math.sin(a) * (r + RAMP_LEN + 60))
            if game.biome_at(q) == NAME:
                return q
    return game.layout.centres[NAME]


def _ground(rng, x, y):
    return art_highlands.ground(rng.choice((0, 0, 1, 1, 2, 3)))


def _decor(rng, x, y):
    return art_highlands.decor(rng.randint(0, 5))


biomes.register(biomes.Biome(
    NAME, title="The Stone Highlands", order=40,
    tint=(232, 232, 224),
    density={"tree": 0.22, "bush": 0.25, "pond": 0.5, "hive": 0.2, "decor": 1.0, "rock": 1.0, "iron": 1.0},
    node_kinds=("boulder", "heather"),
    animals={"goat": 7, "rabbit": 2, "deer": 1, "boar": 1, "wolf": 3, "bee": 0},
    fog=(170, 175, 185, 18),
    gen_surface=gen_surface, ground=_ground, decor=_decor, keepout=keepout, respawn_variant=_respawn,
    update=update, player_tick=player_tick, ambient=ambient, height=height, blocked=blocked, draw3d=draw3d,
))
