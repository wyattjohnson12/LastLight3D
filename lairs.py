"""
lairs.py - THE LAIRS: bosses you choose to wake.

Every boss sleeps in a lair somewhere out in the world, in the biome it belongs to:
    THE QUAKE TITAN       the Stone Highlands, inside the Titan's Crown (the ring of rune stones)
    THE BROOD MOTHER      the Riverlands meadow, at the end of its road
    THE FROST WRAITH      the Frostwood Tundra, in the Wraith's Hollow (the frost scar)
    THE MIRE LURKER       the middle of the Mire
    THE INFERNO COLOSSUS  the Ashlands, on the rim of its lava caldera (it rises out of the lava)
Old worlds (worldgen 1) and any world missing one of those biomes put the lair far from the spawn instead.

A lair is a landmark: a scorched patch with a ring of glowing runes and old bones, an altar stone, and a
tall spire in the boss's colours with embers rising off it, so you can spot it from far away. The first
time you come near one you're told whose it is.

Waking: use the altar (E / controller B), once to get the warning, again within a few seconds to wake it.
The boss rises at its lair right away, day or night, with its intro cutscene. A boss you wake at night
fights until dawn. Wake it by day and it drags the night in with it: the sky darkens while it is out
(game.boss_gloom, folded into game.darkness), so it's cold, the dead don't burn and the fight lasts until
the NEXT dawn. At dawn a surviving boss runs back to its lair and sleeps there, keeping its wounds: wake
it again whenever you're ready. Only one boss can be awake at a time. Bosses can be fought in any order.

A beaten lair goes quiet: grey runes, no embers, no glow, and it stays that way (saved). Once every lair is
quiet the bosses come back stronger, all at once (a new round: each lair remembers how often its boss
has been beaten, and that is the boss's toughness, like the old boss "cycle").

The backstop: if nobody wakes or beats a boss for game.boss_gap nights (the "Bosses wake on their own
after N nights" setting, default settings.BOSS_WAKE_NIGHTS), the next unbeaten boss wakes by itself and
comes for you like bosses used to (main._update_clock). game.boss_day is the night that happens.

Co-op: the lairs are built from the seed on every computer (own random stream, no nodes added, so no
other module's map changes). The host decides everything; each lair's state (times beaten, wounded or
not) goes to the clients in the snapshot ("lr"). Messages, embers and the gloom are worked out locally.
Saves keep each lair's state under "biomes"["lairs"]; saves from before lairs are converted from the old
boss counter (main.boss_num).

Hooks into main.py (all small): interact() / handle_pad() use the altar, spawn_boss(kind, at), kill_boss(),
start_retreat() (runs home), the dawn / dusk / backstop code in _update_clock(), the darkness property
(gloom), the snapshot. ui.py: the HUD line, the context hint, the cutscene texts.
"""
import math
import random

import arcade

import art
import art_lairs
import base
import biomes
import shapes3d as S3
from settings import *
from world import Node

NAME = "lairs"
HOMES = {"titan": "highlands", "brood": "meadow", "wraith": "tundra", "mire": "mire", "colossus": "ash"}
ALTAR_REACH = 105            # how close you must stand to use an altar
FOUND_RADIUS = 560           # "You found the lair of..." this close
CONFIRM_SECONDS = 6.0        # the second press must come this soon after the warning
KEEP_CLEAR = 190             # nothing grows back this close to a lair
NO_BUILD = 120               # ...and nobody builds this close to its altar or spire
SPIRE_BACK = 92              # the spire stands this far behind the altar (away from the spawn)
RISE_BACK = 170              # ...and the boss rises here
SPIRE_ON_SPOT = {"wraith": SPIRE_BACK}   # the Wraith's ice spire stands right in its Hollow, ringed by crystals
LAIR_PROPS = {"wraith": ("frost_crystal", "ice_rock")}   # ...which (and its ring of ice) may crowd the altar
GLOOM = 0.74                 # how dark the day gets while a boss is out
GLOOM_RATE = 0.3             # per second, darkening / clearing
EMBER_SIGHT = 2400           # embers rise off lairs this close to a viewer
SPIRE_STRETCH = 1.5          # how much taller than their recipes below the spires are drawn
SPIRE_TOP = 360              # px: about where the embers start (the spire's tip)


# =========================================================================== 3D shapes
def _P(rings, **kw):
    return S3.Part(rings, **kw)


