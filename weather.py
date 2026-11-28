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
# The 3D view's shaders fog the distance themselves (lighting3d.py: biome haze, foggy and rainy weather), so
# the flat full-screen haze / fog sheets below only keep this much of their old strength: enough to tint the
# whole view with the mood of the place, not so much that near things look washed out.
FLAT_HAZE = 0.4
FLAT_FOG = 0.35
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
        self.wx_wet = 0.0             # weather3d.py: how wet the ground is / how much snow lies (looks only)
        self.wx_snow = 0.0

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
        self.wx_wet = 1.0 if self.wet else 0.0                      # weather3d.py: start soaked / snowed on
        self.wx_snow = 1.0 if self.weather == "snow" else 0.0

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

        self.wx_tick(dt)     # weather3d.py: wet ground, snow cover, wind, the lightning bolt

    def draw_weather_3d(self, vl):
        """Screen overlay drawn over the 3D world (view3d.draw_world_3d), under the HUD: the season's tint and
        the weather's mood. The rain, snow and lightning themselves are 3D now (weather3d.py)."""
        if vl != "over":                 # underground: just the layer's own haze (biomes.LayerInfo.fog)
            fog = self.biome_fog() if hasattr(self, "layout") else None
            if fog:
                arcade.draw_lrbt_rectangle_filled(0, W, 0, H, fog[:3] + (int(fog[3] * FLAT_HAZE),))
            return
        if not hasattr(self, "weather_shown"):
            return
        r, g, b, a = SEASON_TINT[self.season]
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (r, g, b, a))
        fog = self.biome_fog() if hasattr(self, "layout") else None   # biomes.py: the biome's haze (blended)
        if fog:
            a = fog[3] * FLAT_HAZE * (1 - 0.5 * self.darkness)
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, fog[:3] + (int(a),))
        k = self.weather_k
        kind = self.weather_shown
        if k <= 0.01:
            return
        tint = WEATHER_TINT.get(kind)
        night = 1 - 0.6 * self.darkness
        if tint:
            r, g, b, a = tint
            a = a * k * (night * FLAT_FOG if kind == "fog" else 1)     # fog: thicker far away is the shaders' job
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (r, g, b, int(a)))

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
