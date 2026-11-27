"""
defenses.py - base defenses: the Arrow Turret, the Gate and the Lantern. Mixed into the game window.

  * Arrow Turret - shoots the nearest zombie or boss in range all by itself. Every shot uses one
    Arrow from TEAM STORAGE, so keep a Storage Bin stocked. It has health: zombies chew on it,
    the Repair Hammer fixes it.
  * Gate - a wall piece that survivors and pets walk straight through, but zombies (and wild
    beasts that respect walls) can't: they have to break it down like any other wall.
  * Lantern - a little light on a post. Zombies near it stumble along at half speed, and at night
    it lights up the ground around it.

Everything here is decided on the host (or in solo); clients get turret arrows through the normal
"shots" list in the snapshot, the team storage count through "sto", and buildings through "st".
"""
import math

import arcade

import art
import art_defenses
from settings import *
from world import Shot, dist

DEFENSE_KINDS = ("arrow_turret", "gate", "lantern")
WALK_THROUGH = ("gate",)        # built pieces that survivors & pets can walk through (zombies can't)
TURRET_RANGE = 430              # how far a turret can see (on flat ground)
TURRET_HIGH_K = 1.2             # hills.py: +this many px of range per px the turret stands above its target...
TURRET_HIGH_MAX = 170           # ...up to this much extra
TURRET_RELOAD = 1.15            # seconds between shots
TURRET_DAMAGE = 4
TURRET_WARN_EVERY = 25          # seconds between "out of arrows!" messages
LANTERN_RADIUS = 150            # zombies inside this circle are slowed
LANTERN_SLOW = 0.5              # ...to this fraction of their speed
LANTERN_LIGHT = 310             # your circle of light near a lantern at night
LANTERN_FLAME_LIFT = 20         # how high the little flame sits (inside the lantern glass)


