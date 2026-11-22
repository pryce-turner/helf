import { describe, expect, it } from "vitest";
import { buildScript, conflictingMaxes } from "./programBuilder";
import type { BuilderModel } from "@/types/library";

const model: BuilderModel = {
    weeks: 2,
    days: [
        {
            name: "Press",
            items: [
                { kind: "block", name: "Press warm-up" },
                { kind: "wave", exercise: "Overhead Press", tm: 120 },
                { kind: "line", text: "Pull Up / 3x8" },
            ],
        },
        { name: "Squat", items: [{ kind: "wave", exercise: "Barbell Squat", tm: 245 }] },
    ],
};

describe("buildScript", () => {
    it("writes maxes at the top, then every day of every week in order", () => {
        expect(buildScript(model)).toBe(
            [
                "// Written by the program builder. Editing this by hand detaches it.",
                "// Training maxes - the 5/3/1 percentages are taken from these.",
                "// Overhead Press 1RM: 120lb",
                "// Barbell Squat 1RM: 245lb",
                "",
                "## Week 1 - Press",
                "[Press warm-up]",
                "Overhead Press / 1x5 65%, 1x5 75%, 1x5+ 85%",
                "Pull Up / 3x8",
                "",
                "## Week 1 - Squat",
                "Barbell Squat / 1x5 65%, 1x5 75%, 1x5+ 85%",
                "",
                "## Week 2 - Press",
                "[Press warm-up]",
                "Overhead Press / 1x3 70%, 1x3 80%, 1x3+ 90%",
                "Pull Up / 3x8",
                "",
                "## Week 2 - Squat",
                "Barbell Squat / 1x3 70%, 1x3 80%, 1x3+ 90%",
                "",
            ].join("\n"),
        );
    });

    it("repeats the wave past four weeks, and drops the week from a one-week program", () => {
        const six = buildScript({ ...model, weeks: 6, days: [model.days[1]] });
        expect(six).toContain("## Week 5 - Squat\nBarbell Squat / 1x5 65%");
        const one = buildScript({ ...model, weeks: 1 });
        expect(one).toContain("## Press\n");
        expect(one).not.toContain("Week");
    });
});

describe("conflictingMaxes", () => {
    it("names a lift given two different maxes", () => {
        const twice: BuilderModel = {
            weeks: 1,
            days: [
                { name: "A", items: [{ kind: "wave", exercise: "Deadlift", tm: 290 }] },
                { name: "B", items: [{ kind: "wave", exercise: "Deadlift", tm: 300 }] },
            ],
        };
        expect(conflictingMaxes(twice)).toEqual(["Deadlift"]);
        expect(conflictingMaxes(model)).toEqual([]);
    });
});
