#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT_DIR"
BIND_HOST="${MUKU_BIND_HOST:-0.0.0.0}"
WEB_PORT="${MUKU_WEB_PORT:-5657}"

if command -v tailscale >/dev/null 2>&1; then
  tailscale up >/dev/null
fi

MUKU_BIND_HOST="$BIND_HOST" MUKU_WEB_PORT="$WEB_PORT" docker compose up -d

TAILSCALE_IP=""
TAILSCALE_DNS=""
if command -v tailscale >/dev/null 2>&1; then
  TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
  TAILSCALE_DNS="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; data=json.load(sys.stdin); print((data.get("Self",{}).get("DNSName","") or "").rstrip("."))' 2>/dev/null || true)"
fi

echo "Muku Web UI is listening on ${BIND_HOST}:${WEB_PORT}"
if [[ -n "$TAILSCALE_IP" ]]; then
  echo "Tailscale URL: http://${TAILSCALE_IP}:${WEB_PORT}"
fi
if [[ -n "$TAILSCALE_DNS" ]]; then
  echo "MagicDNS URL: http://${TAILSCALE_DNS}:${WEB_PORT}"
fi
