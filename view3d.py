"""
view3d.py - draws the world in 3D.

The game itself still runs on a flat 2D map (x, y), exactly like the top-down version: movement,
collisions, AI, crafting and networking are untouched. Only the drawing is different:

  * The camera sits behind and above the survivor and looks down at an angle, with real perspective.
  * The map's (x, y) becomes the ground plane; height is a new third axis (z).
  * Flat things (grass, ponds, traps, light pools) lie on the ground.
  * Everything that stands up (trees, rocks, survivors, zombies, animals, bosses, benches...) is a
    "cut-out" - the same painted picture, stood upright and turned to face the camera.
  * Walls (cave walls and the walls you build) are real 3D blocks.

Two small custom shaders do the work, fed by the same arcade SpriteLists the 2D game already uses,
so there is no second copy of the world to keep in sync.
"""
import math
from array import array

import arcade
from arcade.gl import BufferDescription
from PIL import ImageDraw
from pyglet import gl
from pyglet.math import Mat4, Vec3

import art
import fx3d
import ui
from settings import *

PITCH = math.radians(CAM_PITCH_DEG)
FOV = CAM_FOV_DEG
TAN = math.tan(math.radians(FOV) / 2)
UP = 1 / math.cos(PITCH)       # stretch upright cut-outs so they look as tall as in the 2D game
WALL_KINDS = ("wood_wall", "stone_wall", "iron_wall")
WALL_SIDES = {"wood_wall": (118, 80, 46), "stone_wall": (128, 128, 132), "iron_wall": (150, 156, 168)}
TRUNK_LIFT = 34                # how high tree canopies float (on their trunks)
NUDGE_FLAG = 1000.0            # sprite.depth >= this means "draw a bit in front" (beehives in trees)

# =========================================================================== shaders
_SPRITE_IN = """
#version 330
layout (points) in;
layout (triangle_strip, max_vertices = 4) out;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform sampler2D sprite_texture;
uniform sampler2D uv_texture;
uniform float uv_offset_bias;
in float v_angle[];
in vec4 v_color[];
in vec2 v_size[];
in float v_texture[];
out vec2 gs_uv;
out vec4 gs_color;
%LIB%
void uvs(out vec2 uv0, out vec2 uv1, out vec2 uv2, out vec2 uv3) {
    getSpriteUVs(uv_texture, int(v_texture[0]), uv0, uv1, uv2, uv3);
    vec2 hp = 0.5 / vec2(textureSize(sprite_texture, 0)) * uv_offset_bias;
    uv0 += hp; uv1 += vec2(-hp.x, hp.y); uv2 += vec2(hp.x, -hp.y); uv3 += -hp;
}
"""

# Lying on the ground (or on top of a wall block). sprite.depth < 0 marks a wall block.
FLAT_GEO = _SPRITE_IN + """
uniform float height;
uniform int boxes_only;
void main() {
    vec3 c = gl_in[0].gl_Position.xyz;
    bool box = c.z < 0.0;
    if ((boxes_only == 1) != box) return;
    float z = box ? height : height + c.z;
    vec2 hs = v_size[0] / 2.0;
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    mat4 mvp = window.projection * window.view;
    vec2 uv0, uv1, uv2, uv3;
    uvs(uv0, uv1, uv2, uv3);
    gs_color = v_color[0];
    gl_Position = mvp * vec4(rot * vec2(-hs.x, hs.y) + c.xy, z, 1.0);  gs_uv = uv0; EmitVertex();
    gl_Position = mvp * vec4(rot * vec2(-hs.x, -hs.y) + c.xy, z, 1.0); gs_uv = uv2; EmitVertex();
    gl_Position = mvp * vec4(rot * vec2(hs.x, hs.y) + c.xy, z, 1.0);   gs_uv = uv1; EmitVertex();
    gl_Position = mvp * vec4(rot * vec2(hs.x, -hs.y) + c.xy, z, 1.0);  gs_uv = uv3; EmitVertex();
    EndPrimitive();
}
"""

