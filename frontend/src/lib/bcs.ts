/**
 * The Bluetooth SIG Weight Scale and Body Composition services.
 *
 * The BF720 speaks these rather than Beurer's proprietary protocol - it is why
 * plan 0015 is cheap, and openScale's handler for it is called
 * `StandardBeurerSanitasHandler` for the same reason. Everything below is
 * decoded from published field layouts, not reverse-engineered.
 *
 * Pure functions over `DataView`, deliberately: no BLE, no network, so the
 * whole decoder runs in CI against fixture bytes. The BLE plumbing that feeds
 * it lives in `scale.ts` and cannot be tested without hardware.
 */

/** 0x181D — Weight Scale Service. */
export const WEIGHT_SCALE_SERVICE = 0x181d;
/** 0x2A9D — Weight Measurement. */
export const WEIGHT_MEASUREMENT_CHAR = 0x2a9d;
/** 0x181B — Body Composition Service. */
export const BODY_COMPOSITION_SERVICE = 0x181b;
/** 0x2A9C — Body Composition Measurement. */
export const BODY_COMPOSITION_CHAR = 0x2a9c;
/** 0x181C — User Data Service, which gates the measurements behind consent. */
export const USER_DATA_SERVICE = 0x181c;
/** 0x2A9F — User Control Point (indications). */
export const USER_CONTROL_POINT_CHAR = 0x2a9f;
/** 0x2A99 — Database Change Increment. */
export const DB_CHANGE_INCREMENT_CHAR = 0x2a99;
/** 0x2A85 — Date of Birth. */
export const USER_DOB_CHAR = 0x2a85;
/** 0x2A8C — Gender: 0 male, 1 female. */
export const USER_GENDER_CHAR = 0x2a8c;
/** 0x2A8E — Height, in centimetres. */
export const USER_HEIGHT_CHAR = 0x2a8e;
/** 0x1805 / 0x2A2B — Current Time, so replayed history is stamped correctly. */
export const CURRENT_TIME_SERVICE = 0x1805;
export const CURRENT_TIME_CHAR = 0x2a2b;
export const BATTERY_SERVICE = 0x180f;

/**
 * Beurer's vendor service, and the reason this file is no longer SIG-only.
 *
 * The SIG profile can consent to a slot but cannot *enumerate* what slots the
 * scale already has, and it has no way to ask for stored readings. Both live
 * here, on `0000ffff-…`, and openScale's `StandardBeurerSanitasHandler` drives
 * exactly these four characteristics for the BF105/720.
 *
 * Without them a client can only register a slot of its own and read what is
 * measured while it is connected — which is the whole trap this codebase spent
 * a day in, and which the comments in `scale.ts` used to state as a hardware
 * limitation. It is not one.
 */
export const BEURER_SERVICE = 0xffff;
/** 0x0001 — the on-device user list. Write to request, notify to receive. */
export const BEURER_USER_LIST_CHAR = 0x0001;
/**
 * 0x0006 — write 0x00 to make the scale send the consented user's stored
 * readings. openScale calls this `TAKE_MEASUREMENT` and fires it immediately
 * after consent; the name is misleading, since nothing can make a scale weigh
 * an absent person. What it does is release the history.
 */
export const BEURER_REQUEST_STORED_CHAR = 0x0006;

/** Status bytes leading a user-list notification. */
export const USER_LIST_END = 0x01;
export const USER_LIST_EMPTY = 0x02;

/**
 * UDS User Control Point opcodes.
 *
 * `REGISTER_NEW_USER` (0x01) is deliberately absent. Helf attaches to the one
 * slot the scale already has and never provisions another: registering is what
 * consumed slots 2 and 3 during development, and a scale that quietly grows a
 * user per failed pairing is a scale whose history is split across slots that
 * nothing will ever read again.
 */
export const UDS_CONSENT = 0x02;
export const UDS_RESPONSE = 0x20;

/** User Data Service control-point response values. */
export const UDS_RESP_SUCCESS = 0x01;
export const UDS_RESP_OP_NOT_SUPPORTED = 0x02;
export const UDS_RESP_INVALID_PARAMETER = 0x03;
export const UDS_RESP_OPERATION_FAILED = 0x04;
export const UDS_RESP_USER_NOT_AUTHORIZED = 0x05;

