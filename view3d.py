"""
view3d.py - draws the world in 3D.

The game itself still runs on a flat 2D map (x, y), exactly like the top-down version: movement,
collisions, AI, crafting and networking are untouched. Only the drawing is different:

  * The camera sits behind and above the survivor and looks down at an angle, with real perspective.
  * The map's (x, y) becomes the ground plane; height is a new third axis (z).
  * Flat things (grass, ponds, traps, light pools) lie on the ground.
  * Trees, rocks, ores, bushes, campfires, braziers, benches, bins, turret pedestals and huts are small
    low-poly 3D shapes with their painted picture draped over them from above (shapes3d.py).
  * Everything else that stands up (survivors, zombies, animals, bosses, lanterns, gates...) is a
    "cut-out" - the same painted picture, stood upright and turned to face the camera. Animals, bosses,
    survivors and zombies are real low-poly 3D models (models3d.py, built in Blender - docs/MODELS.md).
  * Walls (cave walls and the walls you build) are real 3D blocks, lit like everything else, with a
    little surface pattern of their own drawn by the shader (planks, stone blocks, iron plates, rock).
  * Light, shade and fog for everything come from one shared shader library (lighting3d.py).
  * By day the sun casts real shadows (a shadow map, shadows3d.py) from the 3D shapes, creature models
    and walls; painted cut-outs keep their soft blob shadows (and everything gets those again at night).

Two small custom shaders do the work, fed by the same arcade SpriteLists the 2D game already uses,
so there is no second copy of the world to keep in sync.
"""
import math
import time
from array import array

import arcade
from arcade.gl import BufferDescription
from pyglet import gl
from pyglet.math import Mat4, Vec3

import fx3d
import lighting3d
import models3d
import shadows3d
import shapes3d
import terrain3d
import ui
import water3d
from settings import *

PITCH = math.radians(CAM_PITCH_DEG)
FOV = CAM_FOV_DEG
TAN = math.tan(math.radians(FOV) / 2)
UP = 1 / math.cos(PITCH)       # stretch upright cut-outs so they look as tall as in the 2D game
WALL_KINDS = ("wood_wall", "stone_wall", "iron_wall")
WALL_SIDES = {"wood_wall": (118, 80, 46), "stone_wall": (128, 128, 132), "iron_wall": (150, 156, 168)}
# the surface pattern WALL_FS draws on each kind of wall (kinds without one are plain; bricks are for
# terrain.py's brick wall)
WALL_PATTERN = {"wood_wall": 1, "stone_wall": 2, "iron_wall": 3, "brick_wall": 5}
CAVE_PATTERN = 4
TRUNK_LIFT = 34                # sprite.depth of a standing tree (stumps are 0) - shapes3d picks the shape by it
HIVE_LIFT = 16                 # beehives hang under the canopy (tilted-camera cut-out)
HIVE_Z = 64                    # beehives: how high the bottom of the 3D hive hangs
MESH_BUILDS = ("campfire", "brazier", "workbench", "storage", "arrow_turret", "furnace", "lantern", "gate")
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
    vec2 hs = v_size[0] / 2.0;
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    mat4 mvp = window.projection * window.view;
    vec2 uv0, uv1, uv2, uv3;
    uvs(uv0, uv1, uv2, uv3);
    gs_color = v_color[0];
    // HILLS (terrain3d.py): a block's top sits level on the ground under its centre; anything lying on the
    // ground takes the ground height at each corner (+ a hair, so it isn't hidden in the ground mesh)
    float zc = box ? height + ground_z(c.xy) : height + c.z + (hill_on == 1 ? 1.5 : 0.0);
    vec2 p0 = rot * vec2(-hs.x, hs.y) + c.xy, p1 = rot * vec2(-hs.x, -hs.y) + c.xy;
    vec2 p2 = rot * vec2(hs.x, hs.y) + c.xy, p3 = rot * vec2(hs.x, -hs.y) + c.xy;
    gl_Position = mvp * vec4(p0, box ? zc : zc + ground_z(p0), 1.0); gs_uv = uv0; EmitVertex();
    gl_Position = mvp * vec4(p1, box ? zc : zc + ground_z(p1), 1.0); gs_uv = uv2; EmitVertex();
    gl_Position = mvp * vec4(p2, box ? zc : zc + ground_z(p2), 1.0); gs_uv = uv1; EmitVertex();
    gl_Position = mvp * vec4(p3, box ? zc : zc + ground_z(p3), 1.0); gs_uv = uv3; EmitVertex();
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
uniform int fp;         // first person (firstperson.py): stand facing the camera instead
uniform vec2 face_right;
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
        mat4 vp = window.projection * window.view;        // HILLS: each corner on the ground under it
        float zs = hill_on == 1 ? 1.8 : 0.3;
        vec2 s0 = ctr - along + side, s1 = ctr - along - side, s2 = ctr + along + side, s3 = ctr + along - side;
        gl_Position = vp * vec4(s0, zs + ground_z(s0), 1.0); gs_uv = vec2(-1.0, 1.0);  EmitVertex();
        gl_Position = vp * vec4(s1, zs + ground_z(s1), 1.0); gs_uv = vec2(-1.0, -1.0); EmitVertex();
        gl_Position = vp * vec4(s2, zs + ground_z(s2), 1.0); gs_uv = vec2(1.0, 1.0);   EmitVertex();
        gl_Position = vp * vec4(s3, zs + ground_z(s3), 1.0); gs_uv = vec2(1.0, -1.0);  EmitVertex();
        EndPrimitive();
        return;
    }
    float a = radians(v_angle[0]);
    mat2 rot = mat2(cos(a), -sin(a), sin(a), cos(a));
    float y = c.y - near;
    float zc = hs.y + extra + lift;
    vec2 uv0, uv1, uv2, uv3;
    uvs(uv0, uv1, uv2, uv3);
    if (fp == 1) {
        vec2 fwd = vec2(-face_right.y, face_right.x);
        vec2 base = c.xy - fwd * near;
        vec2 q;
        q = rot * vec2(-hs.x, hs.y);  gs_uv = uv0; gl_Position = mvp * vec4(base + face_right * q.x, (zc + q.y) * up_scale, 1.0); EmitVertex();
        q = rot * vec2(-hs.x, -hs.y); gs_uv = uv2; gl_Position = mvp * vec4(base + face_right * q.x, (zc + q.y) * up_scale, 1.0); EmitVertex();
        q = rot * vec2(hs.x, hs.y);   gs_uv = uv1; gl_Position = mvp * vec4(base + face_right * q.x, (zc + q.y) * up_scale, 1.0); EmitVertex();
        q = rot * vec2(hs.x, -hs.y);  gs_uv = uv3; gl_Position = mvp * vec4(base + face_right * q.x, (zc + q.y) * up_scale, 1.0); EmitVertex();
        EndPrimitive();
        return;
    }
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

