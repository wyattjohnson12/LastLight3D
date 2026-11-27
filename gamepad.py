"""
gamepad.py - Xbox (and most other) controller support.

Plug the controller in (USB or Bluetooth) any time - it's picked up automatically.

    Left stick ........ move            Right stick ... aim
    Left stick click .. sprint (until you stop moving; uses energy)
    A / RT (hold) ..... attack, chop, mine, pick
    LT ................ place building / use item
    X (hold) .......... rest
    B ................. drink at a pond, otherwise quick eat/drink
    Y / View .......... backpack & crafting
    LB / RB, D-pad L/R  change hotbar slot
    Menu (Start) ...... pause / help

Uses pyglet's controller support first and falls back to pygame (SDL) if pyglet can't
see the controller - macOS sometimes only exposes wired Xbox pads to SDL.
"""
import math
import warnings

warnings.filterwarnings("ignore", message=".*no controller mappings.*")

DEAD = 0.22
BUTTONS = ("a", "b", "x", "y", "leftshoulder", "rightshoulder", "start", "back", "guide",
           "leftstick", "rightstick", "dpup", "dpdown", "dpleft", "dpright", "lt", "rt")


def _dead(x, y, dz=DEAD):
    m = math.hypot(x, y)
    if m < dz:
        return 0.0, 0.0
    k = min(1.0, (m - dz) / (1 - dz)) / m
    return x * k, y * k


