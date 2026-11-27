"""
explore.py - places to discover out in the world, their loot, and recipes you learn by finding them.

There are no quests and no markers. Out in the wilds lie small abandoned places - a cold camp, a ruined
watchtower, a trapper's hut, a miner's camp (also underground), a survivor's grave, and one kind of place
special to each harsh biome (an ice-locked cache in the tundra, an obsidian shrine in the Ashlands, a sunken
boat in the Mire). Each has one container to search (E / controller B) with a one-time loot roll: richer
the further it is from the spawn and in the harsher biomes. Some places are guarded (zombies hiding in the
shade burst out when you open it, wolves come back to their trapper's hut, a golem guards the cave camp).

Recipe discovery: the recipes in LOCKED_ORDER (mid-tier gear and defences - never the basics you need for
the first nights) are unknown at the start. Notes, manuals and blueprints in the places teach them, and every
locked recipe is put in at least MIN_COPIES places of every world (by construction, from the seed). A recipe
that can't be placed twice (a crowded map) simply starts known. Known recipes are shared by the whole team.

Saves & co-op:
  * Places are generated from the seed on every computer (gen_surface / gen_layers, own random streams per
    place type), and they add NO nodes, so they never move anyone else's node indices.
  * The host decides: opening, loot, what is learned. The state ("st" event: opened / found / known) goes to
    everyone whenever it changes and to each new player when they join. Saved under "biomes"["explore"].
  * Saves without that field (older versions, or a world from before this module) know every recipe, so
    nothing an old save could craft is ever taken away. Legacy (worldgen 1) worlds have no places and know
    every recipe too.

=====================================================================================================
HOW TO ADD A NEW KIND OF PLACE
=====================================================================================================
1. Paint any new pictures in art_explore.py (square, opaque - they get draped over 3D shapes).
2. Register 3D shapes for the new prop kinds in SHAPES below (shapes3d.py's guide; units are R = half the
   sprite's side; x = forward, y = left, z = up), and give each prop kind a picture + size in PROP_ART.
3. Append a PlaceType to TYPES (append only, so older worlds' places keep their ids):

       PlaceType("cart", "a crashed supply cart", "crashed carts", "A torn shipping list",
                 where=[("meadow", 2), ("forest", 1)], radius=90,
                 props=[Prop("ex_cart", -20, 10, solid=(80, 40)), Prop("rock", 40, -30, tex="rock:1")],
                 box=("ex_crate", "ex_crate_open", 30, -10), patch="dirt",
                 loot=[("wood", 4, 9, 3), ("arrows", 5, 12, 2)], rare=[("iron_sword", 1, 1, 1)],
                 teaches=("arrow_turret",), guards={"zombies": (0, 2)})

   `where` lists (biome, how many per world); "cave" puts them underground. Props are (kind, x, y) in px
   around the centre (the whole place is turned to a random angle), `solid=(w, h)` makes an invisible
   blocker. `teaches` are the locked recipes its notes may hold. `guards`: {"zombies": (lo, hi)},
   {"wolves": (lo, hi)}, {"golems": (lo, hi)} - lo at the spawn, up to lo + hi at the far edge.
4. A new locked recipe: add its item to LOCKED_ORDER and to at least one type's `teaches`.
=====================================================================================================
"""
import math
import random

import arcade

import art
import art_explore as AE
import biomes
import shapes3d as S3
from settings import *
from world import Animal, dist

NAME = "explore"
SPAWN_CLEAR = 430          # no place closer than this to the spawn
LAIR_CLEAR = 560           # ...or to a region's centre (where boss lairs go)
SPACING = 400              # between two places
OPEN_RANGE = 92            # how close you must stand to search a container
FIND_RANGE = 300           # walk this close and the place counts as found
COPIES, MIN_COPIES = 3, 2  # every locked recipe is put in COPIES places (at least MIN_COPIES, or it starts known)
HARSH = {"tundra": 0.15, "ash": 0.2, "highlands": 0.12, "mire": 0.15, "cave": 0.2}

# mid-tier recipes you have to find (order is fixed: it picks which places hold them)
LOCKED_ORDER = ["iron_pickaxe", "iron_sword", "iron_helmet", "iron_armor", "bow", "bear_trap", "arrow_turret",
                "iron_wall", "brazier", "medkit"]


# =========================================================================== data
class Prop:
    def __init__(self, kind, x, y, rot=0.0, solid=None, tex=None, size=None):
        self.kind, self.x, self.y, self.rot, self.solid, self.tex, self.size = kind, x, y, rot, solid, tex, size


class PlaceType:
    def __init__(self, key, title, plural, note, where, radius, props, box, loot, rare=(), teaches=(),
                 guards=None, patch=None, patch_size=230, glows=(), cave_props=None, box_name="chest",
                 min_dist=SPAWN_CLEAR, near_pool=False):
        self.key, self.title, self.plural, self.note = key, title, plural, note
        self.where, self.radius, self.props, self.box = list(where), radius, list(props), box
        self.loot, self.rare, self.teaches = list(loot), list(rare), tuple(teaches)
        self.guards = dict(guards or {})
        self.patch, self.patch_size, self.glows = patch, patch_size, list(glows)
        self.cave_props = cave_props          # props used instead underground (None = the same)
        self.box_name, self.min_dist, self.near_pool = box_name, min_dist, near_pool


