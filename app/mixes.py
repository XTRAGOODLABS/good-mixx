"""Mixes screen: remembers good transitions and serves the song list.
Plugged into server.py; the stems/FX page and MIDI are untouched."""
import csv, io, json, os, re, subprocess, threading, time
from pathlib import Path
import djay_live
import error_log
import djay_screen
import recorder
import studio
import traktor_live

BASE = Path(__file__).parent
DATA = Path(os.environ.get("GOODMIXX_DATA") or BASE / "data")   # the app keeps its data outside itself
ASSETS = BASE / "assets"
INFO = {}   # filled in by mixes_server.py (iPad address)
LIB = DATA / "library.json"
MIXES = DATA / "mixes.json"
lock = threading.Lock()
STEMS = True          # False when run from mixes_server.py (no stems page)
_djay = djay_live.Djay()
_traktor = traktor_live.Traktor()
_screen = None   # started below, once _norm exists
_index = {"mtime": None, "both": {}, "title": {}}
STUDIO = DATA / "studio_mixes.json"
_finder = studio.Finder(DATA, djay=_djay, traktor=_traktor, library=LIB.exists())
_recorder = recorder.Recorder(DATA)
_finder.recorder = _recorder


def start_recorder():
    """Record sets whenever djay is open on this Mac (if djay-pro-mcp is set up and recording is on)."""
    import atexit
    atexit.register(_recorder.stop)
    _recorder.start_watching()
_render = studio.Renderer()


def _load():
    if MIXES.exists():
        try:
            return json.loads(MIXES.read_text())
        except ValueError:
            pass
    return {"version": 1, "links": []}


def _save(db):
    DATA.mkdir(parents=True, exist_ok=True)
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


# ---------------------------------------------------------------- STUDIO (Mac window only)
def _local(h):
    return h.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def _studio_load():
    try:
        return json.loads(STUDIO.read_text())
    except (OSError, ValueError):
        return {"version": 1, "mixes": []}


def _studio_save(db):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = STUDIO.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1))
    os.replace(tmp, STUDIO)


def _studio_sets(limit=30):
    """Past sets played on this Mac (djay or Traktor), each with its songs in the order played."""
    plays, err = _plays()
    ix = _lookup()
    by = {}
    for p in plays:
        by.setdefault(p["session"], []).append(p)
    out = []
    has_rec = bool(_recorder.files())
    for sid, ps in sorted(by.items(), key=lambda kv: kv[1][0]["start"], reverse=True)[:limit]:
        songs, last = [], None
        for p in sorted(ps, key=lambda x: x["start"]):
            if last and (_norm(last["title"]), _norm(last["artist"])) == (_norm(p["title"]), _norm(p["artist"])):
                continue                            # the same song started twice in a row
            last = p
            s = _djay_song(p)
            lib = ix["both"].get(_norm(p["artist"]) + "|" + _norm(p["title"])) or ix["title"].get(_norm(p["title"])) or {}
            song = {"sid": s["id"], "title": p["title"], "artist": p["artist"], "key": s.get("key", ""),
                    "bpm": p.get("bpm") or lib.get("bpm") or "", "length": p.get("length") or lib.get("length") or 0,
                    "tid": p.get("tid", ""), "set_start": p["start"]}
            if has_rec:
                ref = _recorder.match(p["title"], p["artist"], p["start"], deck=p.get("deck"))
                if ref:
                    song["rec"] = ref
            songs.append(song)
        out.append({"id": sid, "start": int(ps[0]["start"]), "end": int(ps[-1]["start"]), "songs": songs,
                    "recorded": sum(1 for x in songs if x.get("rec")),
                    "app": "Traktor" if str(ps[0]["key"]).startswith("tk-") else "djay"})
    return {"error": err, "sets": out}


def _studio_info():
    return {"ffmpeg": bool(studio.ffmpeg()), "out": str(studio.OUT_DIR), "mixes": _studio_load()["mixes"],
            "render": _render.status}


