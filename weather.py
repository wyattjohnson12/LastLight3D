"""
weather.py - seasons and weather. Mixed into the game window.

Seasons follow the day counter: SEASON_DAYS days each of spring, summer, autumn and winter, then round
again. The weather changes every minute or two, picked from the season's table in settings.py:
  * rain  - campfires out in the open (not next to a hut) can go out for a while, boss fire burns out
            faster, and standing in it keeps your thirst up a little.
  * storm - heavier rain (fires go out 3x as often, even braziers), lightning, a bit colder.
  * snow  - winter only. Cold whenever you're outside away from a fire.
  * fog   - hard to see.
Winter nights are bitter: away from a fire or a hut you lose warmth and energy much faster.
Spring brings more animals, winter fewer; berry bushes regrow slowly in winter.

The host (or solo player) decides the weather; co-op clients get it in the snapshots ("wx").
The season comes from the day number, which is already synced and saved.
"""
import math
import random

import arcade

from settings import *

W, H = SCREEN_WIDTH, SCREEN_HEIGHT
WEATHERS = ("clear", "rain", "storm", "snow", "fog")
WEATHER_NAME = {"clear": "Clear", "rain": "Rain", "storm": "Storm", "snow": "Snow", "fog": "Fog"}
SEASON_COLOR = {"spring": (150, 230, 140), "summer": (255, 220, 110), "autumn": (240, 150, 80),
                "winter": (190, 225, 255)}
SEASON_TINT = {"spring": (170, 255, 170, 8), "summer": (255, 235, 160, 12), "autumn": (255, 160, 80, 18),
               "winter": (225, 235, 255, 45)}
WEATHER_TINT = {"rain": (50, 70, 100, 50), "storm": (25, 32, 60, 80), "snow": (230, 240, 255, 30),
                "fog": (195, 200, 210, 120)}
SEASON_HELLO = {
    "spring": "Spring has come. Animals are out and about - good hunting.",
    "summer": "Summer. Long hot days - keep some water with you. Watch for storms.",
    "autumn": "Autumn. Rain and fog roll in - keep your fires near a hut.",
    "winter": "WINTER. The nights are freezing - stay near a fire or in a hut after dark!",
}
WEATHER_HELLO = {
    "clear": "The sky clears.",
    "rain": "It's starting to rain. Campfires out in the open may go out.",
    "storm": "A STORM is rolling in! Fires will struggle - build them next to a hut.",
    "snow": "It's snowing. Bundle up and stay near a fire.",
    "fog": "A thick fog creeps in...",
}
DROPS = {"rain": 260, "storm": 420, "snow": 190}


