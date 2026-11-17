# Release process

The source repository is XTRAGOODLABS/good-mixx. v1.0.0 is the first source release.

1. Run `python3 tests/smoke_test.py` (quit GOOD MIXX first — the test uses its address).
2. On a Mac, run `bash scripts/package-mac.sh`. It builds `dist/GOOD MIXX/` (app, Traktor link helpers,
   read-me, notices), `dist/GOOD-MIXX-<version>-macOS.zip` and `dist/SHA256SUMS.txt`. Only named files
   are copied into the app.
3. Before upload, unzip the release on a clean user account and check: the app opens, the start screen shows
   the iPad address, Traktor link add/remove works, QUIT stops it. Check the zip contains no `data/` folder,
   song lists, mixes or history.
4. Tag the checked commit (`v1.0.0`), upload the zip and SHA256SUMS.txt to a draft release, verify, publish.

The app is ad-hoc signed only (no Apple Developer ID or notarization), so first launch needs Open Anyway.
Keep personal data out of Git and releases: song lists, saved mixes, play history, djay/Traktor libraries,
logs and Traktor backups. Project code remains UNLICENSED until the owner chooses distribution terms;
third-party parts keep their own licenses (see THIRD-PARTY-NOTICES.md). Version is set in `macos/Info.plist`.