def _clean_mix(m):
    items = []
    for it in (m.get("items") or [])[:400]:
        if not isinstance(it, dict) or not it.get("title"):
            continue
        items.append({k: it.get(k) for k in ("sid", "title", "artist", "bpm", "key", "length", "tid", "set_start",
                                             "blend", "cut_in", "cut_out", "nudge", "start_cue", "bars", "fade", "fx",
                                             "fade_in_len", "fade_out_len", "tail", "rec")
                      if it.get(k) not in (None, "") and not (k in ("cut_in", "cut_out", "nudge", "fade_in_len", "fade_out_len", "tail")
                                                              and not it.get(k))})
    blend = m.get("blend") if m.get("blend") in ("beat", "set", "fade", "rec") else "beat"
    return {"id": str(m.get("id") or "")[:40], "name": str(m.get("name") or "New mix")[:80], "blend": blend,
            "bars": int(m.get("bars") or 16), "fade": float(m.get("fade") or 12), "source": str(m.get("source") or "")[:80],
            "items": items}


def _send_file(h, f, ctype):
    """Send a file, honouring Range requests (Safari / the Mac app need them to play and seek audio)."""
    size = os.path.getsize(f)
    start, end, code = 0, size - 1, 200
    rng = h.headers.get("Range", "")
    m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
    if m and size:
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        elif m.group(2):
            start = max(0, size - int(m.group(2)))
        end = min(end, size - 1)
        if start > end:
            h.send_response(416)
            h.send_header("Content-Range", "bytes */%d" % size)
            h.end_headers()
            return True
        code = 206
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(end - start + 1))
    h.send_header("Cache-Control", "no-store")
    if code == 206:
        h.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    h.end_headers()
    with open(f, "rb") as fh:
        fh.seek(start)
        left = end - start + 1
        while left > 0:
            chunk = fh.read(min(65536, left))
            if not chunk:
                break
            try:
                h.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            left -= len(chunk)
    return True


PREVIEWS = DATA / "previews"


def _audio_type(f):
    return {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}.get(Path(f).suffix.lower(), "application/octet-stream")


def _studio_get(h, path):
    if not _local(h):
        return _send(h, 403, {"error": "STUDIO works in the GOOD MIXX window on the Mac"})
    from urllib.parse import parse_qs, urlsplit
    q = {k: v[0] for k, v in parse_qs(urlsplit(h.path).query).items()}
    if path == "/api/studio/wave":
        f = q.get("p", "")
        if not f.lower().endswith(studio.AUDIO_EXT) or not os.path.isfile(f):
            return _send(h, 404, {"error": "not found"})
        w = studio.wave(f, DATA / "waves")
        return _send(h, 200, w) if w else _send(h, 404, {"error": "no wave (needs ffmpeg)"})
    if path == "/api/studio/audio":
        name = q.get("f", "")
        if name:                                        # a blend preview
            f = PREVIEWS / name
            if "/" in name or ".." in name or not f.is_file():
                return _send(h, 404, {"error": "not found"})
        else:                                           # a finished mix in Music/GOOD MIXX
            f = Path(q.get("p", ""))
            try:
                ok = f.is_file() and f.resolve().parent == studio.OUT_DIR.resolve()
            except OSError:
                ok = False
            if not ok:
                return _send(h, 404, {"error": "not found"})
        return _send_file(h, str(f), _audio_type(f))
    if path == "/api/studio/info":
        return _send(h, 200, _studio_info())
    if path == "/api/studio/sets":
        return _send(h, 200, _studio_sets())
    if path == "/api/studio/render":
        return _send(h, 200, _render.status)
    return _send(h, 404, {"error": "unknown"})


def _studio_post(h, path, raw):
    try:
        return _studio_post_inner(h, path, raw)
    except Exception as e:                       # show the reason in the window instead of hanging
        error_log.record_exception("studio", e)
        return _send(h, 500, {"error": "%s: %s" % (type(e).__name__, e)})


