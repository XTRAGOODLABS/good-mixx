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


def cue_checks(folder):
    """Set timing from djay: start from cue 1 unless it's an intro, place songs at djay's start times,
    flag quick skips, fall back when djay's times don't fit."""
    intro = folder / "Intro.mp3"
    expr = ("0.3*sin(2*PI*220*t)*lt(t,10)+gte(t,10)*0.8*sin(2*PI*55*mod(t-10,60/119))*exp(-mod(t-10,60/119)*22)")
    subprocess.run([studio.ffmpeg(), "-v", "quiet", "-y", "-f", "lavfi", "-i", "aevalsrc='%s':s=44100:d=100" % expr,
                    "-ac", "2", str(intro)], check=True)
    f = {t: str(folder / (t + ".mp3")) for t, _, _, _ in TRACKS}
    items = [
        {"title": "Alpha", "path": f["Alpha"], "bpm": 120, "set_start": 1000, "cues": [{"n": 1, "t": 0.3}]},
        {"title": "Intro", "path": str(intro), "bpm": 119, "set_start": 1060, "cues": [{"n": 1, "t": 0.0}, {"n": 2, "t": 10.0}]},
        {"title": "Bravo", "path": f["Bravo"], "bpm": 123, "set_start": 1130, "cues": [{"n": 1, "t": 0.71}]},
        {"title": "Charlie", "path": f["Charlie"], "bpm": 121, "set_start": 1138, "cues": [{"n": 1, "t": 2.1}]},
        {"title": "Alpha", "path": f["Alpha"], "bpm": 120, "set_start": 1900, "cues": [{"n": 1, "t": 0.3}]},
    ]
    p = studio.plan({"blend": "set", "bars": 16, "items": items})
    r = p["items"]
    assert r[1]["start_from"].startswith("cue 2") and abs(r[1]["song_in"] - 10.0) < 0.05, r[1]          # skipped the intro
    assert abs(r[1]["mix_start"] - 60.0) < 0.6 and r[1]["blend_used"] == "set" and r[1].get("beat_locked")
    assert r[2].get("quick") and r[3]["blend_used"] == "beat"                                       # 8 s play = skip
    assert "ended" in r[4].get("warn", "") and r[4]["blend_used"] == "beat"                         # djay's time didn't fit
    truth = {"Alpha": (120, .30), "Intro": (119, 10.0), "Bravo": (123, .71), "Charlie": (121, 2.10)}
    check_beats(p, truth)
    pick = studio.plan({"blend": "set", "items": [dict(items[0]), dict(items[1], start_cue=0)]})
    assert pick["items"][1]["start_from"] == "beginning"


def fx_checks(folder):
    """Blend effects really filter the sound, only inside the blend; per-blend length works."""
    noise = folder / "noise.mp3"
    subprocess.run([studio.ffmpeg(), "-v", "quiet", "-y", "-f", "lavfi", "-i", "anoisesrc=d=60:c=pink:a=0.3", "-ac", "2",
                    str(noise)], check=True)

    def level(f, t, af):
        o = subprocess.run([studio.ffmpeg(), "-hide_banner", "-ss", str(t), "-t", "3", "-i", str(f), "-af", af + ",volumedetect",
                            "-f", "null", "-"], capture_output=True, text=True).stderr
        return float(o.split("mean_volume:")[1].split("dB")[0])
    for kind, side, band, drop in (("lp_out", "fx_out", "highpass=f=3000", True), ("hp_out", "fx_out", "lowpass=f=120", True),
                                   ("hp_in", "fx_in", "lowpass=f=120", False)):
        r = {"path": str(noise), "song_in": 0, "song_out": 60, "rate": 1.0, "dur": 60, "mix_start": 0, "fade_in": 0, "fade_out": 0,
             side: {"kind": kind, "t0": 20, "t1": 40}}
        out = folder / ("fx_%s.wav" % kind)
        cmd = [c for c in studio.ffmpeg_command({"items": [r], "total": 60}, out, "wav") if c not in ("-progress", "pipe:1")]
        subprocess.run(cmd, check=True, capture_output=True)
        before, after = level(out, 8, band), level(out, 45, band)
        assert (after < before - 20) if drop else (before < after - 20), (kind, before, after)
    f = {t: str(folder / (t + ".mp3")) for t, _, _, _ in TRACKS}
    mix = {"blend": "beat", "bars": 16, "items": [{"title": "Alpha", "path": f["Alpha"], "bpm": 120},
                                                 {"title": "Bravo", "path": f["Bravo"], "bpm": 123, "bars": 4, "fx": "bass_swap"}]}
    p = studio.plan(mix)
    a, b = p["items"]
    assert b["bars_used"] == 4 and abs(b["fade_in"] - 4 * 4 * 60 / 120) < 0.01, b
    assert a["fx_out"]["kind"] == b["fx_in"]["kind"] == "bass_swap"
    clip = studio.preview(p, 1, str(folder / "fxpreview.mp3"))
    assert studio.duration(clip["path"]) > 10
    # each song's fades and tail are its own: changing one never moves or reshapes the other
    base = {"blend": "beat", "bars": 16, "items": [{"title": "Alpha", "path": f["Alpha"], "bpm": 120},
                                                  {"title": "Bravo", "path": f["Bravo"], "bpm": 123}]}
    a0, b0 = studio.plan(base)["items"]
    a1, b1 = studio.plan(dict(base, items=[base["items"][0], dict(base["items"][1], fade_in_len=6.0)]))["items"]
    assert b1["fade_in"] == 6.0 and a1["fade_out"] == a0["fade_out"] and a1["dur"] == a0["dur"]
    a2, b2 = studio.plan(dict(base, items=[dict(base["items"][0], fade_out_len=5.0), base["items"][1]]))["items"]
    assert a2["fade_out"] == 5.0 and b2["fade_in"] == b0["fade_in"] and b2["mix_start"] == b0["mix_start"]
    a3, b3 = studio.plan(dict(base, items=[base["items"][0], dict(base["items"][1], tail=40.0)]))["items"]
    assert b3["mix_start"] == b0["mix_start"] and abs(a3["mix_start"] + a3["dur"] - (b0["mix_start"] + 40)) < 0.01


def check_beats(p, truth):
    for a, b in zip(p["items"], p["items"][1:]):
        assert b.get("beat_locked"), b

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
        cue_checks(folder)
        fx_checks(folder)
        server_checks(tmp, folder)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("studio test passed")


if __name__ == "__main__":
    main()
