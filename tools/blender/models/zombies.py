"""Hostile non-bosses (settings.ZOMBIES): walker, runner, brute (art.py), drowned (art_swamp.py),
broodling, crawler, golem (art_extra.py). Eyes are bright "glow" materials ON the face, with eye_l /
eye_r attachment points on the head so the game's night glow sits exactly on them."""
import math

from lowpoly import Model, eyes, glow, humanoid, mat, shade

RED_EYE = (255, 70, 50)


def _rot_stains(p, c, r, seed, m):
    """A few dark stains / holes on a shirt (box-ish torso centred at c)."""
    import random
    rnd = random.Random(seed)
    for _ in range(3):
        p.box((c[0] + r[0] * 0.52, c[1] + rnd.uniform(-r[1], r[1]) * 0.6, c[2] + rnd.uniform(-r[2], r[2]) * 0.5),
              (0.02, rnd.uniform(0.05, 0.09), rnd.uniform(0.05, 0.09)), m)


def _zombie(name, skin, shirt, pants, height, bulk, lean, meta, seed):
    M = Model(name, meta)
    H = humanoid(M, skin, shirt, pants, shade(pants, 0.7), height=height, bulk=bulk, lean=lean, arms="reach",
                 head_r=0.15, eye_m=glow(RED_EYE), eye_r=0.026)
    s, hip, fx = H["s"], H["hip"], H["fx"]
    zc = hip + 0.33 * s
    _rot_stains(H["body"], (fx(zc), 0, zc), (0.13 * bulk, 0.22 * bulk, 0.25 * s), seed, mat((80, 24, 24)))
    hc = H["head_c"]
    H["head"].ball((hc[0] - 0.02, 0.06 * s, hc[2] + 0.09 * s), 0.06 * s, mat(shade(skin, 0.7)), segs=5, rings=3)  # rot
    H["head"].box((hc[0] + 0.12 * s, 0, hc[2] - 0.07 * s), (0.05, 0.12 * s, 0.035 * s), mat((60, 20, 22)))   # mouth
    M.attach("head_top", (hc[0], 0, hc[2] + 0.17 * s), "head")
    return M, H


def walker():
    M, H = _zombie("walker", (120, 156, 104), (96, 78, 64), (64, 60, 66), 1.8, 1.0, 14,
                   {"anim": {"stride": 0.45, "bob": 0.04, "nod": 0.12, "arms": "reach", "sway": 0.25, "lunge": 0.35},
                    "stride_len": 1.1, "height": 1.8}, 1)
    return M


def runner():
    M, H = _zombie("runner", (176, 184, 150), (60, 76, 110), (52, 52, 58), 1.72, 0.86, 26,
                   {"anim": {"stride": 0.8, "bob": 0.06, "nod": 0.15, "arms": "reach", "sway": 0.4, "lunge": 0.45},
                    "stride_len": 1.5, "height": 1.7}, 2)
    return M


def brute():
    M, H = _zombie("brute", (128, 120, 150), (70, 50, 46), (56, 48, 52), 2.35, 1.55, 12,
                   {"anim": {"stride": 0.35, "bob": 0.06, "nod": 0.08, "arms": "reach", "sway": 0.18, "lunge": 0.3,
                             "breathe": 0.02}, "stride_len": 1.2, "height": 2.35}, 3)
    s = H["s"]
    for nm in ("arm_l", "arm_r"):      # huge fists
        hx = H["hand_" + nm[-1]]
        H[nm].ball(hx, 0.13 * s, mat(shade((128, 120, 150), 0.92)), segs=6, rings=4, jitter=0.01, seed=4)
    hip, fx = H["hip"], H["fx"]
    H["body"].ball((fx(hip + 0.5 * s) - 0.05, 0, hip + 0.55 * s), (0.18, 0.36, 0.14), mat((70, 50, 46)), segs=7,
                   rings=4)    # hunched shoulders
    return M


