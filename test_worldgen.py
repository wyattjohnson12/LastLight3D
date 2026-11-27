"""
test_worldgen.py - world generation stays deterministic and old saves keep their exact map.

    python3 test_worldgen.py

  1. worldgen 1 (saves without a "worldgen" field) rebuilds EXACTLY the map the game made before world-gen
     versions existed: same nodes, same kinds, same positions, same indices (fingerprints below were taken
     from the pre-biomes world.py + swamp.py).
  2. An old-style save (no "worldgen", no "spans") loads as worldgen 1.
  3. A new world (worldgen 2) generates identically twice from the same seed, saves its version + spans,
     and loads back identically.
  4. A plug-in biome registered with its own content never changes anyone else's nodes.
  5. Node-index remapping when a module's node count changes; layers / portals are generic.
"""
import hashlib
import json
import random

import biomes
import main

# seed -> [node count, sha256 of the legacy map] (taken with the code before worldgen versions)
LEGACY_PRINTS = {
    1: [647, "c0828c4e06640cfd9894301ddfd7aa16065e7ba42f68675f989b6925ca7cf1eb"],
    12345: [639, "0fa0f3aaa7e7a5045d2ecd456a9b1242be0f67214fb71115b900acab277f3669"],
    987654321: [656, "84bd55de8bdf8ae1d06afeb9f96837474a6085d1e4924b039cca27de48c0477d"],
    424242: [678, "d8d4ef798fefadc53362cfeb5a48b1a585cd59f43adb629912c114faf728a502"],
}


def rows(g):
    return [[n.idx, n.kind, n.layer, round(n.base[0], 2), round(n.base[1], 2), n.variant, round(n.base_angle, 2)]
            for n in g.nodes]


def legacy_print(g):
    extra = [len(g.layers[k].ground) for k in ("over", "cave")] + [len(g.layers[k].decor) for k in ("over", "cave")]
    extra.append(len(g.links))
    s = json.dumps([rows(g), extra, [[round(v, 2) for v in b] for b in g.swamp_blobs], g.links])
    return [len(g.nodes), hashlib.sha256(s.encode()).hexdigest()]


def full_print(g):
    r = rows(g)
    ground = [(round(s.center_x), round(s.center_y), tuple(s.color)) for L in g.layers.values() for s in L.ground]
    decor = [(round(s.center_x), round(s.center_y)) for L in g.layers.values() for s in L.decor]
    s = json.dumps([r, ground, decor, g.links, g.portals, g.node_spans, sorted(g.layers)])
    return hashlib.sha256(s.encode()).hexdigest()


