#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# IMPORTANT: bump APP_VERSION in summarizer/config.py before each release.
# The GitHub release tag (e.g. v1.6) must match APP_VERSION.
echo "=== Summarizer build ==="

# 1. Create / activate venv
if [ ! -d ".venv" ]; then
    echo "Creating virtualenv…"
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Install dependencies
echo "Installing Python dependencies…"
pip install --upgrade pip -q
pip install -r requirements.txt -q

# On Intel (x86_64) ctranslate2 4.7+ has no wheel — downgrade to last known x86_64 wheel
if [ "$(uname -m)" = "x86_64" ]; then
    echo "Intel Mac detected — pinning ctranslate2 to x86_64 compatible version…"
    pip install "ctranslate2==4.6.0" -q --force-reinstall
fi

# 3. Download static ffmpeg binary matching current architecture
FFMPEG_DIR="bundled_ffmpeg"
if [ ! -f "$FFMPEG_DIR/ffmpeg" ]; then
    mkdir -p "$FFMPEG_DIR"
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        echo "Downloading static ffmpeg (Apple Silicon)…"
        curl -L "https://www.osxexperts.net/ffmpeg80arm.zip" -o "$FFMPEG_DIR/ffmpeg.zip"
    else
        echo "Downloading static ffmpeg (Intel)…"
        curl -L "https://www.osxexperts.net/ffmpeg80intel.zip" -o "$FFMPEG_DIR/ffmpeg.zip"
    fi
    unzip -o "$FFMPEG_DIR/ffmpeg.zip" -d "$FFMPEG_DIR"
    rm -f "$FFMPEG_DIR/ffmpeg.zip"
    chmod +x "$FFMPEG_DIR/ffmpeg"
    xattr -dr com.apple.quarantine "$FFMPEG_DIR/ffmpeg" 2>/dev/null || true
fi
echo "ffmpeg: $FFMPEG_DIR/ffmpeg ($(file -b "$FFMPEG_DIR/ffmpeg" | head -c 60))"

# 4. Pre-download Whisper model (base) into local cache
echo "Pre-downloading Whisper model (base)…"
python3 -c "
from summarizer.transcriber import download_model
download_model('base')
"

# 5. Find the cached model directory
WHISPER_CACHE="$HOME/.summarizer/models/base"
if [ ! -f "$WHISPER_CACHE/model.bin" ]; then
    echo 'ERROR: model not found at $WHISPER_CACHE' >&2
    exit 1
fi
echo "Whisper model cache: $WHISPER_CACHE"

# 6. Generate app icon (.icns for macOS)
echo "Generating app icon…"
ICON_PNG="summarizer/icon.png"
if [ ! -f "$ICON_PNG" ]; then
    python3 -c "
from summarizer.app import _make_app_icon
pm = _make_app_icon(512)
pm.save('$ICON_PNG', 'PNG')
print('Generated $ICON_PNG')
"
fi
ICON_ARG=""
if command -v sips &>/dev/null && command -v iconutil &>/dev/null; then
    ICONSET_DIR="Summarizer.iconset"
    mkdir -p "$ICONSET_DIR"
    for sz in 16 32 64 128 256 512; do
        sips -z $sz $sz "$ICON_PNG" --out "$ICONSET_DIR/icon_${sz}x${sz}.png" &>/dev/null
        dbl=$((sz * 2))
        if [ $dbl -le 1024 ]; then
            sips -z $dbl $dbl "$ICON_PNG" --out "$ICONSET_DIR/icon_${sz}x${sz}@2x.png" &>/dev/null
        fi
    done
    iconutil -c icns "$ICONSET_DIR" -o Summarizer.icns 2>/dev/null && ICON_ARG="--icon Summarizer.icns"
    rm -rf "$ICONSET_DIR"
fi

# 7. Build with PyInstaller
echo "Building Summarizer.app with PyInstaller…"
pyinstaller \
    --windowed \
    --name "Summarizer" \
    --noconfirm \
    --clean \
    $ICON_ARG \
    --add-data "$FFMPEG_DIR/ffmpeg:ffmpeg" \
    --add-data "$WHISPER_CACHE:whisper_model" \
    --hidden-import "google.generativeai" \
    --hidden-import "anthropic" \
    --hidden-import "openai" \
    --hidden-import "faster_whisper" \
    --hidden-import "sounddevice" \
    --hidden-import "soundfile" \
    --hidden-import "numpy" \
    --hidden-import "ctranslate2" \
    --hidden-import "tokenizers" \
    --hidden-import "huggingface_hub" \
    --collect-all "faster_whisper" \
    --collect-all "ctranslate2" \
    --collect-all "sounddevice" \
    --collect-all "google.protobuf" \
    --collect-all "google.generativeai" \
    --exclude-module "onnxruntime" \
    --exclude-module "sympy" \
    --exclude-module "matplotlib" \
    --exclude-module "PIL" \
    --exclude-module "pygments" \
    run.py

# 8. Inject microphone permission into Info.plist
echo "Patching Info.plist for microphone access…"
PLIST="dist/Summarizer.app/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    /usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string 'Summarizer needs microphone access to record audio for transcription.'" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription 'Summarizer needs microphone access to record audio for transcription.'" "$PLIST"
fi

# 9. Deep codesign: sign every binary inside-out so macOS PAC checks pass
echo "Code-signing all binaries inside the bundle…"
APP="dist/Summarizer.app"
ENT="entitlements.plist"

# Sign all .so, .dylib files first (leaves)
find "$APP" -name "*.so" -o -name "*.dylib" | while read -r f; do
    codesign --force --sign - --options runtime --entitlements "$ENT" "$f" 2>/dev/null || true
done

# Sign all .framework bundles
find "$APP" -name "*.framework" -type d | while read -r f; do
    codesign --force --sign - --options runtime --entitlements "$ENT" "$f" 2>/dev/null || true
done

# Sign the main executable
codesign --force --sign - --options runtime --entitlements "$ENT" "$APP/Contents/MacOS/Summarizer" 2>/dev/null || true

# Sign the top-level app bundle
codesign --force --sign - --options runtime --entitlements "$ENT" "$APP"

echo "Verifying signature…"
codesign --verify --deep --strict "$APP" && echo "  ✓ Signature valid" || echo "  ⚠ Signature has warnings (ad-hoc expected)"

# 10. Create DMG installer
echo "Creating DMG installer…"
# Use DMG_NAME env var if set (from CI), otherwise default based on arch
if [ -z "${DMG_NAME:-}" ]; then
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        DMG_NAME="Summarizer-AppleSilicon.dmg"
    else
        DMG_NAME="Summarizer-Intel.dmg"
    fi
fi
DMG_FINAL="dist/$DMG_NAME"
DMG_STAGING="dist/dmg_staging"

rm -f "$DMG_FINAL"
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"

cp -R "$APP" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

hdiutil create -volname "Summarizer" -srcfolder "$DMG_STAGING" \
    -ov -format UDZO "$DMG_FINAL" -quiet

rm -rf "$DMG_STAGING"

echo ""
echo "=== Build complete ==="
echo "App:  $APP  ($(du -sh "$APP" | cut -f1))"
echo "DMG:  $DMG_FINAL  ($(du -sh "$DMG_FINAL" | cut -f1))"
echo ""
echo "Users: open DMG → drag Summarizer to Applications → launch from Applications."
