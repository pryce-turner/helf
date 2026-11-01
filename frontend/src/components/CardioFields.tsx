import { useState } from "react";
import { Ruler, Timer } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    CARDIO_UNITS,
    DURATION_PATTERN,
    formatDuration,
    parseDuration,
} from "@/lib/cardio";

export interface CardioValue {
    duration_s?: number | null;
    amount?: number | null;
    amount_unit?: string | null;
}

/**
 * A cardio set's three fields: time, an amount, and what the amount counts.
 *
 * Time is typed as text and stored as seconds, so the field keeps what was
 * typed rather than reformatting mid-keystroke. It resyncs only when the
 * value changes from outside (a reset, a duplicate), which is what `seen`
 * tracks.
 */
export function CardioFields({
    value,
    onChange,
    idPrefix,
}: {
    value: CardioValue;
    onChange: (next: CardioValue) => void;
    idPrefix: string;
}) {
    const duration = value.duration_s ?? null;
    const [text, setText] = useState(formatDuration(duration));
    const [seen, setSeen] = useState(duration);
    if (duration !== seen) {
        setSeen(duration);
        if (parseDuration(text) !== duration) setText(formatDuration(duration));
    }

    return (
        <div
            className="grid grid-cols-1 md:grid-cols-3"
            style={{ gap: "var(--space-4)" }}
        >
            <div className="form-field">
                <Label htmlFor={`${idPrefix}-time`} className="form-label">
                    <Timer style={{ width: "14px", height: "14px" }} />
                    Time
                </Label>
                <Input
                    id={`${idPrefix}-time`}
                    type="text"
                    inputMode="numeric"
                    placeholder="mm:ss"
                    pattern={DURATION_PATTERN}
                    title="Minutes, mm:ss or h:mm:ss"
                    className="input--mono"
                    value={text}
                    onChange={(e) => {
                        const next = parseDuration(e.target.value);
                        setText(e.target.value);
                        setSeen(next);
                        onChange({ ...value, duration_s: next });
                    }}
                />
            </div>

            <div className="form-field">
                <Label htmlFor={`${idPrefix}-amount`} className="form-label">
                    <Ruler style={{ width: "14px", height: "14px" }} />
                    Amount
                </Label>
                <Input
                    id={`${idPrefix}-amount`}
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    placeholder="0"
                    className="input--mono"
                    value={value.amount ?? ""}
                    onChange={(e) =>
                        onChange({
                            ...value,
                            amount: e.target.value ? parseFloat(e.target.value) : null,
                        })
                    }
                />
            </div>

            <div className="form-field">
                <Label htmlFor={`${idPrefix}-unit`} className="form-label">
                    Unit
                </Label>
                <Select
                    value={value.amount_unit ?? undefined}
                    onValueChange={(unit) => onChange({ ...value, amount_unit: unit })}
                >
                    <SelectTrigger id={`${idPrefix}-unit`} aria-label="Unit">
                        <SelectValue placeholder="Select unit" />
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
        </div>
    );
}
