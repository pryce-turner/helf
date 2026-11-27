#!/bin/sh
#
# Publish the image's watch app onto the data volume (plan 0026).
#
# Runs as the `helf-watch-app` compose service on every `up`, like helf-apk.
# Helf serves whatever is in $DATA/watch-apps/ and says `available: false`
# until it exists, so nothing here can stop Helf starting.
#
# Nothing to sign: a .uapp carries no signature. This only copies, and only
# when the build changed, so an unchanged app keeps its `built_at`.
#
set -eu

DATA="${DATA_DIR:-/app/data}/watch-apps"
SRC="${WATCH_APP_SRC:-/opt/watch-app}"

mkdir -p "$DATA"
name="$(jq -r .file_name "$SRC/watch-app.json")"
sha256="$(jq -r .sha256 "$SRC/watch-app.json")"
[ -f "$SRC/$name" ] || { echo "publish-watch-app: $SRC/$name is missing" >&2; exit 1; }
[ "$(sha256sum "$SRC/$name" | cut -d' ' -f1)" = "$sha256" ] \
    || { echo "publish-watch-app: $name does not match its metadata" >&2; exit 1; }

if [ -f "$DATA/$name" ] && [ -f "$DATA/watch-app.json" ] \
    && [ "$(jq -r .sha256 "$DATA/watch-app.json")" = "$sha256" ] \
    && [ "$(sha256sum "$DATA/$name" | cut -d' ' -f1)" = "$sha256" ]; then
    echo "publish-watch-app: up to date ($name ${sha256%"${sha256#????????}"}), skipped"
    exit 0
fi

# Temp file plus mv, as sign-apk.sh does: a download never sees half a file,
# and the file moves before the metadata that says it is there.
cp "$SRC/$name" "$DATA/.$name.new"
jq --arg built_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '. + {built_at: $built_at}' \
    "$SRC/watch-app.json" > "$DATA/.watch-app.json.new"
mv "$DATA/.$name.new" "$DATA/$name"
mv "$DATA/.watch-app.json.new" "$DATA/watch-app.json"
echo "publish-watch-app: published $name ($sha256)"
