#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
SESSION_NAME="muku_pinggy"
URL_FILE="$RUNTIME_DIR/pinggy-url.txt"
WEB_PORT="${MUKU_WEB_PORT:-5657}"

mkdir -p "$RUNTIME_DIR"

cd "$ROOT_DIR"
"$ROOT_DIR/start-tailnet-webui.sh" >/dev/null

tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
pkill -f 'a.pinggy.io' 2>/dev/null || true

tmux new-session -d -s "$SESSION_NAME" \
  "cd \"$ROOT_DIR\" && ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 -R0:localhost:${WEB_PORT} a.pinggy.io"

PUBLIC_URL=""
for _ in {1..30}; do
  if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    break
  fi

  PUBLIC_URL="$(tmux capture-pane -pt "$SESSION_NAME" | grep -oE 'https://[^[:space:]]+pinggy-free\.link' | head -n 1 || true)"
  if [[ -n "$PUBLIC_URL" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Public tunnel did not start cleanly. Recent log:" >&2
  tmux capture-pane -pt "$SESSION_NAME" | tail -n 40 >&2 || true
  exit 1
fi

printf '%s\n' "$PUBLIC_URL" >"$URL_FILE"
echo "Public URL: $PUBLIC_URL"
echo "Session: $SESSION_NAME"
echo "URL file: $URL_FILE"
