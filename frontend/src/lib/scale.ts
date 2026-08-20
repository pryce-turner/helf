/**
 * Draining the BF720 over Web Bluetooth.
 *
 * The decoding lives in `bcs.ts` and is tested; this file is the BLE plumbing
 * around it and **cannot be tested without the scale**. Keep logic out of it.
 *
 * Three constraints shape everything here:
 *
 * - **There is no background mode.** `requestDevice()` needs a user gesture,
 *   `navigator.bluetooth` is absent from service workers, and the connection
 *   drops with the tab. So this runs on a tap and nowhere else.
 * - **The scale replays its whole ring** - up to 30 stored weighings - on
 *   every connect. That is why nothing here tracks what was seen last time;
 *   the server deduplicates on `UNIQUE (observed_at, source)`.
 * - **Measurements are gated behind UDS consent.** Until the consent code is
 *   accepted, subscribing to the measurement characteristics yields nothing,
 *   which looks exactly like an empty scale.
 */

import {
    BATTERY_SERVICE,
    BODY_COMPOSITION_CHAR,
    BODY_COMPOSITION_SERVICE,
    CURRENT_TIME_CHAR,
    CURRENT_TIME_SERVICE,
    DB_CHANGE_INCREMENT_CHAR,
    type RawBodyComposition,
    type RawWeightMeasurement,
    type ScaleReading,
    UDS_CONSENT,
    UDS_RESP_SUCCESS,
    USER_CONTROL_POINT_CHAR,
    USER_DATA_SERVICE,
    WEIGHT_MEASUREMENT_CHAR,
    WEIGHT_SCALE_SERVICE,
    describeControlPointFailure,
    pairPackets,
    parseBodyComposition,
    parseUserControlPointResponse,
    parseWeightMeasurement,
} from "./bcs";

/** How long to wait after the last packet before calling the replay finished. */
const QUIET_PERIOD_MS = 2500;
/**
 * How long to wait for the *first* packet once consent is accepted.
 *
 * Separate from the ceiling below because the two silences mean different
 * things. Silence after packets means the replay is over; silence before any
 * packet means the scale has nothing stored - and a reset wipes the history, so
 * that is a routine outcome, not a stall. Sharing one 45s timer made an empty
 * scale look like a hang.
 */
const FIRST_PACKET_MS = 8_000;
/** How long to wait for the scale's verdict on the consent code. */
const CONSENT_RESPONSE_MS = 5_000;
/** Hard ceiling, so a chatty or stuck scale cannot hang the page forever. */
const DRAIN_TIMEOUT_MS = 45_000;

export interface ScaleCredentials {
    /** The slot on the scale, 1-8. */
    userIndex: number;
    /** The consent code for that slot, as set in openScale or on the scale. */
    consentCode: number;
}

export interface DrainProgress {
    stage: "connecting" | "authorising" | "reading" | "done";
    packets: number;
}

const CREDENTIALS_KEY = "helf.scale.credentials";

