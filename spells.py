"""
spells.py - magic! Learn spells at shrines deep in the caves, cast them from a Spellbook.
Mixed into the game window.

How it plays:
  * Five shrines are hidden deep underground, one for each element (see elements.py).
    Stand at one and press E (B on a controller) to learn its spell. The first one also gives you a Spellbook.
  * Hold the Spellbook: left-click (RT / A) casts the selected spell, right-click (LT) switches spell.
  * Spells cost Spell Charges (crafted from coal or cave crystal at a workbench).
  * Bosses have types: the right element does double damage, the wrong one is resisted.
    Hitting a boss with an element reveals that weakness / resistance on its health bar - for good.

Spells you learn are yours for the whole game (even if you die), and are saved per player.

ADDING A SPELL: add an entry to SPELLS. "cast" picks how it behaves (bolt, nova, chain, line, pulse);
everything else is just numbers. Then add a shrine colour in SHRINE_COLOR (or it uses the element colour).
"""
import math
import random

import arcade
from PIL import ImageDraw

import art
import elements
from settings import *
from world import LAYERS, Boss, Shot

SPELLS = {
    "fireball": {"name": "Fireball", "element": "fire", "cast": "bolt", "cost": 1, "cooldown": 0.8,
                 "damage": 14, "radius": 70, "range": 560, "speed": 650,
                 "desc": "A ball of fire that bursts where it hits and sets zombies alight."},
    "frost_nova": {"name": "Frost Nova", "element": "frost", "cast": "nova", "cost": 2, "cooldown": 2.5,
                   "damage": 10, "radius": 170, "hold": 0.8,
                   "desc": "Ice bursts out all around you: damage, slows zombies, freezes bosses for a moment."},
    "chain_lightning": {"name": "Chain Lightning", "element": "storm", "cast": "chain", "cost": 2,
                        "cooldown": 1.6, "damage": 11, "range": 420, "jumps": 3, "jump_range": 230,
                        "desc": "Lightning hits the enemy you aim at, then jumps to 3 more."},
    "stone_spikes": {"name": "Stone Spikes", "element": "earth", "cast": "line", "cost": 2, "cooldown": 2.0,
                     "damage": 13, "length": 330, "width": 46, "hold": 1.0,
                     "desc": "A line of stone spikes bursts from the ground where you aim, pinning enemies."},
    "holy_light": {"name": "Holy Light", "element": "light", "cast": "pulse", "cost": 3, "cooldown": 4.0,
                   "damage": 12, "radius": 210, "heal": 18,
                   "desc": "A wave of light: burns the undead (double damage) and heals everyone nearby."},
}
SPELL_ORDER = list(SPELLS)
SHRINE_NEAR = 95                 # how close you stand to use a shrine


# =========================================================================== art
def _shrine_img(col):
    w, h = 54, 84
    img = art._canvas(w, h)
    S = art.S
    d = ImageDraw.Draw(img)
    stone, dark = (112, 108, 118, 255), (60, 58, 66, 255)
    d.polygon([(6 * S, h * S), (12 * S, (h - 12) * S), (42 * S, (h - 12) * S), (48 * S, h * S)], fill=dark)
    d.rectangle([14 * S, 20 * S, 40 * S, (h - 12) * S], fill=stone, outline=dark, width=2 * S)
    for y in (32, 46, 60):
        d.line([16 * S, y * S, 38 * S, y * S], fill=dark, width=S)
    art._ball(img, (12, 0, 42, 30), col)                   # the glowing orb on top
    art._circle(img, 27, 15, 5, (255, 255, 255, 200))
    return art._finish(img, w, h)


def shrine_tex(element):
    return art._tex(f"shrine_{element}", lambda: _shrine_img(elements.ELEMENT_COLOR[element]))


def _spellbook_icon(img):
    art._rrect(img, (8, 6, 40, 42), 3, (96, 52, 120, 255), (50, 24, 64, 255))
    art._rrect(img, (11, 9, 37, 39), 2, (120, 70, 150, 255))
    art._circle(img, 24, 24, 8, None, (255, 220, 120, 255), 2)
    for k in range(5):
        a = -math.pi / 2 + k * math.tau * 2 / 5
        b = -math.pi / 2 + (k + 1) * math.tau * 2 / 5
        art._line(img, [(24 + math.cos(a) * 7, 24 + math.sin(a) * 7), (24 + math.cos(b) * 7, 24 + math.sin(b) * 7)],
                  (255, 220, 120, 255), 1.4)


