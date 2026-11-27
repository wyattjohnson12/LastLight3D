"""
test_explore.py - places to discover (explore.py): placement, loot, recipe discovery, saves and co-op sync.

    python3 test_explore.py

  1. Places are the same every time a seed is built, sit in the right biomes, keep clear of the spawn, the
     region centres (boss lairs), rivers / cliffs / bog pools and each other, stand on land the spawn can reach,
     and a survivor can walk from outside right up to every container (props never wall it in).
  2. Every locked recipe is findable in at least 2 places of every world; legacy worlds have no places and know
     every recipe.
  3. Searching a container gives loot once (the second time: nothing), teaches its recipes, and an unknown
     recipe can't be crafted until then.
  4. Saves keep what was searched, found and learned; saves from before places existed know every recipe.
  5. Co-op: a joining player is sent the state, and a client applying it sees the same opened containers and
     known recipes.
"""
import json
import math
import random
from collections import deque

import arcade

import biomes
import explore
import main
import terrain_map as TM


class FakeConn:
    alive = True

    def __init__(self):
        self.sent = []

    def send(self, msg, droppable=False):
        self.sent.append(json.loads(json.dumps(msg)))

    def receive(self):
        return []


def places(g):
    return explore._st(g).places


def fingerprint(g):
    return [(pl.pid, pl.layer, round(pl.x, 2), round(pl.y, 2), round(pl.angle, 4), pl.notes) for pl in places(g)]


def can_walk_to_box(g, pl):
    """A 26 px survivor can walk from the edge of the place to within reach of its container."""
    L = g.layers[pl.layer]
    step, R = 14, 230
    n = 2 * R // step + 1
    x0, y0 = pl.x - R, pl.y - R
    probe = arcade.SpriteSolidColor(26, 26, center_x=0, center_y=0)

    def free(i, j):
        probe.position = (x0 + i * step, y0 + j * step)
        return not arcade.check_for_collision_with_lists(probe, [L.solid, L.huts])

    seen = set()
    q = deque()
    for i in range(n):
        for j in (0, n - 1):
            for a, b in ((i, j), (j, i)):
                if (a, b) not in seen and free(a, b):
                    seen.add((a, b))
                    q.append((a, b))
    bx, by = pl.box.position
    while q:
        i, j = q.popleft()
        if math.hypot(x0 + i * step - bx, y0 + j * step - by) < explore.OPEN_RANGE - 12:
            return True
        for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= a < n and 0 <= b < n and (a, b) not in seen and free(a, b):
                seen.add((a, b))
                q.append((a, b))
    return False


