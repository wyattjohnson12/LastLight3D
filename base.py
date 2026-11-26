"""
base.py - YOUR BASE: base areas, the Base Flag, and resources that don't grow back where you cleared them.

What's here:
  * Base areas. Every building you place (walls, fires, benches, bins, turrets, traps... anything)
    claims a circle of BASE_RADIUS around it, and a Base Flag claims a bigger one (FLAG_RADIUS).
    Nothing grows back inside a base, and wild animals don't wander in from the wild there either.
  * A spot a survivor cleared stays clear. A chopped tree leaves a stump you can walk over and build on;
    mined rocks, ores, reeds and glowcaps just vanish. They never come back in the same place.
    So the world doesn't run dry, a used-up node turns up again after its "regrow" time (settings.NODES)
    somewhere ELSE: a random open spot in the wild (swamp plants in the Mire, cave ores in the cave),
    never inside a base, never next to a building, a survivor, another node or a spot someone cleared.
    (Berry bushes and beehives are only picked, not destroyed, so they still fill up again in place.)
  * The Base Flag (Supplies tab: 4 wood, 6 fiber, 2 berries). A tall red banner that marks your base -
    you respawn next to it, and there is only one: planting a new one takes the old one down (it goes
    back in your backpack). With no flag the base is wherever most of your buildings are.
  * The base marker: a gold "BASE 12m" tag over the flag, a beam of light above it, and an arrow on the
    edge of the screen pointing home when it's out of sight (in first person too).

Co-op: the host decides where nodes reappear. Moved nodes travel in the snapshot as "nm" rows next to the
usual node states ("n"); the flag is an ordinary building ("st"), and base areas are worked out from the
buildings on every computer, so clients see the same base, marker and flag.
Saves: "base" holds the moved nodes and the cleared spots; older saves load fine (their regrowing nodes
just turn up somewhere else).
"""
import math
import random

import arcade

import art_flag
from settings import *
from world import LAYERS as LAYERS_ORDER

BASE_RADIUS = 300            # every building claims this much ground around it
FLAG_RADIUS = 480            # ...and a Base Flag claims this much
CLUSTER_LINK = 360           # buildings closer than this belong to the same base (for the marker)
PLAYER_GAP = 480             # resources never pop up this close to a survivor
CLEARED_GAP = 70             # ...or this close to a spot someone cleared
CLEARED_KEEP = 3000          # how many cleared spots we remember (oldest are forgotten first)
TRY_EVERY = 0.35             # seconds between attempts to put a used-up node back somewhere
SPOT_TRIES = 30              # random spots tried per attempt
NODE_RADIUS = {"tree": 46, "rock": 34, "iron": 34, "coal": 34, "crystal": 34, "bush": 28,
               "reeds": 16, "glowcap": 16}
_CELL = 128                  # grid for the cleared-spot lookup

ITEMS["base_flag"] = {"name": "Base Flag", "kind": "build", "hp": 120,
                      "desc": "Marks your base: a gold arrow always points home. You respawn here, and nothing "
                              "grows back nearby. Only one - planting a new flag moves your base."}
