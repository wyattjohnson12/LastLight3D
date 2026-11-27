"""Animals (settings.ANIMALS): rabbit, deer, boar, wolf, bee. Pets reuse these models; the optional
"pet_armor" part (a padded coat on the back, recoloured per armor) is shown when a pet wears armor.
Colours come from art_extra.py / art_bees.py."""
from lowpoly import Model, eyes, glow, mat, quad_legs, shade

DARK_EYE = (30, 20, 20)


def pet_armor(M, x, z, rx, ry, rz):
    """A padded coat with a trim stripe; acc1 = the armor colour (leather by default)."""
    p = M.part("pet_armor", (x, 0, z), "body", opt="pet_armor")
    p.ball((x, 0, z), (rx, ry, rz), mat((150, 100, 56), "acc1"), segs=8, rings=4)
    p.box((x, 0, z + rz * 0.7), (rx * 0.35, ry * 2.05, rz * 0.45), mat((210, 180, 120)))
    M.attach("armor", (x, 0, z + rz), "pet_armor")


def rabbit():
    M = Model("rabbit", {"anim": {"stride": 0.7, "bob": 0.09, "nod": 0.1, "wag": 0.2, "hop": 1},
                         "stride_len": 0.55, "height": 0.5})
    fur, head_c, ear_c = (168, 136, 104), (182, 150, 116), (196, 164, 130)
    b = M.part("body", (0, 0, 0.16), "body")
    b.ball((-0.05, 0, 0.18), (0.2, 0.135, 0.15), mat(fur), segs=8, rings=5)
    b.ball((-0.12, 0, 0.12), (0.12, 0.13, 0.1), mat(shade(fur, 0.92)), segs=7, rings=4)   # haunches
    b.ball((0.06, 0, 0.13), (0.07, 0.07, 0.07), mat((226, 214, 196)), segs=6, rings=4)   # pale chest
    h = M.part("head", (0.12, 0, 0.24), "head")
    h.ball((0.18, 0, 0.27), (0.1, 0.08, 0.085), mat(head_c), segs=8, rings=5)
    h.ball((0.27, 0, 0.255), 0.02, mat((230, 150, 150)), segs=5, rings=3)                 # nose
    for side in (1, -1):
        h.limb((0.15, side * 0.035, 0.33), (0.07, side * 0.075, 0.56), 0.035, 0.022, mat(ear_c), segs=5, flat=0.45)
        h.limb((0.152, side * 0.04, 0.35), (0.085, side * 0.074, 0.52), 0.018, 0.012, mat((226, 170, 160)),
               segs=4, flat=0.4)
    eyes(h, 0.245, 0.055, 0.29, 0.017, mat(DARK_EYE), M=M)
    t = M.part("tail", (-0.24, 0, 0.18), "tail")
    t.ball((-0.26, 0, 0.19), 0.055, mat((240, 236, 228)), segs=6, rings=4)
    for nm, x, side, r, z in (("leg_fl", 0.08, 1, 0.026, 0.1), ("leg_fr", 0.08, -1, 0.026, 0.1),
                              ("leg_bl", -0.12, 1, 0.04, 0.1), ("leg_br", -0.12, -1, 0.04, 0.1)):
        role = "leg_a" if nm in ("leg_fl", "leg_br") else "leg_b"
        leg = M.part(nm, (x, side * 0.08, z), role)
        leg.limb((x, side * 0.08, z), (x + 0.02, side * 0.08, 0.015), r, r * 0.8, mat(shade(fur, 0.85)), segs=5)
        if x < 0:   # long hind feet
            leg.box((x + 0.03, side * 0.08, 0.015), (0.12, 0.05, 0.03), mat(shade(fur, 0.8)))
    pet_armor(M, -0.05, 0.25, 0.15, 0.12, 0.07)
    M.attach("mouth", (0.27, 0, 0.24), "head")
    return M


