# Last Light 3D

The 3D version of Last Light - same game, now seen through a tilted 3D camera with real walls,
standing trees and perspective. A survival game: gather by day, build by dusk, survive the night.
Craft at a workbench, smelt iron, wear armor, tame pets, share a team storage bin,
explore the caves, and survive a boss every third night. Play solo, online co-op over
Wi-Fi, or split-screen on one computer. Keyboard + mouse or an Xbox controller.

## First time setup

1. Install **Python 3** from <https://www.python.org/downloads/>
   (Windows: tick **"Add Python to PATH"** in the installer).
2. Open Terminal (Mac) or Command Prompt (Windows) and run:

   ```
   git clone https://github.com/wyattjohnson12/LastLight3D.git
   cd LastLight3D
   pip3 install -r requirements.txt
   ```
   (Windows: use `pip` instead of `pip3`.)

## Play

```
cd LastLight3D
python3 main.py
```
(Windows: `python main.py`)

## Get the newest version

```
cd LastLight3D
git pull
```
That's it - run the game again and you have every update.

## Playing together

- **Online co-op (same Wi-Fi):** one person picks **Host co-op game**, everyone else picks
  **Join co-op game** - the host's game shows up in the list. Click **Allow** if your computer
  asks about network connections. Everyone should `git pull` first so you're on the same version.
- **Local co-op (one screen):** pick **Local co-op**. Press **A** on a controller or **ENTER**
  on the keyboard to join, then **START** / **ENTER** to begin.

## Controls

| Action | Keyboard + mouse | Controller |
|---|---|---|
| Move / aim | WASD / mouse | Left stick / right stick |
| Attack, chop, mine, hunt | Left click | A or RT |
| Build, eat, tame | Right click | LT |
| Hotbar | 1-8, mouse wheel | LB / RB |
| Backpack, crafting, armor | TAB | Y |
| Storage, cave entrance, drink | E | B |
| Quick eat / drink | Q | B |
| Pets menu | P | D-pad up |
| Quick order for all pets | F | D-pad down |
| Rest | SHIFT | hold X |
| Scroll a long list (backpack, crafting, storage, pets) | mouse wheel, UP / DOWN, PAGE UP / DOWN | right stick |
| Pause / help | ESC | Menu |
| Save game (on the pause screen) | S | X |
| Fullscreen on / off | F11 or Cmd+F | |
| First person on / off | V | Click the right stick |

## Saving and resuming

Every game saves itself every morning, when you leave to the title screen, and when you close the
window. Press **S** on the pause screen to save any time. To resume, pick **Load saved game** on the
title screen, choose a save, then play it solo, host it for co-op, or play it split screen.
Co-op friends get their own backpack, armor, pets and spot (surface or cave) back if they join with
**the same name** as last time. Two friends with the same name each keep their own survivor (handed back
in the order they rejoin). Saves live in the `saves/` folder.

To delete a save: in **Load saved game**, highlight it and press **DELETE** (or **X** on a
controller), or pick it and choose **Delete this save**. You'll be asked to confirm first.

## Difficulty (day & night length, boss timing)

On the title screen, **Difficulty** sets how many real seconds the day and the night last:
Relaxed (240s / 45s), Default (117s / 63s), Hard (90s / 90s), Nightmare (60s / 150s), or your own custom
times (day 30-900s, night 20-600s), plus **nights between bosses** (1-10, default 3). Every saved game
keeps its own settings, but you can switch a save to the title-screen settings when you resume it.

## Bosses

The first boss rises on night 3 (or whatever "nights between bosses" is set to). If you don't kill it,
it retreats at dawn - keeping every wound you gave it - and comes back the next night, and every night
after, until it's beaten. Kill it, and the next boss comes 3 nights later.

Every boss drops a material for its own gear, and each boss's gear beats the one before it
(order: Quake Titan -> Brood Mother -> Frost Wraith -> Mire Lurker -> Inferno Colossus):

