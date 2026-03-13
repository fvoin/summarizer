#!/bin/bash
# Installs Summarizer.app to /Applications and removes the macOS quarantine.
# Double-click this file once — the app will launch automatically after install.

DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$DIR/Summarizer.app"
DEST="/Applications/Summarizer.app"

if [ ! -d "$SRC" ]; then
    echo "❌  Summarizer.app not found next to this script."
    echo "    Make sure both files are in the same folder."
    read -n1 -rsp "Press any key to exit…"
    exit 1
fi

echo "→ Copying Summarizer.app to /Applications…"
cp -R "$SRC" "$DEST"

echo "→ Removing macOS quarantine…"
xattr -dr com.apple.quarantine "$DEST"

echo ""
echo "✅  Done! Launching Summarizer from /Applications…"
open "$DEST"