def _altar(glow_col, quiet, k=1.0):
    stone = (112, 106, 98)
    core = (54, 50, 48) if quiet else glow_col
    parts = [
        _P([(1.0, 0.0, 0, 0.6), (1.0, 0.32, 0, 0.82), (0.86, 0.4, 0, 0.92), (0.0, 0.4, 0, 0.95)], color=stone, sides=4),
        _P(S3.tube(0.5, 0.42, 0.8, z0=0.38), color=(98, 92, 86), sides=6),
        _P([(0.4, 1.12, 0.4, 0.8), (0.86, 1.28, 0.8, 0.95), (0.84, 1.42, 0.84, 1.05), (0.62, 1.4, 0.6, 0.9),
            (0.0, 1.3, 0.0, 0.8)], sides=8),                 # the bowl: the altar picture draped on
        _P(S3.ball(3), at=(0, 0, 1.46), size=(0.36, 0.36, 0.26), color=core, sides=6, glow=0.0 if quiet else k),
    ]
    return S3.Shape(parts, foot=(S3.BOX * 0.8, S3.BOX * 0.8), turn=S3.Q, cut=0.1)


def _spire(kind, quiet):
    """The tall landmark behind each altar, one look per boss."""
    stone, glow_col = art_lairs.colours(kind)
    g = 0.0 if quiet else 1.0
    lit = (60, 58, 56) if quiet else glow_col
    if quiet:
        stone = tuple(int(c * 0.6 + 30) for c in stone)
    parts = []
    if kind == "titan":                 # stacked rune blocks, leaning a little
        z = 0.0
        for i, (w, h) in enumerate(((0.95, 1.5), (0.82, 1.6), (0.7, 1.5), (0.56, 1.3), (0.4, 0.9))):
            parts.append(_P([(w, z, 0, 0.62 + 0.05 * i), (w * 0.94, z + h, 0, 0.8 + 0.05 * i), (0.0, z + h, 0, 0.9)],
                            at=(0.04 * i, 0.0, 0), color=stone, sides=4, jitter=0.08))
            parts.append(_P(S3.tube(w * 0.99, w * 0.97, 0.12, z0=z + h * 0.45), at=(0.04 * i, 0.0, 0), color=lit,
                            sides=4, glow=0.8 * g))
            z += h
    elif kind == "wraith":              # a cluster of ice spikes
        parts.append(_P([(0.6, 0.0, 0, 0.7), (0.5, 5.4, 0, 0.95), (0.0, 7.0, 0, 1.1)], color=stone, sides=6))
        for k, (a, h, t) in enumerate(((0.3, 3.4, 0.35), (2.4, 2.6, 0.45), (4.2, 4.0, 0.3), (5.4, 2.0, 0.55))):
            parts.append(_P([(0.32, 0.0, 0, 0.7), (0.24, h * 0.8, 0, 0.95), (0.0, h, 0, 1.1)],
                            at=(math.cos(a) * 0.45, math.sin(a) * 0.45, 0), tilt=math.cos(a) * t,
                            roll=math.sin(a) * t, color=stone, sides=5))
        parts.append(_P(S3.tube(0.36, 0.3, 3.6, z0=1.2), color=lit, sides=6, glow=0.22 * g))
    elif kind == "colossus":            # a black obsidian fang, ember cracks, a burning tip
        parts.append(_P([(0.85, 0.0, 0, 0.55), (0.62, 2.8, 0, 0.75), (0.4, 5.4, 0, 0.9), (0.0, 7.4, 0, 1.0)],
                        color=stone, sides=5, jitter=0.12))
        for k in range(5):
            a = k * 1.3
            parts.append(_P(S3.ball(2), at=(math.cos(a) * 0.6, math.sin(a) * 0.6, 0.9 + k * 1.1),
                            size=(0.16, 0.16, 0.42), color=lit, sides=4, glow=g))
        parts.append(_P(S3.ball(3), at=(0, 0, 7.3), size=0.3, color=lit, sides=5, glow=g))
        for k, a in enumerate((0.8, 2.9, 4.9)):
            parts.append(_P([(0.34, 0.0, 0, 0.6), (0.0, 2.4, 0, 0.95)], at=(math.cos(a) * 0.8, math.sin(a) * 0.8, 0),
                            tilt=math.cos(a) * 0.35, roll=math.sin(a) * 0.35, color=stone, sides=4))
    elif kind == "brood":               # a curling chitin horn with glowing egg sacs at its foot
        z, x = 0.0, 0.0
        for i in range(6):
            w = 0.8 - i * 0.12
            parts.append(_P([(w, 0.0, 0, 0.6 + 0.06 * i), (w * 0.9, 1.25, 0, 0.75 + 0.06 * i)],
                            at=(x, 0.0, z), tilt=0.06 + i * 0.07, color=stone, sides=6))
            x += 1.25 * math.sin(0.06 + i * 0.07)
            z += 1.25 * math.cos(0.06 + i * 0.07)
        parts.append(_P(S3.cone(0.12, 0.9), at=(x, 0.0, z), tilt=0.5, color=stone, sides=5))
        for k, a in enumerate((0.4, 1.9, 3.3, 4.6, 5.6)):
            parts.append(_P(S3.ball(3), at=(math.cos(a) * 0.95, math.sin(a) * 0.95, 0.18), size=(0.3, 0.3, 0.24),
                            color=lit, sides=6, glow=0.7 * g))
    else:                               # the Mire: a rotten root totem hung with moss and glowing fungus
        parts.append(_P([(0.75, 0.0, 0, 0.55), (0.5, 1.6, 0, 0.7), (0.56, 3.4, 0, 0.8), (0.4, 5.2, 0, 0.9),
                         (0.0, 6.2, 0, 0.95)], color=stone, sides=6, jitter=0.18))
        for k, (a, z) in enumerate(((0.5, 2.6), (2.6, 3.6), (4.4, 4.6), (1.6, 5.3))):
            parts.append(_P(S3.tube(0.08, 0.03, 1.4, z0=-1.4), at=(math.cos(a) * 0.5, math.sin(a) * 0.5, z),
                            color=(70, 96, 54), sides=3, sway=0.15))
            parts.append(_P(S3.dome(0.42, 0.25), at=(math.cos(a + 0.8) * 0.55, math.sin(a + 0.8) * 0.55, z - 0.6),
                            color=lit, sides=6, glow=0.8 * g))
        for a in (1.0, 3.1, 5.0):
            parts.append(_P([(0.3, 0.0, 0, 0.6), (0.12, 1.8, 0, 0.8)], at=(math.cos(a) * 0.6, math.sin(a) * 0.6, 0),
                            tilt=math.cos(a) * 0.9, roll=math.sin(a) * 0.9, color=stone, sides=4))
    for p in parts:                     # stretched up, so it stands well above the trees
        p.at = (p.at[0], p.at[1], p.at[2] * SPIRE_STRETCH)
        p.size = (p.size[0], p.size[1], p.size[2] * SPIRE_STRETCH)
    return S3.Shape(parts, foot=(1.0, 1.0), cut=0.1)