class Weather:
    # ------------------------------------------------------------------ state
    def weather_setup(self):
        """Fresh weather for a new world (called from setup)."""
        self.weather = "clear"
        self.weather_t = random.uniform(*CLEAR_SECONDS)
        self.season_seen = self.season
        self.weather_k = 0.0          # how strong the rain / snow / fog looks right now (eases in and out)
        self.weather_shown = "clear"  # the weather that's drawn (fades out before the next one fades in)
        self.weather_flash = 0.0      # lightning
        self.weather_bolt_t = 6.0
        self.weather_said = -99.0
        self.weather_drops = []
        self.weather_cam = None

    @property
    def season(self):
        return SEASONS[((max(1, self.day) - 1) // SEASON_DAYS) % len(SEASONS)]

    @property
    def season_day(self):
        """Which day of the season this is (1..SEASON_DAYS)."""
        return (max(1, self.day) - 1) % SEASON_DAYS + 1

    @property
    def wet(self):
        return self.weather in ("rain", "storm")

    def pick_weather(self, announce=True):
        table = SEASON_WEATHER.get(self.season) or {"clear": 1}
        kinds = [k for k in table if k in WEATHERS]
        new = random.choices(kinds, weights=[table[k] for k in kinds])[0]
        span = CLEAR_SECONDS if new == "clear" else WEATHER_SECONDS
        self.weather_t = random.uniform(*span)
        if new != self.weather:
            self.weather = new
            if announce and not self.intro:
                self.say(WEATHER_HELLO[new], 4)

    # ------------------------------------------------------------------ every frame
    def weather_tick(self, dt):
        """Called from on_update: the host runs the weather, everyone animates it."""
        if self.sim and self.state == "playing" and not self.cut:
            self._weather_logic(dt)
        self._weather_visuals(dt)

    def _weather_logic(self, dt):
        if self.season != self.season_seen:           # a new season started this morning
            self.season_seen = self.season
            self.say(SEASON_HELLO[self.season], 6)
            if self.weather not in SEASON_WEATHER.get(self.season, {}):
                self.pick_weather(announce=False)
        self.weather_t -= dt
        if self.weather_t <= 0:
            self.pick_weather()

        # rain puts out fires that aren't sheltered by a hut, and burns out boss fire faster
        if self.wet:
            chance = RAIN_FIRE_OUT_PER_SEC * (3 if self.weather == "storm" else 1) * dt
            for s in list(self.structs.values()):
                if s.kind not in LIGHT_SOURCES or not s.lit or s.layer != "over":
                    continue
                if s.kind == "brazier" and self.weather != "storm":
                    continue               # a brazier shrugs off ordinary rain
                if random.random() >= chance or self.near_kind(s.position, "over", "hut", SHELTER_RADIUS):
                    continue
                self.set_fire(s, False)
                s.out_t = RAIN_FIRE_OUT_SECONDS
                self.burst(s.center_x, s.center_y, (200, 210, 220), 14, 70, layer="over")
                if self.time_alive - self.weather_said > 20:
                    self.weather_said = self.time_alive
                    self.say("The rain put out a campfire! It'll catch again once it dries. "
                             "Fires next to a hut stay lit.", 4)
            for h in self.hazards:
                if h.kind == "fire" and h.tele <= 0:
                    h.t -= dt * (1.0 if self.weather == "storm" else 0.6)

        # seasons: berries regrow slower in winter, animals turn up faster in spring
        rate = SEASON_BERRY_REGROW.get(self.season, 1.0)
        if rate != 1.0:
            for n in self.over.bushes:
                if n.state == "empty":
                    n.timer -= dt * (rate - 1.0)
        self.animal_t -= dt * (SEASON_ANIMALS.get(self.season, 1.0) - 1.0)

    def weather_survivor(self, p, dt):
        """Called from _update_survivor. Applies thirst/energy changes and returns extra cold per second."""
        if p.layer != "over" or not p.alive:
            return 0.0
        outside = p.in_hut is None
        sheltered = not outside or self.near_fire(p.pos, p.layer)
        cold = 0.0
        if self.season == "winter" and self.darkness > 0 and not sheltered:
            cold += WINTER_COLD_PER_SEC * self.darkness
            p.energy -= WINTER_ENERGY_PER_SEC * self.darkness * dt
        if self.weather == "snow" and not sheltered:
            cold += SNOW_COLD_PER_SEC
        if self.weather == "storm" and outside:
            cold += STORM_COLD_PER_SEC
        if self.wet and outside:
            p.thirst += RAIN_THIRST_PER_SEC * dt
        if self.season == "summer" and self.darkness < 0.2:
            p.thirst -= SUMMER_THIRST_PER_SEC * dt
        return cold

    # ------------------------------------------------------------------ co-op & saves
    def weather_net(self):
        return [self.weather, int(self.weather_t)]

    def weather_apply(self, wx):
        if wx and wx[0] in WEATHERS:
            self.weather = wx[0]
            self.weather_t = float(wx[1]) if len(wx) > 1 else self.weather_t
        self.season_seen = self.season

    def weather_save(self):
        return {"w": self.weather, "t": round(self.weather_t, 1), "season": self.season}

    def weather_load(self, data):
        """Old saves have no weather: they just start clear."""
        data = data or {}
        w = data.get("w", "clear")
        self.weather = w if w in WEATHERS else "clear"
        self.weather_t = float(data.get("t", random.uniform(*CLEAR_SECONDS)))
        self.season_seen = self.season
        self.weather_shown, self.weather_k = self.weather, 1.0 if self.weather != "clear" else 0.0

    # ------------------------------------------------------------------ looks
    def _weather_visuals(self, dt):
        if not hasattr(self, "weather_shown"):
            return
        # fade the old weather out, then the new one in
        if self.weather_shown != self.weather:
            self.weather_k -= dt * 0.5
            if self.weather_k <= 0:
                self.weather_k = 0.0
                self.weather_shown = self.weather
        else:
            goal = 0.0 if self.weather == "clear" else 1.0
            self.weather_k += max(-dt * 0.5, min(dt * 0.35, goal - self.weather_k))
        self.weather_flash = max(0.0, self.weather_flash - dt * 2.5)
        if self.weather_shown == "storm" and self.weather_k > 0.5:
            self.weather_bolt_t -= dt
            if self.weather_bolt_t <= 0:
                self.weather_bolt_t = random.uniform(5, 14)
                self.weather_flash = 1.0
                if self.view_layer == "over":
                    self._play("boom", 0.12, speed=0.6)

        kind = self.weather_shown
        want = DROPS.get(kind, 0)
        drops = self.weather_drops
        if not want:
            drops.clear()
            return
        while len(drops) < want:
            drops.append(self._new_drop(kind, random.uniform(0, H)))
        del drops[want:]
        # drops drift with the camera a little so the world doesn't seem to slide under them
        cam = tuple(self.cam_pos)
        if self.weather_cam is None or getattr(self, "local", False):
            self.weather_cam = cam
        mx, my = cam[0] - self.weather_cam[0], cam[1] - self.weather_cam[1]
        self.weather_cam = cam
        if abs(mx) + abs(my) > 200:      # teleported (cave / respawn): don't smear everything
            mx = my = 0
        wind = -140 if kind == "storm" else -50 if kind == "rain" else 0
        t = self.flame_t
        for d in drops:
            if kind == "snow":
                d[0] += math.sin(t * 1.3 + d[3] * 7) * 22 * dt - mx * 0.9
                d[1] -= d[2] * dt + my * 0.9
            else:
                d[0] += wind * dt - mx * 0.9
                d[1] -= d[2] * dt + my * 0.9
            if d[1] < -20:
                d[:] = self._new_drop(kind, H + random.uniform(0, 40))
            if d[0] < -30:
                d[0] += W + 60
            elif d[0] > W + 30:
                d[0] -= W + 60
            if d[1] > H + 60:
                d[1] -= H + 60

    @staticmethod
    def _new_drop(kind, y):
        if kind == "snow":
            return [random.uniform(-30, W + 30), y, random.uniform(40, 95), random.random()]
        fast = 1.35 if kind == "storm" else 1.0
        return [random.uniform(-30, W + 30), y, random.uniform(650, 900) * fast, random.uniform(10, 20) * fast]

    def draw_weather_3d(self, vl):
        """Screen overlay drawn over the 3D world (view3d.draw_world_3d), under the HUD."""
        if vl != "over" or not hasattr(self, "weather_shown"):
            return
        r, g, b, a = SEASON_TINT[self.season]
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (r, g, b, a))
        k = self.weather_k
        kind = self.weather_shown
        if k <= 0.01:
            return
        tint = WEATHER_TINT.get(kind)
        night = 1 - 0.6 * self.darkness
        if tint:
            r, g, b, a = tint
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (r, g, b, int(a * k * (night if kind == "fog" else 1))))
            if kind == "fog":      # thicker further away (the top of the screen is the far distance)
                for i in range(6):
                    y0 = H * (0.45 + i * 0.09)
                    arcade.draw_lrbt_rectangle_filled(0, W, y0, H, (r, g, b, int(22 * k * night)))
        drops = self.weather_drops
        n = int(len(drops) * k)
        if n and kind in ("rain", "storm"):
            slant = 0.35 if kind == "storm" else 0.12
            pts = []
            for d in drops[:n]:
                pts.append((d[0], d[1]))
                pts.append((d[0] - d[3] * slant, d[1] + d[3]))
            arcade.draw_lines(pts, (175, 195, 230, int(150 * night)), 1)
        elif n and kind == "snow":
            big = [(d[0], d[1]) for d in drops[:n] if d[3] > 0.6]
            small = [(d[0], d[1]) for d in drops[:n] if d[3] <= 0.6]
            arcade.draw_points(small, (240, 245, 255, int(210 * night)), 3)
            arcade.draw_points(big, (250, 252, 255, int(235 * night)), 5)
        if self.weather_flash > 0:
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (235, 240, 255, int(150 * self.weather_flash ** 2)))

    def draw_weather_hud(self, y):
        """One line under the day clock: season (+ day of it) and the weather. Returns the next free y."""
        if not hasattr(self, "weather"):
            return y
        s = self.season
        text = f"{s.capitalize()} {self.season_day}/{SEASON_DAYS}  -  {WEATHER_NAME[self.weather]}"
        self.txt("weatherhud", text, W - 18, y, SEASON_COLOR[s], 11, anchor_x="right", bold=True)
        y -= 16
        if s == "winter" and self.darkness > 0 and self.me and self.me.layer == "over" and self.me.alive and \
                self.me.in_hut is None and not self.near_fire(self.me.pos, "over"):
            self.txt("weathercold", "Freezing night - get to a fire!", W - 18, y, (170, 210, 255), 10,
                     anchor_x="right", bold=True)
            y -= 16
        return y
