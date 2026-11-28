"""firstperson.py - FIRST PERSON MODE: see the world through your survivor's eyes.

Press V (or click the right stick) to switch between the normal tilted camera and first person.
  * Mouse looks around (left/right turns you, up/down looks up and down). W/S walk forward/back,
    A/D step sideways. Your attacks, chopping, mining and building go where you're looking.
  * Controller: left stick walks, right stick looks.
  * Menus (TAB, storage, pets, pause) free the mouse again so you can click them.
  * Cutscenes, the intro, being knocked down and split screen use the normal camera.
The choice is remembered in lastlight_config.json.

The camera maths lives in view3d.py (View3D._basis); this file holds the state, input and HUD bits.
"""
import math

import arcade

import art
import ui
from settings import *

FP_FOV_DEG = 72           # wider than the tilted camera: it feels better in first person
FP_EYE_K = 0.82           # eye height, as a share of your survivor's standing height
FP_MOUSE_SENS = 0.0042    # radians per pixel of mouse movement
FP_PAD_TURN = 2.8         # radians per second at full right stick
FP_PITCH_MIN, FP_PITCH_MAX = math.radians(-70), math.radians(35)
FP_REACH = 80             # where builds go when you aren't looking at the ground nearby


class FirstPerson:
    fp_want = False          # the player picked first person (saved in the config)
    fp_yaw = 0.0             # which way you face (radians, same as Survivor.face)
    fp_pitch = math.radians(-12)
    _fp_grab = False         # mouse currently captured for looking

    # ------------------------------------------------------------------ state
    def fp_on(self):
        """True when the 3D view should be drawn from your eyes right now."""
        me = getattr(self, "me", None)
        return bool(self.fp_want and me and me.alive and self.state == "playing" and not self.local
                    and not self.cut and not self.intro)

    def fp_toggle(self):
        if self.local:
            self.say("First person isn't available in split screen.", 3)
            return
        self.fp_want = not self.fp_want
        self.cfg["first_person"] = self.fp_want
        self.save_cfg()
        if self.fp_want and self.me:
            self.fp_yaw = self.me.face
            self.fp_pitch = math.radians(-12)
        self.say("First person ON - mouse to look, V to switch back." if self.fp_want
                 else "First person OFF.", 3)

    def fp_eye(self):
        me = self.me
        x, y = me.sprite.center_x, me.sprite.center_y
        return x, y, max(30.0, me.sprite.height * FP_EYE_K * (1 / math.cos(
            math.radians(CAM_PITCH_DEG)))) + self.fp_ground(x, y)

    def fp_ground(self, x, y):
        """HILLS: the ground under your feet, eased a little so the view glides over the bumps
        (time-based, so it's the same however often it's asked for in a frame; big jumps snap)."""
        gz = self.ground_z(x, y) if hasattr(self, "ground_z") else 0.0
        t = getattr(self, "flame_t", 0.0)
        st = self.__dict__.get("_fp_gz")
        if st is None or abs(st[0] - gz) > 80 or t < st[1] or t - st[1] > 0.5:
            val = gz
        else:
            val = st[0] + (gz - st[0]) * (1 - math.exp(-(t - st[1]) * 12.0))
        self._fp_gz = (val, t)
        return val

    # ------------------------------------------------------------------ input
    def fp_tick(self, dt):
        """Once per frame: capture / free the mouse, controller looking."""
        if not hasattr(self, "_fp_loaded"):
            self._fp_loaded = True
            self.fp_want = bool(self.cfg.get("first_person", False))
        grab = self.fp_on() and not self.ui_open and not self.paused and not self.use_pad
        if grab != self._fp_grab:
            self._fp_grab = grab
            try:
                self.set_exclusive_mouse(grab)
            except Exception:
                pass
            if not grab:
                self.mouse_screen = (ui.W / 2, ui.H / 2)
        if self.fp_on() and self.use_pad and not self.ui_open and not self.paused:
            rx, ry = self.pad.right
            self.fp_yaw -= rx * FP_PAD_TURN * dt
            self.fp_pitch = max(FP_PITCH_MIN, min(FP_PITCH_MAX, self.fp_pitch + ry * FP_PAD_TURN * 0.6 * dt))

    def fp_mouse(self, dx, dy):
        """Mouse moved. Returns True when first person used it for looking."""
        if not self._fp_grab:
            return False
        self.fp_yaw -= dx * FP_MOUSE_SENS
        self.fp_pitch = max(FP_PITCH_MIN, min(FP_PITCH_MAX, self.fp_pitch + dy * FP_MOUSE_SENS))
        return True

    def fp_move(self, me, dx, dy):
        """Turn W/A/S/D (or the left stick) into a walk relative to where you look; face forward."""
        cy, sy = math.cos(self.fp_yaw), math.sin(self.fp_yaw)
        me.face = self.fp_yaw
        return cy * dy + sy * dx, sy * dy - cy * dx

    def fp_aim(self):
        """The ground spot you're looking at (for building), or a little in front of you."""
        x, y, _ = self.fp_eye()
        g = self.ground_at(ui.W / 2, ui.H / 2)
        if g and math.hypot(g[0] - x, g[1] - y) < 200 and self.fp_pitch < -0.12:
            return g
        return x + math.cos(self.fp_yaw) * FP_REACH, y + math.sin(self.fp_yaw) * FP_REACH

    # ------------------------------------------------------------------ drawing
    def fp_draw_sky(self, vl):
        """Sky above the horizon and plain ground below (drawn before the world, GUI space)."""
        vw, vh = ui.W, ui.H
        d = (vh / 2) / math.tan(math.radians(FP_FOV_DEG) / 2)
        hy = vh / 2 - d * math.tan(self.fp_pitch)
        if vl != "over":
            import biomes
            info = biomes.LAYER_INFO.get(vl)
            arcade.draw_lrbt_rectangle_filled(0, vw, 0, vh, (info and info.sky) or (22, 18, 16))
            return
        hy = max(-10, min(vh + 10, hy))
        arcade.draw_lrbt_rectangle_filled(0, vw, 0, max(0, hy), (40, 58, 34))
        if hy < vh:
            top, low = (96, 150, 214), (178, 208, 232)
            steps = 12
            for i in range(steps):
                y0 = hy + (vh - hy) * i / steps
                y1 = hy + (vh - hy) * (i + 1) / steps
                k = i / (steps - 1)
                col = tuple(int(low[j] + (top[j] - low[j]) * k) for j in range(3))
                arcade.draw_lrbt_rectangle_filled(0, vw, y0, y1 + 1, col)

    def fp_hide_me(self, hide):
        """Don't draw yourself (or what you hold / wear) from inside your own head."""
        me = self.me
        sprites = [me.sprite, me.held] + list(getattr(me, "gear_sprites", {}).values())
        if hide:
            self._fp_hidden = [(s, s.visible) for s in sprites]
            for s in sprites:
                s.visible = False
        else:
            for s, v in getattr(self, "_fp_hidden", []):
                s.visible = v
            self._fp_hidden = []

    def fp_draw_hand(self):
        """A crosshair, plus (only if the 3D arms of fphands3d.py couldn't be drawn) your held item as a flat
        picture in the bottom right, swinging when you attack."""
        me = self.me
        cx, cy = ui.W / 2, ui.H / 2
        arcade.draw_line(cx - 9, cy, cx - 3, cy, (255, 255, 255, 200), 2)
        arcade.draw_line(cx + 3, cy, cx + 9, cy, (255, 255, 255, 200), 2)
        arcade.draw_line(cx, cy - 9, cx, cy - 3, (255, 255, 255, 200), 2)
        arcade.draw_line(cx, cy + 3, cx, cy + 9, (255, 255, 255, 200), 2)
        item = me.hotbar[me.selected]
        if not item or self.ui_open:
            return
        import fphands3d
        if fphands3d.drawn_this_frame(self):
            return                 # fphands3d.py drew your arms and the item in 3D (this is the fallback)
        try:
            tex = art.icon(item)
        except Exception:
            tex = me.held.texture if me.held is not None else None
        if tex is None:
            return
        sw = (me.swing / 0.2) if me.swing > 0 else 0.0
        bob = math.sin(getattr(self, "flame_t", 0) * 7) * 4 * (1 if any(me.move) else 0)
        size = 150
        x = ui.W - 200 - sw * 90
        y = 120 + bob + sw * 40
        ang = -25 - sw * 60
        arcade.draw_texture_rect(tex, arcade.XYWH(x, y, size, size * tex.height / max(1, tex.width)), angle=ang)

    # ------------------------------------------------------------------ overrides
    def draw_hud(self):
        if self.fp_on():
            self.fp_draw_hand()
        super().draw_hud()

    def draw_offscreen_friends(self):
        if self.fp_on():
            return                 # the 2D edge arrows don't make sense from your eyes
        super().draw_offscreen_friends()
