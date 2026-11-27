/**
 * The watch app published from the image, from `GET /api/app/watch`
 * (plan 0026). Every field but `available` is null when there is none.
 */
export interface WatchAppInfo {
    available: boolean;
    name: string | null;
    /** Its folder on the watch: `/Apps/<folder>/<file_name>`. */
    folder: string | null;
    file_name: string | null;
    app_id: string | null;
    size_bytes: number | null;
    sha256: string | null;
    /** CRC-32 as 8 hex digits, the same the watch's DIGEST reports. */
    crc32: string | null;
    sdk_commit: string | null;
    toolchain: string | null;
    built_at: string | null;
}
