"""The Stone Highlands (highlands.py): the mountain goat. Colours come from art_highlands.py's goat sprite.
Pets reuse it (goats can be tamed with heather), so it has the optional "pet_armor" coat too."""
from animals import pet_armor
from lowpoly import Model, eyes, mat, quad_legs, shade

DARK_EYE = (40, 30, 20)


def goat():
    M = Model("goat", {"anim": {"stride": 0.6, "bob": 0.05, "nod": 0.1, "wag": 0.5, "lunge": 0.4},
                       "stride_len": 1.0, "height": 1.05})
    wool, belly, face, horn, legc, hoof, beard = ((226, 220, 204), (244, 240, 228), (196, 188, 172), (120, 104, 84),
                                                 (170, 162, 146), (60, 50, 42), (240, 236, 224))
    b = M.part("body", (0, 0, 0.62), "body")
    b.ball((-0.04, 0, 0.62), (0.42, 0.2, 0.21), mat(wool), segs=8, rings=5, jitter=0.015, seed=5)   # shaggy coat
    b.ball((0.2, 0, 0.66), (0.2, 0.19, 0.22), mat(shade(wool, 1.04)), segs=8, rings=5)              # chest
    b.ball((0.0, 0, 0.5), (0.3, 0.15, 0.1), mat(belly), segs=7, rings=4)
    for k in range(5):        # tufts of long hair hanging off the flanks
        x = -0.3 + k * 0.13
        for side in (1, -1):
            b.limb((x, side * 0.17, 0.56), (x - 0.03, side * 0.19, 0.4), 0.05, 0.015, mat(shade(wool, 0.95)),
                   segs=4, flat=0.6)
    b.limb((0.28, 0, 0.7), (0.42, 0, 0.9), 0.11, 0.08, mat(wool), segs=6)                            # neck
    h = M.part("head", (0.42, 0, 0.9), "head")
    h.ball((0.5, 0, 0.95), (0.12, 0.09, 0.1), mat(face), segs=7, rings=5)
    h.limb((0.55, 0, 0.93), (0.68, 0, 0.84), 0.065, 0.04, mat(face), segs=6)                         # muzzle
    h.ball((0.69, 0, 0.84), 0.025, mat((70, 56, 50)), segs=5, rings=3)                              # nose
    h.limb((0.6, 0, 0.82), (0.58, 0, 0.66), 0.035, 0.01, mat(beard), segs=4, flat=0.6)               # beard
    for side in (1, -1):
        # horns sweep back and curl down: three segments
        a0, a1, a2, a3 = ((0.5, side * 0.05, 1.03), (0.44, side * 0.09, 1.16), (0.32, side * 0.13, 1.2),
                          (0.24, side * 0.15, 1.1))
        h.limb(a0, a1, 0.035, 0.03, mat(horn), segs=5)
        h.limb(a1, a2, 0.03, 0.022, mat(shade(horn, 1.1)), segs=5)
        h.limb(a2, a3, 0.022, 0.008, mat(shade(horn, 1.2)), segs=5)
        h.limb((0.46, side * 0.08, 0.98), (0.42, side * 0.2, 0.95), 0.035, 0.008, mat(face), segs=4, flat=0.4)   # ears
    eyes(h, 0.58, 0.07, 0.98, 0.018, mat(DARK_EYE), pupil=mat((220, 190, 90)), M=M)
    t = M.part("tail", (-0.45, 0, 0.72), "tail")
    t.limb((-0.45, 0, 0.72), (-0.53, 0, 0.82), 0.045, 0.02, mat(belly), segs=5, flat=0.7)               # perky tail
    quad_legs(M, 0.24, -0.3, 0.11, 0.48, 0.05, 0.032, mat(legc), hoof_m=mat(hoof))
    pet_armor(M, -0.05, 0.8, 0.3, 0.2, 0.1)
    M.attach("mouth", (0.68, 0, 0.82), "head")
    M.attach("head_top", (0.46, 0, 1.12), "head")
    return M


MODELS = {"goat": goat}
