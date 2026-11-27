# ----------------------------------------------------------------- window / world
SCREEN_WIDTH = 1100
SCREEN_HEIGHT = 720
SCREEN_TITLE = "Last Light 3D - Survive the Night"
# ----------------------------------------------------------------- 3D camera (see view3d.py)
CAM_PITCH_DEG = 52         # how steeply the camera looks down (90 = straight down like the 2D game)
CAM_FOV_DEG = 50           # vertical field of view
CAVE_WALL_HEIGHT = 95      # how tall cave walls are
BUILD_WALL_HEIGHT = 60     # how tall the walls you build are
WORLD_SIZE = 3200          # the LEGACY (worldgen 1) surface size. Each world has its own: game.world_size /
                           # layer.size (biomes.WORLD_SIZES) - don't use WORLD_SIZE in new code
CAVE_SIZE = 2400           # the underground map
CAVE_CELL = 60             # cave walls are built from cells this big
CAVE_ENTRANCES = 3
CAVE_ENTRANCES_V2 = 5      # worldgen 2 (the big map)
GRID = 40                  # building snap grid

# ----------------------------------------------------------------- player
PLAYER_SPEED = 210         # pixels per second
TIRED_SPEED = 110          # speed when energy is empty
STAT_MAX = 100

HUNGER_DECAY_PER_SEC = 0.55
THIRST_DECAY_PER_SEC = 0.8
ENERGY_DECAY_PER_SEC = 0.9      # while walking
SWING_ENERGY_COST = 1.2
REST_RESTORE_PER_SEC = 12.0     # hold SHIFT
STARVE_DAMAGE_PER_SEC = 2.5
THIRST_DAMAGE_PER_SEC = 3.5
NATURAL_REGEN_PER_SEC = 0.6     # when hunger & thirst are above half
DAY_RESPAWN_SECONDS = 8         # die by day -> back after this long. Die at night -> back at dawn.

# ----------------------------------------------------------------- temperature
COLD_PER_SEC = 2.6              # warmth lost per second in full night with no clothes
CAVE_COLD_PER_SEC = 0.9         # caves are always chilly
WARMTH_PER_GEAR_POINT = 0.2     # each point of clothing warmth cancels this much cold
FIRE_WARM_PER_SEC = 7.0         # standing near a campfire / brazier
HUT_WARM_PER_SEC = 3.5
DAY_WARM_PER_SEC = 4.0
TORCH_WARM_PER_SEC = 1.3
FREEZE_DAMAGE_PER_SEC = 2.5     # when warmth hits 0
FIRE_WARM_RADIUS = 170

# ----------------------------------------------------------------- day / night
DAY_CYCLE_SECONDS = 180    # one full day + night
START_PHASE = 0.05         # start just after dawn
DUSK_START, NIGHT_START, DAWN_START = 0.55, 0.65, 0.90
BOSS_EVERY = 3             # the first boss rises on night 3; each next one 3 nights after the last is killed.
                           # A boss that survives the night comes back every night until it's beaten.
# Difficulty = how long the day and the night last, in real seconds. "Night" runs from dusk to dawn
# (when the zombies are out); "day" is the rest. Pick one on the title screen, or set your own.
DIFFICULTIES = [
    #  name         day   night
    ("Relaxed",     240,  45),
    ("Default",     117,  63),     # the original 180-second cycle
    ("Hard",        90,   90),
    ("Nightmare",   60,   150),
]
DEFAULT_DIFFICULTY = "Default"
CUSTOM_DAY_LIMITS = (30, 900)      # shortest / longest custom day, in seconds
CUSTOM_NIGHT_LIMITS = (20, 600)    # shortest / longest custom night
BOSS_GAP_LIMITS = (1, 10)          # "nights between bosses" setting (the default is BOSS_EVERY)

