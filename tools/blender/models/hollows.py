"""Crystal Hollows creatures (hollows.py / art_hollows.py): shard_crawler, hollow_bat, geode_golem.
Colours come from art_hollows.py's sprites. Crystals and eyes are "glow" materials so they shine in the dark."""
import math

from lowpoly import Model, eyes, glow, mat, shade
from zombies import _spider

ICE, VIOLET, PINK = (130, 230, 255), (200, 140, 255), (255, 120, 220)


def shard_crawler():
    """A crystal-backed cave spider: bigger and nastier than the cave crawler."""
    M = Model("shard_crawler", {"anim": {"stride": 0.5, "bob": 0.02, "nod": 0.08, "lunge": 0.4, "wag": 0.15},
                                "stride_len": 1.0, "height": 0.75})
    b, h = _spider(M, (0, 0, 0.34), (0.34, 0.26, 0.2), (0.19, 0.18, 0.14), (0.12, 0.13, 0.11),
                   ((62, 52, 98), (82, 70, 124), (44, 40, 70)), 0.8, 0.035, 0.34, nlegs=4,
                   eye_m=glow((150, 240, 255)),
                   eye_pos=((0.1, 0.05, 0.04), (0.11, 0.0, 0.055), (0.1, -0.05, 0.04)), mandible=mat((190, 200, 230)))
    # crystal spikes growing out of its back, leaning outwards
    spikes = ((-0.35, 0.0, 0.7, 0.26), (-0.22, 0.12, 0.62, 0.2), (-0.24, -0.13, 0.6, 0.2), (-0.5, 0.1, 0.56, 0.17),
              (-0.48, -0.1, 0.55, 0.16), (-0.08, 0.0, 0.55, 0.15))
    for k, (x, y, z, ln) in enumerate(spikes):
        top = (x - 0.08, y * 1.8, z + ln)
        b.limb((x, y, z - 0.08), top, 0.05, 0.0, glow(ICE if k % 2 == 0 else VIOLET), segs=4)
    return M


def hollow_bat():
    """A big pale-violet cave bat: flies (hover), flaps fast, glowing pink eyes."""
    M = Model("hollow_bat", {"anim": {"flap": 1.3, "hover": 0.9, "float": 0.12, "nod": 0.1, "lunge": 0.4},
                             "stride_len": 1.0, "height": 0.4})
    fur, wing, ear = (92, 74, 116), (70, 56, 92), (104, 86, 128)
    z = 0.12
    b = M.part("body", (0, 0, z), "body")
    b.ball((0, 0, z), (0.14, 0.1, 0.1), mat(fur), segs=7, rings=4)
    h = M.part("head", (0.1, 0, z + 0.02), "head")
    h.ball((0.17, 0, z + 0.03), 0.075, mat(shade(fur, 1.1)), segs=7, rings=4)
    for side in (1, -1):         # big ears
        h.tri([(0.15, side * 0.03, z + 0.08), (0.13, side * 0.08, z + 0.2), (0.2, side * 0.05, z + 0.1)],
              mat(ear), thick=0.01)
        h.limb((0.23, side * 0.012, z), (0.25, side * 0.01, z - 0.04), 0.008, 0.0, mat((240, 240, 250)), segs=3)  # fangs
    eyes(h, 0.235, 0.032, z + 0.05, 0.016, glow(PINK), M=M)
    for side, nm in ((1, "wing_l"), (-1, "wing_r")):
        w = M.part(nm, (0.02, side * 0.08, z + 0.03), nm)
        tips = [(0.06, side * 0.08, z + 0.03), (0.1, side * 0.32, z + 0.08), (0.0, side * 0.55, z + 0.05),
                (-0.06, side * 0.42, z + 0.02), (-0.14, side * 0.5, z + 0.0), (-0.1, side * 0.25, z + 0.0),
                (-0.08, side * 0.08, z + 0.02)]
        w.tri(tips, mat(wing), thick=0.008)
        for t in (tips[1], tips[2], tips[4]):          # finger bones
            w.limb((0.02, side * 0.08, z + 0.04), (t[0], t[1], t[2] + 0.005), 0.01, 0.005, mat(ear), segs=3)
    t = M.part("tail", (-0.12, 0, z), "tail")
    for side in (1, -1):         # dangling feet
        t.limb((-0.12, side * 0.04, z - 0.05), (-0.16, side * 0.05, z - 0.13), 0.012, 0.006, mat(shade(fur, 0.7)), segs=3)
    return M


