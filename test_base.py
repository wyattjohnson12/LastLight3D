"""
test_base.py - quick checks for base.py: used-up nodes never come back in the same spot, nothing grows
inside a base, the Base Flag, saves (new and old) and the co-op snapshot.

    python3 test_base.py

Opens (and closes) a small game window, like the game itself does.
"""
import json
import math
import random

import main
from base import BASE_RADIUS, CLEARED_GAP, FLAG_RADIUS


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class FakeConn:
    alive = True

    def __init__(self):
        self.sent = []

    def send(self, msg, droppable=False):
        self.sent.append(json.loads(json.dumps(msg)))   # same as going over the wire

    def receive(self):
        return []


def fresh(g, seed=12345, save=None):
    random.seed(7)
    g.net = None
    g.start(save=save) if save else g.start()
    g.state, g.intro = "playing", None
    return g


def respawn_all(g, max_steps=4000):
    for item in g.regrow:
        item[0] = 0.0
    steps = 0
    while g.regrow and steps < max_steps:
        g.respawn_try_t = 0.0
        g.update_respawns(0.01)
        for item in g.regrow:
            item[0] = min(item[0], 0.0)
        steps += 1


def main_test():
    g = main.LastLight()
    fresh(g)
    me = g.me
    over = g.over

    # ---- 1. mine out a rock and chop a tree
    rock = next(n for n in over.rocks if n.kind == "rock" and n.state == "full")
    tree = next(n for n in over.trees if n.kind == "tree" and n.state == "full" and n.hive is not None)
    rock_spot, tree_spot = rock.base, tree.base
    while rock.state != "gone":
        g.harvest(rock, 3)
    while tree.state != "stump":
        g.harvest(tree, 3)
    assert rock in [i[1] for i in g.regrow] and tree in [i[1] for i in g.regrow], "used-up nodes are queued"
    assert over.solid not in tree.sprite_lists, "stumps don't block (you can build on them)"
    assert g.near_cleared("over", rock_spot) and g.near_cleared("over", tree_spot), "cleared spots remembered"
    assert tree.hive.state == "gone"

    # ---- 2. a base with a flag, somewhere in the wild
    me.sprite.position = (400, 400)                  # stand out of the way
    flag_pos = (2400.0, 2400.0)
    flag = g.add_structure("base_flag", *flag_pos)
    hut = g.add_structure("campfire", 2400.0 + 600, 2400.0)
    assert g.in_base(flag_pos) and g.in_base((flag_pos[0] + FLAG_RADIUS - 5, flag_pos[1]))
    assert g.in_base((hut.center_x + BASE_RADIUS - 5, hut.center_y))
    assert not g.in_base((flag_pos[0] - FLAG_RADIUS - 50, flag_pos[1] - FLAG_RADIUS - 50))
    assert g.base_home() == flag.position, "the flag is home"
    assert g.base_spot()[0] == flag.center_x, "you respawn at the flag"
    for _ in range(300):
        a, d = random.uniform(0, math.tau), random.uniform(0, FLAG_RADIUS)
        p = (flag_pos[0] + math.cos(a) * d, flag_pos[1] + math.sin(a) * d)
        assert not g.spot_ok("tree", "over", p), "nothing grows in a base"
        assert not g.spot_ok("bush", "over", (hut.center_x + math.cos(a) * d * BASE_RADIUS / FLAG_RADIUS,
                                              hut.center_y + math.sin(a) * d * BASE_RADIUS / FLAG_RADIUS))

    # ---- 3. everything used up turns up again - elsewhere, outside bases, away from people
    for n in random.sample([n for n in g.nodes if n.kind in ("rock", "iron", "tree", "reeds", "glowcap", "coal",
                                                              "crystal") and n.state == "full"], 60):
        while n.state == "full":
            g.harvest(n, 5)
    queued = [(item[1], item[1].base) for item in g.regrow]
    respawn_all(g)
    assert not g.regrow, f"{[(i[1].kind, i[1].layer) for i in g.regrow]} never found a spot"
    for n, old in queued:
        assert n.state == "full" and getattr(n, "moved", False)
        assert dist(n.base, old) > CLEARED_GAP, "never back in the same spot"
        assert not g.in_base(n.base, n.layer), "never inside a base"
        assert all(dist(n.base, p.pos) > 400 for p in g.players.values() if p.layer == n.layer)
        if n.kind in ("reeds", "glowcap"):
            assert g.in_swamp(n.base), "swamp plants come back in the swamp"
        if n.kind == "tree":
            assert (10 <= n.variant < 13) == g.in_swamp(n.base), "swamp trees only in the swamp"
            if n.variant >= 20:
                assert g.biome_at(n.base) == "tundra", "pines only in the tundra"
            assert over.solid in n.sprite_lists
    assert tree.hive.state == "empty" and dist(tree.hive.base, tree.base) < 30, "the hive moved with its tree"
    assert dist(rock.base, rock_spot) > CLEARED_GAP and dist(tree.base, tree_spot) > CLEARED_GAP

    # animals don't spawn inside the base either
    for _ in range(60):
        a = g.spawn_animal()
        if a is not None and a.kind != "bee":
            assert not g.in_base(a.position), "no wild animals spawning in a base"

    # ---- 4. only one flag: planting a second moves the base
    me.inv["base_flag"] = 0
    flag2 = g.add_structure("base_flag", 600.0, 2600.0)
    g.on_built(me, "base_flag")
    assert flag.sid not in g.structs and flag2.sid in g.structs and me.inv.get("base_flag") == 1
    assert g.base_home() == flag2.position

    # some still-used-up nodes for the save
    pending = [n for n in over.rocks if n.state == "full"][:3]
    for n in pending:
        while n.state == "full":
            g.harvest(n, 5)

    # ---- 5. co-op: a client sees moved nodes and the flag
    g.net = "host"
    conn = FakeConn()
    friend = g.add_player("Friend", conn=conn)
    g.sent_nodes_ver = g.sent_struct_ver = g.sent_storage_ver = -1
    g.send_snapshots()
    snap = conn.sent[-1]
    assert "nm" in snap and "n" in snap and any(r[1] == "base_flag" for r in snap["st"])
    host_nodes = [(n.base, n.state, n.variant) for n in g.nodes]
    host_moved = {n.idx for n in g.nodes if getattr(n, "moved", False)}
    # a second snapshot after another harvest: states again, but moves only if something moved
    n2 = next(n for n in over.bushes if n.kind == "bush" and n.state == "full")
    g.harvest(n2, 1)
    g.send_snapshots()
    assert "n" in conn.sent[-1] and "nm" not in conn.sent[-1], "moves aren't resent when nothing moved"
    g.remove_player(friend)

    # ---- 6. save / load round trip
    data = json.loads(json.dumps(g.save_data()))
    want = [(n.base, n.state, n.variant, round(n.hp, 3)) for n in g.nodes]
    want_cleared = list(g.cleared_order)
    want_q = sorted(item[1].idx for item in g.regrow)
    seed = g.seed
    g.net = None
    fresh(g, save=data)
    assert g.seed == seed
    got = [(n.base, n.state, n.variant, round(n.hp, 3)) for n in g.nodes]
    bad = [i for i, (a, b) in enumerate(zip(want, got)) if (round(a[0][0], 1), round(a[0][1], 1)) !=
           (round(b[0][0], 1), round(b[0][1], 1)) or a[1:] != b[1:]]
    assert not bad, f"nodes differ after loading: {bad[:5]}"
    assert len(g.cleared_order) == len(want_cleared)
    assert sorted(item[1].idx for item in g.regrow) == want_q
    assert g.base_flag() is not None and g.base_home() == g.base_flag().position
    assert all(over_n.layer != "over" or g.over.solid not in over_n.sprite_lists
               for over_n in g.nodes if over_n.kind == "tree" and over_n.state == "stump")

    # client applying the host's snapshot to a freshly built world ends up identical
    g.net = None
    g.setup(seed)
    g.apply_node_moves(snap["nm"])
    for n, ch in zip(g.nodes, snap["n"]):
        g.set_node_state(n, main.CODE_NODE.get(ch, "full"))
    for i in host_moved:
        assert dist(g.nodes[i].base, host_nodes[i][0]) < 0.2 and g.nodes[i].variant == host_nodes[i][2]

    # ---- 7. an old save (no "base", stumps on their own timers) still loads, stumps queue up elsewhere
    old = json.loads(json.dumps(data))
    old.pop("base")
    old["regrow"] = []
    stump_idx = next(n.idx for n in g.nodes if n.kind == "tree")
    old["nodes"] = [[stump_idx, "s", 40.0, 0]]
    fresh(g, save=old)
    st = g.nodes[stump_idx]
    assert st.state == "stump" and st in [i[1] for i in g.regrow], "old stumps grow back elsewhere"
    old_spot = st.base
    respawn_all(g)
    assert st.state == "full" and dist(st.base, old_spot) > 1

    g.close()
    print("base.py checks passed: nodes never regrow in place, bases stay clear, flag, saves and co-op sync OK")


if __name__ == "__main__":
    main_test()
