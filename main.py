"""
LAST LIGHT - a top-down survival game (version 2 of PythonGame2025).

Gather by day, build and fight by night - alone or with up to 3 friends on the same Wi-Fi.
Craft at a workbench, smelt iron, tame animals, store loot in team storage, explore the caves,
and survive a boss every third night.

Run:                      python3 main.py
Host a co-op game:        python3 main.py --host
Join a friend's game:     python3 main.py --join 192.168.1.23     (or use the Join menu)
Pick your name:           python3 main.py --name Wyatt
Export the art as PNGs:   python3 main.py --export-art
Plug in an Xbox controller any time - see gamepad.py for the button layout.
"""
import getpass
import json
import math
import os
import random
import sys

import arcade

import swamp  # noqa: F401  (first: adds the Mire's items, recipes and boss before ui.py reads them)
import biomes  # noqa: E402  (biome registry; then every biome / terrain / layer plug-in registers itself)
biomes.load_plugins()
import base  # noqa: F401  (also early: adds the Base Flag recipe before ui.py reads the tabs)
import art
import art_bees
import art_defenses
import art_extra
import art_gear
import defenses
import firstperson
import intro
import local_coop
import net
import options
import pets
import progress
import repair
import savegame
import ui
import venom
import view3d
import weather
from gamepad import Gamepad
from settings import *
from world import LAYERS, Animal, Boss, Hazard, Node, Shot, Structure, Zombie, build_world, dist

W, H = SCREEN_WIDTH, SCREEN_HEIGHT
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "lastlight_config.json")
NODE_CODE = {"full": "f", "stump": "s", "empty": "e", "gone": "g"}
CODE_NODE = {v: k for k, v in NODE_CODE.items()}
PLAYER_COLORS = [(110, 200, 210), (240, 120, 110), (160, 220, 110), (250, 210, 100)]
PET_MODES = ["follow", "work", "stay"]
SNAPSHOT_RATE = 1 / 20
INPUT_RATE = 1 / 30


def load_sound(name):
    try:
        return arcade.load_sound(f":resources:sounds/{name}")
    except Exception:
        return None


def load_config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        with open(CONFIG, "w") as f:
            json.dump(cfg, f, indent=1)
    except OSError:
        pass


def r1(v):
    return round(v, 1)


class Survivor:
    """Everything about one player: sprite, stats, backpack, gear and what they're pressing."""

    def __init__(self, pid, name, x, y):
        self.id, self.name = pid, name
        self.color = PLAYER_COLORS[pid % 4]
        self.sprite = arcade.Sprite(art.player(pid), center_x=x, center_y=y)
        self.held = arcade.Sprite(art.icon("club"), scale=0.85)
        self.held.visible = False
        self.layer = "over"
        self.health = self.hunger = self.thirst = self.energy = self.warmth = float(STAT_MAX)
        self.inv = dict(STARTING_ITEMS)
        self.hotbar = [None] * HOTBAR_SLOTS
        self.equip = {s: None for s in ARMOR_SLOTS}
        self.selected = 0
        self.move = (0.0, 0.0)
        self.face = 0.0
        self.attacking = False
        self.resting = False
        self.attack_cd = 0.0
        self.swing = 0.0
        self.swings = 0
        self.hurt = 0.0
        self.in_hut = None
        self.alive = True
        self.respawn_t = -1.0     # seconds until respawn; -1 = waiting for dawn
        self.kills = 0
        self.tp = 0               # bumps when the host teleports this player
        self.trap_cd = 0.0        # spike traps prick you too
        self.trap_warned = -99.0
        self.conn = None
        self.events = []
        self.target = (x, y)
        self.physics = None
        for k in self.inv:
            if ITEMS[k]["kind"] not in ("material", "armor") and k not in self.hotbar:
                self.hotbar[self.hotbar.index(None)] = k

    @property
    def pos(self):
        return self.sprite.position

    def weapon(self):
        it = self.hotbar[self.selected]
        if it and ITEMS[it]["kind"] in ("weapon", "tool"):
            return it, ITEMS[it]
        return None, HANDS

    def gear(self, stat):
        return sum(ITEMS[i].get(stat, 0) for i in self.equip.values() if i)

    @property
    def holding_torch(self):
        return self.hotbar[self.selected] == "torch"


