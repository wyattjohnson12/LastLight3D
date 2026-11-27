"""
pets.py - the Pets menu (P, or D-pad up on a controller). Mixed into the game window.

Every survivor looks after their own pets (up to MAX_PETS each - in co-op, every tamer has their own).
In the menu you can see each pet's health, give it its own order (follow / work / stay), give it a name,
and put pet armor on it so zombie bites hurt less. The list scrolls if it ever gets longer than the screen, and
renaming has an on-screen keyboard so a controller-only player (e.g. split screen) can type and save a name.
Everything you click is sent as an action, so in co-op the host checks it's really your pet.
"""
import random

import arcade

import art
import art_extra
import ui
from settings import *

PET_MODES = ["follow", "work", "stay"]
PET_ARMOR = [k for k, v in ITEMS.items() if v["kind"] == "petarmor"]
NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -'")
NAME_MAX = 12


def clean_name(text):
    return "".join(ch for ch in str(text) if ch in NAME_CHARS)[:NAME_MAX].strip()


class Pets:
    pet_rename = None      # the pet being renamed (its aid) while you type
    rename_text = ""

    # ------------------------------------------------------------------ who's whose
    def my_pets(self, p=None):
        p = p or self.me
        if p is None:
            return []
        return sorted((a for a in self.over.animals if a.owner == p.id), key=lambda a: a.aid)

    @staticmethod
    def pet_name(a):
        return a.name or a.kind.capitalize()

    def random_pet_name(self, p, current=""):
        used = {a.name for a in self.over.animals if a.pet}      # nobody's pets share a name
        pool = [n for n in PET_NAMES if n not in used and n != current] or PET_NAMES
        return random.choice(pool)

    # ------------------------------------------------------------------ host side (checked)
    def pet_action(self, p, a, kw):
        if a == "petsall":
            mode = kw.get("mode")
            if mode in PET_MODES:
                for pet in self.my_pets(p):
                    pet.mode, pet.goal = mode, None
            return
        try:
            aid = int(kw.get("aid", -1))
        except (TypeError, ValueError):
            return
        pet = next((x for x in self.over.animals if x.aid == aid and x.owner == p.id), None)
        if pet is None:
            return                                  # not your pet - nothing happens
        if a == "petmode" and kw.get("mode") in PET_MODES:
            pet.mode, pet.goal = kw["mode"], None
        elif a == "petname":
            name = clean_name(kw.get("name", ""))
            if name:
                pet.name = name
        elif a == "petarmor":
            item = kw.get("item") or ""
            if item and (item not in PET_ARMOR or not self.take(p, item)):
                return
            if pet.armor:                           # the old armor goes back in your backpack
                self.give(p, pet.armor)
            pet.armor = item or None
            if item:
                self.say(f"{self.pet_name(pet)} is wearing {ITEMS[item]['name']}.", 2, to=p)

    def hurt_pet(self, a, dmg):
        """A zombie bit a pet: its armor soaks part of it."""
        if a.hp <= 0:
            return                                  # already died this frame (another zombie got it first)
        armor = ITEMS[a.armor]["armor"] if a.armor else 0
        a.hp -= dmg / (1 + armor * PET_ARMOR_SOAK)
        a.flash = 0.12
        if a.hp <= 0:
            self.hit_animal(a, 0, None)

    # ------------------------------------------------------------------ the menu
    PET_ROWS, PET_ROW_H = 8, 60       # pets shown at once (one compact row each); more than that scrolls

    def pets_layout(self):
        pw, ph = 980, 620
        return ui.W / 2 - pw / 2, ui.H / 2 - ph / 2 + 10, pw, ph

    def pet_scroll(self):
        most = max(0, len(self.my_pets()) - self.PET_ROWS)
        self._pet_scroll = max(0, min(most, getattr(self, "_pet_scroll", 0)))
        return self._pet_scroll

    def scroll_pets(self, steps):
        if self.pet_rename is None:
            self._pet_scroll = self.pet_scroll() + steps
            self.pet_scroll()

    def shown_pets(self):
        """[(row, pet), ...] for the rows you can see."""
        first = self.pet_scroll()
        return list(enumerate(self.my_pets()[first:first + self.PET_ROWS]))

    def pet_row_top(self, row):
        l, b, pw, ph = self.pets_layout()
        return b + ph - 70 - row * self.PET_ROW_H

    def pet_widgets(self):
        """Every clickable thing in the menu: [(rect, what, data, label, highlighted), ...]."""
        l, b, pw, ph = self.pets_layout()
        me = self.me
        out = []
        for i, a in self.shown_pets():
            top = self.pet_row_top(i)
            x = l + 370
            for j, mode in enumerate(PET_MODES):
                out.append(((x + j * 80, x + j * 80 + 74, top - 44, top - 14), "mode", (a.aid, mode),
                            mode.capitalize(), a.mode == mode))
            out.append(((l + 612, l + 692, top - 44, top - 14), "rename", a.aid, "Rename", self.pet_rename == a.aid))
            out.append(((l + 698, l + 778, top - 44, top - 14), "random", a.aid, "Random", False))
            ax = l + 792
            if a.armor:
                out.append(((ax, ax + 44, top - 52, top - 8), "takeoff", a.aid, a.armor, False))
            for j, item in enumerate(k for k in PET_ARMOR if me.inv.get(k)):
                bx = ax + 50 + j * 46
                out.append(((bx, bx + 42, top - 50, top - 10), "puton", (a.aid, item), item, False))
        for j, mode in enumerate(PET_MODES):
            x = l + 150 + j * 100
            out.append(((x, x + 90, b + 18, b + 48), "all", mode, mode.capitalize(), False))
        return out

    def draw_pets(self):
        me = self.me
        W, H = ui.W, ui.H
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 150))
        l, b, pw, ph = self.pets_layout()
        self.panel(l, l + pw, b, b + ph, 238)
        pets = self.my_pets()
        self.txt("pt1", f"YOUR PETS   {len(pets)}/{MAX_PETS}", l + 24, b + ph - 40, (255, 230, 170), 18, bold=True)
        close = "Y / B close" if self.use_pad else "P / ESC close"
        self.txt("pt2", close, l + pw - 24, b + ph - 38, (170, 170, 170), 11, anchor_x="right")
        mx, my = self.mouse_screen
        if not pets:
            foods = ", ".join(f"{k} ({ITEMS[v['tame']]['name'].lower()})" for k, v in ANIMALS.items() if v["tame"])
            self.txt("pt_none", "No pets yet.", l + pw / 2, b + ph / 2 + 30, (230, 230, 230), 18, anchor_x="center",
                     bold=True)
            self.txt("pt_how", f"Tame one: hold its favourite food and right-click it -  {foods}.",
                     l + pw / 2, b + ph / 2, (190, 190, 190), 12, anchor_x="center")
        for i, a in self.shown_pets():
            top = self.pet_row_top(i)
            arcade.draw_lrbt_rectangle_filled(l + 16, l + pw - 16, top - 56, top, (30, 36, 44, 230))
            arcade.draw_texture_rect(art_extra.animal(a.kind), arcade.XYWH(l + 48, top - 28, 50, 50))
            soak = ITEMS[a.armor]["armor"] if a.armor else 0
            armor = f"bites -{int(100 - 100 / (1 + soak * PET_ARMOR_SOAK))}%" if soak else "no armor"
            if self.pet_rename == a.aid:
                caret = "_" if int(self.flame_t * 2) % 2 == 0 else " "
                arcade.draw_lrbt_rectangle_filled(l + 80, l + 360, top - 30, top - 4, (60, 70, 60, 255))
                arcade.draw_lrbt_rectangle_outline(l + 80, l + 360, top - 30, top - 4, (255, 230, 150), 2)
                self.txt(f"pn{i}", self.rename_text + caret, l + 88, top - 23, (255, 255, 255), 15, bold=True)
                keys = "START = save   B = cancel   X = delete" if self.use_pad else "ENTER = save   ESC = cancel"
                self.txt(f"pk{i}", keys, l + 84, top - 46, (255, 230, 150), 10)
            else:
                self.txt(f"pn{i}", self.pet_name(a), l + 84, top - 22, (255, 255, 255), 15, bold=True)
                job = a.info["desc"].split(":")[0] if a.info.get("desc") else a.kind
                self.txt(f"pk{i}", f"{a.kind.capitalize()} - {job}  -  {armor}", l + 84, top - 38,
                         (190, 200, 210) if not soak else (170, 215, 255), 10)
                k = max(0.0, a.hp) / a.max_hp
                arcade.draw_lrbt_rectangle_filled(l + 84, l + 274, top - 51, top - 45, (40, 40, 46, 255))
                arcade.draw_lrbt_rectangle_filled(l + 84, l + 84 + 190 * k, top - 51, top - 45, (222, 70, 76, 255))
                self.txt(f"php{i}", f"{int(max(0, a.hp))}/{int(a.max_hp)}", l + 282, top - 52, (210, 200, 200), 9)
        tip = None
        renaming = self.pet_rename is not None
        for (rl, rr, rb, rt), what, data, label, on in self.pet_widgets():
            hover = rl < mx < rr and rb < my < rt and not renaming
            if what in ("takeoff", "puton"):
                arcade.draw_lrbt_rectangle_filled(rl, rr, rb, rt, (60, 66, 76, 240) if hover else (40, 46, 60, 230))
                arcade.draw_lrbt_rectangle_outline(rl, rr, rb, rt, (150, 180, 255, 120), 1)
                arcade.draw_texture_rect(art.icon(label), arcade.XYWH((rl + rr) / 2, (rb + rt) / 2, rr - rl - 8,
                                                                      rr - rl - 8))
                if what == "puton":
                    self.txt(f"pc{rl:.0f}{rb:.0f}", str(me.inv.get(label, 0)), rr - 3, rb + 3, (255, 255, 255), 9,
                             anchor_x="right", bold=True)
                if hover:
                    tip = (f"Take off {ITEMS[label]['name']} (back to your backpack)" if what == "takeoff"
                           else f"Put on {ITEMS[label]['name']}: {ITEMS[label]['desc']}")
                continue
            arcade.draw_lrbt_rectangle_filled(rl, rr, rb, rt, (255, 214, 140, 90) if on else
                                              (70, 78, 90, 230) if hover else (44, 50, 60, 230))
            arcade.draw_lrbt_rectangle_outline(rl, rr, rb, rt, (255, 214, 140) if on else (255, 255, 255, 50), 1)
            self.txt(f"pb{what}{rl:.0f}{rb:.0f}", label, (rl + rr) / 2, rb + 10, (255, 255, 255), 11,
                     anchor_x="center", bold=on)
        n, first = len(pets), self.pet_scroll()
        if n > self.PET_ROWS:                   # scrollbar + where you are in the list
            top, bot = self.pet_row_top(0), self.pet_row_top(self.PET_ROWS - 1) - 56
            th = max(24, (top - bot) * self.PET_ROWS / n)
            t0 = top - (top - bot - th) * first / (n - self.PET_ROWS)
            arcade.draw_lrbt_rectangle_filled(l + pw - 12, l + pw - 6, bot, top, (34, 40, 48, 220))
            arcade.draw_lrbt_rectangle_filled(l + pw - 12, l + pw - 6, t0 - th, t0, (255, 214, 140, 210))
            how = "right stick" if self.use_pad else "wheel / UP DOWN"
            self.txt("pt_more", f"pets {first + 1}-{first + self.PET_ROWS} of {n}  ({how})", l + pw - 140,
                     b + ph - 38, (255, 214, 140), 10, anchor_x="right")
        if pets:
            self.txt("pt_all", "ALL PETS:", l + 24, b + 28, (255, 230, 170), 13, bold=True)
        armor_have = sum(me.inv.get(k, 0) for k in PET_ARMOR)
        hint = tip or ("Pet armor: craft it at a workbench (Armor tab)." if not armor_have else
                       "Click a pet armor next to a pet to put it on.")
        self.txt("pt_tip", hint, l + 480, b + 28, (200, 200, 200), 11)
        if renaming:
            self.draw_name_keyboard()
        if self.use_pad:
            self.draw_pad_cursor()

    def click_pets(self, x, y):
        if self.pet_rename is not None:
            self.click_name_keyboard(x, y)
            return
        for (rl, rr, rb, rt), what, data, label, on in self.pet_widgets():
            if not (rl < x < rr and rb < y < rt):
                continue
            if what == "mode":
                self.action("petmode", aid=data[0], mode=data[1])
            elif what == "rename":
                pet = next((a for a in self.my_pets() if a.aid == data), None)
                self.start_rename(data, pet.name if pet else "")
            elif what == "random":
                pet = next((a for a in self.my_pets() if a.aid == data), None)
                self.action("petname", aid=data, name=self.random_pet_name(self.me, pet.name if pet else ""))
            elif what == "takeoff":
                self.action("petarmor", aid=data, item="")
            elif what == "puton":
                self.action("petarmor", aid=data[0], item=data[1])
            elif what == "all":
                self.action("petsall", mode=data)
            return

    def toggle_pets(self, open_=None):
        want = (self.ui_open != "pets") if open_ is None else open_
        self.ui_open = "pets" if want else None
        self.pet_rename = None
        self.mouse_down = False
        if want and self.use_pad:
            self.mouse_screen = (ui.W / 2, ui.H / 2)

    # ------------------------------------------------------------------ typing a name
    def start_rename(self, aid, current):
        self.pet_rename, self.rename_text = aid, current
        self.osk_upper = not current
        if self.use_pad:                         # controller: put the cursor on the on-screen keyboard
            l, r, b, t = self.name_keyboard()[10][0]      # the Q key
            self.mouse_screen = ((l + r) / 2, (b + t) / 2)

    def finish_rename(self, save):
        if save and self.pet_rename is not None:
            name = clean_name(self.rename_text)
            if name:
                self.action("petname", aid=self.pet_rename, name=name)
        self.pet_rename = None

    def rename_key(self, key):
        """Keys while renaming a pet. Returns True if the key was used up by the name box."""
        if self.pet_rename is None or self.ui_open != "pets":
            return False
        if key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.NUM_ENTER):
            self.finish_rename(True)
        elif key == arcade.key.ESCAPE:
            self.finish_rename(False)
        elif key == arcade.key.BACKSPACE:
            self.rename_text = self.rename_text[:-1]
        return True

    def rename_text_in(self, text):
        if self.pet_rename is not None and self.ui_open == "pets":
            self.rename_text = (self.rename_text + "".join(ch for ch in text if ch in NAME_CHARS))[:NAME_MAX]
            return True
        return False

    def rename_pad(self, pr):
        """Controller buttons while renaming (works in split screen with no keyboard at all):
        A types the key under the cursor, START saves, B cancels, X deletes, Y switches ABC / abc.
        Returns True if a button was used up here (so it doesn't close the menu or pause)."""
        if self.pet_rename is None or self.ui_open != "pets":
            return False
        if "start" in pr:
            self.finish_rename(True)
        elif "b" in pr or "back" in pr:
            self.finish_rename(False)
        elif "x" in pr:
            self.rename_text = self.rename_text[:-1]
        elif "y" in pr:
            self.osk_upper = not getattr(self, "osk_upper", False)
        else:
            return False
        return True

    # --- the on-screen keyboard (mouse or controller cursor)
    OSK_ROWS = ["1234567890", "QWERTYUIOP", "ASDFGHJKL'", "ZXCVBNM-"]

    def name_keyboard_box(self):
        l, b, pw, ph = self.pets_layout()
        w, h = 640, 330
        return l + pw / 2 - w / 2, b + ph / 2 - h / 2 - 10, w, h

    def name_keyboard(self):
        """[(rect, what, label), ...] - what is a character or one of: shift space del cancel save."""
        kl, kb, kw, kh = self.name_keyboard_box()
        upper = getattr(self, "osk_upper", False)
        out = []
        for r, row in enumerate(self.OSK_ROWS):
            x0 = kl + 30 + r * 12
            y = kb + kh - 96 - r * 48
            for c, ch in enumerate(row):
                ch = ch if upper else ch.lower()
                x = x0 + c * 58
                out.append(((x, x + 52, y, y + 40), ch, ch))
        y = kb + 22
        for x, w, what, label in ((kl + 30, 90, "shift", "abc" if upper else "ABC"),
                                  (kl + 126, 150, "space", "space"), (kl + 282, 90, "del", "delete"),
                                  (kl + 378, 104, "cancel", "Cancel"), (kl + 488, 122, "save", "SAVE")):
            out.append(((x, x + w, y, y + 40), what, label))
        return out

    def draw_name_keyboard(self):
        kl, kb, kw, kh = self.name_keyboard_box()
        arcade.draw_lrbt_rectangle_filled(kl, kl + kw, kb, kb + kh, (18, 22, 28, 250))
        arcade.draw_lrbt_rectangle_outline(kl, kl + kw, kb, kb + kh, (255, 230, 150), 2)
        caret = "_" if int(self.flame_t * 2) % 2 == 0 else " "
        self.txt("osk_t", f"NAME:  {self.rename_text}{caret}", kl + 30, kb + kh - 38, (255, 255, 255), 16, bold=True)
        how = ("A type   X delete   Y abc/ABC   START save   B cancel" if self.use_pad else
               "type or click   ENTER save   ESC cancel")
        self.txt("osk_h", how, kl + kw - 20, kb + kh - 36, (255, 230, 150), 10, anchor_x="right")
        mx, my = self.mouse_screen
        for (rl, rr, rb, rt), what, label in self.name_keyboard():
            hover = rl < mx < rr and rb < my < rt
            special = what == "save"
            arcade.draw_lrbt_rectangle_filled(rl, rr, rb, rt, (255, 214, 140, 150) if hover else
                                              (90, 120, 80, 230) if special else (44, 50, 60, 240))
            arcade.draw_lrbt_rectangle_outline(rl, rr, rb, rt, (255, 214, 140) if hover else (255, 255, 255, 60), 1)
            self.txt(f"osk{rl:.0f}{rb:.0f}", label, (rl + rr) / 2, rb + 13, (255, 255, 255), 13, anchor_x="center",
                     bold=True)

    def click_name_keyboard(self, x, y):
        for (rl, rr, rb, rt), what, label in self.name_keyboard():
            if not (rl < x < rr and rb < y < rt):
                continue
            if what == "save":
                self.finish_rename(True)
            elif what == "cancel":
                self.finish_rename(False)
            elif what == "del":
                self.rename_text = self.rename_text[:-1]
            elif what == "shift":
                self.osk_upper = not getattr(self, "osk_upper", False)
            else:
                ch = " " if what == "space" else what
                self.rename_text = (self.rename_text + ch)[:NAME_MAX]
                if ch.isalpha():
                    self.osk_upper = False          # like a phone: capital first letter, then lower case
            return
