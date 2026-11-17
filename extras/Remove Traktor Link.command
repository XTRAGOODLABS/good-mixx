#!/bin/bash
# Double-click to put Traktor back exactly how it was before the Traktor link was added.
cd "$(dirname "$0")" || exit 1
BACKUP="$HOME/Library/Application Support/GOOD MIXX/traktor-D2-original-backup"
[ -d "$BACKUP" ] || BACKUP="$HOME/Portal-Stems-FX/traktor-link/D2-original-backup"
APP="/Applications/Native Instruments/Traktor Pro 3/Traktor.app"
[ -d "$APP" ] || APP="$(find /Applications -maxdepth 4 -type d -name '*.app' -path '*Traktor Pro 3*' 2>/dev/null | head -1)"
CSI="$APP/Contents/Resources/qml/CSI"
if [ ! -f "$BACKUP/D2.qml" ] || [ ! -d "$CSI" ]; then
  echo "Nothing to undo (no backup found, or Traktor Pro 3 isn't installed)."
elif pgrep -xq "Traktor"; then
  echo "Please quit Traktor first, then double-click this again."
else
  put() { $1 rm -rf "$CSI/D2.old" 2>/dev/null; $1 cp -R "$BACKUP" "$CSI/D2.old" && $1 chmod -R a+rX "$CSI/D2.old" && $1 rm -rf "$CSI/D2" && $1 mv "$CSI/D2.old" "$CSI/D2"; }
  put "" 2>/dev/null || put sudo
  echo "Done - Traktor is back to normal. You can also remove the Kontrol D2 in Controller Manager."
fi
echo ""; read -n 1 -s -r -p "Press any key to close."
