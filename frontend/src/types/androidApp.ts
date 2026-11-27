/**
 * The APK baked into the image, from `GET /api/app/android`. Every field but
 * `available` is null in a build without one.
 */
export interface AndroidAppInfo {
    available: boolean;
    version_name: string | null;
    version_code: number | null;
    size_bytes: number | null;
    sha256: string | null;
    built_at: string | null;
}
