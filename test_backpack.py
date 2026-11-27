"""
test_backpack.py - quick checks for backpack.py (dying drops your backpack) and sprinting.

    python3 test_backpack.py

Backpack: dying drops everything carried + worn at the spot, respawn gives the starting items, only the
owner can pick it up and gets it all back (armor back on), it's gone at the right dawn (die by day: the
next one; die at night: the one after), a second death loses the old pack, zombies hang around it at
night, saves keep it (old saves load fine) and an online client's snapshot carries it.
Sprint: walking costs no energy, sprinting does and is faster, no sprinting with no energy left, and the
host only takes a flag from a client.

Opens (and closes) a small game window, like the game itself does.
"""
import json
import math
import random

import main
import backpack
from settings import (ARMOR_SLOTS, DAWN_START, DAY_CYCLE_SECONDS, DUSK_START, HOTBAR_SLOTS, NIGHT_START,
                      PLAYER_SPEED, SPRINT_MULT, STARTING_ITEMS)

C = DAY_CYCLE_SECONDS


class FakeConn:
    alive = True

    def __init__(self):
        self.sent = []
        self.inbox = []

    def send(self, msg, droppable=False):
        self.sent.append(json.loads(json.dumps(msg)))   # same as going over the wire

    def receive(self):
        out, self.inbox = self.inbox, []
        return out


def fresh(g, save=None):
    random.seed(7)
    g.net = None
    g.start(save=save) if save else g.start()
    g.state, g.intro = "playing", None
    return g