const KG_TO_LB = 2.2046226218487757;

/**
 * 0xFFFF is the spec's "measurement could not be taken".
 *
 * openScale does not filter it and would render 6553.5%. Left unhandled it
 * would reach `metric` as a real value, and a stray 6553.5 in `body_fat_pct`
 * is the kind of thing that survives into a chart axis and makes eight months
 * of history unreadable.
 */
const UNAVAILABLE = 0xffff;

const u16 = (v: DataView, o: number): number | null => {
    const raw = v.getUint16(o, true);
    return raw === UNAVAILABLE ? null : raw;
};

const scale = (raw: number | null, factor: number): number | null =>
    raw === null ? null : raw * factor;

export interface RawWeightMeasurement {
    isKg: boolean;
    weight: number | null;
    measuredAt: Date | null;
    userIndex: number | null;
    bmi: number | null;
}

export interface RawBodyComposition {
    isKg: boolean;
    bodyFatPct: number | null;
    measuredAt: Date | null;
    userIndex: number | null;
    musclePct: number | null;
    muscleMass: number | null;
    fatFreeMass: number | null;
    softLeanMass: number | null;
    bodyWaterMass: number | null;
    impedanceOhm: number | null;
    weight: number | null;
    multiPacket: boolean;
}

/** The 7-byte SIG date-time, read as the scale's local wall clock. */
const readTimestamp = (v: DataView, o: number): Date =>
    new Date(
        v.getUint16(o, true),
        Math.max(v.getUint8(o + 2) - 1, 0),
        v.getUint8(o + 3),
        v.getUint8(o + 4),
        v.getUint8(o + 5),
        v.getUint8(o + 6),
    );

/**
 * Decode 0x2A9D.
 *
 * The BF720 sends weight here and body composition on 0x2A9C, as two packets
 * describing one weighing - see `mergeMeasurement`.
 */
export function parseWeightMeasurement(
    v: DataView,
): RawWeightMeasurement | null {
    if (v.byteLength < 3) return null;
    let o = 0;

    const flags = v.getUint8(o);
    o += 1;
    const isKg = (flags & 0x01) === 0;
    const hasTimestamp = (flags & 0x02) !== 0;
    const hasUser = (flags & 0x04) !== 0;
    const hasBmiHeight = (flags & 0x08) !== 0;

    // Bit 0 selects the unit, and it is the single most dangerous field here.
    // `mqtt_service.py` multiplies by KG_TO_LB unconditionally, correctly,
    // because openScale always sends kilograms. This does not: the scale
    // reports in whatever it displays. Converting regardless would put ~190 kg
    // in `body_weight_lb` - plausible against nothing, wrong by 2.2x.
    const massFactor = isKg ? 0.005 : 0.01;

    const weight = scale(u16(v, o), massFactor);
    o += 2;

    let measuredAt: Date | null = null;
    if (hasTimestamp) {
        measuredAt = readTimestamp(v, o);
        o += 7;
    }

    let userIndex: number | null = null;
    if (hasUser) {
        userIndex = v.getUint8(o);
        o += 1;
    }

    let bmi: number | null = null;
    if (hasBmiHeight) {
        bmi = scale(u16(v, o), 0.1);
        o += 2;
    }

    return { isKg, weight, measuredAt, userIndex, bmi };
}

