#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
SESSION_NAME="muku_pinggy"

tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
pkill -f 'a.pinggy.io' 2>/dev/null || true
rm -f "$RUNTIME_DIR/pinggy-url.txt"

echo "Stopped public tunnel."