def _ribcage():
    bone = (210, 202, 182)
    parts = [_P(S3.tube(0.08, 0.08, 1.9, z0=-0.95), at=(0, 0, 0.12), tilt=math.pi / 2, color=bone, sides=4)]
    for k in range(4):
        x = -0.6 + k * 0.4
        for s in (1, -1):
            parts.append(_P(S3.tube(0.05, 0.035, 0.75), at=(x, 0.06 * s, 0.1), roll=-s * 1.0, color=bone, sides=3))
    parts.append(_P(S3.ball(3), at=(1.05, 0, 0.2), size=(0.3, 0.24, 0.22), color=bone, sides=6))
    return S3.Shape(parts, foot=(1.0, 1.0), cut=0.1)


def _register_shapes():
    for kind in list(art_lairs.PALETTE):
        S3.SHAPES[f"lair_spire_{kind}"] = _spire(kind, False)
        S3.SHAPES[f"lair_spire_{kind}_quiet"] = _spire(kind, True)
        S3.SHAPES[f"lair_altar_{kind}"] = _altar(art_lairs.colours(kind)[1], False, 0.45 if kind == "wraith" else 1.0)
    S3.SHAPES["lair_altar_quiet"] = _altar((0, 0, 0), True)
    S3.SHAPES["lair_bones"] = _ribcage()


_register_shapes()


# =========================================================================== state
class Lair:
    """One boss's lair. Position and looks come from the seed; kills / hp are the game state."""

    def __init__(self, kind, x, y, ux, uy, rise=None):
        self.kind = kind
        self.x, self.y = x, y                       # the altar
        self.ux, self.uy = ux, uy                   # "behind the altar" (away from where you come from)
        self.spire = (x + ux * SPIRE_BACK, y + uy * SPIRE_BACK)
        self.mid = (x + ux * 45, y + uy * 45)
        self.rise = rise or (x + ux * RISE_BACK, y + uy * RISE_BACK)
        self.kills = 0                              # times its boss has been beaten (= how tough it is now)
        self.hp = None                              # a boss that ran home keeps its wounds (None: unhurt)
        self.quiet = None                           # what the looks show right now (refresh())
        self.ground = self.altar = self.spire_sprite = self.glow = None
        self.spires = {}                            # False / True (quiet) -> SpriteList to draw it with
        self.altars = None

    @property
    def name(self):
        return BOSSES[self.kind]["name"]

    @property
    def pos(self):
        return (self.x, self.y)