CRAFT_TABS["Supplies"].append(R("base_flag", {"wood": 4, "fiber": 6, "berries": 2}))
RECIPES[:] = [r for tab in CRAFT_TABS.values() for r in tab]   # same list object, crafting indexes in tab order


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Base:
    """Mixed into the game window (like defenses.py / swamp.py)."""

    # ------------------------------------------------------------------ setup / bookkeeping
    def base_setup(self):
        """Called from setup(): a fresh world remembers nothing."""
        self.cleared = {}            # (layer, cx, cy) -> [(x, y), ...] spots survivors cleared
        self.cleared_order = []      # same spots, oldest first (to forget the oldest)
        self.moves_ver = 0           # bumps whenever a node moves (co-op: resend the "nm" rows)
        self.sent_moves_ver = -1
        self.respawn_try_t = 0.0
        self._base_cache = None

    def _cleared_key(self, layer, x, y):
        return layer, int(x // _CELL), int(y // _CELL)

    def remember_cleared(self, layer, x, y):
        if not hasattr(self, "cleared"):
            self.base_setup()
        self.cleared.setdefault(self._cleared_key(layer, x, y), []).append((x, y))
        self.cleared_order.append((layer, x, y))
        while len(self.cleared_order) > CLEARED_KEEP:
            ly, ox, oy = self.cleared_order.pop(0)
            lst = self.cleared.get(self._cleared_key(ly, ox, oy))
            if lst and (ox, oy) in lst:
                lst.remove((ox, oy))

    def near_cleared(self, layer, p, gap=CLEARED_GAP):
        cx, cy = int(p[0] // _CELL), int(p[1] // _CELL)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in self.cleared.get((layer, cx + dx, cy + dy), ()):
                    if _dist(p, q) < gap:
                        return True
        return False

    # ------------------------------------------------------------------ base areas
    def _base_info(self):
        """{layer: {"circles": [(x, y, r)], "home": (x, y) or None}} - cached until a building changes."""
        c = self._base_cache
        if c is not None and c[0] == self.struct_ver:
            return c[1]
        info = {}
        for layer in self.layers:
            builds = [s for s in self.structs.values() if s.layer == layer]
            circles = [(s.center_x, s.center_y, FLAG_RADIUS if s.kind == "base_flag" else BASE_RADIUS)
                       for s in builds]
            home = None
            flags = [s for s in builds if s.kind == "base_flag"]
            if flags:
                home = flags[0].position
            elif builds:   # no flag: the middle of the biggest group of buildings
                left = list(builds)
                best = []
                while left:
                    group = [left.pop()]
                    i = 0
                    while i < len(group):
                        g = group[i]
                        near = [s for s in left if _dist(s.position, g.position) < CLUSTER_LINK]
                        for s in near:
                            left.remove(s)
                        group += near
                        i += 1
                    if len(group) > len(best):
                        best = group
                home = (sum(s.center_x for s in best) / len(best), sum(s.center_y for s in best) / len(best))
            info[layer] = {"circles": circles, "home": home}
        self._base_cache = (self.struct_ver, info)
        return info

    def in_base(self, pos, layer="over", pad=0.0):
        """Is this spot inside (or within `pad` of) a base area?"""
        x, y = pos
        for bx, by, r in self._base_info().get(layer, {}).get("circles", ()):
            rr = r + pad
            if (x - bx) ** 2 + (y - by) ** 2 < rr * rr:
                return True
        return False

    def base_home(self, layer="over"):
        """Where 'home' is on a layer: the Base Flag, else the middle of the biggest group of buildings."""
        return self._base_info().get(layer, {}).get("home")

    def base_flag(self):
        return next((s for s in self.structs.values() if s.kind == "base_flag"), None)

    def on_built(self, p, item):
        super().on_built(p, item)
        if item != "base_flag":
            return
        new = max((s for s in self.structs.values() if s.kind == "base_flag"), key=lambda s: s.sid)
        old = [s for s in self.structs.values() if s.kind == "base_flag" and s is not new]
        for s in old:
            self.remove_structure(s)
            self.give(p, "base_flag")
        if old:
            self.say("Base moved! The old flag came down - it's back in your backpack.", 4, to=p)
        else:
            self.say("Base Flag planted! The gold arrow points home, nothing grows back near it, "
                     "and you respawn here.", 5, to=p)

    # ------------------------------------------------------------------ used-up nodes
    def node_used_up(self, n):
        """A node was chopped / mined out (host). Its spot stays clear; it'll turn up somewhere else."""
        self.remember_cleared(n.layer, *n.base)
        t = TREE_REGROW if n.kind == "tree" else NODES[n.kind]["regrow"]
        if not any(item[1] is n for item in self.regrow):
            self.regrow.append([float(t), n])

    def fix_respawn_queue(self):
        """After loading: anything chopped or mined out that isn't waiting to come back yet, is now.
        (Saves from before base.py kept tree stumps on their own timers.)"""
        queued = {id(item[1]) for item in self.regrow}
        for n in self.nodes:
            if id(n) in queued or n.kind in ("bush", "hive"):
                continue
            if n.state == "stump" or (n.state == "gone" and n.kind != "tree"):
                self.regrow.append([max(0.0, float(n.timer)), n])

    def update_respawns(self, dt):
        """Host / solo: count down used-up nodes, and every so often put one back somewhere new."""
        due = []
        for item in self.regrow:
            item[0] -= dt
            if item[0] <= 0:
                due.append(item)
        self.respawn_try_t -= dt
        if not due or self.respawn_try_t > 0:
            return
        self.respawn_try_t = TRY_EVERY
        item = random.choice(due)
        n = item[1]
        spot = self.find_node_spot(n)
        if spot is None:
            item[0] = random.uniform(5, 15)      # nowhere good right now - try again later
            return
        self.regrow.remove(item)
        self.respawn_node(n, *spot)

    def _spot_candidate(self, n, L):
        r = random
        if n.layer == "cave":
            if not len(L.ground):
                return None
            g = L.ground[r.randrange(len(L.ground))]
            return g.center_x + r.uniform(-8, 8), g.center_y + r.uniform(-8, 8)
        if n.kind in ("reeds", "glowcap"):
            blobs = getattr(self, "swamp_blobs", None)
            if not blobs:
                return None
            x, y, rad = r.choice(blobs)
            a, d = r.uniform(0, math.tau), math.sqrt(r.random()) * max(10, rad - 20)
            return x + math.cos(a) * d, y + math.sin(a) * d
        return r.uniform(100, L.size - 100), r.uniform(100, L.size - 100)

    def spot_ok(self, kind, layer, p, rad=None, ignore=None):
        """Could a `kind` node grow at p? Not in a base, not near survivors, buildings, nodes or cleared spots."""
        L = self.layers[layer]
        rad = NODE_RADIUS.get(kind, 30) if rad is None else rad
        x, y = p
        if not (80 < x < L.size - 80 and 80 < y < L.size - 80):
            return False
        if self.in_base(p, layer, pad=rad):
            return False
        if any(q.layer == layer and _dist(q.pos, p) < PLAYER_GAP for q in self.players.values()):
            return False
        if self.near_cleared(layer, p):
            return False
        exits = [e.position for e in L.exits]
        if layer == "over":
            if _dist(p, self.centre) < 170 + rad:
                return False
            if kind == "iron" and _dist(p, self.centre) < 500:
                return False
            if any(_dist(p, e) < 150 for e in exits):
                return False
            swampy = self.in_swamp(p)
            if kind in ("reeds", "glowcap") and not swampy:
                return False
            if swampy and self.in_bog_pool(p):
                return False
        else:
            near = min((_dist(p, e) for e in exits), default=9999)
            if near < 160 or (kind == "crystal" and near < 650):
                return False
        side = int(2 * rad + (52 if layer == "over" else 30))
        probe = arcade.SpriteSolidColor(side, side, center_x=x, center_y=y)
        lists = [L.solid, L.trees, L.rocks, L.bushes, L.builds, L.huts, L.traps, L.exits, L.ponds]
        if layer == "cave":
            lists.append(L.walls)
        hits = arcade.check_for_collision_with_lists(probe, lists)
        return not any(h is not ignore for h in hits)

    def find_node_spot(self, n):
        """A random good spot for a used-up node to turn up again: (x, y) or None."""
        L = self.layers[n.layer]
        for _ in range(SPOT_TRIES * (4 if n.layer == "cave" else 1)):    # caves are cramped: look harder
            p = self._spot_candidate(n, L)
            if p and self.spot_ok(n.kind, n.layer, p, ignore=n):
                return p
        return None

    def place_node(self, n, x, y, variant=None):
        """Move a node (and its trunk, glow and beehive) to a new spot. Host, clients and loading."""
        n.position = (x, y)
        n.base = (x, y)
        n.moved = True
        if variant is not None:
            n.variant = variant
        L = self.layers[n.layer]
        trunk = getattr(L, "trunk_of", {}).get(id(n))      # view3d.py's 3D trunk under the canopy
        if trunk is not None:
            trunk.position = (x, y)
        for node, g in getattr(self, "swamp_glows", ()):    # glowcaps carry their glow along
            if node is n:
                g.position = (x, y)
        if n.kind == "tree" and n.hive is not None:
            a = random.Random(n.idx).uniform(0, math.tau)
            n.hive.position = n.hive.base = (x + math.cos(a) * 24, y + math.sin(a) * 24)
            n.hive.moved = True
        if n.kind == "tree" and n.state == "full":
            import art
            n.texture = art.tree(n.variant)
            n.angle = n.base_angle
        self.moves_ver += 1

    def respawn_node(self, n, x, y):
        """Host: a used-up node grows again at (x, y)."""
        variant = None
        if n.kind == "tree":
            from swamp import SWAMP_TREE
            swampy = self.in_swamp((x, y))
            variant = (SWAMP_TREE if swampy else 0) + random.randint(0, 2)
            n.base_angle = 0.0 if swampy else random.uniform(0, 360)
        self.place_node(n, x, y, variant)
        n.hp = NODES[n.kind]["hp"]
        n.timer = 0.0
        self.set_node_state(n, "full")
        if n.kind == "tree" and n.hive is not None:    # the bees move in with it; honey takes a while
            self.set_node_state(n.hive, "empty")
            n.hive.timer = HIVE_REGROW
        self.nodes_ver += 1

    # ------------------------------------------------------------------ co-op
    def node_moves_rows(self, force=False):
        """Rows for the snapshot ("nm"): [idx, x, y, variant] for every node that moved. None = no change."""
        if not force and self.moves_ver == self.sent_moves_ver:
            return None
        self.sent_moves_ver = self.moves_ver
        return [[n.idx, round(n.base[0], 1), round(n.base[1], 1), n.variant, round(n.base_angle, 1)]
                for n in self.nodes if getattr(n, "moved", False)]

    def apply_node_moves(self, rows):
        for row in rows or ():
            idx, x, y, variant = row[:4]
            if 0 <= idx < len(self.nodes):
                n = self.nodes[idx]
                if len(row) > 4:
                    n.base_angle = row[4]
                if n.base != (x, y) or n.variant != variant:
                    self.place_node(n, x, y, variant)

    # ------------------------------------------------------------------ saves
    def base_save(self):
        li = LAYERS_ORDER.index
        return {"moved": [[n.idx, round(n.base[0], 1), round(n.base[1], 1), n.variant, round(n.base_angle, 1)]
                          for n in self.nodes if getattr(n, "moved", False)],
                "cleared": [[li(ly), round(x, 1), round(y, 1)] for ly, x, y in getattr(self, "cleared_order", [])]}

    def base_load(self, data):
        """Before the node states are loaded: put moved nodes in their new spots."""
        data = data or {}
        for row in data.get("moved", []):
            idx, x, y, variant = row[:4]
            if 0 <= idx < len(self.nodes):
                n = self.nodes[idx]
                if len(row) > 4:
                    n.base_angle = float(row[4])
                self.place_node(n, float(x), float(y), int(variant))
        for li, x, y in data.get("cleared", []):
            if 0 <= li < len(LAYERS_ORDER):
                self.remember_cleared(LAYERS_ORDER[li], float(x), float(y))

    # ------------------------------------------------------------------ drawing
    def tick_flags(self):
        """The banner flaps (swap between its pictures)."""
        f = int(getattr(self, "flame_t", 0.0) * 5) % art_flag.FRAMES
        for s in self.structs.values():
            if s.kind == "base_flag":
                tex = art_flag.flag(f)
                if s.texture is not tex:
                    s.texture = tex

    def draw_offscreen_friends(self):
        """Called by ui.on_draw (GUI space, before the HUD): the base marker, then the friends' arrows."""
        self.draw_base_marker()
        super().draw_offscreen_friends()

    def draw_base_marker(self):
        me = self.me
        if me is None or self.state != "playing" or getattr(self, "cut", None):
            return
        vl = self.view_layer
        home = self.base_home(vl)
        if home is None:
            return
        import ui
        W, H = ui.W, ui.H
        self.tick_flags()
        flag = self.base_flag()
        hx, hy = home
        view = self.view_pos()
        metres = int(_dist(view, home) / GRID)
        if flag is not None and flag.layer == vl:
            self.draw_flag_beacon(flag)
        if metres < 3:
            return
        s = self.project(hx, hy, 130 if flag is not None and flag.layer == vl else 40)
        if s and 20 < s[0] < W - 20 and 110 < s[1] < H - 150:
            art_flag.draw_label(self, s[0], s[1], metres)
            return
        ang = math.atan2(hy - view[1], hx - view[0])     # world direction home
        if self.fp_on():                                 # first person: relative to where you look
            ang = math.pi / 2 + (ang - self.fp_yaw)
        art_flag.draw_arrow(self, ang, metres, W, H)

    def draw_flag_beacon(self, flag):
        """Hook for the 3D view: a column of light over the flag (stronger at night)."""
        dk = getattr(self, "darkness", 0.0) if flag.layer == "over" else 0.6
        art_flag.draw_beacon(self, flag.center_x, flag.center_y, 0.45 + 0.55 * dk)


