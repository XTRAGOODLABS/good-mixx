"""Mixes screen: remembers good transitions and serves the song list.
Plugged into server.py; the stems/FX page and MIDI are untouched."""
import csv, io, json, os, re, threading, time
from pathlib import Path
import djay_live
import djay_screen
import traktor_live

BASE = Path(__file__).parent
DATA = BASE / "data"
LIB = DATA / "library.json"
MIXES = DATA / "mixes.json"
lock = threading.Lock()
STEMS = True          # False when run from mixes_server.py (no stems page)
_djay = djay_live.Djay()
_traktor = traktor_live.Traktor()
_screen = None   # started below, once _norm exists
_index = {"mtime": None, "both": {}, "title": {}}


def _load():
    if MIXES.exists():
        try:
            return json.loads(MIXES.read_text())
        except ValueError:
            pass
    return {"version": 1, "links": []}


def _save(db):
    DATA.mkdir(exist_ok=True)
    if MIXES.exists():
        (DATA / "mixes.backup.json").write_text(MIXES.read_text())
    tmp = MIXES.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1))
    os.replace(tmp, MIXES)


def _plays():
    """Songs played in djay and Traktor on this Mac, oldest first."""
    found, err = _djay.plays()
    tk = _traktor.plays()
    if tk:
        found = sorted(found + tk, key=lambda p: p["start"])
        err = ""
    elif err and _traktor.connected():
        err = ""
    return found, err


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"\((feat|ft|with)[^)]*\)|\bfeat\.?.*$|\bft\.?.*$", "", s)
    s = re.sub(r"\(.*?(edit|version|remaster|clean|radio|explicit|dirty).*?\)|\[.*?\]", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


_screen = djay_screen.ScreenKeys(_norm)


def _library():
    """Your show-folder song list; on a Mac without one, Traktor's own collection."""
    if LIB.exists():
        return json.loads(LIB.read_text())
    return {"songs": [dict(s) for s in _traktor.songs()]}


def _parse_history(text):
    """Read a djay playlist export (CSV) or a plain list, in play order."""
    text = text.lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    ti = next((i for i, h in enumerate(head) if h in ("title", "name", "song", "track", "track title", "song title")), None)
    ai = next((i for i, h in enumerate(head) if "artist" in h), None)
    out = []
    if ti is not None:
        for r in rows[1:]:
            if len(r) > ti and r[ti].strip():
                out.append({"title": r[ti].strip(), "artist": r[ai].strip() if ai is not None and len(r) > ai else ""})
        return out
    for line in text.splitlines():  # plain text: "Artist - Title" per line
        line = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
        if not line:
            continue
        parts = line.split(" - ", 1)
        out.append({"artist": parts[0].strip(), "title": parts[1].strip()} if len(parts) == 2 else {"artist": "", "title": line})
    return out


def _match(items):
    songs = _library()["songs"]
    by_both, by_title = {}, {}
    for s in songs:
        by_both.setdefault(_norm(s["artist"]) + "|" + _norm(s["title"]), s)
        by_title.setdefault(_norm(s["title"]), s)
    res = []
    for it in items:
        s = by_both.get(_norm(it["artist"]) + "|" + _norm(it["title"])) or by_title.get(_norm(it["title"]))
        res.append({"id": s["id"] if s else "ext:" + (it["artist"] + " - " if it["artist"] else "") + it["title"],
                    "title": s["title"] if s else it["title"], "artist": s["artist"] if s else it["artist"],
                    "found": bool(s)})
    return res


def _lookup():
    """Song list index, re-read only when library.json changes."""
    if LIB.exists():
        mtime = LIB.stat().st_mtime
    else:
        _traktor.songs()
        mtime = ("traktor", _traktor.coll["mtime"])
    if _index["mtime"] != mtime:
        both, title = {}, {}
        for s in _library()["songs"]:
            for d, k in ((both, _norm(s["artist"]) + "|" + _norm(s["title"])), (title, _norm(s["title"]))):
                if k not in d or (s.get("key") and not d[k].get("key")):  # prefer a copy that has a key
                    d[k] = s
        _index.update(mtime=mtime, both=both, title=title)
    return _index


def _djay_keys():
    """djay's own key for each song it has analysed: by artist+title, and by title when only one key fits."""
    both, title = {}, {}
    for t, a, key in list(_djay.keys()) + _traktor.keys():
        both[_norm(a) + "|" + _norm(t)] = key
        title.setdefault(_norm(t), set()).add(key)
    for t, a, key in _screen.all():          # keys djay showed on a deck but did not save
        if both.setdefault(_norm(a) + "|" + _norm(t), key) == key:
            title.setdefault(_norm(t), set()).add(key)
    return both, {t: next(iter(ks)) for t, ks in title.items() if len(ks) == 1}


def _library_with_djay_keys():
    """The song list, with djay's key used wherever djay has one (the file's own key kept as tagkey)."""
    lib = _library()
    both, title = _djay_keys()
    for s in lib["songs"]:
        k = both.get(_norm(s["artist"]) + "|" + _norm(s["title"])) or title.get(_norm(s["title"]))
        if k and k != s.get("key"):
            s["tagkey"] = s.get("key", "")
            s["key"] = k
    return lib


def _djay_song(p):
    """One djay play -> the matching song from the show folders, or a stand-in with djay's BPM/key."""
    ix = _lookup()
    s = ix["both"].get(_norm(p["artist"]) + "|" + _norm(p["title"])) or ix["title"].get(_norm(p["title"]))
    if s:
        return {"id": s["id"], "title": s["title"], "artist": s["artist"], "found": True,
                "key": p["djkey"] or _screen.key_for(p["title"], p["artist"]) or s.get("key", "")}
    return {"id": "ext:" + (p["artist"] + " - " if p["artist"] else "") + p["title"], "title": p["title"],
            "artist": p["artist"], "found": False, "bpm": p["bpm"] or "",
            "key": p["djkey"] or _screen.key_for(p["title"], p["artist"]), "dj": True}


def _now():
    """What djay is playing right now on this Mac (left decks = A, right decks = B)."""
    plays, err = _plays()
    out = {"ok": True, "stems": STEMS, "djay": not err, "error": err, "live": False, "age": None,
           "screen": _screen.status, "traktor": _traktor.connected(),
           "rev": "", "decks": {"A": None, "B": None}, "playing": None}
    if not plays:
        return out
    newest = plays[-1]
    out["age"] = max(0, int(time.time() - newest["start"]))
    out["live"] = out["age"] < djay_live.LIVE_WINDOW
    out["rev"] = newest["key"]
    out["playing"] = djay_live.side(newest["deck"])
    out["source"] = "traktor" if str(newest["key"]).startswith("tk-") else "djay"
    for p in plays:
        if p["session"] == newest["session"]:
            out["decks"][djay_live.side(p["deck"])] = _djay_song(p)
    return out


def _sessions(limit=12):
    """Recent djay sets played on this Mac, newest first, with every mix in each."""
    plays, err = _plays()
    by = {}
    for p in plays:
        by.setdefault(p["session"], []).append(p)
    out = []
    for sid, ps in sorted(by.items(), key=lambda kv: kv[1][0]["start"], reverse=True)[:limit]:
        songs = [_djay_song(p) for p in ps]
        pairs = [{"from": _djay_song(a), "to": _djay_song(b)} for a, b in djay_live.pairs_for(ps)]
        pairs = [x for x in pairs if x["from"]["id"] != x["to"]["id"]]
        out.append({"id": sid, "start": int(ps[0]["start"]), "songs": len(ps),
                    "found": sum(s["found"] for s in songs), "pairs": pairs})
    return {"djay": not err, "error": err, "sessions": out}


def _send(h, code, body=b"", ctype="application/json"):
    if isinstance(body, (dict, list)):
        body = json.dumps(body, ensure_ascii=False).encode()
    h.send_response(code)
    h.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)
    return True