TYPES = [
    PlaceType("camp", "an abandoned camp", "abandoned camps", "A torn journal",
              where=[("forest", 2), ("meadow", 2), ("tundra", 1), ("mire", 1)], radius=100,
              props=[Prop("ex_tent", -40, 32, 20, solid=(70, 56)), Prop("ex_firepit", 38, -6, solid=(28, 28)),
                     Prop("ex_log", 62, 40, 70, solid=(14, 40)), Prop("ex_flag", -84, -42, solid=(8, 8))],
              box=("ex_chest", "ex_chest_open", -6, -56), patch="dirt",
              loot=[("berries", 2, 5, 3), ("cooked_meat", 1, 2, 2), ("water", 1, 2, 2), ("fiber", 3, 8, 3),
                    ("wood", 4, 10, 2), ("bandage", 1, 2, 2), ("leather", 1, 3, 1), ("arrows", 4, 10, 1)],
              rare=[("leather_cap", 1, 1, 2), ("leather_tunic", 1, 1, 2), ("honey_salve", 1, 2, 2),
                    ("spear", 1, 1, 1), ("bow", 1, 1, 1)],
              teaches=("bow", "arrow_turret", "medkit"), guards={"zombies": (0, 2)}),
    PlaceType("tower", "a ruined watchtower", "ruined watchtowers", "A soldier's field manual",
              where=[("meadow", 2), ("highlands", 2), ("forest", 1)], radius=120,
              props=[Prop("ex_tower", -34, 28, solid=(92, 92)), Prop("rock", 64, 44, tex="rock:1", solid=(22, 22)),
                     Prop("rock", 40, -70, 40, tex="rock:3", solid=(22, 22)),
                     Prop("ex_pillar", 92, -8, solid=(20, 20)), Prop("ex_wallruin", 8, 98, 8, solid=(76, 18)),
                     Prop("rock", -96, -52, tex="rock:0", solid=(22, 22))],
              box=("ex_chest", "ex_chest_open", 32, -14), patch="flagstone", patch_size=300,
              loot=[("stone", 6, 12, 2), ("arrows", 6, 14, 3), ("iron_ingot", 1, 3, 2), ("iron_ore", 2, 5, 2),
                    ("leather", 1, 3, 1), ("bandage", 1, 2, 2), ("wood", 4, 8, 1)],
              rare=[("iron_helmet", 1, 1, 2), ("iron_sword", 1, 1, 2), ("iron_armor", 1, 1, 1), ("bow", 1, 1, 1),
                    ("fire_pot", 2, 4, 2), ("medkit", 1, 1, 1)],
              teaches=("iron_sword", "iron_helmet", "iron_armor", "arrow_turret", "iron_wall"),
              guards={"zombies": (1, 3)}),
    PlaceType("hut", "a trapper's hut", "trappers' huts", "A trapper's notebook",
              where=[("forest", 2), ("tundra", 2), ("mire", 1)], radius=112,
              props=[Prop("ex_cabin", -22, 30, solid=(92, 76)), Prop("ex_rack", 64, 52, solid=(12, 44)),
                     Prop("ex_woodpile", -88, -24, solid=(40, 40))],
              box=("ex_chest", "ex_chest_open", 42, -30), patch="dirt",
              loot=[("hide", 2, 5, 3), ("fur", 1, 4, 2), ("leather", 2, 4, 2), ("meat", 2, 4, 2),
                    ("cooked_meat", 1, 3, 1), ("fiber", 3, 6, 2), ("arrows", 5, 12, 2)],
              rare=[("fur_cloak", 1, 1, 2), ("bow", 1, 1, 2), ("bear_trap", 1, 2, 2), ("pet_leather_armor", 1, 1, 1),
                    ("leather_tunic", 1, 1, 1)],
              teaches=("bear_trap", "bow"), guards={"wolves": (1, 2)}),
    PlaceType("mine", "a miner's camp", "miners' camps", "Miner's notes",
              where=[("highlands", 2), ("ash", 1), ("cave", 3)], radius=110,
              props=[Prop("ex_headframe", -30, 22, solid=(64, 64)), Prop("ex_minecart", 46, 22, 30, solid=(40, 30)),
                     Prop("iron", -62, -56, tex="ore:iron", solid=(22, 22)),
                     Prop("iron", 8, -72, 50, tex="ore:iron", solid=(22, 22)),
                     Prop("lantern", -80, 44, tex="icon:lantern", solid=(12, 12))],
              cave_props=[Prop("ex_support", -36, 18, solid=(14, 70)), Prop("ex_minecart", 40, 30, 30, solid=(40, 30)),
                          Prop("iron", -64, -50, tex="ore:iron", solid=(22, 22)),
                          Prop("lantern", -70, 46, tex="icon:lantern", solid=(12, 12))],
              box=("ex_crate", "ex_crate_open", 54, -40), patch="gravel", box_name="crate",
              glows=[(-62, 46, 150, (255, 196, 120), 0.75)],
              loot=[("iron_ore", 3, 7, 3), ("coal", 3, 6, 3), ("iron_ingot", 1, 3, 2), ("stone", 6, 12, 1),
                    ("torch", 1, 2, 1)],
              rare=[("crystal", 1, 2, 3), ("iron_pickaxe", 1, 1, 1), ("starstone", 1, 2, 1), ("medkit", 1, 1, 1)],
              teaches=("iron_pickaxe", "brazier", "iron_wall"), guards={"zombies": (1, 2), "golems": (1, 1)}),
    PlaceType("grave", "a survivor's grave", "graves", "A note in the dead survivor's hand",
              where=[("forest", 2), ("meadow", 1), ("tundra", 1), ("highlands", 1), ("ash", 1), ("mire", 1)],
              radius=64, min_dist=360,
              props=[Prop("ex_mound", 0, 0, solid=(62, 34), size=80), Prop("ex_cross", -48, 0, solid=(10, 10), size=24),
                     Prop("rock", -36, 36, tex="rock:2", size=34)],
              box=("ex_pack", "ex_pack_open", 26, -32), patch="mud", patch_size=140, box_name="backpack",
              loot=[("berries", 2, 4, 2), ("bandage", 1, 2, 3), ("fiber", 2, 5, 2), ("torch", 1, 1, 1),
                    ("water", 1, 1, 2)],
              rare=[("iron_sword", 1, 1, 1), ("medkit", 1, 1, 2), ("honey", 1, 2, 2), ("leather_cap", 1, 1, 1)],
              teaches=("medkit", "iron_sword", "iron_pickaxe"), guards={"zombies": (0, 1.4)}),
    PlaceType("ice", "an ice-locked cache", "ice-locked caches", "A frozen letter",
              where=[("tundra", 2)], radius=96,
              props=[Prop("ex_icespike", 52, 30, solid=(26, 26)), Prop("ex_icespike", -48, 40, 60, solid=(26, 26)),
                     Prop("ex_icespike", -20, -58, 120, solid=(26, 26)), Prop("ex_flag", 72, -42, solid=(8, 8)),
                     Prop("ex_firepit", -74, -10, solid=(28, 28))],
              box=("ex_icechest", "ex_chest_open", 0, 0), patch="frost", box_name="frozen chest",
              glows=[(0, 0, 120, (150, 210, 255), 0.35)],
              loot=[("clear_ice", 2, 4, 2), ("whitewood", 3, 6, 2), ("snow_pelt", 1, 3, 2), ("fur", 2, 4, 2),
                    ("coal", 2, 4, 2), ("cooked_meat", 1, 3, 1)],
              rare=[("frost_shard", 1, 1, 1), ("fur_cloak", 1, 1, 2), ("snowfox_hood", 1, 1, 1),
                    ("iron_armor", 1, 1, 1), ("crystal", 1, 2, 2)],
              teaches=("iron_armor", "medkit"), guards={"zombies": (1, 2)}),
    PlaceType("shrine", "an obsidian shrine", "obsidian shrines", "Runes on an obsidian tablet",
              where=[("ash", 2)], radius=104,
              props=[Prop("ex_obelisk", -62, 44, solid=(26, 18)), Prop("ex_obelisk", 62, 44, solid=(26, 18)),
                     Prop("ex_altar", 0, 34, solid=(54, 36))],
              box=("ex_urn", "ex_urn_open", 0, -26), patch="scorch", patch_size=270, box_name="urn",
              glows=[(0, 34, 170, (255, 110, 40), 0.9)],
              loot=[("obsidian", 1, 3, 2), ("ember", 2, 4, 2), ("sulfur", 2, 4, 2), ("coal", 3, 5, 2),
                    ("iron_ingot", 1, 3, 2)],
              rare=[("crystal", 1, 3, 2), ("fire_pot", 3, 5, 2), ("medkit", 1, 1, 1), ("starstone", 1, 2, 1)],
              teaches=("brazier", "iron_helmet"), guards={"zombies": (1, 3)}),
    PlaceType("boat", "a sunken boat", "sunken boats", "A waterlogged logbook",
              where=[("mire", 2)], radius=110, near_pool=True,
              props=[Prop("ex_boat", 0, 28, 15, solid=(90, 40)), Prop("ex_post", -74, -30, solid=(10, 10)),
                     Prop("ex_post", 78, -40, solid=(10, 10))],
              box=("ex_chest", "ex_chest_open", -26, -42), patch="mud",
              loot=[("reeds", 3, 6, 2), ("glowcap", 1, 3, 2), ("raw_fish", 1, 3, 2), ("fiber", 3, 6, 1),
                    ("leather", 1, 3, 1), ("iron_ingot", 1, 2, 1), ("arrows", 5, 10, 1)],
              rare=[("swamp_tonic", 1, 2, 2), ("mire_mask", 1, 1, 1), ("fishing_rod", 1, 1, 1),
                    ("iron_helmet", 1, 1, 1), ("crystal", 1, 1, 1)],
              teaches=("bear_trap", "iron_helmet"), guards={"zombies": (1, 2)}),
]
TYPE = {t.key: t for t in TYPES}


