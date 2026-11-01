import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { CARDIO_UNITS } from "@/lib/cardio";

/**
 * Whether an exercise is cardio, and if so what it is measured in.
 *
 * One value, not two: the exercise is cardio exactly when it has a unit
 * (`exercises.cardio_unit`), so the switch and the picker cannot disagree.
 * `""` is "switched on, no unit picked yet", which callers treat as
 * incomplete rather than as resistance.
 */
export function CardioSwitch({
    value,
    onChange,
    idPrefix,
}: {
    value: string | null;
    onChange: (next: string | null) => void;
    idPrefix: string;
}) {
    const on = value !== null;
    return (
        <div
            className="flex flex-wrap items-center"
            style={{ gap: "var(--space-4)", minHeight: "40px" }}
        >
            <div className="flex items-center" style={{ gap: "var(--space-3)" }}>
                <button
                    type="button"
                    role="switch"
                    id={`${idPrefix}-cardio`}
                    aria-checked={on}
                    aria-label="Cardio"
                    className="switch"
                    data-state={on ? "checked" : "unchecked"}
                    onClick={() => onChange(on ? null : "")}
                >
                    <span className="switch__thumb" />
                </button>
                <Label htmlFor={`${idPrefix}-cardio`}>Cardio</Label>
            </div>
            {on && (
                <div style={{ flex: "1 1 180px", maxWidth: "240px" }}>
                    <Select
                        value={value || undefined}
                        onValueChange={(unit) => onChange(unit)}
                    >
                        <SelectTrigger aria-label="Unit">
                            <SelectValue placeholder="Measured in…" />
                        </SelectTrigger>
                        <SelectContent>
                            {CARDIO_UNITS.map((u) => (
                                <SelectItem key={u.value} value={u.value}>
                                    {u.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            )}
        </div>
    );
}