# ----------------------------------------------------------------- seasons & weather (see weather.py)
SEASONS = ["spring", "summer", "autumn", "winter"]
SEASON_DAYS = 4            # days in each season (day 1-4 spring, 5-8 summer, ...)
# chance of each weather when the weather changes, per season
SEASON_WEATHER = {
    "spring": {"clear": 45, "rain": 35, "storm": 8, "fog": 12},
    "summer": {"clear": 65, "rain": 12, "storm": 18, "fog": 5},
    "autumn": {"clear": 35, "rain": 32, "storm": 8, "fog": 25},
    "winter": {"clear": 35, "snow": 50, "fog": 15},
}
WEATHER_SECONDS = (45, 120)       # how long one spell of weather lasts (real seconds, random)
CLEAR_SECONDS = (60, 160)         # clear spells last a bit longer
RAIN_FIRE_OUT_PER_SEC = 0.012     # chance per second that rain puts out an unsheltered campfire (storm x3)
RAIN_FIRE_OUT_SECONDS = 14        # how long a rained-out fire takes to dry off and catch again
SHELTER_RADIUS = 110              # a fire this close to a hut is sheltered from the rain
RAIN_THIRST_PER_SEC = 0.35        # standing out in the rain: thirst drains this much slower
SUMMER_THIRST_PER_SEC = 0.2       # summer days: thirst drains this much faster
WINTER_COLD_PER_SEC = 1.3         # extra warmth lost on winter nights away from a fire / hut
SNOW_COLD_PER_SEC = 0.6           # extra cold while it snows (day or night)
STORM_COLD_PER_SEC = 0.6
WINTER_ENERGY_PER_SEC = 0.5       # winter nights away from a fire also wear you out
# how fast berry bushes regrow and animals turn up, per season (1 = normal)
SEASON_BERRY_REGROW = {"spring": 1.3, "summer": 1.2, "autumn": 1.0, "winter": 0.4}
SEASON_ANIMALS = {"spring": 1.8, "summer": 1.0, "autumn": 1.0, "winter": 0.5}

# ----------------------------------------------------------------- enemies
ZOMBIES = {
    #             hp   speed  damage  attack_every
    "walker":    (6,   72,    9,      1.0),
    "runner":    (4,   128,   7,      0.8),
    "brute":     (20,  52,    18,     1.4),
    "broodling": (3,   150,   5,      0.7),   # summoned by the Brood Mother
    "crawler":   (5,   140,   7,      0.8),   # underground
    "golem":     (30,  46,    20,     1.5),   # underground, drops crystal & iron
}
SUN_BURN_PER_SEC = 2.5     # zombies burn in daylight
FIRE_FEAR_RADIUS = 110     # walkers and runners avoid campfires

# ----------------------------------------------------------------- animals
# hp, speed, temper (flee | defend), drops, tame food (None = can't tame), pet job
ANIMALS = {
    "rabbit": {"hp": 2, "speed": 170, "temper": "flee", "drops": {"meat": 1, "hide": 1},
               "tame": "berries", "chance": 0.6, "job": "forager", "dmg": 0,
               "desc": "Forager: picks berries & fiber from bushes and hauls them home."},
    "deer": {"hp": 6, "speed": 195, "temper": "flee", "drops": {"meat": 3, "hide": 2},
             "tame": None, "chance": 0, "job": None, "dmg": 0, "desc": ""},
    "boar": {"hp": 10, "speed": 115, "temper": "defend", "drops": {"meat": 3, "hide": 1},
             "tame": "berries", "chance": 0.35, "job": "hauler", "dmg": 8,
             "desc": "Hauler: chops trees and breaks rocks, carries wood & stone home."},
    "wolf": {"hp": 12, "speed": 165, "temper": "defend", "drops": {"meat": 1, "fur": 2},
             "tame": "meat", "chance": 0.3, "job": "guard", "dmg": 6,
             "desc": "Guard: fights zombies next to you (or around your base)."},
    "bee": {"hp": 1, "speed": 120, "temper": "defend", "drops": {}, "flies": True,
            "tame": "honey", "chance": 0.5, "job": "beekeeper", "dmg": 3,
            "desc": "Honey bee: on WORK it buzzes between flowers and brings honey to your Storage Bins."},
}
ANIMAL_CAP = 26
MAX_PETS = 8               # per player - in co-op every tamer has their own 8
PET_ARMOR_SOAK = 0.15      # each point of pet armor: bites do 1 / (1 + armor * this) damage
PET_NAMES = ["Biscuit", "Pepper", "Shadow", "Maple", "Scout", "Clover", "Ember", "Rocky", "Hazel", "Bandit",
             "Sunny", "Tank", "Juniper", "Pickle", "Ranger", "Willow", "Nugget", "Ash", "Koda", "Bramble"]
