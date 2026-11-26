"""
swamp.py - THE MIRE: a swamp biome in one corner of the overworld, and its boss, THE MIRE LURKER.

What's here:
  * The Mire itself: dark bog ground, murky pools that slow you down, drooping willows and dead
    trees, Marsh Reeds and glowing Glowcap mushrooms (they light up at night) to gather.
  * Drowned: a swamp zombie that rises at night in the Mire. Drops reeds and glowcaps.
  * New gear: Mire Mask (head - filters spore gas), Swamp Tonic, Reed Arrows, Thornroot Whip.
  * THE MIRE LURKER joins the boss rotation (before the Inferno Colossus):
      SPORE BURST     - lobs spore pods that burst into poison gas clouds
      GRASPING ROOTS  - roots burst up under survivors and hold them in place
      SUBMERGE        - sinks into the mud and erupts under someone
      ...and it heals while it stands in the swamp, so lure it out.

The map is built from the world seed on every computer (host and clients alike), so the Mire is
in the same place for everyone and the slow-down in pools works locally. Everything that changes
the world (bosses, hazards, harvesting, snaring) runs on the host and reaches clients through the
normal snapshots, plus one per-player event ("snare") for the roots.

This module is imported FIRST by main.py: it adds its items, recipes, nodes, zombie and boss to the
tables in settings.py before ui.py builds the crafting tabs.
"""
import math
import random

import arcade

import art
from settings import *
from world import Hazard, Node

# =========================================================================== data (added to settings.py's tables)
SWAMP_TREE = 10              # tree variants >= this are swamp trees (see art_swamp.py)
SWAMP_DIST = 1020            # how far from the map centre the Mire sits
MIRE_REGEN = 3.0             # boss health per second while it stands in the swamp
POOL_SPEED = 0.6             # walking speed in a bog pool
MUD_SPEED = 0.9              # ...and anywhere else in the Mire
TOXIN_SOAK = 0.35            # Mire Mask: spore gas does this much damage
ROOT_HOLD = 1.6              # seconds the Grasping Roots hold you (half with a Mire Mask)

ITEMS.update({
    "reeds": {"name": "Marsh Reeds", "kind": "material",
              "desc": "Grow in the Mire (the swamp). Light and strong: arrows, masks, whips."},
    "glowcap": {"name": "Glowcap", "kind": "material",
                "desc": "A glowing swamp mushroom - easy to find at night. Tonics and masks."},
    "mire_heart": {"name": "Mire Heart", "kind": "material", "desc": "Dropped by the Mire Lurker. It still beats, slowly."},
    "swamp_tonic": {"name": "Swamp Tonic", "kind": "food", "health": 35, "energy": 30, "thirst": 15,
                    "desc": "Glowcap brew from a campfire. +35 health, +30 energy, +15 thirst."},
    "mire_mask": {"name": "Mire Mask", "kind": "armor", "slot": "head", "armor": 4, "warmth": 1, "toxin": 1,
                  "desc": "Armor 4, warmth 1 (the best helmet). Filters the air: spore gas does a third of the damage, "
                          "and roots hold you half as long."},
    "thornroot_whip": {"name": "Thornroot Whip", "kind": "weapon", "damage": 13, "reach": 100, "cooldown": 0.42,
                       "slow": 1, "desc": "13 damage, very long reach. Thorny roots tangle enemies so they slow down."},
})
NODES.update({
    "reeds": {"gives": "reeds", "hp": 2, "regrow": 70},
    "glowcap": {"gives": "glowcap", "hp": 2, "regrow": 110},
})
ZOMBIES["drowned"] = (11, 64, 11, 1.2)       # swamp zombie: slow, soggy, tough
BOSSES["mire"] = {
    "name": "THE MIRE LURKER", "hp": 245, "speed": 62, "damage": 20, "radius": 50,
    "tag": "The swamp is its body. Drag it out of the mud.",
    "moves": ["SPORE BURST - lobs spore pods that burst into poison gas. Stay out of the purple.",
              "GRASPING ROOTS - roots burst up under you and hold you still. Watch the ground, keep moving.",
              "SUBMERGE - sinks into the mud and erupts under someone. It HEALS in the swamp: lure it out!"],
    "drops": {"mire_heart": 2, "reeds": 8, "glowcap": 4},
}
if "mire" not in BOSS_ORDER:
    BOSS_ORDER.insert(BOSS_ORDER.index("colossus") if "colossus" in BOSS_ORDER else len(BOSS_ORDER), "mire")
