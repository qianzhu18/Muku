#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
BUILD_TOOLS_VERSION="${BUILD_TOOLS_VERSION:-36.1.0}"
ANDROID_PLATFORM="${ANDROID_PLATFORM:-android-33}"
OUT_DIR="$ROOT_DIR/build"
GEN_DIR="$OUT_DIR/generated"
CLASS_DIR="$OUT_DIR/classes"
DEX_DIR="$OUT_DIR/dex"
APK_DIR="$OUT_DIR/apk"
KEYSTORE_PATH="$ROOT_DIR/signing/debug.keystore"
UNSIGNED_APK="$APK_DIR/muku-remote-unsigned.apk"
ALIGNED_APK="$APK_DIR/muku-remote-aligned.apk"
FINAL_APK="$APK_DIR/${FINAL_APK_NAME:-muku-muku.apk}"

AAPT2="$SDK_ROOT/build-tools/$BUILD_TOOLS_VERSION/aapt2"
D8="$SDK_ROOT/build-tools/$BUILD_TOOLS_VERSION/d8"
ZIPALIGN="$SDK_ROOT/build-tools/$BUILD_TOOLS_VERSION/zipalign"
APKSIGNER="$SDK_ROOT/build-tools/$BUILD_TOOLS_VERSION/apksigner"
ANDROID_JAR="$SDK_ROOT/platforms/$ANDROID_PLATFORM/android.jar"

for tool in "$AAPT2" "$D8" "$ZIPALIGN" "$APKSIGNER" "$ANDROID_JAR"; do
  if [[ ! -e "$tool" ]]; then
    echo "Missing Android tool: $tool" >&2
    exit 1
  fi
done

rm -rf "$OUT_DIR"
mkdir -p "$GEN_DIR" "$CLASS_DIR" "$DEX_DIR" "$APK_DIR"
mkdir -p "$(dirname "$KEYSTORE_PATH")"

if [[ -x "$ROOT_DIR/generate_icons.sh" && -f "$ROOT_DIR/assets/qianzhu-avatar.jpg" ]]; then
  "$ROOT_DIR/generate_icons.sh"
fi

"$AAPT2" compile \
  --dir "$ROOT_DIR/res" \
  -o "$OUT_DIR/compiled-res.zip"

"$AAPT2" link \
  --manifest "$ROOT_DIR/AndroidManifest.xml" \
  --java "$GEN_DIR" \
  -I "$ANDROID_JAR" \
  --auto-add-overlay \
  -R "$OUT_DIR/compiled-res.zip" \
  -o "$UNSIGNED_APK"

JAVA_SOURCES=()
while IFS= read -r source_file; do
  JAVA_SOURCES+=("$source_file")
done < <(find "$ROOT_DIR/src" "$GEN_DIR" -name '*.java' | sort)
if [[ "${#JAVA_SOURCES[@]}" -eq 0 ]]; then
  echo "No Java sources found." >&2
  exit 1
fi

javac \
  -source 8 \
  -target 8 \
  -Xlint:-options \
  -classpath "$ANDROID_JAR" \
  -d "$CLASS_DIR" \
  "${JAVA_SOURCES[@]}"

CLASS_FILES=()
while IFS= read -r class_file; do
  CLASS_FILES+=("$class_file")
done < <(find "$CLASS_DIR" -name '*.class' | sort)

"$D8" \
  --lib "$ANDROID_JAR" \
  --output "$DEX_DIR" \
  "${CLASS_FILES[@]}"

(
  cd "$DEX_DIR"
  zip -q -u "$UNSIGNED_APK" classes.dex
)

"$ZIPALIGN" -f 4 \
  "$UNSIGNED_APK" \
  "$ALIGNED_APK"

if [[ ! -f "$KEYSTORE_PATH" ]]; then
  keytool -genkeypair \
    -alias androiddebugkey \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storetype PKCS12 \
    -keystore "$KEYSTORE_PATH" \
    -storepass android \
    -keypass android \
    -dname "CN=Android Debug,O=Android,C=US"
fi

"$APKSIGNER" sign \
  --ks "$KEYSTORE_PATH" \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out "$FINAL_APK" \
  "$ALIGNED_APK"

"$APKSIGNER" verify "$FINAL_APK"

echo "$FINAL_APK"
