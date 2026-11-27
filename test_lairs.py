"""
test_lairs.py - the bosses' lairs (lairs.py): bosses you choose to wake.

    python3 test_lairs.py

  1. Lairs are placed the same way every time from the seed, each in its own biome on new maps (legacy maps
     too, away from the spawn), and every one can be reached from the spawn.
  2. Using an altar warns first; using it again wakes the boss AT its lair (with its intro cutscene), restarts
     the backstop clock, and nobody can wake a second boss while one is out.
  3. A boss that runs home at dawn keeps its wounds in its lair and comes back with them when woken again.
  4. Beating a boss makes its lair quiet; that survives a save + load; a quiet altar won't wake anything.
  5. The backstop: nobody woke a boss for too long -> the next unbeaten one wakes by itself at nightfall.
  6. A save from before lairs loads with the old boss counter turned into beaten lairs.
  7. Co-op: the lair state reaches a client through the snapshot rows.
"""
import json
import random

import biomes
import lairs
import main
import terrain_map as TM
from settings import BOSS_ORDER, BOSS_WAKE_NIGHTS, DAY_CYCLE_SECONDS, DUSK_START, NIGHT_START


def spots(g):
    return {k: (round(l.x, 2), round(l.y, 2), round(l.ux, 4), round(l.uy, 4)) for k, l in lairs._state(g).lairs.items()}


def boss_out(g):
    return [b for b in g.over.bosses]


def clear_bosses(g):
    g.end_cutscene()
    for b in list(g.over.bosses):
        g.bmap.pop(b.bid, None)
        b.remove_from_sprite_lists()