class State:
    """Per-world lair state (game.lair_st). Made by gen_surface on every computer."""

    def __init__(self, game):
        self.nodes = game.nodes            # which world this belongs to
        self.lairs = {}                    # boss kind -> Lair, in BOSS_ORDER
        self.ground = arcade.SpriteList()
        self.bones = arcade.SpriteList()
        self.found = set()                 # lairs this computer has already announced
        self.confirm = {}                  # host: player id -> (kind, time) of an altar warning


def _state(game):
    st = getattr(game, "lair_st", None)
    return st if st is not None and st.nodes is game.nodes else None


def lair_of(game, kind):
    st = _state(game)
    return st.lairs.get(kind) if st else None


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# =========================================================================== generation (every computer)
def _clear_of_things(over, x, y, rad, small=0, ignore=()):
    """No tree, rock or other solid thing within about rad of (x, y) (and no bush / reeds within `small`)."""
    probe = arcade.SpriteSolidColor(int(rad * 2), int(rad * 2), center_x=x, center_y=y)
    for h in arcade.check_for_collision_with_lists(probe, [over.solid, over.trees, over.rocks]):
        plant = h.kind in WALKABLE_NODES and h.kind != "rock" if isinstance(h, Node) else False
        if isinstance(h, Node) and (h.state == "gone" or h.kind in ignore or plant):
            continue       # the Titan's quake pool waits off the map; little plants only matter close up
        return False
    if small:
        probe = arcade.SpriteSolidColor(int(small * 2), int(small * 2), center_x=x, center_y=y)
        if arcade.check_for_collision_with_list(probe, over.bushes):
            return False
    return True


def _open(g, p, u, kind=""):
    """Is there room for a lair at p (altar at p, spire behind it along u, room to stand in front)?"""
    over = g.layers["over"]
    x, y = p
    if not (300 < x < over.size - 300 and 300 < y < over.size - 300):
        return False
    import ashlands
    spire = (x + u[0] * SPIRE_BACK, y + u[1] * SPIRE_BACK)
    front = (x - u[0] * 75, y - u[1] * 75)
    mid = (x + u[0] * 45, y + u[1] * 45)
    for k in range(9):           # firm, dry ground: no cliffs or rivers under the lair
        q = mid if k == 0 else (mid[0] + math.cos(k * math.tau / 8) * 100, mid[1] + math.sin(k * math.tau / 8) * 100)
        if g.terrain_blocked(q[0], q[1], "over") or g.terrain_water(q[0], q[1], "over"):
            return False
    for q in (p, front) if kind in ("colossus", "mire") else (p, spire, front):   # (their spires stand in lava / bog)
        if ashlands.in_lava(g, q, pad=34) or (g.in_swamp(q) and g.in_bog_pool(q)):
            return False
    for s in list(over.ponds) + list(over.exits):
        if _dist(s.position, mid) < 200:
            return False
    skip = LAIR_PROPS.get(kind, ())
    small = 0 if kind == "mire" else 26           # (the Mire is all reeds and glowcaps)
    return (_clear_of_things(over, x, y, 40, small, skip)
            and _clear_of_things(over, spire[0], spire[1], 38, small, skip)
            and _clear_of_things(over, front[0], front[1], 30, 0, skip))


def _facing(g, kind, p, pool):
    if pool is not None:                       # the Colossus: the spire stands between the altar and its lava
        dx, dy = pool[0] - p[0], pool[1] - p[1]
    else:                                      # everyone else: behind the altar as you come from the spawn
        dx, dy = p[0] - g.layout.centre[0], p[1] - g.layout.centre[1]
    d = math.hypot(dx, dy) or 1.0
    return dx / d, dy / d


def _search(gen, kind, want, inside, taken, pool=None):
    """The nearest open spot to `want` (spiralling out), inside(p) true, far from other lairs."""
    g = gen.game
    for k in range(420):
        a, d = k * 2.39996, 38.0 * math.sqrt(k)
        p = (want[0] + math.cos(a) * d, want[1] + math.sin(a) * d)
        if inside is not None and not inside(p):
            continue
        if _dist(p, gen.layout.centre) < 650 or any(_dist(p, q) < 700 for q in taken):
            continue
        u = _facing(g, kind, p, pool)
        turns = (0.0,) if k else (0.0, 0.3, -0.3, 0.6, -0.6, 0.9, -0.9, 1.2, -1.2)   # right on the spot: turn a bit
        for t in turns:
            c, s_ = math.cos(t), math.sin(t)
            v = (u[0] * c - u[1] * s_, u[0] * s_ + u[1] * c)
            off = SPIRE_ON_SPOT.get(kind, 0.0)
            q = (p[0] - v[0] * off, p[1] - v[1] * off)
            if _open(g, q, v, kind):
                return q, v
    return None


