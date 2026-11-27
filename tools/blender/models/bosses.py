"""Bosses (settings.BOSSES): titan, brood, wraith, mire, colossus. Colours from art_extra.py / art_swamp.py.
Glowing spots (eyes, cores, lava) have glow_* / eye_* attachment points: the game puts a light there at night."""
import math
import random

from lowpoly import Model, eyes, glow, mat, shade

from zombies import _spider


def _giant(M, rock_cols, crack, eye_c, seed, height=4.6, lumpy=0.16):
    """A big rocky humanoid: stubby pillar legs, boulder torso, head sunk between the shoulders,
    long arms with boulder fists. rock_cols = (body, chest, head, arm, fist)."""
    body_c, chest_c, head_c, arm_c, fist_c = rock_cols
    s = height / 4.6
    rnd = random.Random(seed)
    b = M.part("body", (0, 0, 1.6 * s), "body")
    b.rock((0, 0, 2.6 * s), (1.0 * s, 1.35 * s, 1.15 * s), mat(body_c), sub=1, jitter=lumpy, seed=seed)
    b.rock((0.45 * s, 0, 2.5 * s), (0.6 * s, 0.9 * s, 0.75 * s), mat(chest_c), sub=1, jitter=lumpy, seed=seed + 1)
    b.rock((-0.1 * s, 0, 1.55 * s), (0.7 * s, 0.85 * s, 0.5 * s), mat(shade(body_c, 0.85)), sub=1, jitter=lumpy,
           seed=seed + 2)
    for k in range(9):         # glowing cracks / seams over the chest and back
        a = rnd.uniform(-2.2, 2.2)
        z = rnd.uniform(1.8, 3.3) * s
        x, y = math.cos(a) * 0.98 * s, math.sin(a) * 1.25 * s
        b.box((x, y, z), (0.1 * s, 0.1 * s, rnd.uniform(0.3, 0.6) * s), glow(crack),
              rot=(rnd.uniform(-40, 40), 0, math.degrees(a)))
    M.attach("glow_core", (0.95 * s, 0, 2.6 * s), "body")
    h = M.part("head", (0.5 * s, 0, 3.35 * s), "head")
    h.rock((0.75 * s, 0, 3.55 * s), (0.45 * s, 0.48 * s, 0.4 * s), mat(head_c), sub=1, jitter=0.1, seed=seed + 3)
    h.box((1.08 * s, 0, 3.66 * s), (0.12 * s, 0.7 * s, 0.12 * s), mat(shade(head_c, 0.7)))   # heavy brow
    eyes(h, 1.1 * s, 0.18 * s, 3.55 * s, 0.075 * s, glow(eye_c), M=M)
    for side, nm in ((1, "arm_l"), (-1, "arm_r")):
        sh = (0.1 * s, side * 1.25 * s, 3.1 * s)
        a = M.part(nm, sh, nm)
        a.rock((0.1 * s, side * 1.55 * s, 3.2 * s), (0.55 * s, 0.5 * s, 0.45 * s), mat(shade(body_c, 1.08)), sub=1,
               jitter=lumpy, seed=seed + 4)                                                     # shoulder boulder
        a.limb((0.1 * s, side * 1.55 * s, 2.9 * s), (0.5 * s, side * 1.7 * s, 1.6 * s), 0.38 * s, 0.32 * s,
               mat(arm_c), segs=6)
        a.rock((0.65 * s, side * 1.72 * s, 1.15 * s), (0.6 * s, 0.55 * s, 0.55 * s), mat(fist_c), sub=1,
               jitter=lumpy, seed=seed + 5)
        a.box((0.8 * s, side * 1.72 * s, 1.35 * s), (0.08 * s, 0.07 * s, 0.35 * s), glow(crack), rot=(0, 20, 0))
        M.attach("hand_" + nm[-1], (0.9 * s, side * 1.72 * s, 1.0 * s), nm)
    for side, nm, role in ((1, "leg_l", "leg_a"), (-1, "leg_r", "leg_b")):
        lg = M.part(nm, (0, side * 0.6 * s, 1.5 * s), role)
        lg.rock((0, side * 0.62 * s, 0.85 * s), (0.45 * s, 0.42 * s, 0.85 * s), mat(shade(body_c, 0.9)), sub=1,
                jitter=lumpy * 0.8, seed=seed + 6)
        lg.box((0.15 * s, side * 0.62 * s, 0.14 * s), (0.9 * s, 0.7 * s, 0.28 * s), mat(shade(body_c, 0.75)),
               taper=0.8)
    return b, h


