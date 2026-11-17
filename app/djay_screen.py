"""Reads the key djay SHOWS on each deck (newer djay versions no longer save it in the library file).

Every few seconds it asks macOS for just the title, artist and key text on djay's decks.
Read-only: it never clicks, types or changes anything in djay. It needs the Accessibility
permission for the app that runs DJ Mixes (Terminal). Every key it sees is remembered in
data/djay_screen_keys.json, so a song only has to be loaded on a deck once.
"""
import json, os, re, subprocess, sys, threading, time
from pathlib import Path

BASE = Path(__file__).parent
SCRIPT = BASE / "tools" / "djay_deck_keys.js"
STORE = Path(os.environ.get("GOODMIXX_DATA") or BASE / "data") / "djay_screen_keys.json"
EVERY = 3.0

MAJOR = ["B", "F#", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E"]
MINOR = ["Abm", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "Dbm"]
ALIAS = {"Gb": "F#", "C#": "Db", "G#": "Ab", "D#": "Eb", "A#": "Bb", "Cb": "B", "E#": "F", "B#": "C", "Fb": "E"}


def camelot(raw):
    """'9 A', '9A', 'Am', 'F#m', '2d' -> Camelot like '9A'. Unknown -> ''."""
    s = (raw or "").strip().replace("♯", "#").replace("♭", "b")
    m = re.fullmatch(r"(\d{1,2})\s*([ABab])", s)
    if m and 1 <= int(m[1]) <= 12:
        return "%d%s" % (int(m[1]), m[2].upper())
    m = re.fullmatch(r"(\d{1,2})\s*([dmDM])", s)
    if m and 1 <= int(m[1]) <= 12:
        return "%d%s" % ((int(m[1]) + 6) % 12 + 1, "A" if m[2].lower() == "m" else "B")
    m = re.fullmatch(r"([A-Ga-g])([#b]?)\s*(m|min|minor|maj|major)?", s)
    if m:
        root = m[1].upper() + m[2]
        root = ALIAS.get(root, root)
        minor = (m[3] or "").lower() in ("m", "min", "minor")
        lst = MINOR if minor else MAJOR
        name = root + ("m" if minor else "")
        if name in lst:
            return "%d%s" % (lst.index(name) + 1, "A" if minor else "B")
    return ""


class ScreenKeys:
    def __init__(self, norm):
        self.norm = norm
        self.lock = threading.Lock()
        self.status = "off"          # off / on / no-permission / djay-closed / error
        self.decks = {}              # "1" -> {"title","artist","key"}
        self.saved = {}              # norm(artist)|norm(title) -> {"title","artist","key"}
        try:
            self.saved = json.loads(STORE.read_text())
        except (OSError, ValueError):
            pass
        if sys.platform == "darwin" and SCRIPT.exists():
            self.status = "starting"
            threading.Thread(target=self._loop, daemon=True).start()

    def _id(self, title, artist):
        return self.norm(artist) + "|" + self.norm(title)

    def _read_once(self):
        try:
            r = subprocess.run(["osascript", "-l", "JavaScript", str(SCRIPT)],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return "error", {}
        out = (r.stdout or "").strip()
        if r.returncode != 0:
            err = (r.stderr or "").lower()
            if any(x in err for x in ("assistive", "not allowed", "not authorized", "-1719", "-25211", "-1743", "-10004")):
                return "no-permission", {}
            return "error", {}
        if out == "NOT_RUNNING":
            return "djay-closed", {}
        decks = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 4 and parts[1]:
                decks[parts[0]] = {"title": parts[1], "artist": parts[2], "key": camelot(parts[3])}
        return "on", decks

    def _loop(self):
        while True:
            status, decks = self._read_once()
            changed = False
            with self.lock:
                self.status, self.decks = status, decks
                for d in decks.values():
                    if d["key"]:
                        k = self._id(d["title"], d["artist"])
                        if self.saved.get(k, {}).get("key") != d["key"]:
                            self.saved[k] = dict(d)
                            changed = True
                snap = dict(self.saved) if changed else None
            if snap is not None:
                try:
                    STORE.parent.mkdir(parents=True, exist_ok=True)
                    tmp = STORE.with_suffix(".tmp")
                    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
                    os.replace(tmp, STORE)
                except OSError:
                    pass
            time.sleep(EVERY if status == "on" else 10)

    def key_for(self, title, artist):
        """The key djay showed for this song (now or any earlier time), or ''."""
        with self.lock:
            hit = self.saved.get(self._id(title, artist))
            if hit:
                return hit["key"]
            t = self.norm(title)
            ks = {v["key"] for v in self.saved.values() if self.norm(v["title"]) == t}
            return ks.pop() if len(ks) == 1 else ""

    def all(self):
        with self.lock:
            return [(v["title"], v["artist"], v["key"]) for v in self.saved.values()]
