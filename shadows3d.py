"""
shadows3d.py - real sun shadows for the 3D view (a shadow map). Mixed into View3D.

How it works, once per view and frame, on the surface by day (view3d.draw_world_3d calls sh_frame first):
  1. Fit a square around what the camera can see (the tilted camera's patch of ground, or first person
     out to FP_REACH), turned to face the sun. Its size never changes with the camera - only where it
     sits - and that spot is snapped to whole shadow-map texels, so shadow edges don't crawl or shimmer
     as you walk.
  2. Draw everything that casts a shadow into a depth-only texture, as seen from the sun with a straight
     (orthographic) projection: the 3D shapes (trees, rocks, bushes, buildings - shapes3d's geometry
     shader with a depth-only fragment shader, see-through picture pixels let the light through), the
     creature models (models3d), the wall blocks, cliffs and bridges (small extras on the shapes - flowers,
     little leaves - are left out). It's the same drawing code as the
     real frame: view3d's mesh() / stand() / flat() check `_sh_pass` and swap in the depth programs
     (cut-outs and flat things don't cast). Nothing is built on the CPU, and everything outside the square
     is thrown away by the shaders' own culling.
  3. Every lit shader asks lighting3d's lt_sunlit(position, normal) how much sun reaches each pixel
     (3 x 3 filtered taps, with offsets that grow at grazing angles so surfaces never shadow themselves)
     and takes that much of its daylight away. Shadows fade out at the edge of the square.

The sun direction is the one everything is already lit with: (-sx, -sy, 1.4) from fx3d.sun() - long
shadows morning and evening, short at noon. The shadows fade with the evening (gone at night, when the old
soft blob shadows take over again - view3d.drop_shadows) and aren't drawn underground.

Option "sun_shadows" in lastlight_config.json (Screen & graphics): "on" (default), "low" (a smaller map and
fewer taps - for slow computers) or "off" (exactly the old blob shadows).
"""
import math

from pyglet import gl
from pyglet.math import Mat4, Vec3, Vec4

import lighting3d
import models3d
import terrain3d

SHADOW_RES = 2048               # shadow map size ("on")
SHADOW_RES_LOW = 1024           # ... and on "low"
SUN_DARK = 0.5                  # how much of the daylight a full shadow takes away at noon
FP_REACH = 1500.0               # first person: shadows reach this far ahead (then fade out)
TOWARD_SUN = 1500.0             # the box reaches this far towards the sun (tall things off to the side)
AWAY_SUN = 800.0                # ... and this far below the middle of the view (valleys)
MARGIN = 1.08                   # a little more than the screen (things just off screen cast onto it)

DEPTH_VS = """
#version 330
uniform WindowBlock { mat4 projection; mat4 view; } window;
in vec3 in_pos;
void main() { gl_Position = window.projection * window.view * vec4(in_pos, 1.0); }
"""
DEPTH_FS = """
#version 330
void main() { }
"""


