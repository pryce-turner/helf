/**
 * One way in to the UNA Watch, whichever shell Helf is running in (plan 0025).
 *
 * In a browser this is Web Bluetooth (`unaWatch.ts`); inside the Capacitor app
 * it is the native plugin (`nativeBle.ts`). Both hand back the same
 * `WatchSession`, so the protocol (`fts.ts`) and the sync (`unaSync.ts`) exist
 * once.
 */

import { Capacitor } from "@capacitor/core";

import { NativeWatch } from "./nativeBle";
import type { ConnectOptions, WatchSession } from "./unaSync";
import {
    canReconnectSilently as webCanReconnect,
    connectWatch,
    isSupported as webSupported,
    pairWatch,
    rememberedWatch,
} from "./unaWatch";

export interface WatchConnector {
    readonly kind: "web" | "native";
    isSupported(): boolean;
    /** Whether a poll can reconnect without a tap. */
    canReconnectSilently(): boolean;
    /** Must run inside a tap handler in the browser (the chooser needs it). */
    pair(): Promise<{ name: string }>;
    remembered(): Promise<{ name: string } | null>;
    /**
     * One session at a time, whoever asks: a poll and an app install queue
     * behind each other here (see `exclusive`). Always `disconnect()` it.
     */
    connect(options?: ConnectOptions): Promise<WatchSession>;
}

/**
 * The watch keeps one connection and stops advertising while it is held, so
 * a second session opened over the first would just fail as "unreachable".
 * Every session goes through here, and the next waits for `disconnect()`.
 */
let held: Promise<void> = Promise.resolve();

export function exclusive(open: () => Promise<WatchSession>): Promise<WatchSession> {
    const before = held;
    let release!: () => void;
    held = new Promise<void>((r) => (release = r));
    return before.then(async () => {
        let session: WatchSession;
        try {
            session = await open();
        } catch (e) {
            release();
            throw e;
        }
        let released = false;
        return {
            ...session,
            disconnect: () => {
                try {
                    session.disconnect();
                } finally {
                    if (!released) {
                        released = true;
                        release();
                    }
                }
            },
        };
    });
}

function webConnector(): WatchConnector {
    let device: BluetoothDevice | null = null;
    return {
        kind: "web",
        isSupported: webSupported,
        canReconnectSilently: webCanReconnect,
        pair: async () => {
            device = await pairWatch();
            return { name: device.name ?? "UNA Watch" };
        },
        remembered: async () => {
            device = device ?? (await rememberedWatch());
            return device ? { name: device.name ?? "UNA Watch" } : null;
        },
        connect: (options) => exclusive(() => connectWatch(device, options)),
    };
}

function nativeConnector(): WatchConnector {
    const watch = new NativeWatch(undefined, Capacitor.getPlatform());
    return {
        kind: "native",
        isSupported: () => true,
        canReconnectSilently: () => true,
        pair: () => watch.pair(),
        remembered: async () => watch.remembered(),
        connect: (options) => exclusive(() => watch.connect(options)),
    };
}

let connector: WatchConnector | null = null;

export function getWatchConnector(): WatchConnector {
    connector ??= Capacitor.isNativePlatform() ? nativeConnector() : webConnector();
    return connector;
}

const SYNC_KEY = "helf.watch.syncEnabled";

/**
 * Whether **this device** syncs the watch. Off by default, set per device:
 * the watch has one connection slot, so two syncing devices lock each other
 * out (plan 0025 §2).
 */
export function isSyncEnabled(): boolean {
    try {
        return localStorage.getItem(SYNC_KEY) === "1";
    } catch {
        return false;
    }
}

export function setSyncEnabled(on: boolean): void {
    try {
        localStorage.setItem(SYNC_KEY, on ? "1" : "0");
    } catch {
        // Private mode: the switch just will not stick.
    }
}
