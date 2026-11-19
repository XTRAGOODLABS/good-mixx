"""STUDIO: turn good mixes or a past set into a finished mix.

A mix is an ordered list of songs. For each blend between two songs GOOD MIXX can:
  beat  - match the tempo (pitch stays the same) and line the beats up, then blend over a few bars
  set   - start the next song when you started it in the real set (djay / Traktor history)
  fade  - a plain crossfade at the end of the song
The finished mix is built with ffmpeg (MP3 or WAV) and can also be saved as a playlist (.m3u8)
with a timed tracklist. Your music files are only ever read, never changed.
"""
import json, math, os, re, shutil, subprocess, threading, time
from array import array
from pathlib import Path
from urllib.parse import unquote

AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff", ".flac", ".alac", ".mp4", ".ogg")
OUT_DIR = Path(os.environ.get("GOODMIXX_OUT") or Path.home() / "Music" / "GOOD MIXX")
SR = 11025                 # sample rate used only for finding beats
HOP = 64                   # ~5.8 ms steps when finding beats
MAX_STRETCH = 0.08         # beat-matching changes a song's tempo by at most 8%
DEFAULT_LEN = 240.0


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\((feat|ft|with)[^)]*\)|\bfeat\.?.*$|\bft\.?.*$", "", s)
    s = re.sub(r"\(.*?(edit|version|remaster|clean|radio|explicit|dirty).*?\)|\[.*?\]", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def song_key(title, artist=""):
    return norm(artist) + "|" + norm(title)


# ---------------------------------------------------------------- tools
def _tool(name):
    for d in (os.environ.get("GOODMIXX_FFMPEG_DIR"), "/opt/homebrew/bin", "/usr/local/bin",
              str(Path.home() / "Library" / "Application Support" / "GOOD MIXX" / "bin")):
        if d and os.access(os.path.join(d, name), os.X_OK):
            return os.path.join(d, name)
    return shutil.which(name)


def ffmpeg():
    return _tool("ffmpeg")


def ffprobe():
    return _tool("ffprobe")


_durations = {}


def duration(path):
    """Length of an audio file in seconds (remembered until the file changes)."""
    fp = ffprobe()
    if not fp:
        return 0.0
    try:
        stamp = os.stat(path).st_mtime
    except OSError:
        return 0.0
    hit = _durations.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        out = subprocess.run([fp, "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        secs = float(out) if out else 0.0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0
    _durations[str(path)] = (stamp, secs)
    return secs


# ---------------------------------------------------------------- finding song files
class Finder:
    """Finds the audio file for a song: chosen by hand > Traktor > djay > song list > Spotlight."""

    def __init__(self, data_dir, djay=None, traktor=None, library=None):
        self.path = Path(data_dir) / "studio_files.json"
        self.djay, self.traktor, self.library = djay, traktor, library
        self.lock = threading.Lock()
        self.known = self._load()
        self.misses = {}                 # song key -> time of the last failed search

    def _load(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.known, ensure_ascii=False, indent=0))
        except OSError:
            pass

    def remember(self, item, path):
        with self.lock:
            self.known[song_key(item.get("title"), item.get("artist"))] = {"path": str(path), "by": "you"}
            self.misses.pop(song_key(item.get("title"), item.get("artist")), None)
            self._save()

    def find(self, item):
        k = song_key(item.get("title"), item.get("artist"))
        with self.lock:
            hit = self.known.get(k)
            if hit and os.path.isfile(hit["path"]):
                return hit["path"]
            if time.time() - self.misses.get(k, 0) < 120:
                return ""
        for how in (self._from_id, self._from_djay, self._from_spotlight):
            try:
                p = how(item)
            except Exception:
                p = ""
            if p and os.path.isfile(p):
                with self.lock:
                    self.known[k] = {"path": p, "by": how.__name__[6:]}
                    self._save()
                return p
        with self.lock:
            self.misses[k] = time.time()
        return ""

    def _from_id(self, item):
        sid = str(item.get("sid") or "")
        if sid.startswith("tk:"):
            return traktor_path(sid[3:])
        if self.library and "/" in sid and not sid.startswith(("ext:", "tk:")):
            name = sid.split("/", 1)[1]
            return _spotlight('kMDItemFSName == "%s"' % _q(name), prefer=item)
        return ""

    def _from_djay(self, item):
        if not self.djay:
            return ""
        tid = item.get("tid") or self.djay.tid_for(item.get("title"), item.get("artist"))
        return self.djay.file_for(tid) if tid else ""

    def _from_spotlight(self, item):
        t = (item.get("title") or "").strip()
        if not t:
            return ""
        audio = 'kMDItemContentTypeTree == "public.audio"'
        return (_spotlight('%s && kMDItemTitle == "%s"cd' % (audio, _q(t)), prefer=item)
                or _spotlight('%s && kMDItemFSName == "*%s*"cd' % (audio, _q(t)), prefer=item))


def _q(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("*", "")


def _spotlight(query, prefer=None):
    if not shutil.which("mdfind"):
        return ""
    try:
        out = subprocess.run(["mdfind", query], capture_output=True, text=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    paths = [p for p in out.splitlines() if p.lower().endswith(AUDIO_EXT) and os.path.isfile(p)
             and "/Library/Caches/" not in p and "/.Trash/" not in p]
    if not paths:
        return ""
    if prefer:
        a, t = norm(prefer.get("artist")), norm(prefer.get("title"))
        paths.sort(key=lambda p: -((t and t in norm(p)) * 2 + (a and a in norm(p))))
    return paths[0]


def traktor_path(where):
    """Traktor's 'Macintosh HD/:Users/:joe/:Music/:song.mp3' -> a real path on this Mac."""
    parts = where.split("/:")
    if len(parts) < 2:
        return ""
    vol, rest = parts[0], "/" + "/".join(parts[1:])
    for p in (rest, "/Volumes/" + vol + rest):
        if os.path.isfile(p):
            return p
    return ""


_PATH_RE = re.compile(rb"(?:file://)?(/(?:Users|Volumes)/[^\x00-\x1f\"<>]+?\.(?:mp3|m4a|aac|wav|aiff?|flac|alac|mp4|ogg))",
                      re.I)


def paths_in(raw):
    """Audio file paths written inside a djay library record."""
    out = []
    for m in _PATH_RE.finditer(raw):
        p = m.group(1).decode("utf-8", "replace")
        out.append(unquote(p) if "%" in p else p)
    return out


# ---------------------------------------------------------------- finding the beat
def decode(path, start, length, lowpass=True):
    ff = ffmpeg()
    if not ff:
        return None
    cmd = [ff, "-v", "quiet", "-ss", "%.3f" % max(0.0, start), "-t", "%.3f" % length, "-i", str(path), "-ac", "1",
           "-ar", str(SR)] + (["-af", "lowpass=f=180"] if lowpass else []) + ["-f", "s16le", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    a = array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    if a.itemsize == 2 and array("h", [1]).tobytes() != b"\x01\x00":
        a.byteswap()
    return a


def onsets(samples):
    """How sharply the (bass) volume rises in each ~6 ms step - kicks show up as spikes."""
    env, prev = [], 0.0
    for i in range(0, len(samples) - HOP, HOP):
        e = 0
        for v in samples[i:i + HOP]:
            e += v * v
        e = math.sqrt(e / HOP)
        env.append(max(0.0, e - prev))
        prev = e
    return env


def beat_phase(env, bpm):
    """Seconds from the start of `env` to the first beat, for a song at `bpm`. None if no clear beat."""
    if not env or not bpm:
        return None
    step = HOP / SR
    period = 60.0 / bpm
    n = len(env)
    best, best_score, total = None, -1.0, 0.0
    candidates = int(period / step)
    for c in range(candidates):
        phi = c * step
        s, k = 0.0, 0
        while True:
            pos = (phi + k * period) / step
            i = int(pos)
            if i + 1 >= n:
                break
            s += env[i] + env[i + 1] * 0.5 + (env[i - 1] * 0.5 if i else 0)
            k += 1
        total += s
        if s > best_score:
            best, best_score = phi, s
    if best is None or total <= 0 or best_score < 1.6 * total / candidates:
        return None                       # no beat stands out (silence, ambient intro)
    return best


_phases = {}


def find_phase(path, start, length, bpm):
    """Song time (seconds) of a beat near `start`, or None. Remembered, so previews and rebuilds are quick."""
    try:
        stamp = os.stat(path).st_mtime
    except OSError:
        return None
    key = (str(path), stamp, round(start, 2), round(length, 2), round(bpm, 3))
    if key not in _phases:
        _phases[key] = _find_phase(path, start, length, bpm)
        if len(_phases) > 4000:
            _phases.pop(next(iter(_phases)))
    return _phases[key]


def _find_phase(path, start, length, bpm):
    a = decode(path, start, length)
    if not a or len(a) < SR:
        return None
    ph = beat_phase(onsets(a), bpm)
    return None if ph is None else max(0.0, start) + ph


# ---------------------------------------------------------------- laying out the mix
def _bpm(x):
    try:
        v = float(x or 0)
        return v if 40 <= v <= 250 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _match_tempo(target, bpm):
    """Treat a song at half / double time as matching. Returns (bpm to use, rate) or (0, 0)."""
    if not target or not bpm:
        return 0.0, 0.0
    b = bpm
    while target / b > 1.5:
        b *= 2
    while target / b < 0.75:
        b /= 2
    return b, target / b


def plan(mix, finder=None, analyze=True, lengths=None):
    """Work out where every song starts, at what tempo and where it fades.
    Returns {"items": [...], "total": secs, "warnings": [...], "playable": n}."""
    lengths = lengths if lengths is not None else {}
    blend_all = mix.get("blend") or "beat"
    bars = max(2, min(64, int(mix.get("bars") or 16)))
    fade = max(1.0, min(60.0, float(mix.get("fade") or 12)))
    rows, warnings = [], []
    for it in mix.get("items") or []:
        r = dict(it)
        r["path"] = (finder.find(it) if finder else it.get("path")) or ""
        if r["path"]:
            if r["path"] not in lengths:
                lengths[r["path"]] = duration(r["path"])
            r["length"] = lengths[r["path"]] or float(it.get("length") or 0) or DEFAULT_LEN
        else:
            r["length"] = float(it.get("length") or 0) or DEFAULT_LEN
        r["bpm"] = _bpm(it.get("bpm"))
        rows.append(r)
    playable = [r for r in rows if r["path"]]
    use = playable if playable else rows          # nothing on this Mac: still show a preview
    for r in rows:
        if not r["path"]:
            r["skip"] = bool(playable)
            r["warn"] = "not found on this Mac" + (" - left out of the audio mix" if playable else "")
    prev = None
    for idx, r in enumerate(use):
        cin = max(0.0, float(r.get("cut_in") or 0))
        cout = float(r.get("cut_out") or 0) or r["length"]
        cout = min(cout, r["length"]) if r["length"] else cout
        if cout - cin < 8:
            cin, cout = 0.0, r["length"]
        r.update(song_in=cin, song_out=cout, natural_out=cout, rate=1.0, fade_in=0.0, fade_out=0.0, blend_used="",
                 nudge_used=0.0)
        if prev is None:
            r["mix_start"] = 0.0
            prev = r
            continue
        want = r.get("blend") or blend_all
        used = want
        a = prev
        a_end = a["mix_start"] + (a["song_out"] - a["song_in"]) / a["rate"]
        if want == "set":
            if a.get("set_start") and r.get("set_start"):
                gap = float(r["set_start"]) - float(a["set_start"])
                start = a["mix_start"] + (gap - a["song_in"]) / a["rate"]
                hi = a_end - 2.0
                if start > hi:
                    start = a_end - fade
                start = max(a["mix_start"] + 10.0, start)
                over = max(1.0, min(fade, a_end - start))
                r["mix_start"] = start
                r["fade_in"] = over
                _cut(a, start + over)
                a["fade_out"] = over
            else:
                used = "fade"
                r.setdefault("warn", "no set timing for this song - used a crossfade")
        if want == "beat":
            applied, note = _beat_blend(a, r, bars, analyze)
            if not applied:
                used = "fade"
            if note:
                r.setdefault("warn", note)
        if used == "fade":
            over = max(1.0, min(fade, (a["song_out"] - a["song_in"]) / a["rate"] / 2,
                                (r["song_out"] - r["song_in"]) / 2))
            r["mix_start"] = a_end - over
            r["fade_in"] = over
            a["fade_out"] = over
        r["blend_used"] = used
        if r.get("nudge"):
            _nudge(a, r, float(r["nudge"]), used)
        prev = r
    for r in use:
        r["dur"] = (r["song_out"] - r["song_in"]) / r["rate"]
    for r in rows:
        if r.get("warn"):
            w = "%s: %s" % (r.get("title") or "?", r["warn"])
            if w not in warnings:
                warnings.append(w)
    if use:
        use[-1]["fade_out"] = max(use[-1]["fade_out"], min(3.0, use[-1]["dur"] / 4))
    total = max((r["mix_start"] + r["dur"] for r in use), default=0.0)
    for r in rows:
        if r not in use:
            r.update(mix_start=None, dur=0)
    return {"items": rows, "total": total, "warnings": warnings, "playable": len(playable),
            "preview_only": not playable}


def _nudge(a, b, shift, used):
    """Move song `b` in earlier (shift < 0) or later, by hand. Beat-matched blends move by whole beats
    so the beats stay lined up; song `a` then ends where the new blend ends."""
    if used == "beat" and a.get("bpm"):
        beat = 60.0 / (a["bpm"] * a["rate"])
        shift = round(shift / beat) * beat
    else:
        beat = 0.0
    auto = b["mix_start"]
    a_end = a["mix_start"] + (a["natural_out"] - a["song_in"]) / a["rate"]
    start = auto + shift
    lo, hi = a["mix_start"] + 2.0, a_end - 1.0
    if start < lo:
        start = start + beat * math.ceil((lo - start) / beat) if beat else lo
    if start > hi:
        start = start - beat * math.ceil((start - hi) / beat) if beat else hi
    if hi < lo:
        return
    over = max(0.5, min(b["fade_in"] or 0.5, a_end - start))
    b["mix_start"] = start
    b["fade_in"] = over
    b["nudge_used"] = start - auto
    a["song_out"] = a["natural_out"]
    _cut(a, start + over)
    a["fade_out"] = over


def _cut(a, mix_time):
    """Stop song `a` at `mix_time` (in mix seconds)."""
    a["song_out"] = min(a["song_out"], a["song_in"] + (mix_time - a["mix_start"]) * a["rate"])


def _beat_blend(a, b, bars, analyze):
    """Tempo-match `b` to `a` and line its first beat up with a beat of `a`.
    Returns (applied, note): applied=False means use a crossfade instead."""
    eff = a["bpm"] * a["rate"] if a["bpm"] else 0
    b_bpm, rate = _match_tempo(eff, b["bpm"])
    if not eff or not b_bpm:
        return False, "no BPM for one of the songs - used a crossfade"
    if abs(rate - 1) > MAX_STRETCH:
        return False, "tempos too far apart (%.0f vs %.0f BPM) - used a crossfade" % (eff, b["bpm"])
    ta, tb = 60.0 / a["bpm"], 60.0 / b_bpm
    a_len, b_len = a["song_out"] - a["song_in"], b["song_out"] - b["song_in"]
    while bars > 2 and (bars * 4 * ta > a_len * 0.45 or bars * 4 * tb > b_len * 0.45):
        bars //= 2
    blend_song_a = bars * 4 * ta                      # blend length in song A's own seconds
    target = a["song_out"] - blend_song_a - 4 * 4 * ta  # finish the blend ~4 bars before A ends
    target = max(a["song_in"] + 4 * ta, target)
    pa = pb = None
    if analyze and a.get("path") and b.get("path"):
        pa = find_phase(a["path"], target - 8, 16, a["bpm"])
        pb = find_phase(b["path"], b["song_in"], 20, b_bpm)
    found = pa is not None and pb is not None
    if pa is not None:                                 # snap the blend start onto one of A's beats
        k = round((target - pa) / ta)
        s_bs = pa + k * ta
    else:
        s_bs = target
    s_bs = max(a["song_in"] + ta, s_bs)
    b_in = pb if pb is not None else b["song_in"]
    if b_in < b["song_in"]:
        b_in += tb * math.ceil((b["song_in"] - b_in) / tb)
    t_bs = a["mix_start"] + (s_bs - a["song_in"]) / a["rate"]
    over = blend_song_a / a["rate"]
    b.update(mix_start=t_bs, song_in=b_in, rate=eff / b_bpm, fade_in=over)
    _cut(a, t_bs + over)
    a["fade_out"] = over
    if analyze and not found:
        return True, "couldn't hear the beat clearly - tempo matched, beats may not line up"
    return True, ""


# ---------------------------------------------------------------- building the audio
def ffmpeg_command(p, out_path, fmt="mp3", title="GOOD MIXX mix", clip=False):
    ff = ffmpeg()
    use = [r for r in p["items"] if r.get("mix_start") is not None and r.get("path")]
    if not ff or not use:
        return None
    cmd = [ff, "-y", "-hide_banner", "-nostats", "-progress", "pipe:1"]
    chains = []
    for i, r in enumerate(use):
        cmd += ["-ss", "%.4f" % r["song_in"], "-t", "%.4f" % (r["song_out"] - r["song_in"]), "-i", r["path"]]
        f = ["aresample=44100", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
        if abs(r["rate"] - 1) > 1e-4:
            f.append("atempo=%.6f" % r["rate"])
        dur = r["dur"]
        fi = min(r["fade_in"], dur) if r["fade_in"] else 0.02
        fo = min(r["fade_out"], dur) if r["fade_out"] else 0.02
        f.append("afade=t=in:st=0:d=%.4f:curve=qsin" % fi)
        at = r["fade_out_at"] if r.get("fade_out_at") is not None else dur - fo
        f.append("afade=t=out:st=%.4f:d=%.4f:curve=qsin" % (max(0.0, at), fo))
        ms = int(round(r["mix_start"] * 1000))
        if ms > 0:
            f.append("adelay=delays=%d:all=1" % ms)
        chains.append("[%d:a]%s[a%d]" % (i, ",".join(f), i))
    ins = "".join("[a%d]" % i for i in range(len(use)))
    tail = ""
    if clip:                                   # short preview: soft start and end, no clicks
        tail = ",afade=t=in:st=0:d=0.3,afade=t=out:st=%.3f:d=0.6" % max(0.0, p["total"] - 0.6)
    chains.append("%samix=inputs=%d:normalize=0:dropout_transition=0,alimiter=limit=0.95:level=0%s[out]"
                  % (ins, len(use), tail))
    cmd += ["-filter_complex", ";".join(chains), "-map", "[out]", "-ar", "44100", "-metadata", "title=" + title,
            "-metadata", "artist=GOOD MIXX"]
    cmd += (["-c:a", "libmp3lame", "-b:a", "320k" if not clip else "160k"] if fmt == "mp3" else ["-c:a", "pcm_s16le"])
    return cmd + [str(out_path)]


def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name or "").strip(" .") or "GOOD MIXX mix"
    return name[:80]


def unique(path):
    path = Path(path)
    if not path.exists():
        return path
    for i in range(2, 999):
        p = path.with_name("%s (%d)%s" % (path.stem, i, path.suffix))
        if not p.exists():
            return p
    return path


def clock(secs):
    secs = int(round(secs or 0))
    return ("%d:%02d:%02d" % (secs // 3600, secs // 60 % 60, secs % 60)) if secs >= 3600 else "%02d:%02d" % (secs // 60, secs % 60)


def tracklist(p, name):
    lines = [name, ""]
    for r in p["items"]:
        who = ((r.get("artist") or "") + " - " if r.get("artist") else "") + (r.get("title") or "")
        if r.get("mix_start") is None:
            lines.append("  --:--  %s  (not in the audio mix)" % who)
        else:
            lines.append("  %s  %s" % (clock(r["mix_start"]), who))
    lines += ["", "Made with GOOD MIXX - Crate OS by XTRAGOODLABS"]
    return "\n".join(lines) + "\n"


def playlist(p, name):
    out = ["#EXTM3U", "#PLAYLIST:" + name]
    for r in p["items"]:
        who = ((r.get("artist") or "") + " - " if r.get("artist") else "") + (r.get("title") or "")
        out.append("#EXTINF:%d,%s" % (int(r.get("length") or 0), who))
        out.append(r["path"] if r.get("path") else "# not on this Mac: " + who)
    return "\n".join(out) + "\n"


class Renderer:
    """Runs one ffmpeg job at a time in the background and reports progress."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.status = {"state": "idle"}

    def start(self, p, name, fmt):
        with self.lock:
            if self.status.get("state") in ("planning", "rendering"):
                return False
            self.status = {"state": "rendering", "pct": 0, "name": name}
        threading.Thread(target=self._run, args=(p, name, fmt), daemon=True).start()
        return True

    def _run(self, p, name, fmt):
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out = unique(OUT_DIR / (safe_name(name) + (".mp3" if fmt == "mp3" else ".wav")))
            cmd = ffmpeg_command(p, out, fmt, name)
            if not cmd:
                raise RuntimeError("Nothing to build - none of these songs were found on this Mac." if ffmpeg()
                                   else "Building the audio needs ffmpeg (free). See the read-me.")
            total = max(1.0, p["total"])
            with self.lock:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in self.proc.stdout:
                if line.startswith(("out_time_us=", "out_time_ms=")):
                    try:
                        t = int(line.split("=", 1)[1]) / 1e6
                    except ValueError:
                        continue
                    self.status["pct"] = max(0, min(99, int(t / total * 100)))
            err = self.proc.stderr.read()
            code = self.proc.wait()
            if self.status.get("state") == "cancelled":
                try:
                    out.unlink()
                except OSError:
                    pass
                return
            if code != 0 or not out.exists():
                raise RuntimeError("ffmpeg stopped: " + (err.strip().splitlines() or ["unknown error"])[-1][:300])
            txt = out.with_suffix(".txt")
            txt.write_text(tracklist(p, name))
            self.status = {"state": "done", "pct": 100, "name": name, "out": str(out), "tracklist": str(txt),
                           "total": p["total"]}
        except Exception as e:
            self.status = {"state": "error", "msg": str(e), "name": name}
        finally:
            with self.lock:
                self.proc = None

    def cancel(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.status = {"state": "cancelled"}
                self.proc.terminate()
                return True
        return False


# ---------------------------------------------------------------- song waves
WAVE_POINTS_PER_SEC = 10


def wave(path, cache_dir):
    """The loudness shape of a song: 10 values a second, 0-255. Cached next to your mixes."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    import hashlib
    name = hashlib.sha1(("%s|%s|%s" % (path, st.st_mtime, st.st_size)).encode()).hexdigest()[:20] + ".json"
    f = Path(cache_dir) / name
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        pass
    ff = ffmpeg()
    if not ff:
        return None
    rate = 2000
    try:
        raw = subprocess.run([ff, "-v", "quiet", "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                             capture_output=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    a = array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    if array("h", [1]).tobytes() != b"\x01\x00":
        a.byteswap()
    step = rate // WAVE_POINTS_PER_SEC
    peaks = []
    for i in range(0, len(a), step):
        chunk = a[i:i + step]
        peaks.append(max(max(chunk), -min(chunk)) if chunk else 0)
    top = max(peaks) if peaks else 0
    out = {"rate": WAVE_POINTS_PER_SEC, "length": len(a) / rate,
           "peaks": [int(v * 255 / top) if top else 0 for v in peaks]}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out, separators=(",", ":")))
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- blend previews
def clip_plan(p, t0, t1):
    """The part of a planned mix between t0 and t1 (mix seconds), ready for ffmpeg_command."""
    items = []
    for r in p["items"]:
        if r.get("mix_start") is None or not r.get("path"):
            continue
        start, end = r["mix_start"], r["mix_start"] + r["dur"]
        if end <= t0 or start >= t1:
            continue
        c = dict(r)
        new_start = max(start, t0)
        c["song_in"] = r["song_in"] + (new_start - start) * r["rate"]
        new_end = min(end, t1)
        c["song_out"] = c["song_in"] + (new_end - new_start) * r["rate"]
        c["mix_start"] = new_start - t0
        c["dur"] = new_end - new_start
        c["fade_in"] = max(0.0, r["fade_in"] - (new_start - start)) if r["fade_in"] else 0.0
        if c["fade_in"] and new_start > start:          # started part-way into a fade-in: keep it short
            c["fade_in"] = min(c["fade_in"], 0.5)
        c["fade_out_at"] = (end - r["fade_out"]) - new_start if r["fade_out"] else None
        items.append(c)
    return {"items": items, "total": t1 - t0}


def blend_window(p, index, lead=8.0, tail=8.0):
    """Mix seconds around the blend into song `index`: a little before it starts to a little after the last one ends."""
    r = p["items"][index]
    if r.get("mix_start") is None:
        return None
    prev = None
    for q in p["items"][:index][::-1]:
        if q.get("mix_start") is not None:
            prev = q
            break
    if prev is None:
        return max(0.0, r["mix_start"]), r["mix_start"] + min(r["dur"], 30.0)
    end = prev["mix_start"] + prev["dur"]
    t0 = max(0.0, r["mix_start"] - lead)
    return t0, min(max(end, r["mix_start"] + 4) + tail, t0 + 180)


def preview(p, index, out_path):
    """Build a short MP3 of one blend. Returns the path, or raises with a reason."""
    win = blend_window(p, index)
    if not win:
        raise RuntimeError("This song isn't in the audio mix (no file on this Mac).")
    cp = clip_plan(p, *win)
    cmd = ffmpeg_command(cp, out_path, "mp3", "GOOD MIXX preview", clip=True)
    if not cmd:
        raise RuntimeError("Hearing a blend needs ffmpeg." if not ffmpeg() else "Nothing to play here.")
    cmd = [c for c in cmd if c not in ("-progress", "pipe:1")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not Path(out_path).exists():
        raise RuntimeError("ffmpeg stopped: " + ((r.stderr or "").strip().splitlines() or ["unknown error"])[-1][:300])
    return {"path": str(out_path), "start": win[0], "end": win[1]}