def drowned():
    M, H = _zombie("drowned", (112, 150, 140), (62, 76, 62), (50, 62, 56), 1.85, 1.08, 16,
                   {"anim": {"stride": 0.38, "bob": 0.035, "nod": 0.1, "arms": "reach", "sway": 0.3, "lunge": 0.3},
                    "stride_len": 1.0, "height": 1.85}, 4)
    s, hip, fx = H["s"], H["hip"], H["fx"]
    weed, drip = mat((70, 110, 50)), mat((60, 84, 70))
    import random
    rnd = random.Random(5000)
    for k in range(6):       # weeds hanging off the shoulders and arms
        side = 1 if k % 2 else -1
        x = fx(hip + 0.5 * s) + rnd.uniform(-0.1, 0.1)
        y = side * rnd.uniform(0.05, 0.25)
        H["body"].limb((x, y, hip + 0.58 * s), (x - 0.06, y * 1.15, hip + rnd.uniform(0.05, 0.25) * s), 0.025, 0.006,
                       weed, segs=3)
    for nm in ("arm_l", "arm_r"):
        hx = H["hand_" + nm[-1]]
        H[nm].limb((hx[0] - 0.25, hx[1], hx[2] - 0.03), (hx[0] - 0.28, hx[1], hx[2] - 0.3), 0.02, 0.004, weed,
                   segs=3)
    hc = H["head_c"]
    H["head"].ball((hc[0] - 0.05, 0, hc[2] + 0.1 * s), (0.15 * s, 0.15 * s, 0.07 * s), drip, segs=6, rings=3)  # muck
    for side in (1, -1):     # pale swamp-light eyes over the red ones
        H["head"].ball((hc[0] + 0.15 * s * 0.98, side * 0.15 * s * 0.42, hc[2] + 0.15 * s * 0.15), 0.02 * s,
                       glow((170, 255, 140)), segs=5, rings=3)
    return M


def _spider(M, body_c, abd_r, thx_r, head_r, cols, leg_len, leg_r, z, nlegs=3, eye_m=None, eye_pos=(),
            mandible=None):
    """A many-legged critter: body + head + legs as sleg_a / sleg_b side legs."""
    bodyc, headc, legc = cols
    b = M.part("body", (0, 0, z), "body")
    b.ball((-thx_r[0] - abd_r[0] * 0.8, 0, z + abd_r[2] * 0.25), abd_r, mat(bodyc), segs=8, rings=5)
    b.ball((0, 0, z), thx_r, mat(shade(bodyc, 1.1)), segs=7, rings=4)
    h = M.part("head", (thx_r[0] * 0.8, 0, z), "head")
    hx = thx_r[0] + head_r[0] * 0.7
    h.ball((hx, 0, z), head_r, mat(headc), segs=7, rings=4)
    for i, (dx, dy, dz) in enumerate(eye_pos):
        h.ball((hx + dx, dy, z + dz), 0.018 * head_r[0] / 0.08, eye_m, segs=5, rings=3)
        M.attach(f"eye_{i}", (hx + dx + 0.01, dy, z + dz), "head")
    if mandible is not None:
        for side in (1, -1):
            h.limb((hx + head_r[0] * 0.8, side * head_r[1] * 0.4, z - head_r[2] * 0.4),
                   (hx + head_r[0] * 1.5, side * head_r[1] * 0.15, z - head_r[2] * 0.9), head_r[0] * 0.18, 0.0,
                   mandible, segs=4)
    for k in range(nlegs):
        x = thx_r[0] * (0.6 - 1.2 * k / max(1, nlegs - 1))
        for side, sname in ((1, "l"), (-1, "r")):
            role = "sleg_a" if (k + (side > 0)) % 2 else "sleg_b"
            lg = M.part(f"sleg_{sname}{k + 1}", (x, side * thx_r[1] * 0.8, z), role)
            spread = (0.5 - k / max(1, nlegs - 1)) * 0.9
            kx = x + math.sin(spread) * leg_len * 0.5
            ky = side * (thx_r[1] + math.cos(spread) * leg_len * 0.5)
            knee = (kx, ky, z + leg_len * 0.35)
            foot = (x + math.sin(spread) * leg_len * 0.95, side * (thx_r[1] + math.cos(spread) * leg_len * 0.85), 0.0)
            lg.limb((x, side * thx_r[1] * 0.8, z), knee, leg_r, leg_r * 0.8, mat(legc), segs=4)
            lg.limb(knee, foot, leg_r * 0.8, leg_r * 0.3, mat(shade(legc, 0.8)), segs=4)
    return b, h


