import { describe, expect, it } from "vitest";

import {
    describeControlPointFailure,
    formatLocalTimestamp,
    pairPackets,
    parseBodyComposition,
    parseUserControlPointResponse,
    parseWeightMeasurement,
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
    const compAt = (h: number, weightRaw: number) =>
        parseBodyComposition(
            view([
                ...u16(0x0001 | 0x0002 | 0x0400),
                ...u16(185),
                ...stamp(2026, 8, 20, h, 0, 0),
                ...u16(weightRaw),
            ]),
        )!;

    const weightAt = (h: number, weightRaw: number) =>
        parseWeightMeasurement(
            view([
                WEIGHT_FLAG_IMPERIAL | WEIGHT_FLAG_TIMESTAMP,
                ...u16(weightRaw),
                ...stamp(2026, 8, 20, h, 0, 0),
            ]),
        )!;

    it("pairs on the instant, not on arrival order", () => {
        // A replay sends thirty weighings back to back. Buffering one slot the
        // way openScale does would shift every later pairing by one if a
        // packet arrived out of order.
        const readings = pairPackets(
            [weightAt(9, 18900), weightAt(7, 18840)],
            [compAt(7, 18840), compAt(9, 18900)],
        );
        expect(readings.map((r) => r.timestamp)).toEqual([
            "2026-08-20T07:00:00",
            "2026-08-20T09:00:00",
        ]);
        expect(readings[0].weight).toBeCloseTo(188.4, 2);
        expect(readings[1].weight).toBeCloseTo(189.0, 2);
    });

    it("keeps a weight packet that has no composition beside it", () => {
        const readings = pairPackets([weightAt(7, 18840)], []);
        expect(readings).toHaveLength(1);
        expect(readings[0].weight).toBeCloseTo(188.4, 2);
        expect(readings[0].body_fat_pct).toBeNull();
    });

    it("does not emit a reading twice when both packets are present", () => {
        const readings = pairPackets([weightAt(7, 18840)], [compAt(7, 18840)]);
        expect(readings).toHaveLength(1);
        expect(readings[0].body_fat_pct).toBeCloseTo(18.5, 2);
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
        expect(describeControlPointFailure(denied, 1)).toMatch(
            /rejected the consent code for slot 1/i,
        );
        // A reset is the likeliest cause and the message has to say so.
        expect(describeControlPointFailure(denied, 1)).toMatch(/reset/i);
    });

    it("names the slot in every failure message", () => {
        for (const value of [0x02, 0x03, 0x04, 0x05, 0x7f]) {
            const r = parseUserControlPointResponse(
                view([0x20, UDS_CONSENT, value]),
            )!;
            const message = describeControlPointFailure(r, 3);
            // 0x02 means the scale has no consent mechanism at all, so a slot
            // number would be misleading there and only there.
            if (value !== 0x02) expect(message).toMatch(/slot 3/i);
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
