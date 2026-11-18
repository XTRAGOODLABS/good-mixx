#!/bin/bash
# Builds dist/GOOD MIXX/ (app + Traktor link helpers + read-me) and dist/GOOD-MIXX-<version>-macOS.zip
# Works on macOS or Linux. Only the files named below go into the app - no personal data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(/usr/bin/env python3 -c "import plistlib;print(plistlib.load(open('$ROOT/macos/Info.plist','rb'))['CFBundleShortVersionString'])")"
OUT="$ROOT/dist/GOOD MIXX"
APP="$OUT/GOOD MIXX.app/Contents"
rm -rf "$ROOT/dist"
mkdir -p "$APP/MacOS" "$APP/Resources/app/assets" "$APP/Resources/app/tools" "$APP/Resources/app/traktor-link/Api"
cp "$ROOT/macos/Info.plist" "$APP/Info.plist"
cp "$ROOT/macos/launcher.sh" "$APP/MacOS/GOOD MIXX"
cp "$ROOT/macos/GOODMIXX.icns" "$APP/Resources/GOODMIXX.icns"
for f in mixes.py mixes_server.py djay_live.py djay_screen.py traktor_live.py studio.py mixes.html; do cp "$ROOT/app/$f" "$APP/Resources/app/"; done
cp "$ROOT"/app/assets/*.woff2 "$ROOT"/app/assets/*.png "$ROOT/app/assets/OFL-IBM-Plex.txt" "$APP/Resources/app/assets/"
cp "$ROOT/app/tools/djay_deck_keys.js" "$APP/Resources/app/tools/"
cp "$ROOT"/app/traktor-link/Api/* "$APP/Resources/app/traktor-link/Api/"
cp "$ROOT/app/traktor-link/LICENSE-traktor-api-client.txt" "$APP/Resources/app/traktor-link/"
cp "$ROOT/extras/Add Traktor Link.command" "$ROOT/extras/Remove Traktor Link.command" "$OUT/"
cp "$ROOT/docs/READ-ME-FIRST.txt" "$OUT/READ ME FIRST.txt"
cp "$ROOT/THIRD-PARTY-NOTICES.md" "$OUT/"
chmod -R a+rX "$OUT"
chmod +x "$APP/MacOS/GOOD MIXX" "$OUT"/*.command
if command -v codesign >/dev/null 2>&1; then codesign --force --deep --sign - "$OUT/GOOD MIXX.app" || true; fi
cd "$ROOT/dist"
ZIP="GOOD-MIXX-$VERSION-macOS.zip"
if command -v ditto >/dev/null 2>&1; then ditto -c -k --keepParent "GOOD MIXX" "$ZIP"; else zip -qry "$ZIP" "GOOD MIXX"; fi
if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$ZIP" > SHA256SUMS.txt; else sha256sum "$ZIP" > SHA256SUMS.txt; fi
echo "Built dist/$ZIP"