def _home(gen, kind):
    """(where its lair should be, test for 'still in its biome', lava pool centre) - or None."""
    g, lay = gen.game, gen.layout
    home = HOMES.get(kind)
    if gen.version == biomes.LEGACY:
        if home == "mire" and getattr(g, "swamp_centre", None):
            return g.swamp_centre, g.in_swamp, None
        return None
    if home not in lay.centres:
        return None
    inside = lambda p, h=home: gen.biome_at(p) == h
    if home == "ash" and getattr(g, "ash_lair", None):
        pool = g.ash_lair if getattr(g, "ash_pools", None) else None
        return g.ash_lair, inside, pool
    if home == "mire":
        return getattr(g, "swamp_centre", None) or lay.centres["mire"], inside, None
    return lay.centres[home], inside, None


def _fallback(gen, taken):
    """Somewhere far from the spawn, as far as possible from the other lairs (old maps, missing biomes)."""
    g, c, S = gen.game, gen.layout.centre, gen.size
    a0 = gen.rng.uniform(0, math.tau)
    best = None
    for k in range(36):
        a = a0 + k * math.tau / 36
        p = (c[0] + math.cos(a) * S * 0.36, c[1] + math.sin(a) * S * 0.36)
        far = min([_dist(p, q) for q in taken] + [1e9])
        if best is None or far > best[0]:
            best = (far, p)
    return best[1]


def gen_surface(gen):
    g = gen.game
    st = g.lair_st = State(g)
    g.boss_gloom = 0.0
    taken = []
    spots = {}
    for kind in BOSS_ORDER:
        h = _home(gen, kind)
        if h is None:
            continue
        want, inside, pool = h
        got = _search(gen, kind, want, inside, taken, pool) or _search(gen, kind, want, None, taken, pool)
        if got:
            spots[kind] = got + (pool,)
            taken.append(got[0])
    not_mire = (lambda p: not g.in_swamp(p)) if gen.version == biomes.LEGACY else None
    for kind in BOSS_ORDER:
        if kind in spots:
            continue
        want = _fallback(gen, taken)
        got = _search(gen, kind, want, not_mire, taken) or _search(gen, kind, want, None, [])
        if got is None:                          # (never seen) somewhere at all, so the boss has a home
            got = (want, _facing(g, kind, want, None))
        spots[kind] = got + (None,)
        taken.append(got[0])
    for kind in BOSS_ORDER:
        p, u, pool = spots[kind]
        lair = Lair(kind, p[0], p[1], u[0], u[1], rise=pool)
        st.lairs[kind] = lair
        _build(g, st, lair, gen.rng)


def _build(g, st, lair, rng):
    over = g.layers["over"]
    kind = lair.kind
    glow_col = art_lairs.colours(kind)[1]
    gs = arcade.Sprite(art_lairs.ground(kind), center_x=lair.mid[0], center_y=lair.mid[1])
    gs.scale = 360 / 256
    gs.angle = rng.uniform(0, 360)
    st.ground.append(gs)
    lair.ground = gs
    alt = arcade.Sprite(art_lairs.altar(kind), center_x=lair.x, center_y=lair.y)
    alt.scale = 0.95
    alt.angle = -math.degrees(math.atan2(lair.uy, lair.ux))
    lair.altar = alt
    lair.altars = arcade.SpriteList()       # (one list each: every boss's altar glows in its own colour)
    lair.altars.append(alt)
    over.solid.append(alt)
    sp = arcade.Sprite(art_lairs.spire(kind), center_x=lair.spire[0], center_y=lair.spire[1])
    sp.scale = 1.1 if kind != "titan" else 1.25
    sp.angle = rng.uniform(0, 360)
    lair.spire_sprite = sp
    lair.spires = {False: arcade.SpriteList(), True: arcade.SpriteList()}
    over.solid.append(sp)
    for k in range(3):                           # old rib cages round the altar
        a = math.atan2(lair.uy, lair.ux) + math.pi * 0.5 + k * 1.05 + rng.uniform(-0.25, 0.25)
        d = rng.uniform(105, 140)
        b = arcade.Sprite(art_lairs.bones(), center_x=lair.mid[0] + math.cos(a) * d,
                          center_y=lair.mid[1] + math.sin(a) * d)
        b.scale = rng.uniform(0.75, 1.0)
        b.angle = rng.uniform(0, 360)
        st.bones.append(b)
    haze = tuple(int(c * (0.35 if kind == "wraith" else 0.6)) for c in glow_col)     # (pale ones bloom white)
    gl = arcade.Sprite(art.glow(130, haze), center_x=lair.x, center_y=lair.y)
    gl.light = tuple(c / 255 for c in glow_col) + (0.5 if kind == "wraith" else 0.75,)
    over.glows.append(gl)
    lair.glow = gl
    _refresh_one(st, lair, False)


