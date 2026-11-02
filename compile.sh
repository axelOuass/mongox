#!/bin/bash
# Compiles mongox to native/mongox with Nuitka. --dir builds native/mongox.dist/,
# which starts faster. Needs gcc, python3-dev, nuitka and patchelf.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/native"
JOBS="${JOBS:-$(nproc)}"

# The cache directory name. A new version unpacks to a new directory.
VERSION="${VERSION:-1.0.0}"

MODE=onefile
[ "$1" = "--dir" ] && MODE=dir

# zstandard lets Nuitka compress the payload of a single file build. Without
# it the build still works, only larger.
for module in nuitka patchelf zstandard; do
    if ! python3 -c "import $module" > /dev/null 2>&1; then
        echo "Installing $module..."
        python3 -m pip install --quiet "$module" \
            || python3 -m pip install --quiet --break-system-packages "$module"
    fi
done

if ! command -v gcc > /dev/null; then
    echo "error: gcc is required. sudo apt install build-essential python3-dev" >&2
    exit 1
fi

# Nuitka compiles pymongo from the installed copy.
if ! python3 -c "import pymongo" > /dev/null 2>&1; then
    echo "error: pymongo is not installed on this machine, so there is" >&2
    echo "       nothing to compile. Install it first:" >&2
    echo "       pip install --user pymongo" >&2
    exit 1
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# --onefile-tempdir-spec unpacks once per version. providers, ui and pymongo are
# included by name; dns and chardet are left out as unused.
if [ "$MODE" = "onefile" ]; then
    MODE_FLAGS=(--onefile
                --product-version="$VERSION"
                --onefile-tempdir-spec="{CACHE_DIR}/mongox/{VERSION}")
else
    MODE_FLAGS=(--standalone)
fi

python3 -m nuitka \
    "${MODE_FLAGS[@]}" \
    --assume-yes-for-downloads \
    --jobs="$JOBS" \
    --include-package=providers \
    --include-package=ui \
    --include-package=pymongo \
    --include-package=bson \
    --include-package=gridfs \
    --nofollow-import-to=dns \
    --nofollow-import-to=chardet \
    --output-dir="$OUTPUT_DIR" \
    --output-filename=mongox \
    --remove-output \
    "$SCRIPT_DIR/mongox.py"

if [ "$MODE" = "onefile" ]; then
    BINARY="$OUTPUT_DIR/mongox"
else
    BINARY="$OUTPUT_DIR/mongox.dist/mongox"
fi
chmod 755 "$BINARY"

echo
echo "Built $BINARY ($(du -h "$BINARY" | cut -f1))"
echo "Install it with: bash install_native.sh"
