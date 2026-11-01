import { describe, expect, it } from "vitest";
import { formatDuration, parseDuration } from "./cardio";

describe("parseDuration", () => {
    it("reads mm:ss", () => {
        expect(parseDuration("32:15")).toBe(1935);
    });

    it("reads h:mm:ss", () => {
        expect(parseDuration("1:05:00")).toBe(3900);
    });

    it("reads a bare number as minutes", () => {
        expect(parseDuration("45")).toBe(2700);
    });

    it("tolerates surrounding whitespace", () => {
        expect(parseDuration(" 20:00 ")).toBe(1200);
    });

    it("is null for an empty field", () => {
        expect(parseDuration("")).toBeNull();
    });

    it("is null for anything it cannot read, rather than guessing", () => {
        expect(parseDuration("20:75")).toBeNull();
        expect(parseDuration("20 min")).toBeNull();
        expect(parseDuration("1:2:3:4")).toBeNull();
    });
});

describe("formatDuration", () => {
    it("writes under an hour as m:ss", () => {
        expect(formatDuration(1935)).toBe("32:15");
    });

    it("writes an hour or more as h:mm:ss", () => {
        expect(formatDuration(3900)).toBe("1:05:00");
    });

    it("writes nothing for no duration", () => {
        expect(formatDuration(null)).toBe("");
    });

    it("round-trips what it parses", () => {
        expect(formatDuration(parseDuration("7:05"))).toBe("7:05");
    });
});
