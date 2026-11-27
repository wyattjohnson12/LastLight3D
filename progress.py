"""
progress.py - run stats, achievements and the run summary. Mixed into the game window.

Per-run stats: every survivor keeps a little tally (p.stats) of nights survived, zombies and bosses killed,
items crafted, structures built, animals tamed, times downed and resources gathered. The host (or the solo
player) does the counting, and the tally is saved in the save file with the rest of the survivor.

Achievements are unlocked across all your games and kept in achievements.json (one per computer).
In online co-op the host sends each player their own tally (a "stats" event), and each computer decides
its own unlocks - so a friend's achievements end up on the friend's computer. In split screen everybody
on the couch shares this computer's achievements.

Screens: an Achievements screen on the title menu, a stats panel on the pause screen, and a run summary
when you leave a game to the title screen (there's no game over - the night just passes when everyone is down).
"""
import json
import os
import time

import arcade

import explore
import ui

HERE = os.path.dirname(os.path.abspath(__file__))
ACH_FILE = os.path.join(HERE, "achievements.json")
TOAST_T = 4.5

# (key, column title) - what the stats panel and the run summary show
STAT_COLS = [("nights", "Nights"), ("zombies", "Zombies"), ("bosses", "Bosses"), ("crafted", "Crafted"),
             ("built", "Built"), ("tamed", "Tamed"), ("downed", "Downed"), ("gathered", "Gathered")]
STAT_KEYS = [k for k, _ in STAT_COLS] + ["walls", "pets_max"]
MAX_KEYS = {"pets_max"}           # "most at once" stats: lifetime keeps the best, not the sum


def _g(d, k):
    return int(d.get(k, 0) or 0)


# (id, name, how to get it, test(run_stats, lifetime_stats))
ACHIEVEMENTS = [
    ("first_night", "First Night", "Survive your first night.", lambda r, l: _g(r, "nights") >= 1),
    ("week", "One Week Later", "Survive 7 nights in one game.", lambda r, l: _g(r, "nights") >= 7),
    ("ten_nights", "Hardened", "Survive 10 nights in one game.", lambda r, l: _g(r, "nights") >= 10),
    ("twenty_nights", "Last Light Standing", "Survive 20 nights in one game.", lambda r, l: _g(r, "nights") >= 20),
    ("untouchable", "Untouchable", "Survive 5 nights in one game without going down.",
     lambda r, l: _g(r, "nights") >= 5 and _g(r, "downed") == 0),
    ("first_blood", "First Blood", "Kill a zombie.", lambda r, l: _g(r, "zombies") >= 1),
    ("hunter", "Zombie Hunter", "Kill 100 zombies in one game.", lambda r, l: _g(r, "zombies") >= 100),
    ("exterminator", "Exterminator", "Kill 500 zombies across all your games.", lambda r, l: _g(l, "zombies") >= 500),
    ("boss_slayer", "Boss Slayer", "Help bring down a boss.", lambda r, l: _g(r, "bosses") >= 1),
    ("giant_killer", "Giant Killer", "Help bring down 3 bosses in one game.", lambda r, l: _g(r, "bosses") >= 3),
    ("handy", "Handy", "Craft your first item.", lambda r, l: _g(r, "crafted") >= 1),
    ("master_crafter", "Master Crafter", "Craft 50 things in one game.", lambda r, l: _g(r, "crafted") >= 50),
    ("foundations", "Foundations", "Build your first structure.", lambda r, l: _g(r, "built") >= 1),
    ("fortress", "Fortress", "Build 30 walls in one game.", lambda r, l: _g(r, "walls") >= 30),
    ("best_friend", "Best Friend", "Tame an animal.", lambda r, l: _g(r, "tamed") >= 1),
    ("zookeeper", "Zookeeper", "Have 3 pets at once.", lambda r, l: _g(r, "pets_max") >= 3),
    ("hoarder", "Hoarder", "Gather 500 resources in one game.", lambda r, l: _g(r, "gathered") >= 500),
    ("industrious", "Industrious", "Gather 5000 resources across all your games.",
     lambda r, l: _g(l, "gathered") >= 5000),
    ("back_again", "Not Today", "Go down - and get back up.", lambda r, l: _g(r, "downed") >= 1),
]
ACH_BY_ID = {a[0]: a for a in ACHIEVEMENTS}


