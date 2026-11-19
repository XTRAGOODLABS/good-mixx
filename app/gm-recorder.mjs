// GOOD MIXX set recorder.
// Runs next to djay Pro and writes what happens on the decks to a log GOOD MIXX can rebuild a set from:
// play/pause, song position (djay's progress steps), tempo, channel volume, crossfader, filter and EQ - as you
// move them - plus each deck's song, BPM, key, clock and tempo % read from djay's screen every few seconds.
// It only reads djay; it never presses, loads or changes anything.
// Uses djay-pro-mcp (github.com/ckryptickunal/djay-pro-mcp, MIT) for the MIDI feedback and screen reading.
// Usage: node gm-recorder.mjs <djay-pro-mcp folder> <log file> [screen-read seconds]
import { appendFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [mcpDir, out, axEvery = "3"] = process.argv.slice(2);
const { Djay } = await import(pathToFileURL(join(mcpDir, "dist", "djay.js")).href);
const dj = new Djay();
const midi = await dj.startMidi();
const t0 = Date.now();
writeFileSync(out, "");
const log = (o) => appendFileSync(out, JSON.stringify({ t: Math.round(Date.now() - t0) / 1000, ...o }) + "\n");
log({ k: "start", unix: t0 / 1000, version: dj.catalog.appVersion });

// Only what a rebuild needs (the full feedback is ~1,900 values, mostly pad lights).
const WANT = /^(turntable[1-4]\.(isPlaying|display\.songProgress|effects\.(filter|tempo|gain)\.currentValue|(low|mid|high)EQEffect\.currentValue|song\.loadingSuccess)|mixer\.(masterCrossfade|volumeEffectChannel[1-4]\.currentValue))$/;
const last = new Map();
let axBusy = false, wantAx = false;

function pollMidi() {
  for (const [path, e] of midi.state) {
    if (!WANT.test(path) || last.get(path) === e.value) continue;
    const was = last.get(path);
    last.set(path, e.value);
    log({ k: "m", p: path, v: Math.round(e.value * 10000) / 10000 });
    if (/isPlaying$|loadingSuccess$/.test(path) && was !== undefined) wantAx = true;   // read the screen right away
  }
}

async function readScreen() {
  if (axBusy) return;
  axBusy = true;
  try {
    const decks = await dj.readouts();
    log({
      k: "d",
      decks: decks.map((d) => ({ n: d.deck, title: d.title, artist: d.artist, bpm: d.bpm, key: d.key, time: d.time,
                                 rem: d.timeIsRemaining, tempo: d.tempoPercent })),
    });
  } catch (e) {
    log({ k: "err", e: String(e).slice(0, 200) });
  } finally {
    axBusy = false;
  }
}

setInterval(pollMidi, 100);
setInterval(() => { if (wantAx) { wantAx = false; readScreen(); } }, 250);
setInterval(readScreen, Math.max(1, +axEvery) * 1000);
readScreen();

const stop = () => { try { log({ k: "end" }); dj.shutdown(); } finally { process.exit(0); } };
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
process.stdin.on("end", stop);       // GOOD MIXX closed: stop too
process.stdin.resume();