def main_test():
    random.seed(4)
    g = main.LastLight()
    g.set_visible(False)

    # ---- 1. placement
    for seed in (5, 77, 4242):
        g.setup(seed)
        a = spots(g)
        g.setup(seed)
        assert spots(g) == a, f"seed {seed}: lairs moved between two builds of the same world"
        assert list(a) == list(BOSS_ORDER)
        for kind, lair in lairs._state(g).lairs.items():
            assert g.biome_at(lair.pos) == lairs.HOMES[kind], f"seed {seed}: {kind} lair not in its biome"
            assert lairs._dist(lair.pos, g.centre) > 600
        m = TM.get(g.layout)
        seen = m.flood(g.layout.centre)
        for kind, lair in lairs._state(g).lairs.items():
            i, j = int(lair.x // TM.C), int(lair.y // TM.C)
            near = any(seen[(j + dy) * m.N + i + dx] for dx in range(-3, 4) for dy in range(-3, 4))
            assert near, f"seed {seed}: can't walk to the {kind} lair"
    for seed in (1, 12345):
        g.setup(seed, biomes.LEGACY)
        a = spots(g)
        g.setup(seed, biomes.LEGACY)
        assert spots(g) == a and len(a) == len(BOSS_ORDER)
        assert g.in_swamp(lairs.lair_of(g, "mire").pos), "the old map's Mire Lurker sleeps in the Mire"
        assert all(lairs._dist(l.pos, g.centre) > 600 for l in lairs._state(g).lairs.values())
    print("1. lairs: same place every time, in their biomes, reachable (new and old maps)")

    # ---- 2. waking at the altar
    g.net = None
    g.setup(77)
    g.difficulty = g.chosen_difficulty()
    g.start()
    g.end_intro()
    me = g.me
    assert g.boss_gap == BOSS_WAKE_NIGHTS and g.boss_day == BOSS_WAKE_NIGHTS
    lair = lairs.lair_of(g, "wraith")
    g.set_layer(me, "over", (lair.x - lair.ux * 70, lair.y - lair.uy * 70))
    g.day = 3
    assert lairs.near_altar(g, me) is lair
    g.interact(me)
    assert not boss_out(g), "the first use is only a warning"
    g.interact(me)
    out = boss_out(g)
    assert len(out) == 1 and out[0].kind == "wraith", out
    b = out[0]
    assert lairs._dist(b.position, lair.rise) < 1, "it rises at its own lair"
    assert g.cut and g.cut["kind"] == "wraith" and g.cut["mode"] == "intro"
    assert g.boss_day == 3 + g.boss_gap, "waking one restarts the backstop clock"
    g.end_cutscene()
    other = lairs.lair_of(g, "titan")
    g.set_layer(me, "over", (other.x - other.ux * 70, other.y - other.uy * 70))
    g.interact(me)
    g.interact(me)
    assert len(boss_out(g)) == 1, "only one boss awake at a time"
    print("2. waking: warning, then the boss rises at its lair; one at a time")

    # ---- 3. dawn: it runs home and keeps its wounds
    b.hp = b.max_hp * 0.5
    g.start_retreat(b)
    assert lair.hp == b.hp
    clear_bosses(g)
    g.set_layer(me, "over", (lair.x - lair.ux * 70, lair.y - lair.uy * 70))
    lairs.wake(g, "wraith", me)
    b2 = boss_out(g)[0]
    assert b2.hp == b.hp and not g.cut, "woken again: same wounds, no intro"
    print("3. a boss that ran home keeps its wounds")

    # ---- 4. beating it: the lair goes quiet, and stays quiet after a save
    g.kill_boss(b2, me)
    assert lairs.beaten(lairs._state(g), lair) and g.boss_num == 1 and lair.hp is None
    lairs.visuals(g, 0.1)
    assert lair.quiet and not lair.glow.visible
    data = json.loads(json.dumps(g.save_data()))
    assert data["biomes"]["lairs"]["kills"]["wraith"] == 1
    g.players.clear()
    g.start(save=data)
    g.end_intro()
    me = g.me
    lair = lairs.lair_of(g, "wraith")
    assert lair.kills == 1 and lairs.beaten(lairs._state(g), lair), "beaten lairs stay beaten after loading"
    g.set_layer(me, "over", (lair.x - lair.ux * 70, lair.y - lair.uy * 70))
    g.interact(me)
    g.interact(me)
    assert not boss_out(g), "a quiet lair wakes nothing"
    assert lairs.next_kind(g) == "titan"
    print("4. a beaten lair goes quiet and stays quiet after save / load")

    # ---- 5. the backstop
    g.set_layer(me, "over", g.centre)
    me.alive = True
    g.boss_day = g.day
    g.clock = (DUSK_START - 0.002) * DAY_CYCLE_SECONDS + (g.day - 1) * DAY_CYCLE_SECONDS
    for _ in range(4000):
        g._update_clock(0.05)
        if boss_out(g) or g.phase > NIGHT_START + 0.02:
            break
    out = boss_out(g)
    assert len(out) == 1 and out[0].kind == "titan", "the next unbeaten boss woke by itself"
    assert lairs._dist(out[0].position, me.pos) < 700, "...and came for the survivors"
    assert g.boss_day == g.day + g.boss_gap
    clear_bosses(g)
    print("5. backstop: nobody woke a boss for too long -> one wakes by itself at nightfall")

    # ---- 6. an old save (before lairs): 6 bosses killed in the old order, the next one wounded
    old = json.loads(json.dumps(g.save_data()))
    old["biomes"].pop("lairs")
    old["boss"] = [6, old["day"] + 1, 77.0]
    old["bosses"] = []
    old["meta"]["difficulty"] = old["meta"]["difficulty"][:3] + [3]
    g.players.clear()
    g.start(save=old)
    g.end_intro()
    kills = {k: l.kills for k, l in lairs._state(g).lairs.items()}
    n = len(BOSS_ORDER)
    want = {k: 6 // n + (1 if i < 6 % n else 0) for i, k in enumerate(BOSS_ORDER)}
    assert kills == want, (kills, want)
    assert lairs.lair_of(g, BOSS_ORDER[6 % n]).hp == 77.0
    assert g.boss_gap == BOSS_WAKE_NIGHTS and g.boss_day == g.day + BOSS_WAKE_NIGHTS
    print("6. old saves: the boss counter becomes beaten lairs; the old 3-night rhythm becomes the backstop")

    # ---- 7. co-op rows
    rows = lairs.net_rows(g)
    c = main.LastLight.__new__(main.LastLight)       # just enough of a client to hold the lair state
    c.nodes = g.nodes
    c.lair_st = lairs.State(c)
    for k, l in lairs._state(g).lairs.items():
        c.lair_st.lairs[k] = lairs.Lair(k, l.x, l.y, l.ux, l.uy)
    lairs.net_apply(c, json.loads(json.dumps(rows)))
    assert [l.kills for l in c.lair_st.lairs.values()] == [l.kills for l in lairs._state(g).lairs.values()]
    assert c.lair_st.lairs[BOSS_ORDER[6 % n]].hp is not None
    print("7. co-op: lair state reaches the clients")
    g.close()
    print("lair checks passed")


if __name__ == "__main__":
    main_test()
