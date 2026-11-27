"""
savegame.py - saving and resuming games. Mixed into the game window.

Every game you start gets its own save file in the saves/ folder. The game saves itself:
  * every morning (when a new day starts),
  * when you leave to the title screen or close the window,
  * and whenever you press S (or X on a controller) on the pause screen.
Only the person running the world (solo player or co-op host) saves - joiners are saved by the host.

What's in a save: the world seed + "worldgen" version (the map is rebuilt from them - saves without
"worldgen" are the legacy map, see docs/BIOMES.md) + "spans" (which nodes each biome module made), what's been chopped/mined/built,
team storage, the time and day, the day/night lengths, zombies, bosses, pets, and every survivor.

Survivors are remembered by name. When a co-op friend joins a resumed game with the same name, they
get their own backpack, armor, stats and pets back. The host (or player 1 in split screen) always gets
the "first player" survivor, whatever their name is.
"""
import datetime
import json
import os
import time

import arcade

from settings import *
import biomes
import swamp
from world import LAYERS, Animal, Boss, Zombie

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(HERE, "saves")
SAVE_VERSION = 1
FIRST = "#first"            # record key for the host / player 1
NODE_CODE = {"full": "f", "stump": "s", "empty": "e", "gone": "g"}
CODE_NODE = {v: k for k, v in NODE_CODE.items()}
PET_MODES = ["follow", "work", "stay"]


def list_saves():
    """Every save on this computer, newest first: [(path, meta), ...]."""
    out = []
    try:
        names = os.listdir(SAVE_DIR)
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        path = os.path.join(SAVE_DIR, n)
        try:
            with open(path) as f:
                meta = json.load(f).get("meta", {})
        except (OSError, ValueError):
            continue
        out.append((path, meta))
    out.sort(key=lambda pm: pm[1].get("saved_at", 0), reverse=True)
    return out