# =========================================================================== the rules (host / solo, plus readers)
def round_no(st):
    """How many times EVERY boss has been beaten (all lairs quiet -> they all wake up stronger)."""
    return min((l.kills for l in st.lairs.values()), default=0)


def beaten(st, lair):
    return lair.kills > round_no(st)


def asleep(game):
    """The lairs whose boss is still waiting to be beaten this round."""
    st = _state(game)
    return [l for l in st.lairs.values() if not beaten(st, l)] if st else []


def next_kind(game):
    """The boss the backstop wakes: the first unbeaten one in BOSS_ORDER."""
    left = asleep(game)
    return left[0].kind if left else BOSS_ORDER[game.boss_num % len(BOSS_ORDER)]


def next_name(game):
    return BOSSES[next_kind(game)]["name"]


def cycle(game, kind):
    """How tough this boss is now (the old boss "cycle"): how often it has been beaten."""
    lair = lair_of(game, kind)
    return lair.kills if lair else game.boss_num // len(BOSS_ORDER)


def wounds(game, kind):
    lair = lair_of(game, kind)
    return lair.hp if lair else game.boss_hp


def home(game, kind):
    lair = lair_of(game, kind)
    return lair.rise if lair else None


def remember(game, b):
    """A boss is running home (dawn): its lair keeps its wounds for the next time it's woken."""
    lair = lair_of(game, b.kind)
    if lair and b.hp > 0:
        lair.hp = b.hp


def on_kill(game, b):
    """A boss died: its lair goes quiet. Returns a line for the victory message."""
    st = _state(game)
    lair = lair_of(game, b.kind)
    if not lair:
        return ""
    before = round_no(st)
    lair.kills += 1
    lair.hp = None
    if round_no(st) > before:
        return ("Every lair is quiet... for now. The bosses will wake again - stronger. "
                f"One stirs in {game.boss_gap} nights.")
    left = len(asleep(game))
    return f"{left} boss{'es' if left != 1 else ''} still asleep in {'their lairs' if left != 1 else 'its lair'}."


def near_altar(game, p):
    st = _state(game)
    if not st or not p or p.layer != "over" or not p.alive:
        return None
    for lair in st.lairs.values():
        if _dist(p.pos, lair.pos) < ALTAR_REACH:
            return lair
    return None


def use_altar(game, p, lair):
    """Host / solo: someone used an altar (E / B). First time: a warning. Again soon after: wake it."""
    st = _state(game)
    if beaten(st, lair):
        game.say(f"The lair of {lair.name} lies quiet - you beat it. "
                 "Once every boss is beaten, they all wake again stronger.", 5, to=p)
        return
    out = list(game.over.bosses)
    if out:
        b = out[0]
        if b.kind == lair.kind:
            msg = f"{b.info['name']} is awake already!" if b.state != "flee" else \
                f"{b.info['name']} is still crawling home..."
        else:
            msg = f"{b.info['name']} is awake - deal with it first. Only one boss rises at a time."
        game.say(msg, 3, to=p)
        return
    pend = st.confirm.get(p.id)
    now = game.flame_t
    if not pend or pend[0] != lair.kind or now - pend[1] > CONFIRM_SECONDS:
        st.confirm[p.id] = (lair.kind, now)
        when = ("and fights until dawn" if game.is_night else
                "and drags the night in with it - it fights until the next dawn")
        hurt = ""
        if lair.hp is not None:
            full = BOSSES[lair.kind]["hp"] * (1 + 0.6 * lair.kills)
            hurt = f" It still carries its wounds ({int(lair.hp)}/{int(full)})."
        game.say(f"WAKE {lair.name}? It rises right here {when}.{hurt}  Use the altar again to wake it.",
                 CONFIRM_SECONDS, to=p)
        game.play("mine", 0.25, to=p)
        game.rumble(0.4, 0.3, to=p)
        return
    st.confirm.pop(p.id, None)
    wake(game, lair.kind, p)


def wake(game, kind, by=None):
    """Host / solo: the boss rises at its lair now. Restarts the backstop clock."""
    lair = lair_of(game, kind)
    if lair is None:
        return game.spawn_boss(kind)
    game.boss_day = game.day + game.boss_gap
    glow_col = art_lairs.colours(kind)[1]
    game.fx_layer = "over"
    game.burst(lair.rise[0], lair.rise[1], glow_col, 40, 260, 6, 1.2)
    game.ring(lair.x, lair.y, 20, 360, 0.9, glow_col)
    game.shake(10, 0.8)
    fresh = lair.hp is None
    b = game.spawn_boss(kind, at=lair.rise)
    if by is not None and fresh:      # (a wounded one says "RETURNS" itself; this shows after the intro)
        game.say(f"{by.name} woke {lair.name}! Kill it before dawn - or it crawls back to its lair.", 14)
    return b


