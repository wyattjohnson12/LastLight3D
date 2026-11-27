"""Frostwood Tundra animals (tundra.py / settings.ANIMALS): snow_fox, snow_hare, arctic_wolf.
Colours come from art_tundra.py (the top-down sprites). Pets reuse these models, so each has the optional
"pet_armor" coat like the other animals."""
from lowpoly import Model, eyes, glow, mat, quad_legs, shade

from animals import pet_armor  # noqa: E402  (same folder; build_all puts it on sys.path)

DARK_EYE = (30, 26, 30)


def snow_fox():
    M = Model("snow_fox", {"anim": {"stride": 0.65, "bob": 0.04, "nod": 0.07, "wag": 0.7, "lunge": 0.3},
                           "stride_len": 0.9, "height": 0.6})
    fur, legc, tail_tip, ear_in = (232, 236, 244), (196, 204, 216), (250, 252, 255), (226, 190, 190)
    b = M.part("body", (0, 0, 0.36), "body")
    b.ball((-0.04, 0, 0.36), (0.32, 0.13, 0.14), mat(fur), segs=8, rings=5)
    b.ball((0.16, 0, 0.39), (0.16, 0.14, 0.16), mat(shade(fur, 1.04)), segs=8, rings=5)   # fluffy chest
    b.limb((0.2, 0, 0.42), (0.32, 0, 0.52), 0.1, 0.075, mat(fur), segs=6)                  # neck
    h = M.part("head", (0.32, 0, 0.52), "head")
    h.ball((0.38, 0, 0.55), (0.11, 0.1, 0.09), mat(shade(fur, 1.05)), segs=7, rings=5)
    h.limb((0.44, 0, 0.53), (0.6, 0, 0.5), 0.055, 0.02, mat(fur), segs=6)                  # pointed muzzle
    h.ball((0.6, 0, 0.5), 0.02, mat((30, 26, 30)), segs=5, rings=3)                        # nose
    for side in (1, -1):        # big triangular ears with a pink inside
        h.limb((0.36, side * 0.055, 0.62), (0.33, side * 0.09, 0.78), 0.05, 0.0, mat(fur), segs=4, flat=0.45)
        h.limb((0.37, side * 0.058, 0.63), (0.345, side * 0.085, 0.74), 0.028, 0.0, mat(ear_in), segs=4, flat=0.35)
    eyes(h, 0.47, 0.05, 0.58, 0.016, mat(DARK_EYE), M=M)
    t = M.part("tail", (-0.34, 0, 0.4), "tail")    # huge bushy tail with a white tip
    t.limb((-0.34, 0, 0.4), (-0.6, 0, 0.34), 0.07, 0.11, mat(fur), segs=7)
    t.limb((-0.6, 0, 0.34), (-0.76, 0, 0.28), 0.11, 0.03, mat(tail_tip), segs=7)
    quad_legs(M, 0.18, -0.24, 0.08, 0.3, 0.042, 0.026, mat(legc), knee=-0.015)
    pet_armor(M, -0.04, 0.47, 0.22, 0.14, 0.06)
    M.attach("mouth", (0.6, 0, 0.48), "head")
    return M