# =========================================================================== 3D shapes (shapes3d.py guide)
_P = S3.Part
_K = math.sqrt(2)
Q = math.pi / 4
WOOD, WOOD_D, IRON, STONE, DARK = (120, 84, 50), (84, 60, 38), (66, 64, 62), (134, 128, 118), (26, 22, 20)


def _box(hx, hy, z0, z1, col, at=(0.0, 0.0, 0.0), tilt=0.0, roll=0.0, glow=0.0, sway=0.0, shade=(0.62, 0.95)):
    """An axis-lined box (shapes with turn=Q): half sizes hx, hy, from z0 to z1 (R units). col None = draped."""
    rings = [(0.0, z0, 0.0, shade[0]), (1.0, z0, 1.0, shade[0]), (1.0, z1, 1.0, shade[1]), (0.0, z1, 0.0, shade[1])]
    return _P(rings, at=at, size=(hx * _K, hy * _K, 1.0), tilt=tilt, roll=roll, color=col, sides=4, glow=glow,
              sway=sway)


def _log(r, length, at, yaw=0.0, col=WOOD_D, sides=6):
    """A lying log / beam through `at`, pointing along `yaw` (0 = forward, pi/2 = left)."""
    return _P(S3.tube(r, r, length, z0=-length / 2, caps=True), at=at, roll=math.pi / 2, tilt=math.pi / 2 - yaw,
              color=col, sides=sides)


def _post(r, h, at, col=WOOD, tilt=0.0, roll=0.0, sides=5):
    return _P(S3.tube(r, r * 0.9, h, caps=True), at=at, color=col, sides=sides, tilt=tilt, roll=roll)