OLD_BOSS_ORDER = ["titan", "brood", "wraith", "colossus"]   # saves from before the Mire Lurker

CRAFT_TABS["Tools"].append(R("thornroot_whip", {"mire_heart": 1, "reeds": 6, "iron_ingot": 2}, "workbench"))
CRAFT_TABS["Armor"].append(R("mire_mask", {"reeds": 4, "leather": 2, "glowcap": 1}, "workbench"))
CRAFT_TABS["Supplies"].append(R("arrows", {"reeds": 2, "stone": 1}, n=8))
CRAFT_TABS["Supplies"].append(R("swamp_tonic", {"glowcap": 2, "water": 1}, "campfire"))
RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]   # same list object, crafting indexes in tab order

import art_swamp  # noqa: E402  (after the tables: registers the new art)


def remap_boss_num(n, saved_order):
    """A save made with a different boss rotation: keep the same NEXT boss (and how tough it is)."""
    old = list(saved_order or OLD_BOSS_ORDER)
    if old == BOSS_ORDER or not old:
        return n
    cycle, i = divmod(int(n), len(old))
    kind = old[i]
    if kind not in BOSS_ORDER:
        return n
    return cycle * len(BOSS_ORDER) + BOSS_ORDER.index(kind)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# =========================================================================== the mixin
