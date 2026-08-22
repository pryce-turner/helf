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
 * - **Waking the scale needs the device chooser; reading an awake one does
 *   not.** So a drain has two entry points and the caller picks — see
 *   `connect`. There is no automatic fallback between them, because user
 *   activation expires before the first could fail.
 * - **Stored readings have to be asked for.** Consent alone gets you the
 *   measurement taken while you are connected and nothing else. The history
 *   is released by a write to Beurer's vendor characteristic, and until that
 *   write lands a connected client cannot tell a scale holding a fortnight of
 *   weighings from an empty one. Nothing here tracks what was seen last time;
 *   the server deduplicates on `UNIQUE (observed_at, source)`.
 * - **Measurements are gated behind UDS consent.** Until the consent code is
 *   accepted, subscribing to the measurement characteristics yields nothing,
 *   which looks exactly like an empty scale.
 */

import {
    BATTERY_SERVICE,
    BEURER_REQUEST_STORED_CHAR,
    BEURER_SERVICE,
    BEURER_USER_LIST_CHAR,
    BODY_COMPOSITION_CHAR,
    BODY_COMPOSITION_SERVICE,
    CURRENT_TIME_CHAR,
    CURRENT_TIME_SERVICE,
    DB_CHANGE_INCREMENT_CHAR,
    type ScalePacket,
    type ScaleReading,
    type ScaleUserEntry,
    UDS_CONSENT,
    UDS_RESP_SUCCESS,
    USER_DOB_CHAR,
    USER_GENDER_CHAR,
    USER_HEIGHT_CHAR,
    USER_CONTROL_POINT_CHAR,
    USER_DATA_SERVICE,
    WEIGHT_MEASUREMENT_CHAR,
    WEIGHT_SCALE_SERVICE,
    changeIncrementPayload,
    dateOfBirthPayload,
    describeControlPointFailure,
    genderPayload,
    heightPayload,
    pairPackets,
    parseBodyComposition,
    parseScaleUserList,
    parseUserControlPointResponse,
    parseWeightMeasurement,
    pinDisplayPayload,
    requestStoredPayload,
    userListRequestPayload,
} from "./bcs";

/**
 * The only slot Helf will ever touch.
 *
 * There is one person in this database, so there is one user on the scale, and
 * it is the one the scale calls P01. Helf attaches to it and **never registers
 * another**: REGISTER_NEW_USER is what silently consumed slots 2 and 3 during
 * development, and each new slot starts with an empty history that no longer
 * matches the P01 the user actually steps on. Anything other than P01 being
 * available is an error to report, not a condition to route around.
 */
const SCALE_SLOT = 1;

/** How long to wait after the last packet before calling the replay finished. */
const QUIET_PERIOD_MS = 2500;
/**
 * How long to wait for the first packet once the history has been requested.
 *
 * Separate from the ceiling below because the two silences mean different
 * things. Silence after packets means the history is exhausted; silence before
 * any packet means P01 had nothing stored — routine after a drain, not a
 * stall. Sharing one 45s timer made an empty scale look like a hang.
 */
const FIRST_PACKET_MS = 8_000;
/** How long to wait for the scale's verdict on the consent code. */
const CONSENT_RESPONSE_MS = 5_000;
/** Hard ceiling, so a chatty or stuck scale cannot hang the page forever. */
const DRAIN_TIMEOUT_MS = 45_000;

export interface ScaleCredentials {
    /**
     * P01's consent code, and the only thing Helf has to be told.
     *
     * No slot — there is only P01 (`SCALE_SLOT`). No height, birthday or sex
     * either: the scale hands those over in its user list, and asking for them
     * again would be a second profile for one person, free to disagree with
     * the one the scale's own bioimpedance model uses.
     */
    consentCode: number;
}

const CREDENTIALS_KEY = "helf.scale.credentials";

