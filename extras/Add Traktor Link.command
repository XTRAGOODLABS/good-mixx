#!/bin/bash
# Double-click to connect Traktor Pro 4 (or 3) to GOOD MIXX. Run it again after any Traktor update.
# It adds two lines and a small "Api" folder to Traktor's own Kontrol D2 screen files, so Traktor
# tells GOOD MIXX what each deck is playing. Traktor's original files are backed up first.
# To undo: double-click "Remove Traktor Link.command".
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
done_msg() { echo ""; read -n 1 -s -r -p "Press any key to close."; exit "$1"; }

# The link files: next to this file, inside GOOD MIXX.app, or in this source folder
SRC=""
for d in "$HERE/GOOD MIXX.app/Contents/Resources/app/traktor-link" "/Applications/GOOD MIXX.app/Contents/Resources/app/traktor-link" \
         "$HOME/Applications/GOOD MIXX.app/Contents/Resources/app/traktor-link" "$HERE/../app/traktor-link" "$HERE/traktor-link"; do
  [ -f "$d/Api/ApiClient.js" ] && SRC="$d" && break
done
if [ -z "$SRC" ]; then echo "Keep this file next to GOOD MIXX.app (or put GOOD MIXX in Applications) and try again."; done_msg 1; fi

SUPPORT="$HOME/Library/Application Support/GOOD MIXX"
mkdir -p "$SUPPORT"
LEGACY="$HOME/Portal-Stems-FX/traktor-link/D2-original-backup"   # where the first test version kept it

# Every Traktor Pro 4 / 3 on this Mac, one per line as: <version>|<app path>
find_traktors() {
  local v a found
  for v in 4 3; do
    found=""
    for a in "/Applications/Native Instruments/Traktor Pro $v/Traktor Pro $v.app" \
             "/Applications/Native Instruments/Traktor Pro $v/Traktor.app"; do
      [ -d "$a/Contents/Resources/qml/CSI" ] && found="$a" && break
    done
    [ -z "$found" ] && found="$(find /Applications -maxdepth 4 -type d -name '*.app' -path "*Traktor Pro $v*" 2>/dev/null | head -1)"
    [ -n "$found" ] && [ -d "$found/Contents/Resources/qml/CSI" ] && echo "$v|$found"
  done
}
# Traktor 3 keeps the old backup name so earlier installs still undo cleanly
backup_dir() { if [ "$1" = 3 ]; then echo "$SUPPORT/traktor-D2-original-backup"; else echo "$SUPPORT/traktor$1-D2-original-backup"; fi; }

TRAKTORS="$(find_traktors)"
if [ -z "$TRAKTORS" ]; then
  echo "Traktor Pro 4 or 3 isn't installed in Applications yet. Install it, open it once, then try again."
  done_msg 1
fi
if pgrep -i "traktor" >/dev/null; then
  echo "Please quit Traktor first, then double-click this again."
  done_msg 1
fi

# Copy the new files in next to the old ones first; only swap once the copy worked.
copy_in() {
  $1 rm -rf "$CSI/D2.new" 2>/dev/null
  $1 cp -R "$WORK/D2" "$CSI/D2.new" || return 1
  $1 chmod -R a+rX "$CSI/D2.new" || return 1
  $1 rm -rf "$CSI/D2" && $1 mv "$CSI/D2.new" "$CSI/D2"
}

link_one() {   # $1 = version, $2 = app path
  local V="$1" APP="$2" BACKUP
  CSI="$APP/Contents/Resources/qml/CSI"
  BACKUP="$(backup_dir "$V")"
  echo ""
  echo "== Traktor Pro $V =="
  [ "$V" = 3 ] && [ ! -f "$BACKUP/D2.qml" ] && [ -f "$LEGACY/D2.qml" ] && cp -R "$LEGACY" "$BACKUP"

  # Keep an untouched copy of Traktor's own D2 files (only ever from a copy without the link)
  if [ -f "$CSI/D2/D2.qml" ] && ! grep -q "ApiModule" "$CSI/D2/D2.qml"; then
    rm -rf "$BACKUP.tmp" && cp -R "$CSI/D2" "$BACKUP.tmp" && rm -rf "$BACKUP" && mv "$BACKUP.tmp" "$BACKUP" \
      && echo "Backed up Traktor's original files."
  fi
  if [ ! -f "$BACKUP/D2.qml" ]; then
    echo "Couldn't find Traktor's original D2 files to start from. Tell whoever gave you GOOD MIXX."
    return 1
  fi

  # Build the linked version in a scratch folder first
  WORK="$(mktemp -d)"
  cp -R "$BACKUP" "$WORK/D2" && cp -R "$SRC/Api" "$WORK/D2/Api"
  perl -0pi -e 's/(import "\.\.\/Common\/Settings"\r?\n)/$1import ".\/Api"\n/; s/(\nMapping\s*\{\s*\n)/$1  ApiModule {}\n\n/' "$WORK/D2/D2.qml"
  if ! grep -q '^import "./Api"' "$WORK/D2/D2.qml" || ! grep -q '^  ApiModule {}' "$WORK/D2/D2.qml"; then
    echo "This Traktor version's files look different, so nothing was changed. Tell whoever gave you GOOD MIXX."
    rm -rf "$WORK"; return 1
  fi
  chmod -R a+rX "$WORK/D2"

  if ! copy_in "" 2>/dev/null; then
    echo "macOS needs your Mac password to change files inside Traktor."
    echo "(Type it and press Return - nothing shows while you type.)"
    copy_in sudo
  fi
  rm -rf "$WORK"
  if grep -q "ApiModule" "$CSI/D2/D2.qml" 2>/dev/null && [ -f "$CSI/D2/Api/ApiClient.js" ]; then
    echo "DONE - the Traktor link is added to Traktor Pro $V."
    return 0
  fi
  echo "Couldn't change Traktor's files. If macOS asked about Terminal changing apps, allow it:"
  echo "  System Settings > Privacy & Security > App Management > turn on Terminal"
  echo "then quit Terminal (Command+Q) and double-click this again."
  return 1
}

OK=0
while IFS='|' read -r V APP; do
  [ -n "$V" ] && link_one "$V" "$APP" && OK=1
done <<< "$TRAKTORS"

if [ "$OK" = 1 ]; then
  echo ""
  echo "Last step, only needed once:"
  echo "  1. Open Traktor, then Preferences > Controller Manager"
  echo "  2. Under the Device list, click Add... > Traktor > Kontrol D2"
  echo "     (you don't need to own a D2 - this just switches the link on)"
  echo "  3. Open GOOD MIXX and load a song in Traktor."
  done_msg 0
fi
done_msg 1
