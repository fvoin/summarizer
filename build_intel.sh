#!/usr/bin/env bash
# Build Summarizer.app for Intel x86_64 Macs (via Rosetta on Apple Silicon).
# Requires: macOS with Rosetta, python.org Python 3.11 (universal2 installer).
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
VENV=".venv_intel"

echo "=== Summarizer Intel (x86_64) build ==="

# 1. Verify Rosetta + Python
if ! arch -x86_64 "$PYTHON" -c "import platform; assert platform.machine() == 'x86_64'" 2>/dev/null; then
    echo "ERROR: Cannot run Python as x86_64. Install Rosetta:"
    echo "  softwareupdate --install-rosetta --agree-to-license"
    exit 1
fi

# 2. Create x86_64-only venv
if [ ! -d "$VENV" ]; then
    echo "Creating x86_64 virtualenv…"
    arch -x86_64 "$PYTHON" -m venv --copies "$VENV"
    # Strip arm64 slice so pip and PyInstaller stay in x86_64
    lipo "$VENV/bin/python3" -extract x86_64 -output "$VENV/bin/python3_x86"
    mv "$VENV/bin/python3_x86" "$VENV/bin/python3"
    chmod +x "$VENV/bin/python3"
    cp "$VENV/bin/python3" "$VENV/bin/python3.11"
fi
source "$VENV/bin/activate"
echo "Python arch: $(python3 -c 'import platform; print(platform.machine())')"

# 3. Install deps — force x86_64 wheels for native packages
echo "Installing Python dependencies…"
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Force x86_64 native packages
X86_PKGS=(
    "ctranslate2==4.6.0"
    "numpy"
    "PyQt6==6.10.2"
    "PyQt6-Qt6==6.10.2"
    "PyQt6-sip"
)
for pkg in "${X86_PKGS[@]}"; do
    echo "  Reinstalling $pkg (x86_64)…"
    pip download "$pkg" \
        --platform macosx_10_13_x86_64 --platform macosx_10_14_universal2 --platform macosx_10_9_x86_64 \
        --python-version 311 --only-binary=:all: --no-deps \
        -d /tmp/x86_wheels -q 2>/dev/null || true
done
if ls /tmp/x86_wheels/*.whl 1>/dev/null 2>&1; then
    pip install /tmp/x86_wheels/*.whl --force-reinstall --no-deps -q
fi
rm -rf /tmp/x86_wheels

# Verify critical lib is x86_64
CT2_SO=$(find "$VENV" -name "_ext.cpython-311-darwin.so" | head -1)
if [ -n "$CT2_SO" ]; then
    CT2_ARCH=$(file "$CT2_SO")
    echo "  ctranslate2: $CT2_ARCH"
    if ! echo "$CT2_ARCH" | grep -q "x86_64"; then
        echo "ERROR: ctranslate2 is not x86_64!"
        exit 1
    fi
fi

# 4. ffmpeg for Intel
FFMPEG_DIR="bundled_ffmpeg_intel"
if [ ! -f "$FFMPEG_DIR/ffmpeg" ]; then
    mkdir -p "$FFMPEG_DIR"
    echo "Downloading static ffmpeg (Intel)…"
    curl -L "https://www.osxexperts.net/ffmpeg80intel.zip" -o "$FFMPEG_DIR/ffmpeg.zip"
    unzip -o "$FFMPEG_DIR/ffmpeg.zip" -d "$FFMPEG_DIR"
    rm -f "$FFMPEG_DIR/ffmpeg.zip"
    chmod +x "$FFMPEG_DIR/ffmpeg"
    xattr -dr com.apple.quarantine "$FFMPEG_DIR/ffmpeg" 2>/dev/null || true
fi
echo "ffmpeg: $FFMPEG_DIR/ffmpeg ($(file -b "$FFMPEG_DIR/ffmpeg" | head -c 60))"

# 5. Whisper model
echo "Pre-downloading Whisper model (base)…"
python3 -c "from summarizer.transcriber import download_model; download_model('base')"

WHISPER_CACHE="$HOME/.summarizer/models/base"
if [ ! -f "$WHISPER_CACHE/model.bin" ]; then
    echo "ERROR: model not found at $WHISPER_CACHE" >&2
    exit 1
fi

# 6. App icon
ICON_PNG="summarizer/icon.png"
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

# 7. Build with PyInstaller (x86_64)
echo "Building Summarizer.app (x86_64)…"
pyinstaller \
    --windowed \
    --name "Summarizer" \
    --noconfirm \
    --clean \
    --target-arch x86_64 \
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
    --collect-data "certifi" \
    --exclude-module "onnxruntime" \
    --exclude-module "sympy" \
    --exclude-module "matplotlib" \
    --exclude-module "PIL" \
    --exclude-module "pygments" \
    run.py

# 8. Patch Info.plist
PLIST="dist/Summarizer.app/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    /usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string 'Summarizer needs microphone access to record audio for transcription.'" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription 'Summarizer needs microphone access to record audio for transcription.'" "$PLIST"
fi

# 9. Codesign
echo "Code-signing…"
APP="dist/Summarizer.app"
ENT="entitlements.plist"
find "$APP" -name "*.so" -o -name "*.dylib" | while read -r f; do
    codesign --force --sign - --options runtime --entitlements "$ENT" "$f" 2>/dev/null || true
done
find "$APP" -name "*.framework" -type d | while read -r f; do
    codesign --force --sign - --options runtime --entitlements "$ENT" "$f" 2>/dev/null || true
done
codesign --force --sign - --options runtime --entitlements "$ENT" "$APP/Contents/MacOS/Summarizer" 2>/dev/null || true
codesign --force --sign - --options runtime --entitlements "$ENT" "$APP"
codesign --verify --deep --strict "$APP" && echo "  ✓ Signature valid" || echo "  ⚠ Signature has warnings"

# 10. Verify arch
MAIN_BIN="$APP/Contents/MacOS/Summarizer"
echo "Binary arch: $(file -b "$MAIN_BIN" | head -c 60)"

# 11. Create DMG
echo "Creating DMG…"
DMG_FINAL="dist/Summarizer-Intel.dmg"
DMG_STAGING="dist/dmg_staging_intel"
rm -f "$DMG_FINAL"
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"
cp -R "$APP" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"
hdiutil create -volname "Summarizer" -srcfolder "$DMG_STAGING" -ov -format UDZO "$DMG_FINAL" -quiet
rm -rf "$DMG_STAGING"

echo ""
echo "=== Intel build complete ==="
echo "App:  $APP  ($(du -sh "$APP" | cut -f1))"
echo "DMG:  $DMG_FINAL  ($(du -sh "$DMG_FINAL" | cut -f1))"
