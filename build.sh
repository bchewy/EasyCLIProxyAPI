#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
export GOTELEMETRY=off
python3 scripts/build-private-core.py "$@"
bun install --frozen-lockfile --ignore-scripts
bun tauri build --no-bundle
bun scripts/portable.mjs --binary "$ROOT_DIR/src-tauri/target/release/cpa-gui" --output "$ROOT_DIR/bin-work"
printf 'Private build: %s/bin-work/EasyCLIProxyAPI\n' "$ROOT_DIR"