def main_test():
    g = main.LastLight()
    g.set_visible(False)

    # ---- 1. the legacy map is bit-for-bit the old one
    for seed, want in LEGACY_PRINTS.items():
        g.setup(seed, biomes.LEGACY)
        assert g.worldgen == 1 and g.world_size == 3200
        assert legacy_print(g) == want, f"legacy map changed for seed {seed}"
        assert all(g.biome_at(n.base) in ("forest", "mire") for n in g.nodes if n.layer == "over")
    print("1. legacy maps identical to the pre-biome generator")

    # ---- 2. an old save (no worldgen field) rebuilds the legacy map
    random.seed(3)
    g.net = None
    g.setup(12345, biomes.LEGACY)
    g.difficulty = g.chosen_difficulty()
    g.me = g.add_player("Tester")
    tree = next(n for n in g.nodes if n.kind == "tree")
    g.set_node_state(tree, "stump")
    data = json.loads(json.dumps(g.save_data()))
    assert data["worldgen"] == 1
    data.pop("worldgen")
    data.pop("spans")
    g.players.clear()
    g.start(save=data)
    assert g.worldgen == 1 and legacy_print(g) == LEGACY_PRINTS[12345]
    assert g.nodes[tree.idx].state == "stump", "the saved node state lands on the same node"
    assert g.worldgen == 1 and g.world_size == 3200
    print("2. an old-style save (no worldgen) loads the legacy map")

    # ---- 3. new worlds: deterministic, versioned, round-trip through a save
    for seed in (5, 31337):
        g.setup(seed)
        assert g.worldgen == biomes.WORLDGEN and g.world_size == biomes.world_size(biomes.WORLDGEN)
        a = full_print(g)
        g.setup(seed)
        assert full_print(g) == a, f"worldgen {g.worldgen} isn't deterministic (seed {seed})"
        names = {g.biome_at(n.base) for n in g.nodes if n.layer == "over"}
        assert {"forest", "mire"} <= names
        assert g.biome_at(g.centre) == "forest", "spawn is in the forest"
    random.seed(4)
    g.players.clear()
    g.start()
    seed, wg = g.seed, g.worldgen
    want = full_print(g)
    n = next(n for n in g.nodes if n.kind == "rock" and n.layer == "over")
    g.set_node_state(n, "empty")
    data = json.loads(json.dumps(g.save_data()))
    assert data["worldgen"] == wg and data["spans"] == g.node_spans
    g.players.clear()
    g.setup(999)
    g.start(save=data)
    assert g.seed == seed and g.worldgen == wg and full_print(g) == want
    assert g.nodes[n.idx].state == "empty"
    print(f"3. worldgen {wg} worlds are deterministic and survive a save ({g.world_size}px, {len(g.nodes)} nodes)")

    # ---- 4. one module's content never moves anyone else's nodes
    g.setup(seed)
    before = rows(g)
    spans = dict(g.node_spans)

    def extra(gen):
        for _ in range(25):
            p = gen.spot("tundra")
            if p and gen.free(p, 30):
                gen.add_node(main.Node("rock", main.art.rock(0), *p), gen.over.rocks)

    biomes.register(biomes.Biome("zz_test", order=25, region=False, gen_surface=extra))
    try:
        g.setup(seed)
        after = rows(g)
        # every other module's nodes are exactly the same (later modules' indices just move up - saves remap them)
        for k, (s0, c0) in spans.items():
            s1, c1 = g.node_spans[k]
            assert c1 == c0 and [r[1:] for r in after[s1:s1 + c1]] == [r[1:] for r in before[s0:s0 + c0]], \
                f"adding a module changed {k}'s nodes"
        assert "zz_test" in g.node_spans and all(g.node_spans[k] == v for k, v in spans.items()
                                                 if biomes.get(k).order <= 25 or k in ("base", "mire"))
    finally:
        biomes.BIOMES.pop("zz_test")
        biomes._cache.clear()
    print("4. a new module only appends its own nodes")

    # ---- 5. remapping + generic layers / portals
    f = biomes.remap_index({"base": [0, 10], "mire": [10, 5], "tundra": [15, 4]},
                           {"base": [0, 10], "mire": [10, 5], "ash": [15, 3], "tundra": [18, 2]})
    assert [f(i) for i in (0, 9, 10, 14, 15, 16, 17, 18)] == [0, 9, 10, 14, 18, 19, None, None]
    assert biomes.remap_index(None, {"base": [0, 3]})(7) == 7
    g.setup(seed)
    for name in main.LAYERS:
        assert name in g.layers
    g.players.clear()
    g.me = g.add_player("Tester")
    g.state = "playing"
    surf, cave = g.links[0]
    g.set_layer(g.me, "over", (surf[0] + 20, surf[1]))
    g.travel(g.me)
    assert g.me.layer == "cave"
    g.travel(g.me)
    assert g.me.layer == "over"
    if "deep" in g.layers:
        g.set_layer(g.me, "deep", (500, 500))
        for _ in range(5):
            g.on_update(1 / 30)
        g.on_draw()
    print("5. remapping, layers and portals OK")
    g.close()
    print("world generation checks passed")


if __name__ == "__main__":
    main_test()