def _shapes():
    sh = {}
    chest_body = [_box(0.72, 0.48, 0.0, 0.62, WOOD), _box(0.08, 0.52, 0.0, 0.66, IRON, at=(0.42, 0, 0)),
                  _box(0.08, 0.52, 0.0, 0.66, IRON, at=(-0.42, 0, 0))]
    sh["ex_chest"] = S3.Shape(chest_body + [
        _box(0.76, 0.52, 0.62, 0.88, None), _box(0.09, 0.54, 0.6, 0.92, IRON, at=(0.42, 0, 0)),
        _box(0.09, 0.54, 0.6, 0.92, IRON, at=(-0.42, 0, 0)),
        _box(0.05, 0.09, 0.42, 0.66, (230, 186, 80), at=(0.76, 0, 0), glow=0.35)], foot=(1, 1), turn=Q, cut=0.1)
    t = -1.75
    sh["ex_chest_open"] = S3.Shape(chest_body + [
        _box(0.66, 0.42, 0.56, 0.6, (34, 24, 16)),
        _box(0.75, 0.51, -0.12, 0.12, None, at=(-0.72 + 0.75 * math.cos(t), 0, 0.62 - 0.75 * math.sin(t)), tilt=t)],
        foot=(1, 1), turn=Q, cut=0.1)
    crate = [_box(0.72, 0.72, 0.0, 1.25, (132, 94, 56)), _box(0.75, 0.75, 0.22, 0.32, WOOD_D),
             _box(0.75, 0.75, 0.9, 1.0, WOOD_D)]
    sh["ex_crate"] = S3.Shape(crate + [_box(0.75, 0.75, 1.25, 1.34, None)], foot=(1, 1), turn=Q, cut=0.1)
    sh["ex_crate_open"] = S3.Shape(crate + [_box(0.66, 0.66, 1.18, 1.22, (30, 22, 16)),
                                            _box(0.06, 0.72, -0.7, 0.7, None, at=(0.98, 0, 0.7), tilt=-0.32)],
                                   foot=(1, 1), turn=Q, cut=0.1)
    sack = (112, 82, 52)
    sh["ex_pack"] = S3.Shape([_P(S3.ball(4), at=(0, 0, 0.6), size=(0.85, 0.66, 0.6), color=sack, sides=8, jitter=0.1),
                              _P(S3.ball(3), at=(0.18, 0, 1.08), size=(0.62, 0.56, 0.2), color=(94, 68, 42), sides=7),
                              _P(S3.tube(0.12, 0.12, 0.9, caps=True), at=(-0.5, 0.3, 0.15), tilt=0.5, color=(70, 52, 34),
                                 sides=4)], foot=(1, 1), cut=0.1)
    sh["ex_pack_open"] = S3.Shape([_P(S3.ball(3), at=(0, 0, 0.18), size=(0.95, 0.75, 0.22), color=sack, sides=8,
                                      jitter=0.2),
                                   _P(S3.ball(3), at=(0.95, 0.2, 0.06), size=(0.5, 0.5, 0.08), color=(94, 68, 42),
                                      sides=6)], foot=(1, 1), cut=0.1)
    clay = (96, 52, 36)
    urn = [(0.0, 0.0, 0, 0.6), (0.5, 0.0, 0.5, 0.6), (0.85, 0.5, 0.8, 0.8), (0.9, 0.82, 0.85, 0.95),
           (0.6, 1.25, 0.55, 1.0), (0.36, 1.45, 0.34, 1.0), (0.48, 1.6, 0.45, 1.05), (0.0, 1.56, 0.0, 0.5)]
    sh["ex_urn"] = S3.Shape([_P(urn, color=clay, sides=9),
                             _P(S3.tube(0.92, 0.89, 0.14, z0=0.66), color=(255, 130, 50), sides=9, glow=0.7)],
                            foot=(1, 1), cut=0.1)
    sh["ex_urn_open"] = S3.Shape([_P(urn[:4] + [(0.8, 0.86, 0.75, 0.6)], color=clay, sides=9, jitter=0.3),
                                  _P(S3.ball(2), at=(1.1, 0.3, 0.06), size=(0.3, 0.2, 0.1), color=clay, sides=4),
                                  _P(S3.ball(2), at=(-0.9, 0.7, 0.06), size=(0.25, 0.3, 0.1), color=clay, sides=4)],
                                 foot=(1, 1), cut=0.1)
    ice = (190, 226, 248)
    sh["ex_icechest"] = S3.Shape([_box(0.95, 0.75, 0.0, 1.12, ice, glow=0.12, shade=(0.8, 1.05)),
                                  _box(0.76, 0.52, 1.12, 1.16, (150, 110, 70)),
                                  _P(S3.cone(0.26, 1.0, z0=0.9), at=(0.5, 0.35, 0), tilt=0.35, color=ice, sides=5, glow=0.2),
                                  _P(S3.cone(0.22, 0.8, z0=0.9), at=(-0.45, -0.3, 0), roll=0.4, color=ice, sides=5,
                                     glow=0.2),
                                  _P(S3.cone(0.3, 1.2, z0=0.0), at=(0.95, -0.7, 0), tilt=0.3, roll=-0.3, color=ice,
                                     sides=5, glow=0.2)], foot=(1, 1), turn=Q, cut=0.1)
    # torn ridge tent: a three-sided prism lying along x (tilt -90 deg turns the tube's axis to -x, vertex up)
    sh["ex_tent"] = S3.Shape([_P(S3.tube(0.78, 0.78, 1.7, z0=-0.85), at=(0, 0, 0.39), tilt=-math.pi / 2, sides=3),
                              _P(S3.tube(0.035, 0.035, 2.0, z0=-1.0), at=(0, 0, 1.17), tilt=-math.pi / 2, color=WOOD,
                                 sides=4),
                              _P(S3.tube(0.04, 0.04, 1.2, caps=True), at=(0.92, 0, 0), color=WOOD, sides=4)],
                             foot=(1, 1), cut=0.35)
    sh["ex_firepit"] = S3.Shape([_P([(1.0, 0.0, 0.98, 0.7), (1.0, 0.12, 0.98, 0.9), (0.8, 0.22, 0.8, 1.0),
                                     (0.55, 0.08, 0.55, 0.8), (0.0, 0.05, 0.0, 0.7)], sides=12, jitter=0.12),
                                 _log(0.09, 0.95, (0, 0, 0.15), 0.3, (36, 30, 28)),
                                 _log(0.08, 0.85, (0.05, 0.05, 0.22), 1.5, (44, 34, 30)),
                                 _log(0.09, 0.8, (-0.05, 0, 0.17), 2.6, (30, 26, 24))], foot=(1, 1), cut=0.1)
    sh["ex_log"] = S3.Shape([_log(0.3, 1.85, (0, 0, 0.3), 0.0, (96, 70, 46), 7),
                             _post(0.12, 0.5, (0.3, 0.2, 0.45), (84, 64, 42), tilt=0.6)], foot=(1, 1), cut=0.1)
    sh["ex_flag"] = S3.Shape([_post(0.14, 11.0, (0, 0, 0), (104, 76, 48), sides=5),
                              _box(0.85, 0.05, -0.7, 0.7, (156, 54, 42), at=(0.9, 0, 10.0), sway=0.1),
                              _box(0.4, 0.05, -0.5, 0.3, (130, 46, 36), at=(1.3, 0, 8.9), sway=0.12)],
                             foot=(1, 1), turn=Q, cut=0.1)
    tower = [_P([(1.0, 0.0, 1.0, 0.58), (0.97, 1.5, 0.97, 0.78), (0.93, 2.9, 0.93, 0.95)], color=STONE, sides=10,
                jitter=0.06),
             _P([(0.93, 2.9, 0.93, 0.95), (0.8, 2.94, 0.8, 1.0), (0.0, 2.94, 0.0, 1.0)], sides=10),
             _box(0.06, 0.22, 0.0, 0.8, DARK, at=(0.98, 0, 0)), _box(0.06, 0.06, 1.7, 2.05, DARK, at=(0, -0.97, 0)),
             _box(0.06, 0.06, 1.2, 1.55, DARK, at=(-0.97, 0, 0))]
    for k, h in enumerate((0.45, 0.3, 0.0, 0.5, 0.38, 0.0, 0.22, 0.42)):
        if h:
            a = k * math.tau / 8 + 0.2
            tower.append(_box(0.15, 0.15, 2.88, 2.9 + h, (142, 136, 126), at=(0.84 * math.cos(a), 0.84 * math.sin(a), 0)))
    sh["ex_tower"] = S3.Shape(tower, foot=(1, 1), turn=Q, cut=0.1)
    sh["ex_pillar"] = S3.Shape([_box(0.85, 0.85, 0.0, 0.28, (120, 116, 108)),
                                _P(S3.tube(0.62, 0.55, 2.3, z0=0.28, caps=True), color=(152, 146, 134), sides=8, jitter=0.12)],
                               foot=(1, 1), turn=Q, cut=0.1)
    sh["ex_wallruin"] = S3.Shape([_box(0.95, 0.22, 0.0, 1.0, STONE), _box(0.38, 0.22, 1.0, 1.36, STONE, at=(-0.55, 0, 0)),
                                  _box(0.2, 0.22, 1.0, 1.18, STONE, at=(0.2, 0, 0)),
                                  _box(0.2, 0.2, 0.0, 0.25, (110, 106, 98), at=(0.8, 0.6, 0))],
                                 foot=(1, 1), turn=Q, cut=0.1)
    logs = (112, 80, 52)
    sh["ex_cabin"] = S3.Shape([_box(0.78, 0.64, 0.0, 0.95, logs),
                               _box(0.8, 0.66, 0.3, 0.36, (84, 60, 40)), _box(0.8, 0.66, 0.62, 0.68, (84, 60, 40)),
                               _P([(1.0, 0.92, 1.0, 0.95), (0.0, 1.62, 0.0, 1.12)], size=(0.96 * _K, 0.82 * _K, 1.0), sides=4),
                               _P(S3.tube(0.13, 0.12, 1.85, caps=True), at=(-0.5, 0.38, 0), color=(122, 118, 110), sides=6),
                               _box(0.03, 0.17, 0.0, 0.62, (46, 34, 24), at=(0.79, 0.22, 0)),
                               _box(0.03, 0.13, 0.42, 0.68, (40, 44, 52), at=(0.79, -0.34, 0))],
                              foot=(1, 1), turn=Q, cut=0.1)
    sh["ex_rack"] = S3.Shape([_post(0.07, 1.75, (0, 0.8, 0)), _post(0.07, 1.75, (0, -0.8, 0)),
                              _log(0.05, 1.8, (0, 0, 1.66), math.pi / 2, WOOD),
                              _box(0.03, 0.32, 0.55, 1.62, (152, 112, 78), at=(0, -0.38, 0)),
                              _box(0.03, 0.28, 0.75, 1.62, (128, 92, 64), at=(0, 0.4, 0))],
                             foot=(1, 1), turn=Q, cut=0.1)
    bark = (100, 72, 46)
    sh["ex_woodpile"] = S3.Shape([_log(0.21, 1.6, (x, 0, z), math.pi / 2, bark if k % 2 else (112, 82, 52), 6)
                                  for k, (x, z) in enumerate(((-0.42, 0.21), (0, 0.21), (0.42, 0.21), (-0.21, 0.56),
                                                              (0.21, 0.56), (0, 0.9)))], foot=(1, 1), cut=0.1)
    frame = []
    for y in (0.75, -0.75):
        frame.append(_post(0.08, 3.13, (-0.9, y, 0), tilt=0.29, sides=5))
        frame.append(_post(0.08, 3.13, (0.9, y, 0), tilt=-0.29, sides=5))
    sh["ex_headframe"] = S3.Shape(frame + [
        _log(0.08, 1.8, (0, 0, 2.95), math.pi / 2, WOOD_D),
        _P(S3.tube(0.55, 0.55, 0.08, z0=-0.04, caps=True), at=(0, 0, 3.25), roll=math.pi / 2, color=(70, 52, 36), sides=10),
        _box(0.62, 0.62, 0.0, 0.26, (92, 68, 44)), _box(0.48, 0.48, 0.26, 0.28, (12, 10, 10))],
        foot=(1, 1), turn=Q, cut=0.1)
    sh["ex_support"] = S3.Shape([_post(0.1, 2.1, (0, 0.82, 0), sides=6), _post(0.1, 2.1, (0, -0.82, 0), sides=6),
                                 _log(0.1, 2.0, (0, 0, 2.08), math.pi / 2, WOOD_D)], foot=(1, 1), cut=0.1)
    sh["ex_minecart"] = S3.Shape([
        _P([(0.0, 0.28, 0.0, 0.6), (0.8, 0.28, 0.8, 0.62), (1.0, 1.0, 1.0, 0.9), (0.0, 1.0, 0.0, 0.9)],
           size=(0.9 * _K, 0.62 * _K, 1.0), color=(86, 84, 88), sides=4),
        _P([(0.9, 0.98, 0.9, 0.9), (0.6, 1.3, 0.6, 1.0), (0.0, 1.44, 0.0, 1.05)], size=(0.82, 0.55, 1.0), sides=8,
           jitter=0.2)] + [
        _P(S3.tube(0.22, 0.22, 0.08, z0=-0.04, caps=True), at=(x, y, 0.22), roll=math.pi / 2, color=(40, 38, 38), sides=8)
        for x in (-0.55, 0.55) for y in (-0.64, 0.64)], foot=(1, 1), turn=Q, cut=0.1)
    sh["ex_mound"] = S3.Shape([_P([(1.0, 0.0, 1.0, 0.7), (0.88, 0.2, 0.88, 0.85), (0.55, 0.4, 0.55, 1.0),
                                   (0.0, 0.46, 0.0, 1.05)], size=(1.0, 0.56, 1.0), sides=10, jitter=0.08)],
                              foot=(1, 1), cut=0.1)
    sh["ex_cross"] = S3.Shape([_post(0.18, 6.2, (0, 0, 0), (112, 94, 72), tilt=0.06, sides=4),
                               _log(0.15, 3.2, (0.27, 0, 4.6), math.pi / 2, (112, 94, 72), 4)], foot=(1, 1), cut=0.1)
    sh["ex_obelisk"] = S3.Shape([_P([(1.0, 0.0, 0.9, 0.58), (1.02, 1.4, 0.9, 0.74), (0.85, 3.6, 0.8, 0.9),
                                     (0.5, 4.6, 0.45, 1.0), (0.0, 5.0, 0.0, 1.06)], size=(0.7, 0.45, 1.0), sides=6,
                                    jitter=0.08),
                                 _P(S3.tube(1.03, 0.99, 0.16, z0=2.3), size=(0.7, 0.45, 1.0), color=(255, 120, 40), sides=6,
                                    glow=0.85),
                                 _P(S3.tube(0.9, 0.86, 0.12, z0=3.3), size=(0.7, 0.45, 1.0), color=(255, 120, 40), sides=6,
                                    glow=0.85)], foot=(1, 1), cut=0.1)
    sh["ex_altar"] = S3.Shape([_box(0.85, 0.55, 0.0, 0.75, None), _box(0.95, 0.65, 0.75, 0.9, (60, 52, 58)),
                               _P(S3.dome(0.32, 0.22, z0=0.9), color=(255, 110, 40), sides=8, glow=0.9)],
                              foot=(1, 1), turn=Q, cut=0.1)
    hull = [(0.0, 0.0, 0.0, 0.5), (0.6, 0.05, 0.6, 0.6), (0.9, 0.3, 0.9, 0.8), (1.0, 0.62, 1.0, 0.95)]
    sh["ex_boat"] = S3.Shape([_P(hull, at=(0, 0, -0.12), size=(1.0, 0.42, 1.0), tilt=0.22, color=(92, 66, 42), sides=12),
                              _P(S3.disc(0.84, z=0.26), at=(0, 0, -0.12), size=(1.0, 0.38, 1.0), tilt=0.22,
                                 color=(58, 70, 50), sides=12),
                              _P(S3.tube(1.0, 1.0, 0.07, z0=0.58), at=(0, 0, -0.12), size=(1.0, 0.42, 1.0), tilt=0.22,
                                 color=(70, 50, 32), sides=12),
                              _post(0.06, 1.7, (0.12, 0, 0.05), tilt=0.55)], foot=(1, 1), cut=0.1)
    sh["ex_post"] = S3.Shape([_P(S3.tube(0.5, 0.42, 4.4, caps=True), color=(72, 58, 44), sides=6, jitter=0.15)],
                             foot=(1, 1), cut=0.1)
    sh["ex_icespike"] = S3.crystal_cluster(n=4, height=2.3, color=(180, 226, 252), glow=0.22, seed=41)
    return sh


