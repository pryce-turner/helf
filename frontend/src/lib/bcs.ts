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
/** 0x1805 / 0x2A2B — Current Time, so replayed history is stamped correctly. */
export const CURRENT_TIME_SERVICE = 0x1805;
export const CURRENT_TIME_CHAR = 0x2a2b;
export const BATTERY_SERVICE = 0x180f;

/** UDS User Control Point opcodes. */
export const UDS_REGISTER_NEW_USER = 0x01;
export const UDS_CONSENT = 0x02;
export const UDS_LIST_ALL_USERS = 0x04;
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
    const isKg = comp?.isKg ?? weightPacket?.isKg ?? true;
    const nativeWeight = comp?.weight ?? weightPacket?.weight ?? null;
    const measuredAt = comp?.measuredAt ?? weightPacket?.measuredAt ?? null;

    // Without a weight there is no measurement, and without an instant there
    // is nothing to deduplicate against - a reading stamped "now" would import
    // afresh on every drain and pile up thirty copies a fortnight.
    if (nativeWeight === null || nativeWeight <= 0 || measuredAt === null) {
        return null;
    }

    const toLb = (m: number) => (isKg ? m * KG_TO_LB : m);
    const toKg = (m: number) => (isKg ? m : m / KG_TO_LB);

    const bodyFatPct = comp?.bodyFatPct ?? null;

    let waterPct: number | null = null;
    if (comp?.bodyWaterMass != null) {
        waterPct = (comp.bodyWaterMass / nativeWeight) * 100;
    }

    let boneKg: number | null = null;
    if (comp?.softLeanMass != null && bodyFatPct != null) {
        const leanBodyMass = nativeWeight - nativeWeight * (bodyFatPct / 100);
        const bone = leanBodyMass - comp.softLeanMass;
        if (bone > 0) boneKg = toKg(bone);
    }

    const round = (n: number | null, dp = 2) =>
        n === null ? null : Math.round(n * 10 ** dp) / 10 ** dp;

    return {
        timestamp: formatLocalTimestamp(measuredAt),
        date: localDate(measuredAt),
        weight: round(toLb(nativeWeight)) as number,
        body_fat_pct: round(bodyFatPct),
        // The API calls this `muscle_mass` and stores `muscle_pct`. It is a
        // percentage; see AGENTS.md.
        muscle_mass: round(comp?.musclePct ?? null),
        water_pct: round(waterPct),
        bone_mass_kg: round(boneKg),
        bmi: round(weightPacket?.bmi ?? null),
    };
}

/**
 * Group packets arriving during one drain into readings.
 *
 * The scale sends a weight packet and a body-composition packet per weighing,
 * and openScale merges them with a one-slot buffer. Buffering is wrong for a
 * history replay: thirty weighings arrive back to back, and a dropped or
 * out-of-order packet would shift every later pairing by one. Pairing on the
 * timestamp cannot drift, because that is the value the two packets share and
 * the one the reading is keyed by.
 */
export function pairPackets(
    weights: RawWeightMeasurement[],
    comps: RawBodyComposition[],
): ScaleReading[] {
    const key = (d: Date | null) => (d ? formatLocalTimestamp(d) : "");

    const byInstant = new Map<string, RawWeightMeasurement>();
    for (const w of weights) {
        if (w.measuredAt) byInstant.set(key(w.measuredAt), w);
    }

    const readings: ScaleReading[] = [];
    const paired = new Set<string>();

    for (const c of comps) {
        const k = key(c.measuredAt);
        const reading = toScaleReading(c, byInstant.get(k) ?? null);
        if (reading) {
            readings.push(reading);
            paired.add(k);
        }
    }

    // A weight packet with no composition beside it is still a weighing, and a
    // weight is the one field helf cannot do without.
    for (const [k, w] of byInstant) {
        if (paired.has(k)) continue;
        const reading = toScaleReading(null, w);
        if (reading) readings.push(reading);
    }

    return readings.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
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

/** What to tell the user when the scale refuses. */
export function describeControlPointFailure(
    response: UserControlPointResponse,
    userIndex: number,
): string {
    switch (response.value) {
        case UDS_RESP_USER_NOT_AUTHORIZED:
            return `The scale rejected the consent code for slot ${userIndex}. The code is right for a different slot, or that slot was cleared - a scale reset wipes every slot and its code.`;
        case UDS_RESP_INVALID_PARAMETER:
            return `Slot ${userIndex} is not a slot this scale has. The BF720 has eight, numbered from 1.`;
        case UDS_RESP_OP_NOT_SUPPORTED:
            return "This scale does not accept a consent code over Bluetooth, which means it is not the BF720 this was written for.";
        case UDS_RESP_OPERATION_FAILED:
            return `The scale failed the consent for slot ${userIndex} without saying why. If it was just reset, set the user up on the scale first.`;
        default:
            return `The scale refused consent for slot ${userIndex} (code ${response.value}).`;
    }
}