def deer():
    M = Model("deer", {"anim": {"stride": 0.55, "bob": 0.05, "nod": 0.08, "wag": 0.3},
                       "stride_len": 1.5, "height": 1.7})
    coat, legc, spot, antler = (176, 122, 72), (110, 74, 44), (236, 220, 196), (226, 210, 180)
    b = M.part("body", (0, 0, 0.95), "body")
    b.ball((0, 0, 0.95), (0.55, 0.22, 0.24), mat(coat), segs=8, rings=5)
    b.ball((0.05, 0, 0.83), (0.42, 0.17, 0.12), mat((222, 196, 160)), segs=7, rings=4)    # pale belly
    for x, y, z in ((-0.2, 0.2, 1.06), (-0.02, 0.21, 1.1), (0.15, 0.2, 1.05), (-0.3, -0.19, 1.04),
                    (-0.08, -0.21, 1.08), (0.12, -0.2, 1.06)):
        b.box((x, y, z), (0.07, 0.03, 0.06), mat(spot), rot=(0, 0, 0))
    b.limb((0.38, 0, 1.0), (0.6, 0, 1.38), 0.13, 0.09, mat(coat), segs=6)                 # neck
    h = M.part("head", (0.6, 0, 1.38), "head")
    h.ball((0.68, 0, 1.44), (0.14, 0.1, 0.1), mat(shade(coat, 1.08)), segs=7, rings=4)
    h.limb((0.74, 0, 1.43), (0.9, 0, 1.38), 0.075, 0.05, mat(shade(coat, 1.05)), segs=6)  # snout
    h.ball((0.91, 0, 1.39), 0.035, mat((40, 30, 26)), segs=5, rings=3)                    # nose
    for side in (1, -1):
        h.limb((0.62, side * 0.08, 1.5), (0.55, side * 0.2, 1.58), 0.045, 0.015, mat(coat), segs=4, flat=0.4)
        # antlers: a main beam with three tines
        a0, a1, a2 = (0.64, side * 0.05, 1.52), (0.6, side * 0.16, 1.76), (0.5, side * 0.24, 1.95)
        h.limb(a0, a1, 0.022, 0.018, mat(antler), segs=4)
        h.limb(a1, a2, 0.018, 0.008, mat(antler), segs=4)
        h.limb(a1, (0.72, side * 0.2, 1.88), 0.014, 0.004, mat(antler), segs=4)
        h.limb((0.55, side * 0.2, 1.86), (0.44, side * 0.3, 1.98), 0.012, 0.003, mat(antler), segs=4)
    eyes(h, 0.76, 0.075, 1.47, 0.022, mat(DARK_EYE), M=M)
    t = M.part("tail", (-0.52, 0, 1.05), "tail")
    t.limb((-0.52, 0, 1.05), (-0.62, 0, 0.92), 0.05, 0.03, mat((240, 236, 228)), segs=5, flat=0.7)
    quad_legs(M, 0.34, -0.36, 0.12, 0.88, 0.065, 0.032, mat(legc), hoof_m=mat((50, 36, 26)))
    pet_armor(M, 0, 1.12, 0.36, 0.2, 0.1)
    M.attach("mouth", (0.9, 0, 1.36), "head")
    return M


def boar():
    M = Model("boar", {"anim": {"stride": 0.6, "bob": 0.04, "nod": 0.1, "wag": 0.5, "lunge": 0.35},
                       "stride_len": 0.9, "height": 0.8})
    hide, legc, bristle, snout, tusk = (98, 70, 52), (60, 42, 30), (60, 44, 34), (160, 120, 110), (240, 236, 220)
    b = M.part("body", (0, 0, 0.5), "body")
    b.ball((-0.05, 0, 0.5), (0.5, 0.27, 0.27), mat(hide), segs=8, rings=5, jitter=0.012, seed=3)
    b.ball((0.22, 0, 0.55), (0.25, 0.26, 0.28), mat(shade(hide, 1.05)), segs=8, rings=5)  # big shoulders
    for k in range(7):     # bristly ridge along the back
        x = -0.35 + k * 0.1
        b.limb((x, 0, 0.72 + (0.05 if k > 3 else 0)), (x - 0.05, 0, 0.86 + (0.04 if k > 3 else 0)), 0.04, 0.0,
               mat(bristle), segs=4, flat=0.5)
    h = M.part("head", (0.4, 0, 0.55), "head")
    h.box((0.55, 0, 0.47), (0.32, 0.3, 0.3), mat(shade(hide, 1.08)), taper=0.7, rot=(0, 18, 0))
    h.cyl((0.74, 0, 0.4), 0.08, 0.12, mat(snout), segs=6, rot=(0, 90, 0))                 # snout disc
    h.ball((0.8, 0.03, 0.41), 0.015, mat((60, 30, 30)), segs=4, rings=3)
    h.ball((0.8, -0.03, 0.41), 0.015, mat((60, 30, 30)), segs=4, rings=3)
    for side in (1, -1):
        h.limb((0.68, side * 0.08, 0.36), (0.74, side * 0.13, 0.5), 0.025, 0.0, mat(tusk), segs=4)
        h.limb((0.48, side * 0.1, 0.62), (0.42, side * 0.18, 0.74), 0.05, 0.01, mat(shade(hide, 0.8)), segs=4,
               flat=0.45)
    eyes(h, 0.64, 0.1, 0.55, 0.022, mat((20, 10, 10)), M=M)
    t = M.part("tail", (-0.53, 0, 0.6), "tail")
    t.limb((-0.53, 0, 0.6), (-0.62, 0, 0.45), 0.02, 0.012, mat(bristle), segs=4)
    quad_legs(M, 0.26, -0.33, 0.15, 0.36, 0.07, 0.045, mat(legc), hoof_m=mat((40, 28, 20)))
    pet_armor(M, -0.05, 0.68, 0.36, 0.24, 0.12)
    M.attach("mouth", (0.78, 0, 0.42), "head")
    return M