PET_CARRY = 6

# ----------------------------------------------------------------- bees & honey
HIVE_COUNT = 24            # beehives hanging in surface trees
HIVE_REGROW = 75           # seconds for a raided hive to fill with honey again
HIVE_HONEY = 2             # honey you get from raiding a full hive
HIVE_ALERT_RADIUS = 220    # wild bees this close get angry when you raid their hive
BEE_HONEY_EVERY = 5.0      # seconds a working pet bee spends at a flower per honey
BEE_CARRY = 3              # honey a pet bee brings home per trip

# ----------------------------------------------------------------- bosses
# name, hp, speed, melee damage, size, intro lines, drops
BOSSES = {
    "titan": {"name": "THE QUAKE TITAN", "hp": 180, "speed": 55, "damage": 24, "radius": 52,
              "tag": "The ground itself is its weapon.",
              "moves": ["EARTHQUAKE - stomps send a shockwave out from it. Get far away or get hit.",
                        "BOULDER TOSS - hurls rocks. Move out of the red circles.",
                        "WALL BREAKER - smashes through anything you build."],
              "drops": {"titan_core": 2, "stone": 15, "iron_ore": 4}},
    "brood": {"name": "THE BROOD MOTHER", "hp": 200, "speed": 80, "damage": 16, "radius": 48,
              "tag": "She never comes alone.",
              "moves": ["BROOD - keeps hatching fast little broodlings. Thin them out.",
                        "ACID SPIT - globs leave burning pools. Don't stand in green.",
                        "Kill the mother and the swarm stops."],
              "drops": {"chitin": 6, "meat": 4, "fiber": 8}},
    "wraith": {"name": "THE FROST WRAITH", "hp": 220, "speed": 95, "damage": 14, "radius": 42,
               "tag": "It drinks the warmth from the world.",
               "moves": ["BLIZZARD - the night gets brutally cold. Fires near it go out.",
                         "ICE SHARDS - bursts of shards fly out in every direction.",
                         "BLINK - it vanishes and reappears behind you. Walls can't stop it."],
               "drops": {"frost_shard": 4, "crystal": 2}},
    "colossus": {"name": "THE INFERNO COLOSSUS", "hp": 270, "speed": 70, "damage": 22, "radius": 56,
                 "tag": "Everything it touches burns.",
                 "moves": ["FIRE TRAIL - leaves burning ground wherever it walks.",
                           "METEOR RAIN - flaming rocks fall on the red circles.",
                           "CHARGE - watch for the glowing line, then dive sideways."],
                 "drops": {"ember_heart": 2, "iron_ore": 6, "coal": 6}},
}
BOSS_ORDER = ["titan", "brood", "wraith", "colossus"]

POISON_SECONDS = 4.0          # Brood Fang venom: how long a poisoned enemy keeps hurting (see venom.py)
POISON_DPS = 3.0              # ...and how much damage a second (bosses too)

