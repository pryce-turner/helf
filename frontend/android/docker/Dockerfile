# Android build image for Helf: JDK 21 + Android SDK, nothing else.
#
# Build and run with --platform linux/amd64. The Android SDK's aapt2 is not
# published for linux/arm64, so on an Apple-silicon Mac this runs under Rosetta
# emulation. scripts/build-android.sh passes the flag; do it by hand too.
FROM eclipse-temurin:21-jdk

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

RUN apt-get update && apt-get install -y --no-install-recommends unzip curl ca-certificates \
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
