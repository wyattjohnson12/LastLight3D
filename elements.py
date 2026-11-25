"""
elements.py - the type chart (like Pokemon): which attacks hurt which enemies more, or less.

Five attack elements: fire, frost, storm, earth, light.
They go round in a circle - each one beats the next:

    fire  -> melts frost
    frost -> cracks earth
    earth -> grounds storm
    storm -> rain puts out fire

and Light burns "shadow" things (the undead: zombies and the Frost Wraith).

An enemy's *types* decide what hurts it. Super effective = x2, resisted = x0.5, no effect = x0.
An enemy can have two types (they multiply), and anything without a type takes normal damage from
everything - so a brand new boss works straight away and only needs a "types" line to get weaknesses.

HOW TO GIVE A BOSS WEAKNESSES (new bosses too):
  * easiest: add  "types": ["earth"]  to its entry in BOSSES (settings.py), or
  * add a line to BOSS_TYPES below.
  Optional fine-tuning in the BOSSES entry:  "weak": {"light": 2.0},  "resist": {"fire": 0.5}
"""
from settings import BOSSES, ITEMS

ELEMENTS = ["fire", "frost", "storm", "earth", "light"]
ELEMENT_NAME = {"fire": "Fire", "frost": "Frost", "storm": "Storm", "earth": "Earth", "light": "Light",
                "shadow": "Shadow", "beast": "Beast"}
ELEMENT_COLOR = {"fire": (255, 140, 50), "frost": (150, 210, 255), "storm": (190, 170, 255),
                 "earth": (190, 150, 90), "light": (255, 236, 150), "shadow": (150, 110, 190),
                 "beast": (150, 200, 100)}

# What hurts each TYPE of enemy:  CHART[enemy type][attack element] = multiplier (missing = x1)
CHART = {
    "fire":   {"storm": 2.0, "frost": 0.5, "fire": 0.5},     # rain douses it; frost melts first
    "frost":  {"fire": 2.0, "earth": 0.5, "frost": 0.5},
    "earth":  {"frost": 2.0, "storm": 0.5, "earth": 0.5},
    "storm":  {"earth": 2.0, "fire": 0.5, "storm": 0.5},
    "shadow": {"light": 2.0},                                 # the undead
    "beast":  {"fire": 2.0},                                  # flesh and chitin burn
}

# Types for the bosses that ship with the game. New bosses: put "types" in their BOSSES entry instead.
BOSS_TYPES = {
    "titan": ["earth"],
    "brood": ["beast"],
    "wraith": ["frost", "shadow"],
    "colossus": ["fire"],
}
ENEMY_TYPES = {                 # ordinary enemies (keys from ZOMBIES in settings.py)
    "walker": ["shadow"], "runner": ["shadow"], "brute": ["shadow"],
    "broodling": ["beast"], "crawler": ["beast"], "golem": ["earth"],
}
ITEM_ELEMENTS = {               # weapons and throwables that already were elemental
    "ember_blade": "fire", "fire_pot": "fire", "frost_spear": "frost", "titan_hammer": "earth",
}
for _item, _el in ITEM_ELEMENTS.items():      # so w.get("element") works on the item's stats
    if _item in ITEMS:
        ITEMS[_item].setdefault("element", _el)


def boss_info(kind):
    return BOSSES.get(kind, {})


def types_of(enemy):
    """The types of a boss or zombie (empty = takes normal damage from everything)."""
    info = getattr(enemy, "info", None)
    if isinstance(info, dict) and "types" in info:
        return list(info["types"])
    kind = getattr(enemy, "kind", "")
    if kind in BOSSES:
        return list(BOSS_TYPES.get(kind, []))
    return list(ENEMY_TYPES.get(kind, []))


def multiplier(element, enemy):
    """How much an attack of this element hurts this enemy (1.0 = normal)."""
    if not element:
        return 1.0
    m = 1.0
    for t in types_of(enemy):
        m *= CHART.get(t, {}).get(element, 1.0)
    info = getattr(enemy, "info", None)
    if isinstance(info, dict):                      # per-boss fine-tuning
        m *= info.get("weak", {}).get(element, 1.0)
        m *= info.get("resist", {}).get(element, 1.0)
    return m


def verdict(m):
    if m == 0:
        return "No effect!", (170, 170, 170)
    if m >= 2:
        return "SUPER EFFECTIVE!", (255, 230, 90)
    if m > 1:
        return "Effective!", (240, 220, 140)
    if m < 1:
        return "Resisted...", (170, 170, 190)
    return "", (255, 255, 255)


def matchups(enemy_kind):
    """For a boss kind: ({element: x} weaknesses, {element: x} resistances) over the 5 attack elements."""
    class _E:
        kind = enemy_kind
        info = boss_info(enemy_kind)
    weak, resist = {}, {}
    for el in ELEMENTS:
        m = multiplier(el, _E)
        if m > 1:
            weak[el] = m
        elif m < 1:
            resist[el] = m
    return weak, resist
