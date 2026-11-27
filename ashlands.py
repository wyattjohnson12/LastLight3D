"""
ashlands.py - THE ASHLANDS: the volcanic region of the big map, home of the Inferno Colossus.

What's here (worldgen 2 maps only - old saves never see any of it):
  * Black ash and basalt ground, cinders and old bones, charred dead trees, basalt boulders.
  * LAVA CRACKS glowing in the ground (and lighting up the night). Standing on one burns you, and you keep
    burning for a moment after you step off. Armor and potions don't help - only fire-proof gear does.
    In the middle of the region (layout.centres["ash"]) the Colossus's caldera: a lava pool ringed by
    obsidian spires and vents.
  * Smoking VENTS (mine them with a pickaxe for Sulfur), OBSIDIAN spires (iron pickaxe only), coal and
    iron seams, and charred trees that crumble into coal.
  * FIRE BEETLES: neutral, armoured bugs. Crowd them or hit them and they bite - and the bite sets you on
    fire. They drop Beetle Shell and Embers.
  * ASH STORMS roll in every so often (the same moment on every computer, worked out from the seed and the
    clock): the air turns orange-grey and thick, ash pours down, and breathing it slowly drains your energy
    and health - unless you wear a Mire Mask or the Ember Crown.
  * New gear: EMBER CROWN (head) and OBSIDIAN PLATE (body), made from the Inferno Colossus's Ember Hearts -
    the best armor in the game, and fire-proof (each piece halves lava / burning, both together = immune).
    Sulfur Fire Pots (sulfur + ember + stone = 3 fire pots, crafted anywhere).

Co-op / determinism: everything on the map is built from gen.rng (every computer builds the same Ashlands),
hazard damage runs on the host (player_tick / update), and the looks (particles, storm haze, glows) are
worked out locally from the shared world + the synced clock. Art: art_ash.py. 3D shapes: registered into
shapes3d.SHAPES at the bottom of this file. Beetle 3D model: tools/blender/models_ash.py.
"""
import math
import random

import art
import art_ash
import base
import biomes
import shapes3d
from settings import *
from world import Node

NAME = "ash"

# =========================================================================== tuning
LAVA_DPS = 14.0              # standing on a lava crack (armor doesn't help; fire-proof gear does)
BURN_SECONDS = 1.6           # ...and you keep burning this long after stepping off
BURN_DPS = 5.0
BITE_BURN = 2.5              # a fire beetle's bite sets you burning this long
STORM_SLOT = DAY_CYCLE_SECONDS / 3   # the sky is checked for an ash storm every slot of game clock
STORM_CHANCE = 0.42          # chance a slot has a storm (it fills the middle 60% of the slot)
STORM_ENERGY = 1.8           # per second, breathing ash without a mask
STORM_HEALTH = 0.7
STORM_SPEED = 0.88           # walking into the storm without a mask
HEAT = -0.9                  # the ground is warm (negative cold per second)
BEETLE_SPACE = 70            # fire beetles bite anyone who crowds them this close
BASE_FOG = (96, 50, 30, 34)
STORM_FOG = (132, 102, 84, 165)

