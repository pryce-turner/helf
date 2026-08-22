import { describe, expect, it } from "vitest";

import {
    changeIncrementPayload,
    dateOfBirthPayload,
    describeControlPointFailure,
    genderPayload,
    heightPayload,
    formatLocalTimestamp,
    pairPackets,
    parseBodyComposition,
    parseUserControlPointResponse,
    parseWeightMeasurement,
    parseScaleUserList,
    pinDisplayPayload,
    toScaleReading,
} from "./bcs";

const view = (bytes: number[]) => new DataView(Uint8Array.from(bytes).buffer);
const u16 = (n: number) => [n & 0xff, (n >> 8) & 0xff];
/** The SIG 7-byte date-time: year LE, month, day, hour, minute, second. */
const stamp = (y: number, mo: number, d: number, h: number, mi: number, s = 0) => [
    ...u16(y),
    mo,
    d,
    h,
    mi,
    s,
];

const WEIGHT_FLAG_IMPERIAL = 0x01;
const WEIGHT_FLAG_TIMESTAMP = 0x02;

describe("parseWeightMeasurement", () => {
    it("scales a kilogram reading by 0.005", () => {
        // flags=0 (SI), raw 17000 * 0.005 = 85 kg
        const m = parseWeightMeasurement(view([0x00, ...u16(17000)]))!;
        expect(m.isKg).toBe(true);
        expect(m.weight).toBeCloseTo(85, 5);
    });

    it("scales a pound reading by 0.01 and does not convert it", () => {
        // The trap plan 0015 §5 exists for. `mqtt_service.py` multiplies by
        // KG_TO_LB unconditionally because openScale always sends kg; doing
        // that here would report 415 lb for a 188 lb man.
        const m = parseWeightMeasurement(
            view([WEIGHT_FLAG_IMPERIAL, ...u16(18840)]),
        )!;
        expect(m.isKg).toBe(false);
        expect(m.weight).toBeCloseTo(188.4, 5);
    });

    it("reads the timestamp as the scale's wall clock", () => {
        const m = parseWeightMeasurement(
            view([
                WEIGHT_FLAG_IMPERIAL | WEIGHT_FLAG_TIMESTAMP,
                ...u16(18840),
                ...stamp(2026, 8, 20, 7, 31, 12),
            ]),
        )!;
        expect(formatLocalTimestamp(m.measuredAt!)).toBe("2026-08-20T07:31:12");
    });
});

describe("parseBodyComposition", () => {
    /** Imperial + timestamp + musclePct + softLean + water + weight. */
    const FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0080 | 0x0100 | 0x0400;

    const packet = view([
        ...u16(FLAGS),
        ...u16(185), // body fat 18.5%
        ...stamp(2026, 8, 20, 7, 31, 12),
        ...u16(387), // muscle 38.7%
        ...u16(14584), // soft lean mass 145.84 lb
        ...u16(10000), // body water mass 100.00 lb
        ...u16(18840), // weight 188.40 lb
    ]);

    it("decodes the flag-driven field order", () => {
        const c = parseBodyComposition(packet)!;
        expect(c.isKg).toBe(false);
        expect(c.bodyFatPct).toBeCloseTo(18.5, 5);
        expect(c.musclePct).toBeCloseTo(38.7, 5);
        expect(c.softLeanMass).toBeCloseTo(145.84, 5);
        expect(c.bodyWaterMass).toBeCloseTo(100, 5);
        expect(c.weight).toBeCloseTo(188.4, 5);
        // Absent flags must not consume bytes.
        expect(c.muscleMass).toBeNull();
        expect(c.impedanceOhm).toBeNull();
    });

    it("treats 0xFFFF as unavailable rather than 6553.5", () => {
        const unavailable = view([
            ...u16(0x0001 | 0x0400),
            ...u16(0xffff),
            ...u16(18840),
        ]);
        const c = parseBodyComposition(unavailable)!;
        expect(c.bodyFatPct).toBeNull();
        expect(c.weight).toBeCloseTo(188.4, 5);
    });
});