# =========================================================================== game
class LastLight(biomes.BiomeWorld, base.Base, firstperson.FirstPerson, local_coop.LocalCoop, view3d.View3D, options.Options, savegame.SaveGame, pets.Pets, repair.Repair,
                progress.Progress, weather.Weather, defenses.Defenses, swamp.Swamp, ui.UI, arcade.Window):
    def __init__(self):
        super().__init__(W, H, SCREEN_TITLE)
        self.background_color = (24, 34, 22)
        self.camera = arcade.Camera2D()
        self.gui = arcade.Camera2D()
        self.texts = {}
        self.sounds = {k: load_sound(v) for k, v in {
            "hit": "hit3.wav", "chop": "hit1.wav", "mine": "rockHit2.wav", "hurt": "hurt2.wav",
            "pickup": "coin1.wav", "craft": "upgrade1.wav", "place": "jump1.wav",
            "die": "gameover3.wav", "kill": "explosion1.wav", "error": "error2.wav", "drink": "coin3.wav",
            "roar": "explosion2.wav", "boom": "explosion1.wav", "tame": "upgrade4.wav", "travel": "phaseJump1.wav",
            "win": "upgrade5.wav", "laser": "laser1.wav",
        }.items()}
        self.cfg = load_config()
        self.my_name = (self.cfg.get("name") or getpass.getuser() or "Survivor")[:12].capitalize()
        self.difficulty = self.chosen_difficulty()     # (name, day seconds, night seconds) - options.py
        self.save_path = None      # this game's save file (savegame.py)
        self.away = {}             # saved survivors who aren't playing right now
        self.pending_save = None   # a save picked on the title screen, waiting for split-screen to start
        self.save_page = 0
        self.picked_save = None    # (path, meta) chosen in the "Load saved game" list
        self.confirm_from = ("load", 0)   # where "No, keep it" goes back to
        self.save_list = []
        self.use_title_difficulty = False
        self.pad = Gamepad()
        self.use_pad = False
        self.pad_was = None
        self.net = None           # None (solo) | "host" | "client"
        self.server = None
        self.conn = None
        self.finder = None
        self.joiner = None
        self.menu = "main"
        self.menu_sel = 0
        self.ip_text = self.cfg.get("last_ip", "")
        self.menu_note = ""
        self.state = "title"
        self.flame_t = 0.0
        self.my_pid = 0
        self.local = False         # split-screen couch co-op (local_coop.py)
        self.slots = []
        self.lobby = []
        self.ui_slot = None
        self.txt_prefix = ""
        self._split = False
        self.setup(random.randrange(1 << 30))
        self.apply_fit()

    def save_cfg(self):
        save_config(self.cfg)

    def on_close(self):
        self.save_on_exit()       # closing the window never loses your game (even mid-cutscene)
        super().on_close()

    # ------------------------------------------------------------------ setup
    def setup(self, seed, worldgen=None):
        """Build the world from its seed. worldgen: biomes.LEGACY for old saves / old hosts, None = newest."""
        self.seed = seed
        self.worldgen = int(worldgen or biomes.WORLDGEN)
        self.layout = biomes.make_layout(seed, self.worldgen, self)
        self.world_size = self.layout.size
        self.layers, self.nodes, self.links = build_world(seed, self.worldgen, self.layout)
        self.over, self.cave = self.layers["over"], self.layers["cave"]
        self.node_spans = {"base": [0, len(self.nodes)]}
        self.build_swamp()         # swamp.py: the Mire (only adds nodes at the end, so saves still line up)
        self.node_spans["mire"] = [self.node_spans["base"][1], len(self.nodes) - self.node_spans["base"][1]]
        self.portals = [("over", tuple(a), "cave", tuple(b)) for a, b in self.links]
        biomes.generate(self)      # biomes.py: every plug-in's content, in a fixed order, own random streams
        self.animal_cap = int(ANIMAL_CAP * min(2.0, biomes.area_scale(self.worldgen)))
        self.centre = (self.world_size / 2, self.world_size / 2)
        self.player_list = arcade.SpriteList()
        self.held_list = arcade.SpriteList()
        self.cloak_list = arcade.SpriteList()     # worn cloaks (drawn under the survivors)
        self.gear_list = arcade.SpriteList()      # worn armor & helmets (drawn over them)
        self.players = {}
        self.me = None
        self.next_pid = 0
        self.next_sid = self.next_zid = self.next_aid = self.next_bid = 1
        self.structs = {}
        self.zmap, self.amap, self.bmap = {}, {}, {}
        self.hazards = []
        self.shots = []            # arrows and fire pots in the air
        self.rings = []
        self.boss_num = 0          # how many bosses have been killed (picks the next one from BOSS_ORDER)
        self.boss_day = BOSS_EVERY # the night the next boss rises
        self.boss_hp = None        # a boss that got away keeps its wounds and comes back the next night
        self.storage = {}
        self.nodes_ver = self.struct_ver = self.storage_ver = 0
        self.sent_nodes_ver = self.sent_struct_ver = self.sent_storage_ver = -1
        self.events_all = []
        self.fx_layer = "over"

        self.keys = set()
        self.mouse_screen = (W / 2, H / 2)
        self.mouse_down = False
        self.ui_open = None        # None | "inv" | "storage"
        self.craft_tab = 0
        self.move_amount = 0       # index into ui.AMOUNTS for storage transfers
        self.paused = False
        self.clock = START_PHASE * DAY_CYCLE_SECONDS
        self.day = 1
        self.time_alive = 0.0
        self.kills = 0
        self.particles = []
        self.popups = []
        self.message, self.message_t = "Day 1. Gather wood and stone before dark.", 6.0
        self.regrow = []
        self.cam_pos = list(self.centre)
        self.camera.position = self.centre
        self.snap_t = 0.0
        self.input_t = 0.0
        self.last_my_health = STAT_MAX
        self.seen_swings = {}
        self.cut = None            # boss intro cutscene
        self.intro = None          # opening cutscene (intro.py)
        self.shake_t = 0.0
        self.shake_mag = 0.0
        self.cold_mult = 1.0
        self.fast_forward = False
        self.animal_t = 0.0
        self.weather_setup()       # weather.py: seasons & weather
        self.base_setup()          # base.py: base areas, cleared spots, nodes turning up elsewhere

    def add_player(self, name, conn=None, pid=None):
        if pid is None:
            pid = self.next_pid
        self.next_pid = max(self.next_pid, pid + 1)
        a = pid * math.tau / 4 + 0.6
        x = self.centre[0] + math.cos(a) * 40 * (pid > 0)
        y = self.centre[1] + math.sin(a) * 40 * (pid > 0)
        p = Survivor(pid, name, x, y)
        p.conn = conn
        self.players[pid] = p
        self.player_list.append(p.sprite)
        self.held_list.append(p.held)
        p.gear_sprites = {}
        for slot in ("cloak", "body", "head"):          # body before head so helmets sit on top
            spr = arcade.Sprite(art.player(0))
            spr.visible = False
            p.gear_sprites[slot] = spr
            (self.cloak_list if slot == "cloak" else self.gear_list).append(spr)
        p.physics = arcade.PhysicsEngineSimple(p.sprite, walls=[self.over.solid])
        self.restore_player(p)     # resuming a saved game: they get their own stuff back
        return p

    def sync_gear(self, p, shown):
        """Show what a survivor is wearing: line the armor overlays up with their sprite."""
        for slot, spr in getattr(p, "gear_sprites", {}).items():
            item = p.equip.get(slot)
            tex = art_gear.gear(item) if item else None
            spr.visible = bool(shown and tex)
            if tex is not None:
                if spr.texture is not tex:
                    spr.texture = tex
                spr.position = p.sprite.position
                spr.angle = p.sprite.angle

    def remove_player(self, p):
        self.remember_player(p)
        p.sprite.remove_from_sprite_lists()
        p.held.remove_from_sprite_lists()
        for spr in getattr(p, "gear_sprites", {}).values():
            spr.remove_from_sprite_lists()
        self.players.pop(p.id, None)
        for a in self.over.animals:
            if a.owner == p.id:
                a.mode = "stay"

    def set_layer(self, p, layer, pos):
        p.layer = layer
        p.sprite.position = pos
        p.physics = arcade.PhysicsEngineSimple(p.sprite, walls=[self.layers[layer].solid])

    @property
    def sim(self):
        return self.net != "client"

    def alive_players(self, layer=None):
        return [p for p in self.players.values() if p.alive and (layer is None or p.layer == layer)]

    def L(self, thing):
        return self.layers[thing.layer]

    # ------------------------------------------------------------------ effects (shared over the network)
    def _emit(self, ev, to):
        if self.net == "host":
            if to is None:
                self.events_all.append(ev)
            elif to.conn:
                to.events.append(ev)
        return to is None or to is self.me or (self.local and self.slot_of(to) is not None)

    def play(self, name, vol=0.35, to=None, at=None, layer=None):
        at = [r1(at[0]), r1(at[1]), layer or self.fx_layer] if at else None
        if self._emit(["snd", name, vol, at], to):
            self._play(name, vol, at)

    def _play(self, name, vol, at=None, speed=1.0):
        if at and self.me:
            if len(at) > 2 and not self.layer_seen(at[2]):
                return
            refs = [s.p.pos for s in self.slots] if self.local else [self.view_pos()]
            vol *= max(0.0, 1 - min(dist(at, r) for r in refs) / 900)
            if vol < 0.02:
                return
        s = self.sounds.get(name)
        if s:
            try:
                s.play(volume=vol, speed=speed)
            except Exception:
                pass

    def popup(self, text, x, y, color=(255, 255, 255), to=None, layer=None):
        layer = layer or self.fx_layer
        if self._emit(["pop", text, r1(x), r1(y), list(color), layer], to):
            self._popup(text, x, y, color, layer)

    def _popup(self, text, x, y, color, layer="over"):
        if not self.layer_seen(layer):
            return
        t = arcade.Text(text, x, y, tuple(color), 13, anchor_x="center", bold=True,
                        font_name=("Avenir Next", "Helvetica Neue", "Arial"))
        self.popups.append([t, 1.2, layer])

    def burst(self, x, y, color, n=8, speed=120, size=3.0, life=0.5, layer=None):
        layer = layer or self.fx_layer
        if self._emit(["fx", r1(x), r1(y), list(color), n, speed, size, life, layer], None):
            self._burst(x, y, color, n, speed, size, life, layer)

    def _burst(self, x, y, color, n, speed, size, life, layer="over"):
        if not self.layer_seen(layer):
            return
        color = tuple(color)
        for _ in range(n):
            a = random.uniform(0, math.tau)
            v = random.uniform(0.3, 1) * speed
            self.particles.append([x, y, math.cos(a) * v, math.sin(a) * v, life, life, color, size, layer])
        if len(self.particles) > 400:
            del self.particles[:len(self.particles) - 400]

    def ring(self, x, y, r0, r1_, dur, color, layer=None):
        layer = layer or self.fx_layer
        if self._emit(["ring", r1(x), r1(y), r0, r1_, dur, list(color), layer], None):
            self._ring(x, y, r0, r1_, dur, color, layer)

    def _ring(self, x, y, r0, r1_, dur, color, layer):
        if self.layer_seen(layer):
            self.rings.append([x, y, r0, r1_, 0.0, dur, tuple(color), layer])

    def shake(self, mag, dur, layer="over"):
        if self._emit(["shk", mag, dur, layer], None):
            self._shake(mag, dur, layer)

    def _shake(self, mag, dur, layer):
        if self.layer_seen(layer):
            self.shake_mag = max(self.shake_mag, mag)
            self.shake_t = max(self.shake_t, dur)
            if self.use_pad:
                self.pad.rumble(min(1, mag / 14), dur)

    def say(self, msg, t=4.0, to=None):
        if self._emit(["say", msg, t], to):
            if self.local:
                self.local_say(msg, t, to)
            else:
                self.message, self.message_t = msg, t

    def rumble(self, s=0.6, d=0.15, to=None):
        if self._emit(["rum", s, d], to):
            if self.local:
                self.local_rumble(s, d, to)
            elif self.use_pad:
                self.pad.rumble(s, d)

    def apply_event(self, ev):
        k = ev[0]
        if k == "snd":
            self._play(ev[1], ev[2], ev[3])
        elif k == "pop":
            self._popup(*ev[1:])
        elif k == "fx":
            self._burst(*ev[1:])
        elif k == "ring":
            self._ring(*ev[1:])
        elif k == "shk":
            self._shake(*ev[1:])
        elif k == "say":
            self.message, self.message_t = ev[1], ev[2]
        elif k == "rum":
            if self.use_pad:
                self.pad.rumble(ev[1], ev[2])
        elif k == "shake" and 0 <= ev[1] < len(self.nodes):
            self.nodes[ev[1]].shake = 0.18
        elif k == "cut":
            mode, hp = (ev[5], ev[6]) if len(ev) > 6 else ("intro", "")
            self.start_cutscene(ev[1], ev[2], ev[3], ev[4], local=True, mode=mode, hp=hp)
        elif k == "cutend":
            self.cut = None
        elif k == "stats":
            self.progress_event(ev)      # progress.py: my run stats, sent by the host
        else:
            self.swamp_event(ev)       # swamp.py: roots holding you in place

    # ------------------------------------------------------------------ time of day
    @property
    def phase(self):
        return (self.clock % DAY_CYCLE_SECONDS) / DAY_CYCLE_SECONDS

    @property
    def darkness(self):
        p = self.phase
        if p < DUSK_START:
            return 0.0
        if p < NIGHT_START:
            return (p - DUSK_START) / (NIGHT_START - DUSK_START)
        if p < DAWN_START:
            return 1.0
        return 1 - (p - DAWN_START) / (1 - DAWN_START)

    @property
    def is_night(self):
        return DUSK_START + 0.04 <= self.phase < DAWN_START

    @property
    def boss_night(self):
        return self.day >= self.boss_day

    def next_boss(self):
        return BOSSES[BOSS_ORDER[self.boss_num % len(BOSS_ORDER)]]

    @property
    def view_layer(self):
        me = self.me
        if not me:
            return "over"
        if me.alive:
            return me.layer
        alive = self.alive_players()
        return alive[0].layer if alive else me.layer

    def view_pos(self):
        me = self.me
        if not me:
            return self.centre
        if me.alive:
            return me.pos
        alive = self.alive_players()
        return alive[0].pos if alive else me.pos

    # ------------------------------------------------------------------ inventory & storage
    def _hotbar_add(self, p, item, force=False):
        if ITEMS[item]["kind"] in ("material", "armor", "petarmor") or item in p.hotbar:
            return
        for i, s in enumerate(p.hotbar):
            if s is None:
                p.hotbar[i] = item
                return
        if force:
            p.hotbar[p.selected] = item

    def assign_hotbar(self, p, item, slot=None):
        if item not in p.inv:
            return
        if slot is not None:
            p.selected = max(0, min(HOTBAR_SLOTS - 1, int(slot)))
        kind = ITEMS[item]["kind"]
        if kind == "armor":
            self.equip(p, item)
            return
        if kind == "material":
            self.say("Materials live in your backpack - craft something with them!", 2, to=p)
            return
        if kind == "petarmor":
            self.say("Pet armor: open the Pets menu (P / D-pad up) and click it next to a pet.", 2.5, to=p)
            return
        if item in p.hotbar:
            p.hotbar[p.hotbar.index(item)] = None
        p.hotbar[p.selected] = item
        self.say(f"{ITEMS[item]['name']} -> hotbar slot {p.selected + 1}", 1.5, to=p)

    def give(self, p, item, n=1, at=None):
        if n <= 0:
            return
        p.inv[item] = p.inv.get(item, 0) + n
        self._hotbar_add(p, item)
        if at:
            self.popup(f"+{n} {ITEMS[item]['name']}", at[0], at[1] + 24, (255, 240, 200), to=p, layer=p.layer)

    def take(self, p, item, n=1):
        have = p.inv.get(item, 0)
        if have < n:
            return False
        p.inv[item] = have - n
        if p.inv[item] <= 0:
            del p.inv[item]
            if item in p.hotbar:
                p.hotbar[p.hotbar.index(item)] = None
        return True

    def store_add(self, item, n):
        if n > 0:
            self.storage[item] = self.storage.get(item, 0) + n
            self.storage_ver += 1

    def store_take(self, item, n):
        have = self.storage.get(item, 0)
        n = min(n, have)
        if n <= 0:
            return 0
        if have - n <= 0:
            del self.storage[item]
        else:
            self.storage[item] = have - n
        self.storage_ver += 1
        return n

    def near_kind(self, pos, layer, kinds, radius):
        if isinstance(kinds, str):
            kinds = (kinds,)
        return any(s.kind in kinds and s.layer == layer and dist(s.position, pos) < radius
                   for s in self.structs.values())

    def near_storage(self, p, radius=130):
        return self.near_kind(p.pos, p.layer, "storage", radius)

    def near_fire(self, pos, layer, radius=FIRE_WARM_RADIUS):
        return any(s.kind in LIGHT_SOURCES and s.lit and s.layer == layer and dist(s.position, pos) < radius
                   for s in self.structs.values())

    def deposit(self, p, item, n):
        if not self.near_storage(p, 180) or item not in p.inv:
            return
        n = min(int(n), p.inv[item])
        if n > 0 and self.take(p, item, n):
            self.store_add(item, n)
            self.play("pickup", 0.2, to=p)

    def withdraw(self, p, item, n):
        if not self.near_storage(p, 180):
            return
        got = self.store_take(item, int(n))
        if got:
            self.give(p, item, got)
            self.play("pickup", 0.2, to=p)

    def equip(self, p, item):
        info = ITEMS.get(item, {})
        if info.get("kind") != "armor" or not self.take(p, item):
            return
        slot = info["slot"]
        old = p.equip[slot]
        p.equip[slot] = item
        if old:
            self.give(p, old)
        self.play("craft", 0.2, to=p)
        self.say(f"Wearing {info['name']}  (armor {p.gear('armor')}, warmth {p.gear('warmth')})", 2.5, to=p)

    def unequip(self, p, slot):
        item = p.equip.get(slot)
        if item:
            p.equip[slot] = None
            self.give(p, item)

    # ------------------------------------------------------------------ crafting
    def station_ok(self, p, at):
        if at is None:
            return True
        kinds = ("campfire", "brazier") if at == "campfire" else (at,)
        return self.near_kind(p.pos, p.layer, kinds, 150)

    def have(self, p, item, use_storage=None):
        if use_storage is None:
            use_storage = self.near_storage(p, 220)
        return p.inv.get(item, 0) + (self.storage.get(item, 0) if use_storage else 0)

    def can_craft(self, p, rec):
        if not self.station_ok(p, rec["at"]):
            return False
        s = self.near_storage(p, 220)
        return all(self.have(p, k, s) >= v for k, v in rec["cost"].items())

    def craft(self, p, idx):
        if not 0 <= idx < len(RECIPES):
            return
        rec = RECIPES[idx]
        if not self.can_craft(p, rec):
            self.play("error", 0.25, to=p)
            if not self.station_ok(p, rec["at"]):
                self.say(f"Stand next to a {STATIONS.get(rec['at'], rec['at'])} to make that.", 2, to=p)
            else:
                self.say("Not enough materials.", 2, to=p)
            return
        use_store = self.near_storage(p, 220)
        for k, v in rec["cost"].items():
            from_inv = min(v, p.inv.get(k, 0))
            if from_inv:
                self.take(p, k, from_inv)
            if v - from_inv and use_store:
                self.store_take(k, v - from_inv)
        self.give(p, rec["item"], rec["n"])
        self.stat(p, "crafted")
        self._hotbar_add(p, rec["item"], force=True)
        self.play("craft", 0.3, to=p)
        extra = "  (click it in the backpack to wear it)" if ITEMS[rec["item"]]["kind"] == "armor" else ""
        self.say(f"Crafted {ITEMS[rec['item']]['name']}!{extra}", 2.5, to=p)

    # ------------------------------------------------------------------ eating & interacting
    def consume(self, p, item):
        info = ITEMS[item]
        if info["kind"] != "food" or not self.take(p, item):
            return
        p.hunger = min(STAT_MAX, p.hunger + info.get("hunger", 0))
        p.thirst = min(STAT_MAX, p.thirst + info.get("thirst", 0))
        p.health = max(1, min(STAT_MAX, p.health + info.get("health", 0)))
        p.energy = min(STAT_MAX, p.energy + info.get("energy", 0))
        if info.get("energy"):
            self.burst(p.sprite.center_x, p.sprite.center_y, (250, 200, 60), 12, 110, layer=p.layer)
        self.play("drink" if item == "water" else "pickup", 0.25, to=p)
        self.popup(info["name"], p.sprite.center_x, p.sprite.center_y + 30, (190, 255, 190), layer=p.layer)
        if item == "meat":
            self.say("Raw meat... you should cook that at a campfire.", 2, to=p)

    def quick_use(self, p):
        needs = []
        if p.thirst < 80 and "water" in p.inv:
            needs.append((p.thirst, "water"))
        if p.hunger < 85:
            for f in ("cooked_meat", "stew", "berries"):
                if f in p.inv:
                    needs.append((p.hunger, f))
                    break
        if p.health < 60:
            for f in ("bandage", "medkit"):
                if f in p.inv:
                    needs.append((p.health - 10, f))
                    break
        if p.energy < 40 and "honey" in p.inv:
            needs.append((p.energy, "honey"))
        if needs:
            self.consume(p, min(needs)[1])
        else:
            self.say("Nothing useful to eat or drink right now.", 1.5, to=p)

    def near_pond(self, p):
        return p.layer == "over" and any(dist(p.pos, s.position) < 150 for s in self.over.ponds)

    def near_exit(self, p):
        for s in self.layers[p.layer].exits:
            if dist(p.pos, s.position) < 70:
                return s
        return None

    def drink(self, p):
        if not p.alive or not self.near_pond(p):
            return False
        p.thirst = min(STAT_MAX, p.thirst + 35)
        if p.inv.get("water", 0) < 6:
            self.give(p, "water", 1, p.pos)
        self.play("drink", 0.3, to=p)
        self.burst(p.sprite.center_x, p.sprite.center_y, (120, 190, 240), 8, 80, layer=p.layer)
        return True

    def travel(self, p):
        ex = self.near_exit(p)
        if not ex:
            return
        far = self.portal_from(p.layer, ex.position)     # biomes.py: over <-> cave, cave <-> deep, ...
        if far is not None:
            layer, (x, y) = far
            down = biomes.depth(layer) > biomes.depth(p.layer)
            msg = biomes.LAYER_INFO[layer].enter if down else biomes.LAYER_INFO[p.layer].leave
            self.set_layer(p, layer, (x + (60 if layer == "over" else 45), y))
            if msg:
                self.say(msg, 5 if down else 2, to=p)
        p.tp += 1
        self.play("travel", 0.3, to=p)

    def interact(self, p):
        """E / B: use a cave entrance or drink - whichever is at hand (storage opens on your own screen)."""
        if self.near_exit(p):
            self.travel(p)
        elif self.near_pond(p):
            self.drink(p)

    def command_pets(self, p):
        pets = [a for a in self.over.animals if a.owner == p.id]
        if not pets:
            self.say("You have no pets. Tame one: hold its favourite food and use it next to the animal.", 3, to=p)
            return
        mode = PET_MODES[(PET_MODES.index(pets[0].mode) + 1) % len(PET_MODES)]
        for a in pets:
            a.mode = mode
            a.goal = None
        text = {"follow": "FOLLOW - your pets stay with you (wolves fight for you).",
                "work": "WORK - foragers and haulers gather and bring it to your Storage Bins. Wolves guard the base.",
                "stay": "STAY - your pets wait right here."}[mode]
        self.say(f"Pets: {text}", 4, to=p)

    def tame(self, p, aid):
        a = next((x for x in self.over.animals if x.aid == aid), None)
        if not a or a.pet or p.layer != "over" or dist(a.position, p.pos) > 110:
            return
        food = a.info["tame"]
        if not food:
            self.say(f"A {a.kind} can't be tamed - but it makes a good meal.", 2, to=p)
            return
        if not self.take(p, food):
            self.say(f"A {a.kind} can be tamed with {ITEMS[food]['name']}.", 2, to=p)
            return
        if sum(1 for x in self.over.animals if x.owner == p.id) >= MAX_PETS:
            self.give(p, food)
            self.say(f"You can only look after {MAX_PETS} pets.", 2, to=p)
            return
        self.fx_layer = "over"
        if random.random() < a.info["chance"]:
            a.owner, a.mode, a.hp, a.aggro = p.id, "follow", a.max_hp, None
            a.name = self.random_pet_name(p)
            self.on_tamed(p)
            self.burst(a.center_x, a.center_y, (255, 120, 160), 14, 90, 3, 0.9)
            self.play("tame", 0.35, to=p)
            self.say(f"You tamed a {a.kind} - meet {a.name}!  {a.info['desc']}  "
                     "P (or D-pad up): Pets menu to rename it, give orders and armor.", 7, to=p)
        else:
            self.burst(a.center_x, a.center_y, (200, 200, 200), 6, 60)
            self.say(f"The {a.kind} snatched the food but isn't sure about you yet... try again.", 2.5, to=p)

    # ------------------------------------------------------------------ building
    def placement(self, p, target):
        item = p.hotbar[p.selected]
        if not item or ITEMS[item]["kind"] != "build" or not p.alive:
            return None
        L = self.layers[p.layer]
        mx, my = target
        g = GRID
        x, y = math.floor(mx / g + 0.5) * g, math.floor(my / g + 0.5) * g
        if item == "hut":
            x, y = x + g / 2, y + g / 2
        ghost = arcade.Sprite(art.icon(item), center_x=x, center_y=y)
        ok = dist((x, y), p.pos) < 190 and 40 < x < L.size - 40 and 40 < y < L.size - 40
        if ok:
            ok = not arcade.check_for_collision_with_lists(ghost, [L.solid, L.huts, L.zombies, L.traps, L.exits]
                                                            + self.defense_blockers(L))
            if ok and item != "hut" and item not in TRAP_KINDS:
                ok = not arcade.check_for_collision_with_list(ghost, self.player_list)
        return item, ghost, ok

    def place(self, p, target):
        pl = self.placement(p, target)
        if not pl:
            return False
        item, ghost, ok = pl
        if not ok:
            self.play("error", 0.2, to=p)
            self.say("Can't build there.", 1.2, to=p)
            return True
        self.take(p, item)
        s = self.add_structure(item, ghost.center_x, ghost.center_y, layer=p.layer)
        self.on_built(p, item)
        self.burst(s.center_x, s.center_y, (200, 170, 120), 10, 90, layer=p.layer)
        self.play("place", 0.25, at=s.position, layer=p.layer)
        if item == "storage":
            self.say("Storage Bin built! Press E (or B) next to it to open TEAM STORAGE.", 4, to=p)
        elif item == "workbench":
            self.say("Workbench built! Stand near it and open the backpack for advanced crafting.", 4, to=p)
        return True

    def add_structure(self, kind, x, y, sid=None, layer="over"):
        if sid is None:
            sid = self.next_sid
            self.next_sid += 1
        L = self.layers[layer]
        s = Structure(kind, x, y, sid, layer)
        self.structs[sid] = s
        if kind == "hut":
            L.huts.append(s)
        elif kind in TRAP_KINDS:
            L.traps.append(s)
        else:
            L.builds.append(s)
            if kind not in defenses.WALK_THROUGH:   # gates: survivors walk through, zombies don't
                L.solid.append(s)
        self.add_defense(s, L)          # defenses.py: gates, lanterns, turrets
        if kind in LIGHT_SOURCES:
            f = arcade.Sprite(art.flame(0), center_x=s.center_x, center_y=s.center_y + 6,
                              scale=1.0 if kind == "campfire" else 0.8)
            g = arcade.Sprite(art.glow(170 if kind == "campfire" else 210), center_x=s.center_x, center_y=s.center_y)
            L.flames.append(f)
            L.glows.append(g)
            s.extras = [f, g]
        self.struct_ver += 1
        return s

    def remove_structure(self, s):
        for e in s.extras:
            e.remove_from_sprite_lists()
        for p in self.players.values():
            if p.in_hut is s:
                p.in_hut = None
        self.structs.pop(s.sid, None)
        s.remove_from_sprite_lists()
        self.struct_ver += 1

    def damage_structure(self, s, amount):
        if s.sid not in self.structs:
            return
        s.hp -= amount
        s.flash = 0.15
        self.struct_ver += 1
        self.burst(s.center_x, s.center_y, (170, 130, 90), 4, 80, layer=s.layer)
        if s.hp <= 0:
            self.burst(s.center_x, s.center_y, (130, 100, 70), 20, 160, 4, layer=s.layer)
            self.say(f"A {ITEMS[s.kind]['name']} was destroyed!", 2.5)
            self.remove_structure(s)

    def set_fire(self, s, lit):
        """Fires: lit or put out. Bear traps use the same switch for armed / sprung."""
        if s.lit != lit:
            s.lit = lit
            if s.kind == "bear_trap":
                s.color = (255, 255, 255) if lit else (120, 120, 120)
            for e in s.extras:
                e.visible = lit
            self.struct_ver += 1

    def set_node_state(self, n, state):
        if n.state == state:
            return
        n.state = state
        L = self.layers[n.layer]
        if n.kind == "tree":
            n.texture = art.tree(n.variant) if state == "full" else art.stump()
            n.angle = n.base_angle if state == "full" else 0
            if state != "full" and L.solid in n.sprite_lists:      # a stump: walk over it, build on it
                L.solid.remove(n)
            elif state == "full" and L.solid not in n.sprite_lists:
                L.solid.append(n)
        elif n.kind == "bush":
            n.texture = art.bush(state == "full")
        elif n.kind == "hive":   # never solid; hidden while its tree is a stump
            n.texture = art_bees.hive(state == "full")
            n.visible = state != "gone"
        else:   # rock & ores vanish when mined out
            n.visible = state != "gone"
            if state == "gone" and L.solid in n.sprite_lists:
                L.solid.remove(n)
            elif state != "gone" and L.solid not in n.sprite_lists:
                L.solid.append(n)
        self.nodes_ver += 1

    # ------------------------------------------------------------------ combat & gathering
    def harvest(self, n, mult):
        """Take one 'hit' worth of resources out of a node. Returns {item: count}."""
        n.shake = 0.18
        self._emit(["shake", n.idx], None)
        got = {}
        if n.kind == "bush":
            got = {"berries": 3, "fiber": 2}
            self.set_node_state(n, "empty")
            n.timer = NODES["bush"]["regrow"]
            self.burst(n.center_x, n.center_y, (80, 150, 60), 8, 100, layer=n.layer)
            self.play("pickup", 0.2, at=n.position, layer=n.layer)
            return got
        if n.kind == "hive":
            got = {"honey": HIVE_HONEY}
            self.set_node_state(n, "empty")
            n.timer = HIVE_REGROW
            self.burst(n.center_x, n.center_y, (236, 170, 40), 10, 100, layer=n.layer)
            self.play("pickup", 0.25, at=n.position, layer=n.layer)
            return got
        give = NODES[n.kind]["gives"]
        got[give] = mult
        n.hp -= mult
        col = {"tree": (150, 104, 60), "iron": (196, 120, 70), "coal": (40, 40, 40),
               "crystal": (150, 220, 255)}.get(n.kind, (150, 150, 150))
        self.burst(n.center_x, n.center_y, col, 7, 120, layer=n.layer)
        self.play("chop" if n.kind == "tree" else "mine", 0.3, at=n.position, layer=n.layer)
        if n.hp <= 0:
            if n.kind == "tree":
                got[give] += 2
                self.set_node_state(n, "stump")
                n.timer = TREE_REGROW
                self.node_used_up(n)     # base.py: it grows back somewhere else, never here
                if n.hive:   # the hive falls with the tree
                    if n.hive.state == "full":
                        got["honey"] = HIVE_HONEY
                    self.set_node_state(n.hive, "gone")
                self.burst(n.center_x, n.center_y, (70, 120, 50), 24, 200, 4, 0.8, layer=n.layer)
            else:
                if n.kind in ("iron", "coal"):
                    got["stone"] = 1
                self.set_node_state(n, "gone")
                self.node_used_up(n)     # base.py: it turns up again somewhere else, never here
        return got

    def attack(self, p):
        item, w = p.weapon()
        p.attack_cd = w["cooldown"]
        p.swing = 0.2
        p.swings += 1
        p.energy = max(0, p.energy - SWING_ENERGY_COST)
        L = self.layers[p.layer]
        self.fx_layer = p.layer
        px, py = p.pos
        fx, fy = math.cos(p.face), math.sin(p.face)
        if w.get("ranged"):
            self.shoot(p, w)
            return
        if w.get("repair") and self.repair(p):     # repair.py: hammer aimed at a building
            return
        allround = bool(w.get("quake"))

        def in_front(pos, reach, cone=0.45):
            dx, dy = pos[0] - px, pos[1] - py
            d = math.hypot(dx, dy)
            if d > reach or d < 1:
                return d < 1
            return allround or (dx * fx + dy * fy) / d > cone

        foes = [z for z in L.zombies if in_front(z.position, w["reach"] + z.radius)]
        foes += [b for b in L.bosses if in_front(b.position, w["reach"] + b.radius)]
        foes.sort(key=lambda z: dist(z.position, (px, py)))
        if foes:
            for z in foes[:6 if allround else 2]:
                self.hit_enemy(z, w["damage"], p, fx, fy, w)
            if allround:
                self.ring(px, py, 20, w["reach"] + 30, 0.35, (255, 170, 60))
                self.shake(5, 0.2, p.layer)
            self.play("hit", 0.35, at=p.pos)
            self.rumble(0.35, 0.08, to=p)
            return
        beasts = [a for a in L.animals if not a.pet and in_front(a.position, w["reach"] + 18)]
        if beasts:
            a = min(beasts, key=lambda a: dist(a.position, (px, py)))
            self.hit_animal(a, w["damage"], p, fx, fy)
            self.play("hit", 0.3, at=p.pos)
            return

        nodes = [n for lst in L.node_lists() for n in lst
                 if n.state == "full" and in_front(n.position, w["reach"] + 34, 0.2)]
        if not nodes:
            return
        n = min(nodes, key=lambda n: dist(n.position, (px, py)))
        need = NODES[n.kind].get("needs")
        if need == "pickaxe" and item not in ("pickaxe", "iron_pickaxe"):
            self.say("You need a pickaxe to mine that.", 1.5, to=p)
            self.play("mine", 0.15, to=p)
            return
        if need == "iron_pickaxe" and item != "iron_pickaxe":
            self.say("Crystal is too hard - you need an IRON pickaxe.", 1.8, to=p)
            self.play("mine", 0.15, to=p)
            return
        mult = w.get("harvest", {}).get(n.kind, 1) if item else 1
        got = self.harvest(n, mult)
        self.stat(p, "gathered", sum(got.values()))
        for k, v in got.items():
            self.give(p, k, v, n.position if k == NODES[n.kind]["gives"] else None)
        if "honey" in got:
            self.anger_bees(n.position, p)

    # ------------------------------------------------------------------ arrows & fire pots
    def shoot(self, p, w):
        if not self.take(p, "arrows"):
            p.attack_cd = 0.6
            self.say("Out of arrows! Craft more in the Supplies tab (wood, stone, fiber).", 2, to=p)
            self.play("error", 0.2, to=p)
            return
        fx, fy = math.cos(p.face), math.sin(p.face)
        x, y = p.pos[0] + fx * 26, p.pos[1] + fy * 26
        self.shots.append(Shot("arrow", x, y, fx * ARROW_SPEED, fy * ARROW_SPEED, w["reach"] / ARROW_SPEED,
                               w["damage"], p.id, p.layer))
        self.play("laser", 0.12, at=p.pos, layer=p.layer)

    def throw(self, p, item, tx, ty):
        px, py = p.pos
        dx, dy = tx - px, ty - py
        d = math.hypot(dx, dy)
        if d > FIRE_POT_RANGE:
            dx, dy = dx / d * FIRE_POT_RANGE, dy / d * FIRE_POT_RANGE
        if not self.take(p, item):
            return
        T = FIRE_POT_FLIGHT
        self.shots.append(Shot("pot", px, py, dx / T, dy / T, T, ITEMS[item]["damage"], p.id, p.layer))
        p.swing = 0.2
        p.swings += 1
        self.play("place", 0.25, at=p.pos, layer=p.layer)

    def _update_shots(self, dt):
        for s in self.shots:
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.t += dt
            L = self.layers[s.layer]
            by = self.players.get(s.owner)
            self.fx_layer = s.layer
            if s.kind == "arrow":
                if s.layer != "over" and arcade.get_sprites_at_point((s.x, s.y), L.walls):
                    s.done = True
                    continue
                sp = math.hypot(s.vx, s.vy) or 1
                hit = next((e for e in list(L.zombies) + list(L.bosses)
                            if dist((s.x, s.y), e.position) < e.radius + 8), None)
                if hit is not None:
                    self.hit_enemy(hit, s.dmg, by, s.vx / sp, s.vy / sp)
                    s.done = True
                    continue
                beast = next((a for a in L.animals if not a.pet and dist((s.x, s.y), a.position) < 22), None)
                if beast is not None:
                    self.hit_animal(beast, s.dmg, by, s.vx / sp, s.vy / sp)
                    s.done = True
                elif s.t >= s.T:
                    s.done = True
            elif s.t >= s.T:
                s.done = True
                self._pot_burst(s, by)
        self.shots = [s for s in self.shots if not s.done]

    def _pot_burst(self, s, by):
        """A fire pot lands: flames hurt every enemy close by (never players)."""
        L = self.layers[s.layer]
        r = FIRE_POT_RADIUS
        for z in list(L.zombies):
            if dist(z.position, (s.x, s.y)) < r + z.radius * 0.5:
                z.burn = max(z.burn, 3.0)
                self.hit_enemy(z, s.dmg, by)
        for b in list(L.bosses):
            if dist(b.position, (s.x, s.y)) < r + b.radius:
                self.hit_enemy(b, s.dmg, by)
        for a in list(L.animals):
            if not a.pet and dist(a.position, (s.x, s.y)) < r:
                self.hit_animal(a, s.dmg, by)
        self.burst(s.x, s.y, (255, 140, 40), 30, 220, 5, 0.8, layer=s.layer)
        self.ring(s.x, s.y, 10, r, 0.4, (255, 160, 60), layer=s.layer)
        self.play("boom", 0.35, at=(s.x, s.y), layer=s.layer)
        self.shake(5, 0.25, s.layer)

    def anger_bees(self, pos, p):
        """Raiding a hive makes the wild bees around it come after you (tame bees don't mind)."""
        angry = [a for a in self.over.animals
                 if a.kind == "bee" and not a.pet and dist(a.position, pos) < HIVE_ALERT_RADIUS]
        for a in angry:
            a.aggro, a.aggro_t = p.id, 8.0
        if angry:
            self.say("BZZZ! The bees are angry - run, or swat them!", 2.5, to=p)

    def hit_enemy(self, z, dmg, by=None, fx=0.0, fy=0.0, w=None):
        z.hp -= dmg
        if isinstance(z, Boss) and z.state == "flee" and z.hp > 0:
            self.boss_hp = z.hp            # running off at dawn: it still takes the wound home with it
        z.flash = 0.12
        L = self.L(z)
        if isinstance(z, Zombie):
            kb = 22 if z.kind not in ("brute", "golem") else 8
            z.center_x += fx * kb
            z.center_y += fy * kb
            z.angle = 0
            if arcade.check_for_collision_with_lists(z, [L.solid, L.huts]):
                z.center_x -= fx * kb
                z.center_y -= fy * kb
            if w and w.get("burn"):
                z.burn = 3.0
            if w and w.get("slow"):
                z.chill = 3.0
        venom.apply(z, w, by)              # venom.py: Brood Fang poison (bosses too)
        self.burst(z.center_x, z.center_y, (110, 30, 30), 7, 140, layer=z.layer)
        if z.hp <= 0:
            if isinstance(z, Boss):
                self.kill_boss(z, by)
            else:
                self.kill_zombie(z, by)

    def hit_animal(self, a, dmg, by, fx=0.0, fy=0.0):
        a.hp -= dmg
        a.flash = 0.12
        a.center_x += fx * 14
        a.center_y += fy * 14
        a.angle = 0
        if arcade.check_for_collision_with_list(a, self.over.solid):
            a.center_x -= fx * 14
            a.center_y -= fy * 14
        self.burst(a.center_x, a.center_y, (150, 40, 40), 6, 110, layer="over")
        if a.info["temper"] == "defend" and by:
            a.aggro, a.aggro_t = by.id, 10.0
        else:
            a.aggro, a.aggro_t = (by.id if by else None), 4.0   # run away from them
        if a.hp <= 0:
            self.burst(a.center_x, a.center_y, (130, 40, 40), 14, 150, 4, 0.7, layer="over")
            if by:
                for k, v in a.info["drops"].items():
                    self.give(by, k, v, a.position)
            if a.pet:
                owner = self.players.get(a.owner)
                lost = f" Its {ITEMS[a.armor]['name']} was lost." if a.armor else ""
                self.say(f"{self.pet_name(a)} the {a.kind} died...{lost}", 4, to=owner)
            self.amap.pop(a.aid, None)
            a.remove_from_sprite_lists()

    def kill_zombie(self, z, by=None):
        self.kills += 1
        alive = self.alive_players(z.layer)
        if by is None and alive:
            by = min(alive, key=lambda p: dist(p.pos, z.position))
        self.burst(z.center_x, z.center_y, (90, 30, 30), 18, 180, 4, 0.7, layer=z.layer)
        self.play("kill", 0.15, at=z.position, layer=z.layer)
        if by:
            by.kills += 1
            self.stat(by, "zombies")
            roll = random.random()
            if z.kind == "golem":
                self.give(by, "crystal", 1, z.position)
                self.give(by, "iron_ore", 2)
            elif z.kind == "crawler":
                if roll < 0.5:
                    self.give(by, "coal", 1, z.position)
            elif z.kind == "brute":
                self.give(by, "stone", 3, z.position)
            elif z.kind == "drowned":
                self.give(by, "reeds" if roll < 0.55 else "glowcap", 1, z.position)
            elif roll < 0.30:
                self.give(by, "fiber", 1, z.position)
            elif roll < 0.42:
                self.give(by, "berries", 1, z.position)
        if z.eye:
            z.eye.remove_from_sprite_lists()
        z.remove_from_sprite_lists()

    def spawn_zombie(self, layer="over", kind=None, at=None):
        L = self.layers[layer]
        alive = self.alive_players(layer)
        if not alive and at is None:
            return None
        if kind is None:
            roll = random.random()
            if layer != "over":
                kind = self.layer_zombie_kind(layer, roll)    # biomes.LAYER_INFO[layer].zombie
            else:
                kind = "walker"
                if self.day >= 3 and roll < 0.08 + 0.03 * self.day:
                    kind = "brute"
                elif self.day >= 2 and roll < 0.40:
                    kind = "runner"
        for _ in range(16):
            if at is not None:
                x, y = at[0] + random.uniform(-60, 60), at[1] + random.uniform(-60, 60)
            else:
                anchor = random.choice(alive)
                a = random.uniform(0, math.tau)
                d = random.uniform(600, 800) if layer == "over" else random.uniform(420, 620)
                x = anchor.sprite.center_x + math.cos(a) * d
                y = anchor.sprite.center_y + math.sin(a) * d
                if any(dist((x, y), p.pos) < (520 if layer == "over" else 380) for p in alive):
                    continue
            if not (60 < x < L.size - 60 and 60 < y < L.size - 60):
                continue
            z = Zombie(self.biome_zombie_kind(kind, x, y, layer), x, y, self.next_zid, layer)   # biomes.py
            if arcade.check_for_collision_with_lists(z, [L.solid, L.huts]):
                continue
            if layer != "over" and not arcade.get_sprites_at_point((x, y), L.ground):
                continue
            self.next_zid += 1
            self.add_zombie(z)
            return z
        return None

    def add_zombie(self, z):
        L = self.L(z)
        L.zombies.append(z)
        col = (120, 255, 160) if z.kind == "crawler" else (140, 220, 255) if z.kind == "golem" else (255, 60, 40)
        e = arcade.Sprite(art.glow(14, col), center_x=z.center_x, center_y=z.center_y)
        L.eyes.append(e)
        z.eye = e

    def hurt_player(self, p, dmg):
        """Armor soaks up part of every hit."""
        if not p.alive or getattr(p, "arriving", False):   # still watching their opening cutscene
            return
        armor = p.gear("armor")
        p.health -= dmg / (1 + armor * 0.09)
        p.hurt = 0.35
        self.play("hurt", 0.3, at=p.pos, layer=p.layer)
        self.rumble(0.8, 0.2, to=p)
        self.burst(p.sprite.center_x, p.sprite.center_y, (200, 40, 40), 6, 120, layer=p.layer)

    # ------------------------------------------------------------------ bosses
    def spawn_boss(self):
        n = self.boss_num
        kind = BOSS_ORDER[n % len(BOSS_ORDER)]
        cycle = n // len(BOSS_ORDER)
        alive = self.alive_players("over")
        anchor = random.choice(alive).pos if alive else self.base_spot()
        b = None
        for i in range(30):
            a = random.uniform(0, math.tau)
            x, y = anchor[0] + math.cos(a) * 560, anchor[1] + math.sin(a) * 560
            if not (150 < x < self.world_size - 150 and 150 < y < self.world_size - 150):
                continue
            b = Boss(kind, x, y, self.next_bid, cycle)
            if arcade.check_for_collision_with_lists(b, [self.over.solid, self.over.huts]) and i < 25:
                continue
            break
        if b is None:
            b = Boss(kind, self.centre[0] + 500, self.centre[1], self.next_bid, cycle)
        self.next_bid += 1
        self.over.bosses.append(b)
        self.bmap[b.bid] = b
        if self.boss_hp is not None:      # it got away last night - same boss, same wounds, no intro
            b.hp = min(b.max_hp, self.boss_hp)
            self.play("roar", 0.4)
            self.shake(8, 0.6)
            hurt = f"still wounded ({int(b.hp)}/{int(b.max_hp)})" if b.hp < b.max_hp else "back for another try"
            self.say(f"{b.info['name']} RETURNS - {hurt}. Finish it!", 6)
        else:
            self.start_cutscene(kind, b.center_x, b.center_y, self.day)
        return b

    def start_retreat(self, b):
        """Dawn: the boss turns and runs, fading into the trees, while a short cutscene says it'll be back."""
        alive = self.alive_players("over")
        if alive:
            p = min(alive, key=lambda q: dist(q.pos, b.position))
            a = math.atan2(b.center_y - p.pos[1], b.center_x - p.pos[0])
        else:
            a = random.uniform(0, math.tau)
        b.state, b.state_t, b.snared = "flee", 0.0, 0.0
        b.charge_dir = (math.cos(a), math.sin(a))
        self.play("roar", 0.35, at=b.position, layer="over")
        if b.hp < b.max_hp:
            line = f"It keeps its wounds:  {int(b.hp)}/{int(b.max_hp)} health.  Be ready."
        else:
            line = "It didn't take a scratch. Try a bow, fire pots and bear traps."
        self.start_cutscene(b.kind, b.center_x, b.center_y, self.day, mode="retreat", hp=line)

    def _update_fleeing(self, dt):
        """Bosses running away at dawn. Runs even during the cutscene, so you watch it go."""
        for b in list(self.over.bosses):
            if b.state != "flee":
                continue
            b.state_t += dt
            b.flash = max(0, b.flash - dt)
            dx, dy = b.charge_dir
            speed = b.speed * 2.4 * min(1.0, b.state_t / 0.6)     # turns, then bolts
            b.center_x = max(40, min(self.world_size - 40, b.center_x + dx * speed * dt))
            b.center_y = max(40, min(self.world_size - 40, b.center_y + dy * speed * dt))
            b.heading = math.atan2(dy, dx)
            b.wobble += dt * 8
            b.angle = -math.degrees(b.heading) + math.sin(b.wobble) * 6
            b.alpha = int(255 * max(0.0, 1 - max(0.0, b.state_t - 1.2) / 2.6))
            if random.random() < 0.35:
                self.fx_layer = "over"
                self.burst(b.center_x, b.center_y, (70, 66, 64), 2, 60, 5, 0.9)
            if b.state_t >= 4.0:
                self.bmap.pop(b.bid, None)
                b.remove_from_sprite_lists()

    def start_cutscene(self, kind, x, y, night, local=False, mode="intro", hp=""):
        self.cut = {"kind": kind, "x": x, "y": y, "t": 0.0, "dur": 9.0 if mode == "intro" else 5.5, "night": night,
                    "mode": mode, "hp": hp}
        self.ui_open = None
        self.mouse_down = False
        self._play("roar", 0.25, speed=0.6)
        if not local:
            self._emit(["cut", kind, r1(x), r1(y), night, mode, hp], None)

    def end_cutscene(self):
        if self.cut:
            self.cut = None
            if self.net == "host":
                self.events_all.append(["cutend"])

    def kill_boss(self, b, by=None):
        self.fx_layer = "over"
        self.burst(b.center_x, b.center_y, (255, 200, 120), 50, 320, 6, 1.4)
        self.ring(b.center_x, b.center_y, 20, 420, 0.9, (255, 220, 160))
        self.shake(14, 0.8)
        self.play("win", 0.5)
        self.kills += 1
        drops = ", ".join(f"{v} {ITEMS[k]['name']}" for k, v in b.info["drops"].items())
        for p in self.players.values():
            if p.alive:
                for k, v in b.info["drops"].items():
                    self.give(p, k, v)
        if by:
            by.kills += 1
        self.on_boss_killed(b, by)
        if b.state == "flee" and self.cut and self.cut.get("mode") == "retreat":
            self.end_cutscene()            # shot down as it ran: no "it will be back" scene
        self.boss_num += 1
        self.boss_day = self.day + self.boss_gap
        self.boss_hp = None
        gap = f"{self.boss_gap} night{'s' if self.boss_gap > 1 else ''}"
        self.say(f"{b.info['name']} IS DEFEATED!  Everyone alive gets: {drops}.   "
                 f"Next: {self.next_boss()['name']} in {gap}.", 9)
        self.bmap.pop(b.bid, None)
        b.remove_from_sprite_lists()
        self.hazards = [h for h in self.hazards if h.owner is not b]
        self.cold_mult = 1.0

    # ------------------------------------------------------------------ update
    def on_update(self, dt):
        dt = min(dt, 1 / 20)
        self.flame_t += dt
        self.pad.poll(dt)
        self.fp_tick(dt)                   # firstperson.py: mouse capture, controller looking
        if self.local and self.state == "playing":
            self.local_input(dt)
        else:
            self.handle_pad(dt)
        if self.net == "host":
            self.host_network()
        elif self.net == "client":
            self.client_network(dt)
        if self.state == "title":
            self.clock += dt * 6
            self._update_fx(dt)
            self.update_menu()
            if self.menu == "local":
                self.lobby_pad()
            return
        if self.state == "intro":      # opening cutscene (intro.py)
            self.intro.update(dt, self)
            if self.intro.done:
                self.end_intro()
            return
        if self.intro:                 # co-op opening cutscene: an overlay while the world keeps running
            self.intro.update(dt, self)
            if self.intro.done:
                self.end_intro()
        if self.me:
            self.me.arriving = bool(self.intro)
        frozen =self.net is None and (self.ui_open or self.paused)
        if frozen:
            self._update_fx(dt)
            return
        if self.cut:
            self.cut["t"] += dt
            if self.cut["t"] >= self.cut["dur"]:
                self.end_cutscene()
        if self.sim and self.state == "playing":
            self._update_fleeing(dt)
        if self.local:
            self.local_move(dt)
        else:
            self.read_local_input()
            if self.me and self.me.alive and self.state == "playing" and not self.cut:
                self.move_player(self.me, dt)
        if self.sim:
            if self.state == "playing" and not self.cut:
                self.time_alive += dt
                self._update_clock(dt)
                for p in list(self.players.values()):
                    self._update_survivor(p, dt)
                for L in self.layers.values():
                    self._update_zombies(L, dt)
                self._update_animals(dt)
                self._update_bosses(dt)
                self._update_hazards(dt)
                self._update_shots(dt)
                venom.tick(self, dt)          # venom.py: poisoned enemies take damage
                self._update_defenses(dt)     # defenses.py: turrets shoot
                self._update_world(dt)
                self.update_swamp(dt)      # swamp.py: the Drowned rise at night
                self.biome_update(dt)      # biomes.py: every plug-in's per-frame logic
        else:
            if not self.cut:
                self.clock += dt * self.clock_rate() * (8 if self.fast_forward else 1)
            self._client_visuals(dt)
        self.weather_tick(dt)      # weather.py
        if self.state == "playing":
            self.biome_ambient(dt)     # biomes.py: the viewer's biome particles
        self._update_visuals(dt)
        if self.local:
            self.local_cameras(dt)
        else:
            self._update_camera(dt)
        self._update_fx(dt)
        if self.net == "host":
            self.snap_t -= dt
            if self.snap_t <= 0:
                self.snap_t = SNAPSHOT_RATE
                self.send_snapshots()
        elif self.net == "client":
            self.input_t -= dt
            if self.input_t <= 0:
                self.input_t = INPUT_RATE
                self.send_input()

    # --- local input -> my survivor
    def aim_world(self):
        me = self.me
        if self.fp_on():
            return self.fp_aim()         # firstperson.py: where you're looking
        if self.use_pad:
            return (me.sprite.center_x + math.cos(me.face) * 80, me.sprite.center_y + math.sin(me.face) * 80)
        return self.mouse_ground()   # where the mouse ray hits the 3D ground

    def read_local_input(self):
        me = self.me
        if not me:
            return
        k = self.keys
        busy = bool(self.ui_open or self.paused or self.cut or self.intro)
        dx = (arcade.key.D in k or arcade.key.RIGHT in k) - (arcade.key.A in k or arcade.key.LEFT in k)
        dy = (arcade.key.W in k or arcade.key.UP in k) - (arcade.key.S in k or arcade.key.DOWN in k)
        rest = arcade.key.LSHIFT in k or arcade.key.RSHIFT in k
        attack = self.mouse_down
        pad = self.pad
        if self.use_pad:
            if not busy:
                if pad.left != (0, 0):
                    dx, dy = pad.left
                rest = rest or "x" in pad.down
                attack = attack or "a" in pad.down or "rt" in pad.down
            if self.fp_on():
                pass                     # first person: the right stick looks around (fp_tick)
            elif pad.right != (0, 0):
                me.face = math.atan2(pad.right[1], pad.right[0])
            elif (dx or dy) and not busy:
                me.face = math.atan2(dy, dx)
        else:
            mx, my = self.aim_world()
            me.face = math.atan2(my - me.sprite.center_y, mx - me.sprite.center_x)
        if busy:
            dx = dy = 0
            attack = False
        if self.fp_on():
            dx, dy = self.fp_move(me, dx, dy)   # firstperson.py: walk where you look
        me.move = (dx, dy)
        me.resting = rest
        me.attacking = attack and me.alive and not rest

    def move_player(self, p, dt):
        dx, dy = p.move
        moving = (dx or dy) and not p.resting
        speed = PLAYER_SPEED if p.energy > 0 else TIRED_SPEED
        if p.warmth <= 0:
            speed *= 0.75
        speed *= self.swamp_speed(p, dt)     # swamp.py: mud, bog pools, grasping roots
        speed *= self.biome_speed(p)         # biomes.py: biome + terrain (snow, hills...)
        speed *= 1 + p.gear("speed")         # light armor (Chitin Armor) makes you quicker
        if moving:
            n = max(1.0, math.hypot(dx, dy))
            p.sprite.change_x = dx / n * speed * dt
            p.sprite.change_y = dy / n * speed * dt
        else:
            p.sprite.change_x = p.sprite.change_y = 0
        ox, oy = p.sprite.center_x, p.sprite.center_y
        p.physics.update()
        if biomes.with_hook("blocked") and self.terrain_blocked(p.sprite.center_x, p.sprite.center_y, p.layer):
            if not self.terrain_blocked(p.sprite.center_x, oy, p.layer):     # slide along cliffs / rivers
                p.sprite.center_y = oy
            elif not self.terrain_blocked(ox, p.sprite.center_y, p.layer):
                p.sprite.center_x = ox
            else:
                p.sprite.center_x, p.sprite.center_y = ox, oy
        size = self.layers[p.layer].size
        p.sprite.center_x = max(20, min(size - 20, p.sprite.center_x))
        p.sprite.center_y = max(20, min(size - 20, p.sprite.center_y))

    def _update_clock(self, dt):
        before = self.phase
        everyone_down = bool(self.players) and not self.alive_players()
        self.fast_forward = everyone_down and self.is_night
        self.clock += dt * self.clock_rate() * (8 if self.fast_forward else 1)
        p = self.phase
        if before < DUSK_START <= p:
            if self.boss_night and self.boss_hp is not None:
                self.say(f"{self.next_boss()['name']} is coming back tonight. Finish it!", 6)
            elif self.boss_night:
                self.say("The ground trembles... something BIG is coming tonight. Get ready!", 6)
            else:
                self.say("Dusk... they're coming. Build walls, light a fire, or get to a hut.", 5)
        if before < NIGHT_START <= p and self.boss_night and not self.over.bosses:
            self.spawn_boss()
        if before < DAWN_START <= p:
            self.say("Dawn breaks - the dead burn in the sunlight.", 4)
            for b in list(self.over.bosses):
                if b.state == "flee":
                    continue
                self.boss_hp = b.hp            # it remembers every hit
                self.boss_day = self.day + 1   # ...and comes back tomorrow night
                self.say(f"{b.info['name']} retreats ({int(b.hp)}/{int(b.max_hp)})... it will be back tomorrow night.", 7)
                self.start_retreat(b)
            self.hazards = []
            self.cold_mult = 1.0
            for s in self.players.values():
                if not s.alive:
                    self.respawn(s)
        if p < before:
            self.day += 1
            tonight = ""
            if self.boss_night:
                tonight = (f"  Tonight {self.next_boss()['name']} returns." if self.boss_hp is not None
                           else "  Tonight a BOSS rises.")
            self.say(f"Day {self.day}. You survived the night." + tonight, 5)
            self.on_new_day()    # progress.py: +1 night survived for everyone
            self.save_game()     # autosave every morning
        n_over = len(self.alive_players("over"))
        if self.is_night and n_over:
            self.over.spawn_timer -= dt
            cap = int((6 + 5 * self.day) * (1 + 0.6 * (n_over - 1)))
            if self.over.spawn_timer <= 0 and len(self.over.zombies) < cap:
                self.spawn_zombie("over")
                self.over.spawn_timer = max(0.7, 3.2 - 0.35 * self.day) * random.uniform(0.6, 1.3) / \
                    (1 + 0.5 * (n_over - 1))
        for L in self.layers.values():          # underground layers (cave, deep...): always dark, always hungry
            if L.name == "over":
                continue
            n_cave = len(self.alive_players(L.name))
            if n_cave:
                L.spawn_timer -= dt
                if L.spawn_timer <= 0 and len(L.zombies) < 5 + 3 * n_cave + self.day:
                    self.spawn_zombie(L.name)
                    L.spawn_timer = random.uniform(2.5, 5.0) / n_cave

    def base_spot(self):
        for kind in ("base_flag", "hut", "storage", "workbench"):
            for s in self.structs.values():
                if s.kind == kind and s.layer == "over":
                    return (s.center_x, s.center_y - 70)
        return self.centre

    def respawn(self, p):
        x, y = self.base_spot()
        self.set_layer(p, "over", (x + random.uniform(-30, 30), y))
        p.alive = True
        p.health, p.hunger, p.thirst, p.energy, p.warmth = 70.0, 70.0, 70.0, 100.0, 100.0
        p.inv = dict(STARTING_ITEMS)
        p.hotbar = [None] * HOTBAR_SLOTS
        for k in p.inv:
            self._hotbar_add(p, k)
        p.sprite.visible = True
        p.tp += 1
        p.respawn_t = -1
        self.say(f"{p.name} is back on their feet!", 3)
        self.say("You're back at your base with empty pockets. Check the team storage!", 5, to=p)

    def down_player(self, p):
        p.alive = False
        p.health = 0
        p.attacking = False
        self.stat(p, "downed")
        p.sprite.visible = False
        p.held.visible = False
        self.burst(p.sprite.center_x, p.sprite.center_y, (200, 40, 40), 24, 160, 4, 0.8, layer=p.layer)
        self.play("die", 0.4, to=p)
        lost = sum(p.inv.values()) + sum(1 for v in p.equip.values() if v)
        p.inv = {}
        p.hotbar = [None] * HOTBAR_SLOTS
        p.equip = {s: None for s in ARMOR_SLOTS}
        night = DUSK_START <= self.phase < DAWN_START
        p.respawn_t = -1.0 if night else float(DAY_RESPAWN_SECONDS)
        when = "at dawn" if night else f"in {DAY_RESPAWN_SECONDS} seconds"
        self.say(f"YOU DIED - and lost everything you carried ({lost} items). You'll be back {when}.", 7, to=p)
        if len(self.players) > 1:
            self.say(f"{p.name} died! They'll be back {when}.", 4)

    def _update_survivor(self, p, dt):
        if not p.alive:
            if p.respawn_t > 0:
                p.respawn_t -= dt
                if p.respawn_t <= 0:
                    self.respawn(p)
            return
        if p.health <= 0:
            self.down_player(p)
            return
        p.trap_cd -= dt
        if p.trap_cd <= 0:
            for t in arcade.check_for_collision_with_list(p.sprite, self.layers[p.layer].traps):
                if t.kind == "spike_trap":
                    self.hurt_player(p, SPIKE_PLAYER_DAMAGE)
                    self.damage_structure(t, 1)
                    p.trap_cd = 0.8
                    if self.time_alive - p.trap_warned > 12:
                        p.trap_warned = self.time_alive
                        self.say("OUCH! Spike traps hurt you too - get off it! Put traps in the zombies' path.", 3, to=p)
                    break
        moving = (p.move[0] or p.move[1]) and not p.resting
        L = self.layers[p.layer]
        p.in_hut = None
        for hsp in L.huts:
            if abs(hsp.center_x - p.sprite.center_x) < 46 and abs(hsp.center_y - p.sprite.center_y) < 46:
                p.in_hut = hsp
        fire = self.near_fire(p.pos, p.layer, 120)

        p.hunger -= HUNGER_DECAY_PER_SEC * dt
        p.thirst -= THIRST_DECAY_PER_SEC * dt
        if moving:
            p.energy -= ENERGY_DECAY_PER_SEC * dt
        if p.resting:
            boost = 2.0 if p.in_hut else 1.5 if fire else 1.0
            p.energy += REST_RESTORE_PER_SEC * boost * dt
            if p.in_hut:
                p.health += 3.0 * dt
            elif fire:
                p.health += 1.5 * dt
        if p.hunger <= 0:
            p.health -= STARVE_DAMAGE_PER_SEC * dt
        if p.thirst <= 0:
            p.health -= THIRST_DAMAGE_PER_SEC * dt
        if p.hunger > 50 and p.thirst > 50 and p.warmth > 25:
            p.health += NATURAL_REGEN_PER_SEC * dt

        # temperature: night and caves are cold; fire, huts, torches and clothes keep you warm
        if p.layer != "over":
            cold = self.layer_cold(p.layer)      # biomes.LAYER_INFO (the cave: CAVE_COLD_PER_SEC)
        else:
            cold = COLD_PER_SEC * self.darkness * self.cold_mult
        cold += self.weather_survivor(p, dt)   # weather.py: winter nights, snow, rain
        cold += self.biome_survivor(p, dt)     # biomes.py: tundra chill, ash heat, hazards...
        cold = max(0.0, cold - p.gear("warmth") * WARMTH_PER_GEAR_POINT)
        warm = 0.0
        if self.near_fire(p.pos, p.layer):
            warm += FIRE_WARM_PER_SEC
        if p.in_hut:
            warm += HUT_WARM_PER_SEC
        if p.holding_torch:
            warm += TORCH_WARM_PER_SEC
        if p.layer == "over" and self.darkness < 0.2:
            warm += DAY_WARM_PER_SEC
        p.warmth += (warm - cold) * dt
        if p.warmth <= 0:
            p.health -= FREEZE_DAMAGE_PER_SEC * dt
        p.hunger = max(0, min(STAT_MAX, p.hunger))
        p.thirst = max(0, min(STAT_MAX, p.thirst))
        p.energy = max(0, min(STAT_MAX, p.energy))
        p.warmth = max(0, min(STAT_MAX, p.warmth))
        p.health = min(STAT_MAX, p.health)

        p.attack_cd -= dt
        if p.attacking and p.attack_cd <= 0 and not p.resting:   # resting = hands busy, no farming
            self.attack(p)
        p.swing = max(0, p.swing - dt)
        p.hurt = max(0, p.hurt - dt)
        if p.health <= 0:
            self.down_player(p)

    # --- moving things through the world without walking through walls
    def step_body(self, s, mvx, mvy, blockers):
        """Move a sprite with collisions. Returns (things it bumped into, distance actually moved).
        Hit boxes are checked un-rotated so wobbling sprites can never 'turn' into a wall."""
        s.angle = 0
        hit_now = arcade.check_for_collision_with_lists(s, blockers)
        if hit_now:
            # overlapping something (e.g. a wall got built on it): slide straight out, away from it
            b = hit_now[0]
            ox, oy = s.center_x - b.center_x, s.center_y - b.center_y
            d = math.hypot(ox, oy) or 1
            step = max(2.0, math.hypot(mvx, mvy))
            s.center_x += ox / d * step
            s.center_y += oy / d * step
            return hit_now, 0.0
        blocked, moved = [], 0.0
        s.center_x += mvx
        hit = arcade.check_for_collision_with_lists(s, blockers)
        if hit:
            s.center_x -= mvx
            blocked += hit
        else:
            moved += abs(mvx)
        s.center_y += mvy
        hit = arcade.check_for_collision_with_lists(s, blockers)
        if hit:
            s.center_y -= mvy
            blocked += hit
        else:
            moved += abs(mvy)
        return blocked, moved

    def _update_zombies(self, L, dt):
        if not len(L.zombies):
            return
        self.fx_layer = L.name
        alive = self.alive_players(L.name)
        day_burn = L.name == "over" and not self.is_night and self.darkness < 0.5
        fires = [s for s in L.builds if s.kind in LIGHT_SOURCES and s.lit]
        guards = [a for a in L.animals if a.pet and a.info["job"] == "guard"]
        blockers = [L.solid, L.huts] + self.defense_blockers(L)
        zl = list(L.zombies)
        for z in zl:
            tgt = min(alive, key=lambda p: dist(p.pos, z.position)) if alive else None
            ppos = tgt.pos if tgt else z.position
            dx, dy = ppos[0] - z.center_x, ppos[1] - z.center_y
            d = math.hypot(dx, dy) or 1
            vx, vy = (dx / d, dy / d) if tgt else (0.0, 0.0)
            if z.kind not in ("brute", "golem"):
                for f in fires:
                    fd = dist(f.position, z.position)
                    rad = FIRE_FEAR_RADIUS * (1.4 if f.kind == "brazier" else 1)
                    if fd < rad:
                        push = (rad - fd) / rad * 2.2
                        vx += (z.center_x - f.center_x) / (fd or 1) * push
                        vy += (z.center_y - f.center_y) / (fd or 1) * push
            for o in zl:
                if o is not z:
                    ox, oy = z.center_x - o.center_x, z.center_y - o.center_y
                    od = abs(ox) + abs(oy)
                    if od < 30:
                        vx += ox / (od or 1) * 0.6
                        vy += oy / (od or 1) * 0.6
            n = math.hypot(vx, vy) or 1
            vx, vy = vx / n, vy / n
            if z.detour > 0:
                z.detour -= dt
                vx, vy = vx * 0.3 + z.detour_dir[0], vy * 0.3 + z.detour_dir[1]
                n = math.hypot(vx, vy) or 1
                vx, vy = vx / n, vy / n
            step = z.speed * dt * (0.5 if z.chill > 0 else 1) * (0 if z.snared > 0 else 1)
            step *= self.defense_slow(z)     # defenses.py: lanterns slow them down
            blocked_by, moved = self.step_body(z, vx * step, vy * step, blockers)
            nature = [b for b in blocked_by if not isinstance(b, Structure)]
            if nature and moved < step * 0.35 and z.detour <= 0:
                side = random.choice((-1, 1))
                z.detour_dir = (-vy * side, vx * side)
                z.detour = random.uniform(0.4, 0.9)

            z.attack_cd -= dt
            z.trap_cd -= dt
            z.snared = max(0, z.snared - dt)
            z.chill = max(0, z.chill - dt)
            if z.attack_cd <= 0:
                built = [b for b in blocked_by if isinstance(b, Structure)]
                pet = next((g for g in guards if dist(g.position, z.position) < z.radius + 20), None)
                if tgt and d < z.radius + 18 and not tgt.in_hut:
                    self.hurt_player(tgt, z.damage)
                    z.attack_cd = z.attack_every
                elif built:
                    self.damage_structure(built[0], z.damage * 0.6)
                    z.attack_cd = z.attack_every
                elif pet:
                    self.hurt_pet(pet, z.damage * 0.5)     # pet armor soaks some of it
                    z.attack_cd = z.attack_every
            if z.trap_cd <= 0:
                for t in arcade.check_for_collision_with_list(z, L.traps):
                    if t.kind == "bear_trap":
                        if not t.lit:          # sprung - still re-arming
                            continue
                        z.snared = BEAR_TRAP_HOLD
                        self.set_fire(t, False)
                        t.out_t = BEAR_TRAP_REARM
                        self.burst(z.center_x, z.center_y, (190, 190, 200), 8, 90, layer=z.layer)
                        self.play("hit", 0.3, at=t.position, layer=t.layer)
                        self.damage_structure(t, 15)
                    else:
                        z.hp -= SPIKE_ZOMBIE_DAMAGE
                        z.flash = 0.12
                        self.burst(z.center_x, z.center_y, (110, 30, 30), 5, 100, layer=z.layer)
                        self.damage_structure(t, SPIKE_WEAR)
                    z.trap_cd = 0.6
                    break
            if z.burn > 0:
                z.burn -= dt
                z.hp -= 2.0 * dt
                if random.random() < 0.4:
                    self.burst(z.center_x, z.center_y, (255, 140, 40), 1, 50, 3, 0.5)
            if day_burn and z.kind not in ("golem", "crawler"):
                z.hp -= SUN_BURN_PER_SEC * dt
                if random.random() < 0.3:
                    self.burst(z.center_x, z.center_y, (90, 90, 90), 1, 40, 4, 0.8)
            z.wobble += dt * 9
            z.heading = math.atan2(vy, vx) if (vx or vy) else z.heading
            z.angle = -math.degrees(z.heading) + math.sin(z.wobble) * 7
            z.flash = max(0, z.flash - dt)
            if z.hp <= 0:
                if day_burn and z.burn <= 0:
                    self.burst(z.center_x, z.center_y, (80, 80, 80), 14, 90, 5, 1.0)
                    if z.eye:
                        z.eye.remove_from_sprite_lists()
                    z.remove_from_sprite_lists()
                else:
                    self.kill_zombie(z)

    # ------------------------------------------------------------------ animals & pets
    def spawn_animal(self):
        alive = self.alive_players("over")
        S = self.world_size
        for _ in range(20):
            x, y = random.uniform(150, S - 150), random.uniform(150, S - 150)
            if any(dist((x, y), p.pos) < 550 for p in alive) or self.in_base((x, y)):
                continue
            weights = self.animal_weights((x, y))      # biomes.py: each biome has its own wildlife
            kind = random.choices(list(ANIMALS), [weights.get(k, 2) for k in ANIMALS])[0]
            if kind == "bee":
                return self.spawn_bee(alive)
            a = Animal(kind, x, y, self.next_aid)
            if arcade.check_for_collision_with_lists(a, [self.over.solid, self.over.huts]):
                continue
            self.next_aid += 1
            self.over.animals.append(a)
            self.amap[a.aid] = a
            return a

    def spawn_bee(self, alive):
        """Wild bees live around the beehives in the trees (a couple per hive)."""
        homes = {}
        for a in self.over.animals:
            if a.kind == "bee" and not a.pet and a.hive:
                homes[a.hive] = homes.get(a.hive, 0) + 1
        hives = [n for n in self.over.trees if n.kind == "hive" and n.state != "gone" and homes.get(n, 0) < 2
                 and not any(dist(n.position, p.pos) < 450 for p in alive)]
        if not hives:
            return None
        h = random.choice(hives)
        a = Animal("bee", h.center_x + random.uniform(-30, 30), h.center_y + random.uniform(-30, 30), self.next_aid)
        a.hive = h
        self.next_aid += 1
        self.over.animals.append(a)
        self.amap[a.aid] = a
        return a

    def _update_animals(self, dt):
        L = self.over
        self.fx_layer = "over"
        wild = [a for a in L.animals if not a.pet]
        self.animal_t -= dt
        if self.animal_t <= 0:
            self.animal_t = 4.0
            if len(wild) < self.animal_cap and not self.is_night:
                self.spawn_animal()
        blockers = [L.solid, L.huts]
        players_over = self.alive_players("over")
        for a in list(L.animals):
            a.flash = max(0, a.flash - dt)
            a.attack_cd -= dt
            if a.pet:
                vx, vy, speed = self._pet_brain(a, dt)
                a.hp = min(a.max_hp, a.hp + 0.4 * dt)
            else:
                vx, vy, speed = self._wild_brain(a, dt, players_over)
            a.moving = bool(vx or vy) and speed > 0
            if a.moving:
                if a.detour > 0:
                    a.detour -= dt
                    vx, vy = vx * 0.3 + a.detour_dir[0], vy * 0.3 + a.detour_dir[1]
                n = math.hypot(vx, vy) or 1
                vx, vy = vx / n, vy / n
                step = speed * dt
                blocked, moved = self.step_body(a, vx * step, vy * step, [] if a.info.get("flies") else blockers)
                if blocked and moved < step * 0.35 and a.detour <= 0:
                    side = random.choice((-1, 1))
                    a.detour_dir = (-vy * side, vx * side)
                    a.detour = random.uniform(0.4, 0.9)
                a.heading = math.atan2(vy, vx)
                a.center_x = max(40, min(self.world_size - 40, a.center_x))
                a.center_y = max(40, min(self.world_size - 40, a.center_y))
            a.angle = -math.degrees(a.heading)
            if not a.pet and self.is_night and self.darkness > 0.9 and random.random() < dt * 0.01:
                self.amap.pop(a.aid, None)   # wild animals slowly bed down for the night
                a.remove_from_sprite_lists()

    def _wild_brain(self, a, dt, players):
        info = a.info
        near = min(players, key=lambda p: dist(p.pos, a.position)) if players else None
        nd = dist(near.pos, a.position) if near else 9999
        a.aggro_t -= dt
        angry = self.players.get(a.aggro) if a.aggro is not None and a.aggro_t > 0 else None
        if angry and (not angry.alive or angry.layer != "over"):
            angry = None
        if angry and info["temper"] == "defend":
            dx, dy = angry.pos[0] - a.center_x, angry.pos[1] - a.center_y
            d = math.hypot(dx, dy) or 1
            if d < 34:
                if a.attack_cd <= 0:
                    self.hurt_player(angry, info["dmg"])
                    a.attack_cd = 1.2
                return 0.0, 0.0, 0.0
            return dx / d, dy / d, info["speed"] * 1.6
        if (angry or (info["temper"] == "flee" and nd < 170)) and near:
            src = angry or near
            dx, dy = a.center_x - src.pos[0], a.center_y - src.pos[1]
            d = math.hypot(dx, dy) or 1
            return dx / d, dy / d, info["speed"]
        if a.hive is not None:   # wild bees buzz in loops around their hive
            t = self.flame_t * 1.3 + a.aid
            hx, hy = a.hive.center_x + math.cos(t) * 45, a.hive.center_y + math.sin(t * 1.7) * 35
            dx, dy = hx - a.center_x, hy - a.center_y
            d = math.hypot(dx, dy)
            return (dx / d, dy / d, info["speed"] * 0.5) if d > 6 else (0.0, 0.0, 0.0)
        a.wander_t -= dt
        if a.wander_t <= 0:
            a.wander_t = random.uniform(1.5, 4.0)
            if random.random() < 0.6:
                a.heading = random.uniform(0, math.tau)
            a.goal = None if random.random() < 0.4 else "walk"
        if a.goal == "walk":
            return math.cos(a.heading), math.sin(a.heading), info["speed"] * 0.3
        return 0.0, 0.0, 0.0

    def _pet_brain(self, a, dt):
        owner = self.players.get(a.owner)
        job = a.info["job"]
        sp = a.info["speed"]
        home = self.nearest_storage(a.position)
        owner_here = owner is not None and owner.alive and owner.layer == "over"

        def go(x, y, slack=40, speed=sp):
            dx, dy = x - a.center_x, y - a.center_y
            d = math.hypot(dx, dy)
            if d < slack:
                return 0.0, 0.0, 0.0
            return dx / d, dy / d, speed

        # guards always defend: bite zombies close to the pet / its owner / the base
        if job == "guard" and a.mode != "stay":
            centre = owner.pos if (a.mode == "follow" and owner_here) else (home.position if home else a.position)
            foes = [z for z in self.over.zombies if dist(z.position, centre) < 300]
            foes += [b for b in self.over.bosses if dist(b.position, centre) < 300]
            if foes:
                z = min(foes, key=lambda z: dist(z.position, a.position))
                if dist(z.position, a.position) < z.radius + 26:
                    a.heading = math.atan2(z.center_y - a.center_y, z.center_x - a.center_x)
                    if a.attack_cd <= 0:
                        a.attack_cd = 0.8
                        self.hit_enemy(z, 3, owner, 0, 0)
                    return 0.0, 0.0, 0.0
                return go(*z.position, 10, sp * 1.2)
        if a.mode == "stay":
            return 0.0, 0.0, 0.0
        if a.mode == "work" and job == "guard":
            if home:
                t = self.flame_t * 0.3 + a.aid
                return go(home.center_x + math.cos(t) * 120, home.center_y + math.sin(t) * 120, 30, sp * 0.5)
            return 0.0, 0.0, 0.0
        if a.mode == "follow":
            if owner_here:
                d = dist(owner.pos, a.position)
                if d > 900:   # got lost - catch up
                    a.position = (owner.pos[0] - 40, owner.pos[1] - 40)
                return go(*owner.pos, 85, sp * (1.4 if d > 250 else 1))
            return 0.0, 0.0, 0.0
        # --- work: gather, then haul it home
        if a.carrying >= (BEE_CARRY if job == "beekeeper" else PET_CARRY) or a.goal == "home":
            if not a.carrying:
                a.goal = None
                return 0.0, 0.0, 0.0
            a.goal = "home"
            dest = home.position if home else (owner.pos if owner_here else None)
            if dest is None:
                return 0.0, 0.0, 0.0
            mv = go(*dest, 55)
            if mv[2] == 0.0:
                names = ", ".join(f"{v} {ITEMS[k]['name']}" for k, v in a.carry.items())
                for k, v in a.carry.items():
                    if home:
                        self.store_add(k, v)
                    elif owner:
                        self.give(owner, k, v)
                where = "storage" if home else owner.name
                self.popup(f"{a.kind.title()} -> {where}: {names}", a.center_x, a.center_y + 30, (255, 230, 150))
                a.carry = {}
                a.goal = None
            return mv
        if job == "beekeeper":   # visit flowering bushes, turn the nectar into honey (bushes aren't used up)
            if not isinstance(a.goal, Node):
                ref = home.position if home else a.position
                cands = [n for n in self.over.bushes if dist(n.position, ref) < 900]
                cands.sort(key=lambda n: dist(n.position, a.position))
                a.goal = random.choice(cands[:4]) if cands else None
                a.job_t = BEE_HONEY_EVERY
                if a.goal is None:
                    return 0.0, 0.0, 0.0
            n = a.goal
            mv = go(*n.position, 22)
            if mv[2] == 0.0:
                a.job_t -= dt
                if a.job_t <= 0:
                    a.carry["honey"] = a.carry.get("honey", 0) + 1
                    self.burst(n.center_x, n.center_y, (250, 200, 60), 5, 50)
                    a.goal = None   # next flower
            return mv
        kinds = ("bush",) if job == "forager" else ("tree", "rock")
        if not isinstance(a.goal, Node) or a.goal.state != "full":
            ref = home.position if home else a.position
            cands = [n for lst in self.over.node_lists() for n in lst
                     if n.kind in kinds and n.state == "full" and dist(n.position, ref) < 900]
            a.goal = min(cands, key=lambda n: dist(n.position, a.position)) if cands else None
            if a.goal is None:
                if a.carrying:
                    a.goal = "home"
                return 0.0, 0.0, 0.0
        n = a.goal
        mv = go(*n.position, 50)
        if mv[2] == 0.0:
            a.job_t -= dt
            a.heading = math.atan2(n.center_y - a.center_y, n.center_x - a.center_x)
            if a.job_t <= 0:
                a.job_t = 1.6
                for k, v in self.harvest(n, 1).items():
                    a.carry[k] = a.carry.get(k, 0) + v
                if n.state != "full":
                    a.goal = None
        return mv

    def nearest_storage(self, pos):
        bins = [s for s in self.structs.values() if s.kind == "storage" and s.layer == "over"]
        return min(bins, key=lambda s: dist(s.position, pos)) if bins else None

    # ------------------------------------------------------------------ boss brains
    def _update_bosses(self, dt):
        L = self.over
        self.fx_layer = "over"
        self.cold_mult = 1.0
        alive = self.alive_players("over")
        for b in list(L.bosses):
            if b.state == "flee":          # running away at dawn (_update_fleeing)
                continue
            b.flash = max(0, b.flash - dt)
            b.attack_cd -= dt
            b.wobble += dt * 4
            for k in b.timers:
                b.timers[k] -= dt
            if b.kind == "wraith":
                self.cold_mult = 2.6
                for s in self.structs.values():
                    if s.kind in LIGHT_SOURCES and s.lit and s.layer == "over" and dist(s.position, b.position) < 240:
                        self.set_fire(s, False)
                        s.out_t = 20.0
                        self.burst(s.center_x, s.center_y, (200, 230, 255), 12, 100)
            tgt = min(alive, key=lambda p: dist(p.pos, b.position)) if alive else None
            if not tgt:
                continue
            tx, ty = tgt.pos
            d = dist(tgt.pos, b.position)
            vx, vy = (tx - b.center_x) / (d or 1), (ty - b.center_y) / (d or 1)
            speed = b.speed
            if d < b.radius + 16:            # close enough to swing - don't stand on top of people
                speed = 0
            if b.kind == "wraith" and b.timers["b"] > 2.5 and d < 230:   # hangs back to throw shards
                vx, vy = -vx, -vy
                speed = b.speed * 0.6
            if b.state == "windup":
                b.state_t -= dt
                speed = 0
                if b.state_t <= 0:
                    if b.kind == "colossus":
                        b.state, b.state_t = "charge", 0.75
                        self.play("roar", 0.4, at=b.position, layer="over")
                    else:
                        b.state = "walk"
            elif b.state == "charge":
                b.state_t -= dt
                vx, vy = b.charge_dir
                speed = 560
                for p in alive:
                    if dist(p.pos, b.position) < b.radius + 22 and b.attack_cd <= 0:
                        self.hurt_player(p, b.damage * 1.2)
                        b.attack_cd = 0.6
                if b.state_t <= 0:
                    b.state = "walk"
            elif b.state == "blink":
                b.state_t -= dt
                speed = 0
                b.alpha = int(255 * max(0.1, b.state_t / 0.8))
                if b.state_t <= 0:
                    b.position = b.target
                    b.alpha = 255
                    b.state = "walk"
                    self.burst(b.center_x, b.center_y, (200, 230, 255), 26, 200, 4, 0.8)
                    self.play("laser", 0.4, at=b.position, layer="over")
            elif b.state == "submerge":      # swamp.py: the Mire Lurker under the mud
                speed = 0
                self.mire_submerge(b, dt, alive)
            else:
                self._boss_abilities(b, tgt, alive, d)
            b.snared = max(0, b.snared - dt)
            for t in arcade.check_for_collision_with_list(b, L.traps):
                if t.kind == "bear_trap" and t.lit and b.state != "blink":
                    b.snared = BEAR_TRAP_BOSS_HOLD
                    if b.state == "charge":
                        b.state = "walk"
                    self.set_fire(t, False)
                    t.out_t = BEAR_TRAP_REARM
                    self.play("hit", 0.4, at=t.position, layer="over")
                    self.say(f"The Bear Trap caught {b.info['name']}!", 2)
                    self.damage_structure(t, 30)
                elif t.kind == "spike_trap":
                    self.damage_structure(t, 999)          # crushed flat...
                    self.hit_enemy(b, SPIKE_BOSS_DAMAGE)    # ...but it hurt
            if b not in L.bosses:                           # the spikes finished it off
                continue
            if b.snared > 0:
                speed = 0
            if speed and b.state != "blink":
                step = speed * dt
                if b.kind == "wraith":
                    b.center_x += vx * step
                    b.center_y += vy * step
                else:
                    blocked, moved = self.step_body(b, vx * step, vy * step, [L.solid, L.huts] + self.defense_blockers(L))
                    built = [s for s in blocked if isinstance(s, Structure)]
                    if built and b.timers.get("smash", 0) <= 0:
                        smash = 80 if b.state == "charge" else (60 if b.kind == "titan" else 30)
                        self.damage_structure(built[0], smash)
                        b.timers["smash"] = 0.8
                        self.shake(4, 0.2)
                    elif blocked and not built:   # shoulder through trees and rocks
                        b.center_x += vx * step * 0.6
                        b.center_y += vy * step * 0.6
                b.center_x = max(80, min(self.world_size - 80, b.center_x))
                b.center_y = max(80, min(self.world_size - 80, b.center_y))
                if vx or vy:
                    b.heading = math.atan2(vy, vx)
            b.angle = -math.degrees(b.heading) + math.sin(b.wobble) * 3
            if b.state == "walk" and d < b.radius + 26 and b.attack_cd <= 0 and not tgt.in_hut:
                self.hurt_player(tgt, b.damage)
                b.attack_cd = 1.4
            if b.kind == "colossus" and b.timers["trail"] <= 0 and speed:
                b.timers["trail"] = 0.45
                self.hazards.append(Hazard("fire", b.center_x, b.center_y, 30, life=3.0, dmg=6, owner=b))
        for s in self.structs.values():   # fires come back once the wraith has moved on
            if not s.lit:
                s.out_t -= dt
                if s.out_t <= 0:
                    self.set_fire(s, True)

    def _boss_abilities(self, b, tgt, alive, d):
        kind, T = b.kind, b.timers
        if kind == "titan":
            if T["a"] <= 0 and d < 460:
                T["a"] = 8.0
                b.state, b.state_t = "windup", 1.4
                self.hazards.append(Hazard("quake", b.center_x, b.center_y, 290, tele=1.4, dmg=b.damage * 0.8,
                                           owner=b))
                self.play("roar", 0.4, at=b.position, layer="over")
            elif T["b"] <= 0:
                T["b"] = 4.5
                for p in sorted(alive, key=lambda p: dist(p.pos, b.position))[:2]:
                    if dist(p.pos, b.position) < 650:
                        self.hazards.append(Hazard("boulder", p.pos[0], p.pos[1], 62, tele=1.15, dmg=16, owner=b))
        elif kind == "brood":
            if T["a"] <= 0:
                T["a"] = 11.0
                brood = sum(1 for z in self.over.zombies if z.kind == "broodling")
                for _ in range(max(0, min(4, 16 - brood))):
                    self.spawn_zombie("over", "broodling", b.position)
                self.burst(b.center_x, b.center_y, (150, 200, 90), 20, 160, 4, 0.8)
                self.say("The Brood Mother is hatching more!", 2)
            if T["b"] <= 0:
                T["b"] = 4.5
                base = math.atan2(tgt.pos[1] - b.center_y, tgt.pos[0] - b.center_x)
                for k in (-0.35, 0, 0.35):
                    a = base + k
                    self.hazards.append(Hazard("glob", b.center_x, b.center_y, 14, life=min(1.4, d / 330), dmg=9,
                                               vx=math.cos(a) * 330, vy=math.sin(a) * 330, owner=b))
                self.play("laser", 0.3, at=b.position, layer="over")
        elif kind == "wraith":
            if T["a"] <= 0:
                T["a"] = 6.0
                for k in range(12):
                    a = k / 12 * math.tau + random.uniform(0, 0.2)
                    sx, sy = b.center_x + math.cos(a) * b.radius, b.center_y + math.sin(a) * b.radius
                    self.hazards.append(Hazard("shard", sx, sy, 12, life=2.2, dmg=12,
                                               vx=math.cos(a) * 300, vy=math.sin(a) * 300, owner=b))
                self.play("laser", 0.4, at=b.position, layer="over")
            elif T["b"] <= 0:
                T["b"] = 9.0
                behind = tgt.face + math.pi
                tx = max(100, min(self.world_size - 100, tgt.pos[0] + math.cos(behind) * 90))
                ty = max(100, min(self.world_size - 100, tgt.pos[1] + math.sin(behind) * 90))
                b.state, b.state_t, b.target = "blink", 0.8, (tx, ty)
                self.hazards.append(Hazard("mist", tx, ty, 60, tele=0.8, owner=b))
        elif kind == "colossus":
            if T["a"] <= 0:
                T["a"] = 9.0
                for p in alive:
                    for _ in range(3):
                        x = p.pos[0] + random.uniform(-130, 130)
                        y = p.pos[1] + random.uniform(-130, 130)
                        self.hazards.append(Hazard("meteor", x, y, 70, tele=random.uniform(1.3, 2.0),
                                                   dmg=26, owner=b))
                self.say("METEORS! Get out of the red circles!", 2)
            elif T["c"] <= 0 and 150 < d < 600:
                T["c"] = 7.0
                a = math.atan2(tgt.pos[1] - b.center_y, tgt.pos[0] - b.center_x)
                b.charge_dir = (math.cos(a), math.sin(a))
                b.state, b.state_t = "windup", 1.0
                self.hazards.append(Hazard("line", b.center_x, b.center_y, 56, tele=1.0, a=a, ln=440, owner=b))
        elif kind == "mire":
            self.mire_abilities(b, tgt, alive, d)     # swamp.py

    def _update_hazards(self, dt):
        self.fx_layer = "over"
        alive = self.alive_players("over")
        new = []
        for h in self.hazards:
            if h.kind in self.SWAMP_HAZARDS:     # swamp.py
                new += self.swamp_hazard(h, dt, alive)
                continue
            if h.tele > 0:
                h.tele -= dt
                if h.kind == "line" and h.owner is not None:
                    h.x, h.y = h.owner.center_x, h.owner.center_y
                if h.tele <= 0:
                    new += self._trigger(h, alive)
                continue
            if h.kind in ("glob", "shard"):
                h.x += h.vx * dt
                h.y += h.vy * dt
                h.t -= dt
                for p in alive:
                    if dist(p.pos, (h.x, h.y)) < h.r + 14:
                        self.hurt_player(p, h.dmg)
                        if h.kind == "shard":
                            p.warmth = max(0, p.warmth - 12)
                        h.done = True
                        break
                if h.t <= 0 or h.done:
                    h.done = True
                    if h.kind == "glob":
                        new.append(Hazard("acid", h.x, h.y, 48, life=4.5, dmg=9, owner=h.owner))
            elif h.kind in ("acid", "fire"):
                h.t -= dt
                h.tick -= dt
                if h.tick <= 0:
                    h.tick = 0.5
                    for p in alive:
                        if dist(p.pos, (h.x, h.y)) < h.r + 10:
                            self.hurt_player(p, h.dmg * 0.5)
                if h.t <= 0:
                    h.done = True
            else:
                h.done = True
        self.hazards = [h for h in self.hazards if not h.done] + new

    def _trigger(self, h, alive):
        """A telegraphed attack lands. Returns any new hazards it leaves behind."""
        h.done = True
        if h.kind == "quake":
            self.ring(h.x, h.y, 30, h.r, 0.6, (255, 170, 80))
            self.shake(16, 0.9)
            self.burst(h.x, h.y, (150, 120, 90), 40, 300, 5, 1.0)
            self.play("boom", 0.5, at=(h.x, h.y), layer="over")
            for p in alive:
                d = dist(p.pos, (h.x, h.y))
                if d < h.r:
                    self.hurt_player(p, h.dmg * (1 - d / h.r * 0.5))
            for s in list(self.structs.values()):
                if s.layer == "over" and dist(s.position, (h.x, h.y)) < h.r:
                    self.damage_structure(s, 35)
        elif h.kind in ("boulder", "meteor"):
            col = (150, 140, 130) if h.kind == "boulder" else (255, 140, 40)
            self.burst(h.x, h.y, col, 26, 220, 5, 0.8)
            self.ring(h.x, h.y, 10, h.r + 20, 0.4, col)
            self.shake(6, 0.3)
            self.play("boom", 0.35, at=(h.x, h.y), layer="over")
            for p in alive:
                if dist(p.pos, (h.x, h.y)) < h.r + 10:
                    self.hurt_player(p, h.dmg)
            for s in list(self.structs.values()):
                if s.layer == "over" and dist(s.position, (h.x, h.y)) < h.r:
                    self.damage_structure(s, 30)
            if h.kind == "meteor":
                return [Hazard("fire", h.x, h.y, 40, life=3.5, dmg=10, owner=h.owner)]
        return []

    def _update_world(self, dt):
        for n in self.over.trees:
            if n.kind == "hive" and n.state == "empty":
                n.timer -= dt
                if n.timer <= 0:
                    self.set_node_state(n, "full")
        for n in self.over.bushes:
            if n.state == "empty":
                n.timer -= dt
                if n.timer <= 0:
                    self.set_node_state(n, "full")
        self.update_respawns(dt)     # base.py: used-up nodes turn up again somewhere new (never in a base)

    def _update_visuals(self, dt):
        view = self.view_pos()
        vl = self.view_layer
        for n in self.over.trees:
            n.alpha = 140 if n.state == "full" and vl == "over" and dist(n.position, view) < 80 else 255
        for L in self.layers.values():
            for lst in L.node_lists():
                for n in lst:
                    if n.shake > 0:
                        n.shake -= dt
                        n.center_x = n.base[0] + (math.sin(n.shake * 70) * 3 if n.shake > 0 else 0)
        self.defense_visuals(dt)
        for b in self.structs.values():
            if b.flash > 0:
                b.flash -= dt
            b.color = (255, 150, 150) if b.flash > 0 else (255, 255, 255)
        L = self.layers[vl]
        fi = int(self.flame_t * 8) % 3
        for f in L.flames:
            f.texture = art.flame(fi)
        for g in L.glows:
            g.scale = 1.0 + math.sin(self.flame_t * 9 + g.center_x) * 0.04
        for z in L.zombies:
            z.color = (255, 120, 120) if z.flash > 0 else (180, 220, 255) if z.chill > 0 else (255, 255, 255)
            if z.eye:
                z.eye.position = (z.center_x + math.cos(z.heading) * 8 * z.scale_x,
                                  z.center_y + math.sin(z.heading) * 8 * z.scale_x)
        for a in self.over.animals:
            a.color = (255, 120, 120) if a.flash > 0 else (255, 255, 255)
        for b in self.over.bosses:
            b.color = (255, 140, 140) if b.flash > 0 else (255, 255, 255)
        for p in self.players.values():
            shown = p.alive and p.layer == vl
            p.sprite.angle = -math.degrees(p.face)
            p.sprite.visible = shown
            self.sync_gear(p, shown)
            item, _ = p.weapon()
            p.held.visible = bool(item) and shown
            if p.held.visible:
                if p.held.texture is not art.held(item):
                    p.held.texture = art.held(item)
                sw = (p.swing / 0.2) if p.swing > 0 else 0
                a = p.face + math.radians(-55 + 110 * (1 - sw)) if sw else p.face + math.radians(-35)
                p.held.center_x = p.sprite.center_x + math.cos(a) * 26
                p.held.center_y = p.sprite.center_y + math.sin(a) * 26
                p.held.angle = -math.degrees(a)
        self.swamp_visuals(dt)       # swamp.py: glowcaps, fireflies

    def _update_camera(self, dt):
        vx, vy = self.view_pos()
        if self.cut:
            t, dur = self.cut["t"], self.cut["dur"]
            k = min(1, t / 1.2) if t < dur - 1.0 else max(0, (dur - t) / 1.0)
            k = k * k * (3 - 2 * k)
            vx = vx + (self.cut["x"] - vx) * k
            vy = vy + (self.cut["y"] - vy) * k
        size = self.layers[self.view_layer].size
        tx = max(W / 2, min(size - W / 2, vx))
        ty = max(H / 2, min(size - H / 2, vy))
        if abs(tx - self.cam_pos[0]) > 1200 or abs(ty - self.cam_pos[1]) > 1200:
            self.cam_pos = [tx, ty]    # changed layer: jump, don't glide
        snap = 3 if self.cut else 8
        self.cam_pos[0] += (tx - self.cam_pos[0]) * min(1, dt * snap)
        self.cam_pos[1] += (ty - self.cam_pos[1]) * min(1, dt * snap)
        ox = oy = 0.0
        if self.shake_t > 0:
            self.shake_t -= dt
            ox = random.uniform(-1, 1) * self.shake_mag
            oy = random.uniform(-1, 1) * self.shake_mag
            if self.shake_t <= 0:
                self.shake_mag = 0
        self.camera.position = (self.cam_pos[0] + ox, self.cam_pos[1] + oy)

    def _update_fx(self, dt):
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.9
            p[3] *= 0.9
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for pu in self.popups:
            pu[1] -= dt
            pu[0].y += 28 * dt
        self.popups = [p for p in self.popups if p[1] > 0]
        for r in self.rings:
            r[4] += dt
        self.rings = [r for r in self.rings if r[4] < r[5]]
        self.message_t -= dt

    # ------------------------------------------------------------------ networking: host
    def start_host(self, save=None):
        try:
            self.server = net.Server(self.my_name)
        except OSError as e:
            self.menu_note = f"Couldn't host: {e}"
            return False
        self.net = "host"
        self.start(save)
        self.say(f"Hosting!  Friends on your Wi-Fi: Join -> pick '{self.my_name}'   (IP {net.lan_ip()})", 8)
        return True

    def host_network(self):
        self.pending_conn = getattr(self, "pending_conn", [])
        self.pending_conn += self.server.new_connections()
        for c in list(self.pending_conn):
            for m in c.receive():
                if m.get("t") == "hello":
                    self.pending_conn.remove(c)
                    if len(self.players) >= net.MAX_PLAYERS:
                        c.send({"t": "full"})
                        break
                    name = str(m.get("name", "Friend"))[:12] or "Friend"
                    p = self.add_player(name, conn=c)
                    if self.me and not p.restored:     # a returning survivor stays where they were saved
                        self.set_layer(p, self.me.layer, (self.view_pos()[0] + 40, self.view_pos()[1]))
                    p.tp += 1      # tell their game where they are (and on which layer)
                    c.send({"t": "world", "seed": self.seed, "pid": p.id, "wg": self.worldgen})   # clients rebuild it
                    self.sent_nodes_ver = self.sent_struct_ver = self.sent_storage_ver = -1
                    self.say(f"{name} joined the game!", 3)
                    self.play("craft", 0.3)
                    break
            if not c.alive and c in self.pending_conn:
                self.pending_conn.remove(c)
        for p in list(self.players.values()):
            if p.conn is None:
                continue
            if not p.conn.alive:
                self.say(f"{p.name} left the game.", 3)
                self.remove_player(p)
                continue
            for m in p.conn.receive():
                try:
                    self.host_message(p, m)
                except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
                    pass       # a broken / modified client's message never takes the host down
        self.server.players = len(self.players)

    def host_message(self, p, m):
        t = m.get("t")
        if t == "in":
            size = self.layers[p.layer].size
            x, y = net.num(m.get("x"), None, 0, size), net.num(m.get("y"), None, 0, size)
            if m.get("tp") == p.tp and p.alive and x is not None and y is not None:
                p.sprite.position = (x, y)
            p.face = net.num(m.get("f"), p.face)
            p.move = (net.num(m.get("mx"), 0, -1, 1), net.num(m.get("my"), 0, -1, 1))
            p.resting = bool(m.get("r"))
            p.attacking = bool(m.get("a")) and p.alive and not self.cut
            p.arriving = bool(m.get("ar"))
            p.selected = net.whole(m.get("s"), p.selected, 0, HOTBAR_SLOTS - 1)
        elif t == "act" and self.state == "playing":
            self.do_action(p, m.get("a"), m)

    def do_action(self, p, a, kw):
        if not p.alive:
            return
        if p.resting and a != "assign":   # resting means resting: no building, eating, crafting...
            self.say("You're resting - let go of SHIFT (or X) first.", 1.5, to=p)
            return
        self.fx_layer = p.layer
        try:
            size = self.layers[p.layer].size
            if a == "place":
                p.selected = net.whole(kw.get("s"), p.selected, 0, HOTBAR_SLOTS - 1)
                self.place(p, (net.num(kw["x"], -1e6, -1e6, 1e6), net.num(kw["y"], -1e6, -1e6, 1e6)))
            elif a == "craft":
                self.craft(p, net.whole(kw.get("i"), -1))
            elif a == "use" and kw.get("item") in ITEMS:
                self.consume(p, kw["item"])
            elif a == "quick":
                self.quick_use(p)
            elif a == "interact":
                self.interact(p)
            elif a == "assign" and kw.get("item") in ITEMS:
                s = kw.get("s")
                self.assign_hotbar(p, kw["item"], None if s is None else net.whole(s, p.selected, 0, HOTBAR_SLOTS - 1))
            elif a == "unequip" and kw.get("slot") in ARMOR_SLOTS:
                self.unequip(p, kw["slot"])
            elif a == "deposit" and kw.get("item") in ITEMS:
                self.deposit(p, kw["item"], net.whole(kw.get("n", 1), 0, 0, 10 ** 9))
            elif a == "withdraw" and kw.get("item") in ITEMS:
                self.withdraw(p, kw["item"], net.whole(kw.get("n", 1), 0, 0, 10 ** 9))
            elif a == "tame":
                self.tame(p, net.whole(kw.get("aid"), -1))
            elif a == "pets":
                self.command_pets(p)
            elif a in ("petmode", "petname", "petarmor", "petsall"):
                self.pet_action(p, a, kw)      # pets.py: only ever touches your own pets
            elif a == "throw":
                p.selected = net.whole(kw.get("s"), p.selected, 0, HOTBAR_SLOTS - 1)
                it = p.hotbar[p.selected]
                x, y = net.num(kw.get("x"), None, 0, size), net.num(kw.get("y"), None, 0, size)
                if it and ITEMS[it]["kind"] == "throw" and x is not None and y is not None:
                    self.throw(p, it, x, y)
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            pass

    def send_snapshots(self):
        li = LAYERS.index
        common = {
            "t": "snap", "c": r1(self.clock), "d": self.day, "k": self.kills, "g": self.state,
            "ff": int(self.fast_forward), "cm": self.cold_mult, "dn": list(self.difficulty), "wx": self.weather_net(),
            "bd": [self.boss_day, self.boss_num, int(self.boss_hp is not None)],
            "sh": [[s.kind, r1(s.x), r1(s.y), r1(s.vx), r1(s.vy), round(s.t, 2), round(s.T, 2), li(s.layer)]
                   for s in self.shots],
            "p": [[p.id, p.name, r1(p.sprite.center_x), r1(p.sprite.center_y), round(p.face, 2), int(p.health),
                   int(p.alive), p.in_hut.sid if p.in_hut else 0, p.hotbar[p.selected] or "", p.swings, p.kills,
                   li(p.layer)] for p in self.players.values()],
            "z": [[z.zid, z.kind, r1(z.center_x), r1(z.center_y), round(z.heading, 2), int(z.flash > 0) +
                   2 * int(z.chill > 0), li(z.layer)] for L in self.layers.values() for z in L.zombies],
            "a": [[a.aid, a.kind, r1(a.center_x), r1(a.center_y), round(a.heading, 2), int(a.flash > 0), a.owner,
                   PET_MODES.index(a.mode), int(a.carrying > 0), a.name, a.armor or "", r1(a.hp), a.max_hp]
                  for a in self.over.animals],
            "b": [[b.bid, b.kind, r1(b.center_x), r1(b.center_y), round(b.heading, 2), int(b.hp), int(b.max_hp),
                   int(b.flash > 0), b.alpha] for b in self.over.bosses],
            "hz": [[h.kind, r1(h.x), r1(h.y), h.r, r1(h.t), r1(h.tele), round(h.a, 2), h.ln, r1(h.vx), r1(h.vy)]
                   for h in self.hazards],
            "ev": self.events_all,
        }
        if self.nodes_ver != self.sent_nodes_ver:
            common["n"] = "".join(NODE_CODE[n.state] for n in self.nodes)
            moves = self.node_moves_rows(force=self.sent_nodes_ver == -1)   # base.py: nodes that grew elsewhere
            if moves is not None:
                common["nm"] = moves
            self.sent_nodes_ver = self.nodes_ver
        if self.struct_ver != self.sent_struct_ver:
            common["st"] = [[s.sid, s.kind, s.center_x, s.center_y, round(s.hp, 1), li(s.layer), int(s.lit)]
                            for s in self.structs.values()]
            self.sent_struct_ver = self.struct_ver
        if self.storage_ver != self.sent_storage_ver:
            common["sto"] = self.storage
            self.sent_storage_ver = self.storage_ver
        common["eq"] = {str(p.id): [p.equip.get(s) or "" for s in ARMOR_SLOTS] for p in self.players.values()}
        self.events_all = []
        for p in self.players.values():
            if not p.conn:
                continue
            msg = dict(common)
            msg["you"] = {"inv": p.inv, "hb": p.hotbar, "eq": p.equip, "h": r1(p.health), "hu": r1(p.hunger),
                          "th": r1(p.thirst), "en": r1(p.energy), "wa": r1(p.warmth), "tp": p.tp,
                          "x": r1(p.sprite.center_x), "y": r1(p.sprite.center_y), "ly": li(p.layer),
                          "hurt": r1(p.hurt), "rs": r1(p.respawn_t)}
            msg["pev"] = p.events
            p.events = []
            big = any(k in msg for k in ("n", "st", "sto")) or msg["ev"] or msg["pev"]
            p.conn.send(msg, droppable=not big)

    # ------------------------------------------------------------------ networking: client
    def start_join(self, ip):
        ip = ip.strip()
        if not ip:
            self.menu_note = "Type the host's IP address first."
            return
        self.cfg["last_ip"] = ip
        save_config(self.cfg)
        self.menu_note = f"Connecting to {ip}..."
        self.joiner = net.Joiner(ip)

    def update_menu(self):
        j = self.joiner
        if j and j.done:
            self.joiner = None
            if j.error:
                self.menu_note = f"Couldn't connect ({j.error}). Is the host's game running?"
                return
            self.conn = j.conn
            self.net = "client"
            self.conn.send({"t": "hello", "name": self.my_name})
            self.menu_note = "Connected - loading world..."

    def client_network(self, dt):
        c = self.conn
        if not c.alive:
            self.leave_game("Lost connection to the host.")
            return
        for m in c.receive():
            t = m.get("t")
            if t == "full":
                self.leave_game("That game is full (4 players max).")
                return
            if t == "world":
                note = self.menu_note
                self.setup(int(m["seed"]), int(m.get("wg", biomes.LEGACY)))   # an older host: the legacy map
                self.my_pid = int(m["pid"])
                self.state = "playing"
                self.menu_note = note
                self.say("Joined! Stick together - zombies come at night.", 5)
                self.intro = intro.Intro(self.my_name, "join", intro.SUBJECT + max(1, self.my_pid))
            elif t == "snap":
                self.apply_snapshot(m)

    def apply_snapshot(self, m):
        if abs(self.clock - m["c"]) > 0.5:
            self.clock = m["c"]
        else:
            self.clock += (m["c"] - self.clock) * 0.3
        self.day, self.kills = m["d"], m["k"]
        self.fast_forward = bool(m.get("ff"))
        self.cold_mult = m.get("cm", 1.0)
        self.weather_apply(m.get("wx"))
        if "dn" in m:
            self.difficulty = tuple(m["dn"])
        if "bd" in m:
            self.boss_day, self.boss_num = m["bd"][0], m["bd"][1]
            self.boss_hp = 1 if m["bd"][2] else None
        self.shots = []
        for kind, x, y, vx, vy, t, T, ly in m.get("sh", []):
            s = Shot(kind, x, y, vx, vy, T, layer=LAYERS[ly])
            s.t = t
            self.shots.append(s)
        if "nm" in m:
            self.apply_node_moves(m["nm"])     # base.py: before the states, so regrown trees get the right look
        if "n" in m:
            for n, ch in zip(self.nodes, m["n"]):
                self.set_node_state(n, CODE_NODE.get(ch, "full"))
        if "st" in m:
            seen = set()
            for sid, kind, x, y, hp, ly, lit in m["st"]:
                seen.add(sid)
                s = self.structs.get(sid)
                if s is None:
                    s = self.add_structure(kind, x, y, sid, LAYERS[ly])
                if hp < s.hp:
                    s.flash = 0.15
                s.hp = hp
                self.set_fire(s, bool(lit))
            for sid in [k for k in self.structs if k not in seen]:
                self.remove_structure(self.structs[sid])
        if "sto" in m:
            self.storage = m["sto"]
        seen = set()
        for pid, name, x, y, face, hp, alive, hut, held, swings, kills, ly in m["p"]:
            seen.add(pid)
            p = self.players.get(pid)
            if p is None:
                p = self.add_player(name, pid=pid)
                p.sprite.position = (x, y)
                if pid == self.my_pid:
                    self.me = p
            p.alive = bool(alive)
            p.in_hut = self.structs.get(hut)
            p.kills = kills
            if p is not self.me:
                p.layer = LAYERS[ly]
                p.target = (x, y)
                if dist(p.sprite.position, (x, y)) > 400:
                    p.sprite.position = (x, y)
                p.face = face
                p.health = hp
                p.hotbar = [held or None] + [None] * (HOTBAR_SLOTS - 1)
                p.selected = 0
            if swings != self.seen_swings.get(pid, swings):
                p.swing = 0.2
            self.seen_swings[pid] = swings
        for pid in [k for k in self.players if k not in seen]:
            self.remove_player(self.players[pid])
        for pid, eq in m.get("eq", {}).items():    # what everyone else is wearing
            other = self.players.get(int(pid))
            if other is not None and other is not self.me:
                other.equip = {s: (e or None) for s, e in zip(ARMOR_SLOTS, eq)}
        me = self.me
        if me and "you" in m:
            y = m["you"]
            me.inv = y["inv"]
            me.hotbar = y["hb"]
            me.equip = y["eq"]
            if y["h"] < self.last_my_health - 0.5 and y["hurt"] > 0:
                me.hurt = 0.35
            self.last_my_health = me.health = y["h"]
            me.hunger, me.thirst, me.energy, me.warmth = y["hu"], y["th"], y["en"], y["wa"]
            me.respawn_t = y["rs"]
            if y["tp"] != me.tp:
                me.tp = y["tp"]
                self.set_layer(me, LAYERS[y["ly"]], (y["x"], y["y"]))
        self._sync_list(m["z"], self.zmap, self._mk_zombie, self._rm_zombie)
        self._sync_list(m["a"], self.amap, self._mk_animal, lambda a: a.remove_from_sprite_lists())
        self._sync_list(m["b"], self.bmap, self._mk_boss, lambda b: b.remove_from_sprite_lists())
        for row in m["z"]:
            z = self.zmap[row[0]]
            z.target, z.heading = (row[2], row[3]), row[4]
            if row[5] & 1:
                z.flash = 0.12
            z.chill = 1.0 if row[5] & 2 else 0.0
        for row in m["a"]:
            a = self.amap[row[0]]
            a.target, a.heading = (row[2], row[3]), row[4]
            if row[5]:
                a.flash = 0.12
            a.owner, a.mode = row[6], PET_MODES[row[7]]
            a.carry = {"x": 1} if row[8] else {}
            if len(row) > 12:
                a.name, a.armor, a.hp, a.max_hp = row[9], row[10] or None, row[11], row[12]
        for row in m["b"]:
            b = self.bmap[row[0]]
            b.target, b.heading, b.hp, b.max_hp = (row[2], row[3]), row[4], row[5], row[6]
            if row[7]:
                b.flash = 0.12
            b.alpha = row[8]
        self.hazards = [Hazard(kind, x, y, r, tele=tele, life=t, a=a, ln=ln, vx=vx, vy=vy)
                        for kind, x, y, r, t, tele, a, ln, vx, vy in m["hz"]]
        for ev in m.get("ev", []) + m.get("pev", []):
            self.apply_event(ev)

    def _sync_list(self, rows, table, make, remove):
        seen = set()
        for row in rows:
            seen.add(row[0])
            if row[0] not in table:
                table[row[0]] = make(row)
        for k in [k for k in table if k not in seen]:
            remove(table.pop(k))

    def _mk_zombie(self, row):
        z = Zombie(row[1], row[2], row[3], row[0], LAYERS[row[6]])
        self.add_zombie(z)
        return z

    def _rm_zombie(self, z):
        if z.eye:
            z.eye.remove_from_sprite_lists()
        z.remove_from_sprite_lists()

    def _mk_animal(self, row):
        a = Animal(row[1], row[2], row[3], row[0])
        self.over.animals.append(a)
        return a

    def _mk_boss(self, row):
        b = Boss(row[1], row[2], row[3], row[0])
        self.over.bosses.append(b)
        return b

    def _client_visuals(self, dt):
        for s in self.shots:           # keep arrows & pots moving between snapshots
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.t = min(s.T, s.t + dt)
        k = min(1.0, dt * 14)
        for L in self.layers.values():
            for z in L.zombies:
                z.center_x += (z.target[0] - z.center_x) * k
                z.center_y += (z.target[1] - z.center_y) * k
                z.wobble += dt * 9
                z.angle = -math.degrees(z.heading) + math.sin(z.wobble) * 7
                z.flash = max(0, z.flash - dt)
        for a in self.over.animals:
            a.center_x += (a.target[0] - a.center_x) * k
            a.center_y += (a.target[1] - a.center_y) * k
            a.angle = -math.degrees(a.heading)
            a.flash = max(0, a.flash - dt)
        for b in self.over.bosses:
            b.center_x += (b.target[0] - b.center_x) * k
            b.center_y += (b.target[1] - b.center_y) * k
            b.wobble += dt * 4
            b.angle = -math.degrees(b.heading) + math.sin(b.wobble) * 3
            b.flash = max(0, b.flash - dt)
        for h in self.hazards:
            if h.tele > 0:
                h.tele -= dt
            else:
                h.x += h.vx * dt
                h.y += h.vy * dt
                h.t -= dt
        for p in self.players.values():
            if p is not self.me:
                p.sprite.center_x += (p.target[0] - p.sprite.center_x) * k
                p.sprite.center_y += (p.target[1] - p.sprite.center_y) * k
            p.swing = max(0, p.swing - dt)
        if self.me:
            self.me.hurt = max(0, self.me.hurt - dt)

    def send_input(self):
        me = self.me
        if not me or not self.conn:
            return
        self.conn.send({"t": "in", "x": r1(me.sprite.center_x), "y": r1(me.sprite.center_y), "f": round(me.face, 3),
                        "mx": round(me.move[0], 2), "my": round(me.move[1], 2), "r": int(me.resting),
                        "a": int(me.attacking), "s": me.selected, "tp": me.tp, "ar": int(bool(self.intro))},
                       droppable=True)

    def action(self, a, **kw):
        """Do something to my survivor: run it here (solo/host) or ask the host (client)."""
        if not self.me or self.state != "playing":
            return
        if self.net == "client":
            kw.update(t="act", a=a)
            self.conn.send(kw)
            return
        self.do_action(self.me, a, kw)

    def leave_game(self, note=""):
        summary = self.run_summary()      # progress.py: grab the stats before the world goes
        self.save_on_exit()       # autosave on the way out
        self.local_end()
        if self.conn:
            self.conn.close()
        if self.server:
            self.server.close()
        self.conn = self.server = None
        self.net = None
        self.state = "title"
        self.menu = "main"
        self.menu_note = note
        self.setup(random.randrange(1 << 30))
        self.show_summary(summary)

    # ------------------------------------------------------------------ starting
    def start(self, save=None):
        """Start a game: a brand new one, or (with `save`) a saved one picked on the title screen."""
        if save:     # saves from before worldgen versions have no "worldgen": the legacy map, exactly
            self.setup(save["seed"], int(save.get("worldgen", biomes.LEGACY)))
        else:
            self.setup(random.randrange(1 << 30))
        self.away = {}
        self.save_path = None
        if save:
            self.load_world(save)          # savegame.py
            self.save_path = save.get("_path")
        else:
            self.difficulty = self.chosen_difficulty()
            self.boss_day = self.boss_gap
        self.me = self.add_player(self.my_name)
        self.host_ip = net.lan_ip()
        if save:
            self.intro = None
            self.state = "playing"
            self.say(f"Welcome back - Day {self.day}.  ({self.difficulty[0]}: {self.difficulty[1]}s day, "
                     f"{self.difficulty[2]}s night, a boss every {self.boss_gap} nights)", 5)
            if self.net == "host":
                self.say(f"Hosting your saved game! Friends: Join -> pick '{self.my_name}'. "
                         "Use the same name as last time to get your stuff back.", 8)
        # Solo: state "intro" pauses the world while the cutscene plays.
        # Host: the world must keep running for joiners, so the cutscene is an overlay and state stays "playing".
        elif self.net is None:
            self.intro = intro.Intro(self.my_name)
            self.state = "intro"
        else:
            self.intro = intro.Intro(self.my_name, "host")
            self.state = "playing"
        for _ in range(self.animal_cap // 2):
            self.spawn_animal()

    def end_intro(self):
        self.intro = None
        self.keys.clear()
        self.mouse_down = False
        self.state = "playing"

    def on_draw(self):
        if self.local and self.state == "playing":
            self.local_draw()
            return
        if self.intro and self.state in ("intro", "playing"):
            self.clear(color=(0, 0, 0))
            self.gui.use()
            self.intro.draw(self)
            return
        super().on_draw()

    # ------------------------------------------------------------------ input
    def on_key_press(self, key, modifiers):
        if key == arcade.key.F11 or (key == arcade.key.F and modifiers & (arcade.key.MOD_COMMAND | arcade.key.MOD_CTRL)):
            self.toggle_fullscreen()      # F11, or Cmd+F / Ctrl+F
            return
        self.keys.add(key)
        if self.state == "title" and self.menu == "local":
            self.lobby_key(key)
            return
        if self.local and self.state == "playing" and not self.local_key(key):
            return
        if self.rename_key(key):          # typing a pet's name (pets.py)
            self.keys.discard(key)
            return
        self.use_pad = False
        if self.state == "title":
            self.title_key(key, modifiers)
            return
        if self.intro:
            self.keys.discard(key)     # no movement keys leak into the game while watching
            if key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.SPACE, arcade.key.ESCAPE):
                self.intro.skip()
            return
        if self.cut:
            if key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.SPACE, arcade.key.ESCAPE):
                self.skip_cutscene()
            return
        if self.paused and key == arcade.key.Q:
            self.leave_game()
            return
        if self.paused and key == arcade.key.S:
            self.save_game(manual=True)
            return
        if key == arcade.key.ESCAPE:
            if self.ui_open:
                self.ui_open = None
            else:
                self.paused = not self.paused
            return
        if self.ui_scroll_key(key):        # ui.py: UP / DOWN / PAGE keys scroll crafting & pets
            return
        if self.ui_open == "inv" and key in (arcade.key.LEFT, arcade.key.RIGHT):
            self.craft_tab = (self.craft_tab + (1 if key == arcade.key.RIGHT else -1)) % len(CRAFT_TABS)
            return
        if self.ui_open == "storage" and arcade.key.KEY_1 <= key <= arcade.key.KEY_4:
            self.move_amount = key - arcade.key.KEY_1
            return
        if key == arcade.key.P:
            self.toggle_pets()
            return
        if key in (arcade.key.TAB, arcade.key.I):
            self.ui_open = None if self.ui_open == "inv" else "inv"
            self.mouse_down = False
        elif arcade.key.KEY_1 <= key <= arcade.key.KEY_8 and self.me:
            self.me.selected = key - arcade.key.KEY_1
        elif key == arcade.key.Q:
            self.action("quick")
        elif key == arcade.key.E:
            self.interact_key()
        elif key == arcade.key.F:
            self.action("pets")
        elif key == arcade.key.V:
            self.fp_toggle()             # firstperson.py

    def interact_key(self):
        me = self.me
        if not me or not me.alive:
            return
        if self.ui_open == "storage":
            self.ui_open = None
        elif self.near_storage(me):
            self.ui_open = "storage"
            self.mouse_down = False
        else:
            self.action("interact")

    def skip_cutscene(self):
        if self.net == "client":
            self.cut = None
        else:
            self.end_cutscene()

    def title_key(self, key, modifiers):
        items = self.menu_items()
        if self.menu == "diff" and key in (arcade.key.LEFT, arcade.key.RIGHT, arcade.key.A, arcade.key.D):
            step = 30 if modifiers & arcade.key.MOD_SHIFT else 5
            self.diff_adjust(self.menu_sel, step if key in (arcade.key.RIGHT, arcade.key.D) else -step)
            return
        if key == arcade.key.ESCAPE and self.menu in ("diff", "load", "save", "confirm", "ach", "summary"):
            self.menu_back()
            return
        if self.menu == "load" and key in (arcade.key.DELETE, arcade.key.BACKSPACE):
            self.delete_highlighted()
            return
        if key in (arcade.key.UP, arcade.key.W) and not (self.menu == "join" and key == arcade.key.W):
            self.menu_sel = (self.menu_sel - 1) % len(items)
        elif key in (arcade.key.DOWN, arcade.key.S) and not (self.menu == "join" and key == arcade.key.S):
            self.menu_sel = (self.menu_sel + 1) % len(items)
        elif key in (arcade.key.ENTER, arcade.key.RETURN):
            self.menu_pick(self.menu_sel)
        elif key == arcade.key.SPACE and self.menu == "main":
            self.menu_pick(self.menu_sel)
        elif key == arcade.key.ESCAPE and self.menu == "join":
            self.menu, self.menu_sel, self.menu_note = "main", 2, ""
        elif self.menu == "join":
            if key == arcade.key.BACKSPACE:
                self.ip_text = self.ip_text[:-1]
            else:
                ch = None
                if arcade.key.KEY_0 <= key <= arcade.key.KEY_9:
                    ch = chr(ord("0") + key - arcade.key.KEY_0)
                elif arcade.key.NUM_0 <= key <= arcade.key.NUM_9:
                    ch = chr(ord("0") + key - arcade.key.NUM_0)
                elif key in (arcade.key.PERIOD, arcade.key.NUM_DECIMAL):
                    ch = "."
                elif arcade.key.A <= key <= arcade.key.Z:
                    ch = chr(key)
                elif key == arcade.key.MINUS:
                    ch = "-"
                if ch and len(self.ip_text) < 40:
                    self.ip_text += ch
                    self.menu_sel = len(items) - 2

    def on_text(self, text):
        self.rename_text_in(text)         # letters typed into a pet's name

    def on_key_release(self, key, modifiers):
        self.keys.discard(key)

    def on_mouse_motion(self, x, y, dx, dy):
        if self.fp_mouse(dx, dy):          # firstperson.py: mouse looks around
            self.use_pad = False
            return
        x, y = self.to_layout(x, y)      # fullscreen: undo the scaling (options.py)
        self.mouse_screen = (x, y)
        if abs(dx) + abs(dy) > 2:
            self.use_pad = False
        if self.state == "title":
            for i, (_, (l, r, b, t)) in enumerate(self.menu_rows()):
                if l < x < r and b < y < t:
                    self.menu_sel = i

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.fp_mouse(dx, dy):          # firstperson.py: keep looking while you hold attack
            return
        self.mouse_screen = self.to_layout(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        x, y = self.to_layout(x, y)
        self.mouse_screen = (x, y)
        if self.state == "title" and self.menu == "local":
            self.lobby_click(x, y)
            return
        if self.local and self.state == "playing" and not self.local_mouse():
            return
        self.use_pad = False
        if self.intro:
            return
        self.click(x, y, button, modifiers)

    def click(self, x, y, button, modifiers=0):
        if self.state == "title":
            for i, (_, (l, r, b, t)) in enumerate(self.menu_rows()):
                if l < x < r and b < y < t:
                    self.menu_pick(i, x)
            return
        if self.cut:
            self.skip_cutscene()
            return
        if self.state != "playing" or self.paused or not self.me:
            return
        if self.ui_open == "inv":
            self.click_inventory(x, y, button)
            return
        if self.ui_open == "storage":
            self.click_storage(x, y, button, modifiers)
            return
        if self.ui_open == "pets":
            self.click_pets(x, y)
            return
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_down = True
        elif button == arcade.MOUSE_BUTTON_RIGHT:
            self.use_selected()

    def tame_target(self):
        """A wild animal near where I'm aiming that wants the food I'm holding."""
        me = self.me
        sel = me.hotbar[me.selected]
        if me.layer != "over" or not sel:
            return None
        ax, ay = self.aim_world()
        best = None
        for a in self.over.animals:
            if a.pet or a.info["tame"] != sel:
                continue
            if dist(a.position, me.pos) < 110 and (dist(a.position, (ax, ay)) < 90 or dist(a.position, me.pos) < 70):
                if best is None or dist(a.position, me.pos) < dist(best.position, me.pos):
                    best = a
        return best

    def use_selected(self):
        sel = self.me.hotbar[self.me.selected]
        if not sel:
            return
        kind = ITEMS[sel]["kind"]
        t = self.tame_target()
        if t:
            self.action("tame", aid=t.aid)
        elif kind == "build":
            tx, ty = self.aim_world()
            self.action("place", x=tx, y=ty, s=self.me.selected)
        elif kind == "food":
            self.action("use", item=sel)
        elif kind == "throw":
            me = self.me
            if self.use_pad:      # controller: throw it a good way in front of you
                tx, ty = me.pos[0] + math.cos(me.face) * 260, me.pos[1] + math.sin(me.face) * 260
            else:
                tx, ty = self.aim_world()
            self.action("throw", x=tx, y=ty, s=me.selected)

    def on_mouse_release(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_down = False

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if self.local and self.state == "playing" and not self.local_mouse():
            return
        if self.state == "playing" and not self.ui_open and self.me and scroll_y:
            self.me.selected = (self.me.selected - int(math.copysign(1, scroll_y))) % HOTBAR_SLOTS
        elif self.state == "playing" and self.ui_open and scroll_y:
            self.ui_scroll(-int(math.copysign(1, scroll_y)))     # ui.py: scroll the crafting / pets list

    # --- controller
    def handle_pad(self, dt):
        pad = self.pad
        if pad.connected != self.pad_was:
            if pad.connected and self.pad_was is not None:
                self.message, self.message_t = f"Controller connected: {pad.name}", 3
                self.use_pad = True
            elif not pad.connected and self.pad_was:
                self.message, self.message_t = "Controller disconnected.", 3
                self.use_pad = False
            self.pad_was = pad.connected
        if not pad.connected:
            return
        if pad.active:
            if not self.use_pad and self.ui_open:
                self.mouse_screen = (W / 2, H / 2)
            self.use_pad = True
        pr = pad.pressed
        if self.intro:
            if "a" in pr or "start" in pr or "b" in pr:
                self.intro.skip()
            return
        if self.state == "title":
            if self.menu == "local":
                return            # the lobby reads each controller itself (local_coop.lobby_pad)
            if self.menu == "join" and self.joiner is None and "b" in pr:
                self.menu, self.menu_sel, self.menu_note = "main", 2, ""
                return
            items = self.menu_items()
            if "dpup" in pr:
                self.menu_sel = (self.menu_sel - 1) % len(items)
            if "dpdown" in pr:
                self.menu_sel = (self.menu_sel + 1) % len(items)
            ly = pad.left[1]
            self._stick_t = getattr(self, "_stick_t", 0) - dt
            if abs(ly) > 0.6 and self._stick_t <= 0:
                self.menu_sel = (self.menu_sel + (1 if ly < 0 else -1)) % len(items)
                self._stick_t = 0.25
            elif abs(ly) < 0.3:
                self._stick_t = 0
            if self.menu == "diff":
                lx = pad.left[0]
                self._stick_x = getattr(self, "_stick_x", 0) - dt
                if "dpright" in pr or (lx > 0.6 and self._stick_x <= 0):
                    self.diff_adjust(self.menu_sel, 5)
                    self._stick_x = 0.2
                elif "dpleft" in pr or (lx < -0.6 and self._stick_x <= 0):
                    self.diff_adjust(self.menu_sel, -5)
                    self._stick_x = 0.2
                elif abs(lx) < 0.3:
                    self._stick_x = 0
            if "b" in pr and self.menu in ("diff", "load", "save", "confirm", "ach", "summary"):
                self.menu_back()
                return
            if "x" in pr and self.menu == "load":
                self.delete_highlighted()
                return
            if "a" in pr or "start" in pr:
                self.menu_pick(self.menu_sel)
            return
        if self.cut:
            if "a" in pr or "start" in pr or "b" in pr:
                self.skip_cutscene()
            return
        if self.paused:
            if "start" in pr or "b" in pr:
                self.paused = False
            elif "back" in pr:
                self.leave_game()
            elif "x" in pr:
                self.save_game(manual=True)
            return
        if self.rename_pad(pr):            # pets.py: controller typing a pet's name
            return
        if "start" in pr:
            self.paused = True
            return
        if "rightstick" in pr:
            self.fp_toggle()             # firstperson.py
        me = self.me
        if not me:
            return
        if "leftshoulder" in pr or (not self.ui_open and "dpleft" in pr):
            me.selected = (me.selected - 1) % HOTBAR_SLOTS
        if "rightshoulder" in pr or (not self.ui_open and "dpright" in pr):
            me.selected = (me.selected + 1) % HOTBAR_SLOTS
        if self.ui_open:
            mx, my = self.mouse_screen
            vx, vy = pad.left
            vx += ("dpright" in pad.down) - ("dpleft" in pad.down)
            vy += ("dpup" in pad.down) - ("dpdown" in pad.down)
            mx = max(0, min(W, mx + vx * 700 * dt))
            my = max(0, min(H, my + vy * 700 * dt))
            self.mouse_screen = (mx, my)
            if "a" in pr:
                self.click(mx, my, arcade.MOUSE_BUTTON_LEFT)
            self.ui_scroll_pad(pad, dt)      # ui.py: right stick scrolls long lists
            if self.ui_open == "inv":
                if "lt" in pr:
                    self.craft_tab = (self.craft_tab - 1) % len(CRAFT_TABS)
                if "rt" in pr:
                    self.craft_tab = (self.craft_tab + 1) % len(CRAFT_TABS)
            if self.ui_open == "storage" and "x" in pr:
                self.move_amount = (self.move_amount + 1) % len(ui.AMOUNTS)
            if "y" in pr or "b" in pr or "back" in pr:
                self.ui_open = None
            return
        if "dpup" in pr:
            self.toggle_pets(True)
            return
        if "y" in pr or "back" in pr:
            self.ui_open = "inv"
            self.mouse_down = False
            self.mouse_screen = (W / 2, H / 2)
            return
        if "lt" in pr:
            self.use_selected()
        if "dpdown" in pr:
            self.action("pets")
        if "b" in pr:
            if self.near_storage(me) or self.near_exit(me) or self.near_pond(me):
                self.interact_key()
            else:
                self.action("quick")


def main():
    args = sys.argv[1:]
    if "--export-art" in args:
        LastLight()
        for name in ITEMS:
            art.icon(name)
        for k in ("walker", "runner", "brute"):
            art.zombie(k)
        for i in range(4):
            art.player(i)
        art_extra.all_new_textures()
        art_bees.all_textures()
        art_defenses.all_textures()
        swamp.art_swamp.all_textures()
        art.save_all(os.path.join(HERE, "art_export"))
        print("Saved every texture to the art_export/ folder.")
        return
    game = LastLight()
    if game.cfg.get("fullscreen"):
        game.set_fullscreen(True)
    if "--name" in args and args.index("--name") + 1 < len(args):
        game.my_name = args[args.index("--name") + 1][:12]
        game.cfg["name"] = game.my_name
        save_config(game.cfg)
    if "--host" in args:
        game.start_host()
    elif "--join" in args:
        i = args.index("--join")
        ip = args[i + 1] if i + 1 < len(args) else "127.0.0.1"
        game.ip_text = ip
        game.start_join(ip)
    game.run()


if __name__ == "__main__":
    main()
