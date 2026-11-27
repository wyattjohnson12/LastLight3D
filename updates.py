"""
updates.py - which version of Last Light this is, and whether a newer one is out.

version.json (next to this file) says which version you have. The newest version.json on GitHub says which
version is out. Both the game's title screen and the launcher (play.py) use this; it only needs the Python
standard library, so the launcher can use it before the game's packages are installed.

Checking never gets in the way: it runs in the background, gives up after a few seconds, and offline it
simply says nothing.
"""
import json
import os
import ssl
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "wyattjohnson12/LastLight3D"
BRANCH = os.environ.get("LASTLIGHT_BRANCH", "main")   # (testers can point the updater at another branch)
LATEST_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/version.json"
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
WEBSITE = "https://wyattjohnson12.github.io/LastLight3D/"


def local_info():
    """This copy's version.json (or a stand-in if it's missing)."""
    try:
        with open(os.path.join(HERE, "version.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"version": "0.0.0", "notes": []}


def local_version():
    return local_info().get("version", "0.0.0")


def parse(v):
    """'2.10.1' -> (2, 10, 1), so versions compare like numbers, not like words."""
    out = []
    for part in str(v).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (3 - len(out)))


def newer(a, b):
    """Is version a newer than version b?"""
    return parse(a) > parse(b)


def _contexts():
    """SSL setups to try. Python from python.org on a Mac often has no certificates until you run its
    "Install Certificates" script - but pip always carries its own, so fall back to those."""
    yield None
    try:
        from pip._vendor import certifi
        yield ssl.create_default_context(cafile=certifi.where())
    except Exception:       # noqa: BLE001 - no pip: nothing else to try
        return


def download(url, timeout=4.0):
    """The bytes at url (raises if it can't be fetched)."""
    err = None
    for ctx in _contexts():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LastLight-updater", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read()
        except Exception as e:      # noqa: BLE001 - try the next SSL setup
            err = e
    raise err


def fetch_latest(timeout=4.0):
    """The newest version.json on GitHub, or None (offline, GitHub down, ...)."""
    try:
        return json.loads(download(LATEST_URL, timeout).decode("utf-8"))
    except Exception:       # noqa: BLE001 - any failure just means "don't know"
        return None


class Checker:
    """Looks for a new version in the background. .latest is None until (and unless) it finds one."""

    def __init__(self):
        self.mine = local_version()
        self.latest = None          # the newer version.json, once found
        self.done = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        info = fetch_latest()
        if info and newer(info.get("version", "0"), self.mine):
            self.latest = info
        self.done = True
