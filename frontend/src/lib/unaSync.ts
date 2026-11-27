/**
 * What to fetch from the UNA Watch, and the poll loop that fetches it.
 *
 * Pure orchestration over an `FtsClient`, a server manifest and an injected
 * `connect`, so every branch — new file, changed file, file growing under the
 * read, watch out of range, Helf unreachable — runs under test without a
 * radio. The Web Bluetooth side is `unaWatch.ts`.
 *
 * The shape follows the scale drain (plan 0015 §4): **the browser holds no
 * state.** What has been uploaded is the server's manifest, read fresh on
 * every poll, so clearing the PWA's storage or swapping phones re-converges on
 * the next run. Unlike the scale, reading the watch is not destructive — the
 * files stay on the watch — so a failed upload just means the same file is
 * fetched again next time.
 */

import {
    type DirEntry,
    type FtsClient,
    FtsDisconnectedError,
    FtsError,
    Status,
    crc32,
} from "./fts";

/** A file on the watch, as LISTDIR described it. */
export interface WatchFile {
    path: string;
    size: number;
    /** Raw `modificationTime`, compared as an opaque string — see `DirEntry`. */
    mtime: string;
}

/** What the server already holds for a path (`GET /api/watch/files`). */
export interface ManifestEntry {
    path: string;
    size: number;
    mtime: string;
    crc32: number;
}

export interface WatchApi {
    manifest(): Promise<ManifestEntry[]>;
    upload(file: WatchFile, bytes: Uint8Array, crc: number): Promise<{ status: string }>;
}

/** Below this the watch has no DIGEST, so nothing can be verified. */
export const MIN_FTS_VERSION = 5;

const MONTH_DIR = /^\d{6}$/;
const DAILY_FILE = /^dh_\d{8}\.json$/;
const DAY_DIR = /^\d{8}$/;
/** SleepLog chunks (plan 0024): only `.bin`, which the app renames to once complete. */
const SLEEP_CHUNK = /^\d{6}(-\d+)?\.bin$/;
/** Drinks events (plan 0027): only `.json`, which the app renames to from `.tmp` once written. */
const DRINK_EVENT = /^\d{6}(-\d+)?\.json$/;

/**
 * Directories under `/Workouts` that are inputs *to* the watch — planned
 * workouts a phone pushed there — rather than anything it recorded.
 */
const WORKOUT_INPUT_DIRS = new Set(["Schedule"]);

/** Whether a listed file differs from what the server holds. */
export function needsFetch(
    file: WatchFile,
    held: ReadonlyMap<string, ManifestEntry>,
): boolean {
    const known = held.get(file.path);
    return !known || known.size !== file.size || known.mtime !== file.mtime;
}

function join(dir: string, name: string): string {
    return dir.endsWith("/") ? `${dir}${name}` : `${dir}/${name}`;
}

function asFile(dir: string, e: DirEntry): WatchFile {
    return { path: join(dir, e.name), size: e.size, mtime: e.mtime };
}

/** LISTDIR that treats "no such directory" as empty. */
async function listOrEmpty(client: FtsClient, path: string): Promise<DirEntry[]> {
    try {
        return await client.listDir(path);
    } catch (e) {
        if (e instanceof FtsError && e.status === Status.NO_FILE) return [];
        throw e;
    }
}

/**
 * Archived days: `/DailyHealth/YYYYMM/dh_YYYYMMDD.json`.
 *
 * `dh.tmp` is deliberately skipped. It is today's crash-recovery state in a
 * binary format, rewritten continuously; today's numbers are better read over
 * the Custom Command Service (plan 0023 §6) and the finished day arrives as
 * JSON after midnight anyway.
 */