# Standing up. mode 0 = the cut-out itself, mode 1 = its soft shadow on the ground.
BILL_GEO = _SPRITE_IN + """
uniform float up_scale;
uniform float lift;
uniform float nudge;
uniform int mode;
uniform vec2 sun;       // shadows: direction * length, in shadow widths (fx3d.sun)
void corner(mat4 mvp, vec2 p, float cx, float y, float zc, float fx, float sx) {
    vec4 q = mvp * vec4(cx + p.x, y, (zc + p.y) * up_scale, 1.0);
    q.x = (fx + p.x * sx) * q.w;
    gl_Position = q;
    EmitVertex();
}
void main() {
    vec3 c = gl_in[0].gl_Position.xyz;
    if (c.z < 0.0) return;                      // wall blocks are drawn as real 3D boxes
    float extra = c.z;
    float near = nudge;
    if (extra >= 1000.0) { extra -= 1000.0; near += 40.0; }
    vec2 hs = v_size[0] / 2.0;
    mat4 mvp = window.projection * window.view;
    gs_color = v_color[0];
    if (mode == 1) {
        // soft blob shadow, stretched away from the sun; things up high (tree canopies) cast further
        float rx = hs.x * 0.55;
        float ln = length(sun);
        vec2 dir = ln > 0.001 ? sun / ln : vec2(0.0, -1.0);
        vec2 side = vec2(-dir.y, dir.x) * rx * 0.95;
        vec2 along = dir * rx * (0.5 + 0.6 * ln);
        vec2 ctr = c.xy + dir * (rx * 0.5 + extra * 0.6) * ln;
        gl_Position = mvp * vec4(ctr - along + side, 0.3, 1.0); gs_uv = vec2(-1.0, 1.0);  EmitVertex();
        gl_Position = mvp * vec4(ctr - along - side, 0.3, 1.0); gs_uv = vec2(-1.0, -1.0); EmitVertex();
        gl_Position = mvp * vec4(ctr + along + side, 0.3, 1.0); gs_uv = vec2(1.0, 1.0);   EmitVertex();
        gl_Position = mvp * vec4(ctr + along - side, 0.3, 1.0); gs_uv = vec2(1.0, -1.0);  EmitVertex();
        EndPrimitive();
        return;
    }
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    float y = c.y - near;
    float zc = hs.y + extra + lift;
    vec2 uv0, uv1, uv2, uv3;
    uvs(uv0, uv1, uv2, uv3);
    // Stand straight up on screen: keep each corner's real height and depth (so walls still hide
    // things properly), but take its left/right position from the feet. Without this, perspective
    // makes everything near the screen edges lean outwards like a fisheye lens.
    vec4 feet = mvp * vec4(c.x, y, 0.0, 1.0);
    float fx = feet.x / feet.w;
    float sx = window.projection[0][0] / feet.w;
    gs_uv = uv0; corner(mvp, rot * vec2(-hs.x, hs.y), c.x, y, zc, fx, sx);
    gs_uv = uv2; corner(mvp, rot * vec2(-hs.x, -hs.y), c.x, y, zc, fx, sx);
    gs_uv = uv1; corner(mvp, rot * vec2(hs.x, hs.y), c.x, y, zc, fx, sx);
    gs_uv = uv3; corner(mvp, rot * vec2(hs.x, -hs.y), c.x, y, zc, fx, sx);
    EndPrimitive();
}
"""

SPRITE_FS = """
#version 330
uniform sampler2D sprite_texture;
uniform vec4 spritelist_color;
uniform int mode;
uniform float alpha_cut;
uniform float shade;     // shadow strength (fainter at night)
in vec2 gs_uv;
in vec4 gs_color;
out vec4 f_color;
void main() {
    if (mode == 1) {
        float d = dot(gs_uv, gs_uv);
        if (d > 1.0) discard;
        float k = 1.0 - d;
        k = k * k * (3.0 - 2.0 * k);         // smooth soft edge, darker core
        f_color = vec4(0.0, 0.0, 0.0, k * 0.5 * shade * gs_color.a * spritelist_color.a);
        return;
    }
    vec4 t = texture(sprite_texture, gs_uv);
    if (t.a <= alpha_cut) discard;      // also drops the painted-on shadows of the 2D art
    f_color = t * gs_color * spritelist_color;
}
"""

