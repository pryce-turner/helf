/**
 * Install the watch app Helf publishes, from download to verified file on
 * the watch (plan 0026), and restart the watch afterwards.
 *
 * Orchestration only, over injected `download` and `connect`, so it runs
 * under test against `FakeWatch`. The protocol is `ftsInstall.ts`; the
 * Bluetooth plumbing is behind `WatchConnector.connect`.
 */

import { crc32 } from "./fts";
import { FtsAppInstaller, type InstallResult, type InstallStep, installApp } from "./ftsInstall";
import { type ConnectOptions, MIN_FTS_VERSION, type WatchSession } from "./unaSync";
import type { WatchAppInfo } from "../types/watchApp";

export interface InstallDeps {
    download: (fileName: string) => Promise<Uint8Array>;
    connect: (options: ConnectOptions) => Promise<WatchSession>;
    onStep?: (s: InstallStep) => void;
    onProgress?: (written: number, total: number) => void;
}

/** Without a negotiated MTU to go on: fits any link above 140, halves below. */
const DEFAULT_CHUNK = 128;

function hex8(n: number): string {
    return n.toString(16).padStart(8, "0");
}

export async function installWatchApp(app: WatchAppInfo, deps: InstallDeps): Promise<InstallResult> {
    if (!app.available || !app.folder || !app.file_name || !app.crc32) {
        throw new Error("Helf has no watch app to install. Is the helf-watch-app service built?");
    }
    const bytes = await deps.download(app.file_name);
    // The server's own record of the build, checked before anything is
    // written: a truncated download must never reach the watch.
    if (bytes.length !== app.size_bytes || hex8(crc32(bytes)) !== app.crc32.toLowerCase()) {
        throw new Error("The downloaded app does not match Helf's checksum. Try again.");
    }

    const session = await deps.connect({ installFolder: app.folder });
    try {
        if (session.version < MIN_FTS_VERSION) {
            throw new Error(
                `The watch speaks FTS version ${session.version}; installing needs ${MIN_FTS_VERSION} (DIGEST, to verify). Update the watch firmware.`,
            );
        }
        if (!(session.client instanceof FtsAppInstaller)) {
            throw new Error("The connection is not an install session.");
        }
        return await installApp(
            session.client,
            { fileName: app.file_name, bytes, appId: app.app_id ?? undefined },
            {
                write: { chunk: session.maxWritePayload ?? DEFAULT_CHUNK, onProgress: deps.onProgress },
                onStep: deps.onStep,
            },
        );
    } finally {
        session.disconnect();
    }
}

/** RESET, on its own short session. The app runs from the boot that follows. */
export async function restartWatch(
    app: WatchAppInfo,
    connect: (options: ConnectOptions) => Promise<WatchSession>,
): Promise<void> {
    if (!app.folder) throw new Error("No watch app to restart for.");
    const session = await connect({ installFolder: app.folder });
    try {
        if (!session.reboot) {
            throw new Error("This connection cannot restart the watch. Restart it by hand: Up until Power Off, Select twice, then hold Select.");
        }
        await session.reboot();
    } finally {
        session.disconnect();
    }
}
