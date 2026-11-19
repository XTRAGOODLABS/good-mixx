"""STUDIO check: makes three beat tracks, plays them as a Traktor set, then recreates the set in STUDIO,
plans a beat-matched mix, checks the beats line up, builds the MP3 and exports the playlist.
Needs ffmpeg (skips the audio parts without it). Run: python3 tests/studio_test.py"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import studio  # noqa: E402

TRACKS = [("Alpha", 120.0, 0.30, 100), ("Bravo", 123.0, 0.71, 100), ("Charlie", 121.0, 2.10, 90)]


def make_tracks(folder):
    for title, bpm, first, secs in TRACKS:
        expr = ("0.8*gte(t,{f})*sin(2*PI*55*mod(t-{f},60/{b}))*exp(-mod(t-{f},60/{b})*22)+0.05*sin(2*PI*440*t)"
                .format(f=first, b=bpm))
        subprocess.run([studio.ffmpeg(), "-v", "quiet", "-y", "-f", "lavfi", "-i", "aevalsrc='%s':s=44100:d=%d" % (expr, secs),
                        "-ac", "2", str(folder / (title + ".mp3"))], check=True)


def collection(home, folder):
    """A tiny Traktor collection.nml pointing at the test tracks."""
    d = home / "Documents" / "Native Instruments" / "Traktor 4.0.0"
    d.mkdir(parents=True)
    rows = "".join('<ENTRY TITLE="%s" ARTIST="Test"><LOCATION DIR="%s" FILE="%s.mp3" VOLUME="Macintosh HD"/>'
                   '<TEMPO BPM="%s"/></ENTRY>' % (t, "/:" + "/:".join(folder.parts[1:]) + "/:", t, b)
                   for t, b, _, _ in TRACKS)
    (d / "collection.nml").write_text('<?xml version="1.0"?><NML><COLLECTION>%s</COLLECTION></NML>' % rows)


def planner_checks(folder):
    mix = {"blend": "beat", "bars": 16, "items": [{"title": t, "path": str(folder / (t + ".mp3")), "bpm": b}
                                                 for t, b, _, _ in TRACKS]}
    moved = dict(mix, items=[dict(it) for it in mix["items"]])
    moved["items"][1]["nudge"] = -16.3                   # dragged in earlier by hand
    auto = studio.plan(mix)["items"][1]["mix_start"]
    truth = {t: (b, f) for t, b, f, _ in TRACKS}
    for p in (studio.plan(mix), studio.plan(moved)):
        check_beats(p, truth)
    shifted = studio.plan(moved)["items"][1]
    beat = 60 / 120.0
    assert shifted["mix_start"] < auto and abs(shifted["nudge_used"] / beat - round(shifted["nudge_used"] / beat)) < 1e-6
    p = studio.plan(mix)
    clip = studio.preview(p, 1, str(folder / "preview.mp3"))
    assert 30 < studio.duration(clip["path"]) < 90, clip
    for blend in ("set", "fade"):
        q = studio.plan(dict(mix, blend=blend, items=[dict(it, set_start=1000 + 80 * i) for i, it in enumerate(mix["items"])]))
        assert all(r["blend_used"] == blend for r in q["items"][1:]), (blend, q["items"])
    missing = studio.plan({"items": mix["items"][:1] + [{"title": "Nowhere", "length": 200}]})
    assert missing["playable"] == 1 and missing["items"][1]["skip"] and missing["warnings"]


def check_beats(p, truth):
    for a, b in zip(p["items"], p["items"][1:]):
        assert b["blend_used"] == "beat", b

        def beats(r):
            bpm, first = truth[r["title"]]
            out, k = [], 0
            while first + k * 60 / bpm <= r["song_out"]:
                s = first + k * 60 / bpm
                k += 1
                if s >= r["song_in"]:
                    out.append(r["mix_start"] + (s - r["song_in"]) / r["rate"])
            return out
        ba, bb = beats(a), beats(b)
        end = a["mix_start"] + a["dur"]
        worst = max(min(abs(x - y) for y in ba) for x in bb if b["mix_start"] <= x <= end)
        assert worst < 0.012, "beats off by %.1f ms in %s -> %s" % (worst * 1000, a["title"], b["title"])


def call(port, path, data=None):
    req = urllib.request.Request("http://localhost:%d%s" % (port, path), method="POST" if data is not None else "GET",
                                 data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def server_checks(tmp, folder):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    home = tmp / "home"
    collection(home, folder)
    env = dict(os.environ, GOODMIXX_PORT=str(port), GOODMIXX_DATA=str(tmp / "data"), HOME=str(home),
               DJAY_LIBRARY=str(tmp / "none.db"), GOODMIXX_OUT=str(tmp / "out"))
    proc = subprocess.Popen([sys.executable, "mixes_server.py"], cwd=ROOT / "app", env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                call(port, "/api/info")
                break
            except OSError:
                time.sleep(0.25)
        for i, (title, bpm, _, _) in enumerate(TRACKS):         # play the set in "Traktor"
            deck = "AB"[i % 2]
            call(port, "/traktor/deckLoaded/" + deck, {"title": title, "artist": "Test", "bpm": bpm, "isPlaying": True})
            time.sleep(0.05)
        info = call(port, "/api/studio/info")
        assert "mixes" in info and info["ffmpeg"] == bool(studio.ffmpeg())
        sets = call(port, "/api/studio/sets")["sets"]
        assert sets and [s["title"] for s in sets[0]["songs"]] == [t[0] for t in TRACKS], sets
        mix = {"name": "Test Set", "blend": "beat", "items": sets[0]["songs"]}
        saved = call(port, "/api/studio/save", {"mix": mix})
        assert saved["mix"]["id"] and len(saved["mixes"]) == 1
        p = call(port, "/api/studio/plan", {"mix": mix})
        assert p["playable"] == 3, p["warnings"]
        assert [r["blend_used"] for r in p["items"]] == ["", "beat", "beat"], p["items"]
        wave = call(port, "/api/studio/wave?p=" + urllib.parse.quote(p["items"][0]["path"]))
        assert wave["rate"] == 10 and len(wave["peaks"]) > 900 and max(wave["peaks"]) == 255
        pv = call(port, "/api/studio/preview", {"mix": mix, "index": 1})
        assert pv.get("url") and pv["blend_used"] == "beat", pv
        req = urllib.request.Request("http://localhost:%d%s" % (port, pv["url"]), headers={"Range": "bytes=0-99"})
        with urllib.request.urlopen(req, timeout=10) as r:      # Safari / the Mac app need byte ranges to play audio
            assert r.status == 206 and r.headers["Content-Range"].startswith("bytes 0-99/") and len(r.read()) == 100
        ex = call(port, "/api/studio/export", {"mix": mix})
        assert Path(ex["playlist"]).read_text().count(str(folder)) == 3 and Path(ex["tracklist"]).exists()
        st = call(port, "/api/studio/render", {"mix": mix, "format": "mp3"})
        for _ in range(240):
            if st.get("state") not in ("rendering", "planning"):
                break
            time.sleep(0.25)
            st = call(port, "/api/studio/render")
        assert st["state"] == "done", st
        assert abs(studio.duration(st["out"]) - st["total"]) < 1.5 and Path(st["tracklist"]).exists()
        with urllib.request.urlopen("http://localhost:%d/api/studio/audio?p=%s" % (port, urllib.parse.quote(st["out"])),
                                    timeout=10) as r:
            assert r.status == 200 and r.headers["Content-Type"] == "audio/mpeg"
        call(port, "/api/studio/delete", {"id": saved["mix"]["id"]})
        assert call(port, "/api/studio/info")["mixes"] == []
    finally:
        proc.terminate()
        proc.wait(5)


def main():
    if not studio.ffmpeg():
        print("studio test skipped (no ffmpeg)")
        return
    tmp = Path(tempfile.mkdtemp())
    try:
        folder = tmp / "music"
        folder.mkdir()
        make_tracks(folder)
        planner_checks(folder)
        server_checks(tmp, folder)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("studio test passed")


if __name__ == "__main__":
    main()