def check_unlocks(run, life, have):
    """Pure logic: the ids of achievements this tally newly earns (not already in `have`)."""
    return [aid for aid, _, _, test in ACHIEVEMENTS if aid not in have and test(run, life)]


def load_progress(path=None):
    try:
        with open(path or ACH_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError):
        data = {}
    data.setdefault("unlocked", {})
    data.setdefault("life", {})
    data.setdefault("runs", 0)
    data.setdefault("best_nights", 0)
    return data


def save_progress(data, path=None):
    path = path or ACH_FILE
    try:
        with open(path + ".tmp", "w") as f:
            json.dump(data, f, indent=1)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


class Progress:
    _prog = None             # achievements.json contents (loaded on first use)
    _prog_dirty = False
    _prog_saved_t = 0.0
    client_stats = None      # co-op joiner: my own tally, as last sent by the host
    run_unlocks = None       # names unlocked during this game (for the summary)
    ach_toasts = None        # [[name, desc, shown_at or None, pid or None], ...]
    last_run = None          # the run summary shown after leaving a game

    # ------------------------------------------------------------------ the file
    @property
    def prog(self):
        if self._prog is None:
            self._prog = load_progress()
        return self._prog

    def prog_flush(self, force=False):
        if self._prog_dirty and (force or time.time() - self._prog_saved_t > 10):
            save_progress(self.prog)
            self._prog_dirty = False
            self._prog_saved_t = time.time()

    def on_close(self):
        self.prog_flush(True)
        super().on_close()

    # ------------------------------------------------------------------ counting (host / solo)
    def stats_of(self, p):
        st = getattr(p, "stats", None)
        if st is None:
            st = p.stats = {}
        return st

    def stat(self, p, key, n=1):
        """Add n to one of a survivor's run stats. Hook calls: self.stat(p, "zombies")."""
        if p is None or not n or self.net == "client":
            return
        st = self.stats_of(p)
        st[key] = _g(st, key) + int(n)
        self._stat_changed(p, key, int(n))

    def stat_max(self, p, key, value):
        if p is None or self.net == "client":
            return
        st = self.stats_of(p)
        if int(value) > _g(st, key):
            st[key] = int(value)
            self._stat_changed(p, key, 0)

    def _stat_changed(self, p, key, n):
        st = self.stats_of(p)
        # local player (solo / host / split screen) -> count it here; remote joiner -> send it to them
        if self._emit(["stats", dict(st), key, n], p):
            self._count_local(p.id, st, key, n)

    # hooks with a little logic of their own
    def on_new_day(self):
        for p in list(self.players.values()):
            self.stat(p, "nights")

    def on_built(self, p, item):
        self.stat(p, "built")
        if item.endswith("_wall"):
            self.stat(p, "walls")

    def on_tamed(self, p):
        self.stat(p, "tamed")
        self.stat_max(p, "pets_max", sum(1 for a in self.over.animals if a.owner == p.id))

    def on_boss_killed(self, b, by=None):
        for p in self.players.values():       # a boss is a team effort: everyone alive up top gets it
            if (p.alive and p.layer == getattr(b, "layer", "over")) or p is by:
                self.stat(p, "bosses")

    # ------------------------------------------------------------------ this computer's achievements
    def progress_event(self, ev):
        """A co-op joiner got their tally from the host: ["stats", tally, key, added]."""
        st = ev[1] if isinstance(ev[1], dict) else {}
        self.client_stats = st
        me = self.me
        self._count_local(me.id if me else None, st, ev[2], int(ev[3] or 0))

    def _count_local(self, pid, run, key, n):
        prog = self.prog
        life = prog["life"]
        if key in MAX_KEYS:
            life[key] = max(_g(life, key), _g(run, key))
        elif n > 0:
            life[key] = _g(life, key) + n
        if key == "nights":
            prog["best_nights"] = max(prog.get("best_nights", 0), _g(run, "nights"))
        self._prog_dirty = True
        for aid in check_unlocks(run, life, prog["unlocked"]):
            self.unlock(aid, pid)
        self.prog_flush()

    def unlock(self, aid, pid=None):
        prog = self.prog
        if aid in prog["unlocked"] or aid not in ACH_BY_ID:
            return
        prog["unlocked"][aid] = int(time.time())
        self._prog_dirty = True
        self.prog_flush(True)
        _, name, desc, _ = ACH_BY_ID[aid]
        if self.run_unlocks is None:
            self.run_unlocks = []
        self.run_unlocks.append(name)
        if self.ach_toasts is None:
            self.ach_toasts = []
        self.ach_toasts.append([name, desc, None, pid if self.local else None])
        self._play("win", 0.45)

    # ------------------------------------------------------------------ toast
    def on_draw(self):
        super().on_draw()
        if self.ach_toasts and self.state == "playing":
            self.draw_ach_toast()

    def draw_ach_toast(self):
        """One toast at a time, for whoever's view this is; each shows for TOAST_T seconds."""
        now = self.flame_t
        me = self.me
        t = None
        for row in list(self.ach_toasts):
            if row[3] is not None and not (me and me.id == row[3]):
                continue
            if row[2] is None:
                row[2] = now
            if now - row[2] > TOAST_T:
                self.ach_toasts.remove(row)
                continue
            t = row
            break
        if t is None:
            return
        name, desc, t0, _ = t
        age = now - t0
        k = max(0.0, min(1.0, age / 0.3, (TOAST_T - age) / 0.5))
        W, H = ui.W, ui.H
        w = min(420, W - 40)
        l, b = W / 2 - w / 2, H - 150 + 40 * (1 - k)
        a = int(235 * k)
        arcade.draw_lrbt_rectangle_filled(l, l + w, b, b + 56, (20, 22, 30, a))
        arcade.draw_lrbt_rectangle_outline(l, l + w, b, b + 56, (255, 214, 140, a), 2)
        arcade.draw_circle_filled(l + 30, b + 28, 16, (255, 200, 90, a))
        self.txt("ach_star", "★", l + 30, b + 28, (60, 40, 10, a), 18, anchor_x="center", anchor_y="center",
                 bold=True)
        self.txt("ach_t1", "ACHIEVEMENT UNLOCKED", l + 56, b + 36, (255, 214, 140, a), 10, bold=True)
        self.txt("ach_t2", f"{name}  -  {desc}", l + 56, b + 14, (255, 255, 255, a), 12, bold=True)

    # ------------------------------------------------------------------ tallies for the screens
    def stats_rows(self):
        if self.net == "client":
            return [(self.me.name if self.me else "You", self.client_stats or {})]
        ps = sorted(self.players.values(), key=lambda p: p.id)
        return [(p.name, dict(self.stats_of(p))) for p in ps]

    def run_summary(self):
        """Called at the top of leave_game(), while the world is still there."""
        if self.state != "playing" or not self.me:
            return None
        return {"day": self.day, "time": self.time_alive, "kills": self.kills, "rows": self.stats_rows(),
                "unlocked": list(self.run_unlocks or []), "client": self.net == "client"}

    def show_summary(self, summary):
        """Called at the end of leave_game(): show the run summary instead of the main menu."""
        self.client_stats = None
        self.run_unlocks = None
        self.ach_toasts = None
        if not summary:
            return
        prog = self.prog
        prog["runs"] = prog.get("runs", 0) + 1
        self._prog_dirty = True
        self.prog_flush(True)
        self.last_run = summary
        self.menu, self.menu_sel = "summary", 0

    # ------------------------------------------------------------------ title menu screens
    def menu_items(self):
        if self.menu == "ach":
            return ["Back"]
        if self.menu == "summary":
            return ["Continue"]
        items = super().menu_items()
        if self.menu == "main" and items and items[-1] == "Quit":
            items = items[:-1] + ["Achievements", "Quit"]
        return items

    def menu_rows(self):
        if self.menu in ("ach", "summary"):
            label = self.menu_items()[0]
            return [(label, (ui.W / 2 - 120, ui.W / 2 + 120, 28, 64))]
        rows = super().menu_rows()
        extra = len(rows) - 8
        if self.menu == "main" and extra > 0:          # lift a long main menu clear of the notes at the bottom
            rows = [(it, (l, r, b + 24 * extra, t + 24 * extra)) for it, (l, r, b, t) in rows]
        return rows

    def menu_pick(self, i, x=None):
        items = self.menu_items()
        if self.menu in ("ach", "summary"):
            self.menu_back()
            return
        if self.menu == "main" and 0 <= i < len(items) and items[i] == "Achievements":
            self.menu, self.menu_sel, self.menu_note = "ach", 0, ""
            return
        super().menu_pick(i, x)

    def menu_back(self):
        if self.menu in ("ach", "summary"):
            was = self.menu
            self.menu = "main"
            items = self.menu_items()
            self.menu_sel = items.index("Achievements") if was == "ach" and "Achievements" in items else 0
            return
        super().menu_back()

    def draw_title(self):
        if self.menu == "ach":
            self.draw_achievements()
        elif self.menu == "summary":
            self.draw_summary()
        else:
            super().draw_title()

    def _back_button(self):
        for i, (label, (l, r, b, t)) in enumerate(self.menu_rows()):
            arcade.draw_lrbt_rectangle_filled(l, r, b, t, (255, 214, 140, 60))
            arcade.draw_lrbt_rectangle_outline(l, r, b, t, (255, 214, 140), 2)
            self.txt(f"prog_back{i}", label, (l + r) / 2, b + 12, (255, 255, 255), 15, anchor_x="center", bold=True)
        hint = "A / B" if self.pad.connected else "ENTER / ESC"
        self.txt("prog_hint", hint, ui.W / 2, 12, (150, 150, 150), 10, anchor_x="center")

    def draw_achievements(self):
        W, H = ui.W, ui.H
        prog = self.prog
        have = prog["unlocked"]
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 170))
        self.txt("ach_h", "ACHIEVEMENTS", W / 2, H - 56, (255, 214, 140), 30, anchor_x="center", bold=True)
        life = prog["life"]
        self.txt("ach_h2", f"{len([a for a in ACHIEVEMENTS if a[0] in have])} of {len(ACHIEVEMENTS)} unlocked"
                 f"      Games played: {prog.get('runs', 0)}      Best: {prog.get('best_nights', 0)} nights      "
                 f"All-time zombies: {_g(life, 'zombies')}      Resources: {_g(life, 'gathered')}",
                 W / 2, H - 86, (210, 210, 210), 12, anchor_x="center")
        rows = (len(ACHIEVEMENTS) + 1) // 2
        cw, rh = min(500, W / 2 - 30), min(54, (H - 200) / rows)
        for i, (aid, name, desc, _) in enumerate(ACHIEVEMENTS):
            col, row = i // rows, i % rows
            l = W / 2 - cw - 10 if col == 0 else W / 2 + 10
            top = H - 108 - row * rh
            got = aid in have
            arcade.draw_lrbt_rectangle_filled(l, l + cw, top - rh + 6, top, (40, 36, 22, 230) if got else (22, 24, 28, 220))
            arcade.draw_lrbt_rectangle_outline(l, l + cw, top - rh + 6, top,
                                               (255, 214, 140, 200) if got else (255, 255, 255, 40), 1)
            cy = top - (rh - 6) / 2
            arcade.draw_circle_filled(l + 22, cy, 12, (255, 200, 90) if got else (60, 62, 70))
            self.txt(f"ach_i{i}", "★" if got else "?", l + 22, cy, (60, 40, 10) if got else (150, 150, 160), 13,
                     anchor_x="center", anchor_y="center", bold=True)
            self.txt(f"ach_n{i}", name, l + 44, cy + 3, (255, 235, 190) if got else (170, 170, 175), 13, bold=True)
            self.txt(f"ach_d{i}", desc, l + 44, cy - 13, (220, 220, 220) if got else (130, 130, 140), 10)
        self._back_button()

    def _stats_table(self, rows, l, top, w, key, size=11, rh=20):
        """Players down the side, stats across the top."""
        name_w = 130
        cw = (w - name_w) / len(STAT_COLS)
        for j, (_, title) in enumerate(STAT_COLS):
            self.txt(f"{key}h{j}", title, l + name_w + cw * j + cw / 2, top, (255, 230, 170), size, anchor_x="center",
                     bold=True)
        for i, (name, st) in enumerate(rows[:4]):
            y = top - rh * (i + 1)
            self.txt(f"{key}n{i}", name, l, y, (255, 255, 255), size, bold=True)
            for j, (k, _) in enumerate(STAT_COLS):
                self.txt(f"{key}v{i}_{j}", str(_g(st, k)), l + name_w + cw * j + cw / 2, y, (225, 225, 225), size,
                         anchor_x="center")

    def draw_summary(self):
        W, H = ui.W, ui.H
        s = self.last_run or {}
        arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, 170))
        self.txt("sum_h", "RUN SUMMARY", W / 2, H - 70, (255, 214, 140), 30, anchor_x="center", bold=True)
        mins, secs = divmod(int(s.get("time", 0)), 60)
        line = f"You made it to Day {s.get('day', 1)}." if s.get("client") else \
            f"You made it to Day {s.get('day', 1)}  -  {mins}m {secs:02d}s in the world  -  {s.get('kills', 0)} kills in all."
        self.txt("sum_l", line, W / 2, H - 108, (230, 230, 230), 15, anchor_x="center")
        rows = s.get("rows", [])
        tw = min(900, W - 60)
        top = H - 170
        self.panel(W / 2 - tw / 2 - 16, W / 2 + tw / 2 + 16, top - 24 * min(4, len(rows)) - 18, top + 28, 200)
        self._stats_table(rows, W / 2 - tw / 2, top, tw, "sum", 13, 24)
        un = s.get("unlocked", [])
        y = top - 24 * min(4, len(rows)) - 60
        if un:
            self.txt("sum_u", f"Achievements unlocked this game ({len(un)}):", W / 2, y, (255, 214, 140), 14,
                     anchor_x="center", bold=True)
            for i in range(0, min(len(un), 12), 3):
                self.txt(f"sum_u{i}", "     ".join("★ " + n for n in un[i:i + 3]), W / 2, y - 26 - i / 3 * 22,
                         (255, 240, 210), 13, anchor_x="center")
        else:
            prog = self.prog
            n = len([a for a in ACHIEVEMENTS if a[0] in prog["unlocked"]])
            self.txt("sum_u", f"No new achievements this time ({n} of {len(ACHIEVEMENTS)} unlocked).", W / 2, y,
                     (200, 200, 200), 13, anchor_x="center")
        if self.menu_note:
            self.txt("sum_note", self.menu_note, W / 2, 92, (255, 200, 150), 13, anchor_x="center")
        self._back_button()

    # ------------------------------------------------------------------ pause screen
    def draw_help(self, overlay):
        super().draw_help(overlay)
        if not overlay or not self.me:
            return
        W = ui.W
        rows = self.stats_rows()
        n = min(4, len(rows))
        tw = min(960, W - 60)
        top = 166
        self.panel(W / 2 - tw / 2 - 12, W / 2 + tw / 2 + 12, top - 20 * n - 12, top + 34, 170)
        prog = self.prog
        got = len([a for a in ACHIEVEMENTS if a[0] in prog["unlocked"]])
        found = explore.progress_text(self)        # explore.py: places found, recipes found
        self.txt("ps_h", f"THIS GAME  -  Day {self.day}" + (f"     {found}" if found else ""), W / 2 - tw / 2, top + 16,
                 (255, 214, 140), 11, bold=True)
        self.txt("ps_a", f"Achievements {got}/{len(ACHIEVEMENTS)}  (see them on the title screen)", W / 2 + tw / 2,
                 top + 16, (200, 200, 200), 10, anchor_x="right")
        self._stats_table(rows, W / 2 - tw / 2, top - 2, tw, "ps", 11, 20)
