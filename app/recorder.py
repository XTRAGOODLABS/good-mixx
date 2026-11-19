"""Set recorder: runs gm-recorder.mjs next to djay Pro and turns its logs into "segments" - one per stretch of
a song playing on a deck - with everything a rebuild needs: when it started, where in the song, the tempo,
and how loud it was (fader x crossfader), plus filter and EQ moves.

Needs djay-pro-mcp (github.com/ckryptickunal/djay-pro-mcp, MIT) installed - GOOD MIXX can set it up - and
Node.js 22.13+. Recording only reads djay.
"""
import json, os, re, shutil, subprocess, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "gm-recorder.mjs"
MCP_REPO = "https://github.com/ckryptickunal/djay-pro-mcp.git"
MCP_COMMIT = "d392a57d8ac39137345625d5c69ea505cbbb930d"      # the version that was read through and tested
LEFT, RIGHT = (1, 3), (2, 4)                                   # djay's crossfader sides


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\((feat|ft|with)[^)]*\)|\bfeat\.?.*$|\bft\.?.*$", "", s)
    s = re.sub(r"\(.*?(edit|version|remaster|clean|radio|explicit|dirty).*?\)|\[.*?\]", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def find_node():
    for p in ("/opt/homebrew/bin/node", "/usr/local/bin/node", shutil.which("node") or ""):
        if p and os.access(p, os.X_OK):
            try:
                v = subprocess.run([p, "-p", "process.versions.node"], capture_output=True, text=True, timeout=10).stdout.strip()
                a, b = (int(x) for x in v.split(".")[:2])
                return p, v, (a > 22 or (a == 22 and b >= 13))
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
    return "", "", False


class Recorder:
    def __init__(self, data_dir):
        self.data = Path(data_dir)
        self.dir = self.data / "recordings"
        self.mcp = Path(os.environ.get("DJAY_MCP_DIR") or Path.home() / "djay-pro-mcp")
        self.settings = self.data / "recorder.json"
        self.lock = threading.Lock()
        self.proc = None
        self.file = None
        self.setup_msg = ""
        self.setup_busy = False
        self.error = ""
        self._segs = {}
        self._thread = None

    # ---------------------------------------------------------------- status / settings
    def enabled(self):
        try:
            return bool(json.loads(self.settings.read_text()).get("enabled", True))
        except (OSError, ValueError):
            return True

    def set_enabled(self, on):
        self.data.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps({"enabled": bool(on)}))
        if not on:
            self.stop()

    def installed(self):
        return (self.mcp / "dist" / "djay.js").is_file() and (self.mcp / "bin" / "djay-midi-bridge").is_file()

    @staticmethod
    def djay_running():
        try:
            return subprocess.run(["/usr/bin/pgrep", "-x", "djay Pro"], capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def screen_ok(self):
        """False when the recorder is running but can't read djay's screen (song names, clock, tempo)."""
        if not (self.file and self.file.exists()):
            return None
        try:
            with open(self.file, "rb") as fh:
                fh.seek(max(0, self.file.stat().st_size - 20000))
                tail = fh.read().decode("utf-8", "replace").splitlines()[1:]
        except OSError:
            return None
        reads = [l for l in tail if '"k": "d"' in l or '"k":"d"' in l]
        if len(reads) < 4:
            return None
        return any('"title"' in l for l in reads[-6:])

    SCREEN_TEXT = {
        "ok": "Reading djay's screen fine.",
        "no-access": "macOS is blocking GOOD MIXX from reading djay's screen. In System Settings > Privacy & Security > "
                     "Accessibility, select GOOD MIXX, click minus to remove it, click plus and add it again, "
                     "then quit and reopen GOOD MIXX.",
        "djay-closed": "djay Pro isn't open.",
        "no-window": "djay is open but its main window can't be found. Make sure djay's window is open (not minimized).",
        "djay-hidden": "djay is hidden. Show djay's window (click its icon in the Dock).",
        "no-decks": "GOOD MIXX can see djay's window but not the deck info. Try djay's normal 2-deck or 4-deck view "
                    "(not full-screen library or a special mode).",
    }

    def screen_reason(self):
        """The latest reason (from the recorder log) that djay's screen could or couldn't be read."""
        f = self.file
        if not (f and f.exists()):
            return None
        if getattr(self, "_ax_file", None) != f:
            self._ax_file, self._ax_pos, self._ax_reason = f, 0, None
        try:
            with open(f, "rb") as fh:
                fh.seek(self._ax_pos)
                data = fh.read()
        except OSError:
            return self._ax_reason
        cut = data.rfind(b"\n") + 1
        self._ax_pos += cut
        for line in data[:cut].splitlines():
            if b'"k":"ax"' in line or b'"k": "ax"' in line:
                try:
                    self._ax_reason = json.loads(line).get("reason")
                except ValueError:
                    pass
        return self._ax_reason

    def screen_text(self, reason):
        if not reason:
            return ""
        return self.SCREEN_TEXT.get(reason, "djay's screen couldn't be read (" + reason + ").")

    def status(self):
        node, ver, ok = find_node()
        rec = bool(self.proc and self.proc.poll() is None)
        reason = self.screen_reason() if rec else None
        return {"installed": self.installed(), "node": ver, "node_ok": ok, "enabled": self.enabled(),
                "recording": bool(self.proc and self.proc.poll() is None), "file": self.file.name if self.file else "",
                "djay": self.djay_running() if os.path.exists("/usr/bin/pgrep") else False,
                "setup_busy": self.setup_busy, "setup_msg": self.setup_msg, "error": self.error,
                "screen_ok": (reason == "ok") if reason else (self.screen_ok() if rec else None),
                "screen_reason": reason or "", "screen_text": self.screen_text(reason),
                "recordings": len(list(self.dir.glob("*.jsonl"))) if self.dir.exists() else 0}

    # ---------------------------------------------------------------- running
    def start_watching(self):
        """Record whenever djay is open (and recording is on); stop when djay closes."""
        if self._thread:
            return
        def loop():
            while True:
                try:
                    want = self.enabled() and self.installed() and self.djay_running()
                    running = self.proc and self.proc.poll() is None
                    if want and not running:
                        self.start()
                    elif not want and running:
                        self.stop()
                except Exception as e:
                    self.error = str(e)[:200]
                time.sleep(5)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def start(self):
        node, _, ok = find_node()
        if not ok:
            self.error = "Recording needs Node.js 22.13 or newer."
            return
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
            self.dir.mkdir(parents=True, exist_ok=True)
            self.file = self.dir / time.strftime("rec-%Y%m%d-%H%M%S.jsonl")
            errlog = open(self.dir / "recorder-errors.log", "a")
            self.proc = subprocess.Popen([node, "--disable-warning=ExperimentalWarning", str(SCRIPT), str(self.mcp),
                                          str(self.file), "3"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                         stderr=errlog)
            self.error = ""

    def stop(self):
        with self.lock:
            p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()

    # ---------------------------------------------------------------- setup (no Terminal needed)
    def setup(self):
        if self.setup_busy:
            return
        self.setup_busy = True
        threading.Thread(target=self._setup, daemon=True).start()

    def _setup(self):
        def step(msg, cmd, cwd=None, timeout=900):
            self.setup_msg = msg
            env = dict(os.environ, PATH=os.path.dirname(node) + ":" + os.environ.get("PATH", "/usr/bin:/bin"))
            r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
            if r.returncode != 0:
                raise RuntimeError("%s failed: %s" % (msg, ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1][:200]))
        try:
            node, ver, ok = find_node()
            if not ok:
                raise RuntimeError("Needs Node.js 22.13 or newer%s. With Homebrew: brew install node"
                                   % (" (found %s)" % ver if ver else ""))
            npm = os.path.join(os.path.dirname(node), "npm")
            if not (self.mcp / ".git").exists():
                step("Downloading djay-pro-mcp…", ["git", "clone", "-q", MCP_REPO, str(self.mcp)])
            step("Getting the tested version…", ["git", "fetch", "-q", "origin"], cwd=self.mcp)
            step("Getting the tested version…", ["git", "checkout", "-q", MCP_COMMIT], cwd=self.mcp)
            step("Installing (about a minute)…", [npm, "install", "--silent", "--no-fund", "--no-audit"], cwd=self.mcp)
            step("Building…", [npm, "run", "-s", "build"], cwd=self.mcp)
            step("Adding the controller settings to djay…", [npm, "run", "-s", "setup"], cwd=self.mcp)
            self.setup_msg = "Done. Quit djay and open it again - it picks up the new settings when it starts."
        except Exception as e:
            self.setup_msg = "Setup stopped: %s" % e
        finally:
            self.setup_busy = False

    # ---------------------------------------------------------------- reading recordings
    def files(self):
        return sorted(self.dir.glob("rec-*.jsonl")) if self.dir.exists() else []

    def segments(self, f):
        """Every stretch of a song playing on a deck in one log (cached until the file changes)."""
        f = Path(f)
        try:
            stamp = f.stat().st_mtime
        except OSError:
            return []
        hit = self._segs.get(str(f))
        if hit and hit[0] == stamp:
            return hit[1]
        segs = parse(f)
        self._segs[str(f)] = (stamp, segs)
        return segs

    def segment(self, ref):
        """A segment by its reference "file name|index"."""
        try:
            name, idx = ref.rsplit("|", 1)
            segs = self.segments(self.dir / os.path.basename(name))
            return segs[int(idx)]
        except (ValueError, IndexError, OSError):
            return None

    def match(self, title, artist, start_unix, deck=None, window=90):
        """The recorded segment for a song djay logged at start_unix. djay logs a song when it's brought in, so the
        stretch of play that contains that moment wins. Songs with no name from the screen match by deck + time."""
        want = norm(title)
        best, best_score = None, -1e9
        for f in self.files():
            for i, s in enumerate(self.segments(f)):
                end = s["unix"] + (s["t1"] - s["t0"])
                if s.get("title"):
                    if norm(s["title"]) != want or not (s["unix"] - window <= start_unix <= end + window):
                        continue
                elif deck is None or s["deck"] != deck or not (s["unix"] - 10 <= start_unix <= end + 5):
                    continue
                inside = s["unix"] - 2 <= start_unix <= end + 2
                score = (1000 if inside else 0) + s["audible"] - abs(s["unix"] - start_unix) / 100.0
                if score > best_score:
                    best, best_score = "%s|%d" % (f.name, i), score
        return best


def _gain(chan, xf, deck):
    """How loud a deck is: channel fader (audio taper) x crossfader side (both full in the middle)."""
    v = (chan if chan is not None else 1.0) ** 2
    x = 0.5 if xf is None else xf
    side = min(1.0, 2 * (1 - x)) if deck in LEFT else min(1.0, 2 * x) if deck in RIGHT else 1.0
    return round(v * side, 4)


def parse(path):
    """Turn a recorder log into segments."""
    try:
        lines = [json.loads(l) for l in open(path) if l.strip()]
    except (OSError, ValueError):
        return []
    if not lines or lines[0].get("k") != "start":
        return []
    unix0 = lines[0]["unix"]
    st = {n: {"playing": False, "title": None, "artist": None, "bpm": None, "key": None, "tempo": None, "knob": 0.5,
              "chan": 1.0,
              "filter": 0.5, "low": 0.5, "mid": 0.5, "high": 0.5} for n in (1, 2, 3, 4)}
    xf = [0.5]
    open_seg = {}
    segs = []
    end_t = lines[-1]["t"]

    def auto_point(n, t):
        s, d = open_seg.get(n), st[n]
        if not s:
            return
        p = [round(t - s["t0"], 3), _gain(d["chan"], xf[0], n), d["filter"], d["low"], d["mid"], d["high"]]
        if not s["auto"] or s["auto"][-1][1:] != p[1:]:
            s["auto"].append(p)

    def close(n, t):
        s = open_seg.pop(n, None)
        if not s:
            return
        s["t1"] = t
        aud, prev = 0.0, None
        for p in s["auto"] + [[t - s["t0"]] + (s["auto"][-1][1:] if s["auto"] else [1, .5, .5, .5, .5])]:
            if prev is not None and prev[1] > 0.05:
                aud += p[0] - prev[0]
            prev = p
        s["audible"] = round(aud, 2)
        tempos = [x for x in s.pop("tempos") if x is not None]
        tempos.sort()
        s["tempo_known"] = bool(tempos)
        s["rate"] = round(1 + (tempos[len(tempos) // 2] if tempos else 0) / 100.0, 5)
        s["knob"] = st[n]["knob"]
        if s["t1"] - s["t0"] > 1.0:                  # no title from the screen? djay's history names it later
            segs.append(s)

    def open_(n, t):
        d = st[n]
        open_seg[n] = {"deck": n, "t0": t, "unix": round(unix0 + t, 3), "title": d["title"], "artist": d["artist"],
                       "bpm": d["bpm"], "key": d["key"], "prog": [], "clock": [], "auto": [], "tempos": [d["tempo"]]}
        auto_point(n, t)

    for e in lines[1:]:
        t, k = e["t"], e.get("k")
        if k == "m":
            m = re.match(r"(turntable(\d)|mixer)\.(.*)$", e["p"])
            if not m:
                continue
            v = e["v"]
            if m.group(1) == "mixer":
                if m.group(3) == "masterCrossfade":
                    xf[0] = v
                    for n in list(open_seg):
                        auto_point(n, t)
                else:
                    c = re.match(r"volumeEffectChannel(\d)\.", m.group(3))
                    if c:
                        n = int(c.group(1))
                        st[n]["chan"] = v
                        auto_point(n, t)
                continue
            n, what = int(m.group(2)), m.group(3)
            d = st[n]
            if what == "isPlaying":
                if v > 0.5 and not d["playing"]:
                    d["playing"] = True
                    open_(n, t)
                elif v <= 0.5 and d["playing"]:
                    d["playing"] = False
                    close(n, t)
            elif what == "display.songProgress":
                raw = int(round(v * 128)) if v <= 0.5 else int(round((v - 0.5) * 126 + 64))
                s0 = open_seg.get(n)
                if s0 and s0["prog"] and raw < s0["prog"][-1][1] - 1:
                    new_song = s0["prog"][-1][1] >= 125 and raw <= 2   # ran to the end, then back to 0: next song
                    close(n, t)                        # jumped back (cue / restart / loop): a new start from here
                    if new_song:
                        d["title"] = None
                    open_(n, t)
                    open_seg[n]["jump"] = not new_song
                    s0 = open_seg[n]
                if s0:
                    s0["prog"].append([round(t - s0["t0"], 3), raw])
            elif what == "effects.tempo.currentValue":
                d["knob"] = v
            elif what == "song.loadingSuccess":
                close(n, t)
                if d["playing"]:
                    d["title"] = None
            else:
                key = {"effects.filter.currentValue": "filter", "lowEQEffect.currentValue": "low",
                       "midEQEffect.currentValue": "mid", "highEQEffect.currentValue": "high"}.get(what)
                if key:
                    d[key] = v
                    auto_point(n, t)
        elif k == "d":
            for x in e.get("decks") or []:
                n = x.get("n")
                if n not in st:
                    continue
                d = st[n]
                if x.get("title") and d["playing"] and n in open_seg and open_seg[n]["title"] and \
                        norm(x["title"]) != norm(open_seg[n]["title"]):
                    close(n, t)                        # a new song while playing: split
                    open_(n, t)
                for f in ("title", "artist", "bpm", "key"):
                    if x.get(f):
                        d[f] = x[f]
                if isinstance(x.get("tempo"), (int, float)):
                    d["tempo"] = x["tempo"]
                s = open_seg.get(n)
                if s:
                    for f in ("title", "artist", "bpm", "key"):
                        if not s.get(f) and d.get(f):
                            s[f] = d[f]
                    s["tempos"].append(d["tempo"])
                    secs = _clock(x.get("time"))
                    if secs is not None:
                        s["clock"].append([round(t - s["t0"], 3), secs, bool(x.get("rem"))])
    for n in list(open_seg):
        close(n, end_t)
    return _chain(_merge_blips(sorted(segs, key=lambda s: s["t0"])))


def _chain(segs, gap=0.6):
    """Back-to-back pieces on one deck where the song jumped back (a loop, or a cue jump while playing) become one
    play with "pieces", so a rebuild can replay the loop."""
    out = []
    for s in segs:
        prev = next((p for p in reversed(out) if p["deck"] == s["deck"]), None)
        if prev and s.get("jump") and 0 <= s["t0"] - prev["t1"] < gap and \
                (not s.get("title") or not prev.get("title") or norm(s["title"]) == norm(prev["title"])):
            if "pieces" not in prev:
                prev["pieces"] = [{"t": 0.0, "prog": prev["prog"], "clock": prev["clock"], "jump": bool(prev.get("jump"))}]
            off = s["t0"] - prev["t0"]
            prev["pieces"].append({"t": off, "prog": s["prog"], "clock": s["clock"], "jump": True})
            prev["auto"] += [[p[0] + off] + p[1:] for p in s["auto"]]
            prev["t1"] = s["t1"]
            prev["audible"] = round(prev["audible"] + s["audible"], 2)
            prev["title"] = prev.get("title") or s.get("title")
            continue
        out.append(s)
    for s in out:
        if "pieces" in s:
            ends = [p["t"] for p in s["pieces"][1:]] + [s["t1"] - s["t0"]]
            for p, e in zip(s["pieces"], ends):
                p["dur"] = round(e - p["t"], 3)
    return out


def _merge_blips(segs, gap=2.0):
    """A split-second stop (a controller hiccup) shouldn't cut a song in two: join the pieces back up."""
    out = []
    for s in segs:
        prev = next((p for p in reversed(out) if p["deck"] == s["deck"]), None)
        same_spot = not (prev and prev["prog"] and s["prog"] and s["prog"][0][1] < prev["prog"][-1][1] - 1)
        if prev and same_spot and not s.get("jump") and norm(prev["title"]) == norm(s["title"]) and \
                0 <= s["t0"] - prev["t1"] < gap:
            shift = s["t0"] - prev["t0"]
            prev["prog"] += [[t + shift, r] for t, r in s["prog"]]
            prev["clock"] += [[t + shift, c, rem] for t, c, rem in s["clock"]]
            prev["auto"] += [[p[0] + shift] + p[1:] for p in s["auto"]]
            prev["t1"] = s["t1"]
            prev["audible"] = round(prev["audible"] + s["audible"], 2)
            continue
        out.append(s)
    return out


def _clock(text):
    m = re.match(r"^-?(\d+):(\d{2})(?:\.(\d))?$", (text or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2)) + (int(m.group(3)) / 10 if m.group(3) else 0)


def start_position(seg, length, rate=None):
    """Where in the song (seconds) the deck was when this segment started.
    djay's progress value k (of 128) means the song is somewhere in ((k-1)/128, k/128] - it rounds up - and the
    on-screen clock gives whole seconds. Each reading narrows down the start; the middle of what's left wins."""
    rate = rate or seg.get("rate") or 1.0
    step = length / 128.0
    lows, highs = [], []
    for t, raw in (seg.get("prog") or [])[1:]:          # the first reading can be from before play started
        lows.append((raw - 1) * step - t * rate)
        highs.append(raw * step - t * rate)
    for t, secs, rem in seg.get("clock") or []:
        pos = (length - secs) if rem else secs           # remaining time is rounded up, elapsed rounded down
        lows.append(pos - t * rate - 0.15)
        highs.append(pos + 1.0 - t * rate + 0.15)
    if not lows:
        return 0.0
    lows.sort()
    highs.sort()
    lo = lows[-2] if len(lows) > 3 else lows[-1]         # one late reading shouldn't decide it
    hi = highs[1] if len(highs) > 3 else highs[0]
    if hi < lo:                                           # readings disagree a little: split the difference
        lo, hi = sorted(lows)[len(lows) // 2], sorted(highs)[len(highs) // 2]
    return (lo + hi) / 2


def position_at(seg, length, rate, t_at, window=12.0):
    """Where in its song a recorded deck was at t_at (seconds after this play started), from the readings close
    to that moment only - so a slightly wrong tempo doesn't add up over a long play. None if too few readings."""
    part = seg
    for p in seg.get("pieces") or []:
        if p["t"] <= t_at:
            part = p
    off = part.get("t", 0.0) if part is not seg else 0.0
    near = {"prog": [[0, 0]] + [[t - (t_at - off), r] for t, r in (part.get("prog") or [])[1:] if abs(t + off - t_at) <= window],
            "clock": [[t - (t_at - off), c, rem] for t, c, rem in (part.get("clock") or []) if abs(t + off - t_at) <= window]}
    if len(near["prog"]) + len(near["clock"]) < 4:
        return None
    return start_position(near, length, rate)


def fitted_rate(seg, length):
    """The playing speed measured from djay's progress steps (used only when the screen gave no tempo)."""
    prog = seg["pieces"][-1]["prog"] if seg.get("pieces") else seg.get("prog") or []
    pts = [(t, (raw - 0.5) * length / 128.0) for t, raw in prog[1:] if 0 < raw < 127]
    if len(pts) < 20:
        return None
    n = len(pts)
    mt, mp = sum(t for t, _ in pts) / n, sum(p for _, p in pts) / n
    var = sum((t - mt) ** 2 for t, _ in pts)
    if var <= 0:
        return None
    b = sum((t - mt) * (p - mp) for t, p in pts) / var
    worst = max(abs(mp + b * (t - mt) - p) for t, p in pts)
    return b if worst < 1.6 and 0.85 < b < 1.15 else None


def play_pieces(seg, length, rate, bpm=None):
    """For a play with loops / jumps: [[song position, seconds of mix], ...] in order.
    Repeats of the same length are a loop: they share one start point (all their readings pooled), and the loop
    length is snapped to whole beats when the tempo is known."""
    pcs = seg.get("pieces")
    if not pcs:
        return None
    jumps = [p for p in pcs if p["jump"]]
    loop_len = None
    if len(jumps) >= 2:
        durs = sorted(p["dur"] for p in jumps[:-1]) or [jumps[0]["dur"]]
        loop_len = durs[len(durs) // 2]
        if bpm:
            beat = 60.0 / (bpm * rate)
            loop_len = max(1, round(loop_len / beat)) * beat
    pooled = {"prog": [], "clock": []}
    for p in jumps:                                   # every jump goes back to the same spot (the loop start)
        pooled["prog"] += p["prog"][1:]
        pooled["clock"] += p["clock"]
    pooled["prog"] = [[0, 0]] + sorted(pooled["prog"])
    loop_start = start_position(pooled, length, rate) if jumps else None
    out = []
    for i, p in enumerate(pcs):
        dur = p["dur"]
        if p["jump"]:
            pos = loop_start
            if loop_len and i < len(pcs) - 1:
                dur = loop_len
        elif i == 0 and loop_len and loop_start is not None and len(pcs) > 1:
            pos = loop_start + loop_len * rate - dur * rate   # played into the loop's end, then jumped back
            if pos < 0:
                pos = start_position(p, length, rate)
        else:
            pos = start_position(p, length, rate)
        out.append([max(0.0, pos), max(0.05, dur)])
    return out


# ---------------------------------------------------------------- turning knob values into sound
def filter_freqs(v):
    """djay filter knob (0.5 = off) -> (high-pass Hz, low-pass Hz)."""
    if v < 0.48:
        return 20, int(60 * (20000 / 60.0) ** (v / 0.5))
    if v > 0.52:
        return int(20 * (6000 / 20.0) ** ((v - 0.5) / 0.5)), 20000
    return 20, 20000


def eq_db(v):
    """djay EQ knob (0.5 = flat) -> dB: down to -30 (kill), up to +6."""
    return round(-30 * (1 - v / 0.5), 1) if v < 0.5 else round(6 * (v - 0.5) / 0.5, 1)
