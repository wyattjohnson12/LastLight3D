"""The Riverlands (terrain.py): river fish (three looks: trout, perch, golden carp), the mallard duck
(a wild animal, ANIMALS["duck"]) and the river frog (hops on the banks, a visual creature).
Colours match the sprites in art_terrain.py. Fish are drawn under the water surface, swimming; the
"tail" role wags them along, "body" bobs."""
from lowpoly import Model, eyes, mat, quad_legs, shade

DARK_EYE = (24, 20, 18)


def _fish(name, back, belly, fin, spots=None, length=0.5, deep=0.11):
    M = Model(name, {"anim": {"wag": 1.0, "float": 0.03, "nod": 0.05, "bob": 0.0}, "stride_len": 0.4,
                     "height": deep * 2})
    z = deep + 0.02
    L = length
    b = M.part("body", (0, 0, z), "body")
    b.ball((0.02, 0, z + 0.01), (L * 0.42, deep * 0.55, deep), mat(back), segs=8, rings=5)
    b.ball((0.04, 0, z - deep * 0.35), (L * 0.36, deep * 0.5, deep * 0.6), mat(belly), segs=7, rings=4)
    b.ball((L * 0.34, 0, z), (L * 0.14, deep * 0.45, deep * 0.72), mat(shade(back, 1.05)), segs=7, rings=4)  # head
    b.ball((L * 0.47, 0, z - deep * 0.2), (0.02, 0.03, 0.015), mat(shade(belly, 0.6)), segs=5, rings=3)      # mouth
    eyes(b, L * 0.4, deep * 0.32, z + deep * 0.25, 0.018, mat(DARK_EYE), M=M)
    b.tri([(0.05, 0, z + deep * 0.9), (-0.08, 0, z + deep * 1.55), (-0.16, 0, z + deep * 0.8)], mat(fin), thick=0.01)
    for side in (1, -1):        # side fins
        b.tri([(L * 0.2, side * deep * 0.45, z - deep * 0.3), (L * 0.08, side * deep * 1.1, z - deep * 0.55),
               (L * 0.04, side * deep * 0.45, z - deep * 0.4)], mat(fin), thick=0.008)
    if spots:
        for x, y, zz in ((-0.05, 1, 0.4), (0.08, 1, 0.55), (-0.12, -1, 0.5), (0.04, -1, 0.3), (0.15, 1, 0.2)):
            b.ball((x * L * 2.2, y * deep * 0.5, z + deep * zz), 0.016, mat(spots), segs=4, rings=3)
    t = M.part("tail", (-L * 0.36, 0, z), "tail")
    t.limb((-L * 0.36, 0, z), (-L * 0.55, 0, z), deep * 0.35, deep * 0.15, mat(back), segs=6)
    t.tri([(-L * 0.52, 0, z), (-L * 0.78, 0, z + deep * 0.95), (-L * 0.7, 0, z), (-L * 0.78, 0, z - deep * 0.9)],
          mat(fin), thick=0.012)
    return M


def trout():
    return _fish("fish", (92, 110, 96), (226, 214, 190), (120, 130, 110), spots=(60, 50, 44))


def perch():
    M = _fish("fish_perch", (110, 130, 62), (232, 222, 170), (220, 110, 60), length=0.42, deep=0.12)
    b = M.parts[0]
    for x in (-0.1, -0.02, 0.06):      # dark perch bars
        b.ball((x, 0, 0.16), (0.016, 0.07, 0.11), mat((60, 76, 40)), segs=6, rings=4)
    return M


def carp():
    return _fish("fish_gold", (236, 150, 50), (250, 220, 150), (250, 196, 110), length=0.55, deep=0.13)