S3.SHAPES.update(_shapes())

# prop kind -> (picture maker, sprite size in px)
PROP_ART = {
    "ex_chest": (lambda: AE.planks("chest", 44, (128, 88, 50), bands=(70, 66, 62), rows=4), 44),
    "ex_chest_open": (lambda: AE.planks("chest", 44, (128, 88, 50), bands=(70, 66, 62), rows=4), 44),
    "ex_crate": (lambda: AE.planks("crate", 40, (150, 110, 66), rows=4, seed=1), 40),
    "ex_crate_open": (lambda: AE.planks("crate", 40, (150, 110, 66), rows=4, seed=1), 40),
    "ex_pack": (lambda: AE.plain("leather", (112, 82, 52)), 32),
    "ex_pack_open": (lambda: AE.plain("leather", (112, 82, 52)), 32),
    "ex_urn": (lambda: AE.plain("clay", (96, 52, 36)), 32),
    "ex_urn_open": (lambda: AE.plain("clay", (96, 52, 36)), 32),
    "ex_icechest": (lambda: AE.plain("ice", (190, 226, 248)), 44),
    "ex_tent": (lambda: AE.canvas("tent", 96, (176, 160, 122)), 96),
    "ex_firepit": (AE.ash_pit, 52),
    "ex_log": (lambda: AE.plain("bark", (96, 70, 46)), 40),
    "ex_flag": (lambda: AE.plain("pole", (104, 76, 48), 20), 20),
    "ex_tower": (lambda: AE.stone("tower", 120), 120),
    "ex_pillar": (lambda: AE.stone("pale", 32, (152, 146, 134), seed=1), 28),
    "ex_wallruin": (lambda: AE.stone("tower", 120), 80),
    "ex_cabin": (lambda: AE.planks("roof", 112, (92, 76, 54), rows=8, seed=2), 112),
    "ex_rack": (lambda: AE.plain("hide", (152, 112, 78)), 48),
    "ex_woodpile": (lambda: AE.plain("bark", (96, 70, 46)), 44),
    "ex_headframe": (lambda: AE.plain("pole", (104, 76, 48), 20), 80),
    "ex_support": (lambda: AE.plain("pole", (104, 76, 48), 20), 80),
    "ex_minecart": (AE.ore_heap, 44),
    "ex_mound": (lambda: AE.dirt("mound"), 60),
    "ex_cross": (lambda: AE.plain("pole", (104, 76, 48), 20), 20),
    "ex_obelisk": (AE.obsidian, 44),
    "ex_altar": (lambda: AE.stone("dark", 60, (70, 62, 66), moss=False, seed=2), 60),
    "ex_boat": (lambda: AE.planks("boat", 100, (92, 66, 42), rows=6, seed=3), 100),
    "ex_post": (lambda: AE.plain("bark", (96, 70, 46)), 16),
    "ex_icespike": (lambda: AE.plain("ice", (190, 226, 248)), 48),
    "rock": (None, 70), "iron": (None, 66), "lantern": (None, 40),
}


def _texture(prop):
    """The picture for a prop (tex "rock:2" / "ore:iron" / "icon:lantern" reuse the game's own art)."""
    if prop.tex:
        what, arg = prop.tex.split(":")
        if what == "rock":
            return art.rock(int(arg))
        if what == "ore":
            import art_extra
            return art_extra.ore(arg)
        if what == "icon":
            return art.icon(arg)
    return PROP_ART[prop.kind][0]()


# =========================================================================== runtime state
class Place:
    def __init__(self, ptype, idx, x, y, layer, angle, tier, biome):
        self.type, self.pid = ptype, f"{ptype.key}:{idx}"
        self.x, self.y, self.layer, self.angle, self.tier, self.biome = x, y, layer, angle, tier, biome
        self.notes = []          # locked recipes its notes teach
        self.opened = False
        self.found = False
        self.box = None          # the container sprite

    @property
    def pos(self):
        return (self.x, self.y)