def handle_get(h):
    path = h.path.split("?")[0]
    if path in ("/mixes", "/mixes.html"):
        return _send(h, 200, (BASE / "mixes.html").read_bytes(), "text/html")
    if path == "/api/library":
        return _send(h, 200, _library_with_djay_keys())
    if path == "/api/links":
        with lock:
            return _send(h, 200, _load())
    if path == "/api/now":
        return _send(h, 200, _now())
    if path == "/api/djay/sessions":
        return _send(h, 200, _sessions())
    return False


def handle_post(h):
    path = h.path.split("?")[0]
    if path.startswith("/traktor/"):           # live deck info from the Traktor link add-on
        try:
            n = int(h.headers.get("Content-Length", 0))
            msg = json.loads(h.rfile.read(n) or b"{}") if 0 < n < 200_000 else {}
            _traktor.receive(path[len("/traktor/"):], msg if isinstance(msg, dict) else {})
        except (ValueError, TypeError):
            pass
        return _send(h, 200, b"{}")
    if not path.startswith("/api/"):
        return False
    try:
        length = int(h.headers.get("Content-Length", 0))
        if length > 3_000_000:
            return _send(h, 413, {"error": "too big"})
        raw = h.rfile.read(length)
        if path == "/api/history":
            items = _parse_history(raw.decode("utf-8", "replace"))
            played = _match(items)
            pairs = [{"from": played[i], "to": played[i + 1]} for i in range(len(played) - 1)
                     if played[i]["id"] != played[i + 1]["id"]]
            return _send(h, 200, {"songs": len(played), "found": sum(p["found"] for p in played), "pairs": pairs})
        msg = json.loads(raw or b"{}")
        a, b = str(msg["from"])[:400], str(msg["to"])[:400]
        if not a or not b or a == b:
            raise ValueError
        with lock:
            db = _load()
            link = next((l for l in db["links"] if l["from"] == a and l["to"] == b), None)
            if path == "/api/links":
                now = int(time.time())
                if link:
                    link["count"] += 1
                    link["last"] = now
                else:
                    db["links"].append({"from": a, "to": b, "count": 1, "first": now, "last": now,
                                        "source": msg.get("source", "live")})
            elif path == "/api/links/delete":
                db["links"] = [l for l in db["links"] if not (l["from"] == a and l["to"] == b)]
            else:
                return _send(h, 404, {"error": "unknown"})
            _save(db)
            return _send(h, 200, db)
    except (ValueError, KeyError, TypeError):
        return _send(h, 400, {"error": "bad request"})