def wolf():
    M = Model("wolf", {"anim": {"stride": 0.65, "bob": 0.04, "nod": 0.06, "wag": 0.6, "lunge": 0.4},
                       "stride_len": 1.3, "height": 0.95})
    fur, legc, tailc, muzz, ear = (126, 128, 134), (84, 86, 92), (110, 112, 118), (150, 150, 156), (96, 98, 104)
    b = M.part("body", (0, 0, 0.6), "body")
    b.ball((-0.05, 0, 0.6), (0.48, 0.18, 0.2), mat(fur), segs=8, rings=5)
    b.ball((0.22, 0, 0.64), (0.24, 0.2, 0.24), mat(shade(fur, 1.06)), segs=8, rings=5)   # ruff
    b.ball((0.1, 0, 0.5), (0.3, 0.13, 0.1), mat((176, 176, 180)), segs=7, rings=4)       # pale belly
    b.limb((0.3, 0, 0.66), (0.48, 0, 0.8), 0.13, 0.1, mat(fur), segs=6)                   # neck
    h = M.part("head", (0.48, 0, 0.8), "head")
    h.ball((0.56, 0, 0.84), (0.14, 0.12, 0.12), mat(shade(fur, 1.1)), segs=7, rings=5)
    h.limb((0.62, 0, 0.8), (0.82, 0, 0.77), 0.075, 0.04, mat(muzz), segs=6)               # muzzle
    h.ball((0.83, 0, 0.78), 0.025, mat((30, 28, 30)), segs=5, rings=3)                   # nose
    for side in (1, -1):
        h.limb((0.54, side * 0.07, 0.93), (0.5, side * 0.1, 1.06), 0.05, 0.0, mat(ear), segs=4, flat=0.5)
    eyes(h, 0.665, 0.065, 0.87, 0.02, glow((250, 210, 80)), M=M)
    t = M.part("tail", (-0.5, 0, 0.68), "tail")
    t.limb((-0.5, 0, 0.68), (-0.72, 0, 0.5), 0.07, 0.05, mat(tailc), segs=6)
    t.limb((-0.72, 0, 0.5), (-0.8, 0, 0.35), 0.05, 0.02, mat(shade(tailc, 1.2)), segs=6)
    quad_legs(M, 0.24, -0.34, 0.1, 0.48, 0.055, 0.035, mat(legc), knee=-0.02)
    pet_armor(M, -0.08, 0.77, 0.32, 0.18, 0.09)
    M.attach("mouth", (0.82, 0, 0.75), "head")
    return M


def bee():
    M = Model("bee", {"anim": {"flap": 1.0, "hover": 0.7, "float": 0.06, "wag": 0.25},
                      "stride_len": 0.6, "height": 0.25})
    honey, stripe, headc, wing = (236, 170, 40), (40, 30, 20), (50, 40, 30), (225, 240, 255)
    z = 0.12
    b = M.part("body", (0, 0, z), "body")
    b.ball((0.02, 0, z), (0.075, 0.065, 0.065), mat(shade(honey, 0.9)), segs=7, rings=4)  # thorax
    b.ball((0.15, 0, z), 0.05, mat(headc), segs=6, rings=4)                               # head
    eyes(b, 0.18, 0.03, z + 0.015, 0.02, mat((250, 250, 250)), M=M)
    for side in (1, -1):    # antennae
        b.limb((0.18, side * 0.015, z + 0.04), (0.23, side * 0.045, z + 0.1), 0.006, 0.004, mat(stripe), segs=3)
    t = M.part("tail", (-0.04, 0, z), "tail")      # abdomen with stripes + stinger
    t.ball((-0.12, 0, z - 0.01), (0.1, 0.075, 0.075), mat(honey), segs=8, rings=5)
    for x in (-0.09, -0.15):
        t.cyl((x, 0, z - 0.01), 0.073, 0.025, mat(stripe), segs=8, rot=(0, 90, 0))
    t.limb((-0.21, 0, z - 0.02), (-0.27, 0, z - 0.035), 0.015, 0.0, mat(stripe), segs=4)
    for side, nm in ((1, "wing_l"), (-1, "wing_r")):
        w = M.part(nm, (0.02, side * 0.04, z + 0.05), nm)
        w.tri([(0.06, side * 0.04, z + 0.055), (0.0, side * 0.2, z + 0.08), (-0.1, side * 0.17, z + 0.06),
               (-0.05, side * 0.05, z + 0.05)], mat(wing), thick=0.006)
    for x in (0.05, 0.0, -0.04):
        lg = M.part(f"sleg_{x}", (x, 0, z - 0.05), "sleg_a" if x != 0.0 else "sleg_b")
        for side in (1, -1):
            lg.limb((x, side * 0.03, z - 0.05), (x - 0.02, side * 0.06, z - 0.11), 0.006, 0.004, mat(stripe), segs=3)
    pet_armor(M, 0.02, z + 0.05, 0.06, 0.07, 0.03)
    return M


MODELS = {"rabbit": rabbit, "deer": deer, "boar": boar, "wolf": wolf, "bee": bee}