# lighting3d.py is pasted in when the programs are built. Flat pictures have no real facing, so the night's
# point lights light them all round. Things lying on the ground are drawn in the "ground" stage (no light
# here - the light map does it), cut-outs in the "lit" stage (see lighting3d.py).
SPRITE_FS = """
#version 330
uniform sampler2D sprite_texture;
uniform vec4 spritelist_color;
uniform int mode;
uniform float alpha_cut;
uniform float shade;     // shadow strength (fainter at night)
uniform int upright;     // 1: cut-outs (no real facing - sun shadows fall on them all over)
uniform int no_sun;      // 1: not darkened by sun shadows (flames)
in vec2 gs_uv;
in vec4 gs_color;
out vec4 f_color;
void main() {
    vec3 p = lt_world();
    if (mode == 1) {
        float d = dot(gs_uv, gs_uv);
        if (d > 1.0) discard;
        float k = 1.0 - d;
        k = k * k * (3.0 - 2.0 * k);         // smooth soft edge, darker core
        f_color = vec4(0.0, 0.0, 0.0, k * 0.5 * shade * gs_color.a * spritelist_color.a * (1.0 - lt_fog_k(p)));
        return;
    }
    vec4 t = texture(sprite_texture, gs_uv);
    if (t.a <= alpha_cut) discard;      // also drops the painted-on shadows of the 2D art
    vec4 c = t * gs_color * spritelist_color;
    // sun shadows (lighting3d.py / shadows3d.py): the ground and what lies on it face the way the ground does
    float sun = no_sun == 1 ? 1.0 : lt_sunlit(p, upright == 1 ? vec3(0.0) : lt_face(p));
    f_color = vec4(lt_fogged(c.rgb * lt_light(p, vec3(0.0)) * sun, p), c.a);
}
"""

# Plain coloured triangles (terrain.py's rivers, roads and cliffs - their shading is baked into the colours):
# the time of day, point lights (on the cliffs) and fog come from lighting3d.py.
BOX_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec4 in_col;
out vec4 v_col;
out vec3 v_pos;
void main() {
    gl_Position = window.projection * window.view * vec4(in_pos, 1.0);
    v_col = in_col;
    v_pos = in_pos;
}
"""

BOX_FS = """
#version 330
in vec4 v_col;
in vec3 v_pos;
out vec4 f_color;
void main() {
    vec3 n = lt_face(v_pos);
    vec3 rgb = v_col.rgb * lt_light(v_pos, n) * lt_sunlit(v_pos, n);
    f_color = vec4(lt_fogged(rgb, v_pos), v_col.a);
}
"""

# The sides of wall blocks (built walls, cave walls): real normals, sun + hemisphere + a soft fill from the
# camera's side (so the faces you look at read clearly, like the old baked shades), darker towards the
# foot, the night's point lights, fog - and a surface pattern made from the world position, so nothing
# is stored per wall: 1 wood planks, 2 stone blocks, 3 riveted iron plates, 4 rough cave rock, 5 bricks.
WALL_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
in vec3 in_nrm;
in vec4 in_col;      // colour ; pattern
in float in_h;       // 0 at the foot of the wall, 1 at the top
out vec3 v_pos;
out vec3 v_nrm;
out vec3 v_col;
flat out int v_pat;
out float v_h;
void main() {
    gl_Position = window.projection * window.view * vec4(in_pos, 1.0);
    v_pos = in_pos;
    v_nrm = in_nrm;
    v_col = in_col.rgb;
    v_pat = int(in_col.a + 0.5);
    v_h = in_h;
}
"""

WALL_FS = """
#version 330
in vec3 v_pos;
in vec3 v_nrm;
in vec3 v_col;
flat in int v_pat;
in float v_h;
out vec4 f_color;
float wh(vec2 p) {          // a hash that stays steady for big world coordinates
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float wnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(wh(i), wh(i + vec2(1.0, 0.0)), f.x), mix(wh(i + vec2(0.0, 1.0)), wh(i + vec2(1.0, 1.0)), f.x), f.y);
}
float wfbm(vec2 p) { return wnoise(p) * 0.57 + wnoise(p * 2.03 + 7.1) * 0.29 + wnoise(p * 4.01 + 3.7) * 0.14; }
// 1 inside a cell of a size.x x size.y grid, falling to 0 over `e` px at its edges (mortar, seams)
float cell_in(vec2 st, vec2 size, float e) {
    vec2 f = fract(st / size) * size;
    vec2 d = min(f, size - f);
    return smoothstep(0.0, e, min(d.x, d.y));
}
// the wall's colour at this spot. st = (along the face, height) in world pixels
vec3 pattern(vec2 st, vec3 base) {
    if (v_pat == 1) {               // wood: horizontal planks of random lengths, grain, dark seams
        float row = floor(st.y / 10.0);
        float u = st.x + wh(vec2(row, 3.0)) * 60.0;
        float seg = floor(u / 52.0);
        float fy = fract(st.y / 10.0), fx = fract(u / 52.0) * 52.0;
        float seam = smoothstep(0.0, 0.14, fy) * smoothstep(1.0, 0.86, fy) * smoothstep(0.0, 1.2, min(fx, 52.0 - fx));
        float tone = 0.86 + 0.24 * wh(vec2(row, seg));
        float grain = wnoise(vec2(u * 0.09, st.y * 1.3)) * 0.18 + wnoise(vec2(u * 0.4, st.y * 2.5)) * 0.06;
        return base * tone * (0.92 + grain) * mix(0.55, 1.0, seam);
    }
    if (v_pat == 2) {               // stone: blocks in a running bond, mortar lines, speckles
        float row = floor(st.y / 15.0);
        vec2 q = vec2(st.x + mod(row, 2.0) * 11.0, st.y);
        float m = cell_in(q, vec2(22.0, 15.0), 1.6);
        float tone = 0.84 + 0.26 * wh(floor(q / vec2(22.0, 15.0)) + 5.0);
        float sp = wnoise(st * 0.45) * 0.14 + wnoise(st * 1.7) * 0.06;
        float bevel = 1.0 + 0.08 * smoothstep(0.6, 1.0, fract(q.y / 15.0)) * m;       // a lit top edge
        return base * mix(0.6, tone * (0.92 + sp) * bevel, m);
    }
    if (v_pat == 3) {               // iron: plates with seams, rivets in the corners, brushed streaks, rust
        vec2 size = vec2(32.0, 30.0);
        vec2 f = fract(st / size) * size;
        float m = cell_in(st, size, 1.2);
        vec2 r = min(f, size - f);
        float rv = 1.0 - smoothstep(1.3, 2.1, length(r - vec2(4.0)));
        float tone = 0.9 + 0.12 * wh(floor(st / size) + 9.0);
        float streak = wnoise(vec2(st.x * 0.7, st.y * 0.05)) * 0.12;
        vec3 c = base * tone * (0.92 + streak) * mix(0.5, 1.0, m);
        c = mix(c, c * 1.35 + 0.05, rv);
        float rust = (1.0 - v_h) * (1.0 - v_h) * smoothstep(0.45, 0.8, wfbm(st * 0.08));
        return mix(c, vec3(0.42, 0.25, 0.15), rust * 0.55);
    }
    if (v_pat == 4) {               // cave rock: lumpy, layered, a few cracks
        float f = wfbm(st * 0.045) + 0.45 * wfbm(st * 0.16 + 11.0);
        float strata = 0.05 * sin(st.y * 0.22 + wfbm(st * 0.03) * 6.0);
        float crack = smoothstep(0.035, 0.0, abs(wnoise(st * 0.035 + 2.0) - 0.5));
        return base * (0.62 + 0.52 * f + strata) * (1.0 - 0.45 * crack);
    }
    if (v_pat == 5) {               // bricks: small blocks, light mortar
        float row = floor(st.y / 7.5);
        vec2 q = vec2(st.x + mod(row, 2.0) * 8.0, st.y);
        float m = cell_in(q, vec2(16.0, 7.5), 1.0);
        float tone = 0.84 + 0.26 * wh(floor(q / vec2(16.0, 7.5)) + 2.0) + wnoise(st * 0.8) * 0.08;
        return mix(vec3(0.62, 0.6, 0.56), base * tone, m);
    }
    return base;
}
void main() {
    vec3 n = normalize(v_nrm);
    vec2 st = vec2(abs(n.x) > 0.5 ? v_pos.y : v_pos.x, v_pos.z);
    vec3 alb = pattern(st, v_col);
    float ao = mix(0.5, 1.0, v_h);          // darker towards the foot (the old blocks had this baked in)
    vec3 day = (0.62 * lt_hemi(n) + 0.38 * max(dot(n, lt_fill.xyz), 0.0) + 0.25 * max(dot(n, lt_sun.xyz), 0.0)) * ao;
    day *= lt_sunlit(v_pos, n);             // in the shadow of a tree or another wall (shadows3d.py)
    vec3 rgb = alb * day * lt_light(v_pos, n);
    f_color = vec4(lt_fogged(rgb, v_pos), 1.0);
}
"""


