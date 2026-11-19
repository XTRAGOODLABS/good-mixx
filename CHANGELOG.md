# GOOD MIXX version history

GOOD MIXX is based on an idea by **DJ Aquarobotics**: a booth tool that remembers which mixes worked and
suggests what to play next. It began as a "Mixes" screen inside the Portal stems/FX companion, built with Claude in November 2026,
and became a standalone Crate OS app. Versions before 1.0.0 are milestones reconstructed from chats and dated
backups; the Git history follows the same dates.

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
