"""
repair.py - fixing damaged buildings with the Repair Hammer. Mixed into the game window.

Hold the hammer and hit a damaged wall, fire, hut, bench... and it's back to full health.
The price is the building's own recipe, scaled by how much health is missing:
a Stone Wall (4 stone + 1 wood) at half health costs 2 stone + 1 wood.
Materials come from your backpack first, then from Team Storage if you're next to a bin.
"""
import math

import arcade

from settings import *

RECIPE_OF = {r["item"]: r for r in RECIPES}


class Repair:
    def damaged(self, s):
        return s.hp < s.max_hp - 0.5

    def repair_target(self, p):
        """The building in front of the survivor that the hammer would fix (damaged ones first)."""
        reach = ITEMS["repair_hammer"]["reach"] + 40
        px, py = p.pos
        fx, fy = math.cos(p.face), math.sin(p.face)
        found = []
        for s in self.structs.values():
            if s.layer != p.layer:
                continue
            dx, dy = s.center_x - px, s.center_y - py
            d = math.hypot(dx, dy)
            if d > reach or (d > 24 and (dx * fx + dy * fy) / d < 0.3):
                continue
            found.append((not self.damaged(s), d, s))
        return min(found, key=lambda t: t[:2])[2] if found else None

    def repair_cost(self, s):
        """What it costs to bring this building back to full health."""
        rec = RECIPE_OF.get(s.kind)
        missing = 1 - max(0.0, s.hp) / s.max_hp
        if not rec or missing <= 0.005:
            return {}
        return {k: max(1, math.ceil(v * missing - 1e-6)) for k, v in rec["cost"].items()}

    @staticmethod
    def cost_text(cost):
        return ", ".join(f"{v} {ITEMS[k]['name'].lower()}" for k, v in cost.items())

    def can_pay(self, p, cost):
        use_store = self.near_storage(p, 220)
        return all(self.have(p, k, use_store) >= v for k, v in cost.items())

    def repair(self, p):
        """Swing the hammer. Returns True if it was aimed at a building (so it doesn't also hit things)."""
        s = self.repair_target(p)
        if s is None:
            return False
        name = ITEMS[s.kind]["name"]
        if not self.damaged(s):
            self.say(f"That {name} is in perfect shape.", 1.5, to=p)
            return True
        cost = self.repair_cost(s)
        if not self.can_pay(p, cost):
            p.attack_cd = 0.6
            self.say(f"Repairing this {name} needs {self.cost_text(cost)}.", 2.5, to=p)
            self.play("error", 0.2, to=p)
            return True
        use_store = self.near_storage(p, 220)
        for k, v in cost.items():
            from_inv = min(v, p.inv.get(k, 0))
            if from_inv:
                self.take(p, k, from_inv)
            if v - from_inv and use_store:
                self.store_take(k, v - from_inv)
        s.hp = float(s.max_hp)
        s.flash = 0.0
        self.struct_ver += 1
        self.fx_layer = s.layer
        self.burst(s.center_x, s.center_y, (140, 230, 140), 14, 110, layer=s.layer)
        self.play("craft", 0.3, at=s.position, layer=s.layer)
        self.say(f"Repaired the {name}  (-{self.cost_text(cost)})", 2, to=p)
        return True

    def repair_hint(self, p, attack_key):
        s = self.repair_target(p)
        if s is None:
            return "Aim the hammer at a damaged building to repair it"
        name = ITEMS[s.kind]["name"]
        if not self.damaged(s):
            return f"This {name} is in perfect shape"
        cost = self.repair_cost(s)
        pct = int(100 * max(0, s.hp) / s.max_hp)
        short = "" if self.can_pay(p, cost) else "   - not enough!"
        return f"{attack_key}  repair {name} ({pct}%):  {self.cost_text(cost)}{short}"

    def draw_repair_bars(self, L):
        """Holding the hammer: health bars over damaged buildings (called in GUI space)."""
        me = self.me
        if not me or not me.alive or me.hotbar[me.selected] != "repair_hammer":
            return
        target = self.repair_target(me)
        vx, vy = self.view_pos()
        for lst in (L.builds, L.huts, L.traps):
            for s in lst:
                if not self.damaged(s) or abs(s.center_x - vx) > 900 or abs(s.center_y - vy) > 700:
                    continue
                tall = BUILD_WALL_HEIGHT + 14 if s.kind.endswith("_wall") else 20 if s.kind in TRAP_KINDS else 56
                pos = self.project(s.center_x, s.center_y, tall)
                if not pos:
                    continue
                x, y = pos
                k = max(0.0, s.hp) / s.max_hp
                col = (120, 220, 120) if k > 0.6 else (240, 200, 90) if k > 0.3 else (230, 90, 80)
                if s is target:
                    arcade.draw_lrbt_rectangle_outline(x - 29, x + 29, y - 5, y + 5, (255, 230, 150), 2)
                arcade.draw_lrbt_rectangle_filled(x - 27, x + 27, y - 3, y + 3, (30, 30, 34, 220))
                arcade.draw_lrbt_rectangle_filled(x - 27, x - 27 + 54 * k, y - 3, y + 3, col + (255,))
