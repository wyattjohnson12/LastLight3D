"""The Ashlands' creatures (ashlands.py): the Fire Beetle. Colours come from art_ash.py."""
import math

from lowpoly import Model, glow, mat, shade

SHELL, BELLY, LEG, HEAD = (70, 26, 22), (40, 18, 16), (34, 22, 20), (52, 22, 20)
LAVA, HOT = (255, 120, 30), (255, 214, 120)


def fire_beetle():
    """A big armoured beetle (~0.55 m tall): two domed wing cases split down the middle with lava glowing in
    the cracks, a horned head with mandibles, six legs sticking out sideways."""
    M = Model("fire_beetle", {"anim": {"stride": 0.45, "bob": 0.015, "nod": 0.08, "lunge": 0.3, "breathe": 0.02},
                              "stride_len": 0.7, "height": 0.55})
    z = 0.28
    b = M.part("body", (0, 0, z), "body")
    b.ball((-0.05, 0, z - 0.06), (0.36, 0.26, 0.12), mat(BELLY), segs=8, rings=4)            # underside
    for side in (1, -1):                                                                     # wing cases
        b.ball((-0.07, side * 0.12, z + 0.04), (0.36, 0.14, 0.2), mat(SHELL), segs=8, rings=5)

    def top(x, y):          # height of the wing-case surface at (x, y)
        q = 1 - ((x + 0.07) / 0.36) ** 2 - ((abs(y) - 0.12) / 0.14) ** 2
        return z + 0.04 + 0.2 * math.sqrt(max(0.0, q))

    for x in (-0.3, -0.18, -0.06, 0.06, 0.16):                                               # the split, glowing
        b.box((x, 0, top(x, 0.0) + 0.01), (0.13, 0.04, 0.07), glow(LAVA))
    for k, (x, y, ang) in enumerate(((0.08, 0.17, 20), (-0.12, 0.2, -10), (-0.25, 0.13, 30), (0.0, 0.09, -25),
                                     (-0.2, 0.06, 10), (-0.32, 0.18, -20))):
        for side in (1, -1):                                                                 # lava seams
            b.box((x, side * y, top(x, y) - 0.004), (0.12, 0.024, 0.03), glow(LAVA if k % 2 else HOT),
                  rot=(0, 0, side * ang))
    b.ball((0.24, 0, z + 0.02), (0.12, 0.17, 0.12), mat(shade(SHELL, 0.85)), segs=7, rings=4)  # thorax plate
    h = M.part("head", (0.32, 0, z), "head")
    h.ball((0.4, 0, z), (0.1, 0.12, 0.09), mat(HEAD), segs=7, rings=4)
    h.limb((0.44, 0, z + 0.06), (0.56, 0, z + 0.22), 0.035, 0.0, mat(shade(SHELL, 1.2)), segs=4)  # horn
    for side in (1, -1):
        h.limb((0.47, side * 0.06, z - 0.03), (0.6, side * 0.03, z - 0.05), 0.022, 0.0, mat((60, 30, 22)), segs=4)
        h.ball((0.48, side * 0.065, z + 0.03), 0.022, glow((255, 220, 100)), segs=5, rings=3)
        M.attach(f"eye_{'l' if side > 0 else 'r'}", (0.5, side * 0.065, z + 0.03), "head")
    for k in range(3):                                                                       # six legs
        x = 0.16 - 0.17 * k
        for side, sname in ((1, "l"), (-1, "r")):
            role = "sleg_a" if (k + (side > 0)) % 2 else "sleg_b"
            lg = M.part(f"sleg_{sname}{k + 1}", (x, side * 0.16, z - 0.04), role)
            spread = (0.5 - k / 2) * 0.9
            knee = (x + math.sin(spread) * 0.14, side * (0.16 + math.cos(spread) * 0.17), z + 0.04)
            foot = (x + math.sin(spread) * 0.26, side * (0.16 + math.cos(spread) * 0.28), 0.0)
            lg.limb((x, side * 0.16, z - 0.04), knee, 0.036, 0.03, mat(LEG), segs=4)
            lg.limb(knee, foot, 0.03, 0.012, mat(shade(LEG, 0.8)), segs=4)
    M.attach("glow_back", (-0.07, 0, z + 0.24), "body")
    M.attach("mouth", (0.6, 0, z - 0.05), "head")
    return M


MODELS = {"fire_beetle": fire_beetle}