def _charge_icon(img):
    for k, (x, y) in enumerate(((16, 30), (30, 26), (23, 16))):
        col = list(elements.ELEMENT_COLOR.values())[k]
        art._poly(img, [(x, y - 10), (x + 6, y), (x, y + 10), (x - 6, y)], col + (255,), (40, 40, 60, 255), 1.2)


art.ICON_MAKERS.update({"spellbook": _spellbook_icon, "spell_charge": _charge_icon})


# =========================================================================== the mixin
class Spells:
    # ------------------------------------------------------------------ the shrines (called from setup)
    def place_shrines(self):
        """Hide one shrine per spell deep in the cave. Own random stream, so the rest of the map is unchanged."""
        cave = self.cave
        cave.shrines = arcade.SpriteList()
        self.found_weak = {}                       # boss kind -> elements whose effect has been seen
        rng = random.Random(self.seed * 31 + 17)
        C = CAVE_CELL
        cells = {(int(s.center_x // C), int(s.center_y // C)) for s in cave.ground}
        exits = [c for _, c in self.links]
        spots = []
        for (x, y) in cells:
            if not all((x + dx, y + dy) in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                continue                           # needs open floor all round
            px, py = x * C + C / 2, y * C + C / 2
            if arcade.get_sprites_at_point((px, py), cave.solid):
                continue
            deep = min((math.dist((px, py), e) for e in exits), default=9999)
            if deep > 520:
                spots.append((deep, px, py))
        spots.sort(reverse=True)
        pool = spots[:max(10, len(spots) // 2)]    # the deeper half of the cave
        rng.shuffle(pool)
        chosen = []
        for _, px, py in pool:
            if all(math.dist((px, py), c) > 420 for c in chosen):
                chosen.append((px, py))
            if len(chosen) == len(SPELL_ORDER):
                break
        for key, (px, py) in zip(SPELL_ORDER, chosen):
            el = SPELLS[key]["element"]
            s = arcade.Sprite(shrine_tex(el), center_x=px, center_y=py, scale=1.4)
            s.spell = key
            cave.shrines.append(s)
            cave.glows.append(arcade.Sprite(art.glow(90, elements.ELEMENT_COLOR[el]), center_x=px, center_y=py))

    def near_shrine(self, p):
        if p.layer != "cave":
            return None
        for s in getattr(self.cave, "shrines", []):
            if math.dist(p.pos, s.position) < SHRINE_NEAR:
                return s
        return None

    # ------------------------------------------------------------------ what a survivor knows
    @staticmethod
    def known_spells(p):
        return [k for k in SPELL_ORDER if k in getattr(p, "spells", ())]

    def current_spell(self, p):
        known = self.known_spells(p)
        if not known:
            return None
        return known[getattr(p, "spell_sel", 0) % len(known)]

    def _send_spells(self, p):
        """Tell that player's game which spells they know (co-op clients don't run the world)."""
        self._emit(["spells", self.known_spells(p), getattr(p, "spell_sel", 0)], p)

    def learn_at_shrine(self, p, shrine):
        key = shrine.spell
        sp = SPELLS[key]
        if not hasattr(p, "spells"):
            p.spells = set()
        self.fx_layer = "cave"
        if key in p.spells:
            self.say(f"You already know {sp['name']}.", 2, to=p)
            return
        first = not p.spells
        p.spells.add(key)
        p.spell_sel = self.known_spells(p).index(key)
        self.burst(shrine.center_x, shrine.center_y, elements.ELEMENT_COLOR[sp["element"]], 30, 180, 5, 1.0,
                   layer="cave")
        self.ring(shrine.center_x, shrine.center_y, 10, 160, 0.7, elements.ELEMENT_COLOR[sp["element"]], layer="cave")
        self.play("win", 0.4, to=p)
        extra = ""
        if first and "spellbook" not in p.inv:
            self.give(p, "spellbook", 1)
            self.give(p, "spell_charge", 6)
            extra = "  Here's a Spellbook and 6 Spell Charges to start."
        self.say(f"You learned {sp['name']} ({elements.ELEMENT_NAME[sp['element']]})! {sp['desc']}{extra}", 8, to=p)
        self._send_spells(p)

    def next_spell(self, p):
        known = self.known_spells(p)
        if not known:
            self.say("You don't know any spells yet. Find the shrines deep in the caves!", 3, to=p)
            return
        p.spell_sel = (getattr(p, "spell_sel", 0) + 1) % len(known)
        sp = SPELLS[known[p.spell_sel]]
        self.say(f"Spell: {sp['name']}  ({elements.ELEMENT_NAME[sp['element']]}, {sp['cost']} charge"
                 f"{'s' if sp['cost'] > 1 else ''})", 2, to=p)
        self._send_spells(p)

    # ------------------------------------------------------------------ casting (host / solo)
    def cast(self, p):
        key = self.current_spell(p)
        if key is None:
            self.say("You don't know any spells yet. Find the shrines deep in the caves!", 3, to=p)
            p.attack_cd = 0.6
            return
        sp = SPELLS[key]
        if not self.take(p, "spell_charge", sp["cost"]):
            self.say(f"{sp['name']} needs {sp['cost']} Spell Charge{'s' if sp['cost'] > 1 else ''} - craft more at a "
                     "workbench (coal or cave crystal).", 2.5, to=p)
            self.play("error", 0.2, to=p)
            p.attack_cd = 0.6
            return
        p.attack_cd = sp["cooldown"]
        self.fx_layer = p.layer
        getattr(self, "_cast_" + sp["cast"])(p, sp)

    def _foes(self, layer):
        L = self.layers[layer]
        return list(L.zombies) + [b for b in L.bosses if getattr(b, "state", "") != "flee"]

    def _spell_hit(self, e, sp, by, dmg=None, fx=0.0, fy=0.0):
        self.hit_enemy(e, sp["damage"] if dmg is None else dmg, by, fx, fy, element=sp["element"])
        hold = sp.get("hold")
        if hold:
            if isinstance(e, Boss):
                e.snared = max(e.snared, hold)
            else:
                e.snared = max(e.snared, hold)
                if sp["element"] == "frost":
                    e.chill = 3.0

    def _cast_bolt(self, p, sp):
        fx, fy = math.cos(p.face), math.sin(p.face)
        s = Shot("fireball", p.pos[0] + fx * 28, p.pos[1] + fy * 28, fx * sp["speed"], fy * sp["speed"],
                 sp["range"] / sp["speed"], sp["damage"], p.id, p.layer)
        s.element, s.radius = sp["element"], sp["radius"]
        self.shots.append(s)
        self.play("laser", 0.2, at=p.pos, layer=p.layer)

    def fireball_burst(self, s, by):
        """A fireball hits something (called from _update_shots)."""
        for e in self._foes(s.layer):
            d = math.dist(e.position, (s.x, s.y))
            if d < s.radius + getattr(e, "radius", 18):
                self.hit_enemy(e, s.dmg if d < 30 + e.radius else s.dmg * 0.5, by, element=s.element)
                if not isinstance(e, Boss) and e.hp > 0:
                    e.burn = max(e.burn, 2.5)
        col = elements.ELEMENT_COLOR[s.element]
        self.burst(s.x, s.y, col, 22, 200, 5, 0.7, layer=s.layer)
        self.ring(s.x, s.y, 10, s.radius, 0.35, col, layer=s.layer)
        self.play("boom", 0.3, at=(s.x, s.y), layer=s.layer)

    def _cast_nova(self, p, sp):
        x, y = p.pos
        for e in self._foes(p.layer):
            if math.dist(e.position, (x, y)) < sp["radius"] + e.radius:
                self._spell_hit(e, sp, p)
        col = elements.ELEMENT_COLOR[sp["element"]]
        self.ring(x, y, 20, sp["radius"], 0.45, col, layer=p.layer)
        self.burst(x, y, col, 30, 260, 4, 0.6, layer=p.layer)
        self.play("laser", 0.35, at=p.pos, layer=p.layer)

    def _cast_chain(self, p, sp):
        fx, fy = math.cos(p.face), math.sin(p.face)
        px, py = p.pos
        foes = self._foes(p.layer)

        def ahead(e):
            dx, dy = e.center_x - px, e.center_y - py
            d = math.hypot(dx, dy) or 1
            return d < sp["range"] and (dx * fx + dy * fy) / d > 0.55

        first = min((e for e in foes if ahead(e)), key=lambda e: math.dist(e.position, (px, py)), default=None)
        col = elements.ELEMENT_COLOR[sp["element"]]
        if first is None:
            self._zap((px, py), (px + fx * 140, py + fy * 140), col, p.layer)
            self.play("laser", 0.2, at=p.pos, layer=p.layer)
            return
        hit, prev = [first], (px, py)
        while len(hit) <= sp["jumps"]:
            last = hit[-1]
            nxt = min((e for e in foes if e not in hit and math.dist(e.position, last.position) < sp["jump_range"]),
                      key=lambda e: math.dist(e.position, last.position), default=None)
            if nxt is None:
                break
            hit.append(nxt)
        for e in hit:
            self._zap(prev, e.position, col, p.layer)
            prev = e.position
            self._spell_hit(e, sp, p)
        self.play("laser", 0.4, at=p.pos, layer=p.layer)

    def _zap(self, a, b, col, layer):
        n = max(2, int(math.dist(a, b) / 40))
        for k in range(1, n + 1):
            t = k / n
            self.burst(a[0] + (b[0] - a[0]) * t + random.uniform(-8, 8), a[1] + (b[1] - a[1]) * t + random.uniform(-8, 8),
                       col, 2, 40, 4, 0.3, layer=layer)

    def _cast_line(self, p, sp):
        fx, fy = math.cos(p.face), math.sin(p.face)
        px, py = p.pos
        col = elements.ELEMENT_COLOR[sp["element"]]
        for e in self._foes(p.layer):
            dx, dy = e.center_x - px, e.center_y - py
            along = dx * fx + dy * fy
            side = abs(-dx * fy + dy * fx)
            if 0 < along < sp["length"] + e.radius and side < sp["width"] + e.radius * 0.6:
                self._spell_hit(e, sp, p, fx=fx, fy=fy)
        for k in range(1, int(sp["length"] / 40) + 1):
            x, y = px + fx * k * 40, py + fy * k * 40
            self.burst(x, y, col, 4, 90, 5, 0.6, layer=p.layer)
        self.ring(px + fx * sp["length"] / 2, py + fy * sp["length"] / 2, 10, 60, 0.4, col, layer=p.layer)
        self.shake(4, 0.2, p.layer)
        self.play("mine", 0.4, at=p.pos, layer=p.layer)

    def _cast_pulse(self, p, sp):
        x, y = p.pos
        for e in self._foes(p.layer):
            if math.dist(e.position, (x, y)) < sp["radius"] + e.radius:
                self._spell_hit(e, sp, p)
        healed = 0
        for q in self.alive_players(p.layer):
            if math.dist(q.pos, (x, y)) < sp["radius"]:
                q.health = min(STAT_MAX, q.health + sp["heal"])
                healed += 1
        col = elements.ELEMENT_COLOR[sp["element"]]
        self.ring(x, y, 20, sp["radius"], 0.6, col, layer=p.layer)
        self.burst(x, y, col, 34, 200, 5, 0.9, layer=p.layer)
        self.play("tame", 0.4, at=p.pos, layer=p.layer)

    # ------------------------------------------------------------------ boss weaknesses you've seen
    def note_element(self, enemy, element, m):
        """Called from hit_enemy for every elemental hit on a boss: popup + remember what we learned."""
        if not element or not isinstance(enemy, Boss):
            return
        text, col = elements.verdict(m)
        if text:
            self.popup(text, enemy.center_x, enemy.center_y + 60, col, layer=enemy.layer)
        seen = self.found_weak.setdefault(enemy.kind, set())
        if element not in seen and m != 1:
            seen.add(element)
            self._emit(["weak", enemy.kind, element], None)

    def boss_matchup_text(self, kind):
        """For the boss health bar: its types, and the weaknesses / resistances found so far."""
        types = elements.types_of(type("E", (), {"kind": kind, "info": elements.boss_info(kind)}))
        weak, resist = elements.matchups(kind)
        seen = getattr(self, "found_weak", {}).get(kind, set())
        name = elements.ELEMENT_NAME
        shown_weak = [name[e] for e in weak if e in seen]
        shown_res = [name[e] + ("" if resist[e] else " (immune)") for e in resist if e in seen]
        hidden = sum(1 for e in list(weak) + list(resist) if e not in seen)
        parts = []
        if types:
            parts.append("/".join(name.get(t, t.capitalize()).upper() for t in types))
        parts.append("Weak: " + (", ".join(shown_weak) if shown_weak else "?"))
        if shown_res:
            parts.append("Resists: " + ", ".join(shown_res))
        if hidden:
            parts.append(f"({hidden} still unknown - try other spells)")
        return "    ".join(parts)

    # ------------------------------------------------------------------ co-op: shots on a friend's screen
    def merge_shots(self, rows):
        """Client: the shots in a snapshot from the host. A fireball or arrow that has just vanished from the
        snapshot keeps flying for a moment, so quick ones are still seen even if two snapshots arrive together."""
        now = self.flame_t
        new = []
        for kind, x, y, vx, vy, t, T, ly in rows:
            s = Shot(kind, x, y, vx, vy, T, layer=LAYERS[ly])
            s.t = t
            new.append(s)
        for old in self.shots:
            if old.t >= old.T or any(n.kind == old.kind and math.dist((n.x, n.y), (old.x, old.y)) < 70 for n in new):
                continue
            if not hasattr(old, "gone_at"):
                old.gone_at = now + 0.1
            if now < old.gone_at:
                new.append(old)
        return new

    # ------------------------------------------------------------------ hints & events
    def spell_hint(self, p, attack_key, use_key):
        key = self.current_spell(p)
        if key is None:
            return "No spells yet - find the glowing shrines deep in the caves"
        sp = SPELLS[key]
        n = p.inv.get("spell_charge", 0)
        more = f"   {use_key}  next spell" if len(self.known_spells(p)) > 1 else ""
        return (f"{attack_key}  cast {sp['name']} ({elements.ELEMENT_NAME[sp['element']]}, {sp['cost']} of "
                f"{n} charges){more}")

    def shrine_hint(self, p, inter):
        s = self.near_shrine(p)
        if not s:
            return None
        sp = SPELLS[s.spell]
        if s.spell in getattr(p, "spells", ()):
            return f"Shrine of {elements.ELEMENT_NAME[sp['element']]}: you know {sp['name']}"
        return f"{inter}  learn {sp['name']} ({elements.ELEMENT_NAME[sp['element']]}) at the shrine"

    def spell_event(self, ev):
        """Events from the host about spells. Returns True if it was one."""
        if ev[0] == "spells" and self.me:
            self.me.spells = set(ev[1])
            self.me.spell_sel = ev[2]
            return True
        if ev[0] == "weak":
            if not hasattr(self, "found_weak"):
                self.found_weak = {}
            self.found_weak.setdefault(ev[1], set()).add(ev[2])
            return True
        return False

    # ------------------------------------------------------------------ saving (wraps savegame.py)
    def player_record(self, p):
        rec = super().player_record(p)
        rec["spells"] = self.known_spells(p)
        rec["spell_sel"] = getattr(p, "spell_sel", 0)
        return rec

    def restore_player(self, p):
        rec = (getattr(self, "away", None) or {}).get(self.rec_key(p))
        super().restore_player(p)
        if rec and self.net != "client":
            p.spells = {k for k in rec.get("spells", []) if k in SPELLS}
            p.spell_sel = int(rec.get("spell_sel", 0))
            if p.spells:
                self._send_spells(p)

    def save_data(self):
        data = super().save_data()
        data["weak_found"] = {k: sorted(v) for k, v in getattr(self, "found_weak", {}).items()}
        return data

    def load_world(self, data):
        super().load_world(data)
        self.found_weak = {k: set(v) for k, v in data.get("weak_found", {}).items()}