describe("toScaleReading", () => {
    const FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0080 | 0x0100 | 0x0400;
    const comp = parseBodyComposition(
        view([
            ...u16(FLAGS),
            ...u16(185),
            ...stamp(2026, 8, 20, 7, 31, 12),
            ...u16(387),
            ...u16(14584),
            ...u16(10000),
            ...u16(18840),
        ]),
    );

    it("keeps pounds as pounds and derives water as a percentage", () => {
        const r = toScaleReading(comp, null)!;
        expect(r.weight).toBeCloseTo(188.4, 2);
        expect(r.body_fat_pct).toBeCloseTo(18.5, 2);
        // `muscle_mass` is the API's name for a percentage.
        expect(r.muscle_mass).toBeCloseTo(38.7, 2);
        // 100.00 lb of water in 188.40 lb of body.
        expect(r.water_pct).toBeCloseTo((100 / 188.4) * 100, 1);
    });

    it("derives bone mass in kilograms while weight stays in pounds", () => {
        const r = toScaleReading(comp, null)!;
        const leanLb = 188.4 - 188.4 * 0.185;
        const boneLb = leanLb - 145.84;
        expect(r.bone_mass_kg).toBeCloseTo(boneLb / 2.2046226218487757, 1);
        // The pair that looks like a bug and is not: ADR-0003.
        expect(r.bone_mass_kg!).toBeLessThan(r.weight);
    });

    it("converts a kilogram scale to pounds", () => {
        const kg = parseBodyComposition(
            view([
                ...u16(0x0002 | 0x0400),
                ...u16(185),
                ...stamp(2026, 8, 20, 7, 31, 12),
                ...u16(17000), // 85.000 kg
            ]),
        );
        expect(toScaleReading(kg, null)!.weight).toBeCloseTo(187.39, 1);
    });

    it("drops a reading with no timestamp", () => {
        // Nothing to key `UNIQUE (observed_at, source)` on, so stamping it
        // "now" would re-import the same weighing on every single drain.
        const undated = parseBodyComposition(
            view([...u16(0x0001 | 0x0400), ...u16(185), ...u16(18840)]),
        );
        expect(toScaleReading(undated, null)).toBeNull();
    });

    it("drops a packet carrying no weight", () => {
        const noWeight = parseBodyComposition(
            view([...u16(0x0001 | 0x0002), ...u16(185), ...stamp(2026, 8, 20, 7, 31)]),
        );
        expect(toScaleReading(noWeight, null)).toBeNull();
    });
});

describe("formatLocalTimestamp", () => {
    it("renders the wall clock, never UTC", () => {
        // `observed_at` is written with strftime and drops the timezone, and
        // eight months of history is local wall-clock. toISOString() would
        // shift every drained reading by the UTC offset.
        const d = new Date(2026, 7, 20, 7, 31, 12);
        expect(formatLocalTimestamp(d)).toBe("2026-08-20T07:31:12");
        expect(formatLocalTimestamp(d)).not.toBe(d.toISOString());
    });

    it("zero-pads every component", () => {
        expect(formatLocalTimestamp(new Date(2026, 0, 5, 6, 7, 8))).toBe(
            "2026-01-05T06:07:08",
        );
    });
});

