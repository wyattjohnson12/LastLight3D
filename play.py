"""
play.py - the one thing to start Last Light with. The "Play Last Light" files just run this.

Every time it:
  1. checks your Python is new enough (and tells you where to get a new one if not),
  2. looks for a new version of the game and offers to update - no git needed:
       * a git copy (you used `git clone`): it runs `git pull`,
       * a downloaded copy (the .zip from the website): it downloads the newest .zip and copies the new
         files over this folder. Your saves, settings and achievements are never touched,
  3. installs the game's packages (arcade, pygame) the first time, or when an update needs new ones,
  4. starts the game.

    python3 play.py              (Windows: py play.py)
    python3 play.py --update     update only, don't start the game
    python3 play.py --no-update  start without checking for updates

Only uses the Python standard library, so it works before anything is installed.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MIN_PY = (3, 10)
KEEP = {"saves", "lastlight_config.json", "achievements.json", ".git", ".venv"}   # yours - never overwritten
VENV = os.path.join(HERE, ".venv")


def say(msg=""):
    print(msg, flush=True)


def ask(question):
    """Yes/no (ENTER = yes). If there's no keyboard (no terminal), assume yes."""
    if not sys.stdin or not sys.stdin.isatty():
        return True
    try:
        return input(f"{question} [Y/n] ").strip().lower() not in ("n", "no")
    except EOFError:
        return True


def pause_and_exit(code=1):
    """Keep the window open so the message can be read (double-clicked windows close right away)."""
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\nPress ENTER to close this window.")
        except EOFError:
            pass
    sys.exit(code)


def open_page(url):
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:       # noqa: BLE001
        pass


# ----------------------------------------------------------------- 1. Python
def check_python():
    if sys.version_info >= MIN_PY:
        return
    have = ".".join(map(str, sys.version_info[:3]))
    say(f"Last Light needs Python {MIN_PY[0]}.{MIN_PY[1]} or newer - this computer has {have}.")
    say("Opening the Python download page. Install it, then start Last Light again.")
    open_page("https://www.python.org/downloads/")
    pause_and_exit()


# ----------------------------------------------------------------- 2. updates
def update_with_git():
    say("Updating with git pull...")
    r = subprocess.call(["git", "pull", "--ff-only"], cwd=HERE)
    if r != 0:
        say("git pull didn't work (changed files, or another branch?). Starting the version you have.")
    return r == 0


def update_from_zip(updates):
    """Download the newest version and copy it over this folder (keeping KEEP)."""
    say("Downloading the new version...")
    data = updates.download(updates.ZIP_URL, timeout=120)
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        roots = [os.path.join(tmp, d) for d in os.listdir(tmp)]
        src = next((d for d in roots if os.path.exists(os.path.join(d, "main.py"))), None)
        if src is None:
            raise RuntimeError("the download doesn't look like Last Light")
        for name in os.listdir(src):
            if name in KEEP:
                continue
            a, b = os.path.join(src, name), os.path.join(HERE, name)
            if os.path.isdir(a):
                shutil.copytree(a, b, dirs_exist_ok=True)
            else:
                shutil.copy2(a, b)
    for name in os.listdir(HERE):       # zip files forget that the Mac launcher must be runnable
        if name.endswith(".command"):
            os.chmod(os.path.join(HERE, name), 0o755)
    return True


def check_updates(force=False):
    import updates
    mine = updates.local_version()
    say(f"Last Light {mine} - checking for a new version...")
    latest = updates.fetch_latest(timeout=6)
    if latest is None:
        say("Couldn't check (offline?). Starting the version you have.")
        return False
    if not updates.newer(latest.get("version", "0"), mine):
        say("You have the newest version.")
        return False
    say(f"\n  NEW VERSION {latest['version']}" + (f" - {latest['name']}" if latest.get("name") else ""))
    for n in latest.get("notes", [])[:8]:
        say(f"   * {n}")
    say("")
    if not force and not ask("Update now? (your saves are kept)"):
        return False
    git = os.path.isdir(os.path.join(HERE, ".git")) and shutil.which("git")
    try:
        ok = update_with_git() if git else update_from_zip(updates)
    except Exception as e:      # noqa: BLE001
        say(f"The update didn't work ({e}). Starting the version you have.")
        return False
    if ok:
        say(f"Updated to {latest['version']}!")
    return ok


# ----------------------------------------------------------------- 3. packages
def requirements():
    with open(os.path.join(HERE, "requirements.txt"), encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def missing(python):
    """Requirements the given Python doesn't have (in the right version)."""
    code = ("import sys, importlib.metadata as m\n"
            "bad = []\n"
            "for r in sys.argv[1:]:\n"
            "    name, _, want = r.partition('==')\n"
            "    name = name.split('>=')[0].strip()\n"
            "    try:\n"
            "        have = m.version(name)\n"
            "        if want and have != want.strip(): bad.append(r)\n"
            "    except m.PackageNotFoundError: bad.append(r)\n"
            "print('\\n'.join(bad))\n")
    out = subprocess.run([python, "-c", code] + requirements(), capture_output=True, text=True)
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def venv_python():
    return os.path.join(VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV, "bin", "python")


def ensure_packages():
    """The Python to run the game with, with arcade & pygame installed."""
    if os.path.exists(venv_python()):              # we had to make our own earlier: keep using it
        py = venv_python()
    else:
        py = sys.executable
    need = missing(py)
    if not need:
        return py
    say("Installing what the game needs (only the first time, about a minute)...")
    pip = [py, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"]
    if subprocess.call(pip, cwd=HERE) == 0 and not missing(py):
        return py
    if py == sys.executable and subprocess.call(pip + ["--user"], cwd=HERE) == 0 and not missing(py):
        return py
    if py == sys.executable:                       # this Python won't take packages: use a private copy
        say("Setting up a private Python for the game in this folder...")
        if subprocess.call([sys.executable, "-m", "venv", VENV]) == 0:
            vp = venv_python()
            if subprocess.call([vp, "-m", "pip", "install", "--disable-pip-version-check", "-r",
                                "requirements.txt"], cwd=HERE) == 0 and not missing(vp):
                return vp
    say("\nCouldn't install the game's packages. Check your internet connection and try again.")
    say("Still stuck? See 'Help' on the website: " + __import__("updates").WEBSITE)
    pause_and_exit()


# ----------------------------------------------------------------- 4. play
def main():
    args = sys.argv[1:]
    check_python()
    if "--no-update" not in args:
        if check_updates(force="--update" in args) and "--update" not in args:
            # the new files are in place: start again with the new play.py (it may do more)
            sys.exit(subprocess.call([sys.executable, os.path.join(HERE, "play.py"), "--no-update"]))
    if "--update" in args:
        say("Done.")
        return
    py = ensure_packages()
    say("Starting Last Light...")
    code = subprocess.call([py, os.path.join(HERE, "main.py")], cwd=HERE)
    if code != 0:
        say(f"\nThe game stopped with an error (code {code}). The message above says what went wrong.")
        pause_and_exit(code)


if __name__ == "__main__":
    main()
