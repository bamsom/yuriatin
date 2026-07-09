#!/usr/bin/env bash
# serve the birdnest viewer + runs: http://127.0.0.1:8765/viewer/viewer.html
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m http.server "${1:-8765}" --bind 127.0.0.1
