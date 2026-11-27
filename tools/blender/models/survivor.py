"""The survivor (players and co-op friends). Colours from art.py _survivor_img / art_gear.py.
Recolourable per player: acc1 = jacket (art.JACKETS), acc2 = hair (art.HAIR).
Optional worn gear (shown when the player wears it, recoloured from art_gear's colours):
    armor  (acc3) - body armor shell + pauldrons
    helmet (acc4) - cap / helm over the head
    cloak  (acc5) - cloak hanging down the back
hand_r is where the held item (weapon / tool / torch) is drawn."""
from lowpoly import Model, eyes, humanoid, mat, shade

SKIN = (226, 182, 146)


def survivor():
    M = Model("survivor", {"anim": {"stride": 0.55, "bob": 0.035, "nod": 0.04, "arms": "swing"},
                           "stride_len": 1.4, "height": 1.8})
    jacket = mat((58, 104, 112), "acc1")
    H = humanoid(M, SKIN, (58, 104, 112), (62, 58, 66), (70, 50, 32), height=1.8, bulk=1.0, lean=4, arms="swing",
                 head_r=0.135, shirt_m=jacket)
    s, hip, fx = H["s"], H["hip"], H["fx"]
    hc, head, body = H["head_c"], H["head"], H["body"]
    hair = mat((84, 54, 34), "acc2")
    head.ball((hc[0] - 0.03, 0, hc[2] + 0.045), (0.14, 0.142, 0.13), hair, segs=7, rings=4)     # hair (back/top)
    eyes(head, hc[0] + 0.125, 0.05, hc[2] + 0.01, 0.017, mat((40, 30, 30)), M=M)
    head.box((hc[0] + 0.14, 0, hc[2] - 0.03), (0.04, 0.035, 0.05), mat(shade(SKIN, 0.9)))    # nose
    # backpack
    zc = hip + 0.36 * s
    body.box((fx(zc) - 0.2, 0, zc), (0.16, 0.34, 0.4), mat((122, 86, 52)), rot=(0, 4, 0))
    body.box((fx(zc) - 0.2, 0, zc + 0.22), (0.18, 0.36, 0.06), mat((64, 44, 26)))
    body.box((fx(zc) + 0.135, 0, hip + 0.12), (0.02, 0.46, 0.05), mat((70, 50, 30)))          # belt
    # optional gear
    arm = M.part("armor", (0, 0, hip), "body", opt="armor")
    am = mat((150, 156, 168), "acc3")
    arm.box((fx(zc) + 0.01, 0, zc + 0.02), (0.3, 0.5, 0.42), am, taper_y=1.12)
    for side in (1, -1):
        arm.ball((fx(hip + 0.52 * s), side * 0.27, hip + 0.54 * s), (0.11, 0.1, 0.07), mat((150, 156, 168), "acc3"),
                 segs=6, rings=3)
    helm = M.part("helmet", H["neck"], "head", opt="helmet")
    hm = mat((160, 166, 178), "acc4")
    helm.ball((hc[0] - 0.01, 0, hc[2] + 0.05), (0.155, 0.155, 0.13), hm, segs=8, rings=4)
    helm.box((hc[0], 0, hc[2] + 0.0), (0.27, 0.3, 0.035), hm)                                  # brim
    clo = M.part("cloak", (fx(hip + 0.55 * s), 0, hip + 0.55 * s), "body", opt="cloak")
    cm = mat((132, 134, 142), "acc5")
    top = hip + 0.58 * s
    clo.tri([(fx(top) - 0.1, 0.24, top), (fx(top) - 0.1, -0.24, top), (-0.36, -0.3, 0.3), (-0.36, 0.3, 0.3)], cm,
            thick=0.03)
    clo.box((fx(top) + 0.03, 0, top + 0.01), (0.2, 0.46, 0.05), cm)                            # collar
    M.attach("head_top", (hc[0], 0, hc[2] + 0.2), "head")
    return M


MODELS = {"survivor": survivor}
