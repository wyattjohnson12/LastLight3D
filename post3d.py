"""
post3d.py - glow (bloom), gentle colour and smooth edges for the 3D view. Mixed into the game window.

Without this the world is drawn straight onto the screen. With "Glow effects" on (the default) it goes
like this instead, once per view (split screen does it for each player's slice in turn):

  1. post_begin    - the world is drawn into an offscreen picture (colour + depth) the size of the window,
                     instead of onto the screen. With "Smooth edges" on that picture is multisampled
                     (MSAA), so edges stay smooth even though the window's own MSAA can't reach it.
  2. post_glow     - called by view3d.py after the light map and the fires' wide warm haze, just before
                     the glowing things (flames, glowcaps, crystals, lantern glass, zombie eyes, embers,
                     sparks) are added. We keep a copy of the picture at that moment...
  3. post_end      - ...so after the glows, "now minus that copy" is exactly the light the glowing things
                     added. That (plus a little of anything very bright) is blurred at quarter and eighth
                     size and added back as a soft halo. So fires, crystals and eyes bloom at night, but a
                     sunny white rock in the day doesn't turn into a blob.
                     The same pass gives a gentle colour grade: nothing at all in plain daylight, a touch
                     more colour and contrast as dusk and night come (darkness `dk`).

The HUD, menus, weather overlay, health bars and words over heads are drawn afterwards, straight onto the
screen, so they are never blurred or graded.

Options (lastlight_config.json, shown under "Screen & graphics" on the title screen):
    "glow_effects": true/false   - off = exactly the old drawing path (nothing here runs)
    "smooth_edges": true/false   - multisampling; the window's part needs a restart (main.py)

Cheap on purpose (school laptops): one full-size copy for the "before glows" picture, one to resolve the
multisampled picture, then everything else at 1/2, 1/4 and 1/8 size - 8 tiny passes in all. If anything
here fails on an odd driver, it prints once and the game quietly goes back to the plain path.
"""
from arcade.gl.backends.opengl.framebuffer import OpenGLFramebuffer
from arcade.gl.geometry import quad_2d_fs
from pyglet import gl

MSAA_SAMPLES = 4                 # what "Smooth edges" asks for (less if the graphics card can't do 4)
GLOW_DAY, GLOW_NIGHT = 0.6, 3.0    # how strongly the glowing things bloom, day -> full night
GLOW_SOFT = (0.04, 0.30)        # glow light fainter than this hardly blooms (soft edges, faint sprites)
BRIGHT_KNEE = 0.86               # anything brighter than this blooms too: flames, lantern glass, sun on snow
BRIGHT_DAY, BRIGHT_NIGHT = 0.08, 3.0   # ...hardly at all by day; at night only fires & lamps get that bright
NEAR_K, WIDE_K = 0.6, 1.0        # mix of the tight (1/4 size) and wide (1/8 size) halo