describe("pairPackets", () => {
    const compAt = (h: number, weightRaw: number) => ({
        kind: "composition" as const,
        value: parseBodyComposition(
            view([
                ...u16(0x0001 | 0x0002 | 0x0400),
                ...u16(185),
                ...stamp(2026, 8, 20, h, 0, 0),
                ...u16(weightRaw),
            ]),
        )!,
    });

    const weightAt = (h: number, weightRaw: number) => ({
        kind: "weight" as const,
        value: parseWeightMeasurement(
            view([
                WEIGHT_FLAG_IMPERIAL | WEIGHT_FLAG_TIMESTAMP,
                ...u16(weightRaw),
                ...stamp(2026, 8, 20, h, 0, 0),
            ]),
        )!,
    });

    /** A live weighing: flags 0x0398, no timestamp and no weight of its own. */
    const liveComposition = {
        kind: "composition" as const,
        value: parseBodyComposition(
            view([...u16(0x0398), ...u16(265), ...u16(7817), ...u16(382), ...u16(12624), ...u16(8904), ...u16(5100)]),
        )!,
    };

    it("pairs stamped packets on the instant, not on arrival order", () => {
        const readings = pairPackets([
            weightAt(9, 18900),
            weightAt(7, 18840),
            compAt(7, 18840),
            compAt(9, 18900),
        ]);
        expect(readings.map((r) => r.timestamp)).toEqual([
            "2026-08-20T07:00:00",
            "2026-08-20T09:00:00",
        ]);
    });

    it("attaches an unstamped composition to the weighing it followed", () => {
        // The bug this exists for: a live BF720 sends weight (stamped) then
        // composition (flags 0x0398 — no timestamp, no weight). Keying purely
        // on timestamps matched nothing and dropped every live bioimpedance
        // reading, which looked identical to a scale not sending any.
        const readings = pairPackets([weightAt(7, 18840), liveComposition]);
        expect(readings).toHaveLength(1);
        expect(readings[0].timestamp).toBe("2026-08-20T07:00:00");
        expect(readings[0].weight).toBeCloseTo(188.4, 1);
        expect(readings[0].body_fat_pct).toBeCloseTo(26.5, 1);
        expect(readings[0].muscle_mass).toBeCloseTo(38.2, 1);
        expect(readings[0].water_pct).toBeGreaterThan(0);
    });

    it("does not let a stamped replay steal an unstamped packet", () => {
        // Searching backwards for the most recent weighing without composition
        // is what keeps the live packet with the live weighing.
        const readings = pairPackets([
            weightAt(7, 18840),
            compAt(7, 18840),
            weightAt(9, 18900),
            liveComposition,
        ]);
        expect(readings).toHaveLength(2);
        expect(readings[1].timestamp).toBe("2026-08-20T09:00:00");
        expect(readings[1].body_fat_pct).toBeCloseTo(26.5, 1);
        expect(readings[0].body_fat_pct).toBeCloseTo(18.5, 1);
    });

    it("keeps a weight packet that has no composition beside it", () => {
        const readings = pairPackets([weightAt(7, 18840)]);
        expect(readings).toHaveLength(1);
        expect(readings[0].body_fat_pct).toBeNull();
    });

    it("drops an unstamped composition with no weighing to attach to", () => {
        expect(pairPackets([liveComposition])).toEqual([]);
    });
});

describe("parseUserControlPointResponse", () => {
    const UDS_CONSENT = 0x02;

    it("reads the opcode being answered and the verdict", () => {
        const ok = view([0x20, UDS_CONSENT, 0x01]);
        expect(parseUserControlPointResponse(ok)).toEqual({
            requestOpcode: UDS_CONSENT,
            value: 0x01,
            userIndex: null,
        });
    });

    it("reports a rejected consent code distinctly from success", () => {
        // The whole point: before this, a refused code and an empty history
        // buffer were the same observable event - a connection yielding no
        // measurements.
        const denied = parseUserControlPointResponse(
            view([0x20, UDS_CONSENT, 0x05]),
        )!;
        expect(denied.value).toBe(0x05);
        expect(describeControlPointFailure(denied)).toMatch(/P01 rejected/i);
        // The recovery is the scale printing its own code, and the message is
        // the only place the user is told to look at the display.
        expect(describeControlPointFailure(denied)).toMatch(/display/i);
    });

    it("names P01 in every failure message", () => {
        for (const value of [0x02, 0x03, 0x04, 0x05, 0x7f]) {
            const r = parseUserControlPointResponse(
                view([0x20, UDS_CONSENT, value]),
            )!;
            const message = describeControlPointFailure(r);
            // 0x02 means the scale has no consent mechanism at all, so naming
            // a slot would be misleading there and only there.
            if (value !== 0x02) expect(message).toMatch(/P01/);
            expect(message.length).toBeGreaterThan(20);
        }
    });

    it("returns the allocated slot when one is included", () => {
        const registered = parseUserControlPointResponse(
            view([0x20, 0x01, 0x01, 0x04]),
        )!;
        expect(registered.userIndex).toBe(4);
    });

    it("ignores anything that is not a control-point response", () => {
        // Notifications on this characteristic are not all responses; treating
        // one as a verdict would abort a healthy drain.
        expect(parseUserControlPointResponse(view([0x01, 0x02, 0x03]))).toBeNull();
        expect(parseUserControlPointResponse(view([0x20, UDS_CONSENT]))).toBeNull();
        expect(parseUserControlPointResponse(view([]))).toBeNull();
    });
});

