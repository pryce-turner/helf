#!/bin/sh
#
# Sign the image's APK with Helf's own key, onto the data volume.
#
# Runs as the `helf-apk` compose service on every `up`. Helf serves whatever is
# in $DATA/android/ and says `available: false` until it exists, so nothing here
# can stop Helf starting.
#
# Android installs an update only over an app signed by the same key, so the
# key is created once, on the first run, and kept. This script never overwrites
# or deletes it. Losing it means uninstalling the app to update.
#
set -eu

DATA="${DATA_DIR:-/app/data}/android"
SRC="${APK_SRC:-/opt/helf-apk}"
APKSIGNER="${APKSIGNER_JAR:-/opt/apksigner.jar}"
KEYSTORE="$DATA/signing.keystore"
ALIAS=helf
# The password protects nothing: it sits beside the key on the same volume, so
# anyone who can read one can read the other. A fixed value keeps the first
# run unattended.
PASS=android

mkdir -p "$DATA"

if [ ! -f "$KEYSTORE" ]; then
    tmp="$KEYSTORE.tmp.$$"
    keytool -genkeypair -keystore "$tmp" -storetype PKCS12 \
        -storepass "$PASS" -keypass "$PASS" -alias "$ALIAS" \
        -keyalg RSA -keysize 2048 -validity 10950 \
        -dname "CN=Helf,O=Helf" >/dev/null 2>&1
    mv "$tmp" "$KEYSTORE"
    echo "sign-apk: generated $KEYSTORE"
fi

# Lower-case hex, no colons: the form apksigner prints.
cert_sha256="$(keytool -list -v -keystore "$KEYSTORE" -storepass "$PASS" -alias "$ALIAS" \
    | sed -n 's/^[[:space:]]*SHA256:[[:space:]]*//p' | tr -d ':' | tr 'A-F' 'a-f')"
[ -n "$cert_sha256" ] || { echo "sign-apk: could not read the key's fingerprint" >&2; exit 1; }
source_sha256="$(sha256sum "$SRC/helf-unsigned.apk" | cut -d' ' -f1)"

if [ -f "$DATA/helf.apk" ] && [ -f "$DATA/helf-apk.json" ] \
    && [ "$(jq -r .source_sha256 "$DATA/helf-apk.json")" = "$source_sha256" ] \
    && [ "$(jq -r .cert_sha256 "$DATA/helf-apk.json")" = "$cert_sha256" ]; then
    echo "sign-apk: up to date (source ${source_sha256%"${source_sha256#????????}"}, key ${cert_sha256%"${cert_sha256#????????}"}), skipped"
    exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp "$SRC/helf-unsigned.apk" "$work/helf.apk"
java -jar "$APKSIGNER" sign --ks "$KEYSTORE" --ks-pass "pass:$PASS" \
    --ks-key-alias "$ALIAS" --key-pass "pass:$PASS" "$work/helf.apk"
java -jar "$APKSIGNER" verify "$work/helf.apk"

jq -n \
    --slurpfile v "$SRC/version.json" \
    --argjson size_bytes "$(stat -c %s "$work/helf.apk")" \
    --arg sha256 "$(sha256sum "$work/helf.apk" | cut -d' ' -f1)" \
    --arg source_sha256 "$source_sha256" \
    --arg cert_sha256 "$cert_sha256" \
    --arg built_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '$v[0] + {size_bytes: $size_bytes, sha256: $sha256, source_sha256: $source_sha256, cert_sha256: $cert_sha256, built_at: $built_at}' \
    > "$work/helf-apk.json"

# Temp file plus mv, on the volume's own filesystem, so a download never sees
# half a file. The APK moves first: the metadata is what says "up to date".
cp "$work/helf.apk" "$DATA/.helf.apk.new"
cp "$work/helf-apk.json" "$DATA/.helf-apk.json.new"
mv "$DATA/.helf.apk.new" "$DATA/helf.apk"
mv "$DATA/.helf-apk.json.new" "$DATA/helf-apk.json"
echo "sign-apk: signed helf.apk with key ${cert_sha256}"