def build_ok(game, item, x, y, layer):
    if layer != "over":
        return None
    st = _state(game)
    if st and any(_dist((x, y), l.pos) < NO_BUILD or _dist((x, y), l.spire) < NO_BUILD for l in st.lairs.values()):
        return False
    return None


_prev_spot_ok = base.Base.spot_ok


def _spot_ok(self, kind, layer, p, rad=None, ignore=None):
    """Nothing grows back inside a lair (wraps base.Base.spot_ok)."""
    if layer == "over":
        st = _state(self)
        if st and any(_dist(p, l.mid) < KEEP_CLEAR for l in st.lairs.values()):
            return False
    return _prev_spot_ok(self, kind, layer, p, rad, ignore)


base.Base.spot_ok = _spot_ok


# =========================================================================== saves & co-op
def save(game):
    st = _state(game)
    if not st:
        return None
    return {"kills": {k: l.kills for k, l in st.lairs.items()},
            "hp": {k: l.hp for k, l in st.lairs.items() if l.hp is not None},
            "found": sorted(st.found)}


def load(game, data):
    st = _state(game)
    if not st:
        return
    if data is None:          # a save from before lairs: the old boss counter says who's been beaten
        n = int(game.boss_num)
        for i in range(n):
            lair = st.lairs.get(BOSS_ORDER[i % len(BOSS_ORDER)])
            if lair:
                lair.kills += 1
        if game.boss_hp is not None and not len(game.over.bosses):
            lair = st.lairs.get(BOSS_ORDER[n % len(BOSS_ORDER)])
            if lair:
                lair.hp = float(game.boss_hp)
        d = list(game.difficulty)
        if len(d) > 3 and int(d[3]) <= BOSS_EVERY:     # the old "a boss every 3 nights": give it the new backstop
            d[3] = BOSS_WAKE_NIGHTS
            game.difficulty = tuple(d)
        game.boss_day = game.day + game.boss_gap
    else:
        for k, n in (data.get("kills") or {}).items():
            if k in st.lairs:
                st.lairs[k].kills = max(0, int(n))
        for k, hp in (data.get("hp") or {}).items():
            if k in st.lairs and hp is not None:
                st.lairs[k].hp = float(hp)
        st.found = {k for k in data.get("found", []) if k in st.lairs}
    for b in game.over.bosses:      # a boss that was out when the game was saved hits as hard as its round says
        lair = st.lairs.get(b.kind)
        if lair:
            b.damage = b.info["damage"] * (1 + 0.25 * lair.kills)


def net_rows(game):
    st = _state(game)
    return [[st.lairs[k].kills, int(st.lairs[k].hp is not None)] for k in BOSS_ORDER if k in st.lairs] if st else []


def net_apply(game, rows):
    st = _state(game)
    if not st or not isinstance(rows, list):
        return
    for kind, row in zip([k for k in BOSS_ORDER if k in st.lairs], rows):
        try:
            st.lairs[kind].kills = int(row[0])
            st.lairs[kind].hp = 1.0 if row[1] else None
        except (TypeError, ValueError, IndexError):
            pass


# =========================================================================== looks & messages (every computer)
def _refresh_one(st, lair, quiet):
    if lair.quiet == quiet:
        return
    lair.quiet = quiet
    for lst in lair.spires.values():
        if lair.spire_sprite in lst:
            lst.remove(lair.spire_sprite)
    lair.spires[quiet].append(lair.spire_sprite)
    lair.ground.texture = art_lairs.ground(lair.kind, quiet)
    lair.glow.visible = not quiet


def _viewers(game):
    """The survivors playing on this computer (split screen: everyone on the couch)."""
    if getattr(game, "local", False):
        return [s.p for s in getattr(game, "slots", [])]
    return [game.me] if game.me else []


def hint(game, p, inter):
    """The line under the hotbar next to an altar ('' if not next to one)."""
    lair = near_altar(game, p)
    if not lair:
        return ""
    st = _state(game)
    if beaten(st, lair):
        return f"The lair of {lair.name} lies quiet - you beat it"
    if len(game.over.bosses):
        return f"{game.over.bosses[0].info['name']} is awake - no waking another"
    hurt = "  (still wounded)" if lair.hp is not None else ""
    return f"{inter}  WAKE {lair.name} - it rises right here{hurt}"


def hud_line(game):
    """(text, colour, bold) for the boss line under the clock."""
    out = [b for b in game.over.bosses if b.state != "flee"]
    if out:
        return f"{out[0].info['name']} IS AWAKE", (255, 110, 90), True
    if game.boss_night:
        return "A BOSS WAKES TONIGHT", (255, 110, 90), True
    n = max(1, game.boss_day - game.day)
    left = len(asleep(game))
    when = f"one stirs in {n} night{'s' if n > 1 else ''}"
    return f"Bosses asleep: {left}  -  {when}", (200, 170, 160), False