class Defenses:
    # ------------------------------------------------------------------ bookkeeping
    def gates(self, L):
        """The gates on a layer (a sprite list of their own: they block zombies, not survivors)."""
        g = getattr(L, "gates", None)
        if g is None:
            g = L.gates = arcade.SpriteList(use_spatial_hash=True)
        return g

    def defense_blockers(self, L):
        """Extra sprite lists that stop zombies and bosses (but not survivors or pets)."""
        return [self.gates(L)]

    def add_defense(self, s, L):
        """Called from add_structure for every new building (host and clients, and when loading)."""
        if s.kind == "gate":
            self.gates(L).append(s)
        elif s.kind == "lantern":
            f = arcade.Sprite(art.flame(0), center_x=s.center_x + 8, center_y=s.center_y, scale=0.26)
            f.depth = LANTERN_FLAME_LIFT
            g = arcade.Sprite(art.glow(LANTERN_RADIUS, (255, 214, 120)), center_x=s.center_x, center_y=s.center_y)
            L.flames.append(f)
            L.glows.append(g)
            s.extras = [f, g]
        elif s.kind == "arrow_turret":
            s.reload = 0.6
            s.aim_left = False

    def defense_slow(self, z):
        """Speed multiplier for a zombie: lanterns slow down everything that walks near them."""
        for x, y in getattr(self, "_lanterns", {}).get(z.layer, ()):
            if abs(z.center_x - x) < LANTERN_RADIUS and abs(z.center_y - y) < LANTERN_RADIUS \
                    and math.hypot(z.center_x - x, z.center_y - y) < LANTERN_RADIUS:
                return LANTERN_SLOW
        return 1.0

    def near_lantern(self, pos, layer, radius=LANTERN_RADIUS):
        return any(s.kind == "lantern" and s.layer == layer and dist(s.position, pos) < radius
                   for s in self.structs.values())

    # ------------------------------------------------------------------ host: turrets fire
    def turret_reach(self, t, x, y):
        """How far turret t sees towards (x, y): farther when it stands above the target (hills.py)."""
        if t.layer != "over":
            return TURRET_RANGE
        k = (t.center_x, t.center_y)
        if getattr(t, "_hz", (None,))[0] != k:
            t._hz = (k, self.ground_height(*k))
        up = t._hz[1] - self.ground_height(x, y)
        return TURRET_RANGE + max(0.0, min(TURRET_HIGH_MAX, up * TURRET_HIGH_K))

    def _turret_target(self, t, L):
        best, bd = None, 1e9
        reach = TURRET_RANGE + TURRET_HIGH_MAX
        for e in list(L.zombies) + [b for b in L.bosses if getattr(b, "state", "") != "flee"]:
            d = dist(e.position, t.position) - e.radius
            if d < bd and d < reach and (d < TURRET_RANGE or d < self.turret_reach(t, e.center_x, e.center_y)):
                best, bd = e, d
        return best

    def _update_defenses(self, dt):
        lanterns, turrets = {}, []
        for s in self.structs.values():
            if s.kind == "lantern":
                lanterns.setdefault(s.layer, []).append((s.center_x, s.center_y))
            elif s.kind == "arrow_turret":
                turrets.append(s)
        self._lanterns = lanterns
        for t in turrets:
            t.reload = getattr(t, "reload", 0.0) - dt
            if t.reload > 0:
                continue
            L = self.layers[t.layer]
            foe = self._turret_target(t, L)
            if foe is None:
                t.reload = 0.25
                continue
            if self.storage.get("arrows", 0) <= 0:
                t.reload = 1.0
                if self.time_alive - getattr(self, "_turret_warned", -999) > TURRET_WARN_EVERY:
                    self._turret_warned = self.time_alive
                    bins = any(s.kind == "storage" for s in self.structs.values())
                    self.say("Your Arrow Turrets are out of arrows! Put Arrows into a Storage Bin."
                             if bins else "Arrow Turrets shoot Arrows from TEAM STORAGE - build a Storage Bin "
                                          "and put Arrows in it.", 4)
                continue
            self.store_take("arrows", 1)
            dx, dy = foe.center_x - t.center_x, foe.center_y - t.center_y
            d = math.hypot(dx, dy) or 1
            ux, uy = dx / d, dy / d
            x, y = t.center_x + ux * 22, t.center_y + uy * 22
            reach = self.turret_reach(t, foe.center_x, foe.center_y)
            self.shots.append(Shot("arrow", x, y, ux * ARROW_SPEED, uy * ARROW_SPEED,
                                   (reach + 80) / ARROW_SPEED, TURRET_DAMAGE, -1, t.layer))
            self.play("laser", 0.08, at=t.position, layer=t.layer)
            t.reload = TURRET_RELOAD

    # ------------------------------------------------------------------ everyone: looks
    def defense_visuals(self, dt):
        """Turrets swing their crossbow towards whatever they're aiming at (runs on clients too)."""
        for t in self.structs.values():
            if t.kind != "arrow_turret":
                continue
            foe = self._turret_target(t, self.layers[t.layer])
            if foe is not None and abs(foe.center_x - t.center_x) > 6:
                t.aim_left = foe.center_x < t.center_x
            tex = art_defenses.turret(getattr(t, "aim_left", False))
            if t.texture is not tex:
                t.texture = tex

    def draw_defense_preview(self, item, ghost):
        """While placing a turret or lantern: show how far it reaches (drawn on the 3D ground)."""
        r = {"arrow_turret": TURRET_RANGE, "lantern": LANTERN_RADIUS}.get(item)
        if r:
            col = (255, 214, 120, 120) if item == "lantern" else (220, 230, 255, 110)
            x, y = ghost.center_x, ghost.center_y
            ring = getattr(self, "ground_ring", None)      # view3d.py: lies on the hills
            if ring is None:
                arcade.draw_circle_outline(x, y, r, col, 3)
                return
            ring(x, y, r, col, 3)
            if item == "arrow_turret" and self.view_layer == "over":
                # high ground: how far it reaches downhill (the average over 8 directions), if farther
                h0 = self.ground_height(x, y)
                k = sum(max(0.0, min(TURRET_HIGH_MAX, (h0 - self.ground_height(x + math.cos(a) * r, y + math.sin(a) * r))
                                      * TURRET_HIGH_K)) for a in (i * math.tau / 8 for i in range(8))) / 8
                if k > 8:
                    ring(x, y, r + k, (255, 240, 170, 90), 2)

    # ------------------------------------------------------------------ overrides of ui.UI
    def light_radius(self):
        r = super().light_radius()
        if self.view_layer == "over" and self.near_lantern(self.view_pos(), "over"):
            r = max(r, LANTERN_LIGHT)
        return r

    def context_hint(self):
        me = self.me
        if me and me.alive:
            sel = me.hotbar[me.selected]
            use = "LT" if self.use_pad else "Right-click"
            arrows = self.storage.get("arrows", 0)
            if sel == "arrow_turret":
                return f"{use}  place Arrow Turret  - shoots zombies by itself, uses Arrows from Team Storage ({arrows})"
            if sel == "gate":
                return f"{use}  place Gate  - you and your pets walk through, zombies don't"
            if sel == "lantern":
                return f"{use}  place Lantern  - zombies near it slow down, lights up the night"
        hint = super().context_hint()
        if me and me.alive and hint.startswith(("Left-click  hit", "RT/A hit")):
            t = next((s for s in self.structs.values() if s.kind == "arrow_turret" and s.layer == me.layer
                      and dist(s.position, me.pos) < 110), None)
            if t is not None:
                n = self.storage.get("arrows", 0)
                hint = (f"Arrow Turret ({int(100 * max(0, t.hp) / t.max_hp)}%): {n} arrows in Team Storage"
                        + ("" if n else " - put Arrows in a Storage Bin!"))
        return hint
