# GOOD MIXX version history

GOOD MIXX is based on an idea by **DJ Aquarobotics**: a booth tool that remembers which mixes worked and
suggests what to play next. It began as a "Mixes" screen inside the Portal stems/FX companion, built with Claude in November 2026,
and became a standalone Crate OS app. Versions before 1.0.0 are milestones reconstructed from chats and dated
backups; the Git history follows the same dates.

## v1.8.2 — November 20, 2026 · Report a problem

- **REPORT A PROBLEM** button at the top of the window (on the iPad too) and a new **Help** menu with
  Report a Problem, Suggest an Idea and Show Error Log.
- It opens the GOOD MIXX bug form on GitHub with the version, your Mac and recent errors already filled in.
  Nothing is sent unless you press Submit on GitHub.
- GOOD MIXX now keeps a small error log on your Mac (`~/Library/Logs/GOOD MIXX errors.log`), with your
  user name hidden in folder paths.

## v1.8.1 — November 18, 2026 · Recorder says why it can't read djay

- When GOOD MIXX can't read djay's screen (song names, tempo, clock), the recorder now writes down **why** —
  macOS blocking it, djay closed/hidden/minimized, or djay's window showing no decks — and the **REC ⚠** button
  and its pop-up say what to do in plain words.
- Most common fix after updating: in Accessibility, remove GOOD MIXX (−), add it again (+), then reopen GOOD MIXX.
  Each update looks like a new app to macOS, so the old ON switch can stop counting.
- **Clearer Traktor setup steps:** right-click → Open for the helper (double-click is blocked the first time),
  what to expect when it asks for your password, and how to tell it worked.
- **Check Traktor Link** now comes in the download and ends with a plain YES / NO list of what's missing.

## v1.8.0 — November 18, 2026 · Recorded sets rebuild in time

Fixes from the first real recorded set:
- **Start points were ~1.8 s late:** djay rounds its progress steps up; GOOD MIXX treated them as rounded down.
- **Songs with no name from djay's screen** (screen reading blocked) now match djay's history by deck + time, so
  the recording is still used. **REC ⚠** warns when djay's screen can't be read (turn on GOOD MIXX in
  Accessibility) - with it, recordings get djay's exact tempo and clock.
- **Loops:** a loop (or cue jump) while playing is recognised and replayed - the loop snapped to whole beats.
- **Cue back to the start after a pause** and **a new song loaded on the same deck** are no longer mistaken for
  one continuous play.