# =========================================================================== items, nodes, recipes, creatures
ITEMS.update({
    "obsidian": {"name": "Obsidian", "kind": "material",
                 "desc": "Black volcanic glass from the Ashlands' spires. Only an IRON pickaxe can break it."},
    "sulfur": {"name": "Sulfur", "kind": "material",
               "desc": "Yellow crust from the Ashlands' smoking vents (pickaxe). Makes fire pots."},
    "ember": {"name": "Ember", "kind": "material",
              "desc": "A coal that never goes out. Dropped by Fire Beetles. Fire pots and the Ember Crown."},
    "beetle_shell": {"name": "Beetle Shell", "kind": "material",
                     "desc": "Heat-proof shell plate from a Fire Beetle. Obsidian Plate is built on it."},
    "ember_crown": {"name": "Ember Crown", "kind": "armor", "slot": "head", "armor": 6, "warmth": 2, "toxin": 1,
                    "ashproof": 1, "fireproof": 0.5,
                    "desc": "Armor 6, warmth 2 - the best helmet. Filters ash storms and spore gas, and halves lava "
                            "and burning damage (with Obsidian Plate: immune)."},
    "obsidian_plate": {"name": "Obsidian Plate", "kind": "armor", "slot": "body", "armor": 15, "warmth": 4,
                       "fireproof": 0.5,
                       "desc": "Armor 15, warmth 4 - the best armor there is. Halves lava and burning damage "
                               "(with the Ember Crown: immune)."},
})
NODES.update({
    "obsidian": {"gives": "obsidian", "hp": 10, "regrow": 240, "needs": "iron_pickaxe"},
    "vent": {"gives": "sulfur", "hp": 8, "regrow": 200, "needs": "pickaxe"},
    "charred_tree": {"gives": "coal", "hp": 4, "regrow": 150},
    "ash_coal": {"gives": "coal", "hp": 6, "regrow": 160, "needs": "pickaxe"},
    "ash_iron": {"gives": "iron_ore", "hp": 8, "regrow": 200, "needs": "pickaxe"},
})
ASH_KINDS = ("obsidian", "vent", "charred_tree", "ash_coal", "ash_iron")
ITEMS["pickaxe"]["harvest"].update({"vent": 1, "ash_coal": 1, "ash_iron": 1})
ITEMS["iron_pickaxe"]["harvest"].update({"vent": 2, "ash_coal": 2, "ash_iron": 2, "obsidian": 1})
ITEMS["axe"]["harvest"]["charred_tree"] = 2
ITEMS["iron_axe"]["harvest"]["charred_tree"] = 2
base.NODE_RADIUS.update({"obsidian": 30, "vent": 30, "charred_tree": 30, "ash_coal": 34, "ash_iron": 34})
# the old "best" gear makes way for the Colossus armor
for _k, _old, _new in (("mire_mask", " (the best helmet)", ""),
                       ("chitin_armor", " The best body armor.", " Only Obsidian Plate is better.")):
    if _k in ITEMS:
        ITEMS[_k]["desc"] = ITEMS[_k]["desc"].replace(_old, _new)

ANIMALS["fire_beetle"] = {"hp": 14, "speed": 95, "temper": "defend", "drops": {"beetle_shell": 1, "ember": 2},
                          "tame": None, "chance": 0, "job": None, "dmg": 8,
                          "desc": "Fire Beetle: armoured, neutral - until you crowd it. Its bite burns."}
for _b in ("forest", "mire"):              # wildlife tables that say nothing about beetles default to 2:
    if _b in biomes.BIOMES and biomes.BIOMES[_b].animals is not None:     # beetles live in the ash only
        biomes.BIOMES[_b].animals.setdefault("fire_beetle", 0)

CRAFT_TABS["Armor"].append(R("ember_crown", {"obsidian": 3, "ember_heart": 1, "ember": 4, "iron_ingot": 2}, "workbench"))
CRAFT_TABS["Armor"].append(R("obsidian_plate", {"obsidian": 6, "ember_heart": 1, "beetle_shell": 4, "iron_ingot": 3},
                             "workbench"))
CRAFT_TABS["Supplies"].append(R("fire_pot", {"sulfur": 1, "ember": 1, "stone": 1}, n=3))
RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]   # same list object, crafting indexes in tab order


# =========================================================================== the ash storm (same on every computer)
_SEED = biomes.seed_int(0, "ashstorm")


def storm_k(game):
    """0..1: how hard the ash storm is blowing right now. A pure function of the seed and the (synced) clock."""
    if getattr(game, "worldgen", 1) == biomes.LEGACY or not hasattr(game, "clock"):
        return 0.0
    s = game.clock / STORM_SLOT
    i = int(math.floor(s))
    if biomes._h(biomes.seed_int(game.seed, "ashstorm"), i, 7) >= STORM_CHANCE or i < 1:
        return 0.0
    f = s - i
    return max(0.0, min(1.0, min(f - 0.2, 0.8 - f) / 0.08))


def masked(p):
    return bool(p.gear("toxin") or p.gear("ashproof"))


def fireproof(p):
    return min(1.0, p.gear("fireproof"))


# =========================================================================== lava lookup (pure, every computer)
_CELL = 128