def geode_golem():
    """A hulking rock golem with a cracked-open violet geode in its chest."""
    M = Model("geode_golem", {"anim": {"stride": 0.28, "bob": 0.05, "nod": 0.05, "arms": "reach", "sway": 0.1,
                                       "lunge": 0.35, "breathe": 0.02}, "stride_len": 1.4, "height": 2.6})
    rock, head_c, fist = (70, 68, 90), (88, 86, 108), (78, 76, 98)
    b = M.part("body", (0, 0, 1.1), "body")
    b.rock((0, 0, 1.55), (0.5, 0.68, 0.6), mat(rock), sub=1, jitter=0.15, seed=21)
    b.rock((0.0, 0, 1.05), (0.36, 0.45, 0.28), mat(shade(rock, 0.88)), sub=1, jitter=0.12, seed=22)
    b.ball((0.42, 0, 1.55), (0.12, 0.26, 0.26), mat((40, 20, 70)), segs=8, rings=4)      # the geode's hollow
    for k in range(9):           # crystals inside it, pointing out
        a = k / 9 * math.tau
        y, zz = math.cos(a) * 0.15, 1.55 + math.sin(a) * 0.15
        b.limb((0.44, y, zz), (0.62, y * 1.3, zz + math.sin(a) * 0.06), 0.05, 0.0, glow(VIOLET if k % 3 else PINK),
               segs=4)
    for side in (1, -1):         # crystal shards on the shoulders
        for j in range(3):
            x = -0.1 + j * 0.12
            b.limb((x, side * 0.45, 1.95), (x - 0.05, side * (0.6 + 0.05 * j), 2.3 + 0.08 * (j % 2)), 0.08, 0.0,
                   glow(ICE if j % 2 else VIOLET), segs=4)
    h = M.part("head", (0.15, 0, 2.05), "head")
    h.rock((0.32, 0, 2.18), (0.24, 0.26, 0.21), mat(head_c), sub=1, jitter=0.1, seed=23)
    eyes(h, 0.52, 0.1, 2.2, 0.04, glow((220, 170, 255)), M=M)
    for side, nm in ((1, "arm_l"), (-1, "arm_r")):
        a = M.part(nm, (0.05, side * 0.7, 1.85), nm)
        a.rock((0.15, side * 0.78, 1.68), (0.22, 0.2, 0.28), mat(shade(rock, 1.05)), sub=1, jitter=0.1, seed=24)
        a.rock((0.45, side * 0.76, 1.32), (0.3, 0.28, 0.28), mat(fist), sub=1, jitter=0.12, seed=25)
        a.limb((0.5, side * 0.76, 1.5), (0.62, side * 0.9, 1.7), 0.07, 0.0, glow(VIOLET), segs=4)
        M.attach("hand_" + nm[-1], (0.68, side * 0.76, 1.25), nm)
    for side, nm, role in ((1, "leg_l", "leg_a"), (-1, "leg_r", "leg_b")):
        lg = M.part(nm, (0, side * 0.28, 1.0), role)
        lg.rock((0, side * 0.3, 0.55), (0.23, 0.2, 0.47), mat(shade(rock, 0.85)), sub=1, jitter=0.1, seed=26)
        lg.box((0.06, side * 0.3, 0.09), (0.4, 0.3, 0.18), mat(shade(rock, 0.75)))
    return M


MODELS = {"shard_crawler": shard_crawler, "hollow_bat": hollow_bat, "geode_golem": geode_golem}