def broodling():
    M = Model("broodling", {"anim": {"stride": 0.5, "bob": 0.02, "nod": 0.1, "lunge": 0.3},
                            "stride_len": 0.6, "height": 0.35})
    _spider(M, (0, 0, 0.16), (0.14, 0.12, 0.1), (0.08, 0.08, 0.07), (0.06, 0.06, 0.055),
            ((110, 160, 60), (140, 190, 70), (60, 90, 40)), 0.32, 0.014, 0.16, nlegs=3, eye_m=glow((255, 80, 60)),
            eye_pos=((0.05, 0.025, 0.02), (0.05, -0.025, 0.02)), mandible=mat((50, 60, 30)))
    return M


def crawler():
    M = Model("crawler", {"anim": {"stride": 0.45, "bob": 0.02, "nod": 0.08, "lunge": 0.35},
                          "stride_len": 0.9, "height": 0.6})
    b, h = _spider(M, (0, 0, 0.3), (0.3, 0.22, 0.17), (0.17, 0.16, 0.13), (0.11, 0.12, 0.1),
                   ((78, 66, 96), (96, 82, 116), (60, 52, 70)), 0.7, 0.03, 0.3, nlegs=4,
                   eye_m=glow((120, 255, 160)),
                   eye_pos=((0.09, 0.05, 0.04), (0.1, 0.0, 0.05), (0.09, -0.05, 0.04)), mandible=mat((200, 190, 170)))
    for k in range(4):        # armour ridges along the back
        b.box((-0.2 - k * 0.12, 0, 0.47 - k * 0.01), (0.06, 0.3, 0.05), mat((62, 52, 78)))
    return M


def golem():
    M = Model("golem", {"anim": {"stride": 0.3, "bob": 0.05, "nod": 0.05, "arms": "reach", "sway": 0.12,
                                 "lunge": 0.3, "breathe": 0.015}, "stride_len": 1.3, "height": 2.3})
    rock, head_c, fist, vein = (92, 88, 100), (112, 108, 120), (104, 100, 112), (130, 220, 255)
    b = M.part("body", (0, 0, 1.0), "body")
    b.rock((0, 0, 1.4), (0.45, 0.6, 0.55), mat(rock), sub=1, jitter=0.14, seed=7)
    b.rock((0.0, 0, 0.95), (0.32, 0.4, 0.25), mat(shade(rock, 0.9)), sub=1, jitter=0.12, seed=8)
    for k, (y, z) in enumerate(((0.25, 1.55), (-0.2, 1.3), (0.05, 1.7), (-0.32, 1.6), (0.3, 1.2))):
        b.box((0.4, y, z), (0.08, 0.06, 0.16), glow(vein), rot=(25 * k, 0, 0))   # crystal veins on the chest
    for side in (1, -1):
        b.limb((0.0, side * 0.32, 1.9), (0.05, side * 0.36, 2.2), 0.08, 0.0, glow((160, 230, 255)), segs=4)
    h = M.part("head", (0.15, 0, 1.85), "head")
    h.rock((0.3, 0, 1.98), (0.22, 0.24, 0.2), mat(head_c), sub=1, jitter=0.1, seed=9)
    eyes(h, 0.48, 0.09, 2.0, 0.035, glow((160, 240, 255)), M=M)
    for side, nm in ((1, "arm_l"), (-1, "arm_r")):
        a = M.part(nm, (0.05, side * 0.6, 1.7), nm)
        a.rock((0.15, side * 0.68, 1.55), (0.2, 0.18, 0.25), mat(shade(rock, 1.05)), sub=1, jitter=0.1, seed=11)
        a.rock((0.42, side * 0.66, 1.25), (0.26, 0.24, 0.24), mat(fist), sub=1, jitter=0.12, seed=12)
        M.attach("hand_" + nm[-1], (0.6, side * 0.66, 1.2), nm)
    for side, nm, role in ((1, "leg_l", "leg_a"), (-1, "leg_r", "leg_b")):
        lg = M.part(nm, (0, side * 0.25, 0.9), role)
        lg.rock((0, side * 0.27, 0.5), (0.2, 0.18, 0.42), mat(shade(rock, 0.85)), sub=1, jitter=0.1, seed=13)
        lg.box((0.06, side * 0.27, 0.08), (0.36, 0.26, 0.16), mat(shade(rock, 0.75)))
    return M


MODELS = {"walker": walker, "runner": runner, "brute": brute, "drowned": drowned, "broodling": broodling,
          "crawler": crawler, "golem": golem}
