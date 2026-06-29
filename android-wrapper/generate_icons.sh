#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_IMAGE="${1:-$ROOT_DIR/assets/qianzhu-avatar.jpg}"

if [[ ! -f "$SOURCE_IMAGE" ]]; then
  echo "Missing source image: $SOURCE_IMAGE" >&2
  exit 1
fi

for spec in \
  "mipmap-mdpi:48" \
  "mipmap-hdpi:72" \
  "mipmap-xhdpi:96" \
  "mipmap-xxhdpi:144" \
  "mipmap-xxxhdpi:192"
do
  bucket="${spec%%:*}"
  size="${spec##*:}"
  target_dir="$ROOT_DIR/res/$bucket"
  mkdir -p "$target_dir"
  sips -s format png -z "$size" "$size" "$SOURCE_IMAGE" --out "$target_dir/ic_launcher.png" >/dev/null
  cp "$target_dir/ic_launcher.png" "$target_dir/ic_launcher_round.png"
done

echo "Generated launcher icons from $SOURCE_IMAGE"