# ----------------------------------------------------------------- traps & ranged weapons
SPIKE_ZOMBIE_DAMAGE = 3       # every 0.6s while a zombie stands on spikes
SPIKE_WEAR = 3                # trap health lost per prick (Spike Trap has 24 -> about 8 pricks)
SPIKE_PLAYER_DAMAGE = 6       # spikes hurt survivors standing on them too (every 0.8s)
SPIKE_BOSS_DAMAGE = 8         # a boss crushes the trap - but takes a hit doing it
BEAR_TRAP_HOLD = 3.0          # seconds a Bear Trap holds a zombie
BEAR_TRAP_BOSS_HOLD = 2.0     # ...or a boss
BEAR_TRAP_REARM = 4.0         # seconds before it can snap again
ARROW_SPEED = 900
FIRE_POT_RANGE = 380          # furthest you can throw a fire pot
FIRE_POT_RADIUS = 95
FIRE_POT_FLIGHT = 0.7         # seconds in the air

# ----------------------------------------------------------------- items
# kind: material | food | weapon | tool | build | armor
ITEMS = {
    # --- basic materials
    "wood":    {"name": "Wood", "kind": "material", "desc": "Chop trees. Used for almost everything."},
    "stone":   {"name": "Stone", "kind": "material", "desc": "Mine rocks. Tools, walls and fire rings."},
    "fiber":   {"name": "Plant Fiber", "kind": "material", "desc": "From bushes. Bandages, rope, clothing."},
    "hide":    {"name": "Raw Hide", "kind": "material", "desc": "From hunted animals. Tan it into leather at a workbench."},
    "leather": {"name": "Leather", "kind": "material", "desc": "Armor, clothing and grips."},
    "fur":     {"name": "Wolf Fur", "kind": "material", "desc": "Warm! Makes cloaks for cold nights."},
    "iron_ore": {"name": "Iron Ore", "kind": "material", "desc": "Rusty rocks on the surface, rich veins underground. Needs a pickaxe."},
    "coal":    {"name": "Coal", "kind": "material", "desc": "Found underground. Fuel for the furnace and braziers."},
    "iron_ingot": {"name": "Iron Ingot", "kind": "material", "desc": "Smelted in a furnace. Iron tools, armor and walls."},
    "crystal": {"name": "Cave Crystal", "kind": "material", "desc": "Deep underground. Needs an iron pickaxe."},
    "titan_core": {"name": "Titan Core", "kind": "material", "desc": "Dropped by the Quake Titan. Still rumbling."},
    "chitin":  {"name": "Brood Chitin", "kind": "material", "desc": "Dropped by the Brood Mother. Light and tough."},
    "frost_shard": {"name": "Frost Shard", "kind": "material", "desc": "Dropped by the Frost Wraith. Never melts."},
    "ember_heart": {"name": "Ember Heart", "kind": "material", "desc": "Dropped by the Inferno Colossus. Hot to the touch."},
    "arrows":  {"name": "Arrows", "kind": "material", "desc": "Ammo for the Hunting Bow. Each shot uses one."},
    # --- food & healing
    "berries": {"name": "Berries", "kind": "food", "hunger": 14, "thirst": 3,
                "desc": "Quick snack. +14 hunger. Rabbits and boars love them (taming)."},
    "water":   {"name": "Water Flask", "kind": "food", "thirst": 35, "desc": "Fill at a pond with E. +35 thirst."},
    "meat":    {"name": "Raw Meat", "kind": "food", "hunger": 10, "health": -4,
                "desc": "Cook it at a campfire! Wolves can be tamed with it."},
    "cooked_meat": {"name": "Cooked Meat", "kind": "food", "hunger": 45, "health": 8, "desc": "+45 hunger, +8 health."},
    "stew":    {"name": "Berry Stew", "kind": "food", "hunger": 50, "health": 12,
                "desc": "Cooked at a campfire. +50 hunger, +12 health."},
    "honey":   {"name": "Honey", "kind": "food", "hunger": 8, "energy": 50, "health": 4,
                "desc": "Sweet energy! +50 energy, +8 hunger. Raid beehives in trees. Bees can be tamed with it."},
    "bandage": {"name": "Bandage", "kind": "food", "health": 30, "desc": "Patch yourself up. +30 health."},
    "medkit":  {"name": "Crystal Medkit", "kind": "food", "health": 80, "desc": "+80 health. Glows faintly."},
    "honey_salve": {"name": "Honey Salve", "kind": "food", "health": 45, "energy": 20,
                    "desc": "+45 health, +20 energy. Honey and plant fiber - great mid-fight."},
    # --- weapons & tools
    "club":    {"name": "Wooden Club", "kind": "weapon", "damage": 2.5, "reach": 58, "cooldown": 0.45,
                "desc": "Bonk. 2.5 damage."},
    "spear":   {"name": "Stone Spear", "kind": "weapon", "damage": 4, "reach": 86, "cooldown": 0.55,
                "desc": "Long reach. 4 damage."},
    "axe":     {"name": "Stone Axe", "kind": "tool", "damage": 2, "reach": 56, "cooldown": 0.42,
                "harvest": {"tree": 2}, "desc": "Double wood from trees."},
    "pickaxe": {"name": "Stone Pickaxe", "kind": "tool", "damage": 1.5, "reach": 56, "cooldown": 0.42,
                "harvest": {"rock": 2, "iron": 1, "coal": 1}, "desc": "Double stone. Can mine iron and coal."},
    "torch":   {"name": "Torch", "kind": "tool", "damage": 1.5, "reach": 52, "cooldown": 0.45, "light": 1,
                "desc": "Hold it for a bigger circle of light and a little warmth."},
    "iron_axe": {"name": "Iron Axe", "kind": "tool", "damage": 3.5, "reach": 60, "cooldown": 0.38,
                 "harvest": {"tree": 3}, "desc": "Triple wood. Decent weapon too."},
    "iron_pickaxe": {"name": "Iron Pickaxe", "kind": "tool", "damage": 3, "reach": 60, "cooldown": 0.38,
                     "harvest": {"rock": 3, "iron": 2, "coal": 2, "crystal": 1},
                     "desc": "Fast mining. The only thing that can break crystal."},
    "iron_sword": {"name": "Iron Sword", "kind": "weapon", "damage": 6, "reach": 70, "cooldown": 0.4,
                   "desc": "6 damage, quick swings."},
    # boss weapons climb with the boss order (titan -> brood -> wraith -> mire -> colossus):
    # damage per second 16 (hits everything around you) -> 22 (with venom) -> 24 -> 31 -> 38 (+ burning)
    "titan_hammer": {"name": "Titan Hammer", "kind": "weapon", "damage": 14, "reach": 76, "cooldown": 0.85,
                     "quake": 1, "desc": "14 damage to EVERYTHING around you. Slow but devastating."},
    "brood_fang": {"name": "Brood Fang", "kind": "weapon", "damage": 5.5, "reach": 66, "cooldown": 0.28,
                   "poison": 1, "desc": "5.5 damage, lightning-fast stabs. Venom: poisoned enemies (even bosses) "
                                        "take 3 damage a second for 4s."},
    "frost_spear": {"name": "Frost Spear", "kind": "weapon", "damage": 11, "reach": 104, "cooldown": 0.45,
                    "slow": 1, "desc": "11 damage, huge reach. Chills enemies so they slow down."},
    "repair_hammer": {"name": "Repair Hammer", "kind": "tool", "damage": 1.5, "reach": 70, "cooldown": 0.5,
                      "repair": 1, "desc": "Hit a damaged building to fix it. Costs part of its recipe - the more "
                                           "damage, the more it costs."},
    "bow":     {"name": "Hunting Bow", "kind": "weapon", "damage": 5, "reach": 560, "cooldown": 0.65, "ranged": 1,
                "desc": "Shoots where you aim, 5 damage. Uses Arrows from your backpack. Keep your distance!"},
    "fire_pot": {"name": "Fire Pot", "kind": "throw", "damage": 18,
                 "desc": "Right-click to throw where you aim: bursts into flame, 18 damage + burning. Won't hurt friends."},
    "ember_blade": {"name": "Ember Blade", "kind": "weapon", "damage": 13, "reach": 76, "cooldown": 0.34,
                    "burn": 1, "desc": "13 damage, quick swings, and sets enemies on fire. The best blade there is."},
    # --- armor & clothing (slot: head | body | cloak)
    "leather_cap":   {"name": "Leather Cap", "kind": "armor", "slot": "head", "armor": 1, "warmth": 1,
                      "desc": "Armor 1, warmth 1."},
    "leather_tunic": {"name": "Leather Tunic", "kind": "armor", "slot": "body", "armor": 2, "warmth": 3,
                      "desc": "Armor 2, warmth 3."},
    "fur_cloak":     {"name": "Fur Cloak", "kind": "armor", "slot": "cloak", "armor": 0, "warmth": 7,
                      "desc": "Warmth 7. Nights are a lot less scary."},
    "iron_helmet":   {"name": "Iron Helmet", "kind": "armor", "slot": "head", "armor": 3, "warmth": 0,
                      "desc": "Armor 3."},
    "iron_armor":    {"name": "Iron Armor", "kind": "armor", "slot": "body", "armor": 5, "warmth": 0,
                      "desc": "Armor 5. Cold metal - wear a cloak."},
    "chitin_armor":  {"name": "Chitin Armor", "kind": "armor", "slot": "body", "armor": 12, "warmth": 3, "speed": 0.1,
                      "desc": "Armor 12, warmth 3. Light as a shell: you move 10% faster. The best body armor."},
    "frost_cloak":   {"name": "Frost Cloak", "kind": "armor", "slot": "cloak", "armor": 4, "warmth": 14,
                      "desc": "Armor 4, warmth 14. You'll never be cold again."},
    "pet_leather_armor": {"name": "Leather Pet Armor", "kind": "petarmor", "armor": 3,
                          "desc": "Pet armor 3: bites hurt your pet about a third less. Put it on in the Pets menu (P)."},
    "pet_iron_armor": {"name": "Iron Pet Armor", "kind": "petarmor", "armor": 6,
                       "desc": "Pet armor 6: bites do about half damage. Lost if the pet dies. Pets menu (P)."},
    "titan_plate":   {"name": "Titan Plate", "kind": "armor", "slot": "body", "armor": 10, "warmth": 2,
                      "desc": "Armor 10, warmth 2. Heavy stone plate - the Brood Mother's chitin is even better."},
    # --- buildings
    "wood_wall":  {"name": "Wood Wall", "kind": "build", "hp": 45, "desc": "Blocks zombies. Right-click to place."},
    "stone_wall": {"name": "Stone Wall", "kind": "build", "hp": 120, "desc": "Tough wall."},
    "iron_wall":  {"name": "Iron Wall", "kind": "build", "hp": 700,
                   "desc": "Very tough wall: 700 health (a stone wall has 120). Even a boss needs a while."},
    "spike_trap": {"name": "Spike Trap", "kind": "build", "hp": 24,
                   "desc": "Hurts zombies that walk over it - and YOU if you stand on it. Wears out. Put it in their path."},
    "bear_trap":  {"name": "Bear Trap", "kind": "build", "hp": 60,
                   "desc": "Snaps shut on an enemy and holds it 3s - even a boss (2s). Re-arms itself. Breaks after a few snaps."},
    "campfire":   {"name": "Campfire", "kind": "build", "hp": 60,
                   "desc": "Light and warmth. Scares walkers. Cook food. Rest here to heal."},
    "brazier":    {"name": "Iron Brazier", "kind": "build", "hp": 160,
                   "desc": "A sturdier fire: big light, lots of warmth, scares zombies."},
    "hut":        {"name": "Hut", "kind": "build", "hp": 220,
                   "desc": "Shelter. Zombies can't reach you inside. Warm. You respawn at huts."},
    "workbench":  {"name": "Workbench", "kind": "build", "hp": 80,
                   "desc": "Stand near it for ADVANCED crafting: leather, armor, iron gear."},
    "furnace":    {"name": "Furnace", "kind": "build", "hp": 140, "desc": "Smelts iron ore into ingots."},
    "storage":    {"name": "Storage Bin", "kind": "build", "hp": 160,
                   "desc": "TEAM storage, shared by everyone. Safe when you die. Craft straight out of it."},
    # --- base defenses (defenses.py)
    "arrow_turret": {"name": "Arrow Turret", "kind": "build", "hp": 150,
                     "desc": "Shoots the nearest zombie or boss in range by itself (4 damage). Each shot uses one "
                             "Arrow from TEAM STORAGE. Zombies attack it - fix it with the Repair Hammer."},
    "gate":       {"name": "Gate", "kind": "build", "hp": 70,
                   "desc": "A wall piece you and your pets walk straight through - zombies can't. Put it in your walls."},
    "lantern":    {"name": "Lantern", "kind": "build", "hp": 40,
                   "desc": "Zombies near it slow down to half speed, and it lights up the night around it."},
}
HANDS = {"name": "Fists", "damage": 1, "reach": 50, "cooldown": 0.40}
ARMOR_SLOTS = ["head", "body", "cloak"]
LIGHT_SOURCES = ("campfire", "brazier")
TRAP_KINDS = ("spike_trap", "bear_trap")     # lie flat on the ground, don't block anyone
STATIONS = {"workbench": "Workbench", "furnace": "Furnace", "campfire": "Campfire"}