/** Decode 0x2A9C. Field order is flag-driven; every offset below is load-bearing. */
export function parseBodyComposition(v: DataView): RawBodyComposition | null {
    if (v.byteLength < 4) return null;
    let o = 0;

    const flags = v.getUint16(o, true);
    o += 2;
    const isKg = (flags & 0x0001) === 0;
    const hasTimestamp = (flags & 0x0002) !== 0;
    const hasUser = (flags & 0x0004) !== 0;
    const hasBasal = (flags & 0x0008) !== 0;
    const hasMusclePct = (flags & 0x0010) !== 0;
    const hasMuscleMass = (flags & 0x0020) !== 0;
    const hasFatFree = (flags & 0x0040) !== 0;
    const hasSoftLean = (flags & 0x0080) !== 0;
    const hasWaterMass = (flags & 0x0100) !== 0;
    const hasImpedance = (flags & 0x0200) !== 0;
    const hasWeight = (flags & 0x0400) !== 0;
    const hasHeight = (flags & 0x0800) !== 0;
    const multiPacket = (flags & 0x1000) !== 0;

    const massFactor = isKg ? 0.005 : 0.01;

    // Body fat is the one mandatory field, immediately after the flags.
    const bodyFatPct = scale(u16(v, o), 0.1);
    o += 2;

    let measuredAt: Date | null = null;
    if (hasTimestamp) {
        measuredAt = readTimestamp(v, o);
        o += 7;
    }

    let userIndex: number | null = null;
    if (hasUser) {
        userIndex = v.getUint8(o);
        o += 1;
    }

    // Basal metabolism is in kJ. helf has no metric name for it and adding one
    // is a migration by design (AGENTS.md), so it is skipped rather than
    // silently coerced into something that does exist.
    if (hasBasal) o += 2;

    let musclePct: number | null = null;
    if (hasMusclePct) {
        musclePct = scale(u16(v, o), 0.1);
        o += 2;
    }

    let muscleMass: number | null = null;
    if (hasMuscleMass) {
        muscleMass = scale(u16(v, o), massFactor);
        o += 2;
    }

    let fatFreeMass: number | null = null;
    if (hasFatFree) {
        fatFreeMass = scale(u16(v, o), massFactor);
        o += 2;
    }

    let softLeanMass: number | null = null;
    if (hasSoftLean) {
        softLeanMass = scale(u16(v, o), massFactor);
        o += 2;
    }

    let bodyWaterMass: number | null = null;
    if (hasWaterMass) {
        bodyWaterMass = scale(u16(v, o), massFactor);
        o += 2;
    }

    let impedanceOhm: number | null = null;
    if (hasImpedance) {
        impedanceOhm = scale(u16(v, o), 0.1);
        o += 2;
    }

    let weight: number | null = null;
    if (hasWeight) {
        weight = scale(u16(v, o), massFactor);
        o += 2;
    }

    if (hasHeight) o += 2;

    return {
        isKg,
        bodyFatPct,
        measuredAt,
        userIndex,
        musclePct,
        muscleMass,
        fatFreeMass,
        softLeanMass,
        bodyWaterMass,
        impedanceOhm,
        weight,
        multiPacket,
    };
}

/**
 * One drained reading, in the shape `POST /api/body-composition/sync/scale`
 * takes. Field names match `BodyCompositionCreate` exactly, including the two
 * that are misleading and documented in AGENTS.md: `muscle_mass` holds a
 * **percentage**, and `bone_mass_kg` is kilograms while `weight` is pounds.
 */
export interface ScaleReading {
    timestamp: string;
    date: string;
    weight: number;
    body_fat_pct?: number | null;
    muscle_mass?: number | null;
    water_pct?: number | null;
    bone_mass_kg?: number | null;
    bmi?: number | null;
}

/**
 * Render the scale's wall clock verbatim - **never** `toISOString()`.
 *
 * `observation.observed_at` is written with
 * `strftime("%Y-%m-%d %H:%M:%S.%f")`, which discards the timezone entirely,
 * and eight months of openScale history is stored as local wall-clock time.
 * `toISOString()` converts to UTC first, so every drained reading would land
 * seven or eight hours ahead of where the same weighing belongs - misaligned
 * with the existing series, and offset by a different amount either side of a
 * DST boundary.
 *
 * `UNIQUE (observed_at, source)` is a textual comparison, so this also decides
 * whether a replayed reading deduplicates or silently doubles.
 */
