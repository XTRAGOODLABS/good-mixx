#!/bin/bash
# Checks each piece of the Traktor link and saves the results to a log file. Changes nothing.
cd "$(dirname "$0")" || exit 1
OUT="$HOME/Library/Logs/GOOD MIXX traktor check.txt"; mkdir -p "$HOME/Library/Logs"
{
echo "== $(date)"
APP="/Applications/Native Instruments/Traktor Pro 3/Traktor.app"
[ -d "$APP" ] || APP="$(find /Applications -maxdepth 4 -type d -name '*.app' -path '*Traktor Pro 3*' 2>/dev/null | head -1)"
echo "app: $APP"
CSI="$APP/Contents/Resources/qml/CSI"
echo "-- D2 folder:"; ls -la "$CSI/D2" "$CSI/D2/Api" 2>&1
echo "-- link address:"; head -1 "$CSI/D2/Api/ApiClient.js" 2>&1
echo "-- leftovers:"; ls -d "$CSI"/D2* 2>&1
echo "-- Traktor running:"; pgrep -lf "Traktor" 2>&1 | head -3
echo "-- DJ Mixes running on 8770:"; lsof -nP -iTCP:8770 -sTCP:LISTEN 2>&1 | head -3
echo "-- DJ Mixes answer:"; curl -s -m 3 http://localhost:8770/api/now | head -c 300; echo
echo "-- test message to DJ Mixes:"; curl -s -m 3 -X POST -d '{}' http://localhost:8770/traktor/updateMasterClock; echo " (sent)"
curl -s -m 3 http://localhost:8770/api/now | grep -o '"traktor": [a-z]*'
echo "-- Traktor settings mention D2:"; grep -a -c "D2" "$HOME/Documents/Native Instruments/Traktor 3.11.1/Traktor Settings.tsi" 2>&1
echo "-- Traktor logs:"; ls -t "$HOME/Documents/Native Instruments/Traktor 3.11.1/Logs/"* 2>/dev/null | head -3
L="$(ls -t "$HOME/Documents/Native Instruments/Traktor 3.11.1/Logs/"*/* "$HOME/Documents/Native Instruments/Traktor 3.11.1/Logs/"* 2>/dev/null | grep -v '/$' | head -1)"
[ -f "$L" ] && grep -a -i -E "qml|d2|api|error|warn" "$L" | tail -40
} > "$OUT" 2>&1
cat "$OUT"
echo ""; echo "Saved to your Library/Logs folder."
read -n 1 -s -r -p "Press any key to close."
