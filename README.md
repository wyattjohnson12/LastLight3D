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
| Pause / help | ESC | Menu |
| Save game (on the pause screen) | S | X |
| Fullscreen on / off | F11 or Cmd+F | |

## Saving and resuming

Every game saves itself every morning, when you leave to the title screen, and when you close the
window. Press **S** on the pause screen to save any time. To resume, pick **Load saved game** on the
title screen, choose a save, then play it solo, host it for co-op, or play it split screen.
Co-op friends get their own backpack, armor and pets back if they join with **the same name** as last
time. Saves live in the `saves/` folder.

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

## The Mire (swamp biome)

Somewhere out past the meadows (a different spot on every map) lies **the Mire**: dark bog ground,
drooping willows and dead trees, and murky pools. Mud slows you down a little, and the pools a lot.
- **Marsh Reeds** and **Glowcaps** (glowing mushrooms that light up at night) grow only here.
- At night the **Drowned** climb out of the bog: soggy, slow, tough swamp zombies that drop reeds and glowcaps.
- New crafts: **Reed Arrows** (2 reeds + 1 stone = 8 arrows), **Swamp Tonic** (campfire: +35 health,
  +30 energy), **Mire Mask** (workbench, head slot: spore gas does a third of the damage and roots hold
  you half as long), and **Thornroot Whip** (8 damage, very long reach, slows enemies) from the boss's Mire Heart.

**THE MIRE LURKER** joins the boss rotation (after the Frost Wraith, before the Inferno Colossus):
spore pods that burst into poison gas (purple circles), roots that burst up under you and hold you still
(brown circles), and it sinks into the mud and erupts under someone (bubbling patch). It **heals while it's
in the swamp**, so lure it out onto dry ground. The code lives in `swamp.py` (and the art in `art_swamp.py`).

## Pets

Tame an animal by holding its favourite food and right-clicking it (wolf: meat, boar & rabbit: berries,
bee: honey). Each player can have **3 pets** - in co-op everyone has their own. Press **P** (D-pad up)
for the **Pets menu**: see their health, give each one its own order (follow / work / stay), rename them,
and put on **Pet Armor** (leather or iron, made at a workbench) so zombie bites hurt less.
**F** (D-pad down) still gives the same quick order to all your pets at once.

## Repairing buildings

Craft a **Repair Hammer** (3 wood, 2 stone) and hit a damaged wall, fire, hut or bench with it. It goes
back to full health, and costs part of its recipe: the more damage, the more it costs (a stone wall at half
health = 2 stone + 1 wood). Holding the hammer shows health bars over damaged buildings.

## Useful gear for boss fights

- **Hunting Bow** (workbench) + **Arrows** - shoot from a safe distance.
- **Fire Pot** (made at a campfire) - throw it with right-click: fire damage to everything it lands on.
- **Bear Trap** (workbench) - holds a zombie for 3s, or a boss for 2s. Re-arms itself.
- **Honey Salve** - +45 health, +20 energy.
- **Spike Traps** wear out, and they hurt *you* if you stand on them - put them in the zombies' path.
- **Iron Walls** have 700 health (stone walls 120).

## Tweaking the 3D camera

The camera lives in `settings.py`: `CAM_PITCH_DEG` (how steeply it looks down; 90 = straight down),
`CAM_FOV_DEG` (field of view), and `CAVE_WALL_HEIGHT` / `BUILD_WALL_HEIGHT`. All the 3D drawing is in
`view3d.py`; the game logic, co-op and networking are the same as the 2D version.