- **Tempo:** without djay's tempo readout, each song is set to the tempo of the song before (you beat-matched it).
- **Blends line up with the right part of the song before** - from djay's readings around that moment.
- **You may start a song a little before or after the beat - djay catches up:** the rebuild does the same, always
  moving the song onto the nearest beat (up to half a beat), and tries several spots to hear the beat before
  giving up (and says so when it can't).

## v1.7.1 — November 18, 2026

- STUDIO: **⤢ BIG** no longer hides PAST SETS / MY MIXES / SONGS (the panel just gets narrower), and the BIG button
  is always there - before, an empty mix in BIG mode left no way back to your sets.
- REC asks before turning recording off, and says **REC OFF · TURN ON** when it's off.

## v1.7.0 — November 18, 2026 · Set recorder

- **Set recorder:** follows djay Pro on the Mac while you play - play/pause, where each deck is in its song,
  tempo, channel faders, crossfader, filter and EQ - and saves it with your sets. Starts by itself whenever djay
  is open; the **REC** button turns it on or off. **SET UP RECORDER** installs what it needs (no Terminal).
  Uses djay-pro-mcp by ckryptickunal (MIT); only reads djay.
- **As recorded** blend in STUDIO: songs start from the exact spot you started them, at your tempo, with your
  fader / crossfader / filter / EQ moves replayed - then nudged by less than half a beat so the beats line up.
  Recorded sets show **● RECORDED** in PAST SETS and recreate this way automatically.
- Split-second stops (a controller hiccup) don't cut a song in two.

## v1.6.0 — November 18, 2026 · Each song's fades are its own

- Every song has its **own fade-in ◆ and fade-out ◆**. Dragging one changes only that song - the other song's
  fade and position stay put. Snaps to beats on beat-matched songs (hold ⌥ for free).
- A song's **right edge** now sets how long it keeps playing under the next song, without moving the next song.
- Blend effects cover the whole overlap, whatever the fades. ↺ also resets fades and tails.

## v1.5.0 — November 18, 2026 · Bigger timeline, blend effects

- **⤢ BIG** timeline: tall lanes (fills the window, song list panel hides), remembered between visits.
- **Bar and beat lines** drawn on beat-matched songs when zoomed in, and a **volume line** showing each fade.
- **◆ Blend handle:** drag it to make a blend longer or shorter - whole bars when beat-matched, half seconds otherwise.
- **Blend effects** (FX picker per blend): **low-pass out** (outgoing song gets muffled), **high-pass out** (outgoing
  song thins out), **high-pass in** (new song comes in thin and opens up), **bass swap** (bass handed over halfway).
  Used in ▶ BLEND previews and the finished MP3 / WAV.

## v1.4.0 — November 18, 2026 · Set timing that follows your cues

- **Set timing reads your djay cue points.** Each song starts from cue 1, or from the next cue in its first 90 s
  when cue 1 starts on an intro (GOOD MIXX listens for where the kick comes in).
- Songs come in **when djay says you started them**, now tempo-matched and beat-locked to the song before.
- When djay's times don't add up (the last song had already ended, or a long pause) the song is blended
  automatically and marked. Songs you only played for under 20 s are marked as **quick skips**, with
  **REMOVE QUICK SKIPS** to drop them all.
- **Start:** picker under each song: auto, beginning, or any of its cues.

## v1.3.0 — November 18, 2026 · Move the audio around

- STUDIO timeline: **drag a song** to bring it in earlier or later. Beat-matched blends snap to whole bars
  (hold ⌥ for single beats) so the beats stay lined up; the song before it ends where the new blend ends.
- **Drag a song's right edge** to end it sooner or later (moves the next song with it); **drag its left edge** to
  skip into the song. A tip shows how far you've moved it.
- **◂ ▸** nudge a song by a bar (or a second), **↺** puts it back, **UNDO** / ⌘Z undoes timeline changes.
- Moves are saved with the mix and used for blend previews and the finished MP3 / WAV.

## v1.2.0 — November 18, 2026 · Own window, song waves, blend previews

- **GOOD MIXX is a real Mac app now:** its own window and menus (copy/paste, zoom, full screen), no browser.
  Built by GitHub on a Mac for every change, for Apple silicon and Intel. Quitting GOOD MIXX stops it, iPad screen included.
- **STUDIO song waves:** each song's wave drawn on the timeline, with its fades, plus zoom in / out / fit.
- **▶ BLEND** builds and plays just one blend (same beat-matching as the full mix) with a moving playhead.
  **▶ PLAY** plays a finished mix; click the timeline to jump.
- Audio is served with byte ranges so it plays and seeks in Safari and the Mac app.

## v1.1.1 — November 18, 2026

- After an update, opening GOOD MIXX now stops the old copy still running in the background and starts the new
  one. Before, the old copy kept answering, so STUDIO showed but never worked out the mix.
- STUDIO says what went wrong (with TRY AGAIN) instead of waiting forever.

## v1.1.0 — November 18, 2026 · STUDIO

- New **STUDIO** tab in the Mac window: turn your good mixes into a finished mix, or recreate a set you played
  in djay or Traktor on this Mac.
- Three blend styles, for the whole mix or song by song: **beat-matched** (tempo matched without changing pitch,
  beats lined up by listening for the kick, blended over 8/16/32 bars), **your set's timing**, or a **simple crossfade**.
- **BUILD MP3 / WAV** with a timed tracklist, and **SAVE PLAYLIST** (.m3u8 + tracklist), saved to `Music/GOOD MIXX`.
- Finds each song's file through djay, Traktor, the song list and Spotlight, or by hand with **FIND**.
  Songs that aren't files on the Mac (streaming) stay in the playlist and are left out of the audio.
- Mixes are saved and can be reopened, edited and rebuilt. STUDIO only answers on the Mac, never from the iPad.
- Needs ffmpeg to build audio (`brew install ffmpeg`); playlists work without it.

## v1.0.2 — November 17, 2026

- **Traktor Pro 4** support: Add / Remove / Check Traktor Link now find Traktor Pro 4 as well as 3. A Mac with
  both gets both linked, each with its own backup of Traktor's original files.
- Saved mixes show up again for the song that's playing even when the song comes in under a slightly different
  name (a "(Clean)" or "feat." tag, a missing artist, djay vs Traktor spelling, or added to the song list later).
  The same mix saved under two names shows once, with the counts added together.

## v1.0.1 — November 16, 2026

- One Traktor link now feeds both the GOOD MIXX app and GOOD MIXX inside Crate OS (run Add Traktor Link once more).
- Other websites can't reach or post to GOOD MIXX on your Mac (DNS-rebinding and cross-site protection).

## v1.0.0 — November 16, 2026 · GOOD MIXX

- Standalone Mac app, **GOOD MIXX**, under Crate OS by XTRAGOODLABS. Opens its own window; the start screen
  shows the address for the iPad. QUIT button on the Mac only (never from the iPad).
- BeatDeck look: Crate OS crate on the left of the name in Impact, dark theme, orange accent,
  IBM Plex Sans / Mono built in so it looks the same offline and on iPad.
- App icon: GOOD over MIXX in white Impact on black with the Crate OS crate.
- Data lives outside the app (`~/Library/Application Support/GOOD MIXX`), so updates never touch your mixes.
- Traktor link helper now patches Traktor's own Kontrol D2 file instead of shipping a copy of it, backs up
  the original first, and builds the change in a scratch folder before swapping it in.

## v0.4 — November 16, 2026 · djay screen keys, Traktor Pro 3

- djay stopped saving keys for newly analysed songs; GOOD MIXX now reads the key djay *shows* on each deck
  (read-only, a few elements, every 3 seconds) and remembers it.
- **Traktor Pro 3** support through traktor-api-client: live song, artist, key and BPM for all four decks,
  history saved for after-set review, and the Traktor collection used as the song list when there is none.
- Switch between djay and Traktor in the same set — GOOD MIXX follows whichever played last.
- Keys show the way the DJ app shows them: Open Key (3m) on Traktor, Camelot (10A) on djay. Matching is unchanged.
- Own address (port 8770) so it runs alongside Crate OS.

## v0.3 — November 16, 2026 · key fallback

- When djay has no key for a song, use the key from the song file's tags; prefer a library copy that has a key.

## v0.2 — November 13, 2026 · follows djay on the Mac

- Reads djay's own history on the Mac (read-only) so decks fill in by themselves; iPad as the second screen.
- BPM and key from djay's analysis win over file tags.
- After the gig: pick a set played on this Mac and tap GOOD on the mixes that worked.

## v0.1 — November 8, 2026 · the Mixes screen

- Two decks, a big GOOD MIX button and a swap button; search to pick songs by hand.
- What's next: your proven mixes first, then BPM + Camelot key matches; same-show and energy-up filters.
- Review a set from a djay playlist CSV or a pasted list. My Mixes list with undo.
- Song list built from show folders by `tools/scan_library.py` (reads tags, never changes files).