export function loadCredentials(): ScaleCredentials | null {
    try {
        const raw = localStorage.getItem(CREDENTIALS_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw) as ScaleCredentials;
        if (
            typeof parsed?.userIndex !== "number" ||
            typeof parsed?.consentCode !== "number"
        ) {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}

export function saveCredentials(credentials: ScaleCredentials): void {
    localStorage.setItem(CREDENTIALS_KEY, JSON.stringify(credentials));
}

/**
 * Whether this browser can do any of this at all.
 *
 * Firefox never will - Mozilla classes Web Bluetooth "Harmful" - and Brave
 * ships it disabled until switched on at `brave://flags`. The UI feature-tests
 * on this rather than offering a button that cannot work.
 */
export function isSupported(): boolean {
    return typeof navigator !== "undefined" && "bluetooth" in navigator;
}

/** The SIG Current Time payload, so replayed history is stamped correctly. */
function currentTimePayload(): Uint8Array<ArrayBuffer> {
    const now = new Date();
    const buf = new ArrayBuffer(10);
    const v = new DataView(buf);
    v.setUint16(0, now.getFullYear(), true);
    v.setUint8(2, now.getMonth() + 1);
    v.setUint8(3, now.getDate());
    v.setUint8(4, now.getHours());
    v.setUint8(5, now.getMinutes());
    v.setUint8(6, now.getSeconds());
    // ISO weekday: the spec wants 1=Monday..7=Sunday, JS gives 0=Sunday.
    v.setUint8(7, now.getDay() === 0 ? 7 : now.getDay());
    v.setUint8(8, 0); // fractions of a second
    v.setUint8(9, 0); // adjust reason
    return new Uint8Array(buf);
}

function consentPayload({
    userIndex,
    consentCode,
}: ScaleCredentials): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([
        UDS_CONSENT,
        userIndex & 0xff,
        consentCode & 0xff,
        (consentCode >> 8) & 0xff,
    ]);
}

/**
 * Ask for the scale, preferring a grant we already hold.
 *
 * `getDevices()` sits behind `#enable-experimental-web-platform-features`. With
 * it, a drain reconnects silently; without it every drain raises the chooser.
 * Both work, so this degrades rather than requiring the flag.
 */
async function findDevice(): Promise<BluetoothDevice> {
    const bluetooth = navigator.bluetooth;

    if (typeof bluetooth.getDevices === "function") {
        try {
            const known = await bluetooth.getDevices();
            const previously = known.find((d) =>
                (d.name ?? "").toUpperCase().includes("BF720"),
            );
            if (previously) return previously;
        } catch {
            // Flag off or permission backend unavailable - fall through to the
            // chooser, which always works.
        }
    }

    return bluetooth.requestDevice({
        filters: [
            { services: [WEIGHT_SCALE_SERVICE] },
            { services: [BODY_COMPOSITION_SERVICE] },
            { namePrefix: "BF720" },
        ],
        // Every service touched below must be declared here or it is
        // unreachable after connecting, with a confusing SecurityError.
        optionalServices: [
            WEIGHT_SCALE_SERVICE,
            BODY_COMPOSITION_SERVICE,
            USER_DATA_SERVICE,
            CURRENT_TIME_SERVICE,
            BATTERY_SERVICE,
        ],
    });
}

async function subscribe(
    server: BluetoothRemoteGATTServer,
    service: number,
    characteristic: number,
    onValue: (v: DataView) => void,
): Promise<BluetoothRemoteGATTCharacteristic | null> {
    try {
        const svc = await server.getPrimaryService(service);
        const chr = await svc.getCharacteristic(characteristic);
        chr.addEventListener("characteristicvaluechanged", (event) => {
            const value = (event.target as BluetoothRemoteGATTCharacteristic)
                .value;
            if (value) onValue(value);
        });
        await chr.startNotifications();
        return chr;
    } catch {
        // Optional on some firmware. A missing battery or change-increment
        // characteristic must not abort a drain that would otherwise work.
        return null;
    }
}

export class ScaleError extends Error {}

/**
 * Connect, authorise, collect whatever the scale replays, disconnect.
 *
 * Completion is inferred from silence: the replay has no terminator, so the
 * drain ends `QUIET_PERIOD_MS` after the last packet, or at the hard timeout.
 */
export async function drainScale(
    credentials: ScaleCredentials,
    onProgress?: (p: DrainProgress) => void,
): Promise<ScaleReading[]> {
    if (!isSupported()) {
        throw new ScaleError(
            "This browser has no Web Bluetooth. Brave needs it enabled at brave://flags; Firefox does not implement it.",
        );
    }

    const weights: RawWeightMeasurement[] = [];
    const comps: RawBodyComposition[] = [];
    let packets = 0;

    const device = await findDevice();
    onProgress?.({ stage: "connecting", packets });

    const server = await device.gatt?.connect();
    if (!server) throw new ScaleError("Could not connect to the scale.");

    try {
        let settle: () => void = () => {};
        const finished = new Promise<void>((resolve) => {
            settle = resolve;
        });

        let quiet: ReturnType<typeof setTimeout> | undefined;
        const sawPacket = () => {
            packets += 1;
            onProgress?.({ stage: "reading", packets });
            if (quiet) clearTimeout(quiet);
            quiet = setTimeout(settle, QUIET_PERIOD_MS);
        };

        await subscribe(
            server,
            WEIGHT_SCALE_SERVICE,
            WEIGHT_MEASUREMENT_CHAR,
            (v) => {
                const m = parseWeightMeasurement(v);
                if (m) weights.push(m);
                sawPacket();
            },
        );
        await subscribe(
            server,
            BODY_COMPOSITION_SERVICE,
            BODY_COMPOSITION_CHAR,
            (v) => {
                const m = parseBodyComposition(v);
                if (m) comps.push(m);
                sawPacket();
            },
        );
        // The control point must be subscribed *before* consent is written or
        // the scale's reply is lost. That reply is the only thing that
        // distinguishes a refused code from an empty history buffer: both
        // otherwise present as a connection that yields no measurements.
        let resolveConsent: (r: ReturnType<typeof parseUserControlPointResponse>) => void =
            () => {};
        const consentVerdict = new Promise<
            ReturnType<typeof parseUserControlPointResponse>
        >((resolve) => {
            resolveConsent = resolve;
        });
        await subscribe(
            server,
            USER_DATA_SERVICE,
            USER_CONTROL_POINT_CHAR,
            (v) => {
                const response = parseUserControlPointResponse(v);
                if (response?.requestOpcode === UDS_CONSENT) {
                    resolveConsent(response);
                }
            },
        );
        await subscribe(
            server,
            USER_DATA_SERVICE,
            DB_CHANGE_INCREMENT_CHAR,
            () => {},
        );

        // Best effort: a scale with a wrong clock stamps its history wrongly,
        // and those stamps are what deduplication is keyed on.
        try {
            const timeSvc = await server.getPrimaryService(CURRENT_TIME_SERVICE);
            const timeChr = await timeSvc.getCharacteristic(CURRENT_TIME_CHAR);
            await timeChr.writeValue(currentTimePayload());
        } catch {
            // Read-only on some firmware.
        }

        onProgress?.({ stage: "authorising", packets });
        try {
            const uds = await server.getPrimaryService(USER_DATA_SERVICE);
            const ucp = await uds.getCharacteristic(USER_CONTROL_POINT_CHAR);
            await ucp.writeValue(consentPayload(credentials));
        } catch (cause) {
            throw new ScaleError(
                `The scale refused the consent code for slot ${credentials.userIndex}. Check it in openScale, or on the scale itself.`,
                { cause },
            );
        }

        // Wait for the verdict, but do not *require* one: firmware that
        // accepts consent silently would otherwise be unusable. Only an
        // explicit refusal aborts.
        const verdict = await Promise.race([
            consentVerdict,
            new Promise<null>((resolve) =>
                setTimeout(() => resolve(null), CONSENT_RESPONSE_MS),
            ),
        ]);
        if (verdict && verdict.value !== UDS_RESP_SUCCESS) {
            throw new ScaleError(
                describeControlPointFailure(verdict, credentials.userIndex),
            );
        }

        onProgress?.({ stage: "reading", packets });
        quiet = setTimeout(settle, FIRST_PACKET_MS);
        await Promise.race([
            finished,
            new Promise<void>((resolve) =>
                setTimeout(resolve, DRAIN_TIMEOUT_MS),
            ),
        ]);
        if (quiet) clearTimeout(quiet);
    } finally {
        // Leaving it connected would hold the scale's radio and block openScale
        // from ever pairing again during the overlap fortnight.
        try {
            device.gatt?.disconnect();
        } catch {
            // Already gone.
        }
    }

    onProgress?.({ stage: "done", packets });
    return pairPackets(weights, comps);
}