def visuals(game, dt):
    st = _state(game)
    if not st:
        return
    for lair in st.lairs.values():
        _refresh_one(st, lair, beaten(st, lair))
    # the gloom: a boss out in the daytime darkens the sky (folded into game.darkness)
    target = GLOOM if len(game.over.bosses) else 0.0
    g = getattr(game, "boss_gloom", 0.0)
    step = GLOOM_RATE * dt
    game.boss_gloom = min(target, g + step) if target > g else max(target, g - step)
    if game.state != "playing":
        return
    # "You found the lair of..."
    pad = "B" if game.use_pad else "E"
    if getattr(game, "local", False):
        pad = "E / B"
    for p in _viewers(game):
        if not p or not p.alive or p.layer != "over":
            continue
        for lair in st.lairs.values():
            if lair.kind in st.found or _dist(p.pos, lair.pos) > FOUND_RADIUS:
                continue
            st.found.add(lair.kind)
            if beaten(st, lair):
                msg = f"The lair of {lair.name} - quiet now. You beat it."
            else:
                msg = f"You found the lair of {lair.name}. Wake it at the altar when you're ready ({pad})."
            game.say(msg, 8, to=p)
    # embers rising off every live spire near a viewer, a thin grey smoke off the quiet ones
    if not getattr(game, "_fx_pool", None):
        return
    eyes = [p.pos for p in _viewers(game) if p and p.layer == "over"]
    if not eyes:
        return
    rnd = random.random
    for lair in st.lairs.values():
        if min(_dist(e, lair.spire) for e in eyes) > EMBER_SIGHT:
            continue
        sx, sy = lair.spire
        if lair.quiet:
            if rnd() < dt * 2:
                game.fx_spawn("over", sx + (rnd() - 0.5) * 16, sy + (rnd() - 0.5) * 16, SPIRE_TOP * 0.8, 0, 0,
                              18 + rnd() * 10, 4.0, 9 + rnd() * 5, (110, 110, 112), 0.35, 0, 0.1, 3.0, False)
            continue
        col = art_lairs.colours(lair.kind)[1]
        for _ in range(int(dt * 26 + rnd())):
            game.fx_spawn("over", sx + (rnd() - 0.5) * 30, sy + (rnd() - 0.5) * 30, SPIRE_TOP * (0.55 + rnd() * 0.45),
                          (rnd() - 0.5) * 14, (rnd() - 0.5) * 14, 70 + rnd() * 80, 4.0 + rnd() * 3.0, 5 + rnd() * 6,
                          col, 0.55 if lair.kind == "wraith" else 0.95, -4.0, 0.15, -0.6, True)
        if rnd() < dt * 6:                    # motes drifting round the altar
            a = rnd() * math.tau
            game.fx_spawn("over", lair.x + math.cos(a) * 60, lair.y + math.sin(a) * 60, 10 + rnd() * 30, 0, 0,
                          12 + rnd() * 12, 2.0, 3 + rnd() * 2, col, 0.8, 0, 0.3, 0, True)


def draw3d(game, L, vl, stage="props"):
    if vl != "over":
        return
    st = _state(game)
    if not st:
        return
    if stage == "ground":
        game.flat(st.ground)
        return
    if stage != "props":
        return
    dk = game.darkness
    glow = (game.ctx.SRC_ALPHA, game.ctx.ONE)
    for lair in st.lairs.values():
        spire = f"lair_spire_{lair.kind}" + ("_quiet" if lair.quiet else "")
        altar = "lair_altar_quiet" if lair.quiet else f"lair_altar_{lair.kind}"
        lst = lair.spires[bool(lair.quiet)]
        game.mesh(lst, spire)
        game.mesh(lair.altars, altar)
        if dk > 0.05 and not lair.quiet:         # the runes and embers shine through the night
            game.mesh(lst, spire, blend=glow, glow=True)
            game.mesh(lair.altars, altar, blend=glow, glow=True)
    game.mesh(st.bones, "lair_bones")


def debug_spot(game, kind):
    """A good screenshot spot in front of a lair's altar (tools / tests)."""
    lair = lair_of(game, kind)
    return (lair.x - lair.ux * 190, lair.y - lair.uy * 190) if lair else game.centre


biomes.register(biomes.Biome(
    NAME, title="Boss lairs", order=90, region=False, legacy=True,
    gen_surface=gen_surface, build_ok=build_ok, save=save, load=load, visuals=visuals, draw3d=draw3d,
))
