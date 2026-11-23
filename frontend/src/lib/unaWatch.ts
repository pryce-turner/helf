/**
 * The UNA Watch over Web Bluetooth: pairing, connecting, and a transport for
 * `FtsClient`.
 *
 * Like `scale.ts`, this is the one layer no test can reach, so it is kept
 * free of logic: the protocol is `fts.ts`, the sync is `unaSync.ts`.
 *
 * What shapes it (plan 0023 §4):
 *
 * - **`requestDevice()` needs a tap**, once. After that `getDevices()` returns
 *   the granted watch and polling reconnects without a chooser — on Chrome
 *   for Android with the new permissions backend, which is the thing the
 *   first test on the phone has to confirm.
 * - **The watch is not a sleeping scale.** It advertises continuously (every
 *   ~1 s to bonded devices), so dialling the remembered device is expected to
 *   work without the chooser's active scan. If it does not, that is the
 *   finding, and the fallback is Capacitor rather than a tap per poll.
 * - **Bonding is the OS's job.** FTS refuses unencrypted links; Android raises
 *   its pairing dialog on the first protected read and bonds.
 */

import { FTS_RAW_CHAR, FTS_SERVICE, FTS_VERSION_CHAR, FtsClient, type FtsTransport } from "./fts";
import { WatchNotPairedError, WatchUnreachableError, type WatchSession } from "./unaSync";

const NAME_PREFIX = "UNA Watch";
const BATTERY_SERVICE = 0x180f;
const DEVICE_INFO_SERVICE = 0x180a;
/** An awake, in-range watch connects in well under this. */
const CONNECT_TIMEOUT_MS = 10_000;

export function isSupported(): boolean {
    return typeof navigator !== "undefined" && "bluetooth" in navigator;
}

/** Whether a granted watch can be found again without a tap. */
export function canReconnectSilently(): boolean {
    return isSupported() && typeof navigator.bluetooth.getDevices === "function";
}

/**
 * Open the chooser. **Must run inside the tap handler**, before anything slow:
 * transient activation expires about five seconds after the click.
 *
 * Filtered on the name prefix as well as the service: the watch may put its
 * name only in the scan response, and the 128-bit vendor services do not fit
 * the advert, so a service-only filter can miss it.
 */
export async function pairWatch(): Promise<BluetoothDevice> {
    return navigator.bluetooth.requestDevice({
        filters: [{ namePrefix: NAME_PREFIX }, { services: [FTS_SERVICE] }],
        // Anything touched after connecting must be declared here or it is
        // unreachable, with a SecurityError that reads like a pairing fault.
        optionalServices: [FTS_SERVICE, BATTERY_SERVICE, DEVICE_INFO_SERVICE],
    });
}

export async function rememberedWatch(): Promise<BluetoothDevice | null> {
    if (!canReconnectSilently()) return null;
    try {
        const devices = await navigator.bluetooth.getDevices();
        return devices.find((d) => (d.name ?? "").startsWith(NAME_PREFIX)) ?? null;
    } catch {
        return null;
    }
}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
    return Promise.race([
        promise,
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error(message)), ms)),
    ]);
}

/**
 * Connect to the granted watch and hand back an FTS session.
 *
 * Errors are mapped onto the two the poll loop acts on. Everything that looks
 * like silence — out of range, or another bonded device holding the single
 * connection slot — is `WatchUnreachableError`, because from here they are
 * indistinguishable.
 */
export async function connectWatch(device?: BluetoothDevice | null): Promise<WatchSession> {
    if (!isSupported()) {
        throw new WatchNotPairedError(
            "This browser has no Web Bluetooth. Use Chrome on Android (or a Capacitor build).",
        );
    }
    const watch = device ?? (await rememberedWatch());
    if (!watch?.gatt) {
        throw new WatchNotPairedError(
            canReconnectSilently()
                ? "No watch paired with this browser yet. Tap Pair watch."
                : "This browser cannot reconnect without a tap (no getDevices()). Enable chrome://flags/#enable-web-bluetooth-new-permissions-backend.",
        );
    }

    const gatt = watch.gatt;
    let server: BluetoothRemoteGATTServer;
    try {
        server = await withTimeout(gatt.connect(), CONNECT_TIMEOUT_MS, "connect timed out");
    } catch (cause) {
        try {
            gatt.disconnect();
        } catch {
            // Never opened.
        }
        throw new WatchUnreachableError(
            "The watch did not answer: out of range, or another paired device (an old phone, the Mac) holds its only connection.",
            { cause },
        );
    }

    try {
        const service = await server.getPrimaryService(FTS_SERVICE);
        // The first protected read is what triggers Android's bonding dialog.
        const version = (await (await service.getCharacteristic(FTS_VERSION_CHAR)).readValue()).getUint32(0, true);
        const raw = await service.getCharacteristic(FTS_RAW_CHAR);

        const transport: FtsTransport = {
            write: (data) => raw.writeValueWithoutResponse(data),
            subscribe: (listener) => {
                const handler = (event: Event) => {
                    const value = (event.target as BluetoothRemoteGATTCharacteristic).value;
                    // Copy: Chrome may reuse the buffer for the next event.
                    if (value) listener(new DataView(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength)));
                };
                raw.addEventListener("characteristicvaluechanged", handler);
                return () => raw.removeEventListener("characteristicvaluechanged", handler);
            },
            onClose: (listener) => {
                watch.addEventListener("gattserverdisconnected", listener);
                return () => watch.removeEventListener("gattserverdisconnected", listener);
            },
        };
        // Subscribe before notifications start, so the first one is not lost.
        const client = new FtsClient(transport);
        await raw.startNotifications();

        return {
            client,
            version,
            disconnect: () => {
                client.dispose();
                try {
                    watch.gatt?.disconnect();
                } catch {
                    // Already gone.
                }
            },
        };
    } catch (cause) {
        try {
            gatt.disconnect();
        } catch {
            // Already gone.
        }
        throw new Error(
            "Connected, but the File Transfer Service refused. If Android did not offer to pair, remove the watch from Bluetooth settings, put it in pairing mode (Settings → Phone → Pair) and pair again.",
            { cause },
        );
    }
}
