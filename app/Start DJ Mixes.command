#!/bin/bash
# Double-click to start DJ Mixes on this Mac. Works from wherever this folder lives.
cd "$(dirname "$0")" || exit 1
PY=""
for p in "./.venv/bin/python" /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if [ -x "$p" ] && "$p" -c "import sqlite3" >/dev/null 2>&1; then PY="$p"; break; fi
done
if [ -z "$PY" ] && xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 -c "import sqlite3" >/dev/null 2>&1; then PY=/usr/bin/python3; fi
if [ -z "$PY" ]; then
  echo ""
  echo "This Mac needs Python before DJ Mixes can run."
  echo "A window may pop up offering to install Apple's developer tools - click Install,"
  echo "wait for it to finish, then double-click this again."
  xcode-select --install >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi
"$PY" mixes_server.py
echo ""
read -n 1 -s -r -p "Press any key to close."
