"""
local_coop.py - split-screen couch co-op: 1-4 players on one computer.

Each player uses a controller or the keyboard + mouse. Every player gets their own slice of
the screen (side by side for two, corners for three or four) with their own camera, light,
HUD and hotbar. The backpack, storage and pause screens open full-screen and pause the game,
just like in single player.

How it works: the game was written around "self.me" (the player at this screen). For local
co-op we keep a list of slots and quickly *focus* each one in turn - swapping in that player's
survivor, controller, camera and messages - then run the normal input / camera / drawing code.
"""
import arcade

import ui
from gamepad import PadView
from settings import *

FULL_W, FULL_H = SCREEN_WIDTH, SCREEN_HEIGHT
LOBBY_COLORS = [(110, 200, 210), (240, 120, 110), (160, 220, 110), (250, 210, 100)]


class NullPad:
    """The keyboard player's 'controller': never pressed."""
    connected = False
    name = None
    left = right = (0.0, 0.0)
    down = pressed = frozenset()
    active = False

    def rumble(self, *a, **k):
        pass


NULL_PAD = NullPad()


class Slot:
    def __init__(self, player, src):
        self.p = player
        self.src = src                       # "kb" or a PadView
        self.camera = arcade.Camera2D()
        self.gui = arcade.Camera2D()
        self.cam_pos = list(player.pos)
        self.message, self.message_t = "", 0.0
        self.pad_was = True
        self.vw, self.vh = FULL_W, FULL_H

    @property
    def kb(self):
        return self.src == "kb"