class State:
    def __init__(self, nodes):
        self.nodes = nodes                  # which world this belongs to (game.nodes is new for every world)
        self.places = []
        self.by_id = {}
        self.lists = {}                     # layer -> {shape kind: SpriteList}
        self.patches = {}                   # layer -> SpriteList of flat ground patches
        self.locked = set()                 # recipes this world gates behind discovery
        self.known = set()                  # ...of which the team has found these
        self.where = {}                     # recipe -> place type keys that hold it (the crafting hint)
        self.guards = []                    # zombies that hide in the shade by day
        self.seen_players = set()
        self.tick = 0.0


def _st(game):
    st = getattr(game, "_explore", None)
    return st if st is not None and st.nodes is game.nodes else None


def _rot(dx, dy, a):
    c, s = math.cos(a), math.sin(a)
    return dx * c - dy * s, dx * s + dy * c


def _sprite(st, layer, kind, tex, x, y, angle, size):
    s = arcade.Sprite(tex, center_x=x, center_y=y)
    s.scale = size / max(1, tex.width)
    s.angle = angle
    s.kind = kind
    st.lists.setdefault(layer, {}).setdefault(kind, arcade.SpriteList()).append(s)
    return s


def _build(gen, st, pl):
    """Put a place's props, blockers, ground patch and lights into the world."""
    L = gen.layers[pl.layer]
    t = pl.type
    a = pl.angle
    deg = -math.degrees(a)               # arcade angles turn clockwise
    if t.patch:
        g = arcade.Sprite(AE.patch(t.patch), center_x=pl.x, center_y=pl.y)
        g.scale = t.patch_size / g.texture.width
        g.angle = (pl.x * 7 + pl.y * 13) % 360
        g.depth = 3.0           # a hair over the ground, so gentle hills under it don't swallow its middle
        st.patches.setdefault(pl.layer, arcade.SpriteList()).append(g)
    props = t.cave_props if (pl.layer != "over" and t.cave_props) else t.props
    for pr in props:
        dx, dy = _rot(pr.x, pr.y, a)
        x, y = pl.x + dx, pl.y + dy
        size = pr.size or PROP_ART[pr.kind][1]
        _sprite(st, pl.layer, pr.kind, _texture(pr), x, y, deg - pr.rot, size)
        if pr.solid:
            b = arcade.SpriteSolidColor(int(pr.solid[0]), int(pr.solid[1]), center_x=x, center_y=y,
                                        color=(0, 0, 0, 0))
            b.angle = deg - pr.rot
            b.kind = "ex_blocker"
            L.solid.append(b)
    closed, opened, bx, by = t.box
    dx, dy = _rot(bx, by, a)
    x, y = pl.x + dx, pl.y + dy
    pl.box = _sprite(st, pl.layer, closed, _texture(Prop(closed, 0, 0)), x, y, deg + 90, PROP_ART[closed][1])
    b = arcade.SpriteSolidColor(26, 26, center_x=x, center_y=y, color=(0, 0, 0, 0))
    b.kind = "ex_blocker"
    L.solid.append(b)
    for gx, gy, r, col, k in t.glows:
        dx, dy = _rot(gx, gy, a)
        g = arcade.Sprite(AE.glow(r, col), center_x=pl.x + dx, center_y=pl.y + dy)
        g.light = (col[0] / 255, col[1] / 255, col[2] / 255, k)
        L.glows.append(g)


def _set_opened(st, pl, opened):
    """Swap a container between its closed and opened look (every computer)."""
    if pl.opened == opened or pl.box is None:
        pl.opened = opened
        return
    pl.opened = opened
    closed, open_kind = pl.type.box[0], pl.type.box[1]
    kind = open_kind if opened else closed
    s = pl.box
    s.remove_from_sprite_lists()
    s.kind = kind
    tex = _texture(Prop(kind, 0, 0))
    s.texture = tex
    s.scale = PROP_ART[kind][1] / max(1, tex.width)
    st.lists.setdefault(pl.layer, {}).setdefault(kind, arcade.SpriteList()).append(s)


# =========================================================================== generation (every computer)
def _tier(layout, x, y, biome):
    d = math.hypot(x - layout.centre[0], y - layout.centre[1])
    return max(0.0, min(1.0, (d - 400) / 2000 + HARSH.get(biome, 0.0)))


def _footprint(t, layer, angle):
    """[(dx, dy, r), ...]: the spots a place's solid props and its container need clear (turned by angle)."""
    props = t.cave_props if (layer != "over" and t.cave_props) else t.props
    out = [(0.0, 0.0, 70.0 if layer == "over" else 40.0)]      # a clearing in the middle
    for pr in props:
        if pr.solid:
            dx, dy = _rot(pr.x, pr.y, angle)
            out.append((dx, dy, max(pr.solid) / 2 + 6))
    dx, dy = _rot(t.box[2], t.box[3], angle)
    out.append((dx, dy, 30.0))
    return out


