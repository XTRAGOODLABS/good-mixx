"""Follows what Traktor Pro 4 / 3 is playing, using the small 'Traktor link' add-on (traktor-link/D2).

Traktor sends each deck's song, artist, key, BPM and play/stop to DJ Mixes on this Mac
(http://localhost:8770/traktor/...). Every song you start is saved to data/traktor_history.json,
so after a set the REVIEW tab works just like it does with djay.
Keys for the whole library come from Traktor's own collection.nml file (read-only).
"""
import json, os, threading, time
import xml.etree.ElementTree as ET
from pathlib import Path

import djay_screen

BASE = Path(__file__).parent
HIST = Path(os.environ.get("GOODMIXX_DATA") or BASE / "data") / "traktor_history.json"
NI_DOCS = Path.home() / "Documents" / "Native Instruments"
NEW_SET_GAP = 3 * 3600          # a 3-hour break starts a new set

# Traktor's key numbers: 0-11 = C..B major, 12-23 = C..B minor
_MAJ = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
_MIN = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]


def key_from(text=None, number=None):
    k = djay_screen.camelot(str(text or ""))
    if k:
        return k
    try:
        n = int(number)
    except (TypeError, ValueError):
        return ""
    return (_MAJ + _MIN)[n] if 0 <= n <= 23 else ""


class Traktor:
    def __init__(self):
        self.lock = threading.Lock()
        self.decks = {}          # 1-4 -> current song on that deck
        self.history = []
        self.last_heard = 0.0
        self.coll = {"path": None, "mtime": None, "songs": []}
        try:
            self.history = json.loads(HIST.read_text())
        except (OSError, ValueError):
            pass

    # ---- from Traktor ----
    def receive(self, endpoint, msg):
        parts = endpoint.strip("/").split("/")
        if len(parts) < 2 or parts[0] not in ("deckLoaded", "updateDeck"):
            with self.lock:
                self.last_heard = time.time()
            return
        try:
            deck = "ABCD".index(parts[1].upper()) + 1
        except ValueError:
            return
        with self.lock:
            self.last_heard = time.time()
            d = self.decks.setdefault(deck, {})
            if parts[0] == "deckLoaded":
                d.clear()
                d.update(title=(msg.get("title") or "").strip(), artist=(msg.get("artist") or "").strip(),
                         bpm=round(float(msg.get("bpm") or 0), 1),
                         key=key_from(msg.get("keyText"), msg.get("key")),
                         length=msg.get("trackLength") or 0, logged=False)
            if "isPlaying" in msg:
                d["playing"] = bool(msg["isPlaying"])
            if d.get("playing") and d.get("title") and not d.get("logged"):
                d["logged"] = True
                self._log(deck, d)

    def _log(self, deck, d):
        now = time.time()
        last = self.history[-1] if self.history else None
        session = last["session"] if last and now - last["start"] < NEW_SET_GAP else "traktor-%d" % now
        self.history.append({"key": "tk-%d-%d" % (now * 1000, deck), "session": session, "deck": deck,
                             "start": now, "title": d["title"], "artist": d["artist"], "tid": "",
                             "length": d.get("length", 0), "bpm": d["bpm"], "djkey": d["key"]})
        self.history = self.history[-5000:]
        try:
            HIST.parent.mkdir(parents=True, exist_ok=True)
            tmp = HIST.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.history, ensure_ascii=False, indent=0))
            os.replace(tmp, HIST)
        except OSError:
            pass

    # ---- for DJ Mixes ----
    def connected(self):
        return time.time() - self.last_heard < 120

    def plays(self):
        with self.lock:
            return [dict(p) for p in self.history]

    def songs(self):
        """Every song in Traktor's collection (title, artist, BPM, key). Re-read when Traktor saves it."""
        try:
            files = sorted(NI_DOCS.glob("Traktor*/collection.nml"), key=lambda p: p.stat().st_mtime)
        except OSError:
            files = []
        if not files:
            return []
        path = files[-1]
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return self.coll["songs"]
        if self.coll["path"] == path and self.coll["mtime"] == mtime:
            return self.coll["songs"]
        out = []
        try:
            for _, el in ET.iterparse(str(path)):
                if el.tag != "ENTRY":
                    continue
                loc, info, mk, tempo = el.find("LOCATION"), el.find("INFO"), el.find("MUSICAL_KEY"), el.find("TEMPO")
                fname = loc.get("FILE", "") if loc is not None else ""
                title, artist = el.get("TITLE") or "", el.get("ARTIST") or ""
                if not title and fname:                       # untagged file: "Artist - Title.mp3"
                    base = fname.rsplit(".", 1)[0]
                    artist, _, title = base.partition(" - ") if " - " in base else ("", "", base)
                if title:
                    try:
                        bpm = round(float(tempo.get("BPM")), 1) if tempo is not None else 0
                    except (TypeError, ValueError):
                        bpm = 0
                    where = (loc.get("VOLUME", "") + loc.get("DIR", "") + fname) if loc is not None else title
                    out.append({"title": title.strip(), "artist": artist.strip(), "bpm": bpm,
                                "key": key_from(info.get("KEY") if info is not None else None,
                                                mk.get("VALUE") if mk is not None else None),
                                "show": "Traktor", "id": "tk:" + where})
                el.clear()
        except (ET.ParseError, OSError):
            return self.coll["songs"]
        self.coll = {"path": path, "mtime": mtime, "songs": out}
        return out

    def keys(self):
        """(title, artist, key) for every song in Traktor's collection that has a key."""
        return [(s["title"], s["artist"], s["key"]) for s in self.songs() if s["key"]]