| Boss | Weapon | Armor |
|---|---|---|
| Quake Titan | **Titan Hammer** - 14 damage to everything around you, slow | **Titan Plate** (body) armor 10 |
| Brood Mother | **Brood Fang** - 5.5 damage, very fast stabs, venom: 3 damage/sec for 4s (works on bosses too) | **Chitin Armor** (body) armor 12, warmth 3, move 10% faster |
| Frost Wraith | **Frost Spear** - 11 damage, huge reach, chills | **Frost Cloak** (cloak) armor 4, warmth 14 |
| Mire Lurker | **Thornroot Whip** - 13 damage, long reach, slows | **Mire Mask** (head) armor 4, filters spore gas |
| Inferno Colossus | **Ember Blade** - 13 damage, quick, sets enemies on fire | **Ember Crown** (head) armor 6 + **Obsidian Plate** (body) armor 15, both fire-proof (see the Ashlands) |

## The world and its biomes

New games are played on a much bigger map. You start in **the Forest** in the middle, and around it, in a
different arrangement on every map, lie the **Frostwood Tundra**, the **Stone Highlands**, the **Ashlands**,
**the Mire** and the **Riverlands**. Saved games from before the big map keep their original map exactly.
For modders and contributors: `docs/BIOMES.md` explains how biomes, terrain and extra underground layers
plug in (`biomes.py`).

## Exploring: places to discover

There are no quests and no map markers - but the wilds are full of small **abandoned places** (about 30 on
every new map, a different layout each time). Fewer lie near the spawn; the richest are far out and in the
harsh biomes.

| Place | Where | What's there |
|---|---|---|
| Abandoned camp | Forest, Riverlands, Tundra, Mire | torn tent, cold firepit, a chest |
| Ruined watchtower | Riverlands, Highlands, Forest | a broken stone tower you can see from afar - zombies hide inside |
| Trapper's hut | Forest, Tundra, Mire | log cabin, drying rack - its wolves come back when you open the chest |
| Miner's camp | Highlands, Ashlands, **and in the cave** | headframe, mine cart, ore - a golem guards the cave ones |
| Survivor's grave | everywhere | a mound, a cross and a backpack (sometimes the grave isn't empty...) |
| Ice-locked cache | Tundra | a frozen chest among ice spikes |
| Obsidian shrine | Ashlands | glowing obelisks and an urn on an ember altar |
| Sunken boat | the Mire | a half-sunk boat by a bog pool |

* Walk close and you **find** it ("You found an abandoned camp"). Press **E** (controller **B**) at its chest
  to **search** it once: materials, food, sometimes a rare tool, armor piece or crystal. In co-op the world is
  shared - what one of you takes is gone for everyone.
* **Recipes to find:** the Iron Pickaxe, Iron Sword, Iron Helmet, Iron Armor, Hunting Bow, Bear Trap, Arrow
  Turret, Iron Wall, Iron Brazier and Crystal Medkit are **unknown** in a new game. Notes, manuals and
  blueprints in the places teach them - every one of them is hidden in at least two places on every map. The
  crafting list shows unknown ones as **???** with a hint where to look ("look in miners' camps and graves").
  What one survivor learns, the whole team knows. (You need the Iron Pickaxe to break into the Crystal Hollows.)
* By day, the zombies hiding in a ruin stay in the shade for a while after you wake them - it's a fight.
* The pause screen counts **places found** and **recipes found**. Saves remember what was searched and learned.
  Games saved before this update (and the old small map) already know every recipe.
* For contributors: `explore.py` (how to add a new kind of place is at the top of the file), art in
  `art_explore.py`, tests in `test_explore.py`.

## Hills

The big map isn't flat any more: the ground rolls in gentle hills through the Forest and the Riverlands,
gets bumpier in the Tundra and the Ashlands, and climbs highest in the Stone Highlands. The Mire, the area
around the spawn, ponds, cave entrances and rivers stay flat (water always lies in the valleys).

* Walking **uphill is slower** (down to 60% on the steepest slopes) and walking downhill a little faster.
* **Arrow Turrets on high ground see farther** - up to 170 extra range against things below them. While you
  place one, a second, fainter ring shows how far it reaches downhill.
* Everything stands on the ground where it is: survivors, creatures, trees, rocks, buildings, walls, shadows,
  fire light, particles. In first person your eyes rise and fall with the ground.
* Saved games from before the big map stay perfectly flat, and so do the caves.