export function formatLocalTimestamp(d: Date): string {
    const p = (n: number, w = 2) => String(n).padStart(w, "0");
    return (
        `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` +
        `T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
    );
}

export const localDate = (d: Date): string =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate(),
    ).padStart(2, "0")}`;

/**
 * Fold a weight packet and a body-composition packet into one reading, and
 * convert to helf's canonical units.
 *
 * Three conversions here are not obvious:
 *
 * - **Weight to pounds** only when the scale reported SI (ADR-0003).
 * - **Water as a percentage.** The service reports body water *mass*, but
 *   `water_pct` is a percentage and `metric_def` names it as one. The ratio is
 *   unit-free, so it is computed before any conversion.
 * - **Bone in kilograms**, derived the way openScale derives it: lean body
 *   mass minus soft lean mass. It stays kg while its neighbours are pounds
 *   because `metric_def` already defines `bone_mass_kg` for DEXA, and one
 *   quantity under two names is exactly what ADR-0003 exists to prevent.
 */
export function toScaleReading(
    comp: RawBodyComposition | null,
    weightPacket: RawWeightMeasurement | null,
): ScaleReading | null {
    // The unit flag belongs to the packet carrying the value, and the two can
    // disagree — a live composition packet declares a unit even when it sends
    // no weight at all. Reading `isKg` off the wrong packet double-converts:
    // 188.4 lb becomes 415.35.
    const compHasWeight = comp?.weight != null;
    const nativeWeight = compHasWeight
        ? (comp as RawBodyComposition).weight
        : (weightPacket?.weight ?? null);
    const weightIsKg = compHasWeight
        ? (comp as RawBodyComposition).isKg
        : (weightPacket?.isKg ?? comp?.isKg ?? true);

    const measuredAt = comp?.measuredAt ?? weightPacket?.measuredAt ?? null;

    // Without a weight there is no measurement, and without an instant there
    // is nothing to deduplicate against - a reading stamped "now" would import
    // afresh on every drain and pile up thirty copies a fortnight.
    if (nativeWeight === null || nativeWeight <= 0 || measuredAt === null) {
        return null;
    }

    // Normalise to kilograms first, so a ratio between two masses can never be
    // taken across two different units.
    const weightKg = weightIsKg ? nativeWeight : nativeWeight / KG_TO_LB;
    const compMassKg = (m: number) => (comp?.isKg ? m : m / KG_TO_LB);

    const bodyFatPct = comp?.bodyFatPct ?? null;

    let waterPct: number | null = null;
    if (comp?.bodyWaterMass != null) {
        waterPct = (compMassKg(comp.bodyWaterMass) / weightKg) * 100;
    }

    let boneKg: number | null = null;
    if (comp?.softLeanMass != null && bodyFatPct != null) {
        const leanKg = weightKg - weightKg * (bodyFatPct / 100);
        const bone = leanKg - compMassKg(comp.softLeanMass);
        if (bone > 0) boneKg = bone;
    }

    const round = (n: number | null, dp = 2) =>
        n === null ? null : Math.round(n * 10 ** dp) / 10 ** dp;

    return {
        timestamp: formatLocalTimestamp(measuredAt),
        date: localDate(measuredAt),
        weight: round(weightKg * KG_TO_LB) as number,
        body_fat_pct: round(bodyFatPct),
        // The API calls this `muscle_mass` and stores `muscle_pct`. It is a
        // percentage; see AGENTS.md.
        muscle_mass: round(comp?.musclePct ?? null),
        water_pct: round(waterPct),
        bone_mass_kg: round(boneKg),
        bmi: round(weightPacket?.bmi ?? null),
    };
}

/** One packet, in arrival order. Order is the only thing that pairs some of them. */
export type ScalePacket =
    | { kind: "weight"; value: RawWeightMeasurement }
    | { kind: "composition"; value: RawBodyComposition };

/**
 * Group packets arriving during one drain into readings.
 *
 * Pairing is by timestamp *where there is one*, and by arrival order where
 * there is not — because the BF720 uses both. A history replay stamps every
 * packet, so timestamps pair it safely even if packets arrive out of order. A
 * live weighing does not: the composition packet carries flags 0x0398, with
 * the timestamp and weight bits clear, and means "this belongs to the weight
 * packet you just received".
 *
 * An earlier version keyed purely on timestamps and justified it as immune to
 * drift. It was — and it silently discarded every live body-composition
 * packet, because an unstamped packet matched nothing and a reading with no
 * timestamp and no weight is dropped. That looked exactly like a scale not
 * sending bioimpedance at all.
 */
export function pairPackets(packets: ScalePacket[]): ScaleReading[] {
    const key = (d: Date | null) => (d ? formatLocalTimestamp(d) : "");

    interface Group {
        at: string;
        weight: RawWeightMeasurement | null;
        comp: RawBodyComposition | null;
    }
    const groups: Group[] = [];
    const find = (at: string) =>
        at ? groups.find((g) => g.at === at) : undefined;

    for (const packet of packets) {
        const at = key(packet.value.measuredAt);

        if (packet.kind === "weight") {
            const existing = find(at);
            if (existing && !existing.weight) existing.weight = packet.value;
            else groups.push({ at, weight: packet.value, comp: null });
            continue;
        }

        const existing = find(at);
        if (existing && !existing.comp) {
            existing.comp = packet.value;
            continue;
        }
        if (at) {
            groups.push({ at, weight: null, comp: packet.value });
            continue;
        }

        // Unstamped: it describes the most recent weighing that does not
        // already have composition. Searching backwards rather than taking the
        // last group keeps a stamped history replay from stealing it.
        const owner = [...groups].reverse().find((g) => g.weight && !g.comp);
        if (owner) owner.comp = packet.value;
    }

    return groups
        .map((g) => toScaleReading(g.comp, g.weight))
        .filter((r): r is ScaleReading => r !== null)
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

export interface UserControlPointResponse {
    /** The opcode this answers — `UDS_CONSENT` for a consent attempt. */
    requestOpcode: number;
    /** `UDS_RESP_*`. */
    value: number;
    /** REGISTER_NEW_USER returns the slot it allocated; otherwise absent. */
    userIndex: number | null;
}

/**
 * Decode an indication from the User Control Point (0x2A9F).
 *
 * Worth having because a successful `writeValue` says only that the request
 * was *delivered*. The scale's verdict comes back separately, here. Without
 * reading it, a rejected consent and an empty history buffer are the same
 * observable event — a connection that yields no measurements — and that
 * ambiguity cost a debugging round on the first real drain.
 *
 * Layout is `[0x20, requestOpcode, resultValue, ...]`.
 */
export function parseUserControlPointResponse(
    v: DataView,
): UserControlPointResponse | null {
    if (v.byteLength < 3) return null;
    if (v.getUint8(0) !== UDS_RESPONSE) return null;

    return {
        requestOpcode: v.getUint8(1),
        value: v.getUint8(2),
        userIndex: v.byteLength >= 4 ? v.getUint8(3) : null,
    };
}

/**
 * What to tell the user when the scale refuses.
 *
 * Every message names P01 because that is the only slot Helf will ever use,
 * and every one of them ends in something to do. A refusal here is recoverable
 * without a reset in all but one case, and the recovery — make the scale show
 * its own code — is not discoverable from the scale's manual.
 */
export function describeControlPointFailure(
    response: UserControlPointResponse,
): string {
    switch (response.value) {
        case UDS_RESP_USER_NOT_AUTHORIZED:
            return "P01 rejected that code. The scale is now showing the right one on its display - read it off and enter it below.";
        case UDS_RESP_INVALID_PARAMETER:
            return "This scale has no P01 in its Bluetooth user registry. Set up P01 on the scale itself, then try again.";
        case UDS_RESP_OP_NOT_SUPPORTED:
            return "This scale does not accept a consent code over Bluetooth, which means it is not the BF720 this was written for.";
        case UDS_RESP_OPERATION_FAILED:
            return "The scale failed the consent for P01 without saying why. If it was just reset, set P01 up on the scale first.";
        default:
            return `The scale refused consent for P01 (code ${response.value}).`;
    }
}

/**
 * The profile the scale needs before it will compute anything but mass.
 *
 * A BF720's own on-device user profile is **not** the profile a connected
 * client gets. Consent grants access to a User Data Service slot, and the
 * scale derives bioimpedance for that slot from the values written into it —
 * which for a slot nothing has ever written are absent or defaulted. The
 * result is a drain that reports weight and BMI (against a default height) and
 * silently omits body fat, muscle and water. Confirmed on hardware: with the
 * slot's height written, BMI moved from 31.0 to 28.5 and 0x2A9C began firing.
 *
 * The values come from `ScaleUserEntry` — P01 as the scale itself holds it —
 * not from anything retyped into Helf. Two profiles for one person is one too
 * many, and the scale's is the one its own bioimpedance model was calibrated
 * against.
 */

/** 0x2A85 — year as uint16 LE, then month and day. */
export function dateOfBirthPayload(u: ScaleUserEntry): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([
        u.birthYear & 0xff,
        (u.birthYear >> 8) & 0xff,
        u.birthMonth & 0xff,
        u.birthDay & 0xff,
    ]);
}

/** 0x2A8C — the profile carries only the two values the SIG enum defines. */
export function genderPayload(u: ScaleUserEntry): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([u.sex === "female" ? 1 : 0]);
}

/**
 * 0x2A8E — centimetres as uint16 LE.
 *
 * Two bytes matter even though the scale reports height in one: the
 * characteristic is defined as uint16, and a short write is something firmware
 * may reject outright.
 */
export function heightPayload(u: ScaleUserEntry): Uint8Array<ArrayBuffer> {
    const cm = Math.round(Math.min(Math.max(u.heightCm, 0), 300));
    return Uint8Array.from([cm & 0xff, (cm >> 8) & 0xff]);
}

/**
 * 0x2A99 — bump the database revision so the scale treats the profile above as
 * newly written rather than as the stale copy it already had.
 */
export function changeIncrementPayload(): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([1, 0, 0, 0]);
}

