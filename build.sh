#!/bin/bash
# Packs the sources and pymongo into one executable zip at dist/mongox.
# Needs python3 on the target. --no-bundle leaves pymongo out.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING="$(mktemp -d)"
OUTPUT="$SCRIPT_DIR/dist/mongox"
BUNDLE=1
[ "$1" = "--no-bundle" ] && BUNDLE=0
trap 'rm -rf "$STAGING"' EXIT

# Modules to pack. A .vps profile is configuration read at runtime from the
# working directory or ~/.config/mongox, so it is not part of the archive.
cp "$SCRIPT_DIR"/*.py "$STAGING/"
cp -r "$SCRIPT_DIR/providers" "$SCRIPT_DIR/ui" "$STAGING/"

if [ "$BUNDLE" = "1" ]; then
    if python3 -m pip --version > /dev/null 2>&1; then
        echo "Fetching pymongo..."
        python3 -m pip install --quiet --target "$STAGING" pymongo
        # zipimport cannot load .so files and pymongo runs without them.
        # dist-info is packaging metadata.
        find "$STAGING" \( -name '*.so' -o -name '*.dist-info' \) \
            -exec rm -rf {} + 2>/dev/null || true
    else
        echo "warning: pip is not available, building without pymongo." >&2
        echo "         The built file will install it at first run." >&2
    fi
fi

# Stops on a syntax error before packing.
python3 -m compileall -q "$STAGING"/*.py "$STAGING/providers" "$STAGING/ui" > /dev/null

# compileall writes __pycache__ directories. They are removed after the check
# so that only source files are packed.
find "$STAGING" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# -m mongox:main generates a __main__.py that imports mongox and calls main().
# -p writes the shebang line.
mkdir -p "$SCRIPT_DIR/dist"
python3 -m zipapp "$STAGING" \
    -o "$OUTPUT" \
    -p "/usr/bin/env python3" \
    -m "mongox:main"

chmod 755 "$OUTPUT"
echo "Built $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
