"""
venom.py - Brood Fang poison (any weapon with "poison" in settings.ITEMS).

A hit with a poison weapon leaves venom in the enemy: it takes POISON_DPS damage a second for
POISON_SECONDS (another hit just refreshes the timer, it doesn't stack). Unlike burning and chilling,
venom works on bosses too. Only the host (or a solo game) runs this - clients just see the green
puffs, which reach them like every other particle burst.
"""
import random

from settings import POISON_DPS, POISON_SECONDS
from world import Boss

PUFF = (130, 230, 70)


def apply(z, w, by):
    """Called from hit_enemy: a poison weapon just hit z."""
    if w and w.get("poison") and z.hp > 0:
        z.poison = POISON_SECONDS
        z.poison_by = by


def tick(game, dt):
    """Every frame on the host: hurt every poisoned zombie / boss, and finish off any that die of it."""
    for L in game.layers.values():
        for z in [e for e in L.zombies if getattr(e, "poison", 0) > 0] + \
                 [b for b in L.bosses if getattr(b, "poison", 0) > 0]:
            z.poison -= dt
            boss = isinstance(z, Boss)
            if boss and z.state == "flee":
                z.poison = 0
                continue
            z.hp -= POISON_DPS * dt
            if random.random() < dt * 6:
                game.burst(z.center_x, z.center_y, PUFF, 2, 45, 3, 0.6, layer=z.layer)
            if z.hp <= 0:
                z.poison = 0
                by = getattr(z, "poison_by", None)
                by = by if by is not None and by.id in game.players else None
                if boss:
                    game.kill_boss(z, by)
                else:
                    game.kill_zombie(z, by)
