// Reads only the song title, artist and key shown on each djay deck. Read-only: never clicks anything.
// Prints one line per deck: deck<TAB>title<TAB>artist<TAB>key
function run() {
  const se = Application('System Events');
  let proc = null;
  for (const name of ['djay Pro', 'djay', 'djay Pro AI']) { try { const p = se.processes.byName(name); p.name(); proc = p; break; } catch (e) {} }
  if (!proc) return 'NOT_RUNNING';
  const lines = [];
  const wins = proc.windows;
  const nw = wins.length;
  for (let w = 0; w < nw; w++) {
    let groups;
    try { groups = wins[w].groups.whose({ description: 'Decks' }); if (!groups.length) continue; } catch (e) { continue; }
    const els = groups[0].uiElements;
    const descs = els.description(), vals = els.value();
    const decks = {};
    for (let i = 0; i < descs.length; i++) {
      const m = /^(Title|Artist|Key), Deck (\d)$/.exec(descs[i] || '');
      if (!m) continue;
      const d = decks[m[2]] = decks[m[2]] || {};
      const v = vals[i] === null || vals[i] === undefined ? '' : String(vals[i]);
      if (v && !d[m[1]]) d[m[1]] = v;
    }
    for (const n in decks) lines.push([n, decks[n].Title || '', decks[n].Artist || '', decks[n].Key || ''].join('\t'));
    break;
  }
  return lines.join('\n') || 'NO_DECKS';
}