def _add_seg(game, a, b, hw):
    grid = game.ash_lava
    x0, x1 = min(a[0], b[0]) - hw - 16, max(a[0], b[0]) + hw + 16
    y0, y1 = min(a[1], b[1]) - hw - 16, max(a[1], b[1]) + hw + 16
    for gx in range(int(x0 // _CELL), int(x1 // _CELL) + 1):
        for gy in range(int(y0 // _CELL), int(y1 // _CELL) + 1):
            grid.setdefault((gx, gy), []).append((a, b, hw))


def in_lava(game, pos, pad=4.0):
    """Is pos on a lava crack or in the caldera's pool?"""
    if getattr(game, "worldgen", 1) == biomes.LEGACY:
        return False
    x, y = pos
    for px, py, rx, ry in getattr(game, "ash_pools", ()):
        if ((x - px) / rx) ** 2 + ((y - py) / ry) ** 2 < 1:
            return True
    for (ax, ay), (bx, by), hw in getattr(game, "ash_lava", {}).get((int(x // _CELL), int(y // _CELL)), ()):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        if math.hypot(x - ax - dx * t, y - ay - dy * t) < hw + pad:
            return True
    return False


# =========================================================================== generation (worldgen 2)
def gen_surface(gen):
    rng, over, game = gen.rng, gen.over, gen.game
    for b in biomes.BIOMES.values():       # every biome registered by now: no beetles outside the ash
        if b.animals is not None:
            b.animals.setdefault("fire_beetle", 0)
    game.ash_lava, game.ash_pools, game.ash_glows, game.ash_vents = {}, [], [], []
    game.ash_cracks = []                   # (x, y) of every crack (embers rise from them)
    game.ash_told = game.ash_storm_told = False
    game.ash_fx_t = 0.0
    centre = gen.layout.centres[NAME]
    lava_spots = []                        # (x, y, r): keep nodes off the lava

    def clear(p, rad):
        return gen.free(p, rad) and all(math.hypot(p[0] - x, p[1] - y) > rad + r for x, y, r in lava_spots)

    # the shared rocks out here are basalt
    for n in over.rocks:
        if n.kind == "rock" and gen.biome_at(n.position) == NAME:
            n.texture = art_ash.basalt(n.idx % 4)

    def crack(p, v):
        s = _sprite(art_ash.crack(v), p)
        over.ground.append(s)
        g = _sprite(art.glow(80, (255, 110, 40)), p)
        over.glows.append(g)
        for a, b, hw in art_ash.CRACKS[v]:
            _add_seg(game, (p[0] + a[0], p[1] + a[1]), (p[0] + b[0], p[1] + b[1]), hw)
        game.ash_cracks.append(p)
        lava_spots.append((p[0], p[1], 82))

    # the Colossus's caldera: a lava pool, spires and vents around it, cracks running out of it
    cx, cy = centre
    pool_ok = gen.free(centre, 150, gap=0)
    if pool_ok:
        over.ground.append(_sprite(art_ash.lava_pool(), centre))
        over.glows.append(_sprite(art.glow(200, (255, 100, 30)), centre))
        w, h = art_ash.POOL_SIZE
        game.ash_pools.append((cx, cy, (w - 70) / 2, (h - 64) / 2))
        lava_spots.append((cx, cy, 160))
        for k in range(6):
            a = k / 6 * math.tau + rng.uniform(-0.3, 0.3)
            p = (cx + math.cos(a) * 240, cy + math.sin(a) * 190)
            if gen.free(p, 70, gap=0):
                crack(p, rng.randint(0, 7))
    lair = []
    for k in range(11):
        a = k / 11 * math.tau + rng.uniform(-0.15, 0.15)
        d = rng.uniform(330, 400)
        lair.append(("obsidian" if k % 3 else "vent", (cx + math.cos(a) * d, cy + math.sin(a) * d)))

    # lava cracks all over the region
    placed = 0
    for _ in range(900):
        if placed >= 120:
            break
        p = gen.spot(NAME, margin=140)
        if p and gen.free(p, 60, gap=0) and all(math.hypot(p[0] - x, p[1] - y) > 150 for x, y, _ in lava_spots):
            crack(p, rng.randint(0, 7))
            placed += 1

    def add(kind, tex, p):
        n = gen.add_node(Node(kind, tex, *p), over.rocks)
        if kind == "vent":
            g = _sprite(art.glow(46, (255, 130, 40)), p)
            over.glows.append(g)
            game.ash_glows.append((n, g))
            game.ash_vents.append(n)
        return n

    for kind, p in lair:
        if clear(p, 34):
            add(kind, art_ash.obsidian(rng.randint(0, 2)) if kind == "obsidian" else art_ash.vent(rng.randint(0, 2)), p)
    looks = {"obsidian": lambda: art_ash.obsidian(rng.randint(0, 2)), "vent": lambda: art_ash.vent(rng.randint(0, 2)),
             "charred_tree": lambda: art_ash.charred_tree(rng.randint(0, 2)),
             "ash_coal": lambda: art_ash.ash_ore("coal"), "ash_iron": lambda: art_ash.ash_ore("iron")}
    for kind, count, rad in (("charred_tree", 80, 40), ("vent", 32, 40), ("ash_coal", 34, 36),
                             ("ash_iron", 22, 36), ("obsidian", 26, 36)):
        placed = 0
        for _ in range(count * 8):
            if placed >= count:
                break
            p = gen.spot(NAME, margin=120)
            if p and clear(p, rad):
                n = add(kind, looks[kind](), p)
                if kind == "charred_tree":
                    n.angle = n.base_angle = rng.uniform(0, 360)
                placed += 1


def _sprite(tex, p):
    import arcade
    return arcade.Sprite(tex, center_x=p[0], center_y=p[1])


def _ground(rng, x, y):
    return art_ash.ground(rng.randint(0, 2))


def _decor(rng, x, y):
    roll = rng.random()
    return False if roll < 0.2 else art_ash.decor(rng.randint(0, 3))


# =========================================================================== survivors (host / solo)
def player_tick(game, p, dt):
    """Lava burns, ash storms choke. Returns warmth (negative cold): the ground is hot."""
    if getattr(game, "worldgen", 1) == biomes.LEGACY or getattr(p, "arriving", False):
        return 0.0
    fp = fireproof(p)
    burn = getattr(p, "ash_burn", 0.0)
    if p.in_hut is None and in_lava(game, p.pos):
        if fp < 1:
            p.health -= LAVA_DPS * (1 - fp) * dt
            p.hurt = max(p.hurt, 0.2)
            p.ash_burn = BURN_SECONDS
            p.ash_snd = getattr(p, "ash_snd", 0.0) - dt
            if p.ash_snd <= 0:
                p.ash_snd = 0.6
                game.play("hurt", 0.25, at=p.pos, layer="over")
                game.rumble(0.5, 0.12, to=p)
            if not getattr(p, "ash_lava_told", False):
                p.ash_lava_told = True
                game.say("LAVA! It burns straight through armor - get off the glowing cracks!", 3.5, to=p)
    elif burn > 0:
        p.ash_burn = burn - dt
        p.health -= BURN_DPS * (1 - fp) * dt
    k = storm_k(game)
    if k > 0 and not masked(p) and p.in_hut is None:
        p.energy = max(0.0, p.energy - STORM_ENERGY * k * dt)
        p.health -= STORM_HEALTH * k * dt
        if not getattr(p, "ash_storm_told", False):
            p.ash_storm_told = True
            game.say("ASH STORM! The air is choking you - wear a Mire Mask or an Ember Crown, or shelter in a hut.",
                     5, to=p)
    if not getattr(p, "ash_told", False):
        p.ash_told = True
        game.say("THE ASHLANDS: don't stand on lava. Iron pickaxe for obsidian, pickaxe for vents (sulfur). "
                 "Fire Beetles bite if crowded.", 6, to=p)
    return HEAT


def _speed(game, p):
    k = storm_k(game)
    return 1.0 - (1.0 - STORM_SPEED) * k if k > 0 and not masked(p) else 1.0


def update(game, dt):
    """Host / solo: fire beetles guard their space, and their bites set you on fire."""
    alive = [p for p in game.alive_players("over") if game.biome_at(p.pos) == NAME]
    if not alive:
        return
    for a in game.over.animals:
        if a.kind != "fire_beetle" or a.pet:
            continue
        near = min(alive, key=lambda q: math.hypot(q.pos[0] - a.center_x, q.pos[1] - a.center_y))
        d = math.hypot(near.pos[0] - a.center_x, near.pos[1] - a.center_y)
        if d < BEETLE_SPACE and (a.aggro is None or a.aggro_t <= 0):
            a.aggro, a.aggro_t = near.id, 5.0
            game.burst(a.center_x, a.center_y, (255, 140, 50), 6, 90, 3, 0.5, layer="over")
        tgt = game.players.get(a.aggro) if a.aggro is not None and a.aggro_t > 0 else None
        if tgt is not None and a.attack_cd > 1.2 - 2.5 * dt and \
                math.hypot(tgt.pos[0] - a.center_x, tgt.pos[1] - a.center_y) < 40 and fireproof(tgt) < 1:
            tgt.ash_burn = max(getattr(tgt, "ash_burn", 0.0), BITE_BURN * (1 - fireproof(tgt)))
            game.burst(tgt.sprite.center_x, tgt.sprite.center_y, (255, 120, 30), 10, 120, 3, 0.6, layer="over")


# =========================================================================== looks (every computer)
def ambient(game, dt, x, y):
    """Falling ash, vent smoke, embers over the cracks, the storm, and flames on you when you burn."""
    if getattr(game, "worldgen", 1) == biomes.LEGACY or not hasattr(game, "ash_glows"):
        return
    for n, g in game.ash_glows:          # vent glows follow their vent (respawns move it) and go out when mined
        g.visible = n.state == "full"
        if g.center_x != n.center_x or g.center_y != n.center_y:
            g.position = n.position
    k = storm_k(game)
    if game.state == "playing" and game.me and game.me.alive:
        if not game.ash_told:
            game.ash_told = True
            game.message, game.message_t = ("THE ASHLANDS - home of the Inferno Colossus. Lava cracks burn through "
                                            "any armor. Obsidian, sulfur vents, coal and iron out here.", 6)
        if k > 0.3 and not game.ash_storm_told:
            game.ash_storm_told = True
            game.message, game.message_t = ("An ASH STORM is rolling in! Mire Mask / Ember Crown, or get to a hut.", 5)
        elif k <= 0:
            game.ash_storm_told = False
    if not hasattr(game, "_fx_pool"):
        return
    rnd = random.random
    spawn = game.fx_spawn
    near = lambda px, py, r: abs(px - x) < r and abs(py - y) < r * 0.9

    def count(rate):
        return int(rate * dt + rnd())

    # ash flakes drifting down around the viewer (a blizzard of it in a storm)
    for _ in range(count(26 + 150 * k)):
        a, d = rnd() * math.tau, 40 + rnd() * (520 - 200 * k)
        spawn("over", x + math.cos(a) * d, y + math.sin(a) * d, 60 + rnd() * 160, (rnd() - 0.3) * 40 + 90 * k,
              (rnd() - 0.5) * 30 + 30 * k, -30 - rnd() * 30, 2.0 + rnd() * 1.5, 1.6 + rnd() * 1.6,
              (150, 142, 136) if rnd() < 0.8 else (90, 84, 80), 0.75, 0, 0.2, 0)
    if k > 0.2:      # thick billows of ash close to the ground
        for _ in range(count(14 * k)):
            a, d = rnd() * math.tau, 60 + rnd() * 340
            spawn("over", x + math.cos(a) * d, y + math.sin(a) * d, 10 + rnd() * 50, 70 + rnd() * 50, 20 + rnd() * 20,
                  4 + rnd() * 8, 2.4 + rnd(), 16 + rnd() * 12, (128, 110, 96), 0.28 * k, 0, 0.2, 10)
    # vents: a column of smoke and the odd spray of sparks
    for n in game.ash_vents:
        if n.state != "full" or not near(n.center_x, n.center_y, 900):
            continue
        for _ in range(count(3.2)):
            spawn("over", n.center_x + (rnd() - 0.5) * 8, n.center_y + (rnd() - 0.5) * 8, 28, (rnd() - 0.5) * 12 + 14 * k,
                  (rnd() - 0.5) * 12, 34 + rnd() * 26, 2.6 + rnd() * 1.4, 7 + rnd() * 4, (70, 64, 62), 0.38, -4, 0.25, 12)
        for _ in range(count(1.6)):
            spawn("over", n.center_x, n.center_y, 26, (rnd() - 0.5) * 50, (rnd() - 0.5) * 50, 80 + rnd() * 70,
                  0.8 + rnd() * 0.6, 1.4 + rnd(), (255, 150 + int(rnd() * 70), 50), 1.0, 90, 0.4, 0, True)
    # embers rising off the lava cracks
    for cx, cy in game.ash_cracks:
        if near(cx, cy, 700):
            for _ in range(count(1.1)):
                spawn("over", cx + (rnd() - 0.5) * 90, cy + (rnd() - 0.5) * 90, 3, (rnd() - 0.5) * 16, (rnd() - 0.5) * 16,
                      30 + rnd() * 40, 1.0 + rnd() * 0.8, 1.3 + rnd(), (255, 120 + int(rnd() * 80), 40), 1.0, -6, 0.5,
                      0, True)
    for px, py, rx, ry in game.ash_pools:
        if near(px, py, 900):
            for _ in range(count(9)):
                a, d = rnd() * math.tau, math.sqrt(rnd())
                spawn("over", px + math.cos(a) * rx * d, py + math.sin(a) * ry * d, 4, 0, 0, 40 + rnd() * 50,
                      0.6 + rnd() * 0.5, 2 + rnd() * 3, (255, 130 + int(rnd() * 80), 40), 0.9, 0, 0.5, -2, True)
    # you're on fire
    for p in game.players.values():
        if p.alive and p.layer == "over" and near(p.sprite.center_x, p.sprite.center_y, 900) and \
                (in_lava(game, p.pos) or getattr(p, "ash_burn", 0) > 0) and fireproof(p) < 1:
            for _ in range(count(18)):
                spawn("over", p.sprite.center_x + (rnd() - 0.5) * 18, p.sprite.center_y - 3, 6 + rnd() * 26, 0, 0,
                      55 + rnd() * 30, 0.35 + rnd() * 0.2, 4 + rnd() * 3, (255, 120, 30), 0.6, 0, 0, -8, True)


class AshBiome(biomes.Biome):
    """The Ashlands' haze thickens into an orange-grey wall while an ash storm blows."""

    game = None

    @property
    def fog(self):
        k = storm_k(AshBiome.game) if AshBiome.game is not None else 0.0
        if k <= 0:
            return self._fog
        return tuple(int(a + (b - a) * k) for a, b in zip(self._fog, STORM_FOG))

    @fog.setter
    def fog(self, v):
        self._fog = v


def _gen(gen):
    AshBiome.game = gen.game
    gen_surface(gen)


biomes.register(AshBiome(
    NAME, title="The Ashlands", order=30,
    tint=(206, 196, 188),
    density={"tree": 0.0, "bush": 0.0, "pond": 0.0, "hive": 0.0, "decor": 0.9, "rock": 0.7, "iron": 1.0},
    node_kinds=ASH_KINDS, forbid=("tree", "bush", "reeds", "glowcap"),
    animals={"fire_beetle": 9, "rabbit": 1, "deer": 0, "boar": 1, "wolf": 1, "bee": 0},
    fog=BASE_FOG,
    gen_surface=_gen, ground=_ground, decor=_decor, player_tick=player_tick, speed=_speed, update=update,
    ambient=ambient,
))


# =========================================================================== 3D shapes (shapes3d.SHAPES)
def _register_shapes():
    S3 = shapes3d
    if hasattr(S3, "Part"):          # the part-based shape system (see the how-to at the top of shapes3d.py)
        P, tube, ball, cone, disc = S3.Part, S3.tube, S3.ball, S3.cone, S3.disc
        S3.SHAPES["obsidian"] = S3.crystal_cluster(n=5, height=2.7, seed=31, spread=0.42, sides=5)
        crater = [(1.0, 0.0, 0.95, 0.62), (0.86, 0.42, 0.86, 0.82), (0.58, 1.0, 0.62, 0.98), (0.42, 1.16, 0.44, 1.06),
                  (0.32, 1.02, 0.32, 0.8), (0.24, 0.78, 0.2, 0.7)]
        S3.SHAPES["vent"] = S3.Shape([
            P(crater, sides=9, jitter=0.14),
            P(disc(0.26, z=0.86), color=(255, 132, 40), glow=1.0, sides=8),                 # the molten throat
            P(ball(2), at=(0.55, 0.3, 0.12), size=(0.24, 0.2, 0.16), color=(214, 196, 70), sides=5, jitter=0.2),
            P(ball(2), at=(-0.45, -0.5, 0.1), size=(0.2, 0.18, 0.14), color=(190, 170, 60), sides=5, jitter=0.2),
        ], foot=(0.9, 0.9), cut=0.2)
        rnd = random.Random(41)
        bark, height = (42, 36, 34), 2.5
        parts = [P(tube(0.19, 0.07, height, shade=(0.6, 0.9)), color=bark, sides=6, jitter=0.12),
                 P(cone(0.32, 0.5), color=_mix(bark, 0.85), sides=6, jitter=0.3)]           # root flare
        for i in range(5):
            a = i / 5 * math.tau + rnd.uniform(-0.3, 0.3)
            z = height * rnd.uniform(0.45, 0.82)
            lean = rnd.uniform(0.75, 1.15)
            ln = rnd.uniform(0.7, 1.0)
            parts.append(P(tube(0.075, 0.025, ln), at=(0, 0, z), tilt=math.cos(a) * lean, roll=math.sin(a) * lean,
                           color=bark, sides=4))
            ex, ey = math.cos(a) * ln * math.sin(lean), math.sin(a) * ln * math.sin(lean)
            b = a + rnd.choice((-0.6, 0.6))
            parts.append(P(tube(0.035, 0.01, ln * 0.6), at=(ex, ey, z + ln * math.cos(lean) * 0.9),
                           tilt=math.cos(b) * 0.5, roll=math.sin(b) * 0.5, color=bark, sides=3))
        for i in range(3):                         # embers still glowing in the burnt bark
            a = i * 2.1
            parts.append(P(ball(2), at=(math.cos(a) * 0.13, math.sin(a) * 0.13, 0.5 + i * 0.45),
                           size=(0.05, 0.05, 0.09), color=(255, 110, 40), glow=1.0, sides=4))
        S3.SHAPES["charred_tree"] = S3.Shape(parts, foot=(0.9, 0.9), cut=0.2)
    else:                            # the ring-stack shape system
        Sh = S3.Shape
        S3.SHAPES["obsidian"] = Sh([(1.0, 0.0, 0.9, 0.55), (0.86, 0.4, 0.76, 0.8), (0.56, 0.85, 0.55, 1.0),
                                    (0.42, 1.4, 0.42, 1.18), (0.2, 2.2, 0.24, 1.32), (0.0, 2.85, 0.0, 1.5)],
                                   foot=(0.85, 0.85), segs=5, phase=0.3, jitter=0.38, cut=0.2)
        S3.SHAPES["vent"] = Sh([(1.0, 0.0, 0.95, 0.62), (0.86, 0.42, 0.86, 0.82), (0.58, 1.0, 0.62, 0.98),
                                (0.42, 1.16, 0.44, 1.06), (0.32, 1.02, 0.32, 1.2), (0.2, 0.8, 0.18, 1.35),
                                (0.0, 0.76, 0.0, 1.45)], foot=(0.9, 0.9), segs=9, jitter=0.14, cut=0.2)
        # a bare burnt trunk: root flare, a knotted, gnarled bole and a broken, split top (plain charcoal)
        S3.SHAPES["charred_tree"] = Sh([(0.36, 0.0, 0, -0.5), (0.2, 0.3, 0, -0.62), (0.17, 1.0, 0, -0.75),
                                        (0.2, 1.25, 0, -0.8), (0.13, 1.5, 0, -0.85), (0.1, 2.1, 0, -0.9),
                                        (0.15, 2.3, 0, -0.95), (0.04, 2.65, 0, -1.0)],
                                       foot=(0.9, 0.9), segs=6, solid=(42, 36, 34), jitter=0.32, cut=0.2)
    S3.SHAPES["ash_coal"] = S3.SHAPES["ash_iron"] = S3.SHAPES["rock"]


def _mix(c, f):
    return tuple(int(v * f) for v in c)


_register_shapes()