async function discoverDailyHealth(client: FtsClient): Promise<WatchFile[]> {
    const files: WatchFile[] = [];
    for (const month of await listOrEmpty(client, "/DailyHealth")) {
        if (!month.isDir || !MONTH_DIR.test(month.name)) continue;
        const dir = `/DailyHealth/${month.name}`;
        for (const e of await listOrEmpty(client, dir)) {
            if (!e.isDir && DAILY_FILE.test(e.name)) files.push(asFile(dir, e));
        }
    }
    return files;
}

/**
 * The `.fit` an app is recording into right now, if any.
 *
 * Each app keeps `Activity/.recording` while a workout runs: the app-relative
 * path of the open file on the first line. That file is growing and will be
 * finalised later, so it is left for a later poll rather than uploaded torn.
 */
async function recordingPath(
    client: FtsClient,
    appDir: string,
    activity: DirEntry[],
): Promise<string | null> {
    if (!activity.some((e) => e.name === ".recording" && !e.isDir)) return null;
    try {
        const bytes = await client.readFile(`${appDir}/Activity/.recording`);
        const first = new TextDecoder().decode(bytes).split("\n")[0].trim();
        return first ? join(appDir, first.replace(/^\/+/, "")) : null;
    } catch {
        // Unreadable marker: be conservative and skip nothing; a torn file
        // fails its size check below if it is still growing.
        return null;
    }
}

/**
 * SleepLog chunks: `/Apps/<App>/Sleep/YYYYMMDD/HHMMSS.bin` (plan 0024).
 *
 * Looked for under every app rather than one name, because the folder the
 * watch gives an app is its own business. `.part` files are the chunk being
 * written and are never fetched; a `.bin` is complete and never changes.
 */
async function discoverSleep(client: FtsClient, appDir: string): Promise<WatchFile[]> {
    const files: WatchFile[] = [];
    const sleepDir = `${appDir}/Sleep`;
    for (const day of await listOrEmpty(client, sleepDir)) {
        if (!day.isDir || !DAY_DIR.test(day.name)) continue;
        const dir = `${sleepDir}/${day.name}`;
        for (const f of await listOrEmpty(client, dir)) {
            if (!f.isDir && SLEEP_CHUNK.test(f.name)) files.push(asFile(dir, f));
        }
    }
    return files;
}

/**
 * Drinks events: `/Apps/<App>/Log/YYYYMMDD/HHMMSS.json` (plan 0027). One small
 * file per drink or undo, never rewritten, so each is fetched once.
 */
async function discoverDrinks(client: FtsClient, appDir: string): Promise<WatchFile[]> {
    const files: WatchFile[] = [];
    const logDir = `${appDir}/Log`;
    for (const day of await listOrEmpty(client, logDir)) {
        if (!day.isDir || !DAY_DIR.test(day.name)) continue;
        const dir = `${logDir}/${day.name}`;
        for (const f of await listOrEmpty(client, dir)) {
            if (!f.isDir && DRINK_EVENT.test(f.name)) files.push(asFile(dir, f));
        }
    }
    return files;
}

/** Per app: workouts under `Activity/`, SleepLog chunks under `Sleep/`, Drinks events under `Log/`. */
async function discoverActivities(client: FtsClient): Promise<WatchFile[]> {
    const files: WatchFile[] = [];
    for (const app of await listOrEmpty(client, "/Apps")) {
        if (!app.isDir) continue;
        const appDir = `/Apps/${app.name}`;
        files.push(...(await discoverSleep(client, appDir)));
        files.push(...(await discoverDrinks(client, appDir)));
        const activityDir = `${appDir}/Activity`;
        const activity = await listOrEmpty(client, activityDir);
        if (!activity.length) continue;
        const recording = await recordingPath(client, appDir, activity);

        for (const e of activity) {
            if (!e.isDir && e.name.endsWith(".json")) files.push(asFile(activityDir, e));
            if (!e.isDir || !MONTH_DIR.test(e.name)) continue;
            const monthDir = `${activityDir}/${e.name}`;
            for (const f of await listOrEmpty(client, monthDir)) {
                const file = asFile(monthDir, f);
                if (!f.isDir && f.name.endsWith(".fit") && file.path !== recording) {
                    files.push(file);
                }
            }
        }
    }
    return files;
}

