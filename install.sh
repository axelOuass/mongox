#!/bin/bash
# Builds the binary and installs it as the 'mongox' command.
set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
bash "$SCRIPT_DIR/build.sh"
sudo install -m 755 "$SCRIPT_DIR/dist/mongox" /usr/local/bin/mongox
echo "Installed /usr/local/bin/mongox"
