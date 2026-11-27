# Multi-stage Dockerfile for Helf: FastAPI + React PWA, and the Android app.
#
# Two images come out of it. `production` (web build + backend) is what `helf`
# and `helf-mcp` run, and never builds the Android stages. `android-signer`
# builds the APK (frontend-deps -> android-prep, android-versions ->
# android-build) and is what the one-shot `helf-apk` service runs to sign it
# onto the data volume.

# Nothing here is pinned (user rule): every base image is a floating tag that
# compose re-pulls (`build.pull: true`), and the Android toolchain resolves its
# newest stable release at build time. Breakage from an upstream release shows
# up as a failed build, never as a broken running container.

# Stage 1: Frontend dependencies, shared by the web build and the Android prep
# so `npm ci` runs once. The Capacitor CLI (`cap sync`, below) needs Node >= 22.
FROM node:alpine AS frontend-deps

WORKDIR /app/frontend

COPY frontend/package*.json ./

RUN npm ci --silent

# Stage 1a: Build frontend (React + Vite)
FROM frontend-deps AS frontend-build

# Copy frontend source
COPY frontend/ ./

# Build for production
RUN npm run build

# Stage 1b: Sync the Capacitor project (plan 0025).
#
# Only the native inputs are copied in: capacitor.config.ts and android/. The UI
# is loaded from the server at runtime (`server.url`, plan 0025 §3a), so the
# bundled web assets are never shown. `webDir` has to exist for `cap sync`, so
# it is a placeholder rather than the real `dist`. Bundling the real one would
# rebuild the APK on every UI change, which is the cost §3a exists to avoid.
# If `server.url` is ever removed, bundle the real dist here instead
# (COPY --from=frontend-build) and accept that cost.
FROM frontend-deps AS android-prep

COPY frontend/capacitor.config.ts ./
COPY frontend/android ./android
RUN mkdir dist && echo '<!doctype html><title>Helf</title>' > dist/index.html \
    && npx cap sync android

# Stage 1c: Resolve the newest stable Android toolchain.
#
# ADD of a URL is what makes this re-evaluate: the download's checksum is its
# cache key, so a changed index reruns the RUN below. Only the resolved
# versions leave this stage, and android-build COPYs them, which is keyed on
# content too: the SDK index changes for unrelated reasons (new canary
# platforms), and that must not rebuild the APK unless a version we use moved.
#
# - cmdline-tools: the linux archive of `cmdline-tools;latest`, with the SHA-1
#   Google's own index publishes for it.
# - build-tools: the highest plain X.Y.Z (no -rc).
# - compileSdk/targetSdk: the major of the highest numbered platform. AGP
#   downloads that platform itself during the build.
# - AGP: the highest plain X.Y.Z in Google's Maven (no alpha/beta/rc).
FROM debian:stable-slim AS android-versions

ADD https://dl.google.com/android/repository/repository2-3.xml /tmp/repo.xml
ADD https://dl.google.com/android/maven2/com/android/tools/build/gradle/maven-metadata.xml /tmp/agp.xml

RUN set -eu; \
    block="$(grep -A40 'path="cmdline-tools;latest"' /tmp/repo.xml)"; \
    zip="$(echo "$block" | grep -o 'commandlinetools-linux-[0-9]*_latest\.zip' | head -1)"; \
    sha1="$(echo "$block" | grep -B1 "$zip" | grep -o '[0-9a-f]\{40\}' | head -1)"; \
    bt="$(grep -o 'path="build-tools;[0-9]*\.[0-9]*\.[0-9]*"' /tmp/repo.xml | grep -o '[0-9.]*[0-9]' | sort -uV | tail -1)"; \
    sdk="$(grep -o 'path="platforms;android-[0-9][0-9.]*"' /tmp/repo.xml | grep -o '[0-9][0-9.]*' | sort -uV | tail -1 | cut -d. -f1)"; \
    agp="$(grep -o '<version>[0-9]*\.[0-9]*\.[0-9]*</version>' /tmp/agp.xml | sed 's/<[^>]*>//g' | sort -uV | tail -1)"; \
    for v in "$zip" "$sha1" "$bt" "$sdk" "$agp"; do [ -n "$v" ] || { echo "android-versions: could not resolve a version" >&2; exit 1; }; done; \
    printf 'CMDLINE_ZIP=%s\nCMDLINE_SHA1=%s\nBUILD_TOOLS=%s\nANDROID_SDK=%s\nAGP_VERSION=%s\n' \
      "$zip" "$sha1" "$bt" "$sdk" "$agp" > /versions.env; \
    cat /versions.env

# Stage 1d: Build the Android APK.
#
# gradle:latest brings the newest Gradle and the JDK it ships with; the repo has
# no Gradle wrapper, because a wrapper is a pinned Gradle version.
#
# linux/amd64 on purpose: the Android SDK's aapt2 is not published for
# linux/arm64, so on an Apple-silicon Mac this runs under emulation. The NAS is
# x86_64 and runs it natively.
FROM --platform=linux/amd64 gradle:latest AS android-build

ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk

RUN apt-get update && apt-get install -y --no-install-recommends unzip curl ca-certificates jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=android-versions /versions.env /versions.env

# The `android` CLI replaced `sdkmanager` (deprecated in cmdline-tools 23) and
# no longer needs licences accepted. Its package paths use `/`, not `;`.
RUN set -eu; . /versions.env; \
    curl -fsSL -o /tmp/cmdline-tools.zip "https://dl.google.com/android/repository/${CMDLINE_ZIP}"; \
    echo "${CMDLINE_SHA1}  /tmp/cmdline-tools.zip" | sha1sum -c -; \
    mkdir -p "$ANDROID_HOME/cmdline-tools"; \
    unzip -q /tmp/cmdline-tools.zip -d "$ANDROID_HOME/cmdline-tools"; \
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"; \
    rm /tmp/cmdline-tools.zip; \
    "$ANDROID_HOME/cmdline-tools/latest/bin/android" --sdk="$ANDROID_HOME" sdk install "build-tools/${BUILD_TOOLS}"; \
    test -f "$ANDROID_HOME/build-tools/${BUILD_TOOLS}/lib/apksigner.jar"