/** `/Workouts`, recursively, minus the folders that are inputs to the watch. */
async function discoverWorkouts(client: FtsClient, dir = "/Workouts"): Promise<WatchFile[]> {
    const files: WatchFile[] = [];
    for (const e of await listOrEmpty(client, dir)) {
        if (e.isDir) {
            if (dir === "/Workouts" && WORKOUT_INPUT_DIRS.has(e.name)) continue;
            files.push(...(await discoverWorkouts(client, join(dir, e.name))));
        } else {
            files.push(asFile(dir, e));
        }
    }
    return files;
}

export async function discover(client: FtsClient): Promise<WatchFile[]> {
    return [
        ...(await discoverDailyHealth(client)),
        ...(await discoverActivities(client)),
        ...(await discoverWorkouts(client)),
    ];
}

export interface SyncReport {
    listed: number;
    fetched: string[];
    unchanged: number;
    /** Changed under the read, or failed to verify; retried next poll. */
    skipped: { path: string; reason: string }[];
}

/** Fetch, verify against the watch's own CRC, retrying once on a mismatch. */
async function fetchVerified(
    client: FtsClient,
    file: WatchFile,
): Promise<{ bytes: Uint8Array; crc: number } | { reason: string }> {
    let reason = "";
    for (let attempt = 0; attempt < 2; attempt++) {
        const bytes = await client.readFile(file.path);
        if (bytes.length !== file.size) {
            // Grew or shrank between LISTDIR and READ: being written right
            // now. Its next listing will carry the new size.
            return { reason: `size changed (${file.size} → ${bytes.length})` };
        }
        const digest = await client.digest(file.path);
        const crc = crc32(bytes);
        if (digest.fileSize === bytes.length && digest.crc32 === crc) {
            return { bytes, crc };
        }
        reason = `CRC mismatch (watch ${digest.crc32.toString(16)}, read ${crc.toString(16)})`;
    }
    return { reason };
}

/**
 * One sync over an open connection: list, diff against the manifest, fetch
 * what is new or changed, verify, upload.
 *
 * Each file is uploaded as soon as it verifies, so a connection lost halfway
 * keeps everything before it. A per-file failure skips that file; a lost link
 * or an unreachable server ends the run.
 */
export async function syncOnce(
    client: FtsClient,
    api: WatchApi,
    log: (message: string) => void = () => {},
): Promise<SyncReport> {
    const held = new Map((await api.manifest()).map((m) => [m.path, m]));
    const listed = await discover(client);
    const todo = listed.filter((f) => needsFetch(f, held));
    log(`${listed.length} files on the watch, ${todo.length} new or changed`);

    const report: SyncReport = {
        listed: listed.length,
        fetched: [],
        unchanged: listed.length - todo.length,
        skipped: [],
    };

    for (const file of todo) {
        let result: Awaited<ReturnType<typeof fetchVerified>>;
        try {
            result = await fetchVerified(client, file);
        } catch (e) {
            if (e instanceof FtsDisconnectedError) throw e;
            report.skipped.push({ path: file.path, reason: String((e as Error).message ?? e) });
            continue;
        }
        if ("reason" in result) {
            report.skipped.push({ path: file.path, reason: result.reason });
            log(`skipped ${file.path}: ${result.reason}`);
            continue;
        }
        await api.upload(file, result.bytes, result.crc);
        report.fetched.push(file.path);
        log(`uploaded ${file.path} (${file.size} bytes)`);
    }
    return report;
}

// ---------------------------------------------------------------- poll loop

/** No grant yet: someone has to tap Pair, once. */
export class WatchNotPairedError extends Error {}
/**
 * The watch did not answer. From a phone these are one condition: out of
 * range, asleep in a pocket, or **another bonded device holding the only
 * connection slot** — the watch stops advertising while connected, so all
 * three look like silence.
 */
