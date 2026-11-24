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
import type { WatchSession } from "./unaSync";
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
    connect(): Promise<WatchSession>;
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
        connect: () => connectWatch(device),
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
        connect: () => watch.connect(),
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
