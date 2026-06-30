#!/usr/bin/env bash
# Build the itch.io-ready HTML5 bundle.
#
# Produces build/web/ (loose files) and build/web.zip (for upload).
# The zip is repacked after pygbag finishes because pygbag's own --archive
# only bundles index.html / favicon.png / .apk, missing the .tar.gz
# fallback that the browser index.html references — without it an apk
# parse failure in the browser gives a silent blank screen.

set -euo pipefail

# Resolve repo root (this script is in scripts/).
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

APP_NAME="foodchain"
APP_TITLE="Food Chain"

echo ">> cleaning previous build"
rm -rf build/web build/web.zip
mkdir -p build/web

echo ">> pygbag build (this may download the CDN template on first run)"
python3 -m pygbag \
    --build --archive \
    --app_name "$APP_NAME" \
    --title "$APP_TITLE" \
    --package "$APP_NAME" \
    --template pygbag/default.tmpl \
    main.py

echo ">> adding foodchain.tar.gz to build/web.zip"
(cd build/web && zip -q ../web.zip foodchain.tar.gz)

echo
echo ">> done"
echo
unzip -l build/web.zip | sed 's/^/   /'
echo
echo "   upload build/web.zip to itch.io (HTML5 project, viewport 1004x556)"
