"""
tools/coop_test.py - a two-process online co-op smoke test on localhost.

    python3 tools/coop_test.py

Process 1 (this script) plays two raw network clients, both named "Sam", speaking the real wire protocol.
Process 2 (`coop_test.py --host`) runs the real game as the host in a hidden window and pumps on_update
by hand; this script drives it through stdin with small snippets and reads JSON results back.

Checks: join, two players with the same name keep separate save records, a rejoin of a resumed save puts
each Sam back where (and on which layer) they were saved with their own backpack, malformed withdraw /
input messages (Infinity, NaN, 1e999, strings, lists, non-objects) don't crash the host, a fleeing boss
takes arrow damage, and closing the window mid-cutscene still saves. Saves, config and achievements go to
a temp folder - your real ones are not touched.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PORT = 50655           # not the game's real port, so a running game doesn't get in the way


# ====================================================================== host process
def host_main(tmp):
    os.chdir(tmp)
    import main
    import net
    import progress
    import savegame
    main.CONFIG = os.path.join(tmp, "config.json")
    progress.ACH_FILE = os.path.join(tmp, "achievements.json")
    savegame.SAVE_DIR = os.path.join(tmp, "saves")
    real_server = net.Server
    net.Server = lambda name: real_server(name, port=PORT)

    game = main.LastLight()
    game.set_visible(False)
    game.my_name = "Hosty"
    cmds = []
    threading.Thread(target=lambda: [cmds.append(line) for line in sys.stdin], daemon=True).start()
    env = {"g": game, "main": main, "net": net, "savegame": savegame}

    def out(obj):
        sys.stdout.write("@@" + json.dumps(obj) + "\n")
        sys.stdout.flush()

    while True:
        try:
            game.dispatch_events()
            game.on_update(1 / 30)
        except Exception:
            out({"crash": traceback.format_exc()})
            return
        while cmds:
            code = json.loads(cmds.pop(0))
            env["result"] = None
            try:
                exec(code, env)
                out({"ok": env["result"]})
            except Exception:
                out({"err": traceback.format_exc()})
            if code.strip() == "quit":
                return
        time.sleep(1 / 60)


# ====================================================================== client side (this process)
class Host:
    def __init__(self, tmp):
        self.p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--host", tmp], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, cwd=tmp)

    def run(self, code):
        self.p.stdin.write(json.dumps(code) + "\n")
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("host process died")
            if line.startswith("@@"):
                r = json.loads(line[2:])
                if "ok" not in r:
                    raise RuntimeError(r.get("err") or r.get("crash"))
                return r["ok"]

    def kill(self):
        if self.alive():
            self.p.kill()

    def alive(self):
        return self.p.poll() is None


class Client:
    """A minimal client: says hello, follows the host's teleports, sends inputs."""

    def __init__(self, name):
        import net
        self.net = net
        self.sock = socket.create_connection(("127.0.0.1", PORT), timeout=5)
        self.sock.settimeout(None)
        self.conn = net.Conn(self.sock)
        self.conn.send({"t": "hello", "name": name})
        self.pid, self.you, self.tp, self.pos, self.wg = None, None, 0, (0, 0), None

    def pump(self):
        for m in self.conn.receive():
            if m.get("t") == "world":
                self.pid = m["pid"]
                self.wg = m.get("wg")
            elif m.get("t") == "snap" and "you" in m:
                self.you = m["you"]
                if self.you["tp"] != self.tp:
                    self.tp, self.pos = self.you["tp"], (self.you["x"], self.you["y"])
        if self.pid is not None:
            self.conn.send({"t": "in", "x": self.pos[0], "y": self.pos[1], "f": 0, "mx": 0, "my": 0, "r": 0,
                            "a": 0, "s": 0, "tp": self.tp, "ar": 0})

    def raw(self, text):
        self.sock.sendall(text.encode() + b"\n")

    def close(self):
        self.conn.close()


def wait(clients, secs, until=None):
    end = time.time() + secs
    while time.time() < end:
        for c in clients:
            c.pump()
        if until and until():
            return True
        time.sleep(0.05)
    return False


