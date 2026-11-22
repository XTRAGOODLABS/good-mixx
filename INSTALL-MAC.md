# Installing GOOD MIXX on a Mac

1. Download `GOOD-MIXX-<version>-macOS.zip` from Releases and double-click it.
2. Drag **GOOD MIXX** into Applications and open it.
   The app is not from the App Store, so the first time: right-click it → **Open** → **Open**
   (newer macOS: System Settings → Privacy & Security → **Open Anyway**).
3. If asked, let macOS install its free developer tools (this adds Python), then open GOOD MIXX again.
4. The start screen shows the address to open on your iPad (same Wi-Fi).

**djay:** allow GOOD MIXX in System Settings → Privacy & Security → **Accessibility** so it can read the key djay shows.

**djay:** after updating GOOD MIXX, macOS may stop counting the Accessibility switch even though it shows ON.
Select GOOD MIXX there, click **−**, click **+** and add it again, then reopen GOOD MIXX.

**Traktor Pro 4 or 3 (one time):**
1. Put GOOD MIXX in Applications and open it once.
2. Quit Traktor completely.
3. In the downloaded folder, **right-click "Add Traktor Link" → Open → Open** (double-clicking is blocked the first
   time because it was downloaded). Type your Mac password if asked — it won't show as you type. Wait until it says done.
   If it can't change Traktor's files: System Settings → Privacy & Security → **App Management** → turn on Terminal,
   quit Terminal (⌘Q), and do step 3 again.
4. In Traktor: Preferences → Controller Manager → Add… → Traktor → **Kontrol D2** (no D2 needed).
5. Open GOOD MIXX and load a song in Traktor. **It worked if the song's name shows up in GOOD MIXX.**

Not working? Right-click **Check Traktor Link** → Open → Open. It says what's missing and saves a report to
`~/Library/Logs/GOOD MIXX traktor check.txt`. After a Traktor update, do step 3 again.
**Remove Traktor Link** puts Traktor back exactly as it was.

Set recorder (optional, djay Pro on the Mac only): records your sets so STUDIO can rebuild them exactly as you played them. It does not work with Traktor, and sets played on the iPad can't be recorded.

1. Install the free Node.js 22.13 or newer. With Homebrew, run `brew install node` in Terminal.
2. Click SET UP RECORDER at the top of the GOOD MIXX window (one time). It downloads and installs [djay-pro-mcp](https://github.com/ckryptickunal/djay-pro-mcp) into a `djay-pro-mcp` folder in your home folder.
3. Quit djay completely and open it again.

After that it records whenever djay is open; the REC button turns it on or off. It only reads djay and never changes anything in it. In STUDIO, recorded sets show ● RECORDED.

**STUDIO (optional):** building a finished MP3/WAV mix needs the free **ffmpeg**. With Homebrew, run
`brew install ffmpeg` in Terminal. Saving playlists works without it.

Your mixes live in `~/Library/Application Support/GOOD MIXX`. Click **QUIT** in the Mac window to stop.