How it works (for contributors): `hills.py` makes the heights (seeded noise on a 64 px grid, cached per world,
summed with any other module's `height` hook by `game.ground_height`); `terrain3d.py` puts them on the GPU as a
small texture that every 3D shader reads, turns the ground tiles into a shaded heightfield, and lifts every
sprite, shape, creature model, particle and light by the ground under it.

## The Riverlands, rivers, cliffs and farming

New worlds have wide **rivers** winding through the meadow and around the forest, plus a lake. Deep water
blocks everyone (zombies too), so cross at the shallow **fords** (stepping stones), on the road bridges, or
build your own **Bridge** (Build tab) over the water. Rock **cliffs** make natural chokepoints. Dirt **roads**
lead from the spawn to every region (walk 15% faster); lay **Stone Path** tiles at your base (20% faster).
Drink from any river with E / B.

* **Fishing:** craft a Fishing Rod, swing at water to cast, swing again when you get a BITE. Cook fish at a campfire.
* **Clay** lumps on the river banks -> **Bricks** (furnace) -> **Brick Wall** (300 health).
* **Farming:** a **Hoe** tills grass into a farm plot; right-click with Wheat / Carrot Seeds (from tall grass)
  or a Berry Sapling. Crops grow in 3 stages over ~2 days (faster near water / in rain); hit them to harvest.
  Wheat -> Bread, fish + carrots -> River Stew. Ducks on the rivers drop feathers (better arrows).
* Ground around your base and Base Flag slowly wears down to dirt.

## The Mire (swamp biome)

Somewhere out past the meadows (a different spot on every map) lies **the Mire**: dark bog ground,
drooping willows and dead trees, and murky pools. Mud slows you down a little, and the pools a lot.
- **Marsh Reeds** and **Glowcaps** (glowing mushrooms that light up at night) grow only here.
- At night the **Drowned** climb out of the bog: soggy, slow, tough swamp zombies that drop reeds and glowcaps.
- New crafts: **Reed Arrows** (2 reeds + 1 stone = 8 arrows), **Swamp Tonic** (campfire: +35 health,
  +30 energy), **Mire Mask** (workbench, head slot: spore gas does a third of the damage and roots hold
  you half as long), and **Thornroot Whip** (13 damage, very long reach, slows enemies) from the boss's Mire Heart.

**THE MIRE LURKER** joins the boss rotation (after the Frost Wraith, before the Inferno Colossus):
spore pods that burst into poison gas (purple circles), roots that burst up under you and hold you still
(brown circles), and it sinks into the mud and erupts under someone (bubbling patch). It **heals while it's
in the swamp**, so lure it out onto dry ground. The code lives in `swamp.py` (and the art in `art_swamp.py`).

## The Crystal Hollows (deep underground)

Somewhere in the cave (two spots on every new map) a timber **headframe** stands over a shaft, faint blue
light leaking up past the rubble that plugs it. Break the plug with an **Iron Pickaxe** (or better) and the
shaft stays open for good: press **E** to climb down into **the Crystal Hollows**, a deeper layer of big
caverns lit by glowing crystal clusters, with drifting glowing motes and a cool haze. Ladders lead back up.
The regular cave now has faint **glowing fungus** along its walls, so it's not pitch black in first person.
- **Starstone** veins hide deep in the Hollows, far from the ladders (iron pickaxe; slow to mine). There is
  also plenty of cave crystal, iron and coal down here.
- **Shard Crawlers** (crystal-backed spiders, drop crystal / coal), **Hollow Bats** (fast, fragile, drop meat /
  hide) and **Geode Golems** (huge and hard-hitting; drop crystal and iron, sometimes starstone).
- Workbench crafts: **Starstone Pickaxe** (2 wood, 2 iron ingots, 3 starstone - the fastest pickaxe),
  **Starstone Helm** (3 starstone, 2 iron ingots, 1 leather - armor 6, the best helmet, but no spore
  filter) and the **Starforged Blade** (your Ember Blade + 4 starstone + 3 crystal - 15 damage, quick,
  long reach, burns: the best blade).
- Saves remember who is down there; co-op players can be on different layers. Older saved worlds keep their
  map exactly (they get the fungus, but not the Hollows). Code: `hollows.py`, art `art_hollows.py`,
  creature models `tools/blender/models/hollows.py`.

## The Frostwood Tundra (snow biome)

One of the regions around the forest is the **Frostwood Tundra**: deep snow, snowdrifts and forests of
snow-laden pines. It is **cold** - it drains your warmth even by day. Wear a **Fur Cloak** (or better), keep
a campfire or brazier close, and carry a **Whitewood Warmer**. A hint pops up the first time you walk in.
- **Pines** give wood; **Whitewood** trees (pale, silver leaves) give Whitewood. **Clear Ice** blocks and
  glowing **Frost Crystals** need a pickaxe - the crystals give **Frost Shards**, so you can make the Frost
  Cloak and Frost Spear before beating the Wraith.
- Wildlife: **snow foxes**, **snow hares** (both drop **Snow Pelts**) and **arctic wolves** (fur, tough
  guards as pets). Foxes tame with meat, hares with berries, arctic wolves with meat.
- New crafts: **Snowfox Hood** (head, warmth 4), **Pelt Cloak** (warmth 10), **Whitewood Warmer**
  (campfire; keep one in your backpack and the tundra's cold bites much less), melt **Clear Ice** into
  water at a campfire, and campfires can be built from Whitewood.
- Ponds there freeze in **winter** - walk (and slide) across them. The rest of the year they're icy water
  nobody can cross.
- The snow line follows the seasons: in **winter** the snow and its chill spread far out into the regions
  around the tundra; in **summer** its edges thaw.
- In the middle lies the **Wraith's Hollow**. The **Frost Wraith** heals while it stands in the tundra's
  snow, so fight it somewhere else. Code: `tundra.py` (art `art_tundra.py`, creature models
  `tools/blender/models/tundra.py`).

## The Ashlands (volcanic biome)

The Inferno Colossus's home: black ash and basalt, charred dead trees, smoking vents and **lava cracks**
glowing in the ground (they light up the night). In the middle lies the Colossus's caldera, a lava pool
ringed by obsidian spires and vents. Only on new (big) maps.
- **Lava burns** about 14 health a second and you keep burning for a moment after you step off. Armor and
  potions don't help: watch where you walk. Only fire-proof gear protects you.
- **Ash storms** blow in every so often: the air turns orange-grey and thick, you walk a bit slower, and the
  ash drains your energy and health, unless you wear a **Mire Mask** or an **Ember Crown** (or sit in a hut).
- Resources: **Obsidian** spires (iron pickaxe), **Vents** (pickaxe: Sulfur), coal and iron seams (pickaxe),
  and **charred trees** that crumble into coal. The ground is warm, so you don't get cold here.
- **Fire Beetles**: armoured, neutral bugs. Crowd one or hit it and it bites, and the bite sets you on fire.
  They drop **Beetle Shell** and **Embers**.
- New crafts: **Fire Pots** from sulfur (1 sulfur + 1 ember + 1 stone = 3 pots, made anywhere),
  **Ember Crown** (workbench: 3 obsidian, 1 Ember Heart, 4 embers, 2 iron ingots) and **Obsidian Plate**
  (workbench: 6 obsidian, 1 Ember Heart, 4 beetle shells, 3 iron ingots). The Colossus drops 2 Ember Hearts.

The gear ladder (best last):

| Armor | Slot | Armor | Extra |
|---|---|---|---|
| Titan Plate | body | 10 | warmth 2 |
| Chitin Armor | body | 12 | warmth 3, move 10% faster |
| Frost Cloak | cloak | 4 | warmth 14 |
| Mire Mask | head | 4 | warmth 1, filters spore gas and ash storms, roots hold you half as long |
| **Ember Crown** | head | **6** | warmth 2, filters spore gas and ash storms, **halves lava and burning** |
| **Obsidian Plate** | body | **15** | warmth 4, **halves lava and burning** (with the Ember Crown: immune) |

The code is in `ashlands.py` (art in `art_ash.py`, the beetle's 3D model in `tools/blender/models/ashlands.py`).

## The Stone Highlands

A rocky upland wedge of the big map (new worlds only), home of the Quake Titan. Scree and gravel underfoot,
heather and wiry grass, a cold wind (a little extra chill, worse at night) and only a few **wind-bent pines**,
all leaning the same way. Lots of stone: **boulder fields** (big boulders give plenty of stone - bring a
pickaxe), extra rocks and iron.

* **Plateaus** - raised tablelands ringed by rocky cliff ledges you can't climb. Walk up the **ramps**.
* **The Titan's Crown** - a ring of rune-carved standing stones in the middle of the highlands.
* **Mountain goats** - they butt back when you hit them. Drop meat, **Goat Wool** and **Goat Horn**.
  Tame one with **Heather** and it works as a hauler.
* **Heather** - low purple shrubs to gather. **Heather Tea** (campfire: +30 thirst, +30 energy, +10 health),
  **Highland Wool Cloak** (workbench: warmth 10, armor 1), **Horn Bow** (workbench: 7.5 damage, longer range).
* **Quakes** - every couple of minutes you spend up here the ground trembles. Then boulders break loose:
  some **roll** down at you (sidestep them!), some drop out of the sky on the red circles. Rolling boulders
  that come to rest stay there as new boulders to mine.

## Pets

Tame an animal by holding its favourite food and right-clicking it (wolf: meat, boar & rabbit: berries,
bee: honey). Each player can have **8 pets** - in co-op everyone has their own. Press **P** (D-pad up)
for the **Pets menu**: see their health, give each one its own order (follow / work / stay), rename them,
and put on **Pet Armor** (leather or iron, made at a workbench) so zombie bites hurt less.
Renaming works with just a controller too: an on-screen keyboard pops up (A types, X deletes,
Y switches ABC / abc, START saves, B cancels).
**F** (D-pad down) still gives the same quick order to all your pets at once.

## Repairing buildings

Craft a **Repair Hammer** (3 wood, 2 stone) and hit a damaged wall, fire, hut or bench with it. It goes
back to full health, and costs part of its recipe: the more damage, the more it costs (a stone wall at half
health = 2 stone + 1 wood). Holding the hammer shows health bars over damaged buildings.

## Seasons and weather

The year goes **spring, summer, autumn, winter**, 4 days each (change `SEASON_DAYS` in `settings.py`).
The season and the weather are shown under the day clock.
- **Rain** can put out campfires out in the open. They catch again once they dry. Fires **next to a
  hut** stay lit, and braziers only go out in storms. Standing in the rain keeps your thirst up a bit.
- **Storms** bring heavier rain, lightning and a chill. **Fog** makes it hard to see. **Snow** (winter
  only) is cold whenever you're away from a fire.
- **Winter nights** are freezing: away from a fire or a hut you lose warmth and energy much faster.
- Spring brings more animals and winter fewer. Berry bushes regrow slowly in winter. Summer days make
  you thirsty.

All the numbers are in `settings.py`, and the code is in `weather.py`.

## Your base and the Base Flag

Every building you place claims the ground around it as **base**. Trees, rocks, ores, reeds and glowcaps you
use up are gone for good from that spot (a chopped tree leaves a stump you can walk over and build on). So the
world doesn't run dry, they turn up again later somewhere else in the wild - never inside a base, and never
next to a building, a survivor or a spot someone cleared. Berry bushes and beehives still fill up again in place.

Craft a **Base Flag** (Supplies tab: 4 wood, 6 fiber, 2 berries) and plant it to mark your base: a tall red
banner with a beam of light over it, a gold **BASE 12m** tag above it, and an arrow on the edge of the screen
pointing home when it's out of sight. You respawn at the flag. There's only one - planting a new one moves
your base (the old flag goes back in your backpack). The code lives in `base.py` (art in `art_flag.py`).

## Base defenses

Three buildings in the **Build** tab help you hold your base:

- **Arrow Turret** (workbench: 8 wood, 6 stone, 2 iron ore) - shoots the nearest zombie or boss within
  about 10 tiles all by itself (4 damage). Every shot uses one **Arrow from Team Storage**, so build a
  Storage Bin and keep it stocked. Zombies attack it (150 health) - fix it with the Repair Hammer.
- **Gate** (5 wood, 2 fiber) - put it in your wall: you and your pets walk straight through, zombies
  can't and have to break it down (70 health).
- **Lantern** (3 wood, 2 stone, 2 fiber) - zombies near it move at half speed, and it lights up the
  ground around it at night.

Holding a turret or lantern shows how far it reaches before you place it. The code lives in
`defenses.py` (logic) and `art_defenses.py` (art).

## Useful gear for boss fights

- **Hunting Bow** (workbench) + **Arrows** - shoot from a safe distance.
- **Fire Pot** (made at a campfire) - throw it with right-click: fire damage to everything it lands on.
- **Bear Trap** (workbench) - holds a zombie for 3s, or a boss for 2s. Re-arms itself.
- **Honey Salve** - +45 health, +20 energy.
- **Spike Traps** wear out, and they hurt *you* if you stand on them - put them in the zombies' path.
- **Iron Walls** have 700 health (stone walls 120).

## Stats and achievements

Every game keeps a tally for each survivor: nights survived, zombies and bosses killed, items crafted,
structures built, animals tamed, times downed and resources gathered. It's saved with the game, and shown
on the **pause screen** (ESC) and on the **run summary** you see when you leave a game to the title screen.

There are 19 **achievements** (First Night, Boss Slayer, Zookeeper, Fortress, Hardened...). They count across
all your games and pop up with a sound when you earn one. See them all with **Achievements** on the title
screen. They're kept per computer in `achievements.json` - in online co-op each player earns their own on
their own computer; in split screen everyone on the couch shares them. A boss kill counts for everyone
alive on the surface when it falls.

## First person mode

Press **V** (or click the right stick on a controller) to see the world through your survivor's eyes.
The mouse looks around, **W/S** walk forward and back, **A/D** step sideways, and attacking, chopping,
mining and building all go where the crosshair points. Opening the backpack, storage, pets or pause menu
frees the mouse so you can click. Cutscenes, being knocked down and split screen use the normal camera.
The game remembers your choice. (Code: `firstperson.py`, camera maths in `view3d.py`.)

## Tweaking the 3D camera

The camera lives in `settings.py`: `CAM_PITCH_DEG` (how steeply it looks down; 90 = straight down),
`CAM_FOV_DEG` (field of view), and `CAVE_WALL_HEIGHT` / `BUILD_WALL_HEIGHT`. All the 3D drawing is in
`view3d.py`; the game logic, co-op and networking are the same as the 2D version.

Trees (leafy oaks, swamp willows, dead trees), beehives, rocks, ores, bushes, reeds, glowcaps, campfires,
braziers, furnaces, lanterns, gates, benches, storage bins, turret pedestals and huts are small low-poly 3D
shapes built on the GPU, with their painted picture draped over them or plain colours picked from it
(in first person, animals, zombies, bosses and other survivors get simple 3D bodies). They're all in the
`SHAPES` table in `shapes3d.py` - change a number there to make trees taller or rocks lumpier.

**Adding a 3D object for a new biome:** read the guide at the top of `shapes3d.py`. In short: give the sprite
a `.kind`, put it in `L.trees` / `L.rocks` / `L.bushes` / `L.builds`, and register a shape with one of the
builders, e.g. `SHAPES["pine"] = conifer(tiers=4)`, `SHAPES["ice"] = crystal_cluster(glow=0.5)`,
`SHAPES["river_reeds"] = blade_clump(n=14)`. Creatures and detailed organic props come from Blender models
(`models3d.py`, see `docs/MODELS.md`); terrain props stay in `SHAPES`.

Lighting and effects live in `fx3d.py`: the time-of-day colour grading (warm dawn, golden/purple dusk,
blue night - edit the `_GRADE` table), the light pools from your torch, friends, campfires, braziers
and fire pots, the sun direction for the soft shadows (long in the morning and evening, short at noon),
and the particles (embers and smoke from fires, sparks and blood on hits, chips and dust when chopping
and mining). Particles come from a fixed pool of `MAX_PARTS` slots, so they never slow the game down.

## Making creature models

Creatures are low-poly models built with Blender scripts in `tools/blender/` and saved in
`assets/models/` (you don't need Blender to play). See [docs/MODELS.md](docs/MODELS.md).
