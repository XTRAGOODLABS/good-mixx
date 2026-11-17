#!/bin/bash
# Double-click to put Traktor back exactly how it was before the Traktor link was added.
# Works for Traktor Pro 4 and 3.
cd "$(dirname "$0")" || exit 1
SUPPORT="$HOME/Library/Application Support/GOOD MIXX"
LEGACY="$HOME/Portal-Stems-FX/traktor-link/D2-original-backup"

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
backup_dir() { if [ "$1" = 3 ]; then echo "$SUPPORT/traktor-D2-original-backup"; else echo "$SUPPORT/traktor$1-D2-original-backup"; fi; }

TRAKTORS="$(find_traktors)"
if [ -z "$TRAKTORS" ]; then
  echo "Nothing to undo (Traktor Pro 4 or 3 isn't installed)."
elif pgrep -i "traktor" >/dev/null; then
  echo "Please quit Traktor first, then double-click this again."
else
  put() { $1 rm -rf "$CSI/D2.old" 2>/dev/null; $1 cp -R "$BACKUP" "$CSI/D2.old" && $1 chmod -R a+rX "$CSI/D2.old" && $1 rm -rf "$CSI/D2" && $1 mv "$CSI/D2.old" "$CSI/D2"; }
  while IFS='|' read -r V APP; do
    [ -z "$V" ] && continue
    CSI="$APP/Contents/Resources/qml/CSI"
    BACKUP="$(backup_dir "$V")"
    [ "$V" = 3 ] && [ ! -d "$BACKUP" ] && BACKUP="$LEGACY"
    if ! grep -q "ApiModule" "$CSI/D2/D2.qml" 2>/dev/null; then
      echo "Traktor Pro $V: the link isn't added, nothing to undo."
    elif [ ! -f "$BACKUP/D2.qml" ]; then
      echo "Traktor Pro $V: no backup found, so nothing was changed."
    else
      put "" 2>/dev/null || put sudo
      echo "Traktor Pro $V: back to normal."
    fi
  done <<< "$TRAKTORS"
  echo "You can also remove the Kontrol D2 in Controller Manager."
fi
echo ""; read -n 1 -s -r -p "Press any key to close."
