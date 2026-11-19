#!/bin/bash
# Checks each piece of the Traktor link and saves the results to a log file. Changes nothing.
cd "$(dirname "$0")" || exit 1
OUT="$HOME/Library/Logs/GOOD MIXX traktor check.txt"; mkdir -p "$HOME/Library/Logs"
{
echo "== $(date)"
APP=""
for a in "/Applications/Native Instruments/Traktor Pro 4/Traktor Pro 4.app" "/Applications/Native Instruments/Traktor Pro 4/Traktor.app" \
         "/Applications/Native Instruments/Traktor Pro 3/Traktor.app" "/Applications/Native Instruments/Traktor Pro 3/Traktor Pro 3.app"; do
  [ -d "$a" ] && APP="$a" && break
done
[ -z "$APP" ] && APP="$(find /Applications -maxdepth 4 -type d -name '*.app' \( -path '*Traktor Pro 4*' -o -path '*Traktor Pro 3*' \) 2>/dev/null | head -1)"
echo "app: $APP"
# Traktor's own settings folder (Documents/Native Instruments/Traktor <version>), newest first
TD="$(ls -dt "$HOME/Documents/Native Instruments/Traktor "* 2>/dev/null | head -1)"
echo "settings folder: $TD"
CSI="$APP/Contents/Resources/qml/CSI"
echo "-- D2 folder:"; ls -la "$CSI/D2" "$CSI/D2/Api" 2>&1
echo "-- link address:"; head -1 "$CSI/D2/Api/ApiClient.js" 2>&1
echo "-- leftovers:"; ls -d "$CSI"/D2* 2>&1
echo "-- Traktor running:"; pgrep -lf "Traktor" 2>&1 | head -3
echo "-- GOOD MIXX running on 8770:"; lsof -nP -iTCP:8770 -sTCP:LISTEN 2>&1 | head -3
echo "-- GOOD MIXX answer:"; curl -s -m 3 http://localhost:8770/api/now | head -c 300; echo
echo "-- test message to GOOD MIXX:"; curl -s -m 3 -X POST -d '{}' http://localhost:8770/traktor/updateMasterClock; echo " (sent)"
curl -s -m 3 http://localhost:8770/api/now | grep -o '"traktor": [a-z]*'
echo "-- Traktor settings mention D2:"; grep -a -c "D2" "$TD/Traktor Settings.tsi" 2>&1
echo "-- Traktor logs:"; ls -t "$TD/Logs/"* 2>/dev/null | head -3
L="$(ls -t "$TD/Logs/"*/* "$TD/Logs/"* 2>/dev/null | grep -v '/$' | head -1)"
[ -f "$L" ] && grep -a -i -E "qml|d2|api|error|warn" "$L" | tail -40
} > "$OUT" 2>&1
echo ""
echo "================ RESULT ================"
ok=1
if [ -z "$APP" ]; then echo "NO  - Traktor Pro 4 or 3 isn't in Applications."; ok=0
else echo "YES - Traktor found."; fi
if [ -n "$APP" ] && grep -q "ApiModule" "$CSI/D2/D2.qml" 2>/dev/null && [ -f "$CSI/D2/Api/ApiClient.js" ]; then
  echo "YES - The Traktor link is installed."
else echo "NO  - The Traktor link isn't installed. Quit Traktor, then right-click \"Add Traktor Link\" > Open > Open."; ok=0; fi
if curl -s -m 3 http://localhost:8770/api/now >/dev/null; then echo "YES - GOOD MIXX is open."
else echo "NO  - GOOD MIXX isn't open. Open it, then check again."; ok=0; fi
if [ -n "$TD" ] && grep -a -q "D2" "$TD/Traktor Settings.tsi" 2>/dev/null; then echo "YES - Kontrol D2 is added in Traktor."
else echo "NO? - Kontrol D2 may not be added: Traktor > Preferences > Controller Manager > Add... > Traktor > Kontrol D2."; ok=0; fi
[ $ok = 1 ] && echo "Everything looks right. Load a song in Traktor and it should show in GOOD MIXX."
echo ""
echo "Full report saved to: Library > Logs > GOOD MIXX traktor check.txt (send it to whoever gave you GOOD MIXX)."
read -n 1 -s -r -p "Press any key to close."