class Swamp:
    """Mixed into the game window (like pets.py / repair.py)."""

    SWAMP_HAZARDS = ("spore", "gas", "roots", "vines", "erupt")

    # ------------------------------------------------------------------ building the Mire
    def build_swamp(self):
        """Called by setup() right after build_world(). Uses its own random stream from the seed, and only
        ADDS nodes at the end of self.nodes, so every saved game's node numbers stay the same."""
        r = random.Random(self.seed * 13 + 5)
        over = self.over
        centre = (WORLD_SIZE / 2, WORLD_SIZE / 2)
        a = r.uniform(0, math.tau)
        lim = 640
        cx = max(lim, min(WORLD_SIZE - lim, centre[0] + math.cos(a) * SWAMP_DIST))
        cy = max(lim, min(WORLD_SIZE - lim, centre[1] + math.sin(a) * SWAMP_DIST))
        blobs = [(cx, cy, 310.0)]
        for _ in range(9):
            b = r.uniform(0, math.tau)
            d = r.uniform(140, 360)
            rad = r.uniform(170, 260)
            x, y = cx + math.cos(b) * d, cy + math.sin(b) * d
            if _dist((x, y), centre) - rad < 420 or not (rad < x < WORLD_SIZE - rad and rad < y < WORLD_SIZE - rad):
                continue
            blobs.append((x, y, rad))
        self.swamp_blobs = blobs
        self.swamp_centre = (cx, cy)
        for i, (x, y, rad) in enumerate(blobs):
            s = arcade.Sprite(art_swamp.ground(i % 3), center_x=x, center_y=y)
            s.scale = rad * 2.4 / 512
            s.angle = r.uniform(0, 360)
            over.ground.append(s)

        def inside(margin=0):
            for _ in range(40):
                x, y, rad = r.choice(blobs)
                b = r.uniform(0, math.tau)
                d = math.sqrt(r.random()) * max(10, rad - margin)
                p = (x + math.cos(b) * d, y + math.sin(b) * d)
                if 80 < p[0] < WORLD_SIZE - 80 and 80 < p[1] < WORLD_SIZE - 80:
                    return p
            return None

        keep_clear = [(s.center_x, s.center_y, 150) for s in list(over.ponds) + list(over.exits)]
        self.swamp_pools = []
        for i in range(12):
            p = inside(80)
            if p is None or any(_dist(p, (x, y)) < rr for x, y, rr in keep_clear):
                continue
            if any(_dist(p, (x, y)) < 150 for x, y, _, _ in self.swamp_pools):
                continue
            s = arcade.Sprite(art_swamp.pool(i % 3), center_x=p[0], center_y=p[1])
            over.ground.append(s)
            self.swamp_pools.append((p[0], p[1], 82.0, 52.0))
        for i in range(140):
            p = inside()
            if p:
                over.decor.append(arcade.Sprite(art_swamp.decor(r.randint(0, 3)), center_x=p[0], center_y=p[1]))

        # the trees already standing here turn into swamp trees (same nodes, just a new look)
        for n in over.trees:
            if n.kind == "tree" and self.in_swamp(n.position):
                n.variant = SWAMP_TREE + n.idx % 3
                n.angle = n.base_angle = 0.0
                if n.state == "full":
                    n.texture = art.tree(n.variant)

        def free(p, rad):
            if any(_dist(p, (x, y)) < rr for x, y, rr in keep_clear):
                return False
            if any(abs(p[0] - x) < rx + rad * 0.5 and abs(p[1] - y) < ry + rad * 0.5 for x, y, rx, ry in self.swamp_pools):
                return False
            return all(_dist(p, n.base) > rad + 26 for n in self.nodes if n.layer == "over"
                       and abs(n.base[0] - p[0]) < 200 and abs(n.base[1] - p[1]) < 200)

        def add(kind, tex, p, lst):
            n = Node(kind, tex, *p)
            n.idx = len(self.nodes)
            self.nodes.append(n)
            lst.append(n)
            over.solid.append(n)
            return n

        placed = 0
        for _ in range(26 * 5):
            if placed >= 26:
                break
            p = inside(30)
            if p and free(p, 44):
                placed += 1
                v = SWAMP_TREE + r.randint(0, 2)
                n = add("tree", art.tree(v), p, over.trees)
                n.variant = v
        self.swamp_glows = []
        for kind, count in (("reeds", 46), ("glowcap", 26)):
            placed = 0
            for _ in range(count * 5):
                if placed >= count:
                    break
                if kind == "reeds" and self.swamp_pools and r.random() < 0.55:   # reeds love the pool edges
                    x, y, rx, ry = r.choice(self.swamp_pools)
                    b = r.uniform(0, math.tau)
                    p = (x + math.cos(b) * (rx + 18), y + math.sin(b) * (ry + 16))
                else:
                    p = inside(20)
                if not p or not free(p, 16):
                    continue
                placed += 1
                if kind == "reeds":
                    add("reeds", art_swamp.reeds(), p, over.bushes)
                else:
                    n = add("glowcap", art_swamp.glowcap(), p, over.bushes)
                    g = arcade.Sprite(art.glow(56, (110, 255, 200)), center_x=p[0], center_y=p[1])
                    over.glows.append(g)
                    self.swamp_glows.append((n, g))
        self.swamp_told = False
        self.swamp_fly_t = 0.0

    # ------------------------------------------------------------------ where is the swamp?
    def in_swamp(self, pos):
        x, y = pos
        for bx, by, rad in getattr(self, "swamp_blobs", ()):
            if (x - bx) ** 2 + (y - by) ** 2 < rad * rad:
                return True
        return False

    def in_bog_pool(self, pos):
        x, y = pos
        for px, py, rx, ry in getattr(self, "swamp_pools", ()):
            if ((x - px) / rx) ** 2 + ((y - py) / ry) ** 2 < 1:
                return True
        return False

    def swamp_speed(self, p, dt):
        """Called from move_player (on whichever computer moves that survivor): roots and mud slow you."""
        held = getattr(p, "snared", 0.0)
        if held > 0:
            p.snared = held - dt
            return 0.0
        if p.layer != "over":
            return 1.0
        if self.in_bog_pool(p.pos):
            return POOL_SPEED
        return MUD_SPEED if self.in_swamp(p.pos) else 1.0

    def update_swamp(self, dt):
        """Host / solo, every frame: at night the Drowned climb out of the bog around anyone in the Mire."""
        if not self.is_night:
            return
        here = [p for p in self.alive_players("over") if self.in_swamp(p.pos)]
        self.swamp_spawn_t = getattr(self, "swamp_spawn_t", 4.0) - dt
        if not here or self.swamp_spawn_t > 0:
            return
        self.swamp_spawn_t = random.uniform(5.0, 8.0) / len(here)
        drowned = sum(1 for z in self.over.zombies if z.kind == "drowned")
        if drowned >= 4 + 2 * len(here) + self.day // 2:
            return
        p = random.choice(here)
        for _ in range(10):
            a = random.uniform(0, math.tau)
            d = random.uniform(340, 520)
            spot = (p.pos[0] + math.cos(a) * d, p.pos[1] + math.sin(a) * d)
            if self.in_swamp(spot) and all(_dist(spot, q.pos) > 300 for q in here):
                z = self.spawn_zombie("over", "drowned", spot)
                if z:
                    self.burst(z.center_x, z.center_y, (70, 64, 40), 12, 120, 4, 0.7)
                return

    def swamp_zombie_kind(self, kind, x, y, layer):
        """Night spawns in the Mire are mostly Drowned."""
        if layer == "over" and kind in ("walker", "runner") and self.in_swamp((x, y)) and random.random() < 0.75:
            return "drowned"
        return kind

    def snare_player(self, p, secs):
        if p.gear("toxin"):
            secs *= 0.5
        if self._emit(["snare", round(secs, 2)], p):
            p.snared = max(getattr(p, "snared", 0.0), secs)

    def swamp_event(self, ev):
        """Client side: per-player events from the host."""
        if ev[0] == "snare" and self.me:
            self.me.snared = max(getattr(self.me, "snared", 0.0), float(ev[1]))

    # ------------------------------------------------------------------ the Mire Lurker (host only)
    def mire_abilities(self, b, tgt, alive, d):
        T = b.timers
        T.setdefault("r", 0.5)
        T.setdefault("fx", 0.3)
        if T["r"] <= 0:             # heals in the swamp
            T["r"] = 0.5
            if self.in_swamp(b.position) and b.hp < b.max_hp:
                b.hp = min(b.max_hp, b.hp + MIRE_REGEN * b.max_hp / b.info["hp"] * 0.5)   # tougher cycles heal faster
                self.burst(b.center_x, b.center_y, (120, 230, 110), 4, 70, 3, 0.7)
                if not getattr(b, "regen_told", False):
                    b.regen_told = True
                    self.say(f"{b.info['name']} is HEALING in the swamp! Lure it out onto dry ground.", 4)
        if T["a"] <= 0 and d < 620:
            T["a"] = 7.0
            for p in sorted(alive, key=lambda q: _dist(q.pos, b.position))[:2]:
                if _dist(p.pos, b.position) > 700:
                    continue
                for k in range(3):
                    x = p.pos[0] + (random.uniform(-110, 110) if k else 0)
                    y = p.pos[1] + (random.uniform(-110, 110) if k else 0)
                    fl = random.uniform(1.1, 1.5)
                    self.hazards.append(Hazard("spore", x, y, 64, tele=fl, dmg=8, vx=b.center_x, vy=b.center_y,
                                               a=fl, owner=b))
            self.play("laser", 0.3, at=b.position, layer="over")
            self.burst(b.center_x, b.center_y, (180, 110, 220), 10, 120, 4, 0.6)
        elif T["b"] <= 0:
            T["b"] = 9.0
            for p in alive:
                if _dist(p.pos, b.position) < 650:
                    self.hazards.append(Hazard("roots", p.pos[0], p.pos[1], 52, tele=1.1, dmg=10, owner=b))
            self.play("mine", 0.4, at=b.position, layer="over")
        elif T["c"] <= 0 and d < 750:
            T["c"] = 13.0
            b.state, b.state_t, b.target = "submerge", 0.0, None
            self.play("roar", 0.3, at=b.position, layer="over")
            self.burst(b.center_x, b.center_y, (70, 64, 40), 24, 160, 5, 0.9)

    def mire_submerge(self, b, dt, alive):
        """Sinks (0.8s), a bubbling patch moves under someone, then it bursts out (at 2.1s)."""
        b.state_t += dt
        t = b.state_t
        if t < 0.8:
            b.alpha = int(255 * max(0.0, 1 - t / 0.8))
            if random.random() < 0.4:
                self.burst(b.center_x, b.center_y, (70, 64, 40), 3, 90, 4, 0.6)
            return
        if b.target is None:
            p = min(alive, key=lambda q: _dist(q.pos, b.position)) if alive else None
            spot = p.pos if p else b.position
            b.target = (max(100, min(WORLD_SIZE - 100, spot[0])), max(100, min(WORLD_SIZE - 100, spot[1])))
            b.alpha = 0
            self.hazards.append(Hazard("erupt", b.target[0], b.target[1], 92, tele=1.3, dmg=b.damage * 0.9, owner=b))
        if t >= 2.1:
            b.position = b.target
            b.alpha = 255
            b.state = "walk"
            b.attack_cd = max(b.attack_cd, 0.8)

    def swamp_hazard(self, h, dt, alive):
        """_update_hazards hands every swamp hazard here. Returns new hazards it leaves behind."""
        if h.tele > 0:
            h.tele -= dt
            return self._swamp_trigger(h, alive) if h.tele <= 0 else []
        h.t -= dt
        if h.kind == "gas":
            h.tick -= dt
            if h.tick <= 0:
                h.tick = 0.5
                for p in alive:
                    if _dist(p.pos, (h.x, h.y)) < h.r + 10:
                        self.hurt_player(p, h.dmg * 0.5 * (TOXIN_SOAK if p.gear("toxin") else 1.0))
        if h.t <= 0:
            h.done = True
        return []

    def _swamp_trigger(self, h, alive):
        h.done = True
        self.fx_layer = "over"
        if h.kind == "spore":
            self.burst(h.x, h.y, (180, 110, 220), 14, 160, 4, 0.8)
            self.play("boom", 0.2, at=(h.x, h.y), layer="over")
            for p in alive:
                if _dist(p.pos, (h.x, h.y)) < h.r * 0.6 + 12:
                    self.hurt_player(p, h.dmg * (TOXIN_SOAK if p.gear("toxin") else 1.0))
            return [Hazard("gas", h.x, h.y, h.r + 6, life=5.0, dmg=8, owner=h.owner)]
        if h.kind == "roots":
            self.burst(h.x, h.y, (96, 74, 46), 18, 150, 4, 0.7)
            self.play("hit", 0.35, at=(h.x, h.y), layer="over")
            for p in alive:
                if _dist(p.pos, (h.x, h.y)) < h.r + 10:
                    self.hurt_player(p, h.dmg)
                    self.snare_player(p, ROOT_HOLD)
                    self.say("ROOTS! You're held fast...", 1.5, to=p)
            return [Hazard("vines", h.x, h.y, h.r, life=ROOT_HOLD, owner=h.owner)]
        if h.kind == "erupt":
            self.ring(h.x, h.y, 20, h.r + 40, 0.5, (140, 200, 90))
            self.burst(h.x, h.y, (70, 64, 40), 40, 280, 6, 1.0)
            self.shake(12, 0.6)
            self.play("boom", 0.5, at=(h.x, h.y), layer="over")
            for p in alive:
                d = _dist(p.pos, (h.x, h.y))
                if d < h.r:
                    self.hurt_player(p, h.dmg * (1 - d / h.r * 0.4))
            for s in list(self.structs.values()):
                if s.layer == "over" and _dist(s.position, (h.x, h.y)) < h.r:
                    self.damage_structure(s, 40)
            if self.in_swamp((h.x, h.y)):        # the bog spits up a couple of Drowned with it
                for _ in range(2):
                    self.spawn_zombie("over", "drowned", (h.x, h.y))
        return []

    # ------------------------------------------------------------------ drawing (every computer)
    def draw_swamp_ground(self):
        """Ground part of the swamp hazards (world coordinates, called from draw_ground_hazards)."""
        pulse = 0.5 + 0.5 * math.sin(self.flame_t * 12)
        for h in self.hazards:
            if h.kind not in self.SWAMP_HAZARDS:
                continue
            if h.kind == "spore" and h.tele > 0:
                arcade.draw_circle_filled(h.x, h.y, h.r, (170, 80, 220, int(35 + 45 * pulse)))
                arcade.draw_circle_outline(h.x, h.y, h.r, (210, 140, 255, 220), 3)
            elif h.kind == "gas":
                for k in range(3):
                    wob = math.sin(self.flame_t * 2 + h.x * 0.01 + k * 2.1)
                    ox, oy = math.cos(k * 2.1 + wob) * h.r * 0.25, math.sin(k * 2.1 + wob) * h.r * 0.25
                    arcade.draw_circle_filled(h.x + ox, h.y + oy, h.r * (0.75 + 0.08 * wob),
                                              (150, 90, 190, int(60 * min(1.0, h.t))))
                arcade.draw_circle_filled(h.x, h.y, h.r * 0.45, (190, 230, 120, int(70 * min(1.0, h.t))))
            elif h.kind == "roots" and h.tele > 0:
                k = 1 - h.tele / 1.1
                arcade.draw_circle_filled(h.x, h.y, h.r, (110, 70, 30, int(40 + 50 * pulse)))
                arcade.draw_circle_outline(h.x, h.y, h.r, (180, 120, 60, 220), 3)
                for j in range(8):
                    a = j / 8 * math.tau + 0.4
                    arcade.draw_line(h.x + math.cos(a) * h.r, h.y + math.sin(a) * h.r,
                                     h.x + math.cos(a) * h.r * (1 - k * 0.9), h.y + math.sin(a) * h.r * (1 - k * 0.9),
                                     (60, 40, 20, 220), 4)
            elif h.kind == "vines":
                for j in range(9):
                    a = j / 9 * math.tau
                    arcade.draw_line(h.x + math.cos(a) * h.r * 0.2, h.y + math.sin(a) * h.r * 0.2,
                                     h.x + math.cos(a + 0.3) * h.r, h.y + math.sin(a + 0.3) * h.r, (84, 62, 36, 230), 5)
                arcade.draw_circle_outline(h.x, h.y, h.r * 0.6, (90, 130, 50, 200), 3)
            elif h.kind == "erupt" and h.tele > 0:
                k = 1 - h.tele / 1.3
                arcade.draw_circle_filled(h.x, h.y, h.r, (60, 54, 30, int(70 + 60 * pulse)))
                arcade.draw_circle_outline(h.x, h.y, h.r * (1.3 - 0.3 * k), (150, 210, 90, 230), 3)
                for j in range(5):
                    a = j * 2.4 + self.flame_t * 3
                    arcade.draw_circle_filled(h.x + math.cos(a) * h.r * 0.5, h.y + math.sin(a) * h.r * 0.5,
                                              5 + 4 * pulse, (110, 120, 70, 200))

    def draw_swamp_air(self):
        """Spore pods arcing through the air (GUI space, called from draw_air_hazards)."""
        for h in self.hazards:
            if h.kind != "spore" or h.tele <= 0 or not h.a:
                continue
            k = max(0.0, min(1.0, 1 - h.tele / h.a))
            x = h.vx + (h.x - h.vx) * k
            y = h.vy + (h.y - h.vy) * k
            s = self.project(x, y, 30 + 260 * 4 * k * (1 - k))
            if s:
                arcade.draw_circle_filled(s[0], s[1], 11, (150, 80, 190, 240))
                arcade.draw_circle_filled(s[0] - 3, s[1] + 3, 4, (230, 190, 255, 220))

    def swamp_visuals(self, dt):
        """Every computer, every frame: glowcaps glow while they're there, fireflies, the welcome note."""
        for n, g in getattr(self, "swamp_glows", ()):
            g.visible = n.state == "full"
        me = self.me
        if not me or not me.alive or me.layer != "over" or self.state != "playing":
            return
        here = self.in_swamp(me.pos)
        if here and not self.swamp_told:
            self.swamp_told = True
            self.message, self.message_t = ("THE MIRE: mud slows you. Gather Marsh Reeds & Glowcaps. "
                                            "Beware the Drowned at night.", 6)
        self.swamp_fly_t -= dt
        if here and self.darkness > 0.3 and self.swamp_fly_t <= 0:
            self.swamp_fly_t = 0.12
            a = random.uniform(0, math.tau)
            d = random.uniform(40, 260)
            x, y = me.pos[0] + math.cos(a) * d, me.pos[1] + math.sin(a) * d
            if self.in_swamp((x, y)):
                self._burst(x, y, random.choice(((200, 255, 120), (150, 255, 200))), 1, 14, 2.2, 1.6, "over")

