"""Reads what djay on this Mac is playing, straight from djay's own library file.

djay writes every song you start to its History as you play. This module opens that
library read-only (it never writes to it), so nothing here can touch djay or your decks.
No extra macOS permissions and no installs are needed.
"""
import os, sqlite3, struct, threading, time
from pathlib import Path
from urllib.parse import quote

DB = Path(os.environ.get("DJAY_LIBRARY") or
          Path.home() / "Music" / "djay" / "djay Media Library.djayMediaLibrary" / "MediaLibrary.db")
APPLE_EPOCH = 978307200          # djay stores times as seconds since 2001-01-01
LIVE_WINDOW = 30 * 60            # a song started in the last 30 min counts as "live"
_CAMELOT_MAJOR = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1]
_END = object()


def camelot(i):
    """djay key number (0-23) -> Camelot key like '8A'."""
    if not isinstance(i, int) or not 0 <= i <= 23:
        return ""
    return "%d%s" % (_CAMELOT_MAJOR[i // 2], "A" if i % 2 else "B")


def decode(buf):
    """Decode one djay library record (their 'TSAF' archive format) into plain dicts."""
    if buf[:4] != b"TSAF" or struct.unpack_from("<H", buf, 4)[0] != 3:
        raise ValueError("not a djay record")
    st = {"o": 20}
    strings, objects, classes = [], [], []

    def align(n):
        r = st["o"] % n
        if r:
            st["o"] += n - r

    def num(fmt, size, al=True):
        if al:
            align(size)
        v = struct.unpack_from(fmt, buf, st["o"])[0]
        st["o"] += size
        return v

    def raw():
        end = buf.index(b"\0", st["o"])
        s = buf[st["o"]:end].decode("utf-8", "replace")
        st["o"] = end + 1
        return s

    def keep(v):
        objects.append(v)
        return v

    def read():
        t = num("<B", 1, False)
        if t in (0, 47): return _END
        if t == 1: return None
        if t == 2: return objects[num("<B", 1, False)]
        if t == 3: return objects[num("<H", 2)]
        if t == 4: return objects[num("<I", 4)]
        if t == 5: return strings[num("<B", 1, False)]
        if t == 6: return strings[num("<H", 2)]
        if t == 7: return strings[num("<I", 4)]
        if t == 8:
            s = raw(); strings.append(s); return s
        if t == 23: return keep(raw())
        if t == 13: return True
        if t == 14: return False
        if t == 45: return 1
        if t == 46: return 0
        if t == 15: return num("<b", 1, False)
        if t == 16: return num("<h", 2)
        if t == 17: return num("<i", 4)
        if t == 18: return num("<q", 8)
        if t == 19: return num("<f", 4)
        if t in (20, 44): return num("<d", 8)
        if t == 22: return keep(num("<d", 8))
        if t == 48: return keep(num("<d", 8) + APPLE_EPOCH)
        if t in (21, 28):
            n = num("<I", 4); st["o"] += n; align(4); return keep(None)
        if t in (9, 24):
            n = num("<I", 4); d = {}
            if t == 24: keep(d)
            for _ in range(n):
                v = read(); k = read(); d[str(k)] = v
            return d if t == 24 else keep(d)
        if t in (10, 11, 12, 25, 26, 27):
            n = num("<I", 4); a = []
            if t in (25, 26, 27): keep(a)
            for _ in range(n): a.append(read())
            return a if t in (25, 26, 27) else keep(a)
        if t == 33:
            s = read(); base = read()
            return (base + s) if isinstance(base, str) and base else s
        if t in (34, 35): st["o"] += (-st["o"]) % 8 + 16; return None
        if t in (36, 38): st["o"] += (-st["o"]) % 8 + 32; return None
        if t == 37: num("<I", 4); num("<I", 4); return None
        if t == 39: st["o"] += (-st["o"]) % 8 + 48; return None
        if t == 40: st["o"] += (-st["o"]) % 8 + 128; return None
        if t in (41, 42):
            n = num("<I", 4)
            for _ in range(n): num("<I", 4); num("<I", 4)
            return keep(None)
        if t == 43:
            obj = {"$class": read()}
            while True:
                v = read()
                if v is _END: break
                obj[str(read())] = v
            return keep(obj)
        if t == 29:
            name = read(); n = num("<I", 4)
            classes.append((str(name), [str(read()) for _ in range(n)]))
            return read()
        if t in (30, 31, 32):
            idx = num("<B", 1, False) if t == 30 else num("<H", 2) if t == 31 else num("<I", 4)
            name, keys = classes[idx]
            obj = keep({"$class": name})
            for k in keys: obj[k] = read()
            return obj
        raise ValueError("unknown record type %d" % t)

    root = read()
    return None if root is _END else root


class Djay:
    """Keeps an up-to-date list of what djay has played. Safe to call from many requests."""

    def __init__(self, path=DB):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.items = {}        # history item key -> dict
        self.raw = {}          # history item key -> record bytes (so unchanged ones are not re-read)
        self.last_read = 0.0
        self.meta = {}         # titleID -> (bpm, key)
        self.allkeys = []      # (title, artist, key) for every song djay has saved a key for
        self.keys_read = 0.0
        self.error = ""

    def _open(self):
        return sqlite3.connect("file:" + quote(str(self.path)) + "?mode=ro", uri=True, timeout=1.5)

    def _refresh(self):
        now = time.time()
        if now - self.last_read < 1.0:
            return
        self.last_read = now
        if not self.path.exists():
            self.error = "djay library not found on this Mac"
            return
        try:
            con = self._open()
            try:
                rows = con.execute("select key, data from database2 where collection='historySessionItems'").fetchall()
                fresh, raw = {}, {}
                for key, data in rows:
                    data = bytes(data)
                    raw[key] = data
                    if self.raw.get(key) == data:
                        if key in self.items:
                            fresh[key] = self.items[key]
                        continue
                    try:
                        r = decode(data)
                    except Exception:
                        continue
                    tid = r.get("titleID") or {}
                    start = r.get("startTime")
                    if not isinstance(start, (int, float)) or not tid.get("title"):
                        continue
                    fresh[key] = {"key": key, "session": r.get("sessionUUID") or "", "deck": r.get("deckNumber") or 1,
                                  "start": float(start), "title": tid.get("title") or "", "artist": tid.get("artist") or "",
                                  "tid": tid.get("uuid") or "", "length": tid.get("duration") or 0}
                self.items, self.raw = fresh, raw
                for it in self.items.values():          # BPM + key as djay analysed them
                    if it["tid"] and it["tid"] not in self.meta:
                        row = con.execute("select data from database2 where collection='mediaItemAnalyzedData' and key=?",
                                          (it["tid"],)).fetchone()
                        bpm, key = 0, ""
                        if row:
                            try:
                                a = decode(bytes(row[0]))
                                bpm = a.get("manualBPM") or a.get("bpm") or 0
                                k = a.get("manualKeySignatureIndex")
                                key = camelot(k if isinstance(k, int) else a.get("keySignatureIndex"))
                            except Exception:
                                pass
                            self.meta[it["tid"]] = (round(float(bpm), 1) if bpm else 0, key)
                        elif now - it["start"] > 600:   # djay may still be analysing a new song
                            self.meta[it["tid"]] = (0, "")
                self.error = ""
            finally:
                con.close()
        except sqlite3.Error as e:
            self.error = "could not read djay's library (%s)" % e

    def keys(self):
        """Every song djay on this Mac has saved a key for. Re-read at most every 20 seconds."""
        with self.lock:
            now = time.time()
            if now - self.keys_read < 20 or not self.path.exists():
                return self.allkeys
            self.keys_read = now
            try:
                con = self._open()
                try:
                    out = []
                    for (data,) in con.execute("select data from database2 where collection='mediaItemAnalyzedData'"):
                        try:
                            a = decode(bytes(data))
                        except Exception:
                            continue
                        k = a.get("manualKeySignatureIndex")
                        key = camelot(k if isinstance(k, int) else a.get("keySignatureIndex"))
                        if not key:
                            continue
                        for t in a.get("titleIDs") or []:
                            if isinstance(t, dict) and t.get("title"):
                                out.append((t["title"], t.get("artist") or "", key))
                    self.allkeys = out
                finally:
                    con.close()
            except sqlite3.Error:
                pass
            return self.allkeys

    def plays(self):
        """Every song djay has logged, oldest first."""
        with self.lock:
            self._refresh()
            out = []
            for it in sorted(self.items.values(), key=lambda x: x["start"]):
                bpm, key = self.meta.get(it["tid"], (0, ""))
                out.append(dict(it, bpm=bpm, djkey=key))
            return out, self.error


def side(deck):
    """djay decks 1 and 3 are on the left (A), 2 and 4 on the right (B)."""
    return "A" if int(deck or 1) % 2 == 1 else "B"


def pairs_for(plays):
    """Each mix = a new song starting while the other side's latest song was the one playing."""
    last, out, seen = {}, [], set()
    for p in plays:
        s = side(p["deck"])
        prev = last.get("B" if s == "A" else "A")
        if prev is not None and (prev["title"], prev["artist"]) != (p["title"], p["artist"]):
            k = (prev["key"], p["key"])
            if k not in seen:
                seen.add(k)
                out.append((prev, p))
        last[s] = p
    return out