def read_save(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if data.get("version") == SAVE_VERSION else None
    except (OSError, ValueError):
        return None


def delete_save(path):
    try:
        os.remove(path)
    except OSError:
        pass


def save_label(meta):
    when = datetime.datetime.fromtimestamp(meta.get("saved_at", 0)).strftime("%b %d, %I:%M %p").replace(" 0", " ")
    who = meta.get("names", [])
    people = who[0] if len(who) == 1 else f"{who[0]} + {len(who) - 1}" if who else "?"
    return f"Day {meta.get('day', 1)}   {meta.get('mode', 'Solo')}   {people}   ({when})"


def _items(d):
    return {k: int(v) for k, v in (d or {}).items() if k in ITEMS and int(v) > 0}


class SaveGame:
    # ------------------------------------------------------------------ who's who
    def rec_key(self, p):
        """A survivor's record key: FIRST for the host / player 1, otherwise their name - with a "#2", "#3"...
        suffix if someone already in the game has that name, so two friends both called Sam get their own
        records. Fixed the first time it's asked for, so a returning Sam reclaims the plain "sam" record."""
        if p.id == 0:
            return FIRST
        key = getattr(p, "save_key", None)
        if key is None:
            base = p.name.lower()
            taken = {getattr(q, "save_key", None) for q in self.players.values() if q is not p} | {FIRST}
            key, n = base, 1
            while key in taken:
                n += 1
                key = f"{base}#{n}"
            p.save_key = key
        return key

    def player_record(self, p):
        return {
            "name": p.name, "layer": p.layer, "x": round(p.sprite.center_x, 1), "y": round(p.sprite.center_y, 1),
            "health": p.health, "hunger": p.hunger, "thirst": p.thirst, "energy": p.energy, "warmth": p.warmth,
            "inv": p.inv, "hotbar": p.hotbar, "equip": p.equip, "selected": p.selected,
            "alive": p.alive, "respawn_t": p.respawn_t, "kills": p.kills,
            "stats": dict(getattr(p, "stats", None) or {}),     # progress.py run stats
        }

    def restore_player(self, p):
        """Called for every new survivor: if the save has one for them, give them their stuff back."""
        p.restored = False
        if self.net == "client":
            return
        key = self.rec_key(p)      # pick their (unique) record key now, while we know who's here
        rec = (getattr(self, "away", None) or {}).pop(key, None)
        if rec is None:
            return
        p.restored = True          # host_network leaves them where they were saved
        p.health, p.hunger, p.thirst, p.energy, p.warmth = (
            float(rec.get(k, STAT_MAX)) for k in ("health", "hunger", "thirst", "energy", "warmth"))
        p.inv = _items(rec.get("inv"))
        hb = [i if i in ITEMS else None for i in rec.get("hotbar", [])][:HOTBAR_SLOTS]
        p.hotbar = hb + [None] * (HOTBAR_SLOTS - len(hb))
        eq = rec.get("equip") or {}
        p.equip = {s: (eq.get(s) if eq.get(s) in ITEMS else None) for s in ARMOR_SLOTS}
        p.selected = max(0, min(HOTBAR_SLOTS - 1, int(rec.get("selected", 0))))
        p.kills = int(rec.get("kills", 0))
        p.stats = {k: int(v) for k, v in (rec.get("stats") or {}).items()}   # older saves: none
        layer = rec.get("layer", "over")
        self.set_layer(p, layer if layer in LAYERS else "over", (float(rec.get("x", 0)), float(rec.get("y", 0))))
        if not rec.get("alive", True):
            p.alive = False
            p.health = 0
            p.sprite.visible = False
            p.respawn_t = float(rec.get("respawn_t", -1))
        for a in self.over.animals:          # their pets come back to them
            if getattr(a, "owner_key", None) == key and a.owner not in self.players:
                a.owner = p.id

    def remember_player(self, p):
        """A co-op friend left: keep their survivor so the next save still has them."""
        if self.net == "client" or self.state != "playing":
            return
        if not hasattr(self, "away"):
            self.away = {}
        key = self.rec_key(p)
        self.away[key] = self.player_record(p)
        for a in self.over.animals:
            if a.owner == p.id:
                a.owner_key = key

    # ------------------------------------------------------------------ saving
    def can_save(self):
        return self.state == "playing" and self.net != "client" and bool(self.players) and not self.cut

    def save_on_exit(self):
        """Closing the window / leaving: save even mid-cutscene. A cutscene is only a camera show, so
        finish it now (the boss keeps its real state: a retreating boss's wounds are already in boss_hp)."""
        if self.cut and self.net != "client":
            self.end_cutscene()
        if self.can_save():
            self.save_game()

    def save_game(self, manual=False):
        if not self.can_save():
            if manual:
                self.say("Only the host can save a co-op game." if self.net == "client" else "Can't save right now.", 2)
            return False
        data = self.save_data()
        if not getattr(self, "save_path", None):
            os.makedirs(SAVE_DIR, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.save_path = os.path.join(SAVE_DIR, f"game-{stamp}.json")
        tmp = self.save_path + ".tmp"
        try:
            os.makedirs(SAVE_DIR, exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(data, f, separators=(",", ":"))
            os.replace(tmp, self.save_path)     # never leaves a half-written save behind
        except OSError as e:
            self.say(f"Couldn't save the game: {e}", 4)
            return False
        if manual:
            self.say(f"Game saved (Day {self.day}).", 2.5)
        return True

    def save_data(self):
        li = LAYERS.index
        first = self.players.get(0)
        names = ([first.name] if first else []) + [p.name for p in self.players.values() if p.id != 0]
        mode = "Split screen" if self.local else "Co-op" if self.net == "host" or len(self.players) > 1 else "Solo"
        records = dict(getattr(self, "away", {}))
        for p in self.players.values():
            records[self.rec_key(p)] = self.player_record(p)

        def owner_key(a):
            p = self.players.get(a.owner)
            return self.rec_key(p) if p else getattr(a, "owner_key", None)

        return {
            "version": SAVE_VERSION,
            "meta": {"saved_at": time.time(), "day": self.day, "mode": mode, "names": names,
                     "difficulty": list(self.difficulty)},
            "seed": self.seed, "worldgen": self.worldgen, "spans": dict(self.node_spans),   # biomes.py
            "clock": self.clock, "day": self.day, "kills": self.kills,
            "time_alive": self.time_alive, "cold_mult": self.cold_mult, "weather": self.weather_save(),
            "boss": [self.boss_num, self.boss_day, self.boss_hp],
            "boss_order": list(BOSS_ORDER),     # so a save outlives changes to the boss rotation
            "nodes": [[n.idx, NODE_CODE[n.state], round(n.timer, 1), n.hp] for n in self.nodes
                      if n.state != "full" or n.hp != NODES[n.kind]["hp"]],
            "regrow": [[round(t, 1), n.idx] for t, n in self.regrow],
            "base": self.base_save(),         # base.py: nodes that grew back elsewhere, cleared spots
            "biomes": self.biome_save(),      # biomes.py: each plug-in's own state (terrain.py: worn ground)
            "structs": [[s.kind, s.center_x, s.center_y, s.layer, round(s.hp, 1), int(s.lit), round(s.out_t, 1)]
                        for s in self.structs.values()],
            "storage": self.storage,
            "zombies": [[z.kind, round(z.center_x, 1), round(z.center_y, 1), z.layer, z.hp]
                        for L in self.layers.values() for z in L.zombies],
            "bosses": [[b.kind, round(b.center_x, 1), round(b.center_y, 1), b.hp, b.max_hp] for b in self.over.bosses
                       if b.state != "flee"],      # one running off at dawn is already gone
            "pets": [[a.kind, round(a.center_x, 1), round(a.center_y, 1), owner_key(a), PET_MODES.index(a.mode),
                      a.hp, a.carry, a.name, a.armor] for a in self.over.animals if a.pet and owner_key(a)],
            "players": records,
        }

    # ------------------------------------------------------------------ loading
    def load_world(self, data):
        """Put a saved world back (after setup() has rebuilt the map from the same seed)."""
        self.clock = float(data["clock"])
        self.day, self.kills = int(data["day"]), int(data["kills"])
        self.time_alive = float(data.get("time_alive", 0))
        self.cold_mult = float(data.get("cold_mult", 1.0))
        self.weather_load(data.get("weather"))     # weather.py (older saves: clear skies)
        old = [max(0, (self.day - 1) // BOSS_EVERY), self.day + (-self.day) % BOSS_EVERY, None]  # saves from before
        self.boss_num, self.boss_day, self.boss_hp = data.get("boss", old)
        self.boss_num = swamp.remap_boss_num(self.boss_num, data.get("boss_order"))   # older saves: no Mire Lurker
        default = next(d for d in DIFFICULTIES if d[0] == DEFAULT_DIFFICULTY)
        d = list(data["meta"].get("difficulty") or default)
        gap = d[3] if len(d) > 3 else BOSS_EVERY          # older saves didn't have this setting
        self.difficulty = (d[0], int(d[1]), int(d[2]), int(gap))
        remap = biomes.remap_index(data.get("spans"), self.node_spans)   # a module's node count changed
        data = dict(data)
        if data.get("spans") and data["spans"] != self.node_spans:
            base_data = dict(data.get("base") or {})
            base_data["moved"] = [[remap(r[0])] + list(r[1:]) for r in base_data.get("moved", []) if remap(r[0]) is not None]
            data["base"] = base_data
            data["nodes"] = [[remap(r[0])] + list(r[1:]) for r in data.get("nodes", []) if remap(r[0]) is not None]
            data["regrow"] = [[t, remap(i)] for t, i in data.get("regrow", []) if remap(i) is not None]
        self.base_load(data.get("base"))      # base.py (older saves: nothing moved yet)
        for idx, code, timer, hp in data.get("nodes", []):
            if 0 <= idx < len(self.nodes) and code in CODE_NODE:
                n = self.nodes[idx]
                self.set_node_state(n, CODE_NODE[code])
                n.timer, n.hp = float(timer), hp
        self.regrow = [[float(t), self.nodes[i]] for t, i in data.get("regrow", []) if 0 <= i < len(self.nodes)]
        self.fix_respawn_queue()              # base.py: old saves' stumps now grow back somewhere else
        for kind, x, y, layer, hp, lit, out_t in data.get("structs", []):
            if kind in ITEMS and layer in LAYERS:
                s = self.add_structure(kind, x, y, layer=layer)
                s.hp = float(hp)
                s.out_t = float(out_t)
                self.set_fire(s, bool(lit))
        self.storage = _items(data.get("storage"))
        self.storage_ver += 1
        for kind, x, y, layer, hp in data.get("zombies", []):
            if kind in ZOMBIES and layer in LAYERS:
                z = Zombie(kind, x, y, self.next_zid, layer)
                z.hp = hp
                self.next_zid += 1
                self.add_zombie(z)
        for kind, x, y, hp, max_hp in data.get("bosses", []):
            if kind in BOSSES:    # same cycle as spawn_boss() gave it, so it hits just as hard after loading
                b = Boss(kind, x, y, self.next_bid, int(self.boss_num) // len(BOSS_ORDER))
                b.hp, b.max_hp = hp, max_hp
                self.next_bid += 1
                self.over.bosses.append(b)
                self.bmap[b.bid] = b
        for i, row in enumerate(data.get("pets", [])):
            kind, x, y, key, mode, hp, carry = row[:7]
            name, armor = (row[7], row[8]) if len(row) > 8 else ("", None)    # older saves: no names / armor
            if kind not in ANIMALS:
                continue
            a = Animal(kind, x, y, self.next_aid)
            self.next_aid += 1
            a.owner = 100000 + i              # owner not here yet: they get it back when they join
            a.owner_key = key
            a.mode = PET_MODES[mode] if 0 <= mode < len(PET_MODES) else "stay"
            a.hp = hp
            a.carry = _items(carry)
            a.name = str(name or "")[:12]
            a.armor = armor if armor in ITEMS and ITEMS[armor]["kind"] == "petarmor" else None
            self.over.animals.append(a)
            self.amap[a.aid] = a
        self.away = dict(data.get("players", {}))
        self.biome_load(data.get("biomes"))   # biomes.py (older saves: None)
