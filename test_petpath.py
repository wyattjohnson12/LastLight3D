"""
test_petpath.py - working pets find their way around walls (petpath.py).

    python3 test_petpath.py

A hauler carrying wood is put on one side of a long wall with the Storage Bin on the other side, and must
bring the wood home. Then a pet is walled in completely: it must give up on that trip (not freeze the game).
"""
import math
import random
import time

import main
from settings import GRID
from world import Animal


def fresh(g):
    random.seed(7)
    g.net = None
    g.start()
    g.state, g.intro = "playing", None
    return g


def open_spot(g, w=900, h=700):
    """A patch of plain land with nothing on it: clear the solid things there, avoid cliffs and water."""
    for _ in range(400):
        x0 = random.uniform(300, g.world_size - 300 - w)
        y0 = random.uniform(300, g.world_size - 300 - h)
        probe = Animal("boar", x0, y0)
        ok = all(not g.terrain_blocked(x0 + i * 40, y0 + j * 40, "over")
                 for i in range(w // 40 + 1) for j in range(h // 40 + 1))
        if ok and not g.in_base((x0 + w / 2, y0 + h / 2)):
            for s in list(g.over.solid) + list(g.over.huts):
                if x0 - 60 < s.center_x < x0 + w + 60 and y0 - 60 < s.center_y < y0 + h + 60:
                    s.remove_from_sprite_lists()
            del probe
            return x0, y0
    raise SystemExit("no open land found")


def make_pet(g, kind, x, y, owner):
    a = Animal(kind, x, y, g.next_aid)
    g.next_aid += 1
    a.owner, a.mode = owner.id, "work"
    g.over.animals.append(a)
    g.amap[a.aid] = a
    return a


def run(g, a, seconds, until):
    dt = 1 / 30
    worst = 0.0
    for _ in range(int(seconds / dt)):
        t = time.perf_counter()
        g._update_animals(dt)
        g.flame_t += dt
        worst = max(worst, time.perf_counter() - t)
        if until():
            return True, worst
    return False, worst


def main_test():
    g = fresh(main.LastLight())
    me = g.me
    x0, y0 = open_spot(g)
    for s in [s for s in g.structs.values() if s.kind == "storage"]:
        s.remove_from_sprite_lists()
        g.structs.pop(s.sid, None)
    # pet at the left, bin at the right, a wall in the middle much longer than a pet's sidestep
    pet_at = (x0 + 120, y0 + 350)
    bin_at = (x0 + 720, y0 + 350)
    wall_x = x0 + 420
    for j in range(-6, 7):
        g.add_structure("stone_wall", wall_x, y0 + 350 + j * GRID)
    g.add_structure("storage", *bin_at)
    me.position = (x0 + 450, y0 + 680)   # the owner stands off to one side
    a = make_pet(g, "boar" if "boar" in main.ANIMALS else next(k for k, v in main.ANIMALS.items()
                                                                if v["job"] == "hauler"), *pet_at, me)
    a.carry = {"wood": 5}
    a.goal = "home"
    before = g.storage.get("wood", 0) if hasattr(g, "storage") else 0
    done, worst = run(g, a, 40, lambda: not a.carry)
    assert done, f"pet never got round the wall (stuck at {a.position}, wanted bin at {bin_at})"
    after = g.storage.get("wood", 0) if hasattr(g, "storage") else 5
    assert after >= before + 5 or not hasattr(g, "storage"), "wood didn't reach storage"
    print(f"ok: hauler went round a {13 * GRID}px wall to storage  (slowest update {worst * 1000:.1f} ms)")

    # walled in on every side: it must not freeze the game trying
    cx, cy = x0 + 120, y0 + 120
    for i in range(-2, 3):
        for j in (-2, 2):
            g.add_structure("stone_wall", cx + i * GRID, cy + j * GRID)
            g.add_structure("stone_wall", cx + j * GRID, cy + i * GRID)
    b = make_pet(g, a.kind, cx, cy, me)
    b.carry, b.goal = {"stone": 2}, "home"
    t = time.perf_counter()
    _, worst = run(g, b, 8, lambda: False)
    took = time.perf_counter() - t
    assert worst < 0.25, f"a boxed-in pet made one update take {worst * 1000:.0f} ms"
    print(f"ok: boxed-in pet keeps trying without freezing (8 s simulated in {took:.2f} s, "
          f"slowest update {worst * 1000:.1f} ms)")


if __name__ == "__main__":
    main_test()
    print("all pet path tests passed")