def main_test():
    g = main.LastLight()
    g.set_visible(False)

    # ---- 1 + 2. placement
    for seed in (5, 31337, 77):
        g.setup(seed)
        a = fingerprint(g)
        g.setup(seed)
        assert fingerprint(g) == a, f"seed {seed}: places aren't deterministic"
        st = explore._st(g)
        ps = places(g)
        assert len(ps) >= 20, f"seed {seed}: only {len(ps)} places"
        lay = g.layout
        m = TM.get(lay)
        seen = m.flood(lay.centre)
        for pl in ps:
            if pl.layer == "over":
                assert g.biome_at(pl.pos) in [b for b, _ in pl.type.where], f"{pl.pid} in the wrong biome"
                assert math.hypot(pl.x - lay.centre[0], pl.y - lay.centre[1]) >= pl.type.min_dist
                for name, c in lay.centres.items():
                    assert name == "forest" or math.hypot(pl.x - c[0], pl.y - c[1]) >= explore.LAIR_CLEAR
                for k in range(12):
                    ang = k * math.tau / 12
                    for r in (0, pl.type.radius * 0.5, pl.type.radius):
                        x, y = pl.x + math.cos(ang) * r, pl.y + math.sin(ang) * r
                        assert not g.terrain_blocked(x, y) and not g.terrain_water(x, y), f"{pl.pid} on water / cliff"
                        assert not g.in_bog_pool((x, y)), f"{pl.pid} in a bog pool"
                i, j = int(pl.x // TM.C), int(pl.y // TM.C)
                assert seen[j * m.N + i], f"{pl.pid} can't be reached from the spawn"
            for other in ps:
                if other is not pl and other.layer == pl.layer:
                    assert math.hypot(pl.x - other.x, pl.y - other.y) >= 380, f"{pl.pid} overlaps {other.pid}"
            assert can_walk_to_box(g, pl), f"seed {seed}: {pl.pid}'s container is walled in"
        for rec in explore.LOCKED_ORDER:
            n = sum(rec in pl.notes for pl in ps)
            assert rec in st.locked and n >= explore.MIN_COPIES, f"seed {seed}: {rec} only in {n} places"
        types = {pl.type.key for pl in ps}
        assert len(types) >= 6, f"seed {seed}: only {types}"
        assert any(pl.layer == "cave" for pl in ps), "a miner's camp underground"
    print(f"1. places deterministic, in their biomes, clear of water / cliffs / lairs, reachable ({len(ps)} places)")
    print(f"2. every locked recipe is in >= {explore.MIN_COPIES} places")

    g.setup(12345, biomes.LEGACY)
    assert explore._st(g) is None and all(explore.known(g, r) for r in main.RECIPES), "legacy: everything known"

    # ---- 3. searching
    random.seed(3)
    g.net = None
    g.players.clear()
    g.start()
    g.state, g.intro = "playing", None
    me = g.me
    st = explore._st(g)
    rec = next(r for r in main.RECIPES if r["item"] == "iron_pickaxe")
    assert not explore.known(g, rec) and not g.can_craft(me, rec), "the Iron Pickaxe starts unknown"
    me.inv.update({"wood": 10, "iron_ingot": 10})
    g.add_structure("workbench", me.pos[0] + 60, me.pos[1])
    assert not g.can_craft(me, rec)
    g.craft(me, main.RECIPES.index(rec))
    assert "iron_pickaxe" not in me.inv, "can't craft an unknown recipe"
    pl = next(p for p in st.places if "iron_pickaxe" in p.notes and p.layer == "over")
    bx, by = pl.box.position
    g.set_layer(me, "over", (bx + 40, by))
    for _ in range(20):
        g.on_update(1 / 30)
    assert pl.found, "walking up to a place finds it"
    before = dict(me.inv)
    g.interact(me)
    assert pl.opened and "iron_pickaxe" in st.known and explore.known(g, rec)
    got = {k: v - before.get(k, 0) for k, v in me.inv.items() if v != before.get(k, 0)}
    assert got and all(v > 0 for v in got.values()), "searching gives loot"
    assert pl.box.kind == pl.type.box[1], "the container looks opened"
    after = dict(me.inv)
    g.interact(me)
    assert me.inv == after, "a container only gives its loot once"
    me.inv.update({"wood": 10, "iron_ingot": 10})
    me.alive = True
    g.set_layer(me, "over", (g.structs[max(g.structs)].position[0] - 60, g.structs[max(g.structs)].position[1]))
    assert g.can_craft(me, rec), "a learned recipe can be crafted"
    print("3. searching gives loot once, teaches the recipe, unknown recipes can't be crafted")

    # ---- 4. saves
    data = json.loads(json.dumps(g.save_data()))
    opened = {p.pid for p in st.places if p.opened}
    found = {p.pid for p in st.places if p.found}
    g.players.clear()
    g.setup(999)
    g.start(save=data)
    st2 = explore._st(g)
    assert {p.pid for p in st2.places if p.opened} == opened and {p.pid for p in st2.places if p.found} == found
    assert "iron_pickaxe" in st2.known and "iron_sword" not in st2.known
    assert st2.by_id[pl.pid].box.kind == pl.type.box[1]
    old = json.loads(json.dumps(data))
    old["biomes"].pop("explore")
    g.players.clear()
    g.start(save=old)
    assert all(explore.known(g, r) for r in main.RECIPES), "an older save knows every recipe"
    print("4. saves keep searched / found / learned; older saves know every recipe")

    # ---- 5. co-op sync
    g.players.clear()
    g.start(save=data)
    g.net = "host"
    friend = g.add_player("Friend", conn=FakeConn())
    explore.update(g, 1.0)
    evs = [ev for ev in friend.events if ev[:3] == ["bio", "explore", "st"]]
    assert evs, "a joining player is sent the places' state"
    ev = evs[-1]
    g.net = None
    g.players.clear()
    g.setup(g.seed, g.worldgen)              # what a client does when it joins: rebuild the world from the seed
    assert not any(p.opened for p in places(g))
    g.apply_event(ev)
    st3 = explore._st(g)
    assert {p.pid for p in st3.places if p.opened} == opened and st3.by_id[pl.pid].box.kind == pl.type.box[1]
    assert explore.known(g, rec) and "iron_sword" not in st3.known
    g.me = g.add_player("Viewer")
    g.state = "playing"
    g.set_layer(g.me, pl.layer, (pl.x, pl.y - 150))
    g.on_draw()
    print("5. co-op: joiners get the state; clients see opened containers and known recipes")
    g.close()
    print("explore checks passed")


if __name__ == "__main__":
    main_test()
