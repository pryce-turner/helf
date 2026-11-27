/**
 * The app's one watch-sync runner, and starting it at launch (plan 0025
 * phase 3). See `watchSyncRunner.ts` for why it is not the Watch page's.
 */

import { Capacitor } from "@capacitor/core";

import { watchApi } from "./api";
import { NativeBackground } from "./nativeBackground";
import { getWatchConnector, isSyncEnabled } from "./watchConnector";
import { WatchSyncRunner } from "./watchSyncRunner";

let runner: WatchSyncRunner | null = null;

/**
 * Whether this APK can run the foreground service. The web code comes from
 * the server, so it can be newer than the installed app; an APK from before
 * phase 3 has no notification icon, and the service would crash it. Builds
 * that have it register `HelfNative` (MainActivity).
 */
export function canSyncInBackground(): boolean {
    return Capacitor.getPlatform() === "android" && Capacitor.isPluginAvailable("HelfNative");
}

/** On Android without background support: the APK needs updating. */
export function needsAppUpdateForBackground(): boolean {
    return Capacitor.getPlatform() === "android" && !canSyncInBackground();
}

export function getWatchSync(): WatchSyncRunner {
    if (!runner) {
        const connector = getWatchConnector();
        runner = new WatchSyncRunner({
            connect: () => connector.connect(),
            api: watchApi,
            background: canSyncInBackground() ? new NativeBackground() : null,
        });
    }
    return runner;
}

/**
 * Called once when the app starts. In the native app, with this phone's sync
 * switched on and a watch paired, polling starts whatever page Helf opens on.
 * A browser waits for a tap: it cannot reconnect or keep running unattended.
 */
export async function startWatchSyncIfEnabled(): Promise<void> {
    const connector = getWatchConnector();
    if (connector.kind !== "native" || !isSyncEnabled()) return;
    if (!(await connector.remembered())) return;
    const sync = getWatchSync();
    if (needsAppUpdateForBackground()) {
        sync.log("This Helf app predates background sync: polling only while it is open. Install the new app (Body → Watch).", "var(--warning)");
    }
    sync.start();
}
