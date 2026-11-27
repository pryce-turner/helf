#!/bin/sh
#
# Publish the image's watch apps onto the data volume (plans 0026, 0027).
#
# Runs as the `helf-watch-app` compose service on every `up`, like helf-apk.
# The image holds one folder per app ($SRC/<Folder>/<File>.uapp beside its
# watch-app.json); each is copied to $DATA/<Folder>/. Helf lists whatever is
# there, so nothing here can stop Helf starting.
#
# Nothing to sign: a .uapp carries no signature. This only copies, and only an
# app whose build changed, so an unchanged app keeps its `built_at`.
#
set -eu

DATA="${DATA_DIR:-/app/data}/watch-apps"
SRC="${WATCH_APP_SRC:-/opt/watch-apps}"

publish() {
    src="$1"
    folder="$(basename "$src")"
    dst="$DATA/$folder"
    name="$(jq -r .file_name "$src/watch-app.json")"
    sha256="$(jq -r .sha256 "$src/watch-app.json")"
    [ -f "$src/$name" ] || { echo "publish-watch-app: $folder/$name is missing" >&2; return 1; }
    [ "$(sha256sum "$src/$name" | cut -d' ' -f1)" = "$sha256" ] \
        || { echo "publish-watch-app: $folder/$name does not match its metadata" >&2; return 1; }

    if [ -f "$dst/$name" ] && [ -f "$dst/watch-app.json" ] \
        && [ "$(jq -r .sha256 "$dst/watch-app.json")" = "$sha256" ] \
        && [ "$(sha256sum "$dst/$name" | cut -d' ' -f1)" = "$sha256" ]; then
        echo "publish-watch-app: $folder up to date (${sha256%"${sha256#????????}"}), skipped"
        return 0
    fi

    # Temp file plus mv, as sign-apk.sh does: a download never sees half a
    # file, and the file moves before the metadata that says it is there.
    mkdir -p "$dst"
    cp "$src/$name" "$dst/.$name.new"
    jq --arg built_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '. + {built_at: $built_at}' \
        "$src/watch-app.json" > "$dst/.watch-app.json.new"
    mv "$dst/.$name.new" "$dst/$name"
    mv "$dst/.watch-app.json.new" "$dst/watch-app.json"
    echo "publish-watch-app: published $folder/$name ($sha256)"
}

mkdir -p "$DATA"
status=0
for src in "$SRC"/*/; do
    [ -f "$src/watch-app.json" ] || continue
    publish "${src%/}" || status=1
done
exit "$status"