# ----------------------------------------------------------------- shaders
QUAD_VS = """
#version 330
in vec2 in_vert;
in vec2 in_uv;
out vec2 uv;
void main() { uv = in_uv; gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

# Half size: what did the glow passes add, plus a soft "very bright" part. One bilinear tap at a half-size
# pixel centre averages 2 x 2 full-size pixels, so this is also the first downsample.
EXTRACT_FS = """
#version 330
uniform sampler2D final;     // the finished world
uniform sampler2D base;      // the world just before the glowing things were added
uniform int has_base;
uniform float glow_k;
uniform float glow_lo;
uniform float glow_hi;
uniform float knee;
uniform float bright_k;
in vec2 uv;
out vec4 f_color;
void main() {
    vec3 c = texture(final, uv).rgb;
    vec3 g = has_base == 1 ? max(c - texture(base, uv).rgb, 0.0) : vec3(0.0);
    // the fire's wide, faint warm haze is already a glow: only strong, concentrated light blooms
    g *= smoothstep(glow_lo, glow_hi, max(g.r, max(g.g, g.b)));
    float l = max(c.r, max(c.g, c.b));
    float soft = clamp((l - knee) / (1.0 - knee), 0.0, 1.0);
    vec3 b = c * soft * soft;              // soft knee: fades in instead of a hard edge
    f_color = vec4(g * glow_k + b * bright_k, 1.0);
}
"""

# A smooth 2x downsample: four bilinear taps around the pixel (each already averages 4 texels).
DOWN_FS = """
#version 330
uniform sampler2D src;
uniform vec2 texel;          // 1 / source size
in vec2 uv;
out vec4 f_color;
void main() {
    vec3 s = texture(src, uv + texel * vec2(-1.0, -1.0)).rgb + texture(src, uv + texel * vec2(1.0, -1.0)).rgb
           + texture(src, uv + texel * vec2(-1.0, 1.0)).rgb + texture(src, uv + texel * vec2(1.0, 1.0)).rgb;
    f_color = vec4(s * 0.25, 1.0);
}
"""

# One direction of a 9-tap Gaussian, done in 5 taps by letting the bilinear filter blend neighbours.
BLUR_FS = """
#version 330
uniform sampler2D src;
uniform vec2 step;           // one texel along x or along y
in vec2 uv;
out vec4 f_color;
void main() {
    vec3 s = texture(src, uv).rgb * 0.2270270270;
    s += (texture(src, uv + step * 1.3846153846).rgb + texture(src, uv - step * 1.3846153846).rgb) * 0.3162162162;
    s += (texture(src, uv + step * 3.2307692308).rgb + texture(src, uv - step * 3.2307692308).rgb) * 0.0702702703;
    f_color = vec4(s, 1.0);
}
"""

# Put it together. The halo is added "screen" style, 1 - (1 - c) * exp(-halo): where there is no halo the
# picture is untouched, and hot spots ease towards white instead of clipping into flat blobs.
# Then the colour grade, scaled by `grade` (0 in daylight -> 1 at full night): a little more saturation
# and a gentle contrast curve around a low pivot, so night blues and firelight look richer.
COMP_FS = """
#version 330
uniform sampler2D final;
uniform sampler2D near;
uniform sampler2D wide;
uniform float near_k;
uniform float wide_k;
uniform float grade;
in vec2 uv;
out vec4 f_color;
void main() {
    vec3 c = texture(final, uv).rgb;
    vec3 halo = texture(near, uv).rgb * near_k + texture(wide, uv).rgb * wide_k;
    c = 1.0 - (1.0 - c) * exp(-halo);
    if (grade > 0.0) {
        float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
        c = clamp(mix(vec3(l), c, 1.0 + 0.16 * grade), 0.0, 1.0);  // saturation (clamped: pow() hates < 0)
        const float pivot = 0.22;
        vec3 curved = pivot * pow(c / pivot, vec3(1.0 + 0.10 * grade));   // contrast around the pivot
        vec3 upper = 1.0 - (1.0 - pivot) * pow((1.0 - c) / (1.0 - pivot), vec3(1.0 + 0.10 * grade));
        c = mix(curved, upper, step(pivot, c));
    }
    f_color = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""


class _HiDPIFramebuffer(OpenGLFramebuffer):
    """An offscreen framebuffer that takes viewports and scissor boxes in window units, like the screen does.
    The game's cameras give viewports in window units; the screen multiplies them by the pixel ratio (2 on a
    Retina Mac). A plain offscreen framebuffer wouldn't, and the world would land in one corner."""

    def _ratio(self):
        return self.ctx.window.get_pixel_ratio()

    @OpenGLFramebuffer.viewport.setter
    def viewport(self, value):
        r = self._ratio()
        OpenGLFramebuffer.viewport.fset(self, tuple(int(v * r) for v in value))

    @OpenGLFramebuffer.scissor.setter
    def scissor(self, value):
        r = self._ratio()
        OpenGLFramebuffer.scissor.fset(self, None if value is None else tuple(int(v * r) for v in value))


class Post3D:
    """Bloom + colour grade + multisampled offscreen world. Mixed into the game window."""

    _post_broken = False
    _post_active = False
    _post_no_ms = False

    # ------------------------------------------------------------------ options
    def post_wanted(self):
        """Glow effects on? (config "glow_effects", default on). Off = the plain old drawing path."""
        return bool(getattr(self, "cfg", {}).get("glow_effects", True)) and not self._post_broken

    def smooth_wanted(self):
        return bool(getattr(self, "cfg", {}).get("smooth_edges", True))

    def toggle_glow(self):
        self.cfg["glow_effects"] = not self.post_wanted()
        self._post_broken = False
        self.save_cfg()

    def toggle_smooth(self):
        """The offscreen picture follows this straight away; the window's own MSAA after a restart."""
        self.cfg["smooth_edges"] = not self.smooth_wanted()
        self.save_cfg()
        self._post_main = None          # rebuild the offscreen picture with / without samples

    def _post_fail(self, e):
        print("Glow effects switched off - this graphics card didn't like them:", e)
        self._post_broken = True
        self._post_active = False
        try:
            self.ctx.screen.use(force=True)
        except Exception:      # noqa: BLE001 - already failing; just get back to the screen
            pass

    # ------------------------------------------------------------------ GPU bits
    def _post_init(self):
        if getattr(self, "_post_progs", None):
            return
        ctx = self.ctx
        progs = {}
        for name, fs in (("extract", EXTRACT_FS), ("down", DOWN_FS), ("blur", BLUR_FS), ("comp", COMP_FS)):
            progs[name] = ctx.program(vertex_shader=QUAD_VS, fragment_shader=fs)
        progs["extract"]["final"] = 0
        progs["extract"]["base"] = 1
        progs["comp"]["final"] = 0
        progs["comp"]["near"] = 1
        progs["comp"]["wide"] = 2
        self._post_progs = progs
        self._post_quad = quad_2d_fs()
        self._post_main = None
        self._post_main_key = None
        self._post_views = {}

    def _post_samples(self):
        if not self.smooth_wanted() or self._post_no_ms:
            return 0
        most = int(getattr(self.ctx.info, "MAX_SAMPLES", 0) or 0)
        return min(MSAA_SAMPLES, most) if most >= 2 else 0

    def _post_make_main(self, size, samples):
        """The window-sized picture the world is drawn into (multisampled for smooth edges)."""
        ctx = self.ctx
        if samples:
            col = ctx.texture(size, components=4, samples=samples)
            dep = ctx.texture(size, components=4, samples=samples)
            # arcade can't make a multisampled depth texture, so turn this one into one ourselves
            gl.glActiveTexture(gl.GL_TEXTURE0 + ctx.default_texture_unit)
            gl.glBindTexture(gl.GL_TEXTURE_2D_MULTISAMPLE, dep.glo)
            gl.glTexImage2DMultisample(gl.GL_TEXTURE_2D_MULTISAMPLE, samples, gl.GL_DEPTH_COMPONENT24,
                                       size[0], size[1], True)
            gl.glBindTexture(gl.GL_TEXTURE_2D_MULTISAMPLE, 0)
        else:
            col = ctx.texture(size, components=4)
            dep = ctx.depth_texture(size)
        return _HiDPIFramebuffer(ctx, color_attachments=[col], depth_attachment=dep)

    def _post_main_fbo(self):
        size = tuple(int(v) for v in self.get_framebuffer_size())
        size = (max(16, size[0]), max(16, size[1]))
        key = (size, self._post_samples())
        if self._post_main is None or self._post_main_key != key:
            self._post_views = {}           # window changed size: the per-view targets go too
            self._post_main = None
            try:
                self._post_main = self._post_make_main(size, key[1])
            except Exception as e:          # noqa: BLE001 - e.g. no multisampled depth: try without
                if not key[1]:
                    raise
                print("Smooth edges: no multisampling for the glow picture -", e)
                self._post_no_ms = True     # (just for this run - the saved option is left alone)
                key = (size, 0)
                self._post_main = self._post_make_main(size, 0)
            self._post_main_key = key
        return self._post_main

    def _post_view_targets(self, w, h):
        """Textures sized to one view (split-screen slices are all the same size, so they share these)."""
        t = self._post_views.get((w, h))
        if t:
            return t
        ctx = self.ctx
        lin = (ctx.LINEAR, ctx.LINEAR)

        def target(tw, th, dtype="f1"):
            tex = ctx.texture((max(1, tw), max(1, th)), components=4, dtype=dtype, filter=lin,
                              wrap_x=ctx.CLAMP_TO_EDGE, wrap_y=ctx.CLAMP_TO_EDGE)
            return ctx.framebuffer(color_attachments=[tex]), tex

        t = {
            "final": target(w, h),
            "base": target(w, h),
            "half": target(w // 2, h // 2, "f2"),     # half floats: no banding in faint night halos
            "q_a": target(w // 4, h // 4, "f2"),
            "q_b": target(w // 4, h // 4, "f2"),
            "e_a": target(w // 8, h // 8, "f2"),
            "e_b": target(w // 8, h // 8, "f2"),
        }
        self._post_views[(w, h)] = t
        return t

    def _post_rect(self):
        """This view's rectangle in real framebuffer pixels (left, bottom, width, height)."""
        r = self.get_pixel_ratio()
        vx, vy, vw, vh = self.camera.viewport.lbwh
        fw, fh = self._post_main.width, self._post_main.height
        x0, y0 = max(0, int(vx * r)), max(0, int(vy * r))
        x1, y1 = min(fw, int((vx + vw) * r)), min(fh, int((vy + vh) * r))
        return x0, y0, max(1, x1 - x0), max(1, y1 - y0)

    def _post_blit(self, dst_fbo):
        """Copy (and, if multisampled, smooth down) this view's part of the world picture into dst_fbo."""
        x, y, w, h = self._post_rect_px
        gl.glDisable(gl.GL_SCISSOR_TEST)            # the scissor box would clip the copy
        gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, self._post_main.glo)
        gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, dst_fbo.glo)
        gl.glReadBuffer(gl.GL_COLOR_ATTACHMENT0)
        gl.glDrawBuffer(gl.GL_COLOR_ATTACHMENT0)
        gl.glBlitFramebuffer(x, y, x + w, y + h, 0, 0, w, h, gl.GL_COLOR_BUFFER_BIT, gl.GL_NEAREST)
        gl.glEnable(gl.GL_SCISSOR_TEST)
        self.ctx.active_framebuffer.use(force=True)   # put arcade's idea of what is bound back

    def _post_pass(self, prog, dst, *texs):
        fbo, tex = dst
        for i, t in enumerate(texs):
            t.use(i)
        with fbo.activate():
            fbo.viewport = (0, 0, tex.width, tex.height)
            self._post_quad.render(prog)

    # ------------------------------------------------------------------ hooks (called from view3d.py)
    def post_begin(self, vl):
        """Start of draw_world_3d: send the world into the offscreen picture (if glow effects are on)."""
        self._post_active = False
        if not self.post_wanted():
            return
        try:
            self._post_init()
            main = self._post_main_fbo()
            self._post_prev = self.ctx.active_framebuffer
            main.use()
            self._post_rect_px = x, y, w, h = self._post_rect()
            self._post_marked = False
            # the same background ui.on_draw paints under the world, plus a fresh depth buffer
            bg = (6, 6, 9) if vl != "over" else (24, 34, 22)
            gl.glScissor(x, y, w, h)
            gl.glClearColor(bg[0] / 255, bg[1] / 255, bg[2] / 255, 1.0)
            gl.glDepthMask(gl.GL_TRUE)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
            self.camera.use()               # viewport + scissor for this view, now on our picture
            self._post_active = True
        except Exception as e:              # noqa: BLE001 - never let a graphics extra stop the game
            self._post_fail(e)

    def post_glow(self):
        """Just before the glowing things are drawn: remember the picture so we know what they added."""
        if not self._post_active or self._post_marked:
            return                          # (view3d calls this twice; the first call per view counts)
        try:
            x, y, w, h = self._post_rect_px
            t = self._post_view_targets(w, h)
            self._post_blit(t["base"][0])
            self._post_marked = True
        except Exception as e:              # noqa: BLE001
            self._post_fail(e)

    def post_end(self, dk):
        """After the glows: blur what glows, add it back, grade the colour, and put it on the screen."""
        if not self._post_active:
            return
        self._post_active = False
        ctx = self.ctx
        try:
            x, y, w, h = self._post_rect_px
            t = self._post_view_targets(w, h)
            self._post_blit(t["final"][0])
            self._post_prev.use()
            blend = ctx.is_enabled(ctx.BLEND)
            depth = ctx.is_enabled(ctx.DEPTH_TEST)
            ctx.disable(ctx.BLEND, ctx.DEPTH_TEST)
            p = self._post_progs
            ex = p["extract"]
            ex["has_base"] = int(self._post_marked)
            ex["glow_k"] = GLOW_DAY + (GLOW_NIGHT - GLOW_DAY) * dk
            ex["glow_lo"], ex["glow_hi"] = GLOW_SOFT
            ex["knee"] = BRIGHT_KNEE
            ex["bright_k"] = BRIGHT_DAY + (BRIGHT_NIGHT - BRIGHT_DAY) * dk
            self._post_pass(ex, t["half"], t["final"][1], t["base"][1])
            down, blur = p["down"], p["blur"]
            for src, a, b in (("half", "q_a", "q_b"), ("q_a", "e_a", "e_b")):
                stex = t[src][1]
                down["texel"] = (1.0 / stex.width, 1.0 / stex.height)
                self._post_pass(down, t[a], stex)
                at = t[a][1]
                blur["step"] = (1.0 / at.width, 0.0)
                self._post_pass(blur, t[b], at)
                blur["step"] = (0.0, 1.0 / at.height)
                self._post_pass(blur, t[a], t[b][1])
            comp = p["comp"]
            comp["near_k"] = NEAR_K
            comp["wide_k"] = WIDE_K
            comp["grade"] = max(0.0, min(1.0, dk))
            self.gui.use()                  # this view's viewport + scissor on the screen
            for i, tex in enumerate((t["final"][1], t["q_a"][1], t["e_a"][1])):
                tex.use(i)
            self._post_quad.render(comp)
            if blend:
                ctx.enable(ctx.BLEND)
            if depth:
                ctx.enable(ctx.DEPTH_TEST)
        except Exception as e:              # noqa: BLE001
            self._post_fail(e)
