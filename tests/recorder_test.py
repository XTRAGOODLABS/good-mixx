"""Set recorder check: a made-up recorder log -> segments (start, song position, tempo, fader/crossfader/filter
moves, split-second stops joined) -> an "As recorded" rebuild with beats lined up and the moves replayed ->
the server matching recordings to a past set. Needs ffmpeg for the audio parts. Run: python3 tests/recorder_test.py"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import recorder  # noqa: E402
import studio  # noqa: E402


def write_log(path, unix0, songs, screen=True, loop=None):
    """songs: (deck, title, bpm, start_t, stop_t, start_pos, length, tempo%) -> a recorder log like gm-recorder.mjs writes.
    Like djay: progress k of 128 is rounded UP and sent every ~2.5 s; screen=False = djay's screen couldn't be read.
    loop=(deck, from_t, to_t, loop_secs): that deck jumps back every loop_secs between from_t and to_t."""
    ev = [{"t": 0, "k": "start", "unix": unix0, "version": "5.6.10"},
          {"t": 0.1, "k": "m", "p": "mixer.masterCrossfade", "v": 0.0}]
    for deck, title, bpm, t0, t1, pos0, length, tempo in songs:
        rate = 1 + tempo / 100.0
        ev.append({"t": t0, "k": "m", "p": "turntable%d.isPlaying" % deck, "v": 1})
        def pos_at(t):
            if loop and loop[0] == deck and loop[1] <= t < loop[2]:
                return pos0 + (loop[1] - t0) * rate - loop[3] * rate + ((t - loop[1]) % loop[3]) * rate
            if loop and loop[0] == deck and t >= loop[2]:
                return pos0 + (loop[1] - t0) * rate - loop[3] * rate + ((loop[2] - loop[1]) % loop[3]) * rate + (t - loop[2]) * rate
            return pos0 + (t - t0) * rate
        t = t0 + 0.05
        while t < t1:                                   # djay's clock on screen every 3 s, whole seconds
            pos = pos_at(t)
            ev.append({"t": round(t, 3), "k": "d", "decks": [{"n": deck, "title": title, "artist": "Test", "bpm": bpm,
                                                            "time": "-%d:%02d" % divmod(int(length - pos + 0.999), 60),
                                                            "rem": True, "tempo": tempo}] if screen else []})
            t += 3
        t, last = t0 + 0.3, None                         # progress: rounded up, sent every ~2.5 s
        while t < t1:
            k = min(127, max(1, int(-(-pos_at(t) * 128 // length))))
            if k != last:
                ev.append({"t": round(t, 3), "k": "m", "p": "turntable%d.display.songProgress" % deck,
                           "v": k / 128 if k <= 64 else 0.5 + (k - 64) / 126})
                last = k
            t += 2.5 if not (loop and loop[0] == deck and loop[1] <= t < loop[2] + 3) else 0.5
        ev.append({"t": t1, "k": "m", "p": "turntable%d.isPlaying" % deck, "v": 0})
    return ev


def finish(path, ev, extra=()):
    ev = sorted(ev + list(extra), key=lambda e: (e["t"], e["k"] != "start"))
    ev.append({"t": ev[-1]["t"] + 1, "k": "end"})
    Path(path).write_text("\n".join(json.dumps(e) for e in ev) + "\n")


def parse_checks(tmp):
    log = tmp / "rec-20261118-200000.jsonl"
    ev = write_log(log, 1000.0, [(1, "Alpha", 120, 2.0, 95.0, 10.0, 100.0, 0.0),
                                 (2, "Bravo", 123, 62.0, 99.0, 5.0, 100.0, -2.44)])
    moves = [{"t": 70.0, "k": "m", "p": "mixer.masterCrossfade", "v": 0.5},      # both full
             {"t": 80.0, "k": "m", "p": "mixer.masterCrossfade", "v": 1.0},      # deck 1 out
             {"t": 75.0, "k": "m", "p": "turntable1.effects.filter.currentValue", "v": 0.2},
             {"t": 40.0, "k": "m", "p": "turntable1.isPlaying", "v": 0},          # controller hiccup
             {"t": 40.4, "k": "m", "p": "turntable1.isPlaying", "v": 1}]
    finish(log, ev, moves)
    segs = recorder.parse(log)
    assert [s["title"] for s in segs] == ["Alpha", "Bravo"], [(s["title"], s["t0"]) for s in segs]   # hiccup joined
    a, b = segs
    assert abs(a["unix"] - 1002.0) < 0.01 and abs(b["rate"] - 0.9756) < 0.001
    pa, pb = recorder.start_position(a, 100.0), recorder.start_position(b, 100.0)
    assert abs(pa - 10.0) < 0.5 and abs(pb - 5.0) < 0.5, (pa, pb)
    def gain(seg, t):
        g = None
        for p in seg["auto"]:
            if p[0] <= t:
                g = p[1]
        return g
    assert gain(a, 1) == 1.0 and gain(a, 70) == 1.0 and gain(a, 79) == 0.0, a["auto"]   # crossfader moves, deck 1
    assert gain(b, 1) == 0.0 and gain(b, 9) == 1.0, b["auto"]                         # and deck 2
    assert any(p[2] == 0.2 for p in a["auto"])                                  # filter move
    # djay's screen couldn't be read + a 2-bar loop on deck 2: still one play, loop found, start points right
    log2 = tmp / "rec-20261118-220000.jsonl"
    ev = write_log(log2, 5000.0, [(1, "Alpha", 120, 1.0, 120.0, 0.0, 200.0, 0.0),
                                  (2, "Bravo", 120, 40.0, 150.0, 8.0, 200.0, 0.0)],
                   screen=False, loop=(2, 44.0, 80.0, 4.0))
    finish(log2, ev, [{"t": 40.0, "k": "m", "p": "mixer.masterCrossfade", "v": 0.5}])
    segs = recorder.parse(log2)
    two = [x for x in segs if x["deck"] == 2]
    assert len(two) == 1 and not two[0]["title"] and len(two[0]["pieces"]) >= 8, [(x["t0"], x["t1"]) for x in segs]
    pcs = recorder.play_pieces(two[0], 200.0, 1.0, 120.0)
    assert abs(pcs[1][1] - 4.0) < 0.01 and abs(pcs[1][0] - 8.0) < 0.6, pcs[:3]           # loop: 4 s from ~8 s in
    r = recorder.Recorder(tmp)
    r.dir = tmp
    ref = r.match("Bravo", "Test", 5000.0 + 60.0, deck=2)                     # no name from the screen: deck + time
    assert ref and r.segment(ref)["deck"] == 2 and not r.match("Bravo", "Test", 5000.0 + 60.0, deck=3)
    return log


def plan_checks(folder):
    def track(name, bpm, first, secs):
        expr = ("0.8*gte(t,{f})*sin(2*PI*55*mod(t-{f},60/{b}))*exp(-mod(t-{f},60/{b})*22)+0.2*sin(2*PI*3000*t)"
                .format(f=first, b=bpm))
        subprocess.run([studio.ffmpeg(), "-v", "quiet", "-y", "-f", "lavfi", "-i", "aevalsrc='%s':s=44100:d=%d" % (expr, secs),
                        "-ac", "2", str(folder / name)], check=True)
    track("A.mp3", 120, 0.30, 130)
    track("B.mp3", 123, 0.71, 100)
    A = {"unix": 1000.0, "t0": 0, "t1": 95, "rate": 1.0, "title": "A", "deck": 1, "prog": [],
         "clock": [[0.2, 10.2 - 0.5, False], [3.2, 13.2 - 0.5, False]],
         "auto": [[0, 1.0, .5, .5, .5, .5], [70, 0.5, .5, .5, .5, .5], [75, 0.4, .2, .5, .5, .5], [80, 0.0, .1, .5, .5, .5]]}
    B = {"unix": 1060.17, "t0": 0, "t1": 60, "rate": 120 / 123.0, "title": "B", "deck": 2, "prog": [],
         "clock": [[0.1, 5.0 + 0.1 * 120 / 123 - 0.5, False]], "auto": [[0, 0.0, .5, .5, .5, .5], [8, 1.0, .5, .5, .5, .5]]}
    items = [{"title": "A", "path": str(folder / "A.mp3"), "bpm": 120, "seg": A},
             {"title": "B", "path": str(folder / "B.mp3"), "bpm": 123, "seg": B}]
    p = studio.plan({"blend": "rec", "items": items})
    a, b = p["items"]
    assert a["blend_used"] == b["blend_used"] == "rec" and abs(a["song_in"] - 10.0) < 0.05
    assert abs(b["mix_start"] - 60.17) < 0.35 and b.get("beat_locked"), b
    T = 60 / 120.0
    worst = 0
    for k in range(200):                              # B's beats land on A's beats while both play
        sb = 0.71 + k * 60 / 123.0
        if sb < b["song_in"] or sb > b["song_out"]:
            continue
        mb = b["mix_start"] + (sb - b["song_in"]) / b["rate"]
        if mb > a["mix_start"] + a["dur"]:
            break
        sa = a["song_in"] + (mb - a["mix_start"])
        worst = max(worst, abs(((sa - 0.30) / T) - round((sa - 0.30) / T)) * T)
    assert worst < 0.012, worst
    solo = studio.plan({"blend": "rec", "items": items[:1]})
    out = folder / "A-moves.wav"
    tmp = tempfile.mkdtemp()
    cmd = [c for c in studio.ffmpeg_command(solo, out, "wav", tmpdir=tmp) if c not in ("-progress", "pipe:1")]
    subprocess.run(cmd, check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)

    def level(t, af="anull"):
        o = subprocess.run([studio.ffmpeg(), "-hide_banner", "-ss", str(t), "-t", "2", "-i", str(out), "-af",
                            af + ",volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
        return float(o.split("mean_volume:")[1].split("dB")[0])
    full, half, gone = level(30), level(72), level(85)
    assert half < full - 5 and gone < full - 40, (full, half, gone)                # fader moves replayed
    assert level(77, "highpass=f=2000") < level(30, "highpass=f=2000") - 15          # filter move replayed
    clip = studio.preview(p, 1, str(folder / "rec-preview.mp3"))
    assert studio.duration(clip["path"]) > 10


def call(port, path, data=None):
    req = urllib.request.Request("http://localhost:%d%s" % (port, path), method="POST" if data is not None else "GET",
                                 data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def server_checks(tmp):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    data = tmp / "data"
    (data / "recordings").mkdir(parents=True)
    env = dict(os.environ, GOODMIXX_PORT=str(port), GOODMIXX_DATA=str(data), HOME=str(tmp / "home"),
               DJAY_LIBRARY=str(tmp / "none.db"), GOODMIXX_OUT=str(tmp / "out"), DJAY_MCP_DIR=str(tmp / "no-mcp"))
    proc = subprocess.Popen([sys.executable, "mixes_server.py"], cwd=ROOT / "app", env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                st = call(port, "/api/recorder")
                break
            except OSError:
                time.sleep(0.25)
        assert st["installed"] is False and "recording" in st
        assert call(port, "/api/recorder", {"enabled": False})["enabled"] is False
        now = time.time()
        for i, title in enumerate(("Alpha", "Bravo")):          # the set, as Traktor / djay history logs it
            call(port, "/traktor/deckLoaded/" + "AB"[i], {"title": title, "artist": "Test", "bpm": 120, "isPlaying": True})
            time.sleep(0.05)
        log = data / "recordings" / "rec-20261118-210000.jsonl"
        ev = write_log(log, now - 5, [(1, "Alpha", 120, 5.0, 60.0, 0.0, 100.0, 0.0), (2, "Bravo", 120, 5.05, 50.0, 0.0, 100.0, 0.0)])
        finish(log, ev)
        sets = call(port, "/api/studio/sets")["sets"]
        assert sets[0]["recorded"] == 2 and all(x.get("rec") for x in sets[0]["songs"]), sets[0]
        p = call(port, "/api/studio/plan", {"mix": {"name": "t", "blend": "rec", "items": sets[0]["songs"]}, "analyze": False})
        assert [r["blend_used"] for r in p["items"]] == ["rec", "rec"] and p["items"][0].get("auto"), p["items"]
    finally:
        proc.terminate()
        proc.wait(5)


def main():
    tmp = Path(tempfile.mkdtemp())
    try:
        parse_checks(tmp)
        server_checks(tmp)
        if studio.ffmpeg():
            folder = tmp / "music"
            folder.mkdir()
            plan_checks(folder)
        else:
            print("audio parts skipped (no ffmpeg)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("recorder test passed")


if __name__ == "__main__":
    main()
