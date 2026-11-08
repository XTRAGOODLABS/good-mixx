"""Scan show folders and build data/library.json (title, artist, BPM, Camelot key).
Usage: python3 tools/scan_library.py "/path/to/MCR Shows for iPad" [--show "House Party Frequency"]
Needs ffprobe. Reads tags only; never changes your music files."""
import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AUDIO = ('.mp3', '.m4a', '.flac', '.wav', '.aiff', '.aif')
MINOR = ['Abm','Ebm','Bbm','Fm','Cm','Gm','Dm','Am','Em','Bm','F#m','Dbm']
MAJOR = ['B','F#','Db','Ab','Eb','Bb','F','C','G','D','A','E']
ALIAS = {'G#':'Ab','D#':'Eb','A#':'Bb','C#':'Db','Gb':'F#','Cb':'B','Fb':'E','E#':'F','B#':'C'}

def camelot(raw):
    if not raw: return ''
    s = raw.strip().replace('♯', '#').replace('♭', 'b')
    m = re.fullmatch(r'(\d{1,2})\s*([ABab])', s)
    if m and 1 <= int(m[1]) <= 12: return f"{int(m[1])}{m[2].upper()}"
    m = re.fullmatch(r'(\d{1,2})\s*([dmDM])', s)          # Open Key (Traktor)
    if m and 1 <= int(m[1]) <= 12:
        return f"{(int(m[1]) + 6) % 12 + 1}{'A' if m[2].lower() == 'm' else 'B'}"
    m = re.fullmatch(r'([A-Ga-g])([#b]?)\s*(m|min|minor|maj|major)?', s)
    if m:
        root = m[1].upper() + m[2]
        root = ALIAS.get(root, root)
        minor = (m[3] or '').lower() in ('m', 'min', 'minor')
        name = root + ('m' if minor else '')
        lst = MINOR if minor else MAJOR
        if name in lst: return f"{lst.index(name) + 1}{'A' if minor else 'B'}"
    return ''

def read(path):
    try:
        out = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries',
            'format=duration:format_tags=title,artist,TBPM,BPM,bpm,tmpo,TKEY,initialkey,KEY,key,comment,genre',
            '-of', 'json', str(path)], capture_output=True, text=True, timeout=30).stdout
        fmt = json.loads(out or '{}').get('format', {})
    except Exception:
        fmt = {}
    t = {k.lower(): v for k, v in (fmt.get('tags') or {}).items()}
    bpm = ''
    for k in ('tbpm', 'bpm', 'tmpo'):
        try:
            v = float(str(t.get(k, '')).split('/')[0])
            if 40 <= v <= 250: bpm = round(v, 1); break
        except ValueError: pass
    key = ''
    for k in ('tkey', 'initialkey', 'key'):
        key = camelot(t.get(k, ''))
        if key: break
    if not key:  # Mixed In Key style comment, e.g. "2A - Energy 6"
        m = re.match(r'\s*(\d{1,2}[AB])\b', t.get('comment', ''))
        if m: key = camelot(m[1])
    stem = path.stem
    title, artist = t.get('title', '').strip(), t.get('artist', '').strip()
    if not title:
        parts = stem.split(' - ', 1)
        artist, title = (parts if len(parts) == 2 else (artist, stem))
    try: dur = round(float(fmt.get('duration', 0)))
    except ValueError: dur = 0
    return dict(title=title, artist=artist, bpm=bpm, key=key, genre=t.get('genre', ''),
                length=dur, file=path.name)

def main():
    root = Path(sys.argv[1])
    only = sys.argv[sys.argv.index('--show') + 1] if '--show' in sys.argv else None
    out = Path(__file__).resolve().parent.parent / 'data' / 'library.json'
    lib = json.loads(out.read_text()) if out.exists() else {'songs': []}
    shows = [d for d in sorted(root.iterdir()) if d.is_dir() and (not only or d.name == only)]
    for show in shows:
        files = [p for p in sorted(show.rglob('*')) if p.suffix.lower() in AUDIO and not p.name.startswith('._')]
        with ThreadPoolExecutor(6) as ex: rows = list(ex.map(read, files))
        for r in rows: r['show'] = show.name; r['id'] = f"{show.name}/{r['file']}"
        lib['songs'] = [s for s in lib['songs'] if s.get('show') != show.name] + rows
        print(f"{show.name}: {len(rows)} songs, {sum(1 for r in rows if r['bpm'])} with BPM, {sum(1 for r in rows if r['key'])} with key")
    lib['songs'].sort(key=lambda s: (s['show'], s['artist'].lower(), s['title'].lower()))
    out.write_text(json.dumps(lib, ensure_ascii=False, indent=0))

if __name__ == '__main__': main()