class Gamepad:
    def __init__(self):
        self.name = None
        self.left = (0.0, 0.0)      # +y is up
        self.right = (0.0, 0.0)
        self.lt = self.rt = 0.0
        self.down = set()
        self.pressed = set()        # buttons that went down this frame
        self._prev = set()
        self._pg = None             # pyglet controller
        self._pygame = None
        self.backend = None
        self._mgr = None
        self._sdl_ok = None
        try:
            import pyglet
            self._mgr = pyglet.input.ControllerManager()

            @self._mgr.event
            def on_connect(c):
                if self._pg is None:
                    self._open_pyglet(c)

            @self._mgr.event
            def on_disconnect(c):
                if c is self._pg:
                    self._pg = None
                    self.name = None

            for c in self._mgr.get_controllers():
                self._open_pyglet(c)
                break
        except Exception:
            self._mgr = None
        self._sdl_scan_t = 0.0
        self._sdl_devs = []
        self._sdl_count = -1
        self.devices = {}           # per physical-ish device: key -> DevState (for local split-screen)

    # ------------------------------------------------------------------ backends
    def _open_pyglet(self, c):
        try:
            c.open()
            self._pg = c
            self.name = getattr(c, "name", "Controller") or "Controller"
            self.backend = "pyglet"
        except Exception:
            self._pg = None

    def _sdl_init(self):
        if self._sdl_ok is not None:
            return self._sdl_ok
        try:
            import os
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
            import pygame
            pygame.display.init()      # SDL needs this to pump events (no window is opened)
            pygame.joystick.init()
            try:
                import pygame._sdl2.controller as ctl
                ctl.init()
                self._ctl = ctl
            except Exception:
                self._ctl = None
            self._pygame = pygame
            self._sdl_ok = True
        except Exception:
            self._sdl_ok = False
        return self._sdl_ok

    def _sdl_scan(self):
        """Open EVERY controller SDL can see. macOS often lists one Xbox pad twice (a raw USB/HID
        device plus Apple's GameController device a moment later), and usually only one of the two
        actually reports input - so we read them all and combine."""
        pg = self._pygame
        devs = []
        for i in range(pg.joystick.get_count()):
            try:
                if self._ctl and self._ctl.is_controller(i):
                    devs.append(("ctl", self._ctl.Controller(i)))
                else:
                    j = pg.joystick.Joystick(i)
                    j.init()
                    devs.append(("joy", j))
            except Exception:
                pass
        self._sdl_devs = devs
        self._sdl_count = pg.joystick.get_count()
        names = []
        for kind, d in devs:
            try:
                names.append(d.name if kind == "ctl" else d.get_name())
            except Exception:
                pass
        if devs:
            self.name = next((n for n in names if n and "xbox" in n.lower()), None) or names[0] or "Controller"
            self.backend = "sdl"
        else:
            self.name = None

    def _sdl_events(self):
        """Pump SDL (needed for it to refresh controller state) and spot plug/unplug events."""
        pg = self._pygame
        changed = False
        try:
            for e in pg.event.get():
                if e.type in (pg.JOYDEVICEADDED, pg.JOYDEVICEREMOVED,
                              getattr(pg, "CONTROLLERDEVICEADDED", -1), getattr(pg, "CONTROLLERDEVICEREMOVED", -1)):
                    changed = True
        except Exception:
            pass
        return changed

    @staticmethod
    def _read_sdl(kind, d, down):
        """Read one SDL device -> (lx, ly, rx, ry, lt, rt), adding held buttons to `down`."""
        if kind == "ctl":
            ax = lambda i: d.get_axis(i) / 32767.0   # noqa: E731
            names = ["a", "b", "x", "y", "back", "guide", "start", "leftstick", "rightstick",
                     "leftshoulder", "rightshoulder", "dpup", "dpdown", "dpleft", "dpright"]
            for i, n in enumerate(names):
                if d.get_button(i):
                    down.add(n)
            return ax(0), -ax(1), ax(2), -ax(3), max(0.0, ax(4)), max(0.0, ax(5))
        lx, ly = d.get_axis(0), -d.get_axis(1)
        rx = ry = lt = rt = 0.0
        if d.get_numaxes() >= 6:
            rx, ry = d.get_axis(2), -d.get_axis(3)
            lt, rt = (d.get_axis(4) + 1) / 2, (d.get_axis(5) + 1) / 2
        names = ["a", "b", "x", "y", "leftshoulder", "rightshoulder", "back", "start", "guide",
                 "leftstick", "rightstick"]
        for i, n in enumerate(names[:d.get_numbuttons()]):
            if d.get_button(i):
                down.add(n)
        if d.get_numhats():
            hx, hy = d.get_hat(0)
            if hx < 0: down.add("dpleft")
            if hx > 0: down.add("dpright")
            if hy > 0: down.add("dpup")
            if hy < 0: down.add("dpdown")
        return lx, ly, rx, ry, lt, rt

    # ------------------------------------------------------------------ polling
    def poll(self, dt):
        """Call once per frame. Updates sticks, triggers, held and just-pressed buttons."""
        down = set()
        lx = ly = rx = ry = lt = rt = 0.0
        seen = set()
        c = self._pg
        if c is not None:
            try:
                lx, ly = c.leftx, -c.lefty
                rx, ry = c.rightx, -c.righty
                lt, rt = c.lefttrigger, c.righttrigger
                for b in BUTTONS[:-2]:
                    if getattr(c, b, False):
                        down.add(b)
                dp = getattr(c, "dpad", None)
                if dp is not None:
                    if dp.x < -0.5: down.add("dpleft")
                    if dp.x > 0.5: down.add("dpright")
                    if dp.y > 0.5: down.add("dpup")
                    if dp.y < -0.5: down.add("dpdown")
                self._dev("pg0", (lx, ly, rx, ry, lt, rt), set(down))
                seen.add("pg0")
            except Exception:
                self._pg = None
        if c is None and self._sdl_init():
            changed = self._sdl_events()
            self._sdl_scan_t -= dt
            if changed or self._sdl_scan_t <= 0 or self._sdl_count != self._pygame.joystick.get_count():
                self._sdl_scan_t = 3.0
                self._sdl_scan()
            for i, (kind, d) in enumerate(self._sdl_devs):
                mine = set()
                try:
                    vals = self._read_sdl(kind, d, mine)
                except Exception:
                    self._sdl_scan_t = 0      # device went away - rescan next frame
                    continue
                self._dev(f"sdl{i}", vals, mine, (kind, d))
                seen.add(f"sdl{i}")
                down |= mine
                # combine devices: whichever reports the bigger value wins
                lx, ly, rx, ry, lt, rt = [v if abs(v) > abs(o) else o
                                          for v, o in zip(vals, (lx, ly, rx, ry, lt, rt))]
        elif c is None:
            self.name = None
        for k in [k for k in self.devices if k not in seen]:
            del self.devices[k]

        self.left = _dead(lx, ly)
        self.right = _dead(rx, ry, 0.3)
        self.lt, self.rt = lt, rt
        if lt > 0.45:
            down.add("lt")
        if rt > 0.45:
            down.add("rt")
        self.pressed = down - self._prev
        self._prev = down
        self.down = down

    def _dev(self, key, vals, down, handle=None):
        st = self.devices.get(key)
        if st is None:
            st = self.devices[key] = DevState(key)
        st.update(vals, down, handle)

    @property
    def connected(self):
        return self.name is not None

    @property
    def active(self):
        """True if the player touched the controller this frame."""
        return bool(self.down) or self.left != (0, 0) or self.right != (0, 0)

    def rumble(self, strength=0.6, duration=0.15):
        try:
            if self._pg is not None and hasattr(self._pg, "rumble_play_weak"):
                self._pg.rumble_play_weak(strength, duration)
            for kind, d in self._sdl_devs:
                if kind == "ctl":
                    d.rumble(strength * 0.6, strength, int(duration * 1000))
        except Exception:
            pass


