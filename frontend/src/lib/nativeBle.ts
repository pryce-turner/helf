/**
 * The UNA Watch through Capacitor's Bluetooth plugin (plan 0025 §4).
 *
 * The native counterpart of `unaWatch.ts` (Web Bluetooth): it produces the
 * same `WatchSession`, so `fts.ts` and `unaSync.ts` run unchanged on top of
 * it. Unlike the web layer it is testable — the plugin is injected, and
 * `nativeBle.test.ts` drives it against `FakeWatch`.
 *
 * What differs from the browser:
 * - **No chooser on Android.** The watch is bonded at the OS level once, and
 *   `getBondedDevices()` finds it from then on.
 * - **The device id is kept** (a MAC address on Android, a UUID on iOS), in
 *   local storage. A pointer to which watch, nothing about what was synced —
 *   the server's manifest stays the only record of that.
 */

import { BleClient, type BleClientInterface, type BleDevice } from "@capacitor-community/bluetooth-le";

import { FTS_RAW_CHAR, FTS_SERVICE, FTS_VERSION_CHAR, FtsClient, type FtsTransport } from "./fts";
import { WatchNotPairedError, WatchUnreachableError, type WatchSession } from "./unaSync";

const NAME_PREFIX = "UNA Watch";
const DEVICE_KEY = "helf.watch.deviceId";
const NAME_KEY = "helf.watch.deviceName";
const CONNECT_TIMEOUT_MS = 10_000;
/** See `unaWatch.ts`: the first encrypted read may wait on a passkey. */
const BOND_WAIT_MS = 90_000;
const BOND_RETRY_MS = 2_000;

/** The plugin calls this adapter uses; `BleClient` satisfies it. */
export type BleApi = Pick<
    BleClientInterface,
    | "initialize"
    | "getBondedDevices"
    | "requestDevice"
    | "createBond"
    | "connect"
    | "disconnect"
    | "read"
    | "writeWithoutResponse"
    | "startNotifications"
    | "stopNotifications"
>;

export interface KeyValue {
    getItem(key: string): string | null;
    setItem(key: string, value: string): void;
}

export interface PairedWatch {
    name: string;
}

function safeStorage(): KeyValue {
    try {
        return window.localStorage;
    } catch {
        const m = new Map<string, string>();
        return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v) };
    }
}

export class NativeWatch {
    private readonly ble: BleApi;
    private readonly platform: string;
    private readonly store: KeyValue;
    private initialized = false;

    constructor(ble: BleApi = BleClient, platform = "android", store: KeyValue = safeStorage()) {
        this.ble = ble;
        this.platform = platform;
        this.store = store;
    }

    private async init(): Promise<void> {
        if (this.initialized) return;
        // Scans never derive location, so Android 12+ needs no location grant.
        await this.ble.initialize({ androidNeverForLocation: true });
        this.initialized = true;
    }

    private remember(device: BleDevice): PairedWatch {
        const name = device.name ?? NAME_PREFIX;
        this.store.setItem(DEVICE_KEY, device.deviceId);
        this.store.setItem(NAME_KEY, name);
        return { name };
    }

    remembered(): PairedWatch | null {
        const id = this.store.getItem(DEVICE_KEY);
        return id ? { name: this.store.getItem(NAME_KEY) ?? NAME_PREFIX } : null;
    }

    /**
     * Choose the watch. On Android, a watch already bonded in system settings
     * is taken without a scan; otherwise the plugin's picker runs and Android
     * bonds it (the watch shows a passkey to type into the phone).
     */
    async pair(): Promise<PairedWatch> {
        await this.init();
        if (this.platform === "android") {
            const bonded = await this.ble.getBondedDevices();
            const watch = bonded.find((d) => (d.name ?? "").startsWith(NAME_PREFIX));
            if (watch) return this.remember(watch);
        }
        const picked = await this.ble.requestDevice({
            namePrefix: NAME_PREFIX,
            optionalServices: [FTS_SERVICE],
        });
        if (this.platform === "android") {
            // iOS bonds on the first encrypted read by itself; Android is
            // asked to here so the passkey comes up during pairing, not
            // in the middle of the first sync.
            await this.ble.createBond(picked.deviceId, { timeout: BOND_WAIT_MS });
        }
        return this.remember(picked);
    }

    async connect(): Promise<WatchSession> {
        const deviceId = this.store.getItem(DEVICE_KEY);
        if (!deviceId) throw new WatchNotPairedError("No watch paired with this phone yet. Tap Pair watch.");
        await this.init();

        let connected = false;
        const closeListeners = new Set<() => void>();
        try {
            await this.ble.connect(
                deviceId,
                () => {
                    connected = false;
                    for (const l of closeListeners) l();
                },
                { timeout: CONNECT_TIMEOUT_MS },
            );
            connected = true;
        } catch (cause) {
            throw new WatchUnreachableError(
                "The watch did not answer: out of range, or another paired device holds its only connection.",
                { cause },
            );
        }

        try {
            const version = await this.readVersion(deviceId, () => connected);

            const listeners = new Set<(v: DataView) => void>();
            const transport: FtsTransport = {
                write: (data) =>
                    this.ble.writeWithoutResponse(
                        deviceId,
                        FTS_SERVICE,
                        FTS_RAW_CHAR,
                        new DataView(data.buffer, data.byteOffset, data.byteLength),
                    ),
                subscribe: (listener) => {
                    listeners.add(listener);
                    return () => listeners.delete(listener);
                },
                onClose: (listener) => {
                    closeListeners.add(listener);
                    return () => closeListeners.delete(listener);
                },
            };
            // The client subscribes before notifications start, so the first
            // one cannot be lost.
            const client = new FtsClient(transport);
            await this.ble.startNotifications(deviceId, FTS_SERVICE, FTS_RAW_CHAR, (value) => {
                // Copy: the bridge may reuse the buffer.
                const copy = new DataView(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength));
                for (const l of listeners) l(copy);
            });

            return {
                client,
                version,
                disconnect: () => {
                    client.dispose();
                    void this.ble
                        .stopNotifications(deviceId, FTS_SERVICE, FTS_RAW_CHAR)
                        .catch(() => {})
                        .finally(() => this.ble.disconnect(deviceId).catch(() => {}));
                },
            };
        } catch (cause) {
            await this.ble.disconnect(deviceId).catch(() => {});
            throw new Error(
                "Connected, but the File Transfer Service refused: the phone and watch are not bonded. Remove the watch from Bluetooth settings, put it in pairing mode (Settings → Phone → Pair) and pair again.",
                { cause },
            );
        }
    }

    private async readVersion(deviceId: string, isConnected: () => boolean): Promise<number> {
        const deadline = Date.now() + BOND_WAIT_MS;
        for (;;) {
            try {
                return (await this.ble.read(deviceId, FTS_SERVICE, FTS_VERSION_CHAR)).getUint32(0, true);
            } catch (cause) {
                if (!isConnected() || Date.now() >= deadline) throw cause;
                await new Promise((r) => setTimeout(r, BOND_RETRY_MS));
            }
        }
    }
}