def titan():
    M = Model("titan", {"anim": {"stride": 0.3, "bob": 0.08, "nod": 0.05, "arms": "swing", "breathe": 0.025,
                                 "lunge": 0.25}, "stride_len": 3.0, "height": 4.6})
    _giant(M, ((110, 96, 80), (128, 112, 92), (138, 120, 98), (96, 84, 70), (118, 104, 88)), (255, 140, 40),
           (255, 180, 60), 21)
    return M


def colossus():
    M = Model("colossus", {"anim": {"stride": 0.3, "bob": 0.08, "nod": 0.05, "arms": "swing", "breathe": 0.03,
                                    "lunge": 0.3}, "stride_len": 3.2, "height": 5.2})
    b, h = _giant(M, ((66, 32, 26), (80, 38, 28), (90, 42, 30), (60, 30, 24), (90, 40, 26)), (255, 120, 30),
                  (255, 240, 140), 8, height=5.2, lumpy=0.12)
    s = 5.2 / 4.6
    for k in range(5):          # flaming crown
        a = -1.0 + k * 0.5
        base = (0.72 * s + math.cos(a) * 0.3 * s, math.sin(a) * 0.38 * s, 3.85 * s)
        h.limb(base, (base[0] - 0.05 * s, base[1] * 1.3, 4.45 * s - abs(k - 2) * 0.12 * s), 0.12 * s, 0.0,
               glow((255, 170, 40)), segs=4)
    for side in (1, -1):        # molten shoulder vents
        b.limb((0.0, side * 1.0 * s, 3.4 * s), (-0.1 * s, side * 1.1 * s, 3.9 * s), 0.18 * s, 0.0, glow((255, 120, 30)),
               segs=4)
    M.attach("glow_crown", (0.7 * s, 0, 4.3 * s), "head")
    return M


def brood():
    M = Model("brood", {"anim": {"stride": 0.35, "bob": 0.04, "nod": 0.06, "breathe": 0.03, "lunge": 0.3},
                        "stride_len": 2.2, "height": 1.9})
    b, h = _spider(M, (0, 0, 1.0), (1.25, 0.95, 0.8), (0.55, 0.55, 0.45), (0.35, 0.38, 0.32),
                   ((110, 150, 60), (96, 130, 54), (50, 70, 34)), 2.3, 0.09, 1.0, nlegs=4,
                   eye_m=glow((255, 60, 50)),
                   eye_pos=((0.28, 0.12, 0.12), (0.3, -0.12, 0.12), (0.26, 0.22, 0.02), (0.26, -0.22, 0.02)),
                   mandible=mat((40, 50, 26)))
    rnd = random.Random(16)
    ax = -0.55 - 1.25 * 0.8
    for k in range(9):          # egg sacs on the abdomen
        a = rnd.uniform(0, math.tau)
        el = rnd.uniform(0.2, 1.1)
        p = (ax + math.cos(el) * math.cos(a) * 1.1, math.cos(el) * math.sin(a) * 0.85, 1.2 + math.sin(el) * 0.75)
        b.ball(p, (0.2, 0.17, 0.16), mat((210, 230, 140)), segs=6, rings=4)
    b.ball((0.0, 0, 1.15), (0.6, 0.45, 0.25), mat((80, 112, 46)), segs=7, rings=4)            # thorax plate
    M.attach("glow_core", (0.95, 0, 1.0), "head")
    return M