def _surface_ok(gen, st, t, p, angle, rng, pool=True):
    x, y = p
    lay = gen.layout
    d = math.hypot(x - lay.centre[0], y - lay.centre[1])
    if d < t.min_dist:
        return False
    if rng.random() > min(1.0, 0.22 + (d - t.min_dist) / 1300):      # fewer close to the spawn
        return False
    for name, c in lay.centres.items():
        if name != "forest" and math.hypot(x - c[0], y - c[1]) < LAIR_CLEAR:
            return False
    if any(pl.layer == "over" and math.hypot(x - pl.x, y - pl.y) < SPACING for pl in st.places):
        return False
    # trees and rocks may stand around a place (it's been abandoned a while), but never on its props
    L = gen.over
    for dx, dy, rr in _footprint(t, "over", angle):
        q = (x + dx, y + dy)
        if not gen.free(q, rr, gap=10):
            return False
        probe = arcade.SpriteSolidColor(int(2 * rr), int(2 * rr), center_x=q[0], center_y=q[1])
        if arcade.check_for_collision_with_lists(probe, [L.solid, L.huts, L.exits, L.ponds]):
            return False        # highland ledges / standing stones, other places' blockers
    game = gen.game
    r = t.radius
    bog = getattr(game, "in_bog_pool", None)
    step = 16                   # rivers, roads, cliffs, bog pools: keep the whole place clear of them
    k = int(r // step) + 1
    for i in range(-k, k + 1):
        for j in range(-k, k + 1):
            if (i * i + j * j) * step * step > (r + 10) ** 2:
                continue
            qx, qy = x + i * step, y + j * step
            if biomes.keepout(lay, qx, qy) or game.terrain_blocked(qx, qy) or game.terrain_water(qx, qy):
                return False
            if bog is not None and bog((qx, qy)):
                return False
    if pool and t.near_pool and hasattr(game, "in_bog_pool"):
        if not any(game.in_bog_pool((x + math.cos(k * math.tau / 12) * (r + 70), y + math.sin(k * math.tau / 12) * (r + 70)))
                   for k in range(12)):
            return False
    return True


def gen_surface(gen):
    st = gen.game._explore = State(gen.nodes)
    lay = gen.layout
    G = 100                         # a coarse biome map, so picking candidates doesn't run the noise much
    cells = {}
    for gx in range(2, int(gen.size // G) - 1):
        for gy in range(2, int(gen.size // G) - 1):
            cells.setdefault(lay.biome_at(gx * G + G / 2, gy * G + G / 2), []).append((gx, gy))
    for t in TYPES:
        rng = random.Random(f"{gen.seed}:explore:{t.key}")
        idx = 0
        for biome, count in t.where:
            pool_cells = cells.get(biome) if biome != "cave" else None
            if not pool_cells:
                continue
            placed = 0
            for _ in range(count * 1000):
                if placed >= count:
                    break
                gx, gy = pool_cells[rng.randrange(len(pool_cells))]
                p = (gx * G + rng.uniform(0, G), gy * G + rng.uniform(0, G))
                angle = rng.uniform(0, math.tau)
                if lay.biome_at(*p) != biome:
                    continue
                # a boat looks for a bog pool's edge first, then settles for anywhere in its biome
                if not _surface_ok(gen, st, t, p, angle, rng, pool=_ < count * 500):
                    continue
                pl = Place(t, idx, p[0], p[1], "over", angle, _tier(lay, p[0], p[1], biome), biome)
                idx += 1
                placed += 1
                st.places.append(pl)
                _build(gen, st, pl)


def _cave_ok(gen, st, t, p, angle, open_cells, ladders):
    C = CAVE_CELL
    cx, cy = int(p[0] // C), int(p[1] // C)
    if any((cx + dx, cy + dy) not in open_cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
        return False
    if any(dist(p, q) < 260 for q in ladders):
        return False
    if any(pl.layer == "cave" and dist(p, pl.pos) < 600 for pl in st.places):
        return False
    L = gen.cave
    for dx, dy, rr in _footprint(t, "cave", angle):
        q = (p[0] + dx, p[1] + dy)
        if (int(q[0] // C), int(q[1] // C)) not in open_cells or not gen.free(q, rr, layer="cave", gap=6):
            return False
        probe = arcade.SpriteSolidColor(int(2 * rr), int(2 * rr), center_x=q[0], center_y=q[1])
        if arcade.check_for_collision_with_lists(probe, [L.solid, L.exits]):
            return False        # cave walls
    return True


def gen_layers(gen):
    st = _st(gen.game)
    if st is None:
        return
    C = CAVE_CELL
    open_cells = {(int(s.center_x // C), int(s.center_y // C)) for s in gen.cave.ground}
    ladders = [s.position for s in gen.cave.exits]
    for t in TYPES:
        count = sum(n for b, n in t.where if b == "cave")
        if not count:
            continue
        rng = random.Random(f"{gen.seed}:explore:{t.key}:cave")
        cells = sorted(open_cells)
        idx = sum(1 for pl in st.places if pl.type is t)
        placed = 0
        for _ in range(count * 400):
            if placed >= count:
                break
            c = cells[rng.randrange(len(cells))]
            p = (c[0] * C + C / 2, c[1] * C + C / 2)
            angle = rng.uniform(0, math.tau)
            if not _cave_ok(gen, st, t, p, angle, open_cells, ladders):
                continue
            pl = Place(t, idx, p[0], p[1], "cave", angle, min(1.0, 0.45 + HARSH["cave"]), "cave")
            idx += 1
            placed += 1
            st.places.append(pl)
            _build(gen, st, pl)
    _assign_notes(st, gen.seed)


def _assign_notes(st, seed):
    """Put every locked recipe in COPIES places (themed ones first, then any), so it is always findable."""
    rng = random.Random(f"{seed}:explore:notes")
    st.by_id = {pl.pid: pl for pl in st.places}
    for rec in LOCKED_ORDER:
        if rec not in ITEMS:
            continue
        themed = [pl for pl in st.places if rec in pl.type.teaches]
        rng.shuffle(themed)
        themed.sort(key=lambda pl: len(pl.notes))
        chosen = themed[:COPIES]
        if len(chosen) < MIN_COPIES:
            rest = [pl for pl in st.places if pl not in chosen]
            rng.shuffle(rest)
            rest.sort(key=lambda pl: len(pl.notes))
            chosen += rest[:MIN_COPIES - len(chosen)]
        if len(chosen) < MIN_COPIES:
            continue                       # can't be found twice in this world: it just starts known
        for pl in chosen:
            pl.notes.append(rec)
        st.locked.add(rec)
        st.where[rec] = sorted({pl.type.key for pl in chosen}, key=lambda k: [t.key for t in TYPES].index(k))


# =========================================================================== recipes (every computer)
def known(game, rec):
    """May this recipe be crafted (i.e. is it not still waiting to be found)?"""
    st = _st(game)
    return st is None or rec["item"] not in st.locked or rec["item"] in st.known


def where_hint(game, item):
    st = _st(game)
    keys = st.where.get(item, []) if st else []
    names = [TYPE[k].plural for k in keys]
    if not names:
        return "out in the world"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def draw_locked_recipe(game, gi, rec, rect, hover):
    """ui.py's crafting list: an unknown recipe as a dark silhouette. Returns the hover text."""
    rl, rr, rb, rt = rect
    arcade.draw_lrbt_rectangle_filled(rl, rr, rb, rt, (48, 40, 56, 210) if hover else (28, 30, 38, 210))
    arcade.draw_texture_rect(art.icon(rec["item"]), arcade.XYWH(rl + 20, (rb + rt) / 2, 28, 28),
                             color=arcade.color.BLACK, alpha=200)
    game.txt(f"rn{gi}", "???", rl + 42, rb + 10, (170, 150, 200), 12, bold=True)
    game.txt(f"rc{gi}", f"find it out in the world - look in {where_hint(game, rec['item'])}", rr - 10, rb + 10,
             (160, 140, 190), 10, anchor_x="right")
    return "An unknown recipe. Notes and blueprints in abandoned places teach it to the whole team."


# =========================================================================== searching a place (host / solo)
def _near(st, p, rng=OPEN_RANGE):
    best = None
    for pl in st.places:
        if pl.layer == p.layer and pl.box is not None:
            d = dist(pl.box.position, p.pos)
            if d < rng and (best is None or d < best[0]):
                best = (d, pl)
    return best[1] if best else None


def _roll(game, pl):
    """The place's one-time loot: [(item, n), ...] (seeded per place, richer with its tier)."""
    t = pl.type
    rng = random.Random(f"{game.seed}:explore:loot:{pl.pid}")
    got = {}

    def pick(table):
        table = [e for e in table if e[0] in ITEMS]
        if not table:
            return
        item, lo, hi, _w = rng.choices(table, [e[3] for e in table])[0]
        n = rng.randint(lo, hi)
        if hi > 1:
            n = int(round(n * (1 + 0.5 * pl.tier)))
        got[item] = got.get(item, 0) + max(1, n)

    for _ in range(2 + int(pl.tier * 2.6)):
        pick(t.loot)
    if rng.random() < 0.12 + 0.45 * pl.tier:
        pick(t.rare)
    if rng.random() < 0.15 * pl.tier:
        pick(t.rare)
    return sorted(got.items())


def _guards(game, pl, p, tier):
    """Wake the place's guards. By day, zombies that hid inside get a while in the shade before the sun gets them."""
    st = _st(game)
    rng = random.Random(f"{game.seed}:explore:guards:{pl.pid}")
    for kind, (lo, hi) in pl.type.guards.items():
        n = int(lo + hi * tier + rng.random() * 0.6)
        if kind == "golems":
            if pl.layer == "over":
                continue
            for _ in range(n):
                game.spawn_zombie(pl.layer, "golem", at=pl.pos)
            continue
        if kind == "zombies":
            if pl.layer != "over":
                n = max(1, n - 1)
            for i in range(n):
                zk = None
                if pl.layer == "over":
                    zk = "brute" if tier > 0.65 and i == 0 else "runner" if rng.random() < 0.3 else "walker"
                z = game.spawn_zombie(pl.layer, zk, at=pl.pos)
                if z is not None:
                    z.shade_t = 40.0            # main._update_zombies: no sun burn while this lasts
                    st.guards.append(z)
        elif kind == "wolves" and pl.layer == "over":
            for _ in range(n):
                for _try in range(12):
                    a = rng.uniform(0, math.tau)
                    x, y = pl.x + math.cos(a) * rng.uniform(140, 220), pl.y + math.sin(a) * rng.uniform(140, 220)
                    w = Animal("wolf", x, y, game.next_aid)
                    if arcade.check_for_collision_with_lists(w, [game.over.solid, game.over.huts]) or \
                            game.body_blocked(w, x, y):
                        continue
                    game.next_aid += 1
                    w.aggro, w.aggro_t = p.id, 30.0
                    game.over.animals.append(w)
                    game.amap[w.aid] = w
                    break
    if pl.type.guards:
        game.play("roar", 0.25, at=pl.pos, layer=pl.layer)


def near(game, p):
    """Is a place's container within reach of survivor p? (the controller's B uses this to search, not eat)"""
    st = _st(game)
    return st is not None and _near(st, p) is not None


def open_near(game, p):
    """main.interact (E / B): search the container at hand. True if there was one."""
    st = _st(game)
    if st is None:
        return False
    pl = _near(st, p)
    if pl is None:
        return False
    if pl.opened:
        game.say(f"Already searched - nothing left in this {pl.type.box_name}.", 2, to=p)
        return True
    _set_opened(st, pl, True)
    if not pl.found:
        pl.found = True
    loot = _roll(game, pl)
    bx, by = pl.box.position
    for i, (item, n) in enumerate(loot):
        game.give(p, item, n)
        game.popup(f"+{n} {ITEMS[item]['name']}", bx, by + 30 + i * 18, (255, 236, 170), to=p, layer=pl.layer)
    game.burst(bx, by, (255, 220, 140), 14, 110, layer=pl.layer)
    game.play("pickup", 0.35, at=(bx, by), layer=pl.layer)
    new = [r for r in pl.notes if r in st.locked and r not in st.known]
    st.known.update(new)
    what = ", ".join(f"{n} {ITEMS[i]['name']}" for i, n in loot) or "nothing useful"
    if new:
        names = " and ".join(f"the {ITEMS[r]['name']}" for r in new)
        game.say(f"{pl.type.note}: {p.name} learned {names}! (the whole team can craft it now)", 7)
        game.play("win", 0.4)
    elif pl.notes:
        game.say(f"You searched the {pl.type.box_name}: {what}.  {pl.type.note} - nothing you don't know.", 5, to=p)
    else:
        game.say(f"You searched the {pl.type.box_name}: {what}.", 4, to=p)
    _guards(game, pl, p, pl.tier)
    _sync(game)
    return True


# =========================================================================== sync, save, load
def _payload(st):
    return ["st", sorted(pl.pid for pl in st.places if pl.opened), sorted(pl.pid for pl in st.places if pl.found),
            sorted(st.known)]


def _sync(game, to=None):
    st = _st(game)
    if st is not None and game.net == "host":
        game.biome_emit(NAME, _payload(st), to=to)


def _apply(game, opened, found, known_):
    st = _st(game)
    if st is None:
        return
    opened, found = set(opened or ()), set(found or ())
    for pl in st.places:
        _set_opened(st, pl, pl.pid in opened)
        pl.found = pl.pid in found or pl.opened
    st.known = {r for r in (known_ or ()) if r in st.locked}


def event(game, ev):
    if len(ev) > 5 and ev[2] == "st":
        _apply(game, ev[3], ev[4], ev[5])


def save(game):
    st = _st(game)
    if st is None:
        return None
    p = _payload(st)
    return {"v": 1, "opened": p[1], "found": p[2], "known": p[3]}


def load(game, data):
    st = _st(game)
    if st is None:
        return
    if not data:        # a save from before places existed: everything it could craft stays craftable
        st.known = set(st.locked)
        return
    _apply(game, data.get("opened"), data.get("found"), data.get("known"))


# =========================================================================== every frame
def update(game, dt):
    """Host / solo: first-discovery messages, shaded guards, sending the state to new players."""
    st = _st(game)
    if st is None:
        return
    for z in list(st.guards):
        if getattr(z, "shade_t", 0) > 0 and z.hp > 0 and z.sprite_lists:
            z.shade_t -= dt
        else:
            st.guards.remove(z)
    st.tick -= dt
    if st.tick > 0:
        return
    st.tick = 0.4
    changed = False
    for p in game.alive_players():
        for pl in st.places:
            if not pl.found and pl.layer == p.layer and dist(pl.pos, p.pos) < FIND_RANGE:
                pl.found = True
                changed = True
                n = sum(1 for q in st.places if q.found)
                game.say(f"You found {pl.type.title}.   (places found: {n} of {len(st.places)})", 4.5, to=p)
                game.play("craft", 0.25, to=p)
    if changed:
        _sync(game)
    now = set(game.players)
    for pid in now - st.seen_players:          # someone joined: send them what's been searched and learned
        p = game.players[pid]
        if p.conn is not None:
            _sync(game, to=p)
    st.seen_players = now


def visuals(game, dt):
    """Every computer: a faint glint over containers nobody has searched yet, so explorers notice them."""
    st = _st(game)
    if st is None or game.state != "playing":
        return
    vl = game.view_layer
    vx, vy = game.view_pos()
    for pl in st.places:
        if not pl.opened and pl.layer == vl and pl.box is not None and random.random() < dt * 1.6:
            bx, by = pl.box.position
            if abs(bx - vx) < 900 and abs(by - vy) < 900:
                game._burst(bx + random.uniform(-10, 10), by + random.uniform(-8, 8), (255, 228, 150), 1, 14, 2.6,
                            1.2, vl)


def draw3d(game, L, vl, stage="props"):
    st = _st(game)
    if st is None:
        return
    if stage == "ground":
        if vl in st.patches:
            game.flat(st.patches[vl])
        return
    if stage != "props":
        return
    for kind, lst in st.lists.get(vl, {}).items():
        if len(lst):
            game.mesh(lst, kind)


# =========================================================================== small hooks for other modules
def hint(game, p, inter):
    """ui.context_hint: what E / B would do here."""
    st = _st(game)
    if st is None or not p.alive:
        return None
    pl = _near(st, p)
    if pl is None:
        return None
    if pl.opened:
        return f"{pl.type.title[0].upper()}{pl.type.title[1:]} - already searched"
    return f"{inter}  search the {pl.type.box_name}  ({pl.type.title})"


def progress_text(game):
    """progress.py's pause screen: 'Places found 3/34   Recipes found 2/10' ('' when there are none)."""
    st = _st(game)
    if st is None or not st.places:
        return ""
    found = sum(1 for pl in st.places if pl.found)
    txt = f"Places found {found}/{len(st.places)}"
    if st.locked:
        txt += f"   Recipes found {len(st.known & st.locked)}/{len(st.locked)}"
    return txt


def shaded(z):
    """main._update_zombies: is this zombie still hiding from the sun (a place's guard)?"""
    return getattr(z, "shade_t", 0) > 0


def debug_spots(game):
    """{type key: (layer, x, y)} - one place of each type (screenshots, tests)."""
    st = _st(game)
    out = {}
    for pl in st.places if st else ():
        out.setdefault(pl.type.key + ("_cave" if pl.layer != "over" else ""), pl)
    return out


biomes.register(biomes.Biome(
    NAME, title="Places to discover", order=80, region=False, legacy=False,
    gen_surface=gen_surface, gen_layers=gen_layers, update=update, visuals=visuals, draw3d=draw3d,
    save=save, load=load, event=event,
))
