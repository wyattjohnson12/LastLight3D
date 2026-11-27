"""
ui.py - everything Last Light draws: the world, lighting, HUD, backpack & crafting,
team storage, boss cutscenes, menus. Mixed into the LastLight window class.
"""
import math

import arcade

import art
import art_extra  # noqa: F401  (registers the new icons)
import biomes
import explore
import savegame
from settings import *

W, H = SCREEN_WIDTH, SCREEN_HEIGHT
AMOUNTS = [1, 5, 10, "All"]
FONT = ("Avenir Next", "Helvetica Neue", "Arial")
TAB_NAMES = list(CRAFT_TABS)
TAB_OFFSET = {}
_i = 0
for _name, _rows in CRAFT_TABS.items():
    TAB_OFFSET[_name] = _i
    _i += len(_rows)
SLOT_NAMES = {"head": "Head", "body": "Body", "cloak": "Cloak"}


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class UI:
    # ------------------------------------------------------------------ text helpers
    def txt(self, key, text, x, y, color=(255, 255, 255), size=13, anchor_x="left", bold=False, anchor_y="baseline"):
        key = self.txt_prefix + key if getattr(self, "txt_prefix", "") else key
        t = self.texts.get(key)
        if t is None:
            t = arcade.Text(text, x, y, color, size, anchor_x=anchor_x, anchor_y=anchor_y, bold=bold, font_name=FONT)
            self.texts[key] = t
        else:
            if t.text != text:
                t.text = text
            if (t.x, t.y) != (x, y):
                t.position = (x, y)
            if t.color != color:
                t.color = color
            if t.font_size != size:
                t.font_size = size
        t.draw()
        return t

    def panel(self, l, r, b, t, alpha=170):
        arcade.draw_lrbt_rectangle_filled(l, r, b, t, (14, 18, 22, alpha))
        arcade.draw_lrbt_rectangle_outline(l, r, b, t, (255, 255, 255, 40), 1)

    # ------------------------------------------------------------------ world
    def light_radius(self):
        me = self.me
        vl = self.view_layer
        pos = self.view_pos()
        torch = me is not None and me.alive and me.holding_torch
        fire = self.near_fire(pos, vl, 150)
        if vl != "over":
            return 280 if fire else 260 if torch else 150
        return 300 if fire else 330 if torch else 240

    def on_draw(self):
        vl = self.view_layer
        L = self.layers[vl]
        bg = (6, 6, 9) if vl != "over" else (24, 34, 22)
        if getattr(self, "_split", False):     # local split screen: only paint this player's slice
            self.gui.use()
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, bg)
        else:
            self.clear(color=(0, 0, 0))     # black bars around the game in fullscreen
            self.gui.use()
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, bg)
        self.draw_world_3d(L, vl)   # view3d.py

        self.gui.use()
        if self.state == "title":
            self.draw_title()
            return
        if not self.me:
            self.txt("load", "Loading world...", W / 2, H / 2, (255, 255, 255), 20, anchor_x="center", bold=True)
            return
        me = self.me
        if me.hurt > 0 and not self.cut:
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (200, 0, 0, int(110 * min(1, me.hurt / 0.35))))
        if me.alive and me.warmth < 35:
            self.draw_frost((35 - me.warmth) / 35)
        if self.cut:
            self.draw_cutscene()
            return
        self.draw_offscreen_friends()
        self.draw_hud()
        self.draw_pack_pointer()      # backpack.py: the arrow to your dropped pack (on top of the HUD)
        self.draw_boss_bar()
        if not getattr(self, "_split", False):   # split screen draws these full-size afterwards
            if self.ui_open == "inv":
                self.draw_inventory()
            elif self.ui_open == "storage":
                self.draw_storage()
            elif self.ui_open == "pets":
                self.draw_pets()
            if self.paused:
                self.draw_help(True)
        if not me.alive:
            self.draw_dead()

    def draw_ground_hazards(self):
        if self.view_layer != "over":
            return
        pulse = 0.5 + 0.5 * math.sin(self.flame_t * 14)
        self.draw_swamp_ground()      # swamp.py draws its own hazards
        for h in self.hazards:
            if h.kind in self.SWAMP_HAZARDS:
                continue
            if h.tele > 0:
                if h.kind == "line":
                    ex, ey = h.x + math.cos(h.a) * h.ln, h.y + math.sin(h.a) * h.ln
                    arcade.draw_line(h.x, h.y, ex, ey, (255, 120, 40, int(90 + 80 * pulse)), h.r)
                    arcade.draw_line(h.x, h.y, ex, ey, (255, 220, 120, 160), 4)
                elif h.kind == "mist":
                    arcade.draw_circle_filled(h.x, h.y, h.r, (200, 230, 255, int(60 + 60 * pulse)))
                else:
                    col = (255, 60, 40) if h.kind != "quake" else (255, 150, 60)
                    arcade.draw_circle_filled(h.x, h.y, h.r, col + (int(40 + 50 * pulse),))
                    arcade.draw_circle_outline(h.x, h.y, h.r, col + (220,), 3)
                    if h.kind == "quake":   # cracks spreading out
                        for k in range(10):
                            a = k / 10 * math.tau + 0.3
                            arcade.draw_line(h.x, h.y, h.x + math.cos(a) * h.r * (1 - h.tele / 1.4),
                                             h.y + math.sin(a) * h.r * (1 - h.tele / 1.4), (60, 30, 20, 200), 3)
            elif h.kind == "acid":
                arcade.draw_circle_filled(h.x, h.y, h.r, (110, 220, 60, 110))
                arcade.draw_circle_outline(h.x, h.y, h.r, (170, 255, 100, 200), 2)
            elif h.kind == "fire":
                r = h.r * (0.9 + 0.1 * math.sin(self.flame_t * 20 + h.x))
                arcade.draw_circle_filled(h.x, h.y, r, (255, 110, 30, 120))
                arcade.draw_circle_filled(h.x, h.y, r * 0.55, (255, 210, 90, 140))

    def draw_air_hazards(self):
        if self.view_layer != "over":
            return
        for h in self.hazards:
            if h.kind in ("boulder", "meteor") and h.tele > 0:
                k = max(0.0, h.tele)   # falling object: high up = small shadow offset
                col = (130, 120, 110) if h.kind == "boulder" else (255, 120, 40)
                arcade.draw_circle_filled(h.x + k * 30, h.y + k * 160, 16 + 6 * (1 - k), col + (240,))
            elif h.kind == "glob" and h.tele <= 0:
                arcade.draw_circle_filled(h.x, h.y, h.r, (140, 230, 70, 240))
            elif h.kind == "shard" and h.tele <= 0:
                a = math.atan2(h.vy, h.vx)
                arcade.draw_line(h.x - math.cos(a) * 14, h.y - math.sin(a) * 14, h.x + math.cos(a) * 8,
                                 h.y + math.sin(a) * 8, (190, 235, 255, 255), 5)

    def draw_pet_marks(self, L):
        for a in L.animals:
            if not a.pet:
                continue
            owner = self.players.get(a.owner)
            col = owner.color if owner else (220, 220, 220)
            arcade.draw_circle_filled(a.center_x, a.center_y + 22, 5, col + (230,))
            arcade.draw_circle_outline(a.center_x, a.center_y + 22, 5, (255, 255, 255, 200), 1)
            if a.carrying:
                arcade.draw_circle_filled(a.center_x + 10, a.center_y + 22, 4, (255, 220, 120, 230))

    def draw_frost(self, k):
        a = int(160 * k)
        for i in range(6):
            w = 14 + i * 12
            al = int(a * (1 - i / 6))
            arcade.draw_lrbt_rectangle_outline(w / 2, W - w / 2, w / 2, H - w / 2, (170, 215, 255, al), 12)

    def draw_offscreen_friends(self):
        cx, cy = self.camera.position
        for p in self.players.values():
            if p is self.me or not p.alive or p.layer != self.view_layer:
                continue
            sx, sy = p.sprite.center_x - cx + W / 2, p.sprite.center_y - cy + H / 2
            if 0 < sx < W and 0 < sy < H:
                continue
            a = math.atan2(sy - H / 2, sx - W / 2)
            ex = max(30, min(W - 30, W / 2 + math.cos(a) * (W / 2 - 40)))
            ey = max(110, min(H - 170, H / 2 + math.sin(a) * (H / 2 - 40)))
            tip = (ex + math.cos(a) * 14, ey + math.sin(a) * 14)
            l = (ex + math.cos(a + 2.4) * 10, ey + math.sin(a + 2.4) * 10)
            r = (ex + math.cos(a - 2.4) * 10, ey + math.sin(a - 2.4) * 10)
            arcade.draw_triangle_filled(*tip, *l, *r, p.color + (230,))
            self.txt(f"arr{p.id}", p.name, ex - math.cos(a) * 18, ey - math.sin(a) * 18 - 4, p.color, 10,
                     anchor_x="center", bold=True)

    # ------------------------------------------------------------------ HUD
    def draw_hud(self):
        me = self.me
        self.panel(12, 262, H - 160, H - 12)
        stats = [("heart", me.health, (222, 70, 76)), ("berries", me.hunger, (236, 156, 60)),
                 ("drop", me.thirst, (80, 160, 232)), ("bolt", me.energy, (240, 208, 80)),
                 ("cold", me.warmth, (150, 210, 255))]
        for i, (ic, val, col) in enumerate(stats):
            y = H - 34 - i * 26
            arcade.draw_texture_rect(art.icon(ic), arcade.XYWH(32, y, 22, 22))
            arcade.draw_lrbt_rectangle_filled(50, 230, y - 7, y + 7, (40, 40, 46, 230))
            low = val < 25 and int(self.flame_t * 4) % 2 == 0
            w = 180 * max(0, val) / STAT_MAX
            arcade.draw_lrbt_rectangle_filled(50, 50 + w, y - 7, y + 7, (255, 255, 255) if low else col)
            arcade.draw_lrbt_rectangle_filled(50, 50 + w, y + 2, y + 7, (255, 255, 255, 40))
            self.txt(f"stat{i}", f"{int(max(0, val))}", 238, y - 5, (230, 230, 230), 11)
        arcade.draw_texture_rect(art.icon("shield"), arcade.XYWH(30, H - 150, 16, 16))
        self.txt("armor", f"Armor {me.gear('armor')}", 42, H - 155, (200, 210, 230), 10, bold=True)
        arcade.draw_texture_rect(art.icon("cold"), arcade.XYWH(122, H - 150, 16, 16))
        self.txt("warm", f"Clothing warmth {me.gear('warmth')}", 134, H - 155, (190, 225, 255), 10, bold=True)

        top = H - 172
        pets = [a for a in self.over.animals if a.owner == me.id]
        if pets:
            self.panel(12, 262, top - 30, top, 150)
            arcade.draw_texture_rect(art.icon("paw"), arcade.XYWH(28, top - 15, 18, 18))
            kinds = ", ".join(sorted({a.kind for a in pets}))
            key = "D-pad down" if self.use_pad else "F"
            self.txt("pets", f"{len(pets)} pet{'s' if len(pets) > 1 else ''} ({kinds}) - {pets[0].mode.upper()}"
                             f"  [{key}]", 42, top - 20, (255, 220, 200), 10, bold=True)
            top -= 38

        others = [p for p in self.players.values() if p is not me]
        if others:
            self.panel(12, 262, top - 24 * len(others) - 30, top, 150)
            self.txt("team", "TEAM", 22, top - 18, (255, 230, 170), 10, bold=True)
            for i, p in enumerate(others):
                y = top - 40 - i * 24
                arcade.draw_circle_filled(28, y + 4, 6, p.color if p.alive else (90, 90, 90))
                where = "" if p.layer == "over" else " (cave)"
                self.txt(f"tn{p.id}", (p.name if p.alive else f"{p.name} (dead)") + where, 42, y,
                         (235, 235, 235) if p.alive else (150, 150, 150), 11, bold=True)
                arcade.draw_lrbt_rectangle_filled(160, 250, y, y + 8, (40, 40, 46, 230))
                arcade.draw_lrbt_rectangle_filled(160, 160 + 0.9 * max(0, p.health), y, y + 8, (222, 70, 76))

        # day / night clock
        self.panel(W - 232, W - 12, H - 88, H - 12)
        p = self.phase
        night = DUSK_START <= p < DAWN_START
        arcade.draw_texture_rect(art.icon("moon" if night else "sun"), arcade.XYWH(W - 200, H - 50, 44, 44))
        self.txt("day", f"Day {self.day}", W - 170, H - 44, (255, 255, 255), 18, bold=True)
        if night:
            sub = f"Dawn in {int(self.secs_until(DAWN_START))}s"
        else:
            sub = f"Night in {int(self.secs_until(DUSK_START))}s"
        self.txt("daysub", sub, W - 170, H - 66, (200, 210, 230), 12)
        self.txt("kills", f"Kills {self.kills}", W - 24, H - 44, (230, 120, 110), 12, anchor_x="right")
        bar_w = 196
        arcade.draw_lrbt_rectangle_filled(W - 220, W - 220 + bar_w, H - 82, H - 78, (60, 70, 90))
        arcade.draw_lrbt_rectangle_filled(W - 220 + bar_w * DUSK_START, W - 220 + bar_w * DAWN_START,
                                          H - 82, H - 78, (30, 36, 70))
        arcade.draw_lrbt_rectangle_filled(W - 221 + bar_w * p, W - 219 + bar_w * p, H - 85, H - 75, (255, 230, 150))
        y = H - 106
        if self.boss_night:
            label = "BOSS RETURNS TONIGHT" if self.boss_hp is not None else "BOSS NIGHT"
            self.txt("bossnight", label, W - 18, y, (255, 110, 90), 11, anchor_x="right", bold=True)
            y -= 16
        else:
            n = self.boss_day - self.day
            self.txt("bossnext", f"Next boss in {n} night{'s' if n > 1 else ''}", W - 18, y, (200, 170, 160), 10,
                     anchor_x="right")
            y -= 16
        y = self.draw_weather_hud(y)     # weather.py: season + weather
        if self.view_layer != "over":
            self.txt("cavetag", "UNDERGROUND", W - 18, y, (190, 170, 255), 11, anchor_x="right", bold=True)
            y -= 16
        if self.net:
            tag = f"CO-OP  {len(self.players)}/4" + (f"   host IP {self.host_ip}" if self.net == "host" else "")
            self.txt("netinfo", tag, W - 18, y, (170, 220, 255, 200), 10, anchor_x="right", bold=True)

        # materials strip
        mats = ["wood", "stone", "fiber", "iron_ingot"] if W >= 800 else []
        if mats:
            self.panel(W / 2 - 190, W / 2 + 190, H - 48, H - 12)
        for i, m in enumerate(mats):
            x = W / 2 - 150 + i * 95
            arcade.draw_texture_rect(art.icon(m), arcade.XYWH(x, H - 30, 26, 26))
            self.txt(f"mat{m}", str(me.inv.get(m, 0)), x + 18, H - 36, (255, 255, 255), 14, bold=True)

        # hotbar
        slot, gap = 58, 8
        total = HOTBAR_SLOTS * slot + (HOTBAR_SLOTS - 1) * gap
        x0 = W / 2 - total / 2
        for i in range(HOTBAR_SLOTS):
            l = x0 + i * (slot + gap)
            sel = i == me.selected
            arcade.draw_lrbt_rectangle_filled(l, l + slot, 14, 14 + slot, (20, 24, 30, 200))
            arcade.draw_lrbt_rectangle_outline(l, l + slot, 14, 14 + slot,
                                               (255, 214, 120) if sel else (255, 255, 255, 50), 3 if sel else 1)
            it = me.hotbar[i]
            self.txt(f"hk{i}", str(i + 1), l + 5, 14 + slot - 14, (200, 200, 200, 160), 9)
            if it:
                s = 40 if ITEMS[it]["kind"] != "build" else 36
                arcade.draw_texture_rect(art.icon(it), arcade.XYWH(l + slot / 2, 14 + slot / 2, s, s))
                self.txt(f"hc{i}", str(me.inv.get(it, 0)), l + slot - 5, 18, (255, 255, 255), 11,
                         anchor_x="right", bold=True)
        sel = me.hotbar[me.selected]
        self.txt("sel", ITEMS[sel]["name"] if sel else "Fists", W / 2, 14 + slot + 10, (255, 230, 170), 12,
                 anchor_x="center", bold=True)
        hint = self.context_hint()
        if hint:
            self.txt("hint", hint, W / 2, 14 + slot + 32, (210, 220, 210, 200), 11, anchor_x="center")
        warn = []
        if me.hunger <= 0:
            warn.append("STARVING")
        if me.thirst <= 0:
            warn.append("DEHYDRATED")
        if me.warmth <= 0:
            warn.append("FREEZING - get to a fire!")
        elif me.warmth < 25:
            warn.append("COLD")
        if me.energy <= 0:
            warn.append("EXHAUSTED")
        if me.in_hut:
            warn.append("SHELTERED")
        if warn and me.alive:
            self.txt("warn", "   ".join(warn), W - 18, 100, (255, 140, 120) if not me.in_hut else (160, 230, 160),
                     12, anchor_x="right", bold=True)
        if self.message_t > 0:
            a = int(255 * min(1, self.message_t))
            t = self.txt("msg", self.message, W / 2, 138, (255, 240, 210, a), 14, anchor_x="center", bold=True)
            half = t.content_width / 2 + 14
            arcade.draw_lrbt_rectangle_filled(W / 2 - half, W / 2 + half, 130, 160, (10, 12, 16, int(a * 0.6)))
            t.draw()
        corner = "Y backpack   B use/eat   MENU help" if self.use_pad else "TAB backpack   E use   F pets   ESC help"
        if W >= 800:     # split screen is too narrow - the hotbar needs the room
            self.txt("tabhint", corner, W - 18, 18, (200, 200, 200, 150), 10, anchor_x="right")
        if self.pad.connected:
            self.txt("padname", "Controller connected", 18, 18, (170, 220, 170, 150), 10)

    def draw_boss_bar(self):
        bosses = list(self.over.bosses)
        if not bosses:
            return
        b = bosses[0]
        w = 460 if W >= 800 else W - 60
        l, y = W / 2 - w / 2, (H - 78) if W >= 800 else 190
        arcade.draw_lrbt_rectangle_filled(l - 4, l + w + 4, y - 10, y + 10, (10, 6, 6, 220))
        arcade.draw_lrbt_rectangle_filled(l, l + w * max(0, b.hp) / max(1, b.max_hp), y - 6, y + 6, (220, 50, 40))
        arcade.draw_lrbt_rectangle_filled(l, l + w * max(0, b.hp) / max(1, b.max_hp), y + 1, y + 6, (255, 140, 120, 120))
        self.txt("bossname", b.info["name"], W / 2, y + 14, (255, 200, 170), 12, anchor_x="center", bold=True)

    def context_hint(self):
        me = self.me
        if not me.alive:
            return ""
        pad = self.use_pad
        use, inter = ("LT", "B") if pad else ("Right-click", "E")
        if self.near_storage(me):
            return f"{inter}  open TEAM STORAGE  (crafting nearby uses it automatically)"
        found = explore.hint(self, me, inter)      # explore.py: a place's chest at hand
        if found:
            return found
        ex = self.near_exit(me)
        if ex:
            far = self.portal_from(me.layer, ex.position)      # biomes.py: any layer (cave, deep...)
            lock = self.portal_lock(me.layer, ex.position)
            if lock:
                return lock
            to = far[0] if far else "over"
            down = biomes.depth(to) > biomes.depth(me.layer)
            return f"{inter}  climb {'down ' if down else 'back up '}{self.layer_title(to)}"
        if self.near_pond(me):
            return f"{inter}  drink & fill flask"
        t = self.tame_target()
        if t:
            return f"{use}  try to tame the {t.kind} ({int(t.info['chance'] * 100)}% chance)"
        sel = me.hotbar[me.selected]
        if sel == "repair_hammer":
            return self.repair_hint(me, "RT / A" if pad else "Left-click")
        if sel and ITEMS[sel]["kind"] == "throw":
            return f"{use}  throw {ITEMS[sel]['name']} where you aim  ({me.inv.get(sel, 0)} left)"
        if sel and ITEMS[sel].get("ranged"):
            n = me.inv.get("arrows", 0)
            if not n:
                return "No arrows!  Craft Arrows in the Supplies tab (wood, stone, fiber)"
            return f"{'RT / A' if pad else 'Left-click'}  shoot where you aim   ({n} arrows)"
        if sel and ITEMS[sel]["kind"] == "build":
            return f"{use}  place {ITEMS[sel]['name']}"
        if sel and ITEMS[sel]["kind"] == "food":
            return f"{use}  eat {ITEMS[sel]['name']}     {'B' if pad else 'Q'}  quick eat/drink"
        if self.near_kind(me.pos, me.layer, "workbench", 150):
            return "Workbench here: open the backpack for advanced crafting"
        if self.near_fire(me.pos, me.layer, 150):
            return f"By the fire: warm up, cook food   |   {'hold X' if pad else 'SHIFT (standing)'} rest to heal"
        if pad:
            return "RT/A hit & gather   L-stick move (click: sprint)   R-stick aim   LB/RB hotbar   hold X rest"
        return "Left-click  hit / gather     WASD  move     SHIFT  sprint (standing: rest)"

    # ------------------------------------------------------------------ backpack & crafting
    INV_COLS, INV_ROWS, SLOT, GAP = 5, 5, 62, 8

    def inv_layout(self):
        pw, ph = 980, 610
        return W / 2 - pw / 2, H / 2 - ph / 2 + 10, pw, ph

    def grid_rect(self, l, top, idx, cols):
        size, gap = self.SLOT, self.GAP
        cx = l + (idx % cols) * (size + gap)
        cy = top - (idx // cols + 1) * (size + gap)
        return cx, cx + size, cy, cy + size

    def inv_items(self):
        order = list(ITEMS)
        return sorted(self.me.inv.items(), key=lambda kv: order.index(kv[0]))

    # --- item grids that scroll a row at a time (the backpack has no size limit, so it can be long)
    def grid_first(self, key, total, cols, rows):
        """First visible row of a scrolling grid (clamped)."""
        if not hasattr(self, "_grid_scroll"):
            self._grid_scroll = {}
        most = max(0, -(-total // cols) - rows)
        v = max(0, min(most, self._grid_scroll.get(key, 0)))
        self._grid_scroll[key] = v
        return v

    def grid_scroll(self, key, steps, total, cols, rows):
        self.grid_first(key, total, cols, rows)
        self._grid_scroll[key] += steps
        self.grid_first(key, total, cols, rows)

    def draw_grid_bar(self, key, x, top, total, cols, rows, tag):
        """Scrollbar beside a grid with more items than fit, plus 'N more above / below' notes."""
        total_rows = -(-total // cols)
        if total_rows <= rows:
            return
        first = self.grid_first(key, total, cols, rows)
        pitch = self.SLOT + self.GAP
        bot = top - rows * pitch
        span = top - bot
        th = max(20, span * rows / total_rows)
        t0 = top - (span - th) * first / (total_rows - rows)
        arcade.draw_lrbt_rectangle_filled(x, x + 7, bot, top, (34, 40, 48, 220))
        arcade.draw_lrbt_rectangle_filled(x, x + 7, t0 - th, t0, (255, 214, 140, 210))
        above = first * cols
        below = max(0, total - (first + rows) * cols)
        how = "right stick" if self.use_pad else "mouse wheel"
        self.txt(f"gm{tag}a", f"{above} more above" if above else "", x + 7, top + 3, (255, 214, 140), 10,
                 anchor_x="right")
        self.txt(f"gm{tag}b", f"{below} more below - scroll ({how})" if below else "", x + 7, bot - 12,
                 (255, 214, 140), 10, anchor_x="right")

    def inv_grid_top(self):
        l, b, pw, ph = self.inv_layout()
        return b + ph - 56

    def inv_slots(self):
        """The backpack items you can see right now: [(item, rect), ...] (scrolled)."""
        l, b, pw, ph = self.inv_layout()
        top = self.inv_grid_top()
        items = self.inv_items()
        cols, rows = self.INV_COLS, self.INV_ROWS
        first = self.grid_first("inv", len(items), cols, rows) * cols
        shown = items[first:first + cols * rows]
        return [(it, self.grid_rect(l + 24, top, i, cols)) for i, (it, _) in enumerate(shown)]

    def worn_slots(self):
        l, b, pw, ph = self.inv_layout()
        return [(s, (l + 24 + i * 70, l + 24 + i * 70 + self.SLOT, b + 100, b + 100 + self.SLOT))
                for i, s in enumerate(ARMOR_SLOTS)]

    def tab_rects(self):
        l, b, pw, ph = self.inv_layout()
        x0 = l + 410
        return [(i, (x0 + i * 136, x0 + i * 136 + 130, b + ph - 82, b + ph - 54)) for i in range(len(TAB_NAMES))]

    CRAFT_ROWS, ROW_PITCH = 12, 36      # recipes shown at once; a longer tab scrolls

    def craft_scroll(self, tab=None):
        """How many recipes of this tab are scrolled off the top (each tab remembers its own)."""
        tab = self.craft_tab if tab is None else tab
        if not hasattr(self, "_craft_scroll"):
            self._craft_scroll = {}
        most = max(0, len(CRAFT_TABS[TAB_NAMES[tab]]) - self.CRAFT_ROWS)
        return max(0, min(most, self._craft_scroll.get(tab, 0)))

    def scroll_crafting(self, steps):
        if not hasattr(self, "_craft_scroll"):
            self._craft_scroll = {}
        self._craft_scroll[self.craft_tab] = self.craft_scroll() + steps
        self._craft_scroll[self.craft_tab] = self.craft_scroll()     # clamp

    def recipe_rows(self):
        """The recipes you can see right now: [(index into RECIPES, recipe, rect), ...]."""
        l, b, pw, ph = self.inv_layout()
        name = TAB_NAMES[self.craft_tab]
        x = l + 410
        first = self.craft_scroll()
        rows = []
        for i, rec in enumerate(CRAFT_TABS[name][first:first + self.CRAFT_ROWS]):
            y = b + ph - 112 - i * self.ROW_PITCH
            rows.append((TAB_OFFSET[name] + first + i, rec, (x, x + 548, y - 16, y + 16)))
        return rows

    def craft_scrollbar(self):
        """(track rect, thumb rect) for a tab with more recipes than fit, else None."""
        n = len(CRAFT_TABS[TAB_NAMES[self.craft_tab]])
        if n <= self.CRAFT_ROWS:
            return None
        l, b, pw, ph = self.inv_layout()
        top = b + ph - 112 + 16
        bot = top - self.CRAFT_ROWS * self.ROW_PITCH + 4
        x = l + 410 + 554
        span = top - bot
        th = max(24, span * self.CRAFT_ROWS / n)
        t0 = top - (span - th) * self.craft_scroll() / (n - self.CRAFT_ROWS)
        return (x, x + 8, bot, top), (x, x + 8, t0 - th, t0)

    # ------------------------------------------------------------------ scrolling menus (wheel / keys / stick)
    def ui_scroll(self, steps):
        """Mouse wheel (or keys / right stick) while a menu is open. steps > 0 scrolls down.
        Scrolls whichever list the pointer (or controller cursor) is over."""
        mx = self.mouse_screen[0]
        if self.ui_open == "inv":
            l, b, pw, ph = self.inv_layout()
            if mx < l + 400:
                self.grid_scroll("inv", steps, len(self.me.inv), self.INV_COLS, self.INV_ROWS)
            else:
                self.scroll_crafting(steps)
        elif self.ui_open == "storage":
            l, b, pw, ph = self.storage_layout()
            if mx < l + 450:
                self.grid_scroll("st_m", steps, len(self.me.inv), 5, 5)
            else:
                self.grid_scroll("st_t", steps, len(self.storage), 6, 5)
        elif self.ui_open == "pets":
            self.scroll_pets(steps)

    def ui_scroll_key(self, key):
        """UP / DOWN / PAGE UP / PAGE DOWN in a menu. True if the key was used."""
        if self.ui_open not in ("inv", "pets", "storage") or not self.me:
            return False
        page = self.CRAFT_ROWS if self.ui_open == "inv" else 4
        step = {arcade.key.UP: -1, arcade.key.DOWN: 1, arcade.key.PAGEUP: -page,
                arcade.key.PAGEDOWN: page}.get(key)
        if step is None:
            return False
        self.ui_scroll(step)
        return True

    def ui_scroll_pad(self, pad, dt):
        """Controller: the right stick scrolls the open menu (a step every ~0.12s while held)."""
        ry = pad.right[1]
        self._scroll_t = getattr(self, "_scroll_t", 0) - dt
        if abs(ry) < 0.5:
            self._scroll_t = 0
        elif self._scroll_t <= 0:
            self.ui_scroll(1 if ry < 0 else -1)
            self._scroll_t = 0.22 if abs(ry) < 0.85 else 0.12

    def draw_inventory(self):
        me = self.me
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 150))
        l, b, pw, ph = self.inv_layout()
        self.panel(l, l + pw, b, b + ph, 238)
        self.txt("invt", "BACKPACK", l + 24, b + ph - 36, (255, 230, 170), 18, bold=True)
        self.txt("crt", "CRAFTING", l + 410, b + ph - 36, (255, 230, 170), 18, bold=True)
        tabkeys = "LT / RT" if self.use_pad else "click or LEFT / RIGHT"
        self.txt("crs", f"tabs: {tabkeys}", l + 540, b + ph - 36, (170, 170, 170), 11)
        mx, my = self.mouse_screen
        tip = None
        top = self.inv_grid_top()
        shown = self.inv_slots()
        for idx in range(self.INV_COLS * self.INV_ROWS):
            cl, cr, cb, ct = self.grid_rect(l + 24, top, idx, self.INV_COLS)
            if idx < len(shown) and shown[idx][0] in me.hotbar:
                arcade.draw_lrbt_rectangle_filled(cl - 2, cr + 2, cb - 2, ct + 2, (255, 214, 120, 60))
            arcade.draw_lrbt_rectangle_filled(cl, cr, cb, ct, (34, 40, 48, 230))
            arcade.draw_lrbt_rectangle_outline(cl, cr, cb, ct, (255, 255, 255, 35), 1)
            if idx < len(shown):
                it = shown[idx][0]
                arcade.draw_texture_rect(art.icon(it), arcade.XYWH((cl + cr) / 2, (cb + ct) / 2 + 3, 40, 40))
                self.txt(f"ic{idx}", str(me.inv.get(it, 0)), cr - 5, cb + 4, (255, 255, 255), 11, anchor_x="right",
                         bold=True)
                if cl < mx < cr and cb < my < ct:
                    tip = it
        # no item is ever lost: a long backpack just scrolls
        self.draw_grid_bar("inv", l + 24 + self.INV_COLS * (self.SLOT + self.GAP), top, len(me.inv),
                           self.INV_COLS, self.INV_ROWS, "inv")
        # worn gear
        self.txt("worn", "WEARING", l + 24, b + 172, (255, 230, 170), 12, bold=True)
        for slot, (cl, cr, cb, ct) in self.worn_slots():
            it = me.equip.get(slot)
            arcade.draw_lrbt_rectangle_filled(cl, cr, cb, ct, (40, 46, 60, 230))
            arcade.draw_lrbt_rectangle_outline(cl, cr, cb, ct, (150, 180, 255, 90), 1)
            if it:
                arcade.draw_texture_rect(art.icon(it), arcade.XYWH((cl + cr) / 2, (cb + ct) / 2 + 3, 40, 40))
                if cl < mx < cr and cb < my < ct:
                    tip = it
            else:
                self.txt(f"ws{slot}", SLOT_NAMES[slot], (cl + cr) / 2, cb + 26, (130, 140, 160), 10,
                         anchor_x="center")
        self.txt("ar1", f"Armor  {me.gear('armor')}", l + 240, b + 140, (200, 210, 230), 12, bold=True)
        self.txt("ar2", f"Warmth {me.gear('warmth')}", l + 240, b + 118, (170, 215, 255), 12, bold=True)
        if tip:
            self.txt("tipn", ITEMS[tip]["name"], l + 24, b + 66, (255, 230, 170), 14, bold=True)
            self.txt("tipd", ITEMS[tip]["desc"], l + 24, b + 44, (210, 210, 210), 11)
            kind = ITEMS[tip]["kind"]
            how = {"armor": "Click to wear it (click a worn item to take it off).",
                   "material": "Crafting material.",
                   "petarmor": "Put it on a pet: open the Pets menu (P / D-pad up)."}.get(kind, f"Click to put it in hotbar slot {me.selected + 1}.")
            self.txt("tiph", how, l + 24, b + 24, (150, 150, 150), 10)
        else:
            keys = "LB/RB" if self.use_pad else "1-8"
            self.txt("tipn", "Hover an item to inspect it.", l + 24, b + 66, (170, 170, 170), 12)
            self.txt("tipd", f"Click: put in hotbar slot {me.selected + 1} ({keys}). Armor: wear it.",
                     l + 24, b + 44, (150, 150, 150), 11)
            self.txt("tiph", "", l + 24, b + 24, (150, 150, 150), 10)

        for i, (tl, tr, tb, tt) in self.tab_rects():
            on = i == self.craft_tab
            hover = tl < mx < tr and tb < my < tt
            arcade.draw_lrbt_rectangle_filled(tl, tr, tb, tt, (255, 214, 140, 90) if on else
                                              (60, 66, 76, 220) if hover else (34, 40, 48, 220))
            self.txt(f"tab{i}", TAB_NAMES[i], (tl + tr) / 2, tb + 9, (255, 255, 255) if on else (190, 190, 190),
                     12, anchor_x="center", bold=on)
        use_store = self.near_storage(me, 220)
        hover_desc = None
        for gi, rec, (rl, rr, rb, rt) in self.recipe_rows():
            hover = rl < mx < rr and rb < my < rt
            if not explore.known(self, rec):       # explore.py: not found yet - a silhouette and where to look
                desc = explore.draw_locked_recipe(self, gi, rec, (rl, rr, rb, rt), hover)
                hover_desc = desc if hover else hover_desc
                continue
            ok = self.can_craft(me, rec)
            arcade.draw_lrbt_rectangle_filled(rl, rr, rb, rt, (60, 80, 60, 210) if hover and ok else
                                              (70, 50, 50, 190) if hover else (34, 40, 48, 210))
            item = rec["item"]
            arcade.draw_texture_rect(art.icon(item), arcade.XYWH(rl + 20, (rb + rt) / 2, 28, 28))
            label = ITEMS[item]["name"] + (f" x{rec['n']}" if rec["n"] > 1 else "")
            self.txt(f"rn{gi}", label, rl + 42, rb + 10, (255, 255, 255) if ok else (160, 160, 160), 12, bold=True)
            parts = []
            for k, v in rec["cost"].items():
                parts.append(f"{v} {ITEMS[k]['name'].lower()}")
            cost = ", ".join(parts)
            station_ok = self.station_ok(me, rec["at"])
            at = f"  @ {STATIONS[rec['at']]}" if rec["at"] else ""
            col = (140, 230, 140) if ok else (230, 200, 120) if not station_ok and all(
                self.have(me, k, use_store) >= v for k, v in rec["cost"].items()) else (230, 130, 120)
            self.txt(f"rc{gi}", cost + at, rr - 10, rb + 10, col, 10, anchor_x="right")
            if hover:
                hover_desc = ITEMS[item]["desc"]
        bar = self.craft_scrollbar()
        if bar:
            (tl, tr, tb, tt), (hl, hr, hb, ht) = bar
            arcade.draw_lrbt_rectangle_filled(tl, tr, tb, tt, (34, 40, 48, 220))
            arcade.draw_lrbt_rectangle_filled(hl, hr, hb, ht, (255, 214, 140, 200))
            n = len(CRAFT_TABS[TAB_NAMES[self.craft_tab]])
            first = self.craft_scroll()
            how = "right stick" if self.use_pad else "wheel / UP DOWN"
            more = n - first - self.CRAFT_ROWS
            note = f"{more} more below" if more > 0 else "end of list"
            self.txt("crmore", f"recipes {first + 1}-{min(n, first + self.CRAFT_ROWS)} of {n}  -  {note}  "
                     f"({how} to scroll)", l + pw - 22, tb - 14, (255, 214, 140), 10, anchor_x="right")
        stations = [("Workbench", self.station_ok(me, "workbench")), ("Furnace", self.station_ok(me, "furnace")),
                    ("Fire", self.station_ok(me, "campfire")), ("Team storage", use_store)]
        line = "   ".join(f"{n} {'YES' if ok else '-'}" for n, ok in stations)
        self.txt("stations", "Nearby:  " + line, l + 410, b + 44, (170, 200, 170), 11, bold=True)
        self.txt("tipd2", hover_desc or "Yellow cost = you have the stuff, but need to stand at that station.",
                 l + 410, b + 22, (210, 210, 210) if hover_desc else (140, 140, 140), 10)
        if self.use_pad:
            self.draw_pad_cursor()

    def click_inventory(self, x, y, button):
        me = self.me
        for i, (l, r, b, t) in self.tab_rects():
            if l < x < r and b < y < t:
                self.craft_tab = i
                return
        for gi, rec, (l, r, b, t) in self.recipe_rows():
            if l < x < r and b < y < t:
                self.action("craft", i=gi)
                return
        bar = self.craft_scrollbar()
        if bar:                      # click the scrollbar track: page up / down
            (l, r, b, t), (_, _, hb, ht) = bar
            if l - 6 < x < r + 6 and b < y < t:
                self.scroll_crafting(-self.CRAFT_ROWS if y > ht else self.CRAFT_ROWS if y < hb else 0)
                return
        for it, (l, r, b, t) in self.inv_slots():
            if l < x < r and b < y < t:
                self.action("assign", item=it, s=me.selected)
                return
        for slot, (l, r, b, t) in self.worn_slots():
            if l < x < r and b < y < t and me.equip.get(slot):
                self.action("unequip", slot=slot)
                return

    # ------------------------------------------------------------------ team storage
    def storage_layout(self):
        pw, ph = 960, 560
        return W / 2 - pw / 2, H / 2 - ph / 2 + 10, pw, ph

    def storage_cells(self):
        l, b, pw, ph = self.storage_layout()
        top = b + ph - 74
        mine = self.inv_items()
        first = self.grid_first("st_m", len(mine), 5, 5) * 5
        mine = [(it, self.grid_rect(l + 24, top, i, 5)) for i, (it, _) in enumerate(mine[first:first + 25])]
        order = list(ITEMS)
        team = sorted(self.storage.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 999)
        first = self.grid_first("st_t", len(team), 6, 5) * 6
        team = [(it, self.grid_rect(l + 470, top, i, 6)) for i, (it, _) in enumerate(team[first:first + 30])]
        return mine, team

    def amount_rects(self):
        l, b, pw, ph = self.storage_layout()
        return [(i, (l + 470 + i * 92, l + 470 + i * 92 + 84, b + 20, b + 52)) for i in range(len(AMOUNTS))]

    def draw_storage(self):
        me = self.me
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 150))
        l, b, pw, ph = self.storage_layout()
        self.panel(l, l + pw, b, b + ph, 238)
        self.txt("st1", "YOUR BACKPACK", l + 24, b + ph - 40, (255, 230, 170), 17, bold=True)
        self.txt("st2", "TEAM STORAGE", l + 470, b + ph - 40, (170, 230, 170), 17, bold=True)
        self.txt("st3", "shared by everyone - safe when you die", l + 470, b + ph - 58, (150, 190, 150), 10)
        mx, my = self.mouse_screen
        mine, team = self.storage_cells()
        tip = None
        top = b + ph - 74
        for idx in range(25):
            cl, cr, cb, ct = self.grid_rect(l + 24, top, idx, 5)
            arcade.draw_lrbt_rectangle_filled(cl, cr, cb, ct, (34, 40, 48, 230))
        for idx in range(30):
            cl, cr, cb, ct = self.grid_rect(l + 470, top, idx, 6)
            arcade.draw_lrbt_rectangle_filled(cl, cr, cb, ct, (30, 46, 36, 230))
        for side, cells, src in (("m", mine, me.inv), ("t", team, self.storage)):
            for i, (it, (cl, cr, cb, ct)) in enumerate(cells):
                hover = cl < mx < cr and cb < my < ct
                if hover:
                    arcade.draw_lrbt_rectangle_outline(cl, cr, cb, ct, (255, 230, 150), 2)
                    tip = (it, side)
                arcade.draw_texture_rect(art.icon(it), arcade.XYWH((cl + cr) / 2, (cb + ct) / 2 + 3, 40, 40))
                self.txt(f"s{side}{i}", str(src.get(it, 0)), cr - 5, cb + 4, (255, 255, 255), 11, anchor_x="right",
                         bold=True)
        self.draw_grid_bar("st_m", l + 24 + 5 * (self.SLOT + self.GAP), top, len(me.inv), 5, 5, "stm")
        self.draw_grid_bar("st_t", l + 470 + 6 * (self.SLOT + self.GAP), top, len(self.storage), 6, 5, "stt")
        self.txt("amt", "Move:", l + 410, b + 31, (220, 220, 220), 12, bold=True)
        for i, (al, ar, ab, at) in self.amount_rects():
            on = i == self.move_amount
            arcade.draw_lrbt_rectangle_filled(al, ar, ab, at, (255, 214, 140, 110) if on else (40, 46, 56, 230))
            arcade.draw_lrbt_rectangle_outline(al, ar, ab, at, (255, 255, 255, 60), 1)
            self.txt(f"am{i}", f"x{AMOUNTS[i]}" if AMOUNTS[i] != "All" else "ALL", (al + ar) / 2, ab + 10,
                     (255, 255, 255), 12, anchor_x="center", bold=on)
        keys = "X: change amount   A: move   B: close" if self.use_pad else \
            "Click an item to move it across.  1-4 or the buttons pick how many.  Shift-click = all.  E / ESC to close."
        self.txt("sth", keys, l + 24, b + 70, (170, 170, 170), 10)
        if tip:
            it, side = tip
            verb = "Put in storage" if side == "m" else "Take out"
            self.txt("stt", f"{ITEMS[it]['name']}  -  {verb}", l + 24, b + 36, (255, 230, 170), 13, bold=True)
        else:
            self.txt("stt", "Pets on WORK duty bring what they gather here.", l + 24, b + 36, (150, 150, 150), 11)
        if self.use_pad:
            self.draw_pad_cursor()

    def click_storage(self, x, y, button, modifiers=0):
        for i, (l, r, b, t) in self.amount_rects():
            if l < x < r and b < y < t:
                self.move_amount = i
                return
        amt = AMOUNTS[self.move_amount]
        if modifiers & arcade.key.MOD_SHIFT:
            amt = "All"
        mine, team = self.storage_cells()
        for it, (l, r, b, t) in mine:
            if l < x < r and b < y < t:
                n = self.me.inv.get(it, 0) if amt == "All" else amt
                self.action("deposit", item=it, n=n)
                return
        for it, (l, r, b, t) in team:
            if l < x < r and b < y < t:
                n = self.storage.get(it, 0) if amt == "All" else amt
                self.action("withdraw", item=it, n=n)
                return

    def draw_pad_cursor(self):
        x, y = self.mouse_screen
        arcade.draw_circle_filled(x, y, 9, (255, 214, 120, 120))
        arcade.draw_circle_outline(x, y, 9, (255, 255, 255, 230), 2)

    # ------------------------------------------------------------------ boss intro
    def draw_cutscene(self):
        c = self.cut
        if c.get("mode") == "retreat":
            self.draw_retreat()
            return
        t, dur = c["t"], c["dur"]
        info = BOSSES[c["kind"]]
        k = ease(t / 0.8) if t < dur - 0.8 else ease((dur - t) / 0.8)
        bar = 92 * k
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, int(70 * k)))
        arcade.draw_lrbt_rectangle_filled(0, W, H - bar, H, (0, 0, 0, 255))
        arcade.draw_lrbt_rectangle_filled(0, W, 0, bar, (0, 0, 0, 255))
        fade = ease((t - 1.4) / 0.6) * (ease((dur - 0.6 - t) / 0.5) if t > dur - 1.1 else 1)
        if fade <= 0:
            return
        a = int(255 * fade)
        self.txt("cut_n", f"NIGHT {c['night']}", W / 2, H - 60, (200, 180, 160, a), 14, anchor_x="center", bold=True)
        name = info["name"]
        shown = name[:max(0, min(len(name), int((t - 1.6) * 16)))]
        jitter = math.sin(t * 40) * 2 if t < 3.0 else 0
        self.txt("cut_name_s", shown, W / 2 + 3 + jitter, H / 2 + 147, (0, 0, 0, a), 46, anchor_x="center", bold=True)
        self.txt("cut_name", shown, W / 2 + jitter, H / 2 + 150, (255, 120, 80, a), 46, anchor_x="center", bold=True)
        if t > 2.6:
            ta = int(255 * fade * ease((t - 2.6) / 0.5))
            self.txt("cut_tag", info["tag"], W / 2, H / 2 + 112, (240, 230, 220, ta), 17, anchor_x="center")
        for i, line in enumerate(info["moves"]):
            st = 3.4 + i * 0.8
            if t > st:
                la = int(255 * fade * ease((t - st) / 0.4))
                y = 190 - i * 34
                self.panel(W / 2 - 400, W / 2 + 400, y - 10, y + 22, int(150 * fade))
                head, _, rest = line.partition(" - ")
                if rest:
                    self.txt(f"cut_mh{i}", head, W / 2 - 384, y, (255, 170, 120, la), 13, bold=True)
                    self.txt(f"cut_mr{i}", rest, W / 2 - 384 + 150, y, (235, 235, 235, la), 12)
                else:
                    self.txt(f"cut_mh{i}", "", W / 2 - 384, y, (255, 170, 120, la), 13, bold=True)
                    self.txt(f"cut_mr{i}", head, W / 2 - 384, y, (235, 235, 235, la), 12)
        skip = "A / START to skip" if self.use_pad else "ENTER / click to skip"
        self.txt("cut_skip", skip, W - 20, 30, (180, 180, 180, int(200 * k)), 11, anchor_x="right")

    def draw_retreat(self):
        """Dawn cutscene: the boss gets away - but it'll be back."""
        c = self.cut
        t, dur = c["t"], c["dur"]
        info = BOSSES[c["kind"]]
        k = ease(t / 0.8) if t < dur - 0.8 else ease((dur - t) / 0.8)
        bar = 80 * k
        arcade.draw_lrbt_rectangle_filled(0, W, H - bar, H, (0, 0, 0, 255))
        arcade.draw_lrbt_rectangle_filled(0, W, 0, bar, (0, 0, 0, 255))
        fade = ease((t - 0.5) / 0.6) * (ease((dur - 0.4 - t) / 0.5) if t > dur - 0.9 else 1)
        if fade > 0:
            a = int(255 * fade)
            self.txt("ret_d", f"DAWN  -  NIGHT {c['night']} SURVIVED", W / 2, H - 52, (255, 220, 160, a), 14,
                     anchor_x="center", bold=True)
            self.txt("ret_ns", f"{info['name']} RETREATS", W / 2 + 3, H / 2 + 137, (0, 0, 0, a), 38,
                     anchor_x="center", bold=True)
            self.txt("ret_n", f"{info['name']} RETREATS", W / 2, H / 2 + 140, (255, 150, 100, a), 38,
                     anchor_x="center", bold=True)
            if t > 1.4:
                la = int(255 * fade * ease((t - 1.4) / 0.5))
                self.txt("ret_l", "...but it will be back tomorrow night.", W / 2, H / 2 + 98, (240, 230, 220, la), 19,
                         anchor_x="center")
            if t > 2.2 and c.get("hp"):
                la = int(255 * fade * ease((t - 2.2) / 0.5))
                self.txt("ret_h", c["hp"], W / 2, 46,
                         (230, 190, 170, la), 13, anchor_x="center")
        skip = "A / START to skip" if self.use_pad else "ENTER / click to skip"
        self.txt("cut_skip", skip, W - 20, 20, (180, 180, 180, int(200 * k)), 11, anchor_x="right")

    # ------------------------------------------------------------------ screens
    def menu_items(self):
        if self.menu == "main":
            name, day, night, gap = self.chosen_difficulty()
            return ["Play solo", "Host co-op game", "Join co-op game", "Local co-op (split screen)",
                    "Load saved game", f"Difficulty:  {name}  ({day}s / {night}s,  boss every {gap} nights)",
                    "Screen & graphics...", "Quit"]
        if self.menu == "gfx":
            onoff = lambda v: "On" if v else "Off"
            smooth = self.smooth_wanted()
            later = "   (after a restart)" if smooth != getattr(self, "smooth_at_start", smooth) else ""
            return [f"Fullscreen:  {onoff(self.fullscreen)}   (F11)",
                    f"Smooth edges:  {onoff(smooth)}{later}",
                    f"Glow effects:  {onoff(self.post_wanted())}",
                    f"Sun shadows:  {self.shadows_mode().capitalize()}", "Back"]
        if self.menu == "local":
            return []
        if self.menu == "diff":
            cur = self.chosen_difficulty()[0]
            rows = [("\u2022 " if name == cur else "") + self.difficulty_label(name, day, night)
                    for name, day, night in DIFFICULTIES]
            day, night = self.custom_times()
            mark = "\u2022 " if cur == "Custom" else ""
            gap = self.chosen_difficulty()[3]
            return rows + [f"<      {mark}Custom day:  {day}s      >", f"<      {mark}Custom night:  {night}s      >",
                           f"<      Nights between bosses:  {gap}      >", "Back"]
        if self.menu == "load":
            page = self.save_list[self.save_page * 5:(self.save_page + 1) * 5]
            rows = [savegame.save_label(meta) for _, meta in page]
            if len(self.save_list) > 5:
                pages = (len(self.save_list) + 4) // 5
                rows.append(f"More saves...   (page {self.save_page + 1} of {pages})")
            return rows + ["Back"]
        if self.menu == "save":
            saved = self.picked_difficulty()
            now = self.chosen_difficulty()
            rows = ["Play solo", "Host co-op game", "Local co-op (split screen)"]
            if tuple(saved) != tuple(now):
                use = self.use_title_difficulty
                d = now if use else saved
                gap = d[3] if len(d) > 3 else BOSS_EVERY
                rows.append(f"Difficulty:  {d[0]} {d[1]}s / {d[2]}s, boss every {gap}   "
                            f"({'title-screen setting' if use else 'as saved'})")
            rows.append("Delete this save")
            return rows + ["Back"]
        if self.menu == "confirm":
            return ["No, keep it", "Yes, delete it forever"]
        games = self.finder.list() if self.finder else []
        return [f"{v[0]}'s game   ({v[1]}/4)   {k[0]}" for k, v in games] + ["Connect to IP:  " + self.ip_text, "Back"]

    def picked_difficulty(self):
        meta = self.picked_save[1] if self.picked_save else {}
        return meta.get("difficulty") or self.chosen_difficulty()

    def menu_back(self):
        if self.menu == "confirm":          # "No" / ESC: back where you came from, nothing deleted
            self.menu, self.menu_sel = self.confirm_from
            self.menu_note = savegame.save_label(self.picked_save[1]) if self.menu == "save" else ""
            return
        back = {"diff": ("main", 5), "load": ("main", 4), "save": ("load", 0), "gfx": ("main", 6)}
        self.menu, self.menu_sel = back.get(self.menu, ("main", 0))
        self.menu_note = ""

    def ask_delete(self, save, came_from):
        """Open the 'are you sure?' screen for one save. 'No' is picked by default."""
        self.picked_save = save
        self.confirm_from = came_from
        self.menu, self.menu_sel = "confirm", 0
        self.menu_note = savegame.save_label(save[1])

    def delete_highlighted(self):
        """DELETE / BACKSPACE (or X on a controller) on the Load list."""
        page = self.save_list[self.save_page * 5:(self.save_page + 1) * 5]
        if self.menu == "load" and self.menu_sel < len(page):
            self.ask_delete(page[self.menu_sel], ("load", self.menu_sel))

    def diff_adjust(self, i, amount):
        """LEFT / RIGHT on the custom day / night rows of the difficulty screen."""
        n = len(DIFFICULTIES)
        if i == n:
            self.nudge_custom("day", amount)
        elif i == n + 1:
            self.nudge_custom("night", amount)
        elif i == n + 2:
            self.nudge_gap(amount)

    def menu_pick(self, i, x=None):
        import net
        items = self.menu_items()
        if not items or self.joiner:
            return
        i = max(0, min(len(items) - 1, i))
        label = items[i]
        if self.menu == "main":
            self.pending_save = None
            if i == 0:
                self.net = None
                self.start()
            elif i == 1:
                self.start_host()
            elif i == 2:
                self.menu, self.menu_sel, self.menu_note = "join", 0, ""
                if not self.finder:
                    self.finder = net.Finder()
            elif i == 3:
                self.local_lobby_open()
            elif i == 4:
                self.save_list = savegame.list_saves()
                if not self.save_list:
                    self.menu_note = "No saved games yet - games save every morning and when you leave."
                else:
                    self.menu, self.menu_sel, self.menu_note, self.save_page = "load", 0, "", 0
            elif i == 5:
                names = [d[0] for d in DIFFICULTIES]
                cur = self.chosen_difficulty()[0]
                self.menu, self.menu_note = "diff", ""
                self.menu_sel = names.index(cur) if cur in names else len(names)
            elif i == 6:
                self.menu, self.menu_sel, self.menu_note = "gfx", 0, ""
            else:
                arcade.exit()
        elif self.menu == "gfx":        # post3d.py: smooth edges (MSAA) and glow (bloom); shadows3d.py: shadows
            if i == 0:
                self.toggle_fullscreen()
            elif i == 1:
                self.toggle_smooth()
            elif i == 2:
                self.toggle_glow()
            elif i == 3:
                self.toggle_shadows()
            else:
                self.menu_back()
        elif self.menu == "diff":
            n = len(DIFFICULTIES)
            if i < n:
                self.set_difficulty(DIFFICULTIES[i][0])
            elif i in (n, n + 1, n + 2):
                if x is not None:      # clicked: left half = shorter, right half = longer
                    self.diff_adjust(i, -5 if x < W / 2 else 5)
                elif i < n + 2:
                    self.set_difficulty("Custom")
            else:
                self.menu_back()
        elif self.menu == "load":
            page = self.save_list[self.save_page * 5:(self.save_page + 1) * 5]
            if i < len(page):
                self.picked_save = page[i]
                self.use_title_difficulty = False
                self.menu, self.menu_sel, self.menu_note = "save", 0, savegame.save_label(page[i][1])
            elif label.startswith("More"):
                pages = (len(self.save_list) + 4) // 5
                self.save_page = (self.save_page + 1) % pages
                self.menu_sel = 0
            else:
                self.menu_back()
        elif self.menu == "save":
            path, meta = self.picked_save
            if label.startswith("Delete"):
                self.ask_delete(self.picked_save, ("save", i))
                return
            if label.startswith("Back"):
                self.menu_back()
                return
            if label.startswith("Difficulty"):
                self.use_title_difficulty = not self.use_title_difficulty
                return
            data = savegame.read_save(path)
            if data is None:
                self.menu_note = "That save couldn't be read (it may be from another version)."
                return
            data["_path"] = path
            if self.use_title_difficulty:
                data["meta"]["difficulty"] = list(self.chosen_difficulty())
            if i == 0:
                self.net = None
                self.start(data)
            elif i == 1:
                self.start_host(data)
            else:
                self.pending_save = data
                self.local_lobby_open()
        elif self.menu == "confirm":
            if i == 1:
                path, meta = self.picked_save
                savegame.delete_save(path)
                self.save_list = savegame.list_saves()
                pages = max(1, (len(self.save_list) + 4) // 5)
                self.save_page = min(self.save_page, pages - 1)
                self.menu, self.menu_sel = ("load", 0) if self.save_list else ("main", 4)
                self.menu_note = f"Deleted:  {savegame.save_label(meta)}"
            else:
                self.menu_back()
        else:
            games = self.finder.list() if self.finder else []
            if i < len(games):
                (ip, port), _ = games[i]
                self.ip_text = ip
                self.start_join(ip)
            elif label.startswith("Connect"):
                self.start_join(self.ip_text)
            else:
                self.menu, self.menu_sel, self.menu_note = "main", 2, ""

    def menu_rows(self):
        items = self.menu_items()
        many = len(items) > 6
        top = 400 if many else 360 if self.menu != "main" else 350
        gap, half = (38, 16) if many else (46, 18)
        hw = 300 if self.menu in ("diff", "load", "save") else 270 if self.menu == "main" else 230
        if self.menu == "confirm":
            top, hw = 290, 200
        return [(it, (W / 2 - hw, W / 2 + hw, top - i * gap - half, top - i * gap + half)) for i, it in enumerate(items)]

    def draw_title(self):
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 90))
        self.txt("t1", "LAST LIGHT", W / 2 + 3, H - 157, (0, 0, 0, 160), 68, anchor_x="center", bold=True)
        self.txt("t2", "LAST LIGHT", W / 2, H - 154, (255, 214, 140), 68, anchor_x="center", bold=True)
        self.txt("t3", "Gather by day.  Build by dusk.  Survive the night - together.", W / 2, H - 200,
                 (230, 230, 230), 17, anchor_x="center")
        if self.menu == "join":
            self.txt("jt", "JOIN A GAME", W / 2, 420, (255, 230, 170), 18, anchor_x="center", bold=True)
            if not (self.finder and self.finder.list()):
                dots = "." * (int(self.flame_t * 2) % 4)
                self.txt("jlook", f"Looking for games on your Wi-Fi{dots}", W / 2, 394, (190, 190, 190), 12,
                         anchor_x="center")
        if self.menu == "local":
            self.draw_lobby()
            return
        heads = {"diff": "DIFFICULTY  -  day & night length, and how often bosses come",
                 "load": "LOAD A SAVED GAME", "save": "RESUME THIS GAME AS...",
                 "confirm": "DELETE THIS SAVE?", "gfx": "SCREEN & GRAPHICS"}
        if self.menu == "confirm":
            self.txt("conf0", "DELETE THIS SAVE?", W / 2, 440, (255, 140, 120), 24, anchor_x="center", bold=True)
            self.txt("conf1", self.menu_note, W / 2, 400, (255, 255, 255), 15, anchor_x="center", bold=True)
            self.txt("conf2", "This can't be undone - the world, everyone's stuff and pets are gone for good.",
                     W / 2, 370, (255, 170, 150), 13, anchor_x="center")
        elif self.menu in heads:
            top = self.menu_rows()[0][1][3]
            self.txt("mhead", heads[self.menu], W / 2, top + 16, (255, 230, 170), 16, anchor_x="center", bold=True)
        for i, (label, (l, r, b, t)) in enumerate(self.menu_rows()):
            sel = i == self.menu_sel
            arcade.draw_lrbt_rectangle_filled(l, r, b, t, (255, 214, 140, 60) if sel else (14, 18, 22, 170))
            arcade.draw_lrbt_rectangle_outline(l, r, b, t, (255, 214, 140) if sel else (255, 255, 255, 50),
                                               2 if sel else 1)
            caret = "_" if label.startswith("Connect") and sel and int(self.flame_t * 2) % 2 == 0 else ""
            self.txt(f"menu{self.menu}{i}", label + caret, W / 2, b + 12, (255, 255, 255), 15, anchor_x="center",
                     bold=sel)
        if self.menu_note and self.menu != "confirm":
            self.txt("note", self.menu_note, W / 2, 96, (255, 200, 150), 13, anchor_x="center")
        pad = "Controller ready - D-pad + A to pick" if self.pad.connected else "Plug in a controller any time"
        self.txt("t5", f"Playing as {self.my_name}     |     {pad}", W / 2, 70, (200, 200, 200), 12,
                 anchor_x="center")
        if self.menu == "join":
            self.txt("t6", "Type an IP with the keyboard, ENTER to connect, ESC to go back", W / 2, 46,
                     (160, 160, 160), 11, anchor_x="center")
        elif self.menu == "diff":
            lo_d, hi_d = CUSTOM_DAY_LIMITS
            lo_n, hi_n = CUSTOM_NIGHT_LIMITS
            lo_g, hi_g = BOSS_GAP_LIMITS
            self.txt("t6", f"LEFT / RIGHT or click the arrows (SHIFT = 30s).   Day {lo_d}-{hi_d}s,  night {lo_n}-{hi_n}s,  "
                     f"bosses every {lo_g}-{hi_g} nights.   Saved with each game.", W / 2, 46, (160, 160, 160), 11,
                     anchor_x="center")
        elif self.menu == "load":
            delete = "X" if self.use_pad else "DELETE"
            self.txt("t6", f"Pick a save to play it.   {delete}: delete the highlighted save.   ESC = back",
                     W / 2, 46, (160, 160, 160), 11, anchor_x="center")
        elif self.menu == "save":
            self.txt("t6", "Games save every morning, when you leave, and with S on the pause screen.   ESC = back",
                     W / 2, 46, (160, 160, 160), 11, anchor_x="center")
        elif self.menu == "gfx":
            self.txt("t6", "Smooth edges: no jagged edges (restart to change).   Glow: fires, crystals and eyes "
                     "shine at night.", W / 2, 46, (160, 160, 160), 11, anchor_x="center")
            self.txt("t7", "Sun shadows: trees, walls and creatures cast real shadows by day.   Turn things off "
                     "(or shadows to Low) if the game is slow.", W / 2, 28, (160, 160, 160), 11, anchor_x="center")
        elif self.menu == "confirm":
            self.txt("t6", "ESC / B = keep it", W / 2, 46, (160, 160, 160), 11, anchor_x="center")
        else:
            self.txt("t6", "Tame animals  -  craft armor  -  explore the caves  -  a boss rises every 3rd night",
                     W / 2, 46, (160, 160, 160), 11, anchor_x="center")

    def draw_help(self, overlay):
        if overlay:
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 180))
            self.txt("ph", "PAUSED" if not self.net else "HELP  (the game keeps going in co-op!)", W / 2, H - 70,
                     (255, 214, 140), 28, anchor_x="center", bold=True)
            if self.net == "client":
                bottom = "ESC / MENU to resume       Q / VIEW: leave to title  (the host saves the game)"
            else:
                bottom = "ESC / MENU to resume       S / X: save game       Q / VIEW: save & leave to title"
            self.txt("ph2", bottom, W / 2, 40, (230, 230, 230), 13, anchor_x="center")
        lines = [
            ("WASD  |  L-stick", "move"), ("Mouse  |  R-stick", "aim"),
            ("Left-click  |  A / RT", "attack, chop, mine, hunt"),
            ("Right-click  |  LT", "build / eat / tame (hold the animal's food)"),
            ("1-8, wheel  |  LB / RB", "choose hotbar item"),
            ("TAB  |  Y", "backpack, crafting & armor"),
            ("E  |  B", "open storage, search a place, use cave entrance, drink"),
            ("Q  |  B", "quick eat / drink"), ("P  |  D-pad up", "Pets menu: names, orders, pet armor"),
            ("F  |  D-pad down", "quick order for all pets: follow / work / stay"),
            ("SHIFT + move  |  click L-stick", "sprint (uses energy - walking is free)"),
            ("SHIFT standing  |  hold X", "rest (heals in a hut or by a fire)"),
        ]
        top = H - 120
        self.panel(W / 2 - 330, W / 2 + 330, top - len(lines) * 28 - 16, top + 14, 160)
        for i, (k, v) in enumerate(lines):
            y = top - 12 - i * 28
            self.txt(f"hk_{i}", k, W / 2 - 40, y, (255, 214, 140), 13, anchor_x="right", bold=True)
            self.txt(f"hv_{i}", v, W / 2 - 20, y, (230, 230, 230), 13)
        tips = ["Die and your backpack drops where you fell - get it back before the next dawn (or lose it).",
                "Nights are cold: stay by fire, in a hut, or wear warm clothes (fur cloak!).",
                "Workbench -> leather, armor, iron gear.  Furnace -> iron ingots.  Caves -> iron, coal, crystal."]
        for i, tline in enumerate(tips):
            self.txt(f"tip_{i}", tline, W / 2, top - len(lines) * 28 - 40 - i * 20, (180, 200, 180), 11,
                     anchor_x="center")

    def draw_dead(self):
        me = self.me
        arcade.draw_lrbt_rectangle_filled(0, W, H / 2 - 70, H / 2 + 90, (40, 0, 0, 160))
        self.txt("d1", "YOU DIED", W / 2, H / 2 + 34, (255, 80, 70), 44, anchor_x="center", bold=True)
        if me.respawn_t > 0:
            sub = f"Back on your feet in {int(me.respawn_t) + 1}s - at your base, with the starting things."
        else:
            left = int(self.secs_until(DAWN_START))
            sub = f"You died at night - you'll come back at dawn ({left}s)."
            if self.fast_forward:
                sub = "Everyone is down... the night passes quickly."
        self.txt("d2", sub, W / 2, H / 2 - 10, (240, 230, 230), 15, anchor_x="center")
        self.txt("d3", self.pack_dead_lines(), W / 2, H / 2 - 40, (220, 190, 190), 12, anchor_x="center")
