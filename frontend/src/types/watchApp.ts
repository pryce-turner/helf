/** One watch app published from the image, from `GET /api/app/watch` (plans 0026, 0027). */
export interface WatchAppInfo {
    available: boolean;
    name: string | null;
    /** Its folder on the watch: `/Apps/<folder>/<file_name>`. */
    folder: string | null;
    file_name: string | null;
    app_id: string | null;
    size_bytes: number | null;
    sha256: string | null;
    /**
     * Whole-file CRC-32 as 8 hex digits. Every intact .uapp gives the same
     * value (it ends with its own CRC: the residue 2144df1c), so this catches
     * truncation, not a wrong file; `sha256` does that.
     */
    crc32: string | null;
    sdk_commit: string | null;
    toolchain: string | null;
    built_at: string | null;
}

export interface WatchAppList {
    apps: WatchAppInfo[];
}