def at_phase(g, phase, day_index=None):
    """Set the clock to `phase` of the current (or given) day cycle."""
    k = int(g.clock // C) if day_index is None else day_index
    g.clock = (k + phase) * C


def tick(g, dt, n=1):
    for _ in range(n):
        g._update_clock(dt)
        g.update_packs(dt)
        for p in list(g.players.values()):
            g._update_survivor(p, dt)


def test_backpack():
    g = main.LastLight()
    fresh(g)
    me = g.me
    for z in [z for L in g.layers.values() for z in L.zombies]:
        z.remove_from_sprite_lists()
    # ---- 1. carrying things and wearing armor, then dying by day
    armor = {s: next(k for k, v in main.ITEMS.items() if v["kind"] == "armor" and v["slot"] == s) for s in ARMOR_SLOTS}
    me.inv = {"wood": 17, "stone": 9, "club": 1, "torch": 1}
    me.hotbar = [None] * HOTBAR_SLOTS
    me.hotbar[3], me.hotbar[5] = "torch", "club"
    for slot, item in armor.items():
        me.equip[slot] = item
    spot = (me.sprite.center_x + 600, me.sprite.center_y)
    me.sprite.position = spot
    at_phase(g, 0.2)
    died_clock = g.clock
    g.down_player(me)
    pk = g.pack_of(me)
    assert pk is not None and (round(pk.x), round(pk.y)) == (round(spot[0]), round(spot[1])), "dropped where you fell"
    assert pk.layer == me.layer == "over"
    assert pk.items == {"wood": 17, "stone": 9, "club": 1, "torch": 1} and pk.armor == armor
    assert pk.count == 28 + len(ARMOR_SLOTS)
    assert me.inv == {} and not any(me.equip.values()), "nothing left on you"
    assert "backpack" in g.message and "before dawn" in g.message, g.message
    assert abs(pk.expires - (math.floor(died_clock / C) + DAWN_START) * C) < 1e-6, "died by day: gone at the next dawn"
    assert pk.sprite in g.pack_lists["over"], "drawn in 3D"

    # ---- 2. respawn with the starting items, at the base
    g.respawn(me)
    assert me.alive and me.inv == dict(STARTING_ITEMS)
    assert "follow the arrow" in g.message

    # ---- 3. only the owner can pick it up
    friend = g.add_player("Friend")      # a second survivor on this machine (like split screen)
    friend.sprite.position = (pk.x, pk.y)
    g.update_packs(0.1)
    assert g.pack_of(me) is pk and pk.num in g.packs, "a teammate walking over it doesn't take it"
    assert g._pack_label(pk)[0].startswith("Your pack")
    g.remove_player(friend)
    # the owner walks onto it: everything back, armor back on, hotbar layout back
    me.hotbar[3] = "berries"             # something else sits in the torch's old slot
    me.sprite.position = (pk.x + 10, pk.y)
    me.equip["head"] = None
    g.update_packs(0.1)
    assert g.pack_of(me) is None and not g.packs, "picked up"
    assert me.inv["wood"] == 17 and me.inv["stone"] == 9 and me.inv["club"] == 1 and me.inv["torch"] == 1
    assert me.inv["berries"] == STARTING_ITEMS["berries"], "the starting things are still there"
    assert me.equip == armor, "armor back on"
    assert me.hotbar[3] == "torch" and me.hotbar[5] == "club" and "berries" in me.hotbar, me.hotbar
    assert pk.sprite not in g.pack_lists["over"]

    # armor goes into the bag when you're already wearing something there
    me.inv = {"wood": 1}
    g.down_player(me)
    g.respawn(me)
    pk = g.pack_of(me)
    other = next(k for k, v in main.ITEMS.items() if v["kind"] == "armor" and v["slot"] == "body" and k != armor["body"])
    me.equip["body"] = other
    me.sprite.position = (pk.x, pk.y)
    assert g.pickup_pack(me, backpack.REACH)
    assert me.equip["body"] == other and me.inv.get(armor["body"]) == 1, "armor in the way: into the backpack"

    # ---- 4. died at night: lasts through the next day, gone at the dawn after
    me.inv = {"stone": 5}
    me.sprite.position = (g.centre[0] + 500, g.centre[1] + 300)
    k = int(g.clock // C) + 1
    at_phase(g, NIGHT_START + 0.05, k)
    g.down_player(me)
    pk = g.pack_of(me)
    assert abs(pk.expires - (k + 1 + DAWN_START) * C) < 1e-6, "night death: the dawn after next"
    assert "one day to get it" in g.message
    left = g.pack_secs_left(pk)
    want = g.secs_until(DAWN_START) + sum(g.day_night)
    assert abs(left - want) < 0.6, (left, want)
    g.clock = (k + DAWN_START) * C - 0.05
    tick(g, 0.1)                         # dawn: back on your feet, the pack is still there
    assert me.alive and g.pack_of(me) is pk
    g.clock = (k + 1 + DAWN_START) * C - 0.05
    me.sprite.position = g.base_spot()
    tick(g, 0.1)                         # the next dawn takes it
    assert g.pack_of(me) is None and not g.packs, "gone at the dawn after"
    assert g.message == "Your backpack is gone.", g.message

    # ---- 5. dying again before you get it back: the old pack is lost for good
    me.inv = {"iron_ore": 3}
    at_phase(g, 0.3)
    g.down_player(me)
    first = g.pack_of(me)
    g.respawn(me)
    me.sprite.position = (first.x + 900, first.y)
    g.down_player(me)
    second = g.pack_of(me)
    assert second is not first and first.num not in g.packs and len(g.packs) == 1, "only one pack each"
    assert second.items == dict(STARTING_ITEMS)
    assert "lost for good" in g.message
    g.respawn(me)

    # ---- 6. at night zombies are drawn to it (only when nobody is near), by day nothing
    for z in [z for L in g.layers.values() for z in L.zombies]:
        z.remove_from_sprite_lists()
    me.sprite.position = (second.x + 1500, second.y)
    at_phase(g, 0.3)
    second.guard_t = 0
    g.update_packs(0.1)
    assert not g.over.zombies, "by day nothing special"
    at_phase(g, NIGHT_START + 0.05)
    for _ in range(4):
        second.guard_t = 0
        g.update_packs(0.1)
    guards = [z for z in g.over.zombies if getattr(z, "pack_guard", None) == second.num]
    assert 1 <= len(guards) <= 3 and all(math.hypot(z.center_x - second.x, z.center_y - second.y) < 120
                                         for z in guards)
    z = guards[0]
    goal = g.pack_loiter(z, me)
    assert goal is not None and math.hypot(goal[0] - second.x, goal[1] - second.y) < backpack.GUARD_RING + 1
    me.sprite.position = (z.center_x + 100, z.center_y)
    assert g.pack_loiter(z, me) is None, "someone close: it chases them"

    # ---- 7. saves keep it; old saves load fine
    me.sprite.position = (second.x + 1500, second.y)
    data = json.loads(json.dumps(g.save_data()))
    assert data["packs"]
    fresh(g, save=data)
    got = g.pack_of(g.me)
    assert got is not None and got.items == second.items and abs(got.expires - second.expires) < 0.01
    assert (round(got.x), round(got.y), got.layer) == (round(second.x), round(second.y), second.layer)
    old = dict(data)
    old.pop("packs")
    fresh(g, save=old)
    assert not g.packs, "an old save has no packs"
    fresh(g, save=data)

    # ---- 8. online: a client's snapshot carries it (not its contents)
    g.net = "host"
    conn = FakeConn()
    pal = g.add_player("Pal", conn=conn)
    pal.inv = {"wood": 4}
    pal.sprite.position = (g.me.sprite.center_x + 200, g.me.sprite.center_y)
    g.down_player(pal)
    g.update_packs(0.01)
    g.send_snapshots()
    snap = conn.sent[-1]
    rows = {r[1]: r for r in snap["bp"]}
    assert pal.id in rows and g.me.id in rows and rows[pal.id][2] == "Pal" and rows[pal.id][6] == 4
    assert "wood" not in json.dumps(snap["bp"])
    seed, pid = g.seed, pal.id
    g.remove_player(pal)
    g.net = None
    g.setup(seed)
    g.net = "client"
    g.my_pid = pid
    g.apply_snapshot(snap)
    mine = g.pack_of(g.me)
    assert mine is not None and mine.name == "Pal" and mine.count == 4 and len(g.packs) == 2
    assert g._pack_label(mine)[0].startswith("Your pack")
    assert any(g._pack_label(p)[0] == f"{p.name}'s pack" for p in g.packs.values() if p is not mine)
    assert len(g.pack_lists["over"]) == 2
    snap2 = dict(snap)
    snap2["bp"] = [r for r in snap["bp"] if r[1] != pid]
    g.apply_snapshot(snap2)
    assert g.pack_of(g.me) is None and len(g.pack_lists["over"]) == 1, "picked up / gone on the host: gone here"
    g.net = None
    g.close()


def test_sprint():
    g = main.LastLight()
    fresh(g)
    me = g.me
    for z in [z for L in g.layers.values() for z in L.zombies]:
        z.remove_from_sprite_lists()
    at_phase(g, 0.25)
    # flat, open ground: no biome / mud / hill speed changes and nothing to bump into
    import arcade
    g.biome_speed = lambda p: 1.0
    g.swamp_speed = lambda p, dt: 1.0
    g.terrain_blocked = lambda *a, **k: False
    me.physics = arcade.PhysicsEngineSimple(me.sprite, walls=[])

    def run(sprint, secs=1.0):
        me.energy = 100.0
        me.move, me.sprinting, me.resting = (1.0, 0.0), sprint, False
        x0 = me.sprite.center_x
        dt = 1 / 30
        for _ in range(int(secs / dt)):
            g.move_player(me, dt)
            g._update_survivor(me, dt)
        return me.sprite.center_x - x0, 100.0 - me.energy

    me.sprite.position = g.centre
    walk, walk_cost = run(False)
    me.sprite.position = g.centre
    sprint, sprint_cost = run(True)
    assert walk_cost < 1e-6, f"walking is free ({walk_cost})"
    assert 2.5 < sprint_cost < 3.5, f"sprinting drains about 3 a second ({sprint_cost})"
    assert sprint > walk * 1.3, (walk, sprint)
    assert abs(sprint / walk - SPRINT_MULT) < 0.2, (walk, sprint)
    # no energy: no sprint, tired walk
    me.sprite.position = g.centre
    me.energy, me.move, me.sprinting = 0.0, (1.0, 0.0), True
    assert not g.sprint_active(me)
    x0 = me.sprite.center_x
    g.move_player(me, 0.1)
    assert me.sprite.center_x - x0 < PLAYER_SPEED * 0.1 * 0.8, "too tired to sprint"
    # standing still with SHIFT rests; moving with SHIFT sprints (keyboard)
    g.keys = {arcade.key.LSHIFT}
    g.use_pad = False
    g.read_local_input()
    assert me.resting and not me.sprinting
    g.keys = {arcade.key.LSHIFT, arcade.key.W}
    g.read_local_input()
    assert me.sprinting and not me.resting
    g.keys = set()
    # online: the host takes the sprint flag and drains energy itself
    g.net = "host"
    conn = FakeConn()
    pal = g.add_player("Pal", conn=conn)
    pal.energy = 50.0
    g.host_message(pal, {"t": "in", "x": pal.sprite.center_x, "y": pal.sprite.center_y, "mx": 1, "my": 0,
                         "sp": 1, "tp": pal.tp, "spd": 9999})
    assert pal.sprinting and g.sprint_active(pal)
    g._update_survivor(pal, 1.0)
    assert 46.5 < pal.energy < 47.5, pal.energy
    g.send_snapshots()
    assert pal.id in conn.sent[-1]["spr"], "clients see who's sprinting (dust)"
    g.host_message(pal, {"t": "in", "mx": 1, "my": 0, "sp": 1, "r": 1, "tp": pal.tp})
    assert not pal.sprinting, "resting and sprinting don't mix"
    g.remove_player(pal)
    g.net = None
    g.close()


if __name__ == "__main__":
    test_backpack()
    test_sprint()
    print("backpack & sprint checks passed: drop on death, owner pick-up, dawn expiry, one pack each, guards, "
          "saves, co-op snapshot, sprint energy & speed")
