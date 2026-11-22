import { describe, expect, it } from "vitest";
import { matchExercises } from "./exerciseSearch";
import type { Exercise } from "@/types/exercise";

const ex = (name: string, use_count = 0, category = "Core") =>
    ({ doc_id: name.length * 1000 + use_count, name, category, use_count }) as Exercise;

const CATALOG = [
    ex("Dumbbell Row", 220, "Back"),
    ex("Barbell Row", 29, "Back"),
    ex("Seated Cable Row", 115, "Back"),
    ex("Rower", 0, "Other"),
    ex("Romanian Deadlift", 67, "Legs"),
    ex("Deadlift", 359, "Back"),
];

const names = (query: string) => matchExercises(CATALOG, query).map((e) => e.name);

describe("matchExercises", () => {
    it("puts a name that starts with the query first", () => {
        expect(names("row")[0]).toBe("Rower");
    });

    it("then names where a word starts with it, most used first", () => {
        expect(names("row")).toEqual(["Rower", "Dumbbell Row", "Seated Cable Row", "Barbell Row"]);
    });

    it("needs every term to match, in any order", () => {
        expect(names("row dumb")).toEqual(["Dumbbell Row"]);
        expect(names("dead rom")).toEqual(["Romanian Deadlift"]);
    });

    it("is case-insensitive, and lists nothing for an empty query", () => {
        expect(names("DEADLIFT")).toEqual(["Deadlift", "Romanian Deadlift"]);
        expect(names("   ")).toEqual([]);
    });

    it("finds a substring inside a word last", () => {
        expect(names("lift")).toEqual(["Deadlift", "Romanian Deadlift"]);
    });
});
