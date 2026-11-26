#!/usr/bin/env bash
#
# Build the Android debug APK inside Docker, so the Mac needs no JDK or SDK.
#
# The container runs linux/amd64 (Rosetta on Apple silicon) because aapt2 has no
# linux/arm64 build. The Gradle cache lives in the named volume
# helf-android-gradle, so only the first run downloads dependencies.
#
# The whole frontend/ directory is mounted, not just android/: the Android
# project reaches Capacitor and its plugins through relative paths into
# frontend/node_modules.
#
# Usage:
#   scripts/build-android.sh
#
# Output: frontend/android/app/build/outputs/apk/debug/app-debug.apk
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend="$repo_root/frontend"
image="helf-android-build:latest"
platform="linux/amd64"
apk="$frontend/android/app/build/outputs/apk/debug/app-debug.apk"

if ! docker info >/dev/null 2>&1; then
    echo "build-android: docker is not running" >&2
    exit 1
fi

# Cached after the first build; rebuilds only when the Dockerfile changes.
docker build --platform "$platform" -t "$image" "$frontend/android/docker"

# Web assets are built and synced on the host, where node_modules already is.
# Run `npm ci` yourself first on a fresh clone.
(cd "$frontend" && npm run build && npx cap sync android)

# gradlew is not executable in git, so it is run through sh rather than chmod-ed.
docker run --rm --platform "$platform" \
    -v "$frontend:/work" \
    -v helf-android-gradle:/root/.gradle \
    -w /work/android \
    "$image" \
    sh ./gradlew --no-daemon assembleDebug

echo "build-android: $apk"
