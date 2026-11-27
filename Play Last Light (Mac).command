#!/bin/bash
# Double-click me to play Last Light (the first time: right-click -> Open). Checks for updates first.
cd "$(dirname "$0")"
for py in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    exec "$py" play.py "$@"
  fi
done
echo "Last Light needs Python 3.10 or newer, and this Mac doesn't have it yet."
echo "Opening the Python download page: install it, then double-click this file again."
open "https://www.python.org/downloads/macos/"
read -p "Press ENTER to close this window."