results = []
hosts = [None]


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def scenario(tmp):
    # ---------------------------------------------------------------- 1. a new hosted game, two Sams join
    h = hosts[0] = Host(tmp)
    h.run("g.start_host(None); g.end_intro(); g.intro = None; result = g.net")
    a, b = Client("Sam"), Client("Sam")
    check("both clients joined", wait([a, b], 8, lambda: a.pid is not None and b.pid is not None and a.you and b.you),
          f"pids {a.pid} {b.pid}")
    hw = h.run("result = [g.worldgen, g.world_size]")
    check("the world message carries the host's worldgen version", a.wg == hw[0] and b.wg == hw[0], f"{a.wg} {hw}")
    keys = h.run("result = sorted(g.rec_key(p) for p in g.players.values())")
    check("same-name players get unique record keys", keys == ["#first", "sam", "sam#2"], str(keys))

    # Sam A goes down the cave, Sam B stands at a storage bin on the surface; different backpacks
    h.run(f"""
pa, pb = g.players[{a.pid}], g.players[{b.pid}]
cx, cy = g.cave.size / 2, g.cave.size / 2
g.set_layer(pa, "cave", (cx + 33, cy + 21)); pa.tp += 1
g.set_layer(pb, "over", (g.centre[0] + 300, g.centre[1] - 150)); pb.tp += 1
pa.inv = {{"wood": 3}}; pb.inv = {{"stone": 7}}
g.add_structure("storage", pb.sprite.center_x + 40, pb.sprite.center_y)
g.storage = {{"berries": 50}}; g.storage_ver += 1
result = [pa.layer, pb.layer]
""")
    wait([a, b], 1.5)
    want_a = h.run(f"p = g.players[{a.pid}]; result = [p.layer, round(p.sprite.center_x, 1), round(p.sprite.center_y, 1)]")
    want_b = h.run(f"p = g.players[{b.pid}]; result = [p.layer, round(p.sprite.center_x, 1), round(p.sprite.center_y, 1)]")
    check("clients follow host teleports", a.you["ly"] == 1 and b.you["ly"] == 0, f"A {want_a}  B {want_b}")

    # ---------------------------------------------------------------- 2. malformed messages from a modded client
    bad_n = ["Infinity", "-Infinity", "NaN", "1e999", "-5", "1e30", "100000000000000000000000000000000000",
             '"abc"', "[1]", "{}", "null", "true", "2.7"]
    for n in bad_n:
        b.raw('{"t":"act","a":"withdraw","item":"berries","n":%s}' % n)
    for line in ['[1,2]', '"hello"', 'not json', '{"t":"in","x":NaN,"y":Infinity,"tp":%d,"s":1e999,"f":"x"}' % b.tp,
                 '{"t":"in","x":"abc","y":[1],"mx":Infinity,"my":-1e999,"tp":%d}' % b.tp,
                 '{"t":"act","a":"craft","i":Infinity}', '{"t":"act","a":"tame","aid":1e999}',
                 '{"t":"act","a":"assign","item":"stone","s":NaN}', '{"t":"act","a":"place","x":"a","y":1}',
                 '{"t":"act","a":"throw","x":Infinity,"y":0,"s":-1e999}', '{"t":"act","a":"petname","aid":1e999}',
                 '{"t":"act","a":"deposit","item":"stone","n":-Infinity}', '{"t":"act","a":"deposit","item":["x"]}']:
        b.raw(line)
    wait([a, b], 1.5)
    check("host survives malformed messages", h.alive() and b.conn.alive)
    st = h.run(f"p = g.players[{b.pid}]; result = [g.storage.get('berries', 0), p.inv.get('berries', 0), "
               "list(p.sprite.position), p.selected, p.move]")
    # only the finite, positive amounts count: 1e30 / 1e35 clamp to "everything", 2.7 -> 2, true -> 1
    check("absurd withdraw amounts are clamped, never crash", st[0] == 0 and st[1] == 50, str(st))
    check("position / move stay finite", all(abs(v) < 1e7 for v in st[2] + list(st[4])), str(st[2:]))
    b.raw('{"t":"act","a":"deposit","item":"berries","n":5}')
    wait([a, b], 1.0)
    st = h.run(f"result = [g.storage.get('berries', 0), g.players[{b.pid}].inv.get('berries', 0)]")
    check("a normal deposit still works", st == [5, 45], str(st))

    # ---------------------------------------------------------------- 3. leave, save, quit
    a.close(); b.close()
    wait([], 1.0)
    path = h.run("g.save_game(); result = g.save_path")
    recs = h.run("d = savegame.read_save(g.save_path); result = {k: [v['layer'], v['x'], v['y'], v['inv']] "
                 "for k, v in d['players'].items()}")
    check("save keeps both Sams", "sam" in recs and "sam#2" in recs, json.dumps(recs))
    h.run("g.on_close()")
    h.run("quit")

    # ---------------------------------------------------------------- 4. resume the save, both Sams rejoin
    h = hosts[0] = Host(tmp)
    h.run(f"g.start_host(dict(savegame.read_save({path!r}), _path={path!r})); result = g.state")
    a = Client("Sam")
    wait([a], 6, lambda: a.you is not None)
    b = Client("Sam")
    wait([a, b], 6, lambda: b.you is not None)
    wait([a, b], 1.0)
    got_a = [["over", "cave"][a.you["ly"]], a.you["x"], a.you["y"], a.you["inv"]]
    got_b = [["over", "cave"][b.you["ly"]], b.you["x"], b.you["y"], b.you["inv"]]
    check("rejoining Sam #1 is back in the cave, at the saved spot, with their backpack",
          got_a[:3] == recs["sam"][:3] and got_a[3].get("wood") == 3, f"{got_a} vs {recs['sam']}")
    check("rejoining Sam #2 is back on the surface, at the saved spot, with their backpack",
          got_b[:3] == recs["sam#2"][:3] and got_b[3].get("stone") == 7, f"{got_b} vs {recs['sam#2']}")
    host_pos = h.run("result = [g.me.layer, round(g.me.sprite.center_x, 1), round(g.me.sprite.center_y, 1)]")
    check("...and not at the host's spot", got_a[:3] != host_pos and got_b[:3] != host_pos, str(host_pos))
    c = Client("Newbie")
    wait([a, b, c], 3, lambda: c.you is not None)
    wait([a, b, c], 0.5)
    check("a brand-new friend still appears next to the host",
          c.you and c.you["ly"] == 0 and abs(c.you["x"] - host_pos[1] - 40) < 2, str(c.you and [c.you["x"], c.you["y"]]))

    # ---------------------------------------------------------------- 5. arrow vs a fleeing boss
    r = h.run("""
from world import Shot
b = g.spawn_boss(); g.end_cutscene()
b.hp = b.max_hp * 0.8
g.boss_hp = b.hp
g.start_retreat(b); g.end_cutscene()
before = b.hp
g.shots.append(Shot("arrow", b.center_x - 30, b.center_y, 600, 0, 1.0, 10.0, 0, "over"))
g._update_shots(0.05)
result = [before, b.hp, g.boss_hp, b.state]
""")
    check("an arrow hurts a fleeing boss and the wound is remembered", r[1] < r[0] and r[2] == r[1], str(r))

    # ---------------------------------------------------------------- 6. close the window mid-cutscene
    r = h.run("""
import os
for b in list(g.over.bosses): g.bmap.pop(b.bid, None); b.remove_from_sprite_lists()
g.boss_hp = None
b = g.spawn_boss("brood")   # a fresh boss (the titan went home to its lair wounded): its intro starts
t0 = os.path.getmtime(g.save_path); import time; time.sleep(0.05)
cut = bool(g.cut)
can_before = g.can_save()
g.on_close()
d = savegame.read_save(g.save_path)
result = [cut, can_before, os.path.getmtime(g.save_path) > t0, g.cut, len(d["bosses"]), d["bosses"][0][3] == b.hp]
""")
    check("closing during a boss cutscene still saves (boss included, unhurt)",
          r[0] and not r[1] and r[2] and r[3] is None and r[4] == 1 and r[5], str(r))
    for c_ in (a, b, c):
        c_.close()
    h.run("quit")


if __name__ == "__main__":
    if "--host" in sys.argv:
        host_main(sys.argv[sys.argv.index("--host") + 1])
        sys.exit(0)
    tmp = tempfile.mkdtemp(prefix="lastlight-coop-")
    try:
        scenario(tmp)
    except Exception:
        traceback.print_exc()
        results.append(("scenario finished", False))
    if hosts[0]:
        hosts[0].kill()
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed" + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)