class DevState:
    """One controller device on its own (local split-screen gives each player their own)."""

    def __init__(self, key):
        self.key = key
        self.left = self.right = (0.0, 0.0)
        self.lt = self.rt = 0.0
        self.down, self.pressed, self._prev = set(), set(), set()
        self.handle = None

    def update(self, vals, down, handle=None):
        lx, ly, rx, ry, lt, rt = vals
        self.left = _dead(lx, ly)
        self.right = _dead(rx, ry, 0.3)
        self.lt, self.rt = lt, rt
        if lt > 0.45:
            down.add("lt")
        if rt > 0.45:
            down.add("rt")
        self.pressed = down - self._prev
        self._prev = down
        self.down = down
        if handle is not None:
            self.handle = handle


class PadView:
    """Looks like a Gamepad, but only reads the devices one local player owns.
    (macOS can list one Xbox pad twice - both copies get assigned to the same player.)"""

    def __init__(self, hub, keys):
        self.hub = hub
        self.keys = set(keys)

    def _states(self):
        return [self.hub.devices[k] for k in self.keys if k in self.hub.devices]

    def _pick(self, attr):
        best = (0.0, 0.0)
        for s in self._states():
            v = getattr(s, attr)
            if abs(v[0]) + abs(v[1]) > abs(best[0]) + abs(best[1]):
                best = v
        return best

    @property
    def left(self):
        return self._pick("left")

    @property
    def right(self):
        return self._pick("right")

    @property
    def down(self):
        out = set()
        for s in self._states():
            out |= s.down
        return out

    @property
    def pressed(self):
        out = set()
        for s in self._states():
            out |= s.pressed
        return out

    @property
    def connected(self):
        return bool(self._states())

    @property
    def name(self):
        return self.hub.name if self.connected else None

    @property
    def active(self):
        return bool(self.down) or self.left != (0, 0) or self.right != (0, 0)

    def rumble(self, strength=0.6, duration=0.15):
        for s in self._states():
            try:
                if s.key == "pg0" and self.hub._pg is not None and hasattr(self.hub._pg, "rumble_play_weak"):
                    self.hub._pg.rumble_play_weak(strength, duration)
                elif s.handle and s.handle[0] == "ctl":
                    s.handle[1].rumble(strength * 0.6, strength, int(duration * 1000))
            except Exception:
                pass
