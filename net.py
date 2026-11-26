"""
net.py - LAN co-op networking for Last Light.

The host runs the real game (zombies, crafting, inventories). Each joining player
sends their inputs and position; the host sends back a snapshot of the world ~20x a second.
Messages are one JSON object per line over TCP. Games announce themselves on the
local network with a small UDP broadcast so the Join screen can find them.
"""
import json
import math
import queue
import socket
import threading
import time

PORT = 50555            # TCP game port
DISCOVERY_PORT = 50556  # UDP "a game is running here" broadcasts
MAX_PLAYERS = 4


def lan_ip():
    """Best guess at this computer's address on the local network."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def num(v, default=0.0, lo=None, hi=None):
    """A number from someone else's message: a finite float clamped to [lo, hi], or default if it isn't one.
    (A modified client can send NaN, Infinity, 1e999, strings, lists... none of that may crash the host.)"""
    if isinstance(v, str):
        return default
    try:
        v = float(v)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(v):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def whole(v, default=0, lo=None, hi=None):
    """Like num() but a whole number (rounded down)."""
    v = num(v, None, lo, hi)
    return default if v is None else int(v)


def _no_constant(name):
    return None          # NaN / Infinity / -Infinity aren't real JSON: treat them as missing


def _finite(text):
    v = float(text)
    return v if math.isfinite(v) else None     # 1e999 parses as Infinity: treat it as missing too


def decode(line):
    """One message line -> dict, or None if it isn't a JSON object (garbage lines are skipped, not fatal)."""
    try:
        obj = json.loads(line, parse_constant=_no_constant, parse_float=_finite)
    except (ValueError, RecursionError):
        return None
    return obj if isinstance(obj, dict) else None


def encode(obj):
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode()


class Conn:
    """One TCP connection with background reader/writer threads."""

    def __init__(self, sock):
        self.sock = sock
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.inbox = queue.Queue()
        self.outbox = queue.Queue()
        self.alive = True
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._writer, daemon=True).start()

    def _reader(self):
        buf = b""
        try:
            while self.alive:
                data = self.sock.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = decode(line) if line else None
                    if msg is not None:
                        self.inbox.put(msg)
        except (OSError, ValueError):
            pass
        self.close()

    def _writer(self):
        try:
            while self.alive:
                msg = self.outbox.get()
                if msg is None:
                    break
                self.sock.sendall(msg)
        except OSError:
            pass
        self.close()

    def send(self, obj, droppable=False):
        """Queue a message. droppable=True skips it if the connection is backed up (snapshots)."""
        if not self.alive:
            return
        if droppable and self.outbox.qsize() > 8:
            return
        self.outbox.put(obj if isinstance(obj, bytes) else encode(obj))

    def receive(self):
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        if self.alive:
            self.alive = False
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
            self.outbox.put(None)


class Server:
    """Accepts players and announces the game on the LAN."""

    def __init__(self, host_name, port=PORT):
        self.port = port
        self.host_name = host_name
        self.players = 1
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.sock.listen()
        self.pending = queue.Queue()
        self.running = True
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._announce, daemon=True).start()

    def _accept(self):
        while self.running:
            try:
                c, addr = self.sock.accept()
            except OSError:
                break
            self.pending.put(Conn(c))

    def _announce(self):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            msg = encode({"lastlight": 1, "name": self.host_name, "port": self.port, "players": self.players})
            for target in ("<broadcast>", "127.0.0.1"):
                try:
                    u.sendto(msg, (target, DISCOVERY_PORT))
                except OSError:
                    pass
            time.sleep(1.0)
        u.close()

    def new_connections(self):
        out = []
        while True:
            try:
                out.append(self.pending.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass


class Finder:
    """Listens for game announcements. .games -> {(ip, port): (name, players, last_seen)}"""

    def __init__(self):
        self.games = {}
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.settimeout(0.5)
        try:
            self.sock.bind(("", DISCOVERY_PORT))
            threading.Thread(target=self._listen, daemon=True).start()
        except OSError:
            self.running = False

    def _listen(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                info = json.loads(data)
            except socket.timeout:
                continue
            except (OSError, ValueError):
                if not self.running:
                    break
                continue
            if isinstance(info, dict) and info.get("lastlight"):
                ip = addr[0]
                if ip.startswith("127.") and any(not k[0].startswith("127.") for k in self.games):
                    continue
                self.games[(ip, int(info.get("port", PORT)))] = (str(info.get("name", "?"))[:16],
                                                                 int(info.get("players", 1)), time.time())

    def list(self):
        now = time.time()
        found = [(k, v) for k, v in self.games.items() if now - v[2] < 3.5]
        # the same machine can show up as both 127.0.0.1 and its LAN ip; keep one
        names = {}
        for k, v in sorted(found, key=lambda kv: kv[0][0].startswith("127.")):
            names.setdefault((v[0], k[1]), (k, v))
        return list(names.values())

    def close(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass


class Joiner:
    """Connects in the background so the window doesn't freeze. Check .conn / .error."""

    def __init__(self, ip, port=PORT):
        self.conn, self.error, self.done = None, None, False
        threading.Thread(target=self._go, args=(ip, port), daemon=True).start()

    def _go(self, ip, port):
        try:
            s = socket.create_connection((ip, port), timeout=5)
            s.settimeout(None)
            self.conn = Conn(s)
        except OSError as e:
            self.error = str(e) or "could not connect"
        self.done = True