BOX_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec4 in_col;
out vec4 v_col;
void main() {
    gl_Position = window.projection * window.view * vec4(in_pos, 1.0);
    v_col = in_col;
}
"""

BOX_FS = """
#version 330
in vec4 v_col;
out vec4 f_color;
void main() { f_color = v_col; }
"""


def _trunk_img():
    w, h = 22, 58
    img = art._canvas(w, h)
    d = ImageDraw.Draw(img)
    s = art.S
    d.polygon([(5 * s, h * s), (8 * s, 0), (14 * s, 0), (17 * s, h * s)], fill=(98, 66, 40, 255),
              outline=(54, 36, 22, 255), width=int(1.4 * s))
    for k in range(5):   # bark
        y = (8 + k * 10) * s
        d.line([(9 * s, y), (12 * s, y + 6 * s)], fill=(70, 46, 28, 255), width=s)
    d.polygon([(2 * s, h * s), (6 * s, (h - 6) * s), (16 * s, (h - 6) * s), (20 * s, h * s)], fill=(88, 58, 36, 255))
    return art._finish(img, w, h)


def trunk():
    return art._tex("trunk3d", _trunk_img)


# =========================================================================== the mixin
class View3D(fx3d.FX3D):
    """Mixed into the game window. Replaces the flat camera with a tilted 3D one."""

    # ------------------------------------------------------------------ camera maths
    def _cam(self):
        """Camera for the current view: (eye, d, view w, view h)."""
        vw, vh = ui.W, ui.H
        d = (vh / 2) / TAN
        fx, fy = self.camera.position
        eye = (fx, fy - d * math.cos(PITCH), d * math.sin(PITCH))
        return eye, d, vw, vh

    def project(self, x, y, z=0.0):
        """World point -> screen position in GUI coordinates (None if it's behind the camera)."""
        (ex, ey, ez), d, vw, vh = self._cam()
        rx, ry, rz = x - ex, y - ey, z - ez
        cp, sp = math.cos(PITCH), math.sin(PITCH)
        zc = ry * cp - rz * sp            # distance in front of the camera
        if zc < 1:
            return None
        xc = rx
        yc = ry * sp + rz * cp
        return vw / 2 + xc * d / zc, vh / 2 + yc * d / zc

    def head(self, x, y, px):
        """Screen spot `px` pixels above a cut-out's feet (same units as the sprite's height)."""
        return self.project(x, y, px * UP)

    def ground_at(self, sx, sy):
        """Screen position (GUI coordinates) -> the point on the ground under it."""
        (ex, ey, ez), d, vw, vh = self._cam()
        cp, sp = math.cos(PITCH), math.sin(PITCH)
        u, v = (sx - vw / 2) / d, (sy - vh / 2) / d
        dx, dy, dz = u, cp + v * sp, -sp + v * cp
        if dz > -1e-3:
            dz = -1e-3
        t = -ez / dz
        return ex + dx * t, ey + dy * t

    def mouse_ground(self):
        mx, my = self.to_window(*self.mouse_screen)     # game layout -> real window (fullscreen scaling)
        vp = self.camera.viewport
        sx = (mx - vp.left) * ui.W / vp.width
        sy = (my - vp.bottom) * ui.H / vp.height
        return self.ground_at(sx, sy)

    def use_world3d(self):
        self.camera.use()      # viewport + scissor (split screen) from the 2D camera
        (ex, ey, ez), d, vw, vh = self._cam()
        fx, fy = self.camera.position
        self.projection = Mat4.perspective_projection(vw / vh, 20.0, 8000.0, FOV)
        self.view = Mat4.look_at(Vec3(ex, ey, ez), Vec3(fx, fy, 0.0), Vec3(0.0, 0.0, 1.0))

    # ------------------------------------------------------------------ GPU bits
    def _init3d(self):
        if getattr(self, "_progs3d", None):
            return
        lib = open(arcade.resources.resolve(":system:shaders/lib/sprite.glsl")).read()
        vs = open(arcade.resources.resolve(":system:shaders/sprites/sprite_list_geometry_vs.glsl")).read()
        ctx = self.ctx
        flat = ctx.program(vertex_shader=vs, geometry_shader=FLAT_GEO.replace("%LIB%", lib), fragment_shader=SPRITE_FS)
        bill = ctx.program(vertex_shader=vs, geometry_shader=BILL_GEO.replace("%LIB%", lib), fragment_shader=SPRITE_FS)
        for p in (flat, bill):
            p["sprite_texture"] = 0
            p["uv_texture"] = 1
            p["mode"] = 0
            p["alpha_cut"] = 0.0
        flat["height"] = 0.0
        flat["boxes_only"] = 0
        bill["up_scale"] = UP
        bill["lift"] = 0.0
        bill["nudge"] = 0.0
        bill["sun"] = (0.0, -0.4)
        bill["shade"] = 1.0
        self._progs3d = (flat, bill, ctx.program(vertex_shader=BOX_VS, fragment_shader=BOX_FS))
        self._ghost3d = arcade.SpriteList()
        self._wall_sig = {}
        self._wall_geo = {}

    def _draw_list(self, lst, prog, blend=None, **uniforms):
        if not len(lst):
            return
        lst._init_deferred()
        for k, v in uniforms.items():
            prog[k] = v
        old = lst.data.program
        lst.data.program = prog
        try:
            lst.draw(blend_function=blend)
        finally:
            lst.data.program = old
            for k, v in uniforms.items():   # back to the defaults
                prog[k] = 0 if isinstance(v, int) else 0.0
            if prog is self._progs3d[1]:
                prog["up_scale"] = UP

    def flat(self, lst, height=0.0, boxes=False, blend=None):
        self._draw_list(lst, self._progs3d[0], blend, height=float(height), boxes_only=int(boxes))

    def stand(self, lst, lift=0.0, nudge=0.0, cut=0.32, blend=None, shadow=False):
        if shadow:
            self._draw_list(lst, self._progs3d[1], blend, mode=1)
        else:
            self._draw_list(lst, self._progs3d[1], blend, lift=float(lift), nudge=float(nudge), alpha_cut=float(cut))

    # ------------------------------------------------------------------ 3D blocks
    def _box(self, out, x0, y0, x1, y1, h, col, faces):
        """Side faces of a block (the top is the sprite, drawn flat at height h)."""
        r, g, b = (c / 255 for c in col)

        def quad(a, bb, c, d, shade, dark_bottom=0.45):
            top = (r * shade, g * shade, b * shade, 1.0)
            bot = (r * shade * dark_bottom, g * shade * dark_bottom, b * shade * dark_bottom, 1.0)
            for (px, py, pz) in (a, bb, c, a, c, d):
                out.extend((px, py, pz))
                out.extend(top if pz > 0 else bot)

        if "s" in faces:
            quad((x0, y0, 0), (x1, y0, 0), (x1, y0, h), (x0, y0, h), 1.0)
        if "e" in faces:
            quad((x1, y0, 0), (x1, y1, 0), (x1, y1, h), (x1, y0, h), 0.72)
        if "w" in faces:
            quad((x0, y1, 0), (x0, y0, 0), (x0, y0, h), (x0, y1, h), 0.72)
        if "n" in faces:
            quad((x1, y1, 0), (x0, y1, 0), (x0, y1, h), (x1, y1, h), 0.6)

    def _geo(self, data):
        if not data:
            return None
        buf = self.ctx.buffer(data=array("f", data))
        return self.ctx.geometry([BufferDescription(buf, "3f 4f", ["in_pos", "in_col"])], mode=self.ctx.TRIANGLES)

    def _cave_walls(self, L):
        key = ("cave", id(L))
        if key in self._wall_geo:
            return self._wall_geo[key]
        C = CAVE_CELL
        cell = lambda s: (int(s.center_x // C), int(s.center_y // C))
        open_cells = {cell(s) for s in L.ground}
        out = []
        for w in L.walls:
            w.depth = -1          # draw this one as a block, not as a cut-out
            x, y = cell(w)
            faces = ""
            if (x, y - 1) in open_cells:
                faces += "s"
            if (x + 1, y) in open_cells:
                faces += "e"
            if (x - 1, y) in open_cells:
                faces += "w"
            if (x, y + 1) in open_cells:
                faces += "n"
            if faces:
                self._box(out, x * C, y * C, x * C + C, y * C + C, CAVE_WALL_HEIGHT, (96, 84, 78), faces)
        geo = self._wall_geo[key] = self._geo(out)
        return geo

    def _built_walls(self, L):
        walls = [s for s in L.builds if getattr(s, "kind", "") in WALL_KINDS]
        sig = tuple((id(s), s.center_x, s.center_y) for s in walls)
        if self._wall_sig.get(L.name) != sig:
            self._wall_sig[L.name] = sig
            out = []
            for s in walls:
                s.depth = -1
                hw, hh = s.width / 2, s.height / 2
                self._box(out, s.center_x - hw, s.center_y - hh, s.center_x + hw, s.center_y + hh,
                          BUILD_WALL_HEIGHT, WALL_SIDES[s.kind], "sewn")
            self._wall_geo[L.name] = self._geo(out)
        return self._wall_geo.get(L.name)

    # ------------------------------------------------------------------ trees get trunks
    def _trees(self, L, view):
        if L.name != "over":
            return None
        trunks = getattr(L, "trunks3d", None)
        if trunks is None:
            trunks = L.trunks3d = arcade.SpriteList()
            L.trunk_of = {}
            tex = trunk()
            for n in L.trees:
                if n.kind == "tree":
                    t = arcade.Sprite(tex, center_x=n.base[0], center_y=n.base[1])
                    L.trunk_of[id(n)] = t
                    trunks.append(t)
        vx, vy = view
        for n in L.trees:
            full = n.state == "full"
            if n.kind == "tree":
                t = L.trunk_of.get(id(n))
                lift = TRUNK_LIFT if full else 0
                if n.depth != lift:
                    n.depth = lift
                if t is not None:
                    if t.center_x != n.center_x:
                        t.center_x = n.center_x
                    t.visible = full and n.visible
                if full and 0 < vy - n.center_y < 170 and abs(n.center_x - vx) < 70:
                    n.alpha = 120          # don't let a tree in front hide you
                if t is not None:
                    t.alpha = n.alpha
            else:   # beehive: up in the canopy, drawn just in front of its tree
                up = n.tree is not None and n.tree.state == "full"
                want = NUDGE_FLAG + (TRUNK_LIFT + 18 if up else 0)
                if n.depth != want:
                    n.depth = want
        return trunks

    # ------------------------------------------------------------------ the frame
    def draw_world_3d(self, L, vl):
        self._init3d()
        ctx = self.ctx
        view = self.view_pos()
        trunks = self._trees(L, view)
        cave_geo = self._cave_walls(L) if vl == "cave" else None
        built_geo = self._built_walls(L)
        self.fx_tick()               # fx3d.py: particles move once per frame (not once per split view)
        dk = 0.93 if vl == "cave" else self.darkness
        sx, sy, shade = fx3d.sun(self.phase if vl == "over" else 0.27, dk)
        bill = self._progs3d[1]
        bill["sun"] = (sx, sy)
        bill["shade"] = shade
        self.use_world3d()
        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)

        # ---- on the ground
        self.flat(L.ground)
        self.flat(L.decor)
        self.flat(L.ponds)
        if vl == "over":
            self.flat(L.exits)
        self.flat(L.traps)
        self.draw_ground_hazards()
        uprights = [L.bushes, L.rocks, L.builds, L.animals, self.player_list, L.zombies, L.bosses, L.huts, L.trees]
        for lst in uprights:
            self.stand(lst, shadow=True)
        for x, y, r0, r1, t, dur, col, *ly in self.rings:
            if ly and ly[0] != vl:
                continue
            k = t / dur
            arcade.draw_circle_outline(x, y, r0 + (r1 - r0) * k, col + (int(230 * (1 - k)),), 6 * (1 - k) + 2)

        # ---- standing up (depth tested so blocks hide what's behind them)
        ctx.enable(ctx.DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LEQUAL)
        box = self._progs3d[2]
        if cave_geo:
            cave_geo.render(box)
            self.flat(L.walls, CAVE_WALL_HEIGHT, boxes=True)
        if built_geo:
            built_geo.render(box)
            self.flat(L.builds, BUILD_WALL_HEIGHT, boxes=True)
        if vl == "cave":
            self.stand(L.exits)
        self.stand(L.bushes)
        self.stand(L.rocks)
        self.stand(L.builds)
        self.stand(L.flames, lift=2, nudge=2, cut=0.05)
        self.stand(L.animals)
        self.stand(self.cloak_list, nudge=-1)
        self.stand(self.player_list)
        self.stand(self.gear_list, nudge=1)
        self.stand(self.held_list, lift=8, nudge=2)
        self.stand(L.zombies)
        self.stand(L.bosses)
        my_hut = self.me.in_hut if self.me else None
        for hsp in L.huts:
            inside = hsp is my_hut or any(p.in_hut is hsp for p in self.players.values())
            hsp.alpha = 110 if inside else 255
        self.stand(L.huts)
        if trunks is not None:
            self.stand(trunks, nudge=-1)
        self.stand(L.trees)

        # ---- build preview & tame target
        if self.state == "playing" and self.me and not self.ui_open and not self.cut:
            pl = self.placement(self.me, self.aim_world())
            if pl:
                item, ghost, ok = pl
                ghost.alpha = 150
                ghost.color = (150, 255, 150) if ok else (255, 110, 110)
                self._ghost3d.clear()
                self._ghost3d.append(ghost)
                self.stand(self._ghost3d, cut=0.05)
                self._ghost3d.clear()
                self.draw_defense_preview(item, ghost)   # defenses.py: turret / lantern reach
            ctx.disable(ctx.DEPTH_TEST)
            t = self.tame_target()
            if t:
                ctx.disable(ctx.DEPTH_TEST)
                arcade.draw_circle_outline(t.center_x, t.center_y, 30, (255, 150, 190, 200), 2)
        ctx.enable(ctx.DEPTH_TEST)
        self.fx_draw_particles(vl, additive=False)    # chips, dust, blood, smoke (lit by the light map)
        ctx.disable(ctx.DEPTH_TEST)

        # ---- floating things, drawn on screen at their 3D spot
        self.gui.use()
        self.draw_air_hazards()
        self.draw_pet_marks(L)

        # ---- time of day: colour grading + light map (fx3d.py) - replaces the old darkness sheet
        self.fx_lighting(L, vl, dk)
        if dk > 0:
            self.use_world3d()
            for g in L.glows:      # a warm haze over each fire (the light map already lights the ground)
                g.alpha = int(130 * dk) + 20
            blend = (ctx.SRC_ALPHA, ctx.ONE)
            self.flat(L.glows, blend=blend)
            ctx.enable(ctx.DEPTH_TEST)
            self.stand(L.flames, lift=2, nudge=2, cut=0.05)
            for e in L.eyes:
                e.alpha = int(255 * dk)
            self.stand(L.eyes, lift=16, nudge=3, cut=0.0, blend=blend)
            ctx.disable(ctx.DEPTH_TEST)
            for p in self.players.values():   # teammates carry a little lantern so you can find them
                if p is not self.me and p.alive and p.layer == vl:
                    arcade.draw_circle_filled(p.sprite.center_x, p.sprite.center_y, 30, p.color + (int(70 * dk),))
            for b in L.bosses:     # bosses are always visible - terrifying silhouettes
                arcade.draw_circle_filled(b.center_x, b.center_y, b.radius + 30, (255, 80, 40, int(40 * dk)))
            if vl == "cave":
                for s in L.exits:
                    arcade.draw_circle_filled(s.center_x, s.center_y, 60, (255, 240, 200, 40))
        self.use_world3d()           # embers, sparks and flames glow on top of the night
        ctx.enable(ctx.DEPTH_TEST)
        self.fx_draw_particles(vl, additive=True)
        ctx.disable(ctx.DEPTH_TEST)
        self.gui.use()

        self.draw_weather_3d(vl)  # weather.py: rain / snow / fog and the season's tint
        self.draw_repair_bars(L)  # repair.py: holding the hammer shows how hurt buildings are
        self.draw_shots(vl)      # after the darkness: a burning fire pot shows up at night

        # ---- words over heads
        for t, life, *ly in self.popups:
            if ly and ly[0] != vl:
                continue
            s = self.project(t.x, t.y, 40)
            if not s:
                continue
            ox, oy = t.x, t.y
            t.x, t.y = s
            t.color = t.color[:3] + (int(255 * min(1, life * 2)),)
            t.draw()
            t.x, t.y = ox, oy
        if len(self.players) > 1:
            for p in self.players.values():
                if p.alive and p.layer == vl:
                    s = self.head(p.sprite.center_x, p.sprite.center_y, p.sprite.height + 8)
                    if s:
                        self.txt(f"tag{p.id}", p.name, s[0], s[1], p.color + (220,), 10, anchor_x="center", bold=True)

    # ------------------------------------------------------------------ overrides of the 2D versions
    def draw_air_hazards(self):
        """Falling boulders/meteors and flying globs, drawn at their height (called in GUI space)."""
        if self.view_layer != "over":
            return
        for h in self.hazards:
            if h.kind in ("boulder", "meteor") and h.tele > 0:
                k = max(0.0, h.tele)
                s = self.project(h.x, h.y, 40 + k * 420)
                col = (130, 120, 110) if h.kind == "boulder" else (255, 120, 40)
                if s:
                    arcade.draw_circle_filled(s[0], s[1], 16 + 6 * (1 - k), col + (240,))
            elif h.kind == "glob" and h.tele <= 0:
                s = self.project(h.x, h.y, 24)
                if s:
                    arcade.draw_circle_filled(s[0], s[1], h.r, (140, 230, 70, 240))
            elif h.kind == "shard" and h.tele <= 0:
                a = math.atan2(h.vy, h.vx)
                p0 = self.project(h.x - math.cos(a) * 14, h.y - math.sin(a) * 14, 24)
                p1 = self.project(h.x + math.cos(a) * 8, h.y + math.sin(a) * 8, 24)
                if p0 and p1:
                    arcade.draw_line(*p0, *p1, (190, 235, 255, 255), 5)
        self.draw_swamp_air()     # swamp.py: spore pods in flight

    def draw_shots(self, vl):
        """Arrows and fire pots in the air (called in GUI space, drawn at their 3D spot)."""
        for s in self.shots:
            if s.layer != vl:
                continue
            h = s.height
            if s.kind == "arrow":
                sp = math.hypot(s.vx, s.vy) or 1
                ux, uy = s.vx / sp, s.vy / sp
                p0 = self.project(s.x - ux * 30, s.y - uy * 30, h)
                p1 = self.project(s.x, s.y, h)
                if p0 and p1:
                    arcade.draw_line(*p0, *p1, (214, 180, 120, 255), 3)
                    arcade.draw_circle_filled(p1[0], p1[1], 2.5, (210, 214, 224, 255))
            else:
                g = self.project(s.x, s.y, 0)
                p = self.project(s.x, s.y, h)
                if g:
                    arcade.draw_ellipse_filled(g[0], g[1], 16, 8, (0, 0, 0, 70))
                if p:
                    arcade.draw_circle_filled(p[0], p[1], 8, (176, 96, 60, 255))
                    arcade.draw_circle_filled(p[0] + 2, p[1] + 8, 3.5, (255, 170, 50, 255))

    def draw_pet_marks(self, L):
        tags = []          # name tags already placed this frame - bunched-up pets stack theirs
        for a in L.animals:
            if not a.pet:
                continue
            s = self.head(a.center_x, a.center_y, a.height + 6)
            if not s:
                continue
            owner = self.players.get(a.owner)
            col = owner.color if owner else (220, 220, 220)
            arcade.draw_circle_filled(s[0], s[1], 5, col + (230,))
            arcade.draw_circle_outline(s[0], s[1], 5, (255, 255, 255, 200), 1)
            if a.name:
                shield = " +" if a.armor else ""
                ty = s[1] + 9
                while any(abs(s[0] - tx) < 70 and abs(ty - yy) < 13 for tx, yy in tags):
                    ty += 13
                tags.append((s[0], ty))
                self.txt(f"petname{a.aid}", a.name + shield, s[0], ty, col + (230,), 10, anchor_x="center",
                         bold=True)
            if a.carrying:
                arcade.draw_circle_filled(s[0] + 10, s[1], 4, (255, 220, 120, 230))

    def draw_offscreen_friends(self):
        W, H = ui.W, ui.H
        for p in self.players.values():
            if p is self.me or not p.alive or p.layer != self.view_layer:
                continue
            s = self.project(p.sprite.center_x, p.sprite.center_y, 20)
            if s is None:
                s = (W / 2, -100)
            sx, sy = s
            if 0 < sx < W and 0 < sy < H:
                continue
            a = math.atan2(sy - H / 2, sx - W / 2)
            ex = max(30, min(W - 30, W / 2 + math.cos(a) * (W / 2 - 40)))
            ey = max(110, min(H - 170, H / 2 + math.sin(a) * (H / 2 - 40)))
            tip = (ex + math.cos(a) * 14, ey + math.sin(a) * 14)
            l = (ex + math.cos(a + 2.4) * 10, ey + math.sin(a + 2.4) * 10)
            r = (ex + math.cos(a - 2.4) * 10, ey + math.sin(a - 2.4) * 10)
            arcade.draw_triangle_filled(*tip, *l, *r, p.color + (230,))
            self.txt(f"arr{p.id}", p.name, ex - math.cos(a) * 18, ey - math.sin(a) * 18 - 4, p.color, 10,
                     anchor_x="center", bold=True)
