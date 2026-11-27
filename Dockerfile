# Multi-stage Dockerfile for Helf: FastAPI + React PWA, and the Android app.
#
# Two images come out of it. `production` (web build + backend) is what `helf`
# and `helf-mcp` run, and never builds the Android stages. `android-signer`
# builds the APK (frontend-deps -> android-prep -> android-build) and is what
# the one-shot `helf-apk` service runs to sign it onto the data volume.

# Stage 1: Frontend dependencies, shared by the web build and the Android prep
# so `npm ci` runs once.
#
# Node 24, the current LTS: the Capacitor CLI (`cap sync`, below) requires
# Node >= 22, and Node 20 is end-of-life. It also matches the Node the Mac
# develops on.
FROM node:24-alpine AS frontend-deps

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

# Stage 1c: Build the Android APK.
#
# linux/amd64 on purpose: the Android SDK's aapt2 is not published for
# linux/arm64, so on an Apple-silicon Mac this runs under emulation. The NAS is
# x86_64 and runs it natively.
FROM --platform=linux/amd64 eclipse-temurin:21-jdk AS android-build

ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools

# Pinned to the build listed on developer.android.com/studio (2026-11), which
# publishes this SHA-256 beside the download. Bumping the version means
# re-reading both from that page.
ARG CMDLINE_TOOLS_VERSION=15859902
ARG CMDLINE_TOOLS_SHA256=4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583
# AGP 8.13 defaults to build-tools 36.0.0; compileSdk/targetSdk is 36.
ARG BUILD_TOOLS=36.0.0
ARG PLATFORM=android-36

RUN apt-get update && apt-get install -y --no-install-recommends unzip curl ca-certificates jq \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/cmdline-tools.zip \
      "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS_VERSION}_latest.zip" \
    && echo "${CMDLINE_TOOLS_SHA256}  /tmp/cmdline-tools.zip" | sha256sum -c - \
    && mkdir -p "$ANDROID_HOME/cmdline-tools" \
    && unzip -q /tmp/cmdline-tools.zip -d "$ANDROID_HOME/cmdline-tools" \
    && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
    && rm /tmp/cmdline-tools.zip

# Licences accepted here, in the image, with the user's approval.
RUN yes | sdkmanager --licenses >/dev/null \
    && sdkmanager "platform-tools" "platforms;${PLATFORM}" "build-tools;${BUILD_TOOLS}"

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
# gradlew is not executable in git, so it runs through sh. The Gradle cache is
# a cache mount, not a layer.
RUN --mount=type=cache,target=/root/.gradle \
    set -eu; \
    (cd android && sh ./gradlew --no-daemon assembleDebug); \
    out=android/app/build/outputs/apk/debug; \
    mkdir -p /out; \
    cp "$out/app-debug.apk" /out/helf-unsigned.apk; \
    meta="$out/output-metadata.json"; \
    jq -n \
      --arg version_name "$(jq -r '.elements[0].versionName' "$meta")" \
      --argjson version_code "$(jq '.elements[0].versionCode' "$meta")" \
      '{version_name: $version_name, version_code: $version_code}' \
      > /out/version.json

# Stage 1d: Sign the APK with the key on the data volume.
#
# Run as the `helf-apk` compose service on every `up`, not at build time:
# a build cannot write to the host, and the key has to be created on the first
# run and kept. apksigner is pure Java, so this runs at the native platform;
# only apksigner.jar is taken from the SDK, not the SDK.
FROM eclipse-temurin:21-jre AS android-signer

RUN apt-get update && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=android-build /opt/android-sdk/build-tools/36.0.0/lib/apksigner.jar /opt/apksigner.jar
COPY --from=android-build /out/helf-unsigned.apk /out/version.json /opt/helf-apk/
COPY scripts/sign-apk.sh /usr/local/bin/sign-apk.sh

CMD ["sh", "/usr/local/bin/sign-apk.sh"]

# Stage 2: Python dependencies
FROM python:3.12-slim AS backend-deps

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

# Install dependencies to system Python, including the `mcp` extra.
#
# pyproject calls that extra out as something "the API image should not carry",
# which was true while the MCP server ran on the host over stdio (Plan 0006 §1).
# Once the helf-mcp service started building from this same Dockerfile, that
# stopped holding: one image serves both commands, so the extra has to be in it
# or `python -m app.mcp.qs_mcp` cannot import at all. Splitting the image back
# apart is the alternative if the API image's contents ever need to be minimal.
RUN uv pip install --system --no-cache ".[mcp]"

# Stage 3: Production
FROM python:3.12-slim AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    PYTHONPATH=/app \
    PRODUCTION=true

WORKDIR /app

# Copy Python packages from dependencies stage
COPY --from=backend-deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

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