# =========================================================================== the mixin
class View3D(terrain3d.Terrain3D, fx3d.FX3D, models3d.CreatureModels, shadows3d.SunShadows):
    """Mixed into the game window. Replaces the flat camera with a tilted 3D one."""

    # ------------------------------------------------------------------ camera maths
    def _cam(self):
        """Camera for the current view: (eye, d, view w, view h)."""
        eye, _, _, _, d, vw, vh = self._basis()
        return eye, d, vw, vh

    def _basis(self):
        """(eye, forward, right, up, d, view w, view h). The tilted camera looks north and down;
        first person (firstperson.py) looks out of your survivor's eyes."""
        vw, vh = ui.W, ui.H
        if self.fp_on():
            from firstperson import FP_FOV_DEG
            d = (vh / 2) / math.tan(math.radians(FP_FOV_DEG) / 2)
            cy, sy = math.cos(self.fp_yaw), math.sin(self.fp_yaw)
            cp, sp = math.cos(self.fp_pitch), math.sin(self.fp_pitch)
            return (self.fp_eye(), (cy * cp, sy * cp, sp), (sy, -cy, 0.0), (-cy * sp, -sy * sp, cp), d, vw, vh)
        d = (vh / 2) / TAN
        fx, fy = self.camera.position
        cp, sp = math.cos(PITCH), math.sin(PITCH)
        eye = (fx, fy - d * cp, d * sp + self.ground_z(fx, fy))     # HILLS: the camera rides up with you
        return eye, (0.0, cp, -sp), (1.0, 0.0, 0.0), (0.0, sp, cp), d, vw, vh

    def project(self, x, y, z=0.0):
        """World point -> screen position in GUI coordinates (None if it's behind the camera)."""
        (ex, ey, ez), f, r, u, d, vw, vh = self._basis()
        rx, ry, rz = x - ex, y - ey, z + self.ground_z(x, y) - ez      # HILLS: z is above the ground there
        zc = rx * f[0] + ry * f[1] + rz * f[2]           # distance in front of the camera
        if zc < 1:
            return None
        xc = rx * r[0] + ry * r[1] + rz * r[2]
        yc = rx * u[0] + ry * u[1] + rz * u[2]
        return vw / 2 + xc * d / zc, vh / 2 + yc * d / zc

    def head(self, x, y, px):
        """Screen spot `px` pixels above a cut-out's feet (same units as the sprite's height)."""
        return self.project(x, y, px * UP)

    def ground_at(self, sx, sy):
        """Screen position (GUI coordinates) -> the point on the ground under it (the hills too)."""
        (ex, ey, ez), f, r, up, d, vw, vh = self._basis()
        u, v = (sx - vw / 2) / d, (sy - vh / 2) / d
        dx, dy, dz = (f[i] + r[i] * u + up[i] * v for i in range(3))
        if dz > -1e-3:
            dz = -1e-3
        t = -ez / dz
        g = self.hill_grid()
        if g is None:
            return ex + dx * t, ey + dy * t
        return self._ray_hills(g, ex, ey, ez, dx, dy, dz, t)

    @staticmethod
    def _ray_hills(g, ex, ey, ez, dx, dy, dz, t_flat):
        """HILLS: march the view ray over the height grid to where it first goes under the ground."""
        t0 = max(0.0, (g.hmax - ez) / dz)           # where the ray comes down to the highest hill
        if t0 >= t_flat:
            return ex + dx * t_flat, ey + dy * t_flat
        step = 24.0 / max(1e-3, math.hypot(dx, dy))   # ~24 px along the ground per step
        t_end = min(t_flat, t0 + 6000.0 * step / 24.0)
        prev = t0
        t = t0
        while t < t_end:
            t = min(t_end, t + step)
            if ez + dz * t <= g.at(ex + dx * t, ey + dy * t):
                lo, hi = prev, t
                for _ in range(10):
                    mid = (lo + hi) / 2
                    if ez + dz * mid <= g.at(ex + dx * mid, ey + dy * mid):
                        hi = mid
                    else:
                        lo = mid
                return ex + dx * hi, ey + dy * hi
            prev = t
        return ex + dx * t_end, ey + dy * t_end

    def mouse_ground(self):
        mx, my = self.to_window(*self.mouse_screen)     # game layout -> real window (fullscreen scaling)
        vp = self.camera.viewport
        sx = (mx - vp.left) * ui.W / vp.width
        sy = (my - vp.bottom) * ui.H / vp.height
        return self.ground_at(sx, sy)

    def use_world3d(self):
        self.camera.use()      # viewport + scissor (split screen) from the 2D camera
        (ex, ey, ez), f, _, _, d, vw, vh = self._basis()
        if self.fp_on():
            from firstperson import FP_FOV_DEG
            self.projection = Mat4.perspective_projection(vw / vh, 3.0, 9000.0, FP_FOV_DEG)
        else:
            self.projection = Mat4.perspective_projection(vw / vh, 20.0, 8000.0, FOV)
        self.view = Mat4.look_at(Vec3(ex, ey, ez), Vec3(ex + f[0], ey + f[1], ez + f[2]), Vec3(0.0, 0.0, 1.0))
        self._view3d = self.view

    _ring_lit = False

    def light_at(self, x, y, z=0.0):
        """The light (r, g, b, 0..1) at a spot z above the ground: the time of day's ambient plus the point
        lights near it, topped out at daylight - what the light map gives the ground and lt_light gives
        standing things (lighting3d.py). Uses the current view's lighting state (_lt_frame)."""
        st = getattr(self, "_lt", None)
        if st is None:
            return 1.0, 1.0, 1.0
        r, g, b = st.amb
        if min(r, g, b) >= 0.999:
            return 1.0, 1.0, 1.0
        z += self.ground_z(x, y)
        for lx, ly, lz, reach, cr, cg, cb, _ in st.lights:
            d2 = (lx - x) ** 2 + (ly - y) ** 2 + (lz - z) ** 2
            if d2 >= reach * reach:
                continue
            t = max(0.0, min(1.0, (math.sqrt(d2) / reach - 0.3) / 0.7))
            f = 1.0 - t * t * (3 - 2 * t)          # the shaders' falloff
            r, g, b = r + cr * f, g + cg * f, b + cb * f
        return min(1.0, r), min(1.0, g), min(1.0, b)

    def lit_col(self, col, x, y, z=0.0, glow=0.0):
        """col (r, g, b[, a]) darkened by the light at a spot, for things drawn straight on the screen after
        the light map (falling boulders, pet markers, the build reach ring) so they get dark at night like
        everything around them. glow: 0..1, how much it shines by itself (a burning meteor)."""
        lr, lg, lb = self.light_at(x, y, z)
        k = [glow + (1.0 - glow) * v for v in (lr, lg, lb)]
        out = tuple(int(c * m) for c, m in zip(col[:3], k))
        return out + tuple(col[3:])

    def lift_to_ground(self, x=None, y=None):
        """HILLS: plain arcade shapes drawn in the 3D camera lie at z = 0. Lift the camera so the next ones
        lie on the ground at (x, y); call with no arguments to put it back."""
        base = getattr(self, "_view3d", None)
        if base is None:
            return
        z = self.ground_z(x, y) if x is not None else 0.0
        self.view = base @ Mat4.from_translation(Vec3(0.0, 0.0, z)) if z else base

    def ground_ring(self, x, y, r, col, width=2, lit=False):
        """A circle outline lying on the ground (it follows the hills). Call with the 3D camera on.
        lit: darken it by the light there (for rings drawn after the light map - see lit_col)."""
        if lit or self._ring_lit:
            col = self.lit_col(col, x, y)
        if self.hill_grid() is None:
            arcade.draw_circle_outline(x, y, r, col, width)
            return
        n = max(24, min(96, int(r / 7)))
        strips, cur = [], []
        for i in range(n + 1):
            a = i / n * math.tau
            s = self.project(x + math.cos(a) * r, y + math.sin(a) * r, 1.5)
            if s is None:
                if len(cur) > 1:
                    strips.append(cur)
                cur = []
            else:
                cur.append(s)
        if len(cur) > 1:
            strips.append(cur)
        depth = self.ctx.is_enabled(self.ctx.DEPTH_TEST)
        self.ctx.disable(self.ctx.DEPTH_TEST)
        self.gui.use()
        for pts in strips:
            arcade.draw_line_strip(pts, col, width)
        self.use_world3d()
        if depth:
            self.ctx.enable(self.ctx.DEPTH_TEST)

    # ------------------------------------------------------------------ GPU bits
    def _init3d(self):
        if getattr(self, "_progs3d", None):
            return
        lib = open(arcade.resources.resolve(":system:shaders/lib/sprite.glsl")).read()
        vs = open(arcade.resources.resolve(":system:shaders/sprites/sprite_list_geometry_vs.glsl")).read()
        ctx = self.ctx
        hlib = lib + terrain3d.GLSL          # HILLS: ground_z() in every world shader (terrain3d.py)
        fs = lighting3d.inject(SPRITE_FS, frag=True)     # light + fog in every world shader (lighting3d.py)
        flat = ctx.program(vertex_shader=vs, geometry_shader=FLAT_GEO.replace("%LIB%", hlib), fragment_shader=fs)
        bill = ctx.program(vertex_shader=vs, geometry_shader=terrain3d.inject(BILL_GEO.replace("%LIB%", hlib), "0.0"),
                           fragment_shader=fs)
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
        bill["fp"] = 0
        bill["face_right"] = (1.0, 0.0)
        bill["shade"] = 1.0
        bill["upright"] = 1
        box = ctx.program(vertex_shader=BOX_VS, fragment_shader=lighting3d.inject(BOX_FS, frag=True))
        self._progs3d = (flat, bill, box)
        self._wall_prog = ctx.program(vertex_shader=WALL_VS, fragment_shader=lighting3d.inject(WALL_FS, frag=True))
        self._lt = lighting3d.LightState(ctx)
        # 3D shapes (shapes3d.py): with OpenGL 4 one draw call makes every pass of a shape (geometry shader
        # invocations); on plain 3.3 we fall back to one draw per pass
        self._mesh_lib, self._mesh_vs = hlib, vs
        self._mesh_progs = {}
        self._mesh_inv = ctx.gl_version >= (4, 0)
        try:
            self._mesh_prog(1)
        except Exception:
            self._mesh_inv = False
            self._mesh_progs = {}
            self._mesh_prog(1)
        self._mesh_t0 = time.perf_counter()
        self._hill_init(vs, hlib + lighting3d.glsl(), fs)
        for p in (flat, bill, box, self._wall_prog, self._hill_prog):
            lighting3d.bind(p)
        self._kinds3d = {}
        self._ghost3d = arcade.SpriteList()
        self._wall_sig = {}
        self._wall_geo = {}

    def _mesh_prog(self, passes, verts=shapes3d.MAX_VERTS, shadow=False):
        """The shape program that draws `passes` passes of at most `verts` vertices in one go
        (or the single fallback program). shadow: its depth-only twin for the sun's shadow map."""
        key = (passes, verts) if self._mesh_inv else 0
        if shadow:
            key = ("shadow", key)
        p = self._mesh_progs.get(key)
        if p is None:
            geo, frag = shapes3d.program_sources(self._mesh_lib, passes if self._mesh_inv else None,
                                                 verts if self._mesh_inv else shapes3d.MAX_VERTS, shadow)
            p = self.ctx.program(vertex_shader=self._mesh_vs, geometry_shader=terrain3d.inject(geo, "R * 0.5"),
                                 fragment_shader=frag)
            p["sprite_texture"] = 0
            p["uv_texture"] = 1
            p["inflate"] = 1.0
            p["glow_pass"] = 0
            p["ShapeBlock"] = shapes3d.BINDING
            lighting3d.bind(p)
            self.hill_apply(p)              # HILLS (terrain3d.py)
            self._mesh_progs[key] = p
        return p

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
        if self._sh_pass:           # things lying flat cast no shadow (shadows3d.py)
            return
        self._draw_list(lst, self._progs3d[0], blend, height=float(height), boxes_only=int(boxes))

    def stand(self, lst, lift=0.0, nudge=0.0, cut=0.32, blend=None, shadow=False, sun=True):
        """Cut-outs facing the camera (shadow=True: their soft blob shadows on the ground instead).
        sun=False: not darkened by sun shadows (flames)."""
        if self._sh_pass:           # cut-outs don't cast into the shadow map: they keep their blobs
            return
        if shadow:
            self._draw_list(lst, self._progs3d[1], blend, mode=1)
        elif not sun:
            self._draw_list(lst, self._progs3d[1], blend, lift=float(lift), nudge=float(nudge), alpha_cut=float(cut),
                            no_sun=1)
        else:
            self._draw_list(lst, self._progs3d[1], blend, lift=float(lift), nudge=float(nudge), alpha_cut=float(cut))

    def drop_shadows(self, L, fp, shade):
        """The soft blob shadows under everything standing up. While the sun casts real shadows
        (shadows3d.py) the 3D shapes and models don't need theirs: they fade out as the real ones fade in
        (so at night it's the old look), creatures keep a faint one where they touch the ground, and
        painted cut-outs keep theirs."""
        bill = self._progs3d[1]
        k = self._sh_k
        if k <= 0.0:
            for lst in (L.bushes, L.rocks, L.builds, L.animals, self.player_list, L.zombies, L.bosses, L.huts, L.trees):
                self.stand(lst, shadow=True)
            return
        try:
            for lst, ver, shaped in ((L.bushes, 0, None), (L.rocks, 0, None),
                                     (L.builds, getattr(self, "struct_ver", 0), MESH_BUILDS),
                                     (L.trees, getattr(self, "nodes_ver", 0), None)):
                for kind, sub in self._by_kind(lst, ver).items():
                    real = shapes3d.SHAPES.get(kind) is not None and (shaped is None or kind in shaped)
                    bill["shade"] = shade * (1.0 - k) if real else shade
                    self.stand(sub, shadow=True)
            bill["shade"] = shade * (1.0 - k)
            self.stand(L.huts, shadow=True)
            bill["shade"] = shade * (1.0 - 0.7 * k) if (fp or self.models3d_mode(fp)) else shade
            for lst in (L.animals, self.player_list, L.zombies, L.bosses):
                self.stand(lst, shadow=True)
        finally:
            bill["shade"] = shade

    def mesh(self, lst, shape, cut=None, inflate=1.0, blend=None, glow=False):
        """Draw every sprite in `lst` as the 3D shape `shape` (shapes3d.SHAPES) with its picture draped on.
        glow=True: only its glowing parts, for adding on top of the night (call with an additive blend)."""
        if not len(lst):
            return
        if glow and self._sh_pass:
            return
        sh = shapes3d.SHAPES[shape]
        if sh.ubo is None:
            sh.ubo = self.ctx.buffer(data=sh.data)
        sh.ubo.bind_to_uniform_block(shapes3d.BINDING)
        p = self._mesh_prog(sh.passes, sh.verts, self._sh_pass)    # shadow pass: the depth-only twin
        p["coarse"] = int(self._sh_pass)       # small extras cast no shadow (cheaper)
        p["inflate"] = float(inflate)
        p.set_uniform_safe("sun", self._progs3d[1]["sun"])     # (only shading: not in the depth twin)
        p["alpha_cut"] = float(sh.cut if cut is None else cut)
        p["time"] = time.perf_counter() - self._mesh_t0
        p["glow_pass"] = int(glow)
        lst._init_deferred()
        old = lst.data.program
        lst.data.program = p
        try:
            if self._mesh_inv:
                lst.draw(blend_function=blend)
            else:
                for i in range(sh.passes):
                    p["pass_id"] = i
                    lst.draw(blend_function=blend)
        finally:
            lst.data.program = old
            if glow:
                p["glow_pass"] = 0

    def _by_kind(self, lst, ver=0):
        """The sprites of `lst` split into one SpriteList per .kind (rebuilt only when `lst` changes).
        The sprites stay in `lst` too, so the game never notices."""
        got = self._kinds3d.get(id(lst))
        sig = (len(lst), ver)
        if got is None or got[0] != sig or got[1] is not lst:
            if got is not None:
                for sub in got[2].values():
                    sub.clear()
            groups = {}
            for s in lst:
                kind = shapes3d.shape_key(s)
                if kind not in groups:
                    groups[kind] = arcade.SpriteList()
                groups[kind].append(s)
                lift = shapes3d.FLAME_DEPTH.get(kind)
                if lift is not None and getattr(s, "extras", None):
                    s.extras[0].depth = lift          # its flame burns on top of the 3D shape
            got = self._kinds3d[id(lst)] = (sig, lst, groups)
        return got[2]

    def draw_kinds(self, lst, ver=0, shaped=None):
        """Draw a mixed list: kinds with a 3D shape as shapes, the rest as cut-outs."""
        for kind, sub in self._by_kind(lst, ver).items():
            if not len(sub):
                continue
            sh = shapes3d.SHAPES.get(kind) if shaped is None or kind in shaped else None
            if sh is None:
                self.stand(sub)
                continue
            self.mesh(sub, kind)
            if sh.card_lift is not None:        # e.g. the turret's crossbow stands on its pedestal
                s0 = sub[0]
                self.stand(sub, lift=min(s0.width, s0.height) / 2 * sh.card_lift / UP)

    def draw_kind_glows(self, lst, ver=0, shaped=None):
        """The glowing parts of a mixed list's shapes (glowcaps, lantern glass...), added on top of the night."""
        blend = (self.ctx.SRC_ALPHA, self.ctx.ONE)
        for kind, sub in self._by_kind(lst, ver).items():
            sh = shapes3d.SHAPES.get(kind) if shaped is None or kind in shaped else None
            if sh is not None and sh.has_glow and len(sub):
                self.mesh(sub, kind, blend=blend, glow=True)

    # ------------------------------------------------------------------ 3D blocks
    def _box(self, out, x0, y0, x1, y1, h, col, faces, ground=None, pattern=0):
        """Side faces of a block (the top is the sprite, drawn flat at height h), for WALL_VS / WALL_FS:
        position, normal, colour + pattern, height 0..1 per vertex - the shader does all the shading.
        ground(x, y): HILLS - the bottom follows the ground at each corner, the top sits level h above the
        ground under the centre (the flat shader puts the top sprite there too)."""
        rgbp = tuple(c / 255 for c in col) + (float(pattern),)
        top_z = h + (ground((x0 + x1) / 2, (y0 + y1) / 2) if ground else 0.0)

        def quad(a, bb, c, d, nrm):
            for (px, py, pz) in (a, bb, c, a, c, d):
                if ground:
                    out.extend((px, py, top_z if pz > 0 else ground(px, py) - 4.0))
                else:
                    out.extend((px, py, pz))
                out.extend(nrm)
                out.extend(rgbp)
                out.append(1.0 if pz > 0 else 0.0)

        if "s" in faces:
            quad((x0, y0, 0), (x1, y0, 0), (x1, y0, h), (x0, y0, h), (0.0, -1.0, 0.0))
        if "e" in faces:
            quad((x1, y0, 0), (x1, y1, 0), (x1, y1, h), (x1, y0, h), (1.0, 0.0, 0.0))
        if "w" in faces:
            quad((x0, y1, 0), (x0, y0, 0), (x0, y0, h), (x0, y1, h), (-1.0, 0.0, 0.0))
        if "n" in faces:
            quad((x1, y1, 0), (x0, y1, 0), (x0, y1, h), (x1, y1, h), (0.0, 1.0, 0.0))

    def _block_geo(self, data):
        """Wall blocks made by _box, for the wall program. (_geo below stays the plain coloured-triangle
        format terrain.py uses.)"""
        if not data:
            return None
        buf = self.ctx.buffer(data=array("f", data))
        return self.ctx.geometry([BufferDescription(buf, "3f 3f 4f 1f", ["in_pos", "in_nrm", "in_col", "in_h"])],
                                 mode=self.ctx.TRIANGLES)

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
                self._box(out, x * C, y * C, x * C + C, y * C + C, CAVE_WALL_HEIGHT,
                          getattr(L, "wall_col", (96, 84, 78)), faces,      # a layer may tint its rock
                          pattern=CAVE_PATTERN)
        geo = self._wall_geo[key] = self._block_geo(out)
        return geo

    def _built_walls(self, L):
        walls = [s for s in L.builds if getattr(s, "kind", "") in WALL_KINDS]
        hg = self.hill_grid(L.name)
        sig = (id(hg),) + tuple((id(s), s.center_x, s.center_y) for s in walls)
        if self._wall_sig.get(L.name) != sig:
            self._wall_sig[L.name] = sig
            out = []
            for s in walls:
                s.depth = -1
                hw, hh = s.width / 2, s.height / 2
                self._box(out, s.center_x - hw, s.center_y - hh, s.center_x + hw, s.center_y + hh,
                          BUILD_WALL_HEIGHT, WALL_SIDES[s.kind], "sewn", hg.at if hg is not None else None,
                          WALL_PATTERN.get(s.kind, 0))
            self._wall_geo[L.name] = self._block_geo(out)
        return self._wall_geo.get(L.name)

    # ------------------------------------------------------------------ trees
    def _trees(self, L, view):
        """Tell the tree shapes which trees are standing (depth) and keep trees from hiding you."""
        if L.name != "over":
            return
        vx, vy = view
        fp = self.fp_on()
        for n in L.trees:
            full = n.state == "full"
            if n.kind == "tree":
                lift = TRUNK_LIFT if full else 0
                if n.depth != lift:
                    n.depth = lift
                if fp:
                    if n.alpha != 255:
                        n.alpha = 255      # from your own eyes nothing needs to be see-through
                elif full and 0 < vy - n.center_y < 170 and abs(n.center_x - vx) < 70:
                    n.alpha = 120          # don't let a tree in front hide you
            else:   # beehive: a 3D hive hanging under the canopy (shapes3d "hive", raised by its depth)
                up = n.tree is not None and n.tree.state == "full"
                want = HIVE_Z if up else 0
                if n.depth != want:
                    n.depth = want

    # ------------------------------------------------------------------ light + fog (lighting3d.py)
    def _lt_frame(self, L, vl, dk, sx, sy, fp):
        """Fill this view's LightBlock: camera, time-of-day ambient, sun, rim, point lights and fog.
        Call with the 3D camera on (it reads the matrices and the viewport)."""
        st = self._lt
        st.inv = tuple(~(self.projection @ self.view))
        st.vp = tuple(float(v) for v in self.ctx.viewport)
        (ex, ey, ez), f, _, _, d, _, _ = self._basis()
        st.eye = (ex, ey, ez)
        on = self.fx_lighting_on(vl, dk)
        st.amb = tuple(self.fx_ambient(vl)) if on else (1.0, 1.0, 1.0)
        lx, ly, lz = -sx, -sy, 1.4
        n = math.sqrt(lx * lx + ly * ly + lz * lz)
        st.sun = (lx / n, ly / n, lz / n)
        fx, fy = -f[0], -f[1]                       # the fill comes from behind the camera
        n = math.hypot(fx, fy) or 1.0
        fx, fy = fx / n * 0.96, fy / n * 0.96
        st.fill = (fx, fy, 0.29)
        rim = lighting3d.FILL_RIM_NIGHT if vl == "over" else lighting3d.FILL_RIM_CAVE
        st.rim = tuple(c * 0.55 * dk for c in rim)
        # point lights: the same sources as the light map (fx3d.fx_light_data), nearest first
        data = self.fx_light_data(L, vl, dk) if on else []
        self._lt_data = data
        own = tuple(self.cam_pos) if self.cut else self.view_pos()
        st.lights = lighting3d.pick_lights(data, self.view_pos(), self.ground_z, own)
        # fog: the biome's haze (the layer's, underground), foggy / rainy weather; first person fades into
        # the sky at the horizon
        haze = self.biome_fog() if hasattr(self, "layout") else None
        kind, k = getattr(self, "weather_shown", None), getattr(self, "weather_k", 0.0)
        over = vl == "over"
        horizon = lighting3d.FP_HORIZON
        if not over:
            import biomes
            info = biomes.LAYER_INFO.get(vl)
            horizon = (info and info.sky) or (22, 18, 16)
            haze = haze or horizon + (40,)
        st.fog, st.fogk = lighting3d.fog_params(fp, d, haze,
                                                k if over and kind == "fog" else 0.0,
                                                k if over and kind in ("rain", "storm") else 0.0, horizon)

    # ------------------------------------------------------------------ the frame
    def draw_world_3d(self, L, vl):
        self._init3d()
        ctx = self.ctx
        view = self.view_pos()
        self._trees(L, view)
        cave_geo = self._cave_walls(L) if vl != "over" else None   # any underground layer
        built_geo = self._built_walls(L)
        self.fx_tick()               # fx3d.py: particles move once per frame (not once per split view)
        self._m3_init()
        hilly = self.hill_bind(vl)   # HILLS (terrain3d.py): the height texture, or flat for this layer
        dk = self.layer_dark(vl) if vl != "over" else self.darkness   # biomes.LAYER_INFO
        sx, sy, shade = fx3d.sun(self.phase if vl == "over" else 0.27, dk)
        bill = self._progs3d[1]
        bill["sun"] = (sx, sy)
        bill["shade"] = shade
        fp = self.fp_on()
        bill["fp"] = int(fp)
        bill["face_right"] = (math.sin(self.fp_yaw), -math.cos(self.fp_yaw)) if fp else (1.0, 0.0)
        self.sh_frame(L, vl, dk, (sx, sy), shade, fp, built_geo)    # shadows3d.py: the sun's shadow map
        self.post_begin(vl)          # post3d.py: glow effects - draw the world offscreen (no-op when off)
        if fp:
            self.gui.use()
            self.fp_draw_sky(vl)          # firstperson.py: sky to the horizon
            self.fp_hide_me(True)
        self.use_world3d()
        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)
        self._lt_frame(L, vl, dk, sx, sy, fp)    # lighting3d.py: lights, fog, camera for this view
        self._lt.write("ground")

        # ---- on the ground
        if hilly:       # HILLS: the ground is a heightfield; what lies on it is depth tested against it
            ctx.enable(ctx.DEPTH_TEST)
            gl.glDepthFunc(gl.GL_LEQUAL)
            self.draw_hill_ground(L.ground, (sx, sy))
            gl.glDepthMask(gl.GL_FALSE)
        else:
            self.flat(L.ground)
        if vl == "over":
            water3d.draw_bog(self, getattr(self, "swamp_pool_list", None))    # water3d.py: the Mire's pools
        self.flat(L.decor)
        self.biome_draw3d(L, vl, "ground")     # biomes.py: rivers, roads, worn ground (terrain.py)
        water3d.draw_ponds(self, L.ponds)     # water3d.py: ponds with moving water
        if vl == "over":
            self.flat(L.exits)
        self.flat(L.traps)
        if hilly:       # plain arcade shapes: lifted onto the ground under each hazard, drawn over the hills
            ctx.disable(ctx.DEPTH_TEST)
            every = self.hazards
            try:
                for h in every:
                    self.hazards = [h]
                    self.lift_to_ground(h.x, h.y)
                    self.draw_ground_hazards()
            finally:
                self.hazards = every
                self.lift_to_ground()
            ctx.enable(ctx.DEPTH_TEST)
        else:
            self.draw_ground_hazards()
        self.drop_shadows(L, fp, shade)
        if hilly:
            gl.glDepthMask(gl.GL_TRUE)
            ctx.disable(ctx.DEPTH_TEST)
        for x, y, r0, r1, t, dur, col, *ly in self.rings:
            if ly and ly[0] != vl:
                continue
            k = t / dur
            self.ground_ring(x, y, r0 + (r1 - r0) * k, col + (int(230 * (1 - k)),), 6 * (1 - k) + 2)

        # ---- time of day: colour grading + light map over the ground (fx3d.py) - replaces the old darkness
        # sheet. Everything from here on stands up and lights itself (lighting3d.py "lit" stage).
        self.fx_lighting(L, vl, dk, self._lt_data)
        self.use_world3d()
        self._lt.write("lit")

        # ---- standing up (depth tested so blocks hide what's behind them)
        ctx.enable(ctx.DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LEQUAL)
        if cave_geo:
            cave_geo.render(self._wall_prog)
            self.flat(L.walls, CAVE_WALL_HEIGHT, boxes=True)
        if built_geo:
            built_geo.render(self._wall_prog)
            self.flat(L.builds, BUILD_WALL_HEIGHT, boxes=True)
        if vl != "over":
            self.stand(L.exits)
            self.stand(getattr(L, "shrines", self._ghost3d), cut=0.05)     # spells.py
        self.biome_draw3d(L, vl, "solid")      # biomes.py: cliffs, bridges, crops, fish (terrain.py)
        self.draw_kinds(L.bushes)
        self.draw_kinds(L.rocks)
        self.draw_kinds(L.builds, getattr(self, "struct_ver", 0), MESH_BUILDS)
        self.draw_packs_3d(vl)       # backpack.py: packs dropped where survivors died
        self.stand(L.flames, lift=2, nudge=2, cut=0.05, sun=False)
        if self.models3d_mode(fp):      # models3d.py: real low-poly 3D creatures (Blender-built models)
            self.models3d_creatures(L, fp)
        elif fp:        # from eye level the painted-from-above creatures need real bodies
            self.mesh(L.animals, "body")
            self.mesh(self.cloak_list, "person", inflate=1.08)
            self.mesh(self.player_list, "person")
            self.mesh(self.gear_list, "person", inflate=1.04)
            self.stand(self.held_list, lift=8, nudge=2)
            self.mesh(L.zombies, "person")
            self.mesh(L.bosses, "boss")
        else:
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
        self.mesh(L.huts, "hut")
        self.draw_kinds(L.trees, getattr(self, "nodes_ver", 0))
        self.biome_draw3d(L, vl)     # biomes.py: plug-ins' own 3D props (highland ledges, rolling boulders...)
        if fp:
            self.fp_hide_me(False)

        # ---- build preview & tame target
        if self.state == "playing" and self.me and not self.ui_open and not self.cut:
            pl = self.placement(self.me, self.aim_world())
            if pl:
                item, ghost, ok = pl
                ghost.alpha = 150
                ghost.color = (150, 255, 150) if ok else (255, 110, 110)
                self._ghost3d.clear()
                self._ghost3d.append(ghost)
                if item in MESH_BUILDS or item == "hut":
                    self.mesh(self._ghost3d, item, cut=0.05)
                    sh = shapes3d.SHAPES[item]
                    if sh.card_lift is not None:
                        self.stand(self._ghost3d, cut=0.05,
                                   lift=min(ghost.width, ghost.height) / 2 * sh.card_lift / UP)
                else:
                    self.stand(self._ghost3d, cut=0.05)
                self._ghost3d.clear()
                self._ring_lit = True        # (drawn after the light map: darken it by hand)
                try:
                    self.draw_defense_preview(item, ghost)   # defenses.py: turret / lantern reach
                finally:
                    self._ring_lit = False
            ctx.disable(ctx.DEPTH_TEST)
            t = self.tame_target()
            if t:
                ctx.disable(ctx.DEPTH_TEST)
                self.ground_ring(t.center_x, t.center_y, 30, (255, 150, 190, 200), 2, lit=True)
        ctx.enable(ctx.DEPTH_TEST)
        self.fx_draw_particles(vl, additive=False)    # chips, dust, blood, smoke (lit like the rest)
        ctx.disable(ctx.DEPTH_TEST)
        self._lt.write("glow")      # glows from here on: not darkened, faded out (not fogged) far away

        # ---- floating things, drawn on screen at their 3D spot
        self.gui.use()
        self.draw_air_hazards()
        self.draw_pet_marks(L)
        self.draw_pack_marks(vl)     # backpack.py: "Your pack 2:10" / "Sam's pack"

        if dk > 0:
            self.use_world3d()
            for g in L.glows:      # a warm haze over each fire (the light map already lights the ground)
                g.alpha = int(130 * dk) + 20
            blend = (ctx.SRC_ALPHA, ctx.ONE)
            self.flat(L.glows, blend=blend)
            self.post_glow()         # post3d.py: what's drawn from here on blooms (not the wide haze above)
            ctx.enable(ctx.DEPTH_TEST)
            self.stand(L.flames, lift=2, nudge=2, cut=0.05, sun=False)
            self.draw_kind_glows(L.bushes)        # glowcaps, glowing crystals, lantern glass...
            self.draw_kind_glows(L.rocks)
            self.draw_kind_glows(L.builds, getattr(self, "struct_ver", 0), MESH_BUILDS)
            for e in L.eyes:
                e.alpha = int(255 * dk)
            if self.models3d_mode(fp):  # glows sit on the models' eyes / cores
                self.models3d_glows(dk)
            elif fp:    # on the zombie's 3D head, just in front of its face
                self.stand(L.eyes, lift=40, nudge=16, cut=0.0, blend=blend)
            else:
                self.stand(L.eyes, lift=16, nudge=3, cut=0.0, blend=blend)
            ctx.disable(ctx.DEPTH_TEST)
            for p in self.players.values():   # teammates carry a little lantern so you can find them
                if p is not self.me and p.alive and p.layer == vl:
                    self.lift_to_ground(p.sprite.center_x, p.sprite.center_y)
                    arcade.draw_circle_filled(p.sprite.center_x, p.sprite.center_y, 30, p.color + (int(70 * dk),))
            self.draw_pack_glows(vl, dk)     # backpack.py: a dropped pack's lamp and a faint pool of light
            for b in L.bosses:     # bosses are always visible - terrifying silhouettes
                self.lift_to_ground(b.center_x, b.center_y)
                arcade.draw_circle_filled(b.center_x, b.center_y, b.radius + 30, (255, 80, 40, int(40 * dk)))
            self.lift_to_ground()
            if vl != "over":
                for s in L.exits:
                    arcade.draw_circle_filled(s.center_x, s.center_y, 60, (255, 240, 200, 40))
        self.post_glow()             # post3d.py: (by day) the embers and sparks below bloom
        self.use_world3d()           # embers, sparks and flames glow on top of the night
        ctx.enable(ctx.DEPTH_TEST)
        self.fx_draw_particles(vl, additive=True)
        ctx.disable(ctx.DEPTH_TEST)
        self.gui.use()
        self.post_end(dk)            # post3d.py: bloom + colour grade onto the screen (HUD etc. come after)
        self.fx_vignette(dk)         # fx3d.py: night vignette on the finished picture (not bloomed)

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
        """Falling boulders/meteors and flying globs, drawn at their height (called in GUI space, after the
        light map - so each is darkened by the light where it is, lit_col)."""
        if self.view_layer != "over":
            return
        for h in self.hazards:
            if h.kind in ("boulder", "meteor") and h.tele > 0:
                k = max(0.0, h.tele)
                z = 40 + k * 420
                s = self.project(h.x, h.y, z)
                if h.kind == "boulder":
                    col = self.lit_col((130, 120, 110, 240), h.x, h.y, z)
                else:       # a meteor burns: it mostly shines by itself
                    col = self.lit_col((255, 120, 40, 240), h.x, h.y, z, glow=0.6)
                if s:
                    arcade.draw_circle_filled(s[0], s[1], 16 + 6 * (1 - k), col)
            elif h.kind == "glob" and h.tele <= 0:
                s = self.project(h.x, h.y, 24)
                if s:
                    arcade.draw_circle_filled(s[0], s[1], h.r, self.lit_col((140, 230, 70, 240), h.x, h.y, 24))
            elif h.kind == "shard" and h.tele <= 0:
                a = math.atan2(h.vy, h.vx)
                p0 = self.project(h.x - math.cos(a) * 14, h.y - math.sin(a) * 14, 24)
                p1 = self.project(h.x + math.cos(a) * 8, h.y + math.sin(a) * 8, 24)
                if p0 and p1:
                    arcade.draw_line(*p0, *p1, self.lit_col((190, 235, 255, 255), h.x, h.y, 24, glow=0.3), 5)
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
            elif s.kind == "fireball":
                p = self.project(s.x, s.y, h)
                if p:
                    arcade.draw_circle_filled(p[0], p[1], 15, (255, 120, 30, 90))
                    arcade.draw_circle_filled(p[0], p[1], 9, (255, 170, 60, 255))
                    arcade.draw_circle_filled(p[0], p[1], 4, (255, 240, 180, 255))
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
            z = a.height * UP
            col = self.lit_col(col, a.center_x, a.center_y, z)      # drawn after the light map: dark at night
            arcade.draw_circle_filled(s[0], s[1], 5, col + (230,))
            arcade.draw_circle_outline(s[0], s[1], 5, self.lit_col((255, 255, 255, 200), a.center_x, a.center_y, z), 1)
            if a.name:
                shield = " +" if a.armor else ""
                ty = s[1] + 9
                while any(abs(s[0] - tx) < 70 and abs(ty - yy) < 13 for tx, yy in tags):
                    ty += 13
                tags.append((s[0], ty))
                self.txt(f"petname{a.aid}", a.name + shield, s[0], ty, col + (230,), 10, anchor_x="center",
                         bold=True)
            if a.carrying:
                arcade.draw_circle_filled(s[0] + 10, s[1], 4, self.lit_col((255, 220, 120, 230), a.center_x, a.center_y, z))

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
