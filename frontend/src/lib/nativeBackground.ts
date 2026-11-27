/**
 * Keeping the watch sync alive in the background on Android (plan 0025 §4,
 * phase 3).
 *
 * A foreground service with a persistent notification keeps Helf's process,
 * and with it the WebView, running while the phone is locked or Helf is not
 * on screen. The poll loop itself stays in JavaScript (`pollLoop`), so there
 * is one implementation of it; this only starts and stops the service and
 * keeps its notification saying when the last sync was.
 *
 * Why the JavaScript timer survives: Capacitor's `KeepRunning` defaults to
 * true, so pausing the activity does not pause the WebView's timers
 * (`Bridge.onPause` → `handlePause(true)`). If a phone proves otherwise, the
 * fallback in the plan is to move the interval into native code.
 *
 * Testable like `nativeBle.ts`: the plugin is injected.
 */

import {
    ForegroundService,
    type ForegroundServicePlugin,
    Importance,
    type ServiceType,
} from "@capawesome-team/capacitor-android-foreground-service";

/** The plugin calls this uses; `ForegroundService` satisfies it. */
export type ForegroundApi = Pick<
    ForegroundServicePlugin,
    | "checkPermissions"
    | "requestPermissions"
    | "createNotificationChannel"
    | "startForegroundService"
    | "updateForegroundService"
    | "stopForegroundService"
    | "addListener"
>;

const NOTIFICATION_ID = 2025;
const CHANNEL_ID = "helf-watch-sync";
/** `res/drawable/ic_stat_watch_sync.xml`: a monochrome watch, as status-bar icons must be. */
const SMALL_ICON = "ic_stat_watch_sync";
/**
 * ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE. The plugin's
 * ServiceType enum lists only location and microphone, but passes the integer
 * to `startForeground` unchanged, and the manifest declares connectedDevice.
 */
const SERVICE_TYPE_CONNECTED_DEVICE = 16 as ServiceType;
const STOP_BUTTON = 1;

const TITLE = "Syncing your watch";

export class NativeBackground {
    private readonly fs: ForegroundApi;
    private running = false;
    private channelMade = false;

    constructor(fs: ForegroundApi = ForegroundService) {
        this.fs = fs;
    }

    get isRunning(): boolean {
        return this.running;
    }

    /**
     * Start (or keep) the service. Asks for notification permission first on
     * Android 13+; without it the service still runs, the notification is
     * just hidden, so a refusal is not an error.
     */
    async start(body: string): Promise<void> {
        try {
            const status = await this.fs.checkPermissions();
            if (status.display !== "granted") await this.fs.requestPermissions();
        } catch {
            // Older Android: no runtime notification permission.
        }
        if (!this.channelMade) {
            // Low: no sound or pop-up, just the icon. A sync every half hour
            // should not buzz the phone on the nightstand.
            await this.fs.createNotificationChannel({
                id: CHANNEL_ID,
                name: "Watch sync",
                description: "Shown while Helf syncs the UNA Watch in the background",
                importance: Importance.Low,
            });
            this.channelMade = true;
        }
        const options = {
            id: NOTIFICATION_ID,
            title: TITLE,
            body,
            smallIcon: SMALL_ICON,
            notificationChannelId: CHANNEL_ID,
            serviceType: SERVICE_TYPE_CONNECTED_DEVICE,
            silent: true,
            buttons: [{ id: STOP_BUTTON, title: "Stop" }],
        };
        if (this.running) {
            await this.fs.updateForegroundService(options);
        } else {
            await this.fs.startForegroundService(options);
            this.running = true;
        }
    }

    /** Change the notification's text, e.g. after each sync. No-op when stopped. */
    async update(body: string): Promise<void> {
        if (!this.running) return;
        await this.start(body);
    }

    async stop(): Promise<void> {
        if (!this.running) return;
        this.running = false;
        await this.fs.stopForegroundService();
    }

    /** The notification's Stop button. Returns an unsubscribe. */
    async onStop(listener: () => void): Promise<() => void> {
        const handle = await this.fs.addListener("buttonClicked", (e) => {
            if (e.buttonId === STOP_BUTTON) listener();
        });
        return () => void handle.remove();
    }
}