/**
 * One entry in the scale's on-device user list, or a marker ending it.
 *
 * This is the list the scale shows as P01, P02 … when someone steps on it.
 * It is a **different store** from the SIG User Data Service registry: the
 * profile here is what the user configured on the scale's own control unit,
 * and reading it is the only way to tell "P01 exists and is mine" apart from
 * "P01 was wiped by a reset".
 */
export type ScaleUserListEvent =
    | { kind: "user"; user: ScaleUserEntry }
    | { kind: "end" }
    | { kind: "empty" };

export interface ScaleUserEntry {
    /** The slot number, as printed on the scale: P01 is 1. */
    index: number;
    /** Three characters, or null where the slot has never been named. */
    initials: string | null;
    birthYear: number;
    birthMonth: number;
    birthDay: number;
    /** Centimetres — the wire unit. Converted at the UI boundary, not here. */
    heightCm: number;
    sex: "male" | "female";
    /** 1-5 as the scale numbers it. Feeds its bioimpedance model. */
    activityLevel: number;
}

/**
 * Decode a notification from the vendor user-list characteristic (0xFFFF/0x0001).
 *
 * The status byte leads: 0x02 means the scale holds no users at all, 0x01
 * terminates the list, anything else is a user record. Entries arrive one
 * notification each, so a caller accumulates until it sees an end marker.
 */
