"""
backpack.py - when you die, you drop your backpack where you fell. Mixed into the game window.

Dying still stings, but you get a chance to win your things back:
  * Everything you carried and everything you wore goes into one backpack lying on the spot where you died
    (on that layer: the surface, the caves, the deep...). You respawn at the base with the starting items.
  * The pack lasts until the dawn after you're back on your feet. Die by day (back in a few seconds) and it's
    gone at the next dawn. Die at night (back at dawn) and it lasts through the next day, gone at the dawn
    after that. Then: "Your backpack is gone."
  * One pack per survivor: die again before you've picked it up and the OLD pack is lost for good.
  * At night a few zombies are drawn to an uncollected pack and hang around it (more for a bigger pack).
    Underground it's always night. By day nothing special happens.
  * Only the owner can pick it up: walk onto it (or press E / B next to it). Co-op teammates see it as
    "Sam's pack". Its things go back into your backpack, armor goes back on if that slot is free (or into
    the backpack), and the hotbar gets your old layout back where it can.
  * You can find it: a 3D pack lies on the ground, with a faint glow at night, a label with the time left,
    and an arrow at the edge of the screen pointing to it (with the distance) when it's out of sight.

The host (or the solo / split-screen game) runs all of it. Online clients get a small row per pack in every
snapshot ("bp") - where it is, whose it is, how much is in it and when it expires - never its contents.
Packs are saved with the game (old saves just have none).

Also here, because it's the other half of "less chore, same sting": sprinting. Walking is free; holding SHIFT
while moving (or clicking the left stick) runs at SPRINT_MULT x speed and burns energy (main.py move_player /
_update_survivor ask sprint_active), with a little dust kicked up behind you (sprint_visuals). Online clients
only send a sprint flag - the host decides the energy.
"""
import math
import random

import arcade
from PIL import Image
from pyglet import gl
from pyglet.math import Mat4, Vec3

import shapes3d as S3
import ui
from settings import *
from world import LAYERS

PICKUP_RADIUS = 40          # walk this close to your own pack to pick it up
REACH = 100                 # ...or press E / B this close to it
GUARD_SPAWN_EVERY = 6.0     # seconds between zombies turning up at a pack (until it has enough)
GUARD_KEEP_AWAY = 450       # new pack zombies only turn up when nobody is this close (no popping in)
GUARD_CHASE = 380           # a pack zombie leaves the pack to chase a survivor this close
GUARD_RING = 80             # ...otherwise it shuffles round the pack this far out
PX_PER_M = 40               # the distance on the arrow, in "metres" (one building grid step)

# ------------------------------------------------------------------ the 3D pack (shapes3d.py)
# x = forward, y = left, z = up, in R (half the sprite's size). Plain leather colours; the bedroll strapped
# on top takes the owner's colour from the sprite's picture (a plain square in their colour).
_LEATHER, _DARK, _POCKET = (138, 92, 52), (96, 62, 36), (118, 80, 46)
S3.SHAPES["backpack"] = S3.Shape([
    S3.Part([(0.0, 0.0, 0, 0.55), (0.92, 0.03, 0, 0.62), (1.0, 0.45, 0, 0.82), (0.96, 0.95, 0, 0.95),
             (0.74, 1.14, 0, 1.0), (0.0, 1.2, 0, 1.02)], size=(0.62, 0.86, 1.0), tilt=-0.22, color=_LEATHER, sides=6),
    S3.Part([(0.0, 0.92, 0, 0.8), (0.82, 0.98, 0, 0.85), (0.86, 1.16, 0, 0.95), (0.0, 1.27, 0, 1.0)],
            at=(0.06, 0.0, 0.0), size=(0.66, 0.9, 1.0), tilt=-0.22, color=_DARK, sides=6),
    S3.Part(S3.ball(3), at=(0.52, 0.0, 0.42), size=(0.24, 0.52, 0.3), tilt=-0.22, color=_POCKET, sides=6),
    S3.Part(S3.tube(0.24, 0.24, 1.34, caps=True), at=(-0.16, 0.67, 1.3), roll=-math.pi / 2,
            color=S3.Pick(0.5, 0.5), sides=7),
    S3.Part(S3.tube(0.06, 0.06, 0.95), at=(-0.62, 0.32, 0.12), tilt=-0.2, color=_DARK, sides=3),
    S3.Part(S3.tube(0.06, 0.06, 0.95), at=(-0.62, -0.32, 0.12), tilt=-0.2, color=_DARK, sides=3),
    # a little brass lamp tied to the strap: what you spot first in the dark
    S3.Part(S3.ball(2), at=(0.66, 0.0, 0.86), size=(0.1, 0.1, 0.12), color=(255, 214, 130), sides=5, glow=0.9),
], foot=(1.0, 1.0), cut=0.0)