export class WatchUnreachableError extends Error {}

export interface WatchSession {
    /**
     * Read-only for the sync. An `FtsAppInstaller`, scoped to one app folder,
     * only when `connect` was asked for one (`ConnectOptions.installFolder`).
     */
    client: FtsClient;
    version: number;
    /** Largest WRITE_DATA payload one packet carries, where the platform reports the MTU. */
    maxWritePayload?: number;
    /**
     * Restart the watch (Custom Command RESET, plan 0026). Only on install
     * sessions, and absent where that service cannot be reached.
     */
    reboot?: () => Promise<void>;
    disconnect(): void;
}

export interface ConnectOptions {
    /** Open an install session that may write `/Apps/<installFolder>/*.uapp`. */
    installFolder?: string;
}

export type PollOutcome =
    | { kind: "synced"; at: Date; report: SyncReport }
    | { kind: "unpaired"; at: Date; message: string }
    | { kind: "unreachable"; at: Date; message: string }
    | { kind: "unsupported"; at: Date; message: string }
    | { kind: "error"; at: Date; message: string };

/**
 * Connect, check the version, sync, disconnect. **Never throws.**
 *
 * Disconnect is unconditional: the watch keeps one connection and stops
 * advertising while it is held, so a session left open would lock out every
 * other device, and a held link costs the watch more battery than advertising.
 */
export async function pollOnce(deps: {
    connect: () => Promise<WatchSession>;
    api: WatchApi;
    log?: (message: string) => void;
    now?: () => Date;
}): Promise<PollOutcome> {
    const now = deps.now ?? (() => new Date());
    const log = deps.log ?? (() => {});
    let session: WatchSession;
    try {
        session = await deps.connect();
    } catch (e) {
        const message = (e as Error)?.message ?? String(e);
        if (e instanceof WatchNotPairedError) return { kind: "unpaired", at: now(), message };
        if (e instanceof WatchUnreachableError) return { kind: "unreachable", at: now(), message };
        return { kind: "error", at: now(), message };
    }

    try {
        if (session.version < MIN_FTS_VERSION) {
            return {
                kind: "unsupported",
                at: now(),
                message: `The watch speaks FTS version ${session.version}; DIGEST needs ${MIN_FTS_VERSION}, so nothing could be verified. Update the watch firmware.`,
            };
        }
        const report = await syncOnce(session.client, deps.api, log);
        return { kind: "synced", at: now(), report };
    } catch (e) {
        const message = (e as Error)?.message ?? String(e);
        if (e instanceof FtsDisconnectedError) {
            return { kind: "unreachable", at: now(), message: `Lost the watch mid-sync: ${message}` };
        }
        return { kind: "error", at: now(), message };
    } finally {
        try {
            session.disconnect();
        } catch {
            // Already gone.
        }
    }
}

/** Sleep that wakes early on abort. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
    return new Promise((resolve) => {
        if (signal?.aborted) return resolve();
        const timer = setTimeout(done, ms);
        function done() {
            clearTimeout(timer);
            signal?.removeEventListener("abort", done);
            resolve();
        }
        signal?.addEventListener("abort", done, { once: true });
    });
}

/**
 * Poll every `intervalMs` until aborted. The interval runs from the end of one
 * poll to the start of the next, so a slow sync never overlaps the next one.
 */
export async function pollLoop(
    deps: Parameters<typeof pollOnce>[0] & {
        onOutcome: (outcome: PollOutcome) => void;
        wait?: (ms: number, signal: AbortSignal) => Promise<void>;
    },
    { intervalMs, signal }: { intervalMs: number; signal: AbortSignal },
): Promise<void> {
    const wait = deps.wait ?? sleep;
    while (!signal.aborted) {
        deps.onOutcome(await pollOnce(deps));
        if (signal.aborted) break;
        await wait(intervalMs, signal);
    }
}
