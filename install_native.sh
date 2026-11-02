#!/bin/bash
# Installs the build from compile.sh: a single file onto PATH, or a directory
# into /opt/mongox with a symlink on PATH.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONEFILE="$SCRIPT_DIR/native/mongox"
DIST="$SCRIPT_DIR/native/mongox.dist"
TARGET="/opt/mongox"
LINK="/usr/local/bin/mongox"

if [ -f "$ONEFILE" ]; then
    # A previous directory install would leave a symlink at LINK pointing
    # into /opt, so both are removed before the file is placed.
    sudo rm -rf "$TARGET" "$LINK"
    sudo install -m 755 "$ONEFILE" "$LINK"
    echo "Installed $LINK ($(du -h "$ONEFILE" | cut -f1))"
    echo "It unpacks to ~/.cache/mongox on first run."

elif [ -x "$DIST/mongox" ]; then
    # Removed first, so files dropped in a later version do not linger.
    sudo rm -rf "$TARGET"
    sudo cp -r "$DIST" "$TARGET"
    sudo ln -sf "$TARGET/mongox" "$LINK"
    echo "Installed $TARGET ($(du -sh "$TARGET" | cut -f1))"
    echo "Linked $LINK"

else
    echo "error: no compiled build found in $SCRIPT_DIR/native" >&2
    echo "       run 'bash compile.sh' first" >&2
    exit 1
fi
