"""Starts GOOD MIXX with an empty data folder, plays two songs the way Traktor reports them,
and checks the decks, keys, history and the iPad page. Run: python3 tests/smoke_test.py"""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()   # never clashes with a running GOOD MIXX


def call(path, data=None):
    req = urllib.request.Request("http://localhost:%d%s" % (PORT, path),
                                 data=None if data is None else json.dumps(data).encode(), method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=5) as r:
        body = r.read()
        return json.loads(body) if r.headers.get_content_type() == "application/json" else body


def main():
    tmp = Path(tempfile.mkdtemp())
    env = dict(os.environ, GOODMIXX_PORT=str(PORT), GOODMIXX_DATA=str(tmp / "data"), HOME=str(tmp / "home"), DJAY_LIBRARY=str(tmp / "none.db"))
    proc = subprocess.Popen([sys.executable, "mixes_server.py"], cwd=ROOT / "app", env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                if "ipad" in call("/api/info"):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            sys.exit("server did not start")
        call("/traktor/deckLoaded/A", {"title": "Song One", "artist": "Artist", "keyText": "3m", "bpm": 93, "isPlaying": True})
        time.sleep(0.05)
        call("/traktor/deckLoaded/B", {"title": "Song Two", "artist": "Artist", "key": 19, "bpm": 95.2, "isPlaying": False})
        call("/traktor/updateDeck/B", {"isPlaying": True})
        now = call("/api/now")
        assert now["traktor"] and now["source"] == "traktor", now
        assert now["decks"]["A"]["key"] == "10A" and now["decks"]["B"]["key"] == "6A", now["decks"]
        assert now["playing"] == "B"
        sets = call("/api/djay/sessions")["sessions"]
        assert sets and sets[0]["pairs"][0]["to"]["title"] == "Song Two", sets
        assert (tmp / "data" / "traktor_history.json").exists()
        page = call("/mixes").decode()
        assert "GOOD MIXX" in page and "/gm/assets/gm-lockup.png" in page
        assert call("/gm/assets/gm-lockup.png")[:4] == b"\x89PNG"
        call("/api/links", {"from": now["decks"]["A"]["id"], "to": now["decks"]["B"]["id"]})
        assert call("/api/links")["links"][0]["count"] == 1
        call("/api/quit", {})
        proc.wait(timeout=5)
        print("smoke test passed")
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    main()