# The Android project reaches Capacitor and its plugins by relative path into
# node_modules (android/capacitor.settings.gradle), so those packages sit beside
# android/ exactly as they do in frontend/. Only the three Gradle references are
# copied, not all of node_modules: COPY is keyed on file content, so an
# unrelated npm dependency changing leaves this layer, and Gradle, cached.
WORKDIR /work
COPY --from=android-prep /app/frontend/android ./android
COPY --from=android-prep /app/frontend/node_modules/@capacitor/android ./node_modules/@capacitor/android
COPY --from=android-prep /app/frontend/node_modules/@capacitor-community/bluetooth-le ./node_modules/@capacitor-community/bluetooth-le
COPY --from=android-prep /app/frontend/node_modules/@capawesome-team/capacitor-android-foreground-service ./node_modules/@capawesome-team/capacitor-android-foreground-service

# Gradle signs with its own throwaway debug key here; the signer stage below
# replaces that signature with Helf's real one. The key is not available at
# image build time, and need not be: nothing built here is installed as is.
#
# AGP and the SDK level come in as -P properties (android/build.gradle,
# android/variables.gradle), so the repo names no version. The Gradle cache is
# a cache mount, not a layer.
RUN --mount=type=cache,target=/root/.gradle \
    set -eu; . /versions.env; \
    export GRADLE_USER_HOME=/root/.gradle; \
    (cd android && gradle --no-daemon \
        -PhelfAgpVersion="$AGP_VERSION" -PhelfAndroidSdk="$ANDROID_SDK" \
        assembleDebug); \
    out=android/app/build/outputs/apk/debug; \
    mkdir -p /out; \
    cp "$out/app-debug.apk" /out/helf-unsigned.apk; \
    cp "$ANDROID_HOME/build-tools/${BUILD_TOOLS}/lib/apksigner.jar" /out/apksigner.jar; \
    meta="$out/output-metadata.json"; \
    jq -n \
      --arg version_name "$(jq -r '.elements[0].versionName' "$meta")" \
      --argjson version_code "$(jq '.elements[0].versionCode' "$meta")" \
      '{version_name: $version_name, version_code: $version_code}' \
      > /out/version.json

# Stage 1e: Sign the APK with the key on the data volume.
#
# Run as the `helf-apk` compose service on every `up`, not at build time:
# a build cannot write to the host, and the key has to be created on the first
# run and kept. apksigner is pure Java, so this runs at the native platform;
# only apksigner.jar is taken from the SDK, not the SDK. eclipse-temurin has
# no floating JRE tag, so this is the JDK.
FROM eclipse-temurin:latest AS android-signer

RUN apt-get update && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=android-build /out/apksigner.jar /opt/apksigner.jar
COPY --from=android-build /out/helf-unsigned.apk /out/version.json /opt/helf-apk/
COPY scripts/sign-apk.sh /usr/local/bin/sign-apk.sh

CMD ["sh", "/usr/local/bin/sign-apk.sh"]

# Stage 2: Python dependencies
FROM python:slim AS backend-deps

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install UV for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy backend dependency files
COPY backend/pyproject.toml backend/README.md ./

# Install dependencies into a venv, including the `mcp` extra. A venv rather
# than the system site-packages because python:slim floats across minor
# versions, and copying /usr/local/lib/python3.X/ would name one. Both stages
# are the same python:slim pull, so the venv's interpreter link resolves.
#
# pyproject calls that extra out as something "the API image should not carry",
# which was true while the MCP server ran on the host over stdio (Plan 0006 §1).
# Once the helf-mcp service started building from this same Dockerfile, that
# stopped holding: one image serves both commands, so the extra has to be in it
# or `python -m app.mcp.qs_mcp` cannot import at all. Splitting the image back
# apart is the alternative if the API image's contents ever need to be minimal.
ENV UV_PYTHON_DOWNLOADS=never
RUN uv venv /opt/venv && VIRTUAL_ENV=/opt/venv uv pip install --no-cache ".[mcp]"

# Stage 3: Production
FROM python:slim AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    PYTHONPATH=/app \
    PRODUCTION=true

WORKDIR /app

# Copy Python packages from dependencies stage
COPY --from=backend-deps /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Copy backend code
COPY backend/app /app/app

# Migrations must be in the image: init_db() runs `alembic upgrade head` at
# startup, so a missing migrations/ or alembic.ini fails at container start
# rather than at build time.
COPY backend/alembic.ini /app/alembic.ini
COPY backend/migrations /app/migrations

# The MCP server loads its instructions from docs/design/ at startup and treats
# them as fatal if absent, so the image needs them or `app.mcp.qs_mcp` cannot
# run in a container at all. Copied to /app/docs so that walking up from
# /app/app/mcp/qs_mcp.py finds it, exactly as walking up from
# backend/app/mcp/qs_mcp.py finds the repo copy.
COPY docs/design /app/docs/design

# Copy frontend build
COPY --from=frontend-build /app/frontend/dist /app/static

# Create data directory
RUN mkdir -p /app/data

# 8080 is the API; 8081 is the MCP server when the mcp service overrides CMD.
EXPOSE 8080 8081

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health').read()"

# Run FastAPI with Uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