export function loadCredentials(): ScaleCredentials | null {
    try {
        const raw = localStorage.getItem(CREDENTIALS_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw) as ScaleCredentials;
        if (typeof parsed?.consentCode !== "number") return null;
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

function consentPayload(consentCode: number): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([
        UDS_CONSENT,
        SCALE_SLOT,
        consentCode & 0xff,
        (consentCode >> 8) & 0xff,
    ]);
}

/**
 * How long a remembered device gets to answer.
 *
 * Generous on purpose. `gatt.connect()` is what *wakes* the scale — it pages
 * the device rather than waiting for it to speak — and a sleeping peripheral
 * takes seconds to come up. A short cap turns "waking" into "did not answer",
 * which is the whole point of the button.
 */
const WAKE_TIMEOUT_MS = 12_000;
/**
 * The budget for a scale that should already be awake.
 *
 * An awake BF720 connects near-instantly — measured — so this is not a wait,
 * it is a verdict. Long enough for a live device, short enough that finding
 * out costs nothing worth noticing.
 */
const AWAKE_CONNECT_MS = 5_000;
/** Attempts before a scale that answered the scan is called absent. */
const WAKE_ATTEMPTS = 3;

/**
 * Prompt for the scale. **Must be the first thing the tap does.**
 *
 * `requestDevice()` requires transient user activation, which expires about
 * five seconds after the click, so nothing slow may precede it. That is why
 * there is no "try the remembered device first, fall back to the chooser"
 * path: trying costs more than five seconds, and by the time it has failed the
 * chooser can no longer be opened.
 *
 * **The chooser is not a fallback, it is the mechanism.** A sleeping BF720
 * advertises its real address and refuses connections on it, so a remembered
 * device from `getDevices()` can be dialled forever and never answer. What
 * wakes it is the *active* scan Chrome runs to populate this chooser — that
 * sends scan requests the scale has to answer, where `watchAdvertisements()`
 * only listens passively and rouses nothing. Measured both ways: four
 * advertisements received while asleep with `gatt.connect()` timing out
 * anyway; chooser opened, device picked, connected immediately.
 *
 * Web Bluetooth exposes no other way to trigger an active scan. So the price
 * of a drain that works while the scale is asleep — which is every drain,
 * since the point is to weigh whenever and read later — is one tap on a list.
 */
async function requestDevice(): Promise<BluetoothDevice> {
    const bluetooth = navigator.bluetooth;

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
            // Beurer's own. Omitting it left the user list and the history
            // release unreachable, which is why this looked like a hardware
            // limitation rather than a missing declaration.
            BEURER_SERVICE,
        ],
    });
}

async function subscribe(
    server: BluetoothRemoteGATTServer,
    service: number,
    characteristic: number,
    onValue: (v: DataView) => void,
    { required = false }: { required?: boolean } = {},
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
    } catch (cause) {
        // `required` exists because swallowing everything hid a real fault.
        // Battery and the change-increment are genuinely optional and absent
        // on some firmware, so a failure there must not abort a drain — but
        // the same silence applied to Body Composition turned "the service is
        // unreachable" into a weight-only drain, which is indistinguishable
        // from a scale that simply had no composition to report.
        if (required) {
            throw new ScaleError(
                `The scale would not expose characteristic 0x${characteristic
                    .toString(16)
                    .toUpperCase()}, which this needs to read a measurement.`,
                { cause },
            );
        }
        return null;
    }
}

export class ScaleError extends Error {}

/**
 * The remembered scale did not answer, and the chooser is the way back.
 *
 * Its own class because the UI has to act on it rather than merely print it:
 * this is the one failure with a recovery the user can perform, and that
 * recovery must be reached from a **fresh tap** (see `connect`).
 */
export class ScaleAsleepError extends ScaleError {}

/**
 * Connect, retrying, because one attempt is not a fair test.
 *
 * `gatt.connect()` against a sleeping peripheral routinely fails the first
 * time and succeeds the second: the first attempt is what wakes the radio, and
 * it often times out doing so. Chrome reports that as a bare "Connection
 * attempt failed", which is indistinguishable from a scale that is genuinely
 * absent — so a single attempt turns a normal wake into a hard error.
 */