def _studio_post_inner(h, path, raw):
    if not _local(h):
        return _send(h, 403, {"error": "STUDIO works in the GOOD MIXX window on the Mac"})
    msg = json.loads(raw or b"{}")
    if path == "/api/studio/save":
        mix = _clean_mix(msg.get("mix") or {})
        with lock:
            db = _studio_load()
            if not mix["id"]:
                mix["id"] = "m%d" % (time.time() * 1000)
            mix["saved"] = int(time.time())
            db["mixes"] = [x for x in db["mixes"] if x.get("id") != mix["id"]] + [mix]
            _studio_save(db)
        return _send(h, 200, {"mix": mix, "mixes": db["mixes"]})
    if path == "/api/studio/delete":
        with lock:
            db = _studio_load()
            db["mixes"] = [x for x in db["mixes"] if x.get("id") != msg.get("id")]
            _studio_save(db)
        return _send(h, 200, {"mixes": db["mixes"]})
    if path == "/api/studio/plan":
        return _send(h, 200, studio.plan(_clean_mix(msg.get("mix") or {}), _finder, analyze=bool(msg.get("analyze", True))))
    if path == "/api/studio/render":
        mix = _clean_mix(msg.get("mix") or {})
        fmt = "wav" if msg.get("format") == "wav" else "mp3"
        if not studio.ffmpeg():
            return _send(h, 200, {"state": "error", "msg": "Building the audio needs ffmpeg (free). See the read-me."})
        p = studio.plan(mix, _finder, analyze=True)
        if not p["playable"]:
            return _send(h, 200, {"state": "error", "msg": "None of these songs were found as files on this Mac."})
        if not _render.start(p, mix["name"], fmt):
            return _send(h, 200, {"state": "error", "msg": "Already building a mix - wait for it to finish."})
        return _send(h, 200, _render.status)
    if path == "/api/studio/preview":
        import hashlib
        mix = _clean_mix(msg.get("mix") or {})
        index = int(msg.get("index") or 0)
        if not 0 < index < len(mix["items"]):
            return _send(h, 400, {"error": "pick a song after the first one"})
        p = studio.plan(mix, _finder, analyze=True)
        PREVIEWS.mkdir(parents=True, exist_ok=True)
        old = sorted(PREVIEWS.glob("*.mp3"), key=lambda x: x.stat().st_mtime)
        for f in old[:-40]:                             # keep the folder small
            try:
                f.unlink()
            except OSError:
                pass
        sig = json.dumps([[r.get("path"), round(r.get("mix_start") or 0, 3), round(r.get("rate") or 1, 5),
                           round(r.get("song_in") or 0, 3), round(r.get("song_out") or 0, 3), r.get("fade_in"), r.get("fade_out")]
                          for r in p["items"][max(0, index - 1):index + 2]] + [index])
        name = hashlib.sha1(sig.encode()).hexdigest()[:20] + ".mp3"
        f = PREVIEWS / name
        win = studio.blend_window(p, index)
        if not f.exists():
            try:
                studio.preview(p, index, f)
            except RuntimeError as e:
                return _send(h, 200, {"error": str(e)})
        item = p["items"][index]
        return _send(h, 200, {"url": "/api/studio/audio?f=" + name, "start": win[0] if win else 0,
                              "blend_at": item.get("mix_start"), "blend_used": item.get("blend_used"), "warn": item.get("warn", "")})
    if path == "/api/studio/cancel":
        _render.cancel()
        return _send(h, 200, _render.status)
    if path == "/api/studio/export":
        mix = _clean_mix(msg.get("mix") or {})
        p = studio.plan(mix, _finder, analyze=False)
        studio.OUT_DIR.mkdir(parents=True, exist_ok=True)
        base = studio.safe_name(mix["name"])
        m3u = studio.unique(studio.OUT_DIR / (base + ".m3u8"))
        m3u.write_text(studio.playlist(p, mix["name"]))
        txt = m3u.with_name(m3u.stem + " - tracklist.txt")
        txt.write_text(studio.tracklist(p, mix["name"]))
        return _send(h, 200, {"playlist": str(m3u), "tracklist": str(txt),
                              "found": sum(1 for r in p["items"] if r.get("path")), "songs": len(p["items"])})
    if path == "/api/studio/choose":
        item = msg.get("item") or {}
        who = ((item.get("artist") or "") + " - " if item.get("artist") else "") + (item.get("title") or "this song")
        script = ('tell me to activate\nPOSIX path of (choose file with prompt "Find the music file for %s" '
                  'of type {"public.audio"})' % who.replace("\\", "").replace('"', "'")[:120])
        try:
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
            chosen = r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            chosen = ""
        if chosen and os.path.isfile(chosen):
            _finder.remember(item, chosen)
            return _send(h, 200, {"path": chosen})
        return _send(h, 200, {"path": ""})
    if path == "/api/studio/reveal":
        p = str(msg.get("path") or "")
        if p and os.path.isfile(p) and (p.startswith(str(studio.OUT_DIR)) or p.lower().endswith(studio.AUDIO_EXT)):
            try:
                subprocess.run(["open", "-R", p], timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass
            return _send(h, 200, {"ok": True})
        return _send(h, 404, {"error": "not found"})
    return _send(h, 404, {"error": "unknown"})


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
    if path.startswith("/gm/assets/"):
        name = path[len("/gm/assets/"):]
        f = ASSETS / name
        types = {".png": "image/png", ".woff2": "font/woff2"}
        if "/" in name or ".." in name or not f.is_file() or f.suffix not in types:
            return _send(h, 404, {"error": "not found"})
        h.send_response(200)
        h.send_header("Content-Type", types[f.suffix])
        h.send_header("Cache-Control", "max-age=86400")
        body = f.read_bytes()
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)
        return True
    if path == "/api/info":
        return _send(h, 200, INFO)
    if path in ("/api/report-problem", "/api/suggest-idea"):   # opens the GitHub form; nothing is sent
        h.send_response(302)
        h.send_header("Location", error_log.report_url(INFO.get("version", "")) if path == "/api/report-problem"
                      else error_log.idea_url())
        h.send_header("Cache-Control", "no-store")
        h.send_header("Content-Length", "0")
        h.end_headers()
        return True
    if path == "/api/library":
        return _send(h, 200, _library_with_djay_keys())
    if path == "/api/links":
        with lock:
            return _send(h, 200, _load())
    if path == "/api/now":
        return _send(h, 200, _now())
    if path == "/api/djay/sessions":
        return _send(h, 200, _sessions())
    if path == "/api/recorder":
        return _send(h, 200, _recorder.status())
    if path.startswith("/api/studio/"):
        try:
            return _studio_get(h, path)
        except (BrokenPipeError, ConnectionResetError):
            return True
        except Exception as e:
            error_log.record_exception("studio", e)
            return _send(h, 500, {"error": "%s: %s" % (type(e).__name__, e)})
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
    if path == "/api/quit" and h.client_address[0] in ("127.0.0.1", "::1"):
        _send(h, 200, {"ok": True})              # only from this Mac, never from the iPad
        _recorder.stop()
        threading.Timer(0.3, lambda: os._exit(0)).start()
        return True
    if not path.startswith("/api/"):
        return False
    if path == "/api/client-error":            # an error in the GOOD MIXX page, kept in the local log
        try:
            n = int(h.headers.get("Content-Length", 0))
            msg = json.loads(h.rfile.read(n) or b"{}") if 0 < n < 20_000 else {}
            error_log.record("page", str(msg.get("message", ""))[:500] if isinstance(msg, dict) else "")
        except (ValueError, TypeError):
            pass
        return _send(h, 200, b"{}")
    try:
        length = int(h.headers.get("Content-Length", 0))
        if length > 3_000_000:
            return _send(h, 413, {"error": "too big"})
        raw = h.rfile.read(length)
        if path.startswith("/api/studio/"):
            return _studio_post(h, path, raw)
        if path in ("/api/recorder", "/api/recorder/setup"):
            if not _local(h):
                return _send(h, 403, {"error": "only on the Mac"})
            if path == "/api/recorder/setup":
                _recorder.setup()
            else:
                _recorder.set_enabled(bool(json.loads(raw or b"{}").get("enabled")))
            return _send(h, 200, _recorder.status())
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