_TEX = {}


def _texture(col):
    """A plain square in the owner's colour (the bedroll picks it up)."""
    col = tuple(int(c) for c in col[:3])
    t = _TEX.get(col)
    if t is None:
        t = _TEX[col] = arcade.Texture(Image.new("RGBA", (42, 42), col + (255,)))
    return t


def _count(items, armor):
    return sum(int(n) for n in items.values()) + sum(1 for a in armor.values() if a)


class Pack:
    """One dropped backpack. On the host it holds the things; on online clients only what the snapshot says."""

    def __init__(self, num, key, name, layer, x, y, items=None, armor=None, hotbar=None, expires=0.0,
                 color=(220, 220, 220), owner=-1, count=None):
        self.num, self.key, self.name = num, key, name
        self.layer, self.x, self.y = layer, float(x), float(y)
        self.items = dict(items or {})
        self.armor = {s: (armor or {}).get(s) for s in ARMOR_SLOTS}
        self.hotbar = list(hotbar or [])
        self.expires = float(expires)          # the game clock (game.clock) of the dawn it's gone at
        self.color = tuple(color)
        self.owner = owner                     # the owner's player id while they're in the game, else -1
        self.count = _count(self.items, self.armor) if count is None else int(count)
        self.guard_t = 0.0
        self.sprite = arcade.Sprite(_texture(self.color), center_x=self.x, center_y=self.y)
        self.sprite.kind = "backpack"
        self.sprite.angle = random.uniform(0, 360)

    @property
    def pos(self):
        return self.x, self.y


