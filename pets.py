"""
pets.py - the Pets menu (P, or D-pad up on a controller). Mixed into the game window.

Every survivor looks after their own pets (up to MAX_PETS each - in co-op, every tamer has their own).
In the menu you can see each pet's health, give it its own order (follow / work / stay), give it a name,
and put pet armor on it so zombie bites hurt less.
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
    def pets_layout(self):
        pw, ph = 920, 560
        return ui.W / 2 - pw / 2, ui.H / 2 - ph / 2 + 10, pw, ph

    def pet_widgets(self):
        """Every clickable thing in the menu: [(rect, what, data, label, highlighted), ...]."""
        l, b, pw, ph = self.pets_layout()
        me = self.me
        out = []
        for i, a in enumerate(self.my_pets()[:MAX_PETS]):
            top = b + ph - 84 - i * 136
            x = l + 400
            for j, mode in enumerate(PET_MODES):
                out.append(((x + j * 92, x + j * 92 + 84, top - 46, top - 16), "mode", (a.aid, mode),
                            mode.capitalize(), a.mode == mode))
            out.append(((x, x + 120, top - 92, top - 62), "rename", a.aid, "Rename", self.pet_rename == a.aid))
            out.append(((x + 128, x + 268, top - 92, top - 62), "random", a.aid, "Random name", False))
            ax = l + 700
            if a.armor:
                out.append(((ax, ax + 56, top - 92, top - 36), "takeoff", a.aid, a.armor, False))
            for j, item in enumerate(k for k in PET_ARMOR if me.inv.get(k)):
                bx = ax + 66 + j * 54
                out.append(((bx, bx + 46, top - 92, top - 46), "puton", (a.aid, item), item, False))
        for j, mode in enumerate(PET_MODES):
            x = l + 150 + j * 100
            out.append(((x, x + 90, b + 30, b + 60), "all", mode, mode.capitalize(), False))
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
            self.txt("pt_none", "No pets yet.", W / 2, b + ph / 2 + 30, (230, 230, 230), 18, anchor_x="center", bold=True)
            self.txt("pt_how", f"Tame one: hold its favourite food and right-click it -  {foods}.",
                     W / 2, b + ph / 2, (190, 190, 190), 12, anchor_x="center")
        for i, a in enumerate(pets[:MAX_PETS]):
            top = b + ph - 84 - i * 136
            arcade.draw_lrbt_rectangle_filled(l + 16, l + pw - 16, top - 112, top + 14, (30, 36, 44, 230))
            arcade.draw_texture_rect(art_extra.animal(a.kind), arcade.XYWH(l + 70, top - 46, 76, 76))
            if self.pet_rename == a.aid:
                caret = "_" if int(self.flame_t * 2) % 2 == 0 else " "
                arcade.draw_lrbt_rectangle_filled(l + 126, l + 380, top - 22, top + 8, (60, 70, 60, 255))
                arcade.draw_lrbt_rectangle_outline(l + 126, l + 380, top - 22, top + 8, (255, 230, 150), 2)
                self.txt(f"pn{i}", self.rename_text + caret, l + 134, top - 14, (255, 255, 255), 17, bold=True)
                self.txt(f"pk{i}", "ENTER = save     ESC = cancel", l + 130, top - 40,
                         (255, 230, 150), 11)
            else:
                self.txt(f"pn{i}", self.pet_name(a), l + 130, top - 14, (255, 255, 255), 18, bold=True)
                job = a.info["desc"].split(":")[0] if a.info.get("desc") else a.kind
                self.txt(f"pk{i}", f"{a.kind.capitalize()}  -  {job}", l + 130, top - 40, (190, 200, 210), 11)
            k = max(0.0, a.hp) / a.max_hp
            arcade.draw_lrbt_rectangle_filled(l + 130, l + 370, top - 74, top - 64, (40, 40, 46, 255))
            arcade.draw_lrbt_rectangle_filled(l + 130, l + 130 + 240 * k, top - 74, top - 64, (222, 70, 76, 255))
            self.txt(f"php{i}", f"Health {int(max(0, a.hp))}/{int(a.max_hp)}", l + 130, top - 96, (210, 200, 200), 11)
            soak = ITEMS[a.armor]["armor"] if a.armor else 0
            self.txt(f"par{i}", "ARMOR", l + 700, top - 20, (200, 210, 230), 11, bold=True)
            self.txt(f"pas{i}", f"bites -{int(100 - 100 / (1 + soak * PET_ARMOR_SOAK))}%" if soak else "none",
                     l + 760, top - 20, (170, 215, 255) if soak else (140, 140, 150), 11)
        tip = None
        for (rl, rr, rb, rt), what, data, label, on in self.pet_widgets():
            hover = rl < mx < rr and rb < my < rt
            if what in ("takeoff", "puton"):
                arcade.draw_lrbt_rectangle_filled(rl, rr, rb, rt, (60, 66, 76, 240) if hover else (40, 46, 60, 230))
                arcade.draw_lrbt_rectangle_outline(rl, rr, rb, rt, (150, 180, 255, 120), 1)
                arcade.draw_texture_rect(art.icon(label), arcade.XYWH((rl + rr) / 2, (rb + rt) / 2, rr - rl - 10,
                                                                      rr - rl - 10))
                if what == "puton":
                    self.txt(f"pc{rl:.0f}{rb:.0f}", str(me.inv.get(label, 0)), rr - 4, rb + 3, (255, 255, 255), 10,
                             anchor_x="right", bold=True)
                if hover:
                    tip = (f"Take off {ITEMS[label]['name']} (back to your backpack)" if what == "takeoff"
                           else f"Put on {ITEMS[label]['name']}: {ITEMS[label]['desc']}")
                continue
            arcade.draw_lrbt_rectangle_filled(rl, rr, rb, rt, (255, 214, 140, 90) if on else
                                              (70, 78, 90, 230) if hover else (44, 50, 60, 230))
            arcade.draw_lrbt_rectangle_outline(rl, rr, rb, rt, (255, 214, 140) if on else (255, 255, 255, 50), 1)
            self.txt(f"pb{what}{rl:.0f}{rb:.0f}", label, (rl + rr) / 2, rb + 9, (255, 255, 255), 12,
                     anchor_x="center", bold=on)
        if pets:
            self.txt("pt_all", "ALL PETS:", l + 24, b + 40, (255, 230, 170), 13, bold=True)
        armor_have = sum(me.inv.get(k, 0) for k in PET_ARMOR)
        hint = tip or ("Pet armor: craft it at a workbench (Armor tab)." if not armor_have else
                       "Click a pet armor next to a pet to put it on.")
        self.txt("pt_tip", hint, l + 480, b + 40, (200, 200, 200), 11)
        if self.use_pad:
            self.draw_pad_cursor()

    def click_pets(self, x, y):
        for (rl, rr, rb, rt), what, data, label, on in self.pet_widgets():
            if not (rl < x < rr and rb < y < rt):
                continue
            if what == "mode":
                self.action("petmode", aid=data[0], mode=data[1])
            elif what == "rename":
                pet = next((a for a in self.my_pets() if a.aid == data), None)
                self.pet_rename, self.rename_text = data, (pet.name if pet else "")
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
    def rename_key(self, key):
        """Keys while renaming a pet. Returns True if the key was used up by the name box."""
        if self.pet_rename is None or self.ui_open != "pets":
            return False
        if key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.NUM_ENTER):
            name = clean_name(self.rename_text)
            if name:
                self.action("petname", aid=self.pet_rename, name=name)
            self.pet_rename = None
        elif key == arcade.key.ESCAPE:
            self.pet_rename = None
        elif key == arcade.key.BACKSPACE:
            self.rename_text = self.rename_text[:-1]
        return True

    def rename_text_in(self, text):
        if self.pet_rename is not None and self.ui_open == "pets":
            self.rename_text = (self.rename_text + "".join(ch for ch in text if ch in NAME_CHARS))[:NAME_MAX]
            return True
        return False