export function parseScaleUserList(v: DataView): ScaleUserListEvent | null {
    if (v.byteLength < 1) return null;

    const status = v.getUint8(0);
    if (status === USER_LIST_EMPTY) return { kind: "empty" };
    if (status === USER_LIST_END) return { kind: "end" };
    if (v.byteLength < 12) return null;

    // Bytes 2-4 are the initials. 0xFF throughout is the scale's "unnamed",
    // which would otherwise decode to three replacement characters.
    const raw = [v.getUint8(2), v.getUint8(3), v.getUint8(4)];
    const initials = raw.every((b) => b === 0xff)
        ? null
        : String.fromCharCode(...raw.filter((b) => b > 0x20 && b < 0x7f)) || null;

    return {
        kind: "user",
        user: {
            index: v.getUint8(1),
            initials,
            birthYear: v.getUint16(5, true),
            birthMonth: v.getUint8(7),
            birthDay: v.getUint8(8),
            heightCm: v.getUint8(9),
            sex: v.getUint8(10) === 0 ? "male" : "female",
            activityLevel: v.getUint8(11),
        },
    };
}

/** Ask the scale to send its user list. */
export function userListRequestPayload(): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([0x00]);
}

/**
 * Ask the scale to show a slot's consent code **on its own display**.
 *
 * The code is never readable over the air — that is the point of it — so this
 * is the only way to recover one that was never written down. The scale wants
 * the slot offset into the top nibble: P01 is 0x11, P02 is 0x12.
 */
export function pinDisplayPayload(userIndex: number): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([(0x10 + userIndex) & 0xff]);
}

/**
 * Ask the scale to release the consented user's stored readings.
 *
 * This is the byte that turns a live-only connection into a drain. Everything
 * else here was already right; without it the scale answers a consent and then
 * simply says nothing until someone stands on it.
 */
export function requestStoredPayload(): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([0x00]);
}