describe("UDS profile payloads", () => {
    // P01 as the scale reports it. Nothing here is retyped by the user, which
    // is the point: the slot ends up agreeing with the profile the scale's own
    // bioimpedance model uses.
    const profile = {
        index: 1,
        initials: "PT",
        heightCm: 183,
        birthYear: 1989,
        birthMonth: 7,
        birthDay: 4,
        sex: "male" as const,
        activityLevel: 3,
    };

    it("encodes date of birth as year LE then month, day", () => {
        // 1989 = 0x07C5
        expect([...dateOfBirthPayload(profile)]).toEqual([0xc5, 0x07, 7, 4]);
    });

    it("writes height as uint16 even though the scale reports one byte", () => {
        // The characteristic is uint16 by spec, and a short write is something
        // firmware may reject outright.
        expect([...heightPayload(profile)]).toEqual([183, 0]);
        expect(heightPayload(profile).length).toBe(2);
    });

    it("carries the high byte past 255cm", () => {
        expect([...heightPayload({ ...profile, heightCm: 259 })]).toEqual([3, 1]);
    });

    it("clamps an implausible height rather than wrapping it", () => {
        expect([...heightPayload({ ...profile, heightCm: 5000 })]).toEqual([44, 1]);
        expect([...heightPayload({ ...profile, heightCm: -10 })]).toEqual([0, 0]);
    });

    it("encodes sex as the SIG enum", () => {
        expect([...genderPayload(profile)]).toEqual([0]);
        expect([...genderPayload({ ...profile, sex: "female" })]).toEqual([1]);
    });

    it("bumps the change increment as uint32 LE", () => {
        // Without this the scale can treat the profile it already held as
        // current and ignore what was just written.
        expect([...changeIncrementPayload()]).toEqual([1, 0, 0, 0]);
    });
});

describe("pinDisplayPayload", () => {
    it("offsets the slot into the top nibble", () => {
        // openScale's `scalePinIndex = scaleIndex + 16`. P01 is 0x11.
        expect([...pinDisplayPayload(1)]).toEqual([0x11]);
        expect([...pinDisplayPayload(2)]).toEqual([0x12]);
    });

    it("is one byte, which is what distinguishes it from a list request", () => {
        // A bare 0x00 on the same characteristic asks for the user list. The
        // offset is the only thing separating "show the code" from "list
        // users", so an unoffset index would silently re-request the list.
        expect(pinDisplayPayload(1).length).toBe(1);
        expect(pinDisplayPayload(1)[0]).not.toBe(0x00);
    });
});

describe("parseScaleUserList", () => {
    const entry = (index: number, initials: number[]) =>
        view([
            0x00, // status: a user record
            index,
            ...initials, // bytes 2-4, so the year starts at offset 5
            0xc2,
            0x07, // 1986
            0x03, // March
            0x11, // 17th
            0xb2, // 178cm
            0x00, // male
            0x03, // activity level
        ]);

    it("decodes a user record", () => {
        const event = parseScaleUserList(entry(1, [0x50, 0x54, 0x00]))!;
        expect(event.kind).toBe("user");
        if (event.kind !== "user") throw new Error("unreachable");
        expect(event.user).toMatchObject({
            index: 1,
            initials: "PT",
            birthYear: 1986,
            birthMonth: 3,
            birthDay: 17,
            heightCm: 178,
            sex: "male",
            activityLevel: 3,
        });
    });

    it("reads an all-0xFF name as unnamed rather than as three glyphs", () => {
        // The scale's placeholder. Left alone it decodes to replacement
        // characters and reads as a real, if unpronounceable, user.
        const event = parseScaleUserList(entry(1, [0xff, 0xff, 0xff]))!;
        if (event.kind !== "user") throw new Error("unreachable");
        expect(event.user.initials).toBeNull();
    });

    it("distinguishes the end of the list from an empty scale", () => {
        // These are the two outcomes that decide whether P01 exists, and
        // conflating them is what would send Helf back to registering a slot.
        expect(parseScaleUserList(view([0x01]))).toEqual({ kind: "end" });
        expect(parseScaleUserList(view([0x02]))).toEqual({ kind: "empty" });
    });

    it("refuses a truncated user record instead of decoding garbage", () => {
        expect(parseScaleUserList(view([0x00, 0x01, 0x50]))).toBeNull();
        expect(parseScaleUserList(view([]))).toBeNull();
    });
});
