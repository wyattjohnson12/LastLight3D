"""
options.py - fullscreen and difficulty (how long the day and night last). Mixed into the game window.

Fullscreen: the whole game is laid out for an 1100 x 720 screen. In fullscreen (or any window size)
that layout is scaled up to fit and centred, with thin black bars if the screen is a different shape.
Mouse positions are scaled back, so the rest of the game never needs to know.

Difficulty: the game clock still counts in "phase" (0 = dawn ... 1 = the next dawn), exactly like before.
Only the speed it moves at changes: one speed in the day, another at night, chosen so the day and
night last the number of real seconds picked on the title screen.
"""
import arcade

from settings import *

W, H = SCREEN_WIDTH, SCREEN_HEIGHT
NIGHT_SPAN = DAWN_START - DUSK_START        # how much of the phase is night
DAY_SPAN = 1.0 - NIGHT_SPAN
PRESETS = {name: (day, night) for name, day, night in DIFFICULTIES}


def clamp_day(s):
    return int(max(CUSTOM_DAY_LIMITS[0], min(CUSTOM_DAY_LIMITS[1], s)))


def clamp_night(s):
    return int(max(CUSTOM_NIGHT_LIMITS[0], min(CUSTOM_NIGHT_LIMITS[1], s)))


def clamp_gap(n):
    return int(max(BOSS_GAP_LIMITS[0], min(BOSS_GAP_LIMITS[1], n)))


class Options:
    # ------------------------------------------------------------------ fullscreen
    fit = (1.0, 0.0, 0.0)          # (scale, x offset, y offset) from the 1100 x 720 layout to the window

    def fit_rect(self, x, y, w, h):
        """A rectangle in game-layout units -> where it is in the real window."""
        s, ox, oy = self.fit
        return arcade.LBWH(ox + x * s, oy + y * s, w * s, h * s)

    def to_layout(self, x, y):
        """A point in the real window (e.g. the mouse) -> game-layout units."""
        s, ox, oy = self.fit
        return (x - ox) / s, (y - oy) / s

    def to_window(self, x, y):
        s, ox, oy = self.fit
        return ox + x * s, oy + y * s

    def on_resize(self, width, height):
        super().on_resize(width, height)
        if width <= 0 or height <= 0:
            return
        s = min(width / W, height / H)
        self.fit = (s, (width - W * s) / 2, (height - H * s) / 2)
        self.apply_fit()

    def apply_fit(self):
        vp = self.fit_rect(0, 0, W, H)
        cams = [self.camera, self.gui]
        if getattr(self, "local", False):
            cams = [self._cam_full, self._gui_full]
        for c in cams:
            c.viewport = vp
            c.scissor = vp
            c.projection = arcade.LRBT(-W / 2, W / 2, -H / 2, H / 2)
        if getattr(self, "local", False):
            self.layout_slots()
            if getattr(self, "focused", None) is not None:
                self.camera, self.gui = self.focused.camera, self.focused.gui

    def toggle_fullscreen(self):
        self.set_fullscreen(not self.fullscreen)
        self.cfg["fullscreen"] = self.fullscreen
        self.save_cfg()

    # ------------------------------------------------------------------ difficulty
    def chosen_difficulty(self):
        """What the title screen is set to: (name, day seconds, night seconds, nights before a boss wakes by
        itself). The last one is saved as "boss_wake" (the old "boss_gap" meant a boss every N nights)."""
        name = self.cfg.get("difficulty", DEFAULT_DIFFICULTY)
        gap = clamp_gap(self.cfg.get("boss_wake", BOSS_WAKE_NIGHTS))
        if name == "Custom":
            day, night = self.custom_times()
            return "Custom", day, night, gap
        if name not in PRESETS:
            name = DEFAULT_DIFFICULTY
        return (name,) + PRESETS[name] + (gap,)

    def nudge_gap(self, amount):
        self.cfg["boss_wake"] = clamp_gap(self.chosen_difficulty()[3] + (1 if amount > 0 else -1))
        self.save_cfg()

    def custom_times(self):
        d0, n0 = PRESETS[DEFAULT_DIFFICULTY]
        return clamp_day(self.cfg.get("custom_day", d0)), clamp_night(self.cfg.get("custom_night", n0))

    def set_difficulty(self, name):
        self.cfg["difficulty"] = name
        self.save_cfg()

    def nudge_custom(self, which, amount):
        day, night = self.custom_times()
        if which == "day":
            self.cfg["custom_day"] = clamp_day(day + amount)
        else:
            self.cfg["custom_night"] = clamp_night(night + amount)
        self.set_difficulty("Custom")

    @property
    def boss_gap(self):
        """The backstop (lairs.py): nights without anyone waking or beating a boss before the next one wakes by
        itself and comes for you (also the night that happens first in a new game)."""
        return int(self.difficulty[3]) if len(self.difficulty) > 3 else BOSS_WAKE_NIGHTS

    @property
    def day_night(self):
        """(day seconds, night seconds) for the game being played. self.difficulty = (name, day, night)."""
        return self.difficulty[1], self.difficulty[2]

    @staticmethod
    def difficulty_label(name, day, night):
        return f"{name}  -  {day}s day / {night}s night"

    def clock_rate(self):
        """How fast the clock runs right now (1.0 = the original 180-second day)."""
        day, night = self.day_night
        if DUSK_START <= self.phase < DAWN_START:
            return NIGHT_SPAN * DAY_CYCLE_SECONDS / night
        return DAY_SPAN * DAY_CYCLE_SECONDS / day

    def secs_until(self, target):
        """Real seconds until the day/night phase reaches `target` (e.g. DUSK_START)."""
        day, night = self.day_night
        p = self.phase
        left = (target - p) % 1.0
        total = 0.0
        for _ in range(6):
            if left <= 1e-9:
                break
            is_night = DUSK_START <= p < DAWN_START
            end = DAWN_START if is_night else DUSK_START if p < DUSK_START else 1.0
            step = min(end - p, left)
            total += step * (night / NIGHT_SPAN if is_night else day / DAY_SPAN)
            left -= step
            p = end % 1.0
        return total