# what each resource node gives, its hp and whether it needs a pickaxe
NODES = {
    "tree":    {"gives": "wood", "hp": 6, "regrow": 90},
    "rock":    {"gives": "stone", "hp": 6, "regrow": 120},
    "bush":    {"gives": "berries", "hp": 1, "regrow": 45},
    "hive":    {"gives": "honey", "hp": 1, "regrow": 75},
    "iron":    {"gives": "iron_ore", "hp": 8, "regrow": 200, "needs": "pickaxe"},
    "coal":    {"gives": "coal", "hp": 6, "regrow": 160, "needs": "pickaxe"},
    "crystal": {"gives": "crystal", "hp": 10, "regrow": 260, "needs": "iron_pickaxe"},
}
# pickaxe strength: a node that "needs" a pickaxe can be mined with that pickaxe or any stronger one
PICK_TIER = {"pickaxe": 1, "iron_pickaxe": 2}

# crafting: item, cost, station needed (None = anywhere), menu tab, how many you get
def R(item, cost, at=None, n=1):
    return {"item": item, "cost": cost, "at": at, "n": n}


CRAFT_TABS = {
    "Tools": [
        R("club", {"wood": 4}),
        R("axe", {"wood": 3, "stone": 3}),
        R("pickaxe", {"wood": 3, "stone": 3}),
        R("spear", {"wood": 5, "stone": 4, "fiber": 2}),
        R("torch", {"wood": 2, "fiber": 2}),
        R("iron_axe", {"wood": 2, "iron_ingot": 3}, "workbench"),
        R("iron_pickaxe", {"wood": 2, "iron_ingot": 3}, "workbench"),
        R("iron_sword", {"wood": 1, "iron_ingot": 4, "leather": 1}, "workbench"),
        R("brood_fang", {"chitin": 2, "iron_ingot": 2, "leather": 1}, "workbench"),
        R("frost_spear", {"wood": 3, "iron_ingot": 2, "frost_shard": 2}, "workbench"),
        R("bow", {"wood": 6, "fiber": 5}, "workbench"),
        R("repair_hammer", {"wood": 3, "stone": 2}),
        R("titan_hammer", {"iron_ingot": 5, "titan_core": 1, "leather": 2}, "workbench"),
        R("ember_blade", {"iron_ingot": 4, "ember_heart": 1, "crystal": 2}, "workbench"),
    ],
    "Armor": [
        R("leather_cap", {"leather": 2, "fiber": 2}, "workbench"),
        R("leather_tunic", {"leather": 4, "fiber": 3}, "workbench"),
        R("fur_cloak", {"fur": 4, "leather": 1, "fiber": 2}, "workbench"),
        R("iron_helmet", {"iron_ingot": 3, "leather": 1}, "workbench"),
        R("iron_armor", {"iron_ingot": 6, "leather": 2}, "workbench"),
        R("chitin_armor", {"chitin": 4, "leather": 2, "iron_ingot": 2}, "workbench"),
        R("frost_cloak", {"frost_shard": 3, "fur": 4, "crystal": 1}, "workbench"),
        R("titan_plate", {"titan_core": 1, "iron_ingot": 8, "crystal": 2}, "workbench"),
        R("pet_leather_armor", {"leather": 3, "fiber": 2}, "workbench"),
        R("pet_iron_armor", {"iron_ingot": 3, "leather": 1}, "workbench"),
    ],
    "Build": [
        R("campfire", {"wood": 5, "stone": 3}),
        R("wood_wall", {"wood": 3}),
        R("spike_trap", {"wood": 3, "stone": 2}),
        R("bear_trap", {"iron_ore": 2, "wood": 3, "fiber": 2}, "workbench"),
        R("workbench", {"wood": 12, "stone": 6}),
        R("storage", {"wood": 10, "fiber": 4}),
        R("stone_wall", {"stone": 4, "wood": 1}, "workbench"),
        R("hut", {"wood": 20, "stone": 10, "fiber": 6}, "workbench"),
        R("furnace", {"stone": 16, "wood": 4}, "workbench"),
        R("iron_wall", {"iron_ingot": 2, "stone": 2}, "workbench"),
        R("brazier", {"iron_ingot": 2, "coal": 3, "stone": 4}, "workbench"),
        R("gate", {"wood": 5, "fiber": 2}),
        R("lantern", {"wood": 3, "stone": 2, "fiber": 2}),
        R("arrow_turret", {"wood": 8, "stone": 6, "iron_ore": 2}, "workbench"),
    ],
    "Supplies": [
        R("bandage", {"fiber": 3}),
        R("arrows", {"wood": 2, "stone": 1, "fiber": 1}, n=6),
        R("fire_pot", {"stone": 2, "fiber": 2, "wood": 2}, "campfire", n=2),
        R("honey_salve", {"honey": 1, "fiber": 2}),
        R("stew", {"berries": 3, "water": 1}, "campfire"),
        R("cooked_meat", {"meat": 1}, "campfire"),
        R("leather", {"hide": 2}, "workbench"),
        R("iron_ingot", {"iron_ore": 2, "coal": 1}, "furnace"),
        R("medkit", {"bandage": 2, "crystal": 1}, "workbench"),
    ],
}
RECIPES = [r for tab in CRAFT_TABS.values() for r in tab]

STARTING_ITEMS = {"berries": 2, "water": 1}
HOTBAR_SLOTS = 8

# ----------------------------------------------------------------- resources in the world
TREE_COUNT, ROCK_COUNT, BUSH_COUNT, POND_COUNT, IRON_COUNT = 230, 120, 95, 9, 18
CAVE_ROCKS, CAVE_IRON, CAVE_COAL, CAVE_CRYSTAL = 40, 34, 30, 16
TREE_HP, ROCK_HP = 6, 6
TREE_REGROW, ROCK_REGROW, BERRY_REGROW = 90, 120, 45

# node kinds you can walk over / through (not solid for anyone)
WALKABLE_NODES = {"rock", "bush", "reeds", "river_reeds", "clay", "glowcap", "tall_grass", "heather"}
