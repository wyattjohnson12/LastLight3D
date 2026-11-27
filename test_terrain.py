"""test_terrain.py - rivers / cliffs / roads: deterministic, and the spawn reaches every biome centre and every
cave entrance (through fords and road bridges).   python3 test_terrain.py"""
import biomes
import main
import terrain_map as TM


def main_test():
    g = main.LastLight()
    g.set_visible(False)
    for seed in (5, 31337, 77, 4242, 99):
        g.setup(seed)
        m = TM.get(g.layout)
        TM._cache.clear()
        m2 = TM.get(g.layout)
        assert bytes(m.flags) == bytes(m2.flags), "terrain map isn't deterministic"
        assert m.unreached == 0, f"seed {seed}: {m.unreached} dry cells cut off"
        seen = m.flood(g.layout.centre)
        N = m.N

        def reach(p):
            i, j = int(p[0] // TM.C), int(p[1] // TM.C)
            return any(seen[(j + dy) * N + i + dx] for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))
        for name, c in g.layout.centres.items():
            assert reach(c), f"seed {seed}: can't reach the {name} centre"
        for s in g.over.exits:
            assert reach(s.position), f"seed {seed}: can't reach a cave entrance"
        assert m.fords and m.bridges and m.cliffs
        assert not g.terrain_blocked(*g.layout.centre)
    g.setup(5, biomes.LEGACY)
    assert TM.get(g.layout) is None and not g.terrain_blocked(100, 100)
    g.close()
    print("terrain checks passed: deterministic, everything reachable from the spawn, legacy worlds untouched")


if __name__ == "__main__":
    main_test()
