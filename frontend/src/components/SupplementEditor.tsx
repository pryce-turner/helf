import { useState } from "react";
import { format, parseISO } from "date-fns";
import { AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useFoodUsage, useUpdateFood } from "@/hooks/useFood";
import type { Food } from "@/types/food";

const MACROS = [
    ["kcal_per_serving", "kcal / serving"],
    ["protein_g", "protein g"],
    ["carb_g", "carbs g"],
    ["fat_g", "fat g"],
] as const;

type MacroField = (typeof MACROS)[number][0];

const asText = (value: number | null) => (value == null ? "" : String(value));
const asNumber = (value: string) => (value.trim() === "" ? null : Number(value));

/**
 * Editing the catalog entry, not the group.
 *
 * `serving_desc` and macros belong to the food; `servings` belongs to a
 * stack's membership. Until this existed there was no route to the former at
 * all — a typo in "1 softgel, 1000mg EPA" was permanent from the UI, and
 * whey's calories could only ever be set at creation.
 *
 * The reason this is a deliberate screen rather than an inline field: macros
 * are derived at read time, so changing them **rewrites every past entry's
 * totals**. That is the intended behaviour — it means a correction is a
 * correction, not a fork — but it is a surprising amount of history to move
 * without being told, so the size of it is on screen before you can save.
 */
const SupplementEditor = ({
    food,
    onDone,
}: {
    food: Food;
    onDone: () => void;
}) => {
    const [name, setName] = useState(food.name);
    const [brand, setBrand] = useState(food.brand);
    const [servingDesc, setServingDesc] = useState(food.serving_desc ?? "");
    const [macros, setMacros] = useState<Record<MacroField, string>>({
        kcal_per_serving: asText(food.kcal_per_serving),
        protein_g: asText(food.protein_g),
        carb_g: asText(food.carb_g),
        fat_g: asText(food.fat_g),
    });

    const { data: usage } = useFoodUsage(food.doc_id);
    const update = useUpdateFood();

    const macrosChanged = MACROS.some(
        ([field]) => asNumber(macros[field]) !== food[field],
    );
    const rewrites = macrosChanged ? (usage?.entries ?? 0) : 0;

    const failed = update.error as
        | { response?: { status?: number; data?: { detail?: string } } }
        | null;

    const submit = (event: React.FormEvent) => {
        event.preventDefault();
        if (!name.trim()) return;
        update.mutate(
            {
                id: food.doc_id,
                changes: {
                    name: name.trim(),
                    brand: brand.trim(),
                    serving_desc: servingDesc.trim() || null,
                    ...Object.fromEntries(
                        MACROS.map(([field]) => [field, asNumber(macros[field])]),
                    ),
                },
            },
            { onSuccess: onDone },
        );
    };

    return (
        <Card className="animate-in section">
            <CardContent style={{ paddingTop: "var(--space-5)" }}>
                <form onSubmit={submit}>
                    <div
                        className="grid grid-cols-1 md:grid-cols-2 section"
                        style={{ gap: "var(--space-3)" }}
                    >
                        <div className="form-field">
                            <label className="form-label" htmlFor="supp-name">
                                Name
                            </label>
                            <Input
                                id="supp-name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                autoComplete="off"
                            />
                        </div>
                        <div className="form-field">
                            <label className="form-label" htmlFor="supp-brand">
                                Brand
                            </label>
                            <Input
                                id="supp-brand"
                                value={brand}
                                placeholder="optional"
                                onChange={(e) => setBrand(e.target.value)}
                                autoComplete="off"
                            />
                        </div>
                    </div>

                    <div className="form-field section">
                        <label className="form-label" htmlFor="supp-serving">
                            Serving
                        </label>
                        <Input
                            id="supp-serving"
                            value={servingDesc}
                            placeholder="1 softgel, 1000mg EPA"
                            onChange={(e) => setServingDesc(e.target.value)}
                            autoComplete="off"
                        />
                        <p className="form-hint">
                            Free text. What one unit is — the number you take is on
                            the group, not here.
                        </p>
                    </div>

                    <div
                        className="grid grid-cols-2 md:grid-cols-4 section"
                        style={{ gap: "var(--space-3)" }}
                    >
                        {MACROS.map(([field, label]) => (
                            <div key={field} className="form-field">
                                <label className="form-label" htmlFor={`supp-${field}`}>
                                    {label}
                                </label>
                                <Input
                                    id={`supp-${field}`}
                                    type="number"
                                    inputMode="decimal"
                                    className="input--mono"
                                    placeholder="—"
                                    value={macros[field]}
                                    onChange={(e) =>
                                        setMacros({ ...macros, [field]: e.target.value })
                                    }
                                />
                            </div>
                        ))}
                    </div>

                    {/* Only when macros actually changed, and only when there is
                        history to move. A warning that fires on every edit is a
                        warning nobody reads. */}
                    {rewrites > 0 && (
                        <p className="retro-warning section">
                            <AlertTriangle style={{ width: "15px", height: "15px", flexShrink: 0 }} />
                            <span>
                                Changing macros rewrites <strong>{rewrites}</strong>{" "}
                                logged {rewrites === 1 ? "entry" : "entries"}
                                {usage?.first_logged &&
                                    ` back to ${format(parseISO(usage.first_logged), "d MMM yyyy")}`}
                                . Past totals will change to match — that is how a
                                correction is meant to work, but it is not undoable
                                from here.
                            </span>
                        </p>
                    )}

                    {usage && usage.stacks.length > 0 && (
                        <p className="form-hint section">
                            In {usage.stacks.join(", ")}.
                        </p>
                    )}

                    <div className="flex" style={{ gap: "var(--space-2)" }}>
                        <Button type="submit" disabled={!name.trim() || update.isPending}>
                            {update.isPending ? "Saving..." : "Save"}
                        </Button>
                        <Button type="button" variant="ghost" onClick={onDone}>
                            Cancel
                        </Button>
                    </div>

                    {update.isError && (
                        <p
                            style={{
                                fontSize: "12px",
                                color: "var(--error)",
                                marginTop: "var(--space-3)",
                            }}
                        >
                            {failed?.response?.status === 409
                                ? failed.response.data?.detail ??
                                  "Another supplement already has that name."
                                : "Could not save that."}
                        </p>
                    )}
                </form>
            </CardContent>
        </Card>
    );
};

export default SupplementEditor;