class LocalCoop:
    # ------------------------------------------------------------------ lobby
    def local_lobby_open(self):
        self.menu, self.menu_sel, self.menu_note = "local", 0, ""
        self.lobby = []          # [("kb", None) | ("pad", set_of_device_keys)]

    def _owner_of(self, key):
        for i, (kind, keys) in enumerate(self.lobby):
            if kind == "pad" and key in keys:
                return i
        return None

    def lobby_pad(self):
        """Controllers: A joins, B leaves (or goes back), START begins."""
        devs = self.pad.devices
        pressed_a = [k for k, d in devs.items() if "a" in d.pressed]
        # a second copy of an already-joined pad pressing at the same moment belongs to that player
        owners = {self._owner_of(k) for k in pressed_a} - {None}
        new = [k for k in pressed_a if self._owner_of(k) is None]
        if new:
            if owners:
                self.lobby[min(owners)][1].update(new)
            elif len(self.lobby) < 4:
                self.lobby.append(("pad", set(new)))
                self._play("craft", 0.3)
        for k, d in devs.items():
            if "b" in d.pressed:
                i = self._owner_of(k)
                if i is not None:
                    self.lobby.pop(i)
                    return
                if not self.lobby:
                    self.menu, self.menu_sel = "main", 3
                    return
            if "start" in d.pressed and self.lobby:
                self.start_local()
                return

    def lobby_key(self, key):
        if key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.SPACE):
            if not any(kind == "kb" for kind, _ in self.lobby):
                if len(self.lobby) < 4:
                    self.lobby.append(("kb", None))
                    self._play("craft", 0.3)
            else:
                self.start_local()
        elif key == arcade.key.ESCAPE:
            kb = [i for i, (kind, _) in enumerate(self.lobby) if kind == "kb"]
            if kb:
                self.lobby.pop(kb[0])
            else:
                self.menu, self.menu_sel = "main", 3
        elif key == arcade.key.BACKSPACE:
            self.menu, self.menu_sel = "main", 3

    def lobby_click(self, x, y):
        l, r, b, t = self.lobby_start_rect()
        if l < x < r and b < y < t and self.lobby:
            self.start_local()
            return
        l, r, b, t = self.lobby_back_rect()
        if l < x < r and b < y < t:
            self.menu, self.menu_sel = "main", 3

    def lobby_start_rect(self):
        return FULL_W / 2 - 230, FULL_W / 2 - 10, 90, 130

    def lobby_back_rect(self):
        return FULL_W / 2 + 10, FULL_W / 2 + 230, 90, 130

    def draw_lobby(self):
        W, H = FULL_W, FULL_H
        self.txt("lob_t", "LOCAL CO-OP  -  split screen", W / 2, 430, (255, 230, 170), 20, anchor_x="center", bold=True)
        if self.pending_save:
            self.txt("lob_save", f"Resuming saved game - Day {self.pending_save['day']}  (P1, P2... get their own "
                     "stuff back)", W / 2, 462, (170, 230, 170), 13, anchor_x="center")
        self.txt("lob_s", "Controllers: press A to join.     Keyboard + mouse: press ENTER to join.", W / 2, 400,
                 (210, 210, 210), 12, anchor_x="center")
        cw = 220
        x0 = W / 2 - (4 * cw + 3 * 14) / 2
        for i in range(4):
            l = x0 + i * (cw + 14)
            joined = i < len(self.lobby)
            col = LOBBY_COLORS[i]
            arcade.draw_lrbt_rectangle_filled(l, l + cw, 170, 370, (14, 18, 22, 200))
            arcade.draw_lrbt_rectangle_outline(l, l + cw, 170, 370, col + ((255,) if joined else (60,)), 2)
            self.txt(f"lob_p{i}", f"PLAYER {i + 1}", l + cw / 2, 340, col if joined else (120, 120, 120), 15,
                     anchor_x="center", bold=True)
            if joined:
                kind = self.lobby[i][0]
                arcade.draw_texture_rect(__import__("art").player(i), arcade.XYWH(l + cw / 2, 270, 70, 70))
                self.txt(f"lob_d{i}", "Keyboard + mouse" if kind == "kb" else "Controller", l + cw / 2, 200,
                         (230, 230, 230), 12, anchor_x="center")
            else:
                pulse = 120 + int(60 * (1 + __import__("math").sin(self.flame_t * 3 + i)))
                self.txt(f"lob_d{i}", "press A / ENTER", l + cw / 2, 260, (pulse, pulse, pulse), 12,
                         anchor_x="center")
        for key, (l, r, b, t), label, on in (("lob_go", self.lobby_start_rect(),
                                              f"START  ({len(self.lobby)} player{'s' if len(self.lobby) != 1 else ''})",
                                              bool(self.lobby)),
                                             ("lob_back", self.lobby_back_rect(), "Back", True)):
            arcade.draw_lrbt_rectangle_filled(l, r, b, t, (255, 214, 140, 90) if on else (40, 40, 40, 160))
            arcade.draw_lrbt_rectangle_outline(l, r, b, t, (255, 255, 255, 80), 1)
            self.txt(key, label, (l + r) / 2, b + 13, (255, 255, 255) if on else (140, 140, 140), 14,
                     anchor_x="center", bold=True)
        self.txt("lob_h", "Start: START button or ENTER (once you've joined).   Leave: B / ESC.", W / 2, 60,
                 (170, 170, 170), 11, anchor_x="center")

    # ------------------------------------------------------------------ starting / stopping
    def start_local(self):
        entries = list(self.lobby)
        self.net = None
        self.start(self.pending_save)      # a saved game picked on the title screen, or a new one
        self.pending_save = None
        self.intro = None             # straight into the action with your friends
        self.state = "playing"
        first = self.me
        self.local = True
        self.slots = []
        self._cam_full, self._gui_full = self.camera, self.gui
        for i, (kind, keys) in enumerate(entries):
            p = first if i == 0 else self.add_player(f"P{i + 1}")
            p.name = f"P{i + 1}"
            src = "kb" if kind == "kb" else PadView(self.pad, keys)
            self.slots.append(Slot(p, src))
        self.layout_slots()
        self.focus(self.slots[0])
        self.ui_slot = None
        for s in self.slots:
            s.message, s.message_t = "Day 1. Gather wood and stone before dark - together!", 6.0

    def local_end(self):
        if getattr(self, "local", False):
            self.unfocus()
            self.local = False
            self.slots = []
            self.camera, self.gui = self._cam_full, self._gui_full
            ui.W, ui.H = FULL_W, FULL_H
            self.txt_prefix = ""

    def layout_slots(self):
        n = len(self.slots)
        for i, s in enumerate(self.slots):
            if n == 1:
                x, y, w, h, scale = 0, 0, FULL_W, FULL_H, 1.0
            elif n == 2:
                x, y, w, h, scale = i * FULL_W / 2, 0, FULL_W / 2, FULL_H, 1.0
            else:
                x, y, w, h, scale = (i % 2) * FULL_W / 2, (1 - i // 2) * FULL_H / 2, FULL_W / 2, FULL_H / 2, 0.75
            vw, vh = int(round(w / scale)), int(round(h / scale))   # whole pixels (lighting textures need ints)
            s.vw, s.vh = vw, vh
            vp = self.fit_rect(x, y, w, h)     # fullscreen scaling (options.py)
            proj = arcade.LRBT(-vw / 2, vw / 2, -vh / 2, vh / 2)
            s.camera = arcade.Camera2D(viewport=vp, projection=proj, position=tuple(s.cam_pos), scissor=vp)
            s.gui = arcade.Camera2D(viewport=vp, projection=proj, position=(vw / 2, vh / 2), scissor=vp)
            s.rect = (x, y, w, h)

    # ------------------------------------------------------------------ focus swapping
    def focus(self, s):
        cur = getattr(self, "focused", None)
        if cur is s:
            return
        if cur is not None:
            cur.message, cur.message_t = self.message, self.message_t
            cur.pad_was = self.pad_was
        self.focused = s
        self.me = s.p
        self.camera, self.gui = s.camera, s.gui
        self.cam_pos = s.cam_pos
        self.message, self.message_t = s.message, s.message_t
        self.pad_was = s.pad_was
        self.use_pad = not s.kb
        self.txt_prefix = f"v{self.slots.index(s)}:"

    def unfocus(self):
        cur = getattr(self, "focused", None)
        if cur is not None:
            cur.message, cur.message_t = self.message, self.message_t
        self.focused = None

    def slot_of(self, p):
        for s in self.slots:
            if s.p is p:
                return s
        return None

    def kb_slot(self):
        return next((s for s in self.slots if s.kb), None)

    def local_say(self, msg, t, to):
        for s in self.slots:
            if to is None or s.p is to:
                if s is self.focused:
                    self.message, self.message_t = msg, t
                else:
                    s.message, s.message_t = msg, t

    def local_rumble(self, strength, duration, to):
        for s in self.slots:
            if not s.kb and (to is None or s.p is to):
                s.src.rumble(strength, duration)

    def layer_seen(self, layer):
        if getattr(self, "local", False):
            return any(s.p.layer == layer for s in self.slots)
        return layer == self.view_layer

    # ------------------------------------------------------------------ per-frame
    def local_input(self, dt):
        """Run each player's controller through the normal controller code, one at a time."""
        hub = self.pad
        if self.ui_open and self.ui_slot is None:     # opened with the keyboard / mouse
            self.ui_slot = getattr(self, "_pending_ui_slot", None) or self.kb_slot() or self.slots[0]
        self._pending_ui_slot = None
        self._adopt_twins()
        for s in self.slots:
            if self.ui_open and self.ui_slot is not None and s is not self.ui_slot:
                continue
            self.focus(s)
            if s.kb:
                continue
            self.pad = s.src
            was_ui = self.ui_open
            try:
                self.handle_pad(dt)
            finally:
                self.pad = hub
            if self.ui_open and not was_ui:
                self.ui_slot = s
            if self.state != "playing" or not getattr(self, "local", False):
                return
        if not self.ui_open:
            self.ui_slot = None

    def _adopt_twins(self):
        """macOS shows some pads twice; a spare copy that presses with a player's pad joins that player."""
        owned = {}
        for s in self.slots:
            if not s.kb:
                for k in s.src.keys:
                    owned[k] = s
        for k, d in self.pad.devices.items():
            if k in owned or not d.pressed:
                continue
            for k2, s in owned.items():
                d2 = self.pad.devices.get(k2)
                if d2 and d2.pressed & d.pressed:
                    s.src.keys.add(k)
                    break

    def local_move(self, dt):
        keys, mouse = self.keys, self.mouse_down
        for s in self.slots:
            self.focus(s)
            if not s.kb:
                self.keys, self.mouse_down = set(), False
                hub, self.pad = self.pad, s.src
            try:
                self.read_local_input()
            finally:
                if not s.kb:
                    self.keys, self.mouse_down = keys, mouse
                    self.pad = hub
            if s.p.alive and not self.cut:
                self.move_player(s.p, dt)

    def local_cameras(self, dt):
        for s in self.slots:
            self.focus(s)
            self._update_camera(dt)
            s.camera.position = self.camera.position

    def local_key(self, key):
        """Keyboard goes to the keyboard player. Returns False if the key should be ignored."""
        if self.ui_open and self.ui_slot is not None:
            self.focus(self.ui_slot)
            return True
        kb = self.kb_slot()
        if kb:
            self.focus(kb)
            if self.ui_open is None and key in (arcade.key.TAB, arcade.key.I, arcade.key.E):
                self._pending_ui_slot = kb
            return True
        return key == arcade.key.ESCAPE

    def local_after_key(self):
        s = getattr(self, "_pending_ui_slot", None)
        if s is not None and self.ui_open and self.ui_slot is None:
            self.ui_slot = s
        self._pending_ui_slot = None

    def local_mouse(self):
        if self.ui_open and self.ui_slot is not None:
            self.focus(self.ui_slot)
            return True
        kb = self.kb_slot()
        if kb:
            self.focus(kb)
            return True
        return False

    # ------------------------------------------------------------------ drawing
    def local_draw(self):
        if self.cut:   # boss intro: one big shared view
            s = self.slots[0]
            self.focus(s)
            self.camera, self.gui = self._cam_full, self._gui_full
            self._cam_full.position = s.camera.position
            ui.W, ui.H = FULL_W, FULL_H
            self.txt_prefix = "full:"
            self._split = False
            super().on_draw()
            self.camera, self.gui = s.camera, s.gui
            return
        self.clear(color=(0, 0, 0))
        for s in self.slots:
            self.focus(s)
            ui.W, ui.H = s.vw, s.vh
            self._split = True
            self._local_visibility()
            super().on_draw()
        self._split = False
        ui.W, ui.H = FULL_W, FULL_H
        # split lines
        self._gui_full.use()
        n = len(self.slots)
        if n >= 2:
            arcade.draw_line(FULL_W / 2, 0, FULL_W / 2, FULL_H, (0, 0, 0), 4)
        if n >= 3:
            arcade.draw_line(0, FULL_H / 2, FULL_W, FULL_H / 2, (0, 0, 0), 4)
        if n == 3:
            arcade.draw_lrbt_rectangle_filled(FULL_W / 2 + 2, FULL_W, 0, FULL_H / 2 - 2, (12, 14, 18))
            self.txt_prefix = "full:"
            self.txt("l3", "LAST LIGHT", FULL_W * 0.75, FULL_H / 4, (255, 214, 140, 120), 28,
                     anchor_x="center", bold=True)
        # full-screen menus for whoever opened them
        if self.ui_open or self.paused:
            owner = self.ui_slot or self.slots[0]
            self.focus(owner)
            cam, gui = self.camera, self.gui
            self.camera, self.gui = self._cam_full, self._gui_full
            self.txt_prefix = "full:"
            self._gui_full.use()
            if self.ui_open:
                self.txt("uiowner", f"{owner.p.name}'s menu  (the game is paused)", FULL_W / 2, FULL_H - 16,
                         owner.p.color, 12, anchor_x="center", bold=True)
            if self.ui_open == "inv":
                self.draw_inventory()
            elif self.ui_open == "storage":
                self.draw_storage()
            if self.paused:
                self.draw_help(True)
            self.camera, self.gui = cam, gui

    def _local_visibility(self):
        vl = self.view_layer
        view = self.view_pos()
        for p in self.players.values():
            shown = p.alive and p.layer == vl
            p.sprite.visible = shown
            if not shown:
                p.held.visible = False
            self.sync_gear(p, shown)
        for n in self.over.trees:
            if getattr(n, "kind", "tree") == "tree":
                close = any(s.p.layer == "over" and s.p.alive and
                            (s.p.pos[0] - n.center_x) ** 2 + (s.p.pos[1] - n.center_y) ** 2 < 6400 for s in self.slots)
                n.alpha = 140 if n.state == "full" and close and vl == "over" else 255
