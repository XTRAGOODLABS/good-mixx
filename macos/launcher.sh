#!/bin/bash
# GOOD MIXX - starts the mix-memory helper on this Mac and opens its window.
APP="$(cd "$(dirname "$0")/.." && pwd)"
RES="$APP/Resources/app"
PORT=8770
URL="http://localhost:$PORT/mixes"
LOG="$HOME/Library/Logs/GOOD MIXX.log"
mkdir -p "$HOME/Library/Logs"

say_box() { osascript -e "display dialog \"$1\" with title \"GOOD MIXX\" buttons {\"OK\"} default button 1 with icon note" >/dev/null 2>&1; }

open_window() {
  [ -n "$GM_NO_WINDOW" ] && return   # the GOOD MIXX app shows its own window
  for b in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"; do
    if [ -x "$b" ]; then nohup "$b" --app="$URL" --window-size=1366,880 >/dev/null 2>&1 & return; fi
  done
  open "$URL"
}

# Where your mixes are kept (outside the app, so updates never touch them)
if [ -z "$GOODMIXX_DATA" ]; then
  if [ -f "$HOME/Portal-Stems-FX/data/library.json" ]; then GOODMIXX_DATA="$HOME/Portal-Stems-FX/data"
  else GOODMIXX_DATA="$HOME/Library/Application Support/GOOD MIXX"; fi
fi
export GOODMIXX_DATA
mkdir -p "$GOODMIXX_DATA"

# Already running? Just open the window - but only if it's this version. After an update the old
# one is still running in the background, so it gets stopped and the new one starts instead.
VERSION="$(/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" "$APP/Info.plist" 2>/dev/null)"
RUNNING="$(curl -s -m 2 "http://localhost:$PORT/api/info")"
if echo "$RUNNING" | grep -q '"ipad"' && echo "$RUNNING" | grep -q "\"version\": \"$VERSION\""; then open_window; exit 0; fi

# An older DJ Mixes window holding the address is stopped (only ours).
for pid in $(lsof -nP -t -iTCP:$PORT -sTCP:LISTEN 2>/dev/null); do
  ps -p "$pid" -o command= | grep -q "mixes_server.py" && kill "$pid"
done
sleep 0.5
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  say_box "Another program on this Mac is using GOOD MIXX's address (port $PORT). Quit it and open GOOD MIXX again."
  exit 1
fi

PY=""
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if [ -x "$p" ] && "$p" -c "import sqlite3" >/dev/null 2>&1; then PY="$p"; break; fi
done
if [ -z "$PY" ] && xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 -c "import sqlite3" >/dev/null 2>&1; then PY=/usr/bin/python3; fi
if [ -z "$PY" ]; then
  xcode-select --install >/dev/null 2>&1
  say_box "GOOD MIXX needs Apple's free developer tools once. A window should offer to install them - click Install, wait for it to finish, then open GOOD MIXX again."
  exit 1
fi

cd "$RES" || exit 1
echo "== $(date) starting with $PY, data in $GOODMIXX_DATA" >> "$LOG"
nohup "$PY" -u mixes_server.py >> "$LOG" 2>&1 &
for i in $(seq 1 40); do
  curl -s -m 1 "http://localhost:$PORT/api/info" | grep -q '"ipad"' && break
  sleep 0.25
done
if ! curl -s -m 2 "http://localhost:$PORT/api/info" | grep -q '"ipad"'; then
  say_box "GOOD MIXX didn't start. Details are in your user Library > Logs > GOOD MIXX.log"
  exit 1
fi
open_window
exit 0