def wraith():
    M = Model("wraith", {"anim": {"hover": 0.55, "float": 0.18, "nod": 0.05, "arms": "reach", "sway": 0.25,
                                  "breathe": 0.03, "lunge": 0.3}, "stride_len": 2.0, "height": 3.6})
    cloak, inner, trim, ice = (190, 220, 245), (220, 236, 250), (120, 160, 210), (230, 245, 255)
    b = M.part("body", (0, 0, 1.5), "body")
    # tattered cloak: a ring of long ragged flaps around a cone
    b.cyl((0, 0, 1.55), 0.85, 2.2, mat(cloak), segs=9, r2=0.38, caps=False)
    for k in range(12):
        a = k / 12 * math.tau
        r0, r1 = 0.82, 0.95 + (0.15 if k % 2 else 0.0)
        z1 = 0.2 - (0.35 if k % 2 else 0.0)
        p0 = (math.cos(a) * r0, math.sin(a) * r0, 0.55)
        p1 = (math.cos(a + 0.28) * r0, math.sin(a + 0.28) * r0, 0.55)
        tip = (math.cos(a + 0.14) * r1, math.sin(a + 0.14) * r1, z1)
        b.tri([p0, p1, tip], mat(trim if k % 3 == 0 else cloak), thick=0.04)
    b.cyl((0.05, 0, 2.55), 0.45, 0.5, mat(inner), segs=8, r2=0.55)                              # shoulders
    h = M.part("head", (0.1, 0, 2.8), "head")
    h.ball((0.2, 0, 3.1), (0.42, 0.4, 0.48), mat(inner), segs=8, rings=5)                        # hood
    h.limb((0.0, 0, 3.4), (-0.35, 0, 3.75), 0.25, 0.0, mat(inner), segs=6)                       # hood point
    h.ball((0.42, 0, 3.05), (0.24, 0.27, 0.3), mat((26, 34, 56)), segs=7, rings=4)              # dark face
    eyes(h, 0.62, 0.11, 3.08, 0.055, glow((80, 200, 255)), M=M)
    for side, nm in ((1, "arm_l"), (-1, "arm_r")):
        sh = (0.15, side * 0.5, 2.6)
        a = M.part(nm, sh, nm)
        a.limb(sh, (0.75, side * 0.75, 2.2), 0.16, 0.1, mat(cloak), segs=5)
        a.limb((0.75, side * 0.75, 2.2), (1.2, side * 0.85, 2.15), 0.09, 0.05, mat(inner), segs=5)
        for k in range(3):      # icy claws
            a.limb((1.2, side * 0.85, 2.15), (1.55, side * (0.75 + k * 0.12), 2.05 + k * 0.07), 0.04, 0.0,
                   glow(ice), segs=4)
        M.attach("hand_" + nm[-1], (1.4, side * 0.85, 2.1), nm)
    t = M.part("shards", (0, 0, 2.0), "tail")         # orbiting ice shards (swing with the "tail" wag)
    for k in range(6):
        a = k / 6 * math.tau
        p = (math.cos(a) * 1.35, math.sin(a) * 1.35, 1.6 + 0.5 * math.sin(a * 2))
        t.limb((p[0], p[1], p[2] - 0.25), (p[0], p[1], p[2] + 0.3), 0.1, 0.0, glow((200, 235, 255)), segs=4)
        t.limb((p[0], p[1], p[2] - 0.25), (p[0], p[1], p[2] - 0.45), 0.1, 0.0, glow((170, 215, 250)), segs=4)
    M.attach("glow_core", (0.2, 0, 2.3), "body")
    return M