class SunShadows:
    """Mixed into View3D (needs its _basis, ground_z, mesh / draw_kinds and the lighting state)."""

    _sh_broken = False
    _sh_pass = False             # True while the casters are drawn into the shadow map
    _sh_k = 0.0                  # how much the real shadows stand in for the blob shadows this view (0..1)

    # ------------------------------------------------------------------ the option
    def shadows_mode(self):
        """"on", "low" or "off" (config "sun_shadows"; true / false work too)."""
        v = (getattr(self, "cfg", {}) or {}).get("sun_shadows", "on")
        if v is False:
            return "off"
        return v if v in ("low", "off") else "on"

    def toggle_shadows(self):
        """Screen & graphics: On -> Low -> Off -> On."""
        nxt = {"on": "low", "low": "off", "off": "on"}[self.shadows_mode()]
        self.cfg["sun_shadows"] = nxt
        self._sh_broken = False
        self.save_cfg()

    # ------------------------------------------------------------------ GPU bits
    def _sh_init(self, res):
        if getattr(self, "_sh_res", None) == res:
            return
        ctx = self.ctx
        if getattr(self, "_sh_fbo", None):
            gl.glDeleteFramebuffers(1, self._sh_fbo)
            self._sh_tex.delete()
        else:
            self._sh_depth_prog = ctx.program(vertex_shader=DEPTH_VS, fragment_shader=DEPTH_FS)
            self._sh_m3 = ctx.program(vertex_shader=terrain3d.inject_models(models3d.VS),
                                      fragment_shader=models3d.SHADOW_FS)
            # a 1 x 1 stand-in while there's no real map (and while drawing into the real one)
            self._sh_none = ctx.depth_texture((1, 1))
        tex = ctx.depth_texture((res, res))
        tex.filter = (ctx.LINEAR, ctx.LINEAR)      # with the compare mode: a free 2 x 2 filtered lookup each
        tex.wrap_x = tex.wrap_y = ctx.CLAMP_TO_EDGE
        # our own framebuffer with only a depth texture and no colour (arcade's would ask for a colour target)
        fbo = gl.GLuint()
        gl.glGenFramebuffers(1, fbo)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, fbo)
        gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_DEPTH_ATTACHMENT, gl.GL_TEXTURE_2D, tex.glo, 0)
        gl.glDrawBuffer(gl.GL_NONE)
        gl.glReadBuffer(gl.GL_NONE)
        ok = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) == gl.GL_FRAMEBUFFER_COMPLETE
        ctx.active_framebuffer.use(force=True)
        self._sh_tex, self._sh_fbo, self._sh_res = tex, fbo, res
        if not ok:
            raise RuntimeError("the shadow map framebuffer isn't complete")

    def _sh_fail(self, e):
        print("Sun shadows switched off - this graphics card didn't like them:", e)
        self._sh_broken = True
        self._sh_pass = False
        self._sh_k = 0.0
        self._lt.shk = (0.0,) + tuple(self._lt.shk[1:])
        try:
            self.ctx.active_framebuffer.use(force=True)
        except Exception:      # noqa: BLE001 - already failing
            pass

    # ------------------------------------------------------------------ fitting the map to the view
    def _sh_area(self, fp):
        """(centre x, y, z, radius) of a circle on the ground holding everything this view shows. The
        radius depends only on the camera's shape, never on where it is or which way it turns."""
        (ex, ey, ez), f, r, u, d, vw, vh = self._basis()
        if fp:
            hf = math.atan2(vw / 2 * MARGIN, d)          # half the horizontal field of view
            k = FP_REACH * 0.5
            yaw = self.fp_yaw
            cx, cy = ex + math.cos(yaw) * k, ey + math.sin(yaw) * k
            far = (FP_REACH * math.cos(hf) - k, FP_REACH * math.sin(hf))
            rad = max(k, math.hypot(*far), FP_REACH - k) + 64.0     # (+ room behind you)
            return cx, cy, self.ground_z(cx, cy), rad
        gz = self.ground_z(*self.camera.position)
        pts = []
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            a, b = sx * vw / 2 * MARGIN / d, sy * vh / 2 * MARGIN / d
            dx, dy, dz = (f[i] + r[i] * a + u[i] * b for i in range(3))
            t = (gz - ez) / min(dz, -1e-3)
            pts.append((ex + dx * t, ey + dy * t))
        cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
        cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2
        rad = max(math.hypot(px - cx, py - cy) for px, py in pts)
        return cx, cy, gz, math.ceil(rad / 64.0) * 64.0         # (whole steps: never wobbles)

    def _sh_matrices(self, sun_dir, area, res):
        """The sun's view and orthographic projection for the area, snapped to whole texels."""
        cx, cy, cz, rad = area
        lx, ly, lz = sun_dir
        view = Mat4.look_at(Vec3(lx, ly, lz), Vec3(0.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0))
        c = view @ Vec4(cx, cy, cz, 1.0)
        texel = 2.0 * rad / res
        x0 = round(c.x / texel) * texel
        y0 = round(c.y / texel) * texel
        dist = -c.z
        near, far = dist - TOWARD_SUN, dist + AWAY_SUN
        proj = Mat4.orthogonal_projection(x0 - rad, x0 + rad, y0 - rad, y0 + rad, near, far)
        return view, proj, texel, far - near

    # ------------------------------------------------------------------ the frame
    def sh_frame(self, L, vl, dk, sun, shade, fp, built_geo):
        """Draw this view's shadow map (or switch shadows off for it) and fill in the lighting state's
        shadow values. Call at the start of draw_world_3d, before anything is drawn: it leaves the
        framebuffer and viewport as they were, but the 3D camera has to be set up again afterwards."""
        st = self._lt
        st.shk = (0.0, 1.0, 0.0, 9.0)
        self._sh_k = 0.0
        mode = self.shadows_mode()
        k = SUN_DARK * (1.0 - dk) * shade
        if mode == "off" or self._sh_broken or vl != "over" or k < 0.02:
            if getattr(self, "_sh_none", None) is not None:
                self._sh_none.use(lighting3d.SHADOW_UNIT)
            return
        low = mode == "low"
        try:
            res = SHADOW_RES_LOW if low else SHADOW_RES
            self._sh_init(res)
            sx, sy = sun
            n = math.sqrt(sx * sx + sy * sy + 1.4 * 1.4)
            sun_dir = (-sx / n, -sy / n, 1.4 / n)           # the same as lighting3d's lt_sun
            view, proj, texel, depth = self._sh_matrices(sun_dir, self._sh_area(fp), res)
            self._sh_draw(L, vl, fp, built_geo, view, proj, res)
        except Exception as e:      # noqa: BLE001 - never let a graphics extra stop the game
            self._sh_fail(e)
            return
        self._sh_tex.use(lighting3d.SHADOW_UNIT)
        st.shm = tuple(proj @ view)
        st.shk = (k, texel, 1.0 / depth, 4.0 if low else 9.0)
        self._sh_k = 1.0 - dk           # the blob shadows of real casters fade out as these fade in

    def _sh_draw(self, L, vl, fp, built_geo, view, proj, res):
        ctx = self.ctx
        self._sh_none.use(lighting3d.SHADOW_UNIT)       # never read the map while drawing into it
        depth_on = ctx.is_enabled(ctx.DEPTH_TEST)
        func = gl.GLint()
        gl.glGetIntegerv(gl.GL_DEPTH_FUNC, func)
        self.projection, self.view = proj, view          # every world shader now looks from the sun
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self._sh_fbo)
        gl.glViewport(0, 0, res, res)
        gl.glScissor(0, 0, res, res)                     # (split screen leaves the scissor test on)
        gl.glDepthMask(gl.GL_TRUE)
        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)
        ctx.enable(ctx.DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LEQUAL)
        # slope-scaled bias on the casters' side: faces seen edge-on from the sun get pushed back most
        gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
        gl.glPolygonOffset(1.5, 2.0)
        progs = self._progs3d
        m3 = getattr(self, "_m3_prog", None)
        self._sh_pass = True
        self._progs3d = (progs[0], progs[1], self._sh_depth_prog)     # terrain_draw's cliffs use [2]
        try:
            self._sh_casters(L, vl, fp, built_geo)
        finally:
            self._sh_pass = False
            self._progs3d = progs
            if m3 is not None:
                self._m3_prog = m3
            gl.glDisable(gl.GL_POLYGON_OFFSET_FILL)
            gl.glDepthFunc(func.value)
            if not depth_on:
                ctx.disable(ctx.DEPTH_TEST)
            ctx.active_framebuffer.use(force=True)       # back to the screen / glow picture, its viewport

    def _sh_casters(self, L, vl, fp, built_geo):
        """Everything that casts a shadow, in the same calls the frame uses (view3d.draw_world_3d)."""
        if built_geo:
            built_geo.render(self._sh_depth_prog)
        self.biome_draw3d(L, vl, "solid")          # cliffs, bridges, ford stones (terrain_draw.py)
        self.draw_kinds(L.bushes)
        self.draw_kinds(L.rocks)
        import view3d               # (its build list grows at run time - terrain_draw adds bridges)
        self.draw_kinds(L.builds, getattr(self, "struct_ver", 0), view3d.MESH_BUILDS)
        if self.models3d_mode(fp):
            self.hill_apply(self._sh_m3)
            self._m3_prog = self._sh_m3
            self.models3d_creatures(L, fp)
        elif fp:
            self.mesh(L.animals, "body")
            self.mesh(self.player_list, "person")
            self.mesh(L.zombies, "person")
            self.mesh(L.bosses, "boss")
        self.mesh(L.huts, "hut")
        self.draw_kinds(L.trees, getattr(self, "nodes_ver", 0))
        self.biome_draw3d(L, vl)                   # highland ledges, standing stones, rolling boulders
