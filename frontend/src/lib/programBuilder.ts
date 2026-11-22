import type { BuilderItem, BuilderModel } from "@/types/library";

/**
 * The program builder writes script; it never reads one (plan 0022). Its
 * model is saved beside the script so it can be reopened, and editing the
 * script by hand detaches it.
 */

/** Wendler's waves, as percentages of the training max. Week 4 deloads. */
export const WAVE_531 = [
    "1x5 65%, 1x5 75%, 1x5+ 85%",
    "1x3 70%, 1x3 80%, 1x3+ 90%",
    "1x5 75%, 1x3 85%, 1x1+ 95%",
    "1x5 40%, 1x5 50%, 1x5 60%",
];

export const emptyBuilder = (): BuilderModel => ({ weeks: 4, days: [{ name: "Day 1", items: [] }] });

const itemLine = (item: BuilderItem, week: number): string => {
    switch (item.kind) {
        case "block":
            return `[${item.name}]`;
        case "wave":
            // The wave repeats every four weeks.
            return `${item.exercise} / ${WAVE_531[(week - 1) % WAVE_531.length]}`;
        case "line":
            return item.text.trim();
    }
};

export function buildScript(model: BuilderModel): string {
    const lines: string[] = ["// Written by the program builder. Editing this by hand detaches it."];

    // A wave lift's training max goes where the parser reads it: a `1RM`
    // line at the top. One per lift; the first day that names it sets it.
    const maxes = new Map<string, number>();
    for (const day of model.days) {
        for (const item of day.items) {
            if (item.kind === "wave" && !maxes.has(item.exercise)) maxes.set(item.exercise, item.tm);
        }
    }
    if (maxes.size > 0) {
        lines.push("// Training maxes - the 5/3/1 percentages are taken from these.");
        for (const [exercise, tm] of maxes) lines.push(`// ${exercise} 1RM: ${tm}lb`);
    }

    const weeks = Math.max(1, model.weeks);
    for (let week = 1; week <= weeks; week++) {
        for (const day of model.days) {
            const name = day.name.trim() || "Day";
            lines.push("", weeks > 1 ? `## Week ${week} - ${name}` : `## ${name}`);
            for (const item of day.items) {
                const line = itemLine(item, week);
                if (line) lines.push(line);
            }
        }
    }
    return lines.join("\n") + "\n";
}

/** Two wave items for one lift with different maxes: only the first counts. */
export function conflictingMaxes(model: BuilderModel): string[] {
    const seen = new Map<string, number>();
    const conflicts = new Set<string>();
    for (const day of model.days) {
        for (const item of day.items) {
            if (item.kind !== "wave") continue;
            const first = seen.get(item.exercise);
            if (first === undefined) seen.set(item.exercise, item.tm);
            else if (first !== item.tm) conflicts.add(item.exercise);
        }
    }
    return [...conflicts];
}
