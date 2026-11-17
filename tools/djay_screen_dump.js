// Lists every readable item in djay's window (text, role, position) so we can find where it shows the key.
// Read-only: it never clicks or changes anything.
ObjC.import('Foundation');
function run(argv) {
  const out = [], start = Date.now(), LIMIT_MS = 90000;
  const se = Application('System Events');
  let proc = null;
  for (const name of ['djay Pro', 'djay', 'djay Pro AI']) { try { const p = se.processes.byName(name); p.name(); proc = p; break; } catch (e) {} }
  if (!proc) return 'djay is not open';
  function str(f) { try { const v = f(); return (v === null || v === undefined) ? '' : String(v); } catch (e) { return ''; } }
  let n = 0;
  function walk(el, depth, path) {
    if (Date.now() - start > LIMIT_MS || n > 6000) return;
    n++;
    const role = str(() => el.role()), val = str(() => el.value()), nm = str(() => el.name()),
          desc = str(() => el.description()), title = str(() => el.title()), help = str(() => el.help());
    let pos = '', size = '';
    try { const p = el.position(); pos = p[0] + ',' + p[1]; } catch (e) {}
    try { const s = el.size(); size = s[0] + 'x' + s[1]; } catch (e) {}
    if (val || nm || desc || title || help || depth < 3)
      out.push([depth, path, role, pos, size, 'name=' + nm, 'title=' + title, 'value=' + val, 'desc=' + desc, 'help=' + help].join('\t'));
    if (depth > 25) return;
    let kids = [];
    try { kids = el.uiElements(); } catch (e) {}
    for (let i = 0; i < kids.length; i++) walk(kids[i], depth + 1, path + '.' + i);
  }
  const wins = proc.windows();
  for (let w = 0; w < wins.length; w++) walk(wins[w], 0, 'w' + w);
  out.unshift('elements: ' + n + '  seconds: ' + ((Date.now() - start) / 1000) + '  windows: ' + wins.length);
  return out.join('\n');
}