class Backpacks:
    # ------------------------------------------------------------------ set-up & lookups
    def packs_setup(self):
        """Called from setup(): no packs in a fresh world."""
        self.packs = {}            # num -> Pack
        self.pack_lists = {}       # layer -> SpriteList of pack sprites (drawn in 3D)
        self.next_pack = 1

    def _pack_list(self, layer):
        lst = self.pack_lists.get(layer)
        if lst is None:
            lst = self.pack_lists[layer] = arcade.SpriteList()
        return lst

    def _add_pack(self, pk):
        self.packs[pk.num] = pk
        self._pack_list(pk.layer).append(pk.sprite)
        self.next_pack = max(self.next_pack, pk.num + 1)
        return pk

    def _drop_pack_record(self, pk):
        self.packs.pop(pk.num, None)
        pk.sprite.remove_from_sprite_lists()
        for L in self.layers.values():           # its zombies forget about it
            for z in L.zombies:
                if z.__dict__.get("pack_guard") == pk.num:
                    z.pack_guard = None

    def pack_of(self, p):
        """p's own pack (or None)."""
        if p is None:
            return None
        if self.net == "client":
            return next((pk for pk in self.packs.values() if pk.owner == p.id), None)
        key = self.rec_key(p)                    # savegame.py: survives leaving and rejoining
        return next((pk for pk in self.packs.values() if pk.key == key), None)

    @staticmethod
    def next_dawn(clock):
        """The game clock of the first dawn after `clock`."""
        c = DAY_CYCLE_SECONDS
        return (math.floor(clock / c - DAWN_START) + 1 + DAWN_START) * c

    def pack_secs_left(self, pk):
        """Real seconds until the pack is gone (follows the day / night lengths, like the clock)."""
        left = pk.expires - self.clock
        if left <= 0:
            return 0.0
        to_dawn = ((DAWN_START - self.phase) % 1.0) * DAY_CYCLE_SECONDS
        whole = max(0, int(round((left - to_dawn) / DAY_CYCLE_SECONDS)))
        day, night = self.day_night
        return self.secs_until(DAWN_START) + whole * (day + night)

    @staticmethod
    def clock_text(secs):
        secs = int(secs)
        return f"{secs // 60}:{secs % 60:02d}"

    # ------------------------------------------------------------------ dying & picking up (host / solo)
    def drop_pack(self, p):
        """p just died: everything carried and worn goes into a pack where they fell (the old one is lost).
        Returns (how many things went in, True if an older pack was lost)."""
        old = self.pack_of(p)
        if old is not None:
            self._drop_pack_record(old)
        armor = {s: p.equip.get(s) for s in ARMOR_SLOTS}
        items = {k: int(v) for k, v in p.inv.items() if int(v) > 0}
        n = _count(items, armor)
        if n:
            night = DUSK_START <= self.phase < DAWN_START       # back at dawn: it lasts through that day too
            expires = self.next_dawn(self.clock) + (DAY_CYCLE_SECONDS if night else 0)
            self._add_pack(Pack(self.next_pack, self.rec_key(p), p.name, p.layer, p.sprite.center_x,
                                p.sprite.center_y, items, armor, p.hotbar, expires, p.color, p.id))
        return n, old is not None

    def pickup_pack(self, p, reach=PICKUP_RADIUS):
        """Give p their pack back if they're standing at it. True if they picked it up."""
        pk = self.pack_of(p)
        if (pk is None or not p.alive or pk.layer != p.layer
                or math.hypot(pk.x - p.sprite.center_x, pk.y - p.sprite.center_y) > reach):
            return False
        self._drop_pack_record(pk)
        for item, n in pk.items.items():
            if item in ITEMS and n > 0:
                p.inv[item] = p.inv.get(item, 0) + int(n)
        put_on = 0
        for slot, item in pk.armor.items():
            if item not in ITEMS:
                continue
            if p.equip.get(slot) is None:
                p.equip[slot] = item
                put_on += 1
            else:                                # wearing something new there: the old piece goes in the bag
                p.inv[item] = p.inv.get(item, 0) + 1
        # the hotbar: everything back in its old slot where it can be, the rest fills the gaps
        moved = []
        for i, item in enumerate(pk.hotbar[:HOTBAR_SLOTS]):
            if not item or item not in p.inv or p.hotbar[i] == item:
                continue
            if item in p.hotbar:
                p.hotbar[p.hotbar.index(item)] = None
            if p.hotbar[i]:
                moved.append(p.hotbar[i])
            p.hotbar[i] = item
        for item in moved + list(p.inv):
            self._hotbar_add(p, item)
        self.play("pickup", 0.4, to=p)
        self.burst(pk.x, pk.y, (255, 220, 150), 14, 120, layer=pk.layer)
        worn = f", {put_on} back on" if put_on else ""
        if len(self.players) > 1:       # (first, so your own screen shows your own message)
            self.say(f"{p.name} got their backpack back.", 2.5)
        self.say(f"You got your backpack back! ({pk.count} things{worn})", 4, to=p)
        return True

    def update_packs(self, dt):
        """Host / solo, every frame while playing: pick-ups, the dawn that takes them, the zombies they draw."""
        if not self.packs:
            return
        for p in self.alive_players():
            self.pickup_pack(p)
        for pk in list(self.packs.values()):
            owner = next((p for p in self.players.values() if self.rec_key(p) == pk.key), None)
            pk.owner = owner.id if owner else -1
            if self.clock >= pk.expires:
                self._drop_pack_record(pk)
                if owner is not None:
                    self.say("Your backpack is gone.", 5, to=owner)
                    self.play("error", 0.25, to=owner)
                continue
            self._guard_pack(pk, dt)

    def _guard_pack(self, pk, dt):
        """At night (always, underground) a few zombies are drawn to a pack nobody has picked up."""
        L = self.layers.get(pk.layer)
        here = self.alive_players(pk.layer)
        if L is None or not here or (pk.layer == "over" and not self.is_night):
            return
        pk.guard_t -= dt
        if pk.guard_t > 0:
            return
        pk.guard_t = GUARD_SPAWN_EVERY
        want = 1 + (pk.count >= 25) + (pk.count >= 60)
        have = sum(1 for z in L.zombies if z.__dict__.get("pack_guard") == pk.num)
        if have >= want or any(math.hypot(p.pos[0] - pk.x, p.pos[1] - pk.y) < GUARD_KEEP_AWAY for p in here):
            return
        z = self.spawn_zombie(pk.layer, at=pk.pos)
        if z is not None:
            z.pack_guard = pk.num

    def pack_loiter(self, z, tgt):
        """_update_zombies: where a pack zombie heads instead of the nearest survivor (None = chase as usual).
        It hangs around the pack until a survivor comes close."""
        num = z.__dict__.get("pack_guard")
        if num is None:
            return None
        pk = self.packs.get(num)
        if pk is None or pk.layer != z.layer:
            z.pack_guard = None
            return None
        if tgt is not None and math.hypot(tgt.pos[0] - z.center_x, tgt.pos[1] - z.center_y) < GUARD_CHASE:
            return None
        a = z.zid * 2.4 + self.time_alive * 0.3
        return pk.x + math.cos(a) * GUARD_RING, pk.y + math.sin(a) * GUARD_RING

    # ------------------------------------------------------------------ saves & co-op
    def packs_save(self):
        return [[pk.key, pk.name, pk.layer, round(pk.x, 1), round(pk.y, 1), pk.items,
                 [pk.armor.get(s) for s in ARMOR_SLOTS], pk.hotbar, round(pk.expires, 2), list(pk.color)]
                for pk in self.packs.values()]

    def packs_load(self, rows):
        """After a save is loaded (rows is None for saves from before backpacks)."""
        for row in rows or []:
            try:
                key, name, layer, x, y, items, armor, hotbar, expires, color = row[:10]
                if layer not in self.layers:
                    continue
                items = {k: int(v) for k, v in (items or {}).items() if k in ITEMS and int(v) > 0}
                armor = {s: (a if a in ITEMS else None) for s, a in zip(ARMOR_SLOTS, armor or [])}
                hotbar = [h if h in ITEMS else None for h in (hotbar or [])][:HOTBAR_SLOTS]
                self._add_pack(Pack(self.next_pack, str(key), str(name)[:12], layer, float(x), float(y), items,
                                    armor, hotbar, float(expires), tuple(int(c) for c in color[:3])))
            except (TypeError, ValueError, KeyError):
                continue           # a damaged row never stops a save from loading

    def packs_net(self):
        """The snapshot rows: [num, owner id, name, layer, x, y, how many things, expiry clock, colour]."""
        li = LAYERS.index
        return [[pk.num, pk.owner, pk.name, li(pk.layer), round(pk.x, 1), round(pk.y, 1), pk.count,
                 round(pk.expires, 1), list(pk.color)] for pk in self.packs.values()]

    def packs_apply(self, rows):
        """Online client: the host's packs."""
        if rows is None:
            return
        names = LAYERS
        seen = set()
        for row in rows:
            try:
                num, owner, name, ly, x, y, count, expires, color = row[:9]
                layer = names[int(ly)]
                if layer not in self.layers:
                    continue
            except (TypeError, ValueError, IndexError):
                continue
            seen.add(num)
            pk = self.packs.get(num)
            if pk is None or pk.layer != layer:
                if pk is not None:
                    self._drop_pack_record(pk)
                pk = self._add_pack(Pack(num, "", str(name), layer, x, y, expires=expires, color=color,
                                         owner=int(owner), count=count))
            pk.owner, pk.name, pk.count, pk.expires = int(owner), str(name), int(count), float(expires)
        for num in [k for k in self.packs if k not in seen]:
            self._drop_pack_record(self.packs[num])

    # ------------------------------------------------------------------ drawing (every computer)
    def draw_packs_3d(self, vl):
        """view3d.draw_world_3d, with the standing things: the packs on this layer as small 3D bags."""
        lst = self.pack_lists.get(vl) if hasattr(self, "pack_lists") else None
        if lst is not None and len(lst):
            self.mesh(lst, "backpack")

    def draw_pack_glows(self, vl, dk):
        """At night: the pack's little lamp, and a faint pool of light round it so you can find it."""
        lst = self.pack_lists.get(vl) if hasattr(self, "pack_lists") else None
        if lst is None or not len(lst):
            return
        ctx = self.ctx
        ctx.enable(ctx.DEPTH_TEST)
        self.mesh(lst, "backpack", blend=(ctx.SRC_ALPHA, ctx.ONE), glow=True)
        # the pool lies just above the ground and is depth tested, so the bag itself stays in front of it
        gl.glDepthMask(gl.GL_FALSE)
        base = self._view3d
        pulse = 0.75 + 0.25 * math.sin(self.flame_t * 2.6)
        try:
            for pk in self.packs.values():
                if pk.layer != vl:
                    continue
                mine = pk.owner == getattr(self.me, "id", None)
                self.view = base @ Mat4.from_translation(Vec3(0.0, 0.0, self.ground_z(pk.x, pk.y) + 2.0))
                col = (255, 214, 140) if mine else pk.color
                arcade.draw_circle_filled(pk.x, pk.y, 46, col + (int((45 if mine else 28) * dk * pulse),))
                arcade.draw_circle_filled(pk.x, pk.y, 26, col + (int((55 if mine else 32) * dk * pulse),))
        finally:
            self.view = base
            gl.glDepthMask(gl.GL_TRUE)
            ctx.disable(ctx.DEPTH_TEST)

    def _pack_label(self, pk):
        if pk.owner == getattr(self.me, "id", None):
            return f"Your pack  {self.clock_text(self.pack_secs_left(pk))}", (255, 226, 150)
        return f"{pk.name}'s pack", pk.color

    def draw_pack_marks(self, vl):
        """Over each pack on screen: whose it is (yours: the time left)."""
        for pk in self.packs.values() if hasattr(self, "packs") else ():
            if pk.layer != vl:
                continue
            s = self.project(pk.x, pk.y, 44)
            if s is None or not self._pack_in_view(*s):
                continue
            far = math.hypot(*(a - b for a, b in zip(self.view_pos(), pk.pos)))
            if far > 1400:
                continue
            text, col = self._pack_label(pk)
            self.txt(f"pk{pk.num}", text, s[0], s[1], tuple(col[:3]) + (235,), 10, anchor_x="center", bold=True)

    def draw_pack_pointer(self):
        """HUD: an arrow at the screen's edge pointing to your pack when it's out of sight, with how far it
        is and how long it has left. If it's on another layer, a line says where it is."""
        me = self.me
        pk = self.pack_of(me) if hasattr(self, "packs") else None
        if pk is None or not me.alive:
            return
        W, H = ui.W, ui.H
        left = self.clock_text(self.pack_secs_left(pk))
        if pk.layer != me.layer:
            title = self.layer_title(pk.layer)       # biomes.py: "into the cave"...
            where = "down in " + title[5:] if title.startswith("into ") else title
            if pk.layer == "over":
                where = "up on the surface"
            self.txt("pkfar", f"Your backpack is {where}  ({left} left)", W - 18, 118, (255, 214, 140), 11,
                     anchor_x="right", bold=True)
            return
        s = self._edge_point(pk.x, pk.y, 20)
        sx, sy = s
        if self._pack_in_view(sx, sy):
            return                    # on screen: its own label shows
        a = math.atan2(sy - H / 2, sx - W / 2)
        ex = max(60, min(W - 60, W / 2 + math.cos(a) * (W / 2 - 46)))
        ey = max(110, min(H - 170, H / 2 + math.sin(a) * (H / 2 - 46)))
        if ex < 290 and W >= 800:          # keep clear of the stats / team panels in the top-left corner
            ey = min(ey, H - 250)
        pulse = 0.8 + 0.2 * math.sin(self.flame_t * 4)
        col = (255, 214, 140)
        tip = (ex + math.cos(a) * 17, ey + math.sin(a) * 17)
        l = (ex + math.cos(a + 2.4) * 12, ey + math.sin(a + 2.4) * 12)
        r = (ex + math.cos(a - 2.4) * 12, ey + math.sin(a - 2.4) * 12)
        arcade.draw_triangle_filled(*tip, *l, *r, col + (int(240 * pulse),))
        arcade.draw_triangle_outline(*tip, *l, *r, (60, 36, 20, 220), 1.5)
        m = int(math.hypot(pk.x - me.sprite.center_x, pk.y - me.sprite.center_y) / PX_PER_M)
        tx, ty = ex - math.cos(a) * 26, ey - math.sin(a) * 26
        self.txt("pkarr", f"Pack {m} m", tx, ty + 2, col, 10, anchor_x="center", bold=True)
        self.txt("pkarr2", left, tx, ty - 11, (235, 225, 210), 9, anchor_x="center")

    def _edge_point(self, x, y, z):
        """Screen spot of a world point - or, if it's behind the camera (first person), a spot far off the
        left or right of the screen on the correct side, so the arrow still points the right way."""
        s = self.project(x, y, z)
        if s is not None:
            return s
        (ex, ey, _), f, r, _, _, vw, vh = self._basis()
        xc = (x - ex) * r[0] + (y - ey) * r[1]
        return vw / 2 + (3 * vw if xc >= 0 else -3 * vw), vh / 2      # behind you: "turn left / right"

    @staticmethod
    def _pack_in_view(sx, sy):
        """Is a screen spot clearly in view (not hidden under the HUD panels / hotbar at the edges)?"""
        return 60 < sx < ui.W - 60 and 110 < sy < ui.H - 80

    def pack_dead_lines(self):
        """ui.draw_dead: what the YOU DIED screen says about the pack."""
        pk = self.pack_of(self.me) if hasattr(self, "packs") else None
        if pk is None:
            return "You carried nothing. Things in TEAM STORAGE are always safe."
        left = self.clock_text(self.pack_secs_left(pk))
        if ui.W < 800:        # a split-screen view: the short version
            return f"Your backpack ({pk.count} things) is where you fell - gone in {left}."
        return (f"Your backpack ({pk.count} things) lies where you fell - gone in {left}. "
                "Die again first and it's lost for good.")

    # ------------------------------------------------------------------ sprint dust (every computer)
    def sprint_visuals(self, dt):
        """A little dust kicked up behind anyone sprinting on the layer you're looking at."""
        if getattr(self, "_fx_pool", None) is None:      # fx3d.py sets its particles up on the first frame drawn
            return
        vl = self.view_layer
        for p in self.players.values():
            if not p.alive or p.layer != vl:
                continue
            on = self.sprint_active(p) if (self.sim or p is self.me) else getattr(p, "sprint_seen", False)
            if not on:
                continue
            p.dust_t = getattr(p, "dust_t", 0.0) - dt
            if p.dust_t > 0:
                continue
            p.dust_t = 0.07
            mx, my = p.move
            b = (math.atan2(my, mx) if (mx or my) else p.face) + math.pi      # behind the way they're going
            x = p.sprite.center_x + math.cos(b) * 10 + random.uniform(-4, 4)
            y = p.sprite.center_y + math.sin(b) * 10 + random.uniform(-4, 4)
            col = (176, 160, 128) if vl == "over" else (120, 112, 104)
            self.fx_puff(vl, x, y, 4, col, 2, 28, 18, 0.65, 7, a=0.7, drag=2.5, grow=22)

    @staticmethod
    def sprint_active(p):
        """True while p is really sprinting: asked to, moving, not resting, with energy left."""
        return bool(getattr(p, "sprinting", False) and p.alive and (p.move[0] or p.move[1]) and not p.resting
                    and p.energy > 0)