def mire():
    M = Model("mire", {"anim": {"stride": 0.35, "bob": 0.05, "nod": 0.08, "wag": 0.35, "breathe": 0.03,
                                "lunge": 0.4, "jaw": 0.5}, "stride_len": 2.4, "height": 1.9})
    mud, moss, head_c, maw, tooth = (66, 74, 44), (80, 96, 52), (74, 84, 50), (40, 26, 22), (226, 220, 190)
    reed1, reed2, cap, root, root2, claw = ((120, 140, 64), (150, 150, 76), (90, 230, 200), (52, 40, 28),
                                           (86, 66, 42), (200, 190, 150))
    rnd = random.Random(5100)
    b = M.part("body", (0, 0, 0.9), "body")
    b.rock((-0.3, 0, 0.95), (1.7, 1.05, 0.75), mat(mud), sub=2, jitter=0.07, seed=51)
    b.rock((-0.4, 0, 1.3), (1.3, 0.8, 0.45), mat(moss), sub=1, jitter=0.1, seed=52)
    for k in range(10):       # reeds growing out of its back
        x, y = rnd.uniform(-1.4, 0.6), rnd.uniform(-0.6, 0.6)
        b.limb((x, y, 1.45), (x - rnd.uniform(0.1, 0.3), y * 1.3, 1.45 + rnd.uniform(0.4, 0.8)), 0.03, 0.005,
               mat(rnd.choice([reed1, reed2])), segs=3)
    for x, y, r in ((-0.9, 0.35, 0.18), (-0.5, -0.45, 0.15), (-1.3, -0.1, 0.13), (-0.1, 0.4, 0.12)):
        b.cyl((x, y, 1.62), 0.04, 0.16, mat((220, 210, 180)), segs=4)
        b.ball((x, y, 1.72), (r, r, r * 0.55), glow(cap), segs=6, rings=3)                    # glowcaps
        M.attach(f"glow_cap{len(M.points)}", (x, y, 1.8), "body")
    t = M.part("tail", (-1.9, 0, 0.8), "tail")
    t.limb((-1.9, 0, 0.8), (-3.0, 0, 0.45), 0.5, 0.25, mat(mud), segs=6, flat=0.8)
    t.limb((-3.0, 0, 0.45), (-3.7, 0, 0.3), 0.25, 0.05, mat(shade(mud, 0.9)), segs=5, flat=0.8)
    for k in range(4):
        x = -2.1 - k * 0.4
        t.limb((x, 0, 0.95 - k * 0.12), (x - 0.15, 0, 1.2 - k * 0.14), 0.1, 0.0, mat(moss), segs=4, flat=0.5)
    h = M.part("head", (1.2, 0, 1.0), "head")
    h.box((1.75, 0, 1.08), (1.2, 1.2, 0.42), mat(head_c), taper=0.75)                           # wide flat skull
    for side in (1, -1):      # bulging frog eyes on top
        h.ball((1.55, side * 0.42, 1.38), 0.2, mat(head_c), segs=6, rings=4)
        h.ball((1.68, side * 0.45, 1.42), 0.11, glow((220, 255, 120)), segs=6, rings=4)
        h.ball((1.77, side * 0.46, 1.43), 0.045, mat((40, 60, 20)), segs=4, rings=3)
        M.attach("eye_" + ("l" if side > 0 else "r"), (1.8, side * 0.46, 1.43), "head")
    for k in range(6):
        y = -0.45 + k * 0.18
        h.limb((2.25, y, 0.92), (2.3, y, 0.78), 0.05, 0.0, mat(tooth), segs=3)
    j = M.part("jaw", (1.25, 0, 0.82), "jaw")
    j.box((1.75, 0, 0.72), (1.15, 1.1, 0.22), mat(shade(head_c, 0.85)), taper=1.1)
    j.box((1.85, 0, 0.84), (0.9, 0.9, 0.04), mat(maw))
    for k in range(5):
        y = -0.36 + k * 0.18
        j.limb((2.22, y, 0.8), (2.25, y, 0.95), 0.045, 0.0, mat(tooth), segs=3)
    M.attach("mouth", (2.2, 0, 0.85), "head")
    for nm, x, side in (("leg_fl", 0.8, 1), ("leg_fr", 0.8, -1), ("leg_bl", -1.2, 1), ("leg_br", -1.2, -1)):
        role = "leg_a" if nm in ("leg_fl", "leg_br") else "leg_b"
        lg = M.part(nm, (x, side * 0.85, 0.85), role)
        knee = (x + 0.1, side * 1.35, 0.6)
        lg.limb((x, side * 0.85, 0.85), knee, 0.28, 0.2, mat(shade(mud, 0.9)), segs=5)
        lg.limb(knee, (x + 0.25, side * 1.45, 0.05), 0.2, 0.16, mat(root2), segs=5)
        for k in range(3):    # hooked claws
            lg.limb((x + 0.3, side * 1.45, 0.08), (x + 0.6, side * (1.3 + k * 0.15), 0.02), 0.06, 0.0, mat(claw),
                    segs=3)
    for side, nm in ((1, "arm_l"), (-1, "arm_r")):    # two long root-arms reaching forward
        a = M.part(nm, (0.6, side * 0.9, 1.2), nm)
        a.limb((0.6, side * 0.9, 1.2), (1.6, side * 1.3, 1.1), 0.16, 0.12, mat(root), segs=5)
        a.limb((1.6, side * 1.3, 1.1), (2.4, side * 1.2, 0.8), 0.12, 0.07, mat(root2), segs=5)
        for k in range(3):
            a.limb((2.4, side * 1.2, 0.8), (2.7, side * (1.05 + k * 0.14), 0.7 + k * 0.05), 0.05, 0.0, mat(claw),
                   segs=3)
        for k in range(3):
            x = 1.0 + k * 0.4
            a.limb((x, side * 1.12, 1.2), (x + 0.05, side * 1.2, 1.35), 0.05, 0.0, mat(root), segs=3)
        M.attach("hand_" + nm[-1], (2.6, side * 1.2, 0.75), nm)
    return M


MODELS = {"titan": titan, "brood": brood, "wraith": wraith, "mire": mire, "colossus": colossus}