async function connectWithRetry(
    gatt: BluetoothRemoteGATTServer,
    { attempts = WAKE_ATTEMPTS, timeoutMs = WAKE_TIMEOUT_MS } = {},
): Promise<BluetoothRemoteGATTServer> {
    let last: unknown;

    for (let attempt = 1; attempt <= attempts; attempt++) {
        try {
            return await Promise.race([
                gatt.connect(),
                new Promise<never>((_, reject) =>
                    setTimeout(
                        () => reject(new Error("scale did not answer")),
                        timeoutMs,
                    ),
                ),
            ]);
        } catch (cause) {
            last = cause;
            try {
                // A half-open link makes the next attempt fail immediately.
                gatt.disconnect();
            } catch {
                // Never opened.
            }
            if (attempt < attempts) {
                await new Promise((r) => setTimeout(r, 600));
            }
        }
    }

    throw last;
}

/** What to tell someone when the radio will not come up. */
const CONNECT_ADVICE =
    "Could not connect to the scale. Step on it to wake it and try again. If it keeps failing, the pairing is stale — remove the BF720 under System Settings > Bluetooth (or your phone's Bluetooth settings) and tap Read scale to pair again.";

/**
 * A device we already hold a grant for, if there is one.
 *
 * `getDevices()` sits behind `#enable-experimental-web-platform-features`, so
 * this can simply be absent — in which case every drain has to go through the
 * chooser, which still works, just with the extra tap every time.
 */
async function knownDevice(): Promise<BluetoothDevice | null> {
    const bluetooth = navigator.bluetooth;
    if (typeof bluetooth.getDevices !== "function") return null;
    try {
        const known = await bluetooth.getDevices();
        return (
            known.find((d) => (d.name ?? "").toUpperCase().includes("BF720")) ??
            null
        );
    } catch {
        return null;
    }
}

/**
 * Get a connected GATT server, one of two ways.
 *
 * `pick: false` dials the device we already have a grant for. Silent, instant
 * when the scale is awake, and **useless when it is asleep**: a sleeping BF720
 * advertises its real address and refuses connections on it, so this can never
 * be made to work by waiting longer. It fails fast with `ScaleAsleepError`.
 *
 * `pick: true` opens the chooser, which is what wakes the scale — the active
 * scan Chrome runs to populate it sends requests the peripheral must answer.
 *
 * **The caller chooses; this never falls back on its own.** `requestDevice()`
 * needs transient user activation and that expires about five seconds after
 * the click, so by the time the quiet path has failed the chooser can no
 * longer be opened from the same tap. The fallback has to be a second tap, and
 * making that visible in the UI is the whole reason the two are separate.
 */
async function connect(pick: boolean): Promise<{
    device: BluetoothDevice;
    server: BluetoothRemoteGATTServer;
}> {
    if (!pick) {
        const remembered = await knownDevice();
        if (!remembered?.gatt) {
            throw new ScaleAsleepError(
                "No scale paired with this browser yet.",
            );
        }
        try {
            return {
                device: remembered,
                server: await connectWithRetry(remembered.gatt, {
                    attempts: 1,
                    timeoutMs: AWAKE_CONNECT_MS,
                }),
            };
        } catch (cause) {
            throw new ScaleAsleepError("The scale is asleep.", { cause });
        }
    }

    const device = await requestDevice();
    const gatt = device.gatt;
    if (!gatt) throw new ScaleError(CONNECT_ADVICE);

    try {
        return { device, server: await connectWithRetry(gatt) };
    } catch (cause) {
        throw new ScaleError(CONNECT_ADVICE, { cause });
    }
}

/**
 * Connect, attach to P01, release its stored readings, disconnect.
 *
 * Completion is inferred from silence: the history has no terminator, so the
 * drain ends `QUIET_PERIOD_MS` after the last packet, or at the hard timeout.
 */
export interface DrainResult {
    readings: ScaleReading[];
    weightPackets: number;
    /** Zero means the scale sent no bioimpedance — see the note at the return. */
    bodyCompositionPackets: number;
}

/**
 * How long the user list gets to arrive.
 *
 * Entries come one notification each and end with a status byte, so the wait
 * normally resolves on that marker rather than on this timer. A scale that
 * answers nothing at all falls through here and is reported as "no P01" — the
 * same actionable outcome, reached more slowly.
 */
const USER_LIST_TIMEOUT_MS = 5_000;