def snow_hare():
    M = Model("snow_hare", {"anim": {"stride": 0.7, "bob": 0.09, "nod": 0.1, "wag": 0.2, "hop": 1},
                            "stride_len": 0.6, "height": 0.55})
    fur, head_c, tip = (236, 240, 246), (244, 246, 250), (60, 60, 68)
    b = M.part("body", (0, 0, 0.17), "body")
    b.ball((-0.05, 0, 0.19), (0.22, 0.145, 0.16), mat(fur), segs=8, rings=5)
    b.ball((-0.13, 0, 0.13), (0.13, 0.14, 0.11), mat(shade(fur, 0.94)), segs=7, rings=4)     # haunches
    h = M.part("head", (0.13, 0, 0.26), "head")
    h.ball((0.19, 0, 0.29), (0.105, 0.085, 0.09), mat(head_c), segs=8, rings=5)
    h.ball((0.285, 0, 0.275), 0.02, mat((220, 160, 160)), segs=5, rings=3)                  # nose
    for side in (1, -1):        # long ears with black tips
        h.limb((0.16, side * 0.035, 0.35), (0.08, side * 0.08, 0.56), 0.036, 0.024, mat(fur), segs=5, flat=0.45)
        h.limb((0.08, side * 0.08, 0.56), (0.055, side * 0.09, 0.62), 0.024, 0.008, mat(tip), segs=5, flat=0.45)
    eyes(h, 0.255, 0.058, 0.31, 0.017, mat(DARK_EYE), M=M)
    t = M.part("tail", (-0.26, 0, 0.19), "tail")
    t.ball((-0.28, 0, 0.2), 0.055, mat((252, 252, 255)), segs=6, rings=4)
    for nm, x, side, r in (("leg_fl", 0.08, 1, 0.027), ("leg_fr", 0.08, -1, 0.027),
                           ("leg_bl", -0.13, 1, 0.042), ("leg_br", -0.13, -1, 0.042)):
        role = "leg_a" if nm in ("leg_fl", "leg_br") else "leg_b"
        leg = M.part(nm, (x, side * 0.085, 0.1), role)
        leg.limb((x, side * 0.085, 0.1), (x + 0.02, side * 0.085, 0.015), r, r * 0.8, mat(shade(fur, 0.88)), segs=5)
        if x < 0:   # big snowshoe hind feet
            leg.box((x + 0.035, side * 0.085, 0.015), (0.15, 0.06, 0.03), mat(shade(fur, 0.84)))
    pet_armor(M, -0.05, 0.27, 0.16, 0.13, 0.07)
    M.attach("mouth", (0.28, 0, 0.26), "head")
    return M


def arctic_wolf():
    M = Model("arctic_wolf", {"anim": {"stride": 0.65, "bob": 0.04, "nod": 0.06, "wag": 0.55, "lunge": 0.45},
                              "stride_len": 1.4, "height": 1.05})
    fur, legc, ruff, muzz, ear = (214, 222, 232), (160, 170, 184), (232, 236, 242), (232, 236, 242), (176, 186, 200)
    b = M.part("body", (0, 0, 0.66), "body")
    b.ball((-0.06, 0, 0.66), (0.52, 0.2, 0.22), mat(fur), segs=8, rings=5)
    b.ball((0.24, 0, 0.7), (0.27, 0.23, 0.27), mat(ruff), segs=8, rings=5, jitter=0.015, seed=7)   # thick ruff
    b.ball((0.1, 0, 0.55), (0.32, 0.14, 0.11), mat(shade(fur, 1.06)), segs=7, rings=4)
    b.limb((0.34, 0, 0.72), (0.52, 0, 0.88), 0.14, 0.11, mat(fur), segs=6)                       # neck
    h = M.part("head", (0.52, 0, 0.88), "head")
    h.ball((0.6, 0, 0.92), (0.15, 0.13, 0.13), mat(shade(fur, 1.06)), segs=7, rings=5)
    h.limb((0.67, 0, 0.88), (0.88, 0, 0.84), 0.08, 0.045, mat(muzz), segs=6)                     # muzzle
    h.ball((0.89, 0, 0.85), 0.027, mat((30, 30, 36)), segs=5, rings=3)                          # nose
    for side in (1, -1):
        h.limb((0.58, side * 0.075, 1.01), (0.54, side * 0.1, 1.15), 0.052, 0.0, mat(ear), segs=4, flat=0.5)
    eyes(h, 0.715, 0.07, 0.95, 0.021, glow((120, 200, 255)), M=M)                              # icy eyes
    t = M.part("tail", (-0.55, 0, 0.74), "tail")
    t.limb((-0.55, 0, 0.74), (-0.78, 0, 0.55), 0.08, 0.06, mat(fur), segs=6)
    t.limb((-0.78, 0, 0.55), (-0.87, 0, 0.38), 0.06, 0.02, mat(ruff), segs=6)
    quad_legs(M, 0.26, -0.37, 0.11, 0.52, 0.06, 0.038, mat(legc), knee=-0.02)
    pet_armor(M, -0.08, 0.84, 0.35, 0.2, 0.1)
    M.attach("mouth", (0.88, 0, 0.82), "head")
    return M


MODELS = {"snow_fox": snow_fox, "snow_hare": snow_hare, "arctic_wolf": arctic_wolf}