def duck():
    M = Model("duck", {"anim": {"stride": 0.7, "bob": 0.03, "nod": 0.18, "wag": 0.5, "flap": 0.0},
                       "stride_len": 0.45, "height": 0.55})
    body_c, head_c, chest_c, bill_c = (150, 132, 108), (40, 110, 70), (120, 80, 60), (236, 180, 50)
    z = 0.26
    b = M.part("body", (0, 0, z), "body")
    b.ball((0, 0, z), (0.24, 0.15, 0.13), mat(body_c), segs=8, rings=5)
    b.ball((0.12, 0, z - 0.01), (0.12, 0.12, 0.11), mat(chest_c), segs=7, rings=4)
    b.ball((-0.04, 0, z - 0.07), (0.2, 0.13, 0.07), mat((210, 206, 196)), segs=7, rings=3)    # pale belly
    for side in (1, -1):         # folded wings with a blue speculum
        b.ball((-0.04, side * 0.12, z + 0.03), (0.17, 0.045, 0.08), mat(shade(body_c, 0.85)), segs=6, rings=4)
        b.box((-0.07, side * 0.16, z + 0.03), (0.07, 0.01, 0.03), mat((60, 90, 200)))
    b.limb((0.15, 0, z + 0.04), (0.2, 0, z + 0.2), 0.055, 0.045, mat((240, 240, 236)), segs=6)   # white collar
    h = M.part("head", (0.2, 0, z + 0.2), "head")
    h.limb((0.2, 0, z + 0.2), (0.22, 0, z + 0.28), 0.05, 0.05, mat(head_c), segs=6)
    h.ball((0.23, 0, z + 0.3), (0.07, 0.055, 0.06), mat(head_c), segs=7, rings=4)
    h.box((0.31, 0, z + 0.28), (0.08, 0.05, 0.02), mat(bill_c), taper=0.7)
    eyes(h, 0.27, 0.04, z + 0.32, 0.012, mat(DARK_EYE), M=M)
    t = M.part("tail", (-0.22, 0, z + 0.03), "tail")
    t.box((-0.27, 0, z + 0.06), (0.08, 0.1, 0.03), mat(shade(body_c, 0.7)), taper=0.5, rot=(0, -25, 0))
    t.limb((-0.27, 0, z + 0.08), (-0.25, 0, z + 0.13), 0.012, 0.006, mat((30, 30, 30)), segs=3)   # curl
    for nm, y, role in (("leg_l", 0.06, "leg_a"), ("leg_r", -0.06, "leg_b")):
        lg = M.part(nm, (0.0, y, z - 0.09), role)
        lg.limb((0.0, y, z - 0.09), (0.01, y, 0.02), 0.014, 0.012, mat((236, 140, 50)), segs=4)
        lg.box((0.04, y, 0.01), (0.07, 0.05, 0.015), mat((236, 140, 50)))
    M.attach("mouth", (0.35, 0, z + 0.28), "head")
    return M


def frog():
    M = Model("frog", {"anim": {"stride": 0.9, "bob": 0.05, "nod": 0.05, "hop": 1, "breathe": 0.05},
                       "stride_len": 0.3, "height": 0.16})
    skin, belly = (84, 140, 60), (210, 214, 150)
    z = 0.08
    b = M.part("body", (0, 0, z), "body")
    b.ball((0, 0, z), (0.1, 0.08, 0.06), mat(skin), segs=7, rings=4)
    b.ball((0.01, 0, z - 0.03), (0.09, 0.07, 0.03), mat(belly), segs=6, rings=3)
    for x, y in ((-0.03, 0.04), (0.02, -0.03), (-0.05, -0.02)):
        b.ball((x, y, z + 0.05), 0.014, mat(shade(skin, 0.6)), segs=4, rings=3)
    h = M.part("head", (0.07, 0, z + 0.01), "head")
    h.ball((0.09, 0, z + 0.01), (0.06, 0.07, 0.04), mat(skin), segs=7, rings=4)
    for side in (1, -1):
        h.ball((0.1, side * 0.04, z + 0.045), 0.022, mat((230, 200, 60)), segs=5, rings=3)
        h.ball((0.11, side * 0.045, z + 0.05), 0.011, mat(DARK_EYE), segs=4, rings=3)
    quad_legs(M, 0.05, -0.06, 0.07, 0.06, 0.018, 0.012, mat(shade(skin, 0.85)))
    return M


MODELS = {"fish": trout, "fish_perch": perch, "fish_gold": carp, "duck": duck, "frog": frog}