export async function drainScale(
    credentials: ScaleCredentials,
    { pick = false }: { pick?: boolean } = {},
): Promise<DrainResult> {
    if (!isSupported()) {
        throw new ScaleError(
            "This browser has no Web Bluetooth. Brave needs it enabled at brave://flags; Firefox does not implement it.",
        );
    }

    // One ordered stream: a live composition packet carries no timestamp and
    // is identified only by following its weight packet.
    const packets: ScalePacket[] = [];

    const { device, server } = await connect(pick);

    try {
        let settle: () => void = () => {};
        const finished = new Promise<void>((resolve) => {
            settle = resolve;
        });

        let quiet: ReturnType<typeof setTimeout> | undefined;
        // The drain has no terminator; it ends when the scale goes quiet.
        const sawPacket = () => {
            if (quiet) clearTimeout(quiet);
            quiet = setTimeout(settle, QUIET_PERIOD_MS);
        };

        await subscribe(
            server,
            WEIGHT_SCALE_SERVICE,
            WEIGHT_MEASUREMENT_CHAR,
            (v) => {
                const m = parseWeightMeasurement(v);
                if (m) packets.push({ kind: "weight", value: m });
                sawPacket();
            },
            { required: true },
        );
        await subscribe(
            server,
            BODY_COMPOSITION_SERVICE,
            BODY_COMPOSITION_CHAR,
            (v) => {
                const m = parseBodyComposition(v);
                if (m) packets.push({ kind: "composition", value: m });
                sawPacket();
            },
            { required: true },
        );

        // The control point must be subscribed *before* consent is written or
        // the scale's reply is lost. That reply is the only thing that
        // distinguishes a refused code from an empty history buffer: both
        // otherwise present as a connection that yields no measurements.
        type Ucp = NonNullable<ReturnType<typeof parseUserControlPointResponse>>;
        let onVerdict: ((r: Ucp | null) => void) | null = null;

        /**
         * Arm the wait for the scale's verdict. **Call this before the write**,
         * not after: the scale replies within milliseconds, so writing first
         * dropped the response on the floor and the wait then timed out. A null
         * result is read as "consented silently", so the race turned a refusal
         * into an apparent success — after which nothing is authorised and no
         * measurement ever arrives.
         *
         * The executor runs synchronously, so merely creating the promise arms
         * it; awaiting is deferred until after the write.
         */
        const armConsent = () =>
            new Promise<Ucp | null>((resolve) => {
                onVerdict = resolve;
                setTimeout(() => {
                    if (onVerdict === resolve) {
                        onVerdict = null;
                        resolve(null);
                    }
                }, CONSENT_RESPONSE_MS);
            });

        await subscribe(
            server,
            USER_DATA_SERVICE,
            USER_CONTROL_POINT_CHAR,
            (v) => {
                const response = parseUserControlPointResponse(v);
                if (response?.requestOpcode === UDS_CONSENT && onVerdict) {
                    const resolve = onVerdict;
                    onVerdict = null;
                    resolve(response);
                }
            },
        );
        await subscribe(
            server,
            USER_DATA_SERVICE,
            DB_CHANGE_INCREMENT_CHAR,
            () => {},
        );

        // Beurer's user list. Required: without it there is no way to tell
        // "P01 exists" from "the registry was wiped", and consenting blind to a
        // slot that no longer exists is exactly the failure this replaces.
        const users: ScaleUserEntry[] = [];
        let listDone: () => void = () => {};
        const listFinished = new Promise<void>((r) => {
            listDone = r;
        });
        await subscribe(
            server,
            BEURER_SERVICE,
            BEURER_USER_LIST_CHAR,
            (v) => {
                const event = parseScaleUserList(v);
                if (!event) return;
                if (event.kind === "user") users.push(event.user);
                else listDone();
            },
            { required: true },
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


        const vendor = await server.getPrimaryService(BEURER_SERVICE);
        const userListChr = await vendor.getCharacteristic(
            BEURER_USER_LIST_CHAR,
        );
        await userListChr.writeValue(userListRequestPayload());
        await Promise.race([
            listFinished,
            new Promise<void>((r) => setTimeout(r, USER_LIST_TIMEOUT_MS)),
        ]);

        const scaleUser = users.find((u) => u.index === SCALE_SLOT);
        if (!scaleUser) {
            // Deliberately fatal. The alternative is registering a slot, which
            // is how the scale ended up with users nobody set up and histories
            // nobody reads — see `SCALE_SLOT`.
            throw new ScaleError(
                users.length
                    ? `This scale has no P01 — it holds ${users
                          .map((u) => `P0${u.index}`)
                          .join(", ")}. Helf only ever reads P01. Set P01 up on the scale itself.`
                    : "This scale has no users set up. Create P01 on the scale itself, then pair again — Helf will not create one for you.",
            );
        }

        let ucp: BluetoothRemoteGATTCharacteristic;
        try {
            const uds = await server.getPrimaryService(USER_DATA_SERVICE);
            ucp = await uds.getCharacteristic(USER_CONTROL_POINT_CHAR);
        } catch (cause) {
            throw new ScaleError(
                "The scale does not expose a User Data Service, so there is no slot to consent to.",
                { cause },
            );
        }

        // A verdict is awaited but not *required* — firmware that consents
        // silently would otherwise be unusable, so only an explicit refusal is
        // acted on.
        const pending = armConsent();
        await ucp.writeValue(consentPayload(credentials.consentCode));
        const verdict = await pending;

        if (verdict && verdict.value !== UDS_RESP_SUCCESS) {
            // Make the scale print its own code before giving up. It is the
            // only way to recover one — the code is never readable over the
            // air — and doing it here means the error message can simply say
            // "read it off the display" instead of describing a menu.
            try {
                await userListChr.writeValue(pinDisplayPayload(SCALE_SLOT));
            } catch {
                // Older firmware without the vendor escape; the message below
                // is still the right one, minus the convenience.
            }
            throw new ScaleError(describeControlPointFailure(verdict));
        }

        // Write P01's profile into the slot *after* consent — the slot is not
        // writable until the scale has accepted the code for it. Without this
        // the slot has no height, age or sex and the scale computes no
        // bioimpedance at all, which presents as a drain carrying weight and
        // BMI only.
        //
        // The values are the scale's own, read from the user list above, so
        // the slot ends up agreeing with the profile P01 was set up with
        // instead of with something retyped alongside it.
        const uds = await server.getPrimaryService(USER_DATA_SERVICE);
        for (const [uuid, payload] of [
            [USER_DOB_CHAR, dateOfBirthPayload(scaleUser)],
            [USER_GENDER_CHAR, genderPayload(scaleUser)],
            [USER_HEIGHT_CHAR, heightPayload(scaleUser)],
            [DB_CHANGE_INCREMENT_CHAR, changeIncrementPayload()],
        ] as [number, Uint8Array<ArrayBuffer>][]) {
            // Individually guarded: firmware that rejects one field should not
            // cost the other three, and a slot three-quarters written still
            // beats none.
            try {
                await (await uds.getCharacteristic(uuid)).writeValue(payload);
            } catch {
                // Not writable on this firmware.
            }
        }

        // The write that makes this a drain rather than a live reading. Every
        // other step was already correct, and without this one the scale
        // answers the consent and then says nothing until someone stands on it
        // — which read as "the BF720 does not give a client its history".
        try {
            const releaseChr = await vendor.getCharacteristic(
                BEURER_REQUEST_STORED_CHAR,
            );
            await releaseChr.writeValue(requestStoredPayload());
        } catch (cause) {
            throw new ScaleError(
                "The scale would not accept a request for its stored readings, so only a weighing taken right now would be captured.",
                { cause },
            );
        }

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


    return {
        readings: pairPackets(packets),
        // Both characteristics were subscribed — `required: true` above would
        // have thrown otherwise — so this says the scale *chose* not to send
        // body composition rather than that it could not be asked. The BF720
        // needs a real user profile (height, age, sex) to compute bioimpedance
        // at all; with defaults it reports mass and nothing else.
        weightPackets: packets.filter((p) => p.kind === "weight").length,
        bodyCompositionPackets: packets.filter((p) => p.kind === "composition")
            .length,
    };
}
