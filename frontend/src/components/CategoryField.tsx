import { useState } from "react";
import { Plus } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

/**
 * Pick a category, or name a new one.
 *
 * Free text was how a category got created here, which is also how one gets
 * created twice: "Biceps" and "biceps" are two rows, two accordions, and two
 * halves of one exercise history. The catalog already has 173 exercises across
 * eight categories, so the common case is choosing an existing one and typing
 * it out is both slower and the only way to misspell it.
 *
 * Creating one is still possible — a category list you cannot add to is worse
 * than a typo — but it is the last item rather than the default, so it is a
 * decision rather than an accident.
 */
const ADD_NEW = "__add_new__";

export function CategoryField({
    value,
    onChange,
    categories,
    id,
}: {
    value: string;
    onChange: (next: string) => void;
    categories: string[];
    id?: string;
}) {
    // A brand-new exercise starts with nothing selected; if the catalog has no
    // categories at all there is nothing to pick, so the field starts as text.
    const [naming, setNaming] = useState(categories.length === 0);

    if (naming) {
        return (
            <div className="flex" style={{ gap: "var(--space-2)" }}>
                <Input
                    id={id}
                    value={value}
                    placeholder="New category name"
                    onChange={(e) => onChange(e.target.value)}
                    autoComplete="off"
                    autoFocus
                    style={{ flex: "1 1 auto" }}
                />
                {categories.length > 0 && (
                    <button
                        type="button"
                        className="btn-ghost"
                        style={{ whiteSpace: "nowrap", flex: "0 0 auto" }}
                        onClick={() => {
                            onChange("");
                            setNaming(false);
                        }}
                    >
                        Pick one
                    </button>
                )}
            </div>
        );
    }

    return (
        <Select
            value={value || undefined}
            onValueChange={(next) => {
                if (next === ADD_NEW) {
                    onChange("");
                    setNaming(true);
                    return;
                }
                onChange(next);
            }}
        >
            <SelectTrigger id={id}>
                <SelectValue placeholder="Choose a category" />
            </SelectTrigger>
            <SelectContent>
                {categories.map((category) => (
                    <SelectItem key={category} value={category}>
                        {category}
                    </SelectItem>
                ))}
                <SelectItem value={ADD_NEW}>
                    <span
                        className="flex items-center"
                        style={{ gap: "var(--space-2)", color: "var(--accent)" }}
                    >
                        <Plus style={{ width: "14px", height: "14px" }} />
                        New category
                    </span>
                </SelectItem>
            </SelectContent>
        </Select>
    );
}

export default CategoryField;
