"""Mixes screen: remembers good transitions and serves the song list.
Plugged into server.py; the stems/FX page and MIDI are untouched."""
import csv, io, json, os, re, threading, time
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
LIB = DATA / "library.json"
MIXES = DATA / "mixes.json"
lock = threading.Lock()


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


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"\((feat|ft|with)[^)]*\)|\bfeat\.?.*$|\bft\.?.*$", "", s)
    s = re.sub(r"\(.*?(edit|version|remaster|clean|radio|explicit|dirty).*?\)|\[.*?\]", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _library():
    return json.loads(LIB.read_text()) if LIB.exists() else {"songs": []}


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
        return _send(h, 200, LIB.read_bytes() if LIB.exists() else b'{"songs":[]}')
    if path == "/api/links":
        with lock:
            return _send(h, 200, _load())
    return False


def handle_post(h):
    path = h.path.split("?")[0]
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
