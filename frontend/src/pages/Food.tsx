import { useMemo, useState } from "react";
import { addDays, format, parseISO } from "date-fns";
import {
    AlertTriangle,
    ChevronLeft,
    ChevronRight,
    Plus,
    Trash2,
    Utensils,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import BodySectionTabs from "@/components/BodySectionTabs";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    useDeleteFoodLog,
    useFoodDay,
    useFoodSearch,
    useLogFood,
} from "@/hooks/useFood";
import { MEALS } from "@/types/food";
import type { Food, FoodLogEntry, Meal } from "@/types/food";

// Macro hues. Deliberately not the metric hues used on the composition tab:
// there, colour distinguishes *instrument*, which is semantic. Here it
// distinguishes macro, and the three need to be tellable apart at 11px in a
// row of small numbers.
const MACRO_COLORS: Record<string, string> = {
    Protein: "var(--chart-2)",
    Carbs: "var(--chart-5)",
    Fat: "var(--chart-3)",
};

const todayISO = () => format(new Date(), "yyyy-MM-dd");

const round = (value: number | null | undefined) =>
    value == null ? null : Math.round(value);

/**
 * Intake against the measured target.
 *
 * The bar overfills past 100% rather than clamping. A calorie target is asked
 * "how far over am I", and a bar pinned at full answers "at least zero", which
 * is not an answer.
 */
const IntakeSummary = ({
    kcal,
    target,
    missing,
}: {
    kcal: number | null;
    target: number | null;
    missing: number;
}) => {
    const eaten = round(kcal) ?? 0;
    const pct = target ? Math.min((eaten / target) * 100, 100) : 0;
    const over = target != null && eaten > target;

    return (
        <Card className="animate-in section">
            <CardContent style={{ paddingTop: "var(--space-5)" }}>
                <div
                    className="flex items-end justify-between"
                    style={{ marginBottom: "var(--space-3)" }}
                >
                    <div>
                        <div className="stat-card__header">Eaten</div>
                        <div
                            className="stat-card__value"
                            style={{ color: over ? "var(--warning)" : undefined }}
                        >
                            {eaten.toLocaleString()}
                            <span
                                style={{
                                    fontSize: "14px",
                                    color: "var(--text-muted)",
                                    marginLeft: "var(--space-2)",
                                }}
                            >
                                kcal
                            </span>
                        </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <div className="stat-card__header">Target</div>
                        <div
                            className="stat-card__value"
                            style={{ fontSize: "20px" }}
                        >
                            {target != null ? target.toLocaleString() : "—"}
                        </div>
                    </div>
                </div>

                <div className="intake-bar">
                    <div
                        className={`intake-bar__fill ${over ? "intake-bar__fill--over" : ""}`}
                        style={{ width: `${target ? pct : 0}%` }}
                    />
                </div>

                {/* Never invented. `kcal_target` is NULL until a DEXA scan has
                    supplied a resting rate, and a default here would put a
                    number on screen that no measurement supports. */}
                {target == null && (
                    <p
                        style={{
                            fontSize: "11px",
                            color: "var(--text-muted)",
                            marginTop: "var(--space-3)",
                        }}
                    >
                        No target yet — it comes from the resting rate a DEXA scan
                        measures. Import one on the Composition tab.
                    </p>
                )}
                {target != null && (
                    <p
                        style={{
                            fontSize: "11px",
                            color: "var(--text-muted)",
                            marginTop: "var(--space-3)",
                        }}
                    >
                        {over
                            ? `${(eaten - target).toLocaleString()} kcal over`
                            : `${(target - eaten).toLocaleString()} kcal left`}
                        {" · target is the last DEXA scan's Katch-McArdle RMR × 1.4"}
                    </p>
                )}

                {/* The totals coalesce unknown macros to zero, so without this
                    a partially catalogued day reports a confident low number. */}
                {missing > 0 && (
                    <p
                        className="flex items-center"
                        style={{
                            fontSize: "11px",
                            color: "var(--warning)",
                            marginTop: "var(--space-2)",
                            gap: "var(--space-2)",
                        }}
                    >
                        <AlertTriangle style={{ width: "13px", height: "13px" }} />
                        {missing} {missing === 1 ? "entry is" : "entries are"} missing
                        macros — totals below are understated
                    </p>
                )}
            </CardContent>
        </Card>
    );
};

const MacroRow = ({
    protein,
    carbs,
    fat,
}: {
    protein: number | null;
    carbs: number | null;
    fat: number | null;
}) => (
    <div
        className="grid grid-cols-3 section"
        style={{ gap: "var(--space-3)" }}
    >
        {(
            [
                ["Protein", protein],
                ["Carbs", carbs],
                ["Fat", fat],
            ] as const
        ).map(([label, value]) => (
            <div key={label} className="stat-card animate-in">
                <div className="stat-card__header">
                    <span style={{ color: MACRO_COLORS[label] }}>{label}</span>
                </div>
                <div className="stat-card__value" style={{ fontSize: "20px" }}>
                    {round(value) ?? 0}
                    <span
                        style={{
                            fontSize: "12px",
                            color: "var(--text-muted)",
                            marginLeft: "4px",
                        }}
                    >
                        g
                    </span>
                </div>
            </div>
        ))}
    </div>
);

/**
 * Log entry form.
 *
 * Two paths into one submit: pick a catalogued food from the typeahead, or
 * type a name that isn't in the catalog yet and give its macros. The second is
 * what makes the first useful later — a food entered once is searchable
 * forever after.
 */
const LogForm = ({ date, onDone }: { date: string; onDone: () => void }) => {
    const [name, setName] = useState("");
    const [picked, setPicked] = useState<Food | null>(null);
    const [servings, setServings] = useState("1");
    const [meal, setMeal] = useState<Meal>("snack");
    const [kcal, setKcal] = useState("");
    const [protein, setProtein] = useState("");
    const [carbs, setCarbs] = useState("");
    const [fat, setFat] = useState("");

    // Meals only: the supplements tab owns vitamins, and offering them here
    // would put magnesium in a search for a mango.
    const { data: matches } = useFoodSearch(picked ? "" : name, "food");
    const log = useLogFood();

    const numeric = (value: string) =>
        value.trim() === "" ? null : Number(value);

    const submit = (event: React.FormEvent) => {
        event.preventDefault();
        const amount = Number(servings);
        if (!amount || amount <= 0) return;

        // Time-of-day matters — `date` is derived from `consumed_at` by a
        // generated column, so a logged entry lands on the day the clock says.
        // Backdating keeps today's clock time, which is close enough for a
        // meal and avoids inventing a midnight timestamp.
        //
        // Local time, never `toISOString()`. That column is
        // `substr(consumed_at, 1, 10)` — the date is whatever the first ten
        // characters spell — so a UTC string files the entry under the UTC
        // date. West of Greenwich that is tomorrow for every evening meal:
        // dinner logged at 18:02 on the 10th became `2026-08-11` and vanished
        // from the day it was logged on. The day being viewed is already a
        // local `yyyy-MM-dd`, so it serves for today and for a backdated entry
        // alike.
        const consumed_at = `${date}T${format(new Date(), "HH:mm:ss")}`;

        const entry = picked
            ? { food_id: picked.doc_id, servings: amount, meal, consumed_at }
            : {
                  food: {
                      name: name.trim(),
                      kcal_per_serving: numeric(kcal),
                      protein_g: numeric(protein),
                      carb_g: numeric(carbs),
                      fat_g: numeric(fat),
                  },
                  servings: amount,
                  meal,
                  consumed_at,
              };

        if (!picked && !name.trim()) return;
        log.mutate(entry, { onSuccess: onDone });
    };

    return (
        <Card className="animate-in section">
            <CardContent style={{ paddingTop: "var(--space-5)" }}>
                <form onSubmit={submit}>
                    <div className="form-field section">
                        <label className="form-label" htmlFor="food-name">
                            Food
                        </label>
                        <Input
                            id="food-name"
                            value={picked ? `${picked.name}${picked.brand ? ` · ${picked.brand}` : ""}` : name}
                            onChange={(e) => {
                                setPicked(null);
                                setName(e.target.value);
                            }}
                            placeholder="Search or type a new food"
                            autoComplete="off"
                            // The form only exists because "Log food" was
                            // pressed, and naming the food is the only way to
                            // start. Opening it focused saves a click and lets
                            // the whole entry be typed.
                            autoFocus
                        />

                        {!picked && matches && matches.length > 0 && (
                            <div className="food-suggestions">
                                {matches.slice(0, 6).map((food) => (
                                    <button
                                        key={food.doc_id}
                                        type="button"
                                        className="food-suggestion"
                                        onClick={() => setPicked(food)}
                                    >
                                        <span>
                                            {food.name}
                                            {food.brand && (
                                                <span style={{ color: "var(--text-muted)" }}>
                                                    {" "}· {food.brand}
                                                </span>
                                            )}
                                        </span>
                                        <span
                                            className="mono"
                                            style={{ color: "var(--text-muted)" }}
                                        >
                                            {food.kcal_per_serving ?? "—"} kcal
                                        </span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Only for a food the catalog has never seen. Editing an
                        existing food's macros is a separate, deliberate act —
                        it rewrites every past entry that used it. */}
                    {!picked && name.trim() !== "" && (
                        <div
                            className="grid grid-cols-2 lg:grid-cols-4 section"
                            style={{ gap: "var(--space-3)" }}
                        >
                            {(
                                [
                                    ["kcal / serving", kcal, setKcal],
                                    ["protein g", protein, setProtein],
                                    ["carbs g", carbs, setCarbs],
                                    ["fat g", fat, setFat],
                                ] as const
                            ).map(([label, value, set]) => (
                                <div key={label} className="form-field">
                                    <label className="form-label">{label}</label>
                                    <Input
                                        type="number"
                                        inputMode="decimal"
                                        className="input--mono"
                                        value={value}
                                        onChange={(e) => set(e.target.value)}
                                        placeholder="—"
                                    />
                                </div>
                            ))}
                        </div>
                    )}

                    <div
                        className="grid grid-cols-2 section"
                        style={{ gap: "var(--space-3)" }}
                    >
                        <div className="form-field">
                            <label className="form-label" htmlFor="servings">
                                Servings
                            </label>
                            <Input
                                id="servings"
                                type="number"
                                inputMode="decimal"
                                step="0.25"
                                className="input--mono"
                                value={servings}
                                onChange={(e) => setServings(e.target.value)}
                            />
                        </div>
                        <div className="form-field">
                            <label className="form-label">Meal</label>
                            <Select
                                value={meal}
                                onValueChange={(v) => setMeal(v as Meal)}
                            >
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {MEALS.map((m) => (
                                        <SelectItem key={m} value={m}>
                                            {m[0].toUpperCase() + m.slice(1)}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="flex" style={{ gap: "var(--space-2)" }}>
                        <Button
                            type="submit"
                            disabled={log.isPending || (!picked && !name.trim())}
                        >
                            {log.isPending ? "Logging..." : "Log it"}
                        </Button>
                        <Button type="button" variant="ghost" onClick={onDone}>
                            Cancel
                        </Button>
                    </div>

                    {log.isError && (
                        <p
                            style={{
                                fontSize: "12px",
                                color: "var(--error)",
                                marginTop: "var(--space-3)",
                            }}
                        >
                            Could not log that. Check the numbers and try again.
                        </p>
                    )}
                </form>
            </CardContent>
        </Card>
    );
};

const EntryRow = ({ entry }: { entry: FoodLogEntry }) => {
    const remove = useDeleteFoodLog();

    return (
        <div className="food-row">
            <div style={{ flex: 1, minWidth: 0 }}>
                <div className="food-row__name">
                    {entry.name}
                    {entry.brand && (
                        <span
                            style={{
                                color: "var(--text-muted)",
                                fontWeight: 400,
                            }}
                        >
                            {" "}· {entry.brand}
                        </span>
                    )}
                </div>
                <div className="food-row__meta">
                    {entry.servings}× · {round(entry.protein_g) ?? "—"}p{" "}
                    {round(entry.carb_g) ?? "—"}c {round(entry.fat_g) ?? "—"}f
                </div>
            </div>
            <div className="food-row__kcal">
                {entry.kcal != null ? `${round(entry.kcal)} kcal` : "— kcal"}
            </div>
            <button
                type="button"
                className="action-btn action-btn--danger"
                aria-label={`Delete ${entry.name}`}
                disabled={remove.isPending}
                onClick={() => remove.mutate(entry.doc_id)}
            >
                <Trash2 style={{ width: "15px", height: "15px" }} />
            </button>
        </div>
    );
};

const FoodPage = () => {
    const [date, setDate] = useState(todayISO());
    const [logging, setLogging] = useState(false);

    const { data: day, isLoading } = useFoodDay(date);

    // Meals only. `/api/food/day` returns no supplements at all — they are
    // logged with no meal, they moved nothing on this page, and they live on
    // the supplements tab with their own log. `unsorted` is for food that
    // genuinely has no meal on it, which is now the only thing that lands
    // there.
    const byMeal = useMemo(() => {
        const groups = new Map<string, FoodLogEntry[]>();
        for (const meal of [...MEALS, "unsorted"]) groups.set(meal, []);
        for (const entry of day?.entries ?? []) {
            // The server already filters these out. The guard is for a
            // response that predates it — the service worker caches /api
            // network-first, so a stale day can still carry supplements, and
            // they would land in "unsorted" looking like unfiled food.
            if (entry.kind === "supplement") continue;
            groups.get(entry.meal ?? "unsorted")!.push(entry);
        }
        return [...groups].filter(([, entries]) => entries.length > 0);
    }, [day]);

    const totals = day?.totals;
    const shift = (days: number) =>
        setDate(format(addDays(parseISO(date), days), "yyyy-MM-dd"));

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content page__content--narrow">
                    <div className="page__header animate-in">
                        <h1 className="page__title">BODY</h1>
                        <p className="page__subtitle">
                            What went in, against what the last scan says you burn
                        </p>
                    </div>

                    <BodySectionTabs />

                    {/* Day picker. Arrows rather than a calendar because food
                        is logged for today or yesterday and almost never for a
                        date three weeks ago. */}
                    <div
                        className="flex items-center justify-between section animate-in"
                        style={{ gap: "var(--space-3)" }}
                    >
                        <button
                            type="button"
                            className="icon-btn"
                            aria-label="Previous day"
                            onClick={() => shift(-1)}
                        >
                            <ChevronLeft style={{ width: "18px", height: "18px" }} />
                        </button>
                        <div style={{ textAlign: "center" }}>
                            <div
                                style={{
                                    fontSize: "15px",
                                    fontWeight: 600,
                                    color: "var(--text-primary)",
                                }}
                            >
                                {format(parseISO(date), "EEEE, MMM d")}
                            </div>
                            {date !== todayISO() && (
                                <button
                                    type="button"
                                    className="btn-link"
                                    onClick={() => setDate(todayISO())}
                                >
                                    Back to today
                                </button>
                            )}
                        </div>
                        <button
                            type="button"
                            className="icon-btn"
                            aria-label="Next day"
                            disabled={date >= todayISO()}
                            onClick={() => shift(1)}
                        >
                            <ChevronRight style={{ width: "18px", height: "18px" }} />
                        </button>
                    </div>

                    {isLoading ? (
                        <div
                            className="text-center"
                            style={{ padding: "var(--space-16) 0" }}
                        >
                            <div className="loading-spinner inline-block" />
                        </div>
                    ) : (
                        <>
                            <IntakeSummary
                                kcal={totals?.kcal ?? null}
                                target={totals?.kcal_target ?? null}
                                missing={totals?.foods_missing_macros ?? 0}
                            />

                            <MacroRow
                                protein={totals?.protein_g ?? null}
                                carbs={totals?.carb_g ?? null}
                                fat={totals?.fat_g ?? null}
                            />

                            {logging ? (
                                <LogForm date={date} onDone={() => setLogging(false)} />
                            ) : (
                                <Button
                                    className="section"
                                    onClick={() => setLogging(true)}
                                >
                                    <Plus
                                        style={{
                                            width: "16px",
                                            height: "16px",
                                            marginRight: "var(--space-2)",
                                        }}
                                    />
                                    Log food
                                </Button>
                            )}

                            {byMeal.length === 0 ? (
                                <div className="empty-state animate-in">
                                    <div className="empty-state__icon">
                                        <Utensils
                                            style={{ width: "24px", height: "24px" }}
                                        />
                                    </div>
                                    <div className="empty-state__title">
                                        Nothing logged
                                    </div>
                                    <p className="empty-state__text">
                                        An unlogged day is not a fasted one — it just
                                        reads as blank everywhere else in the app.
                                    </p>
                                </div>
                            ) : (
                                byMeal.map(([meal, entries]) => (
                                    <div key={meal} className="meal-group animate-in">
                                        <div className="meal-group__label">
                                            {meal}
                                            <span
                                                style={{
                                                    color: "var(--text-muted)",
                                                    marginLeft: "var(--space-2)",
                                                    fontWeight: 500,
                                                }}
                                            >
                                                {round(
                                                    entries.reduce(
                                                        (sum, e) => sum + (e.kcal ?? 0),
                                                        0,
                                                    ),
                                                )}{" "}
                                                kcal
                                            </span>
                                        </div>
                                        {entries.map((entry) => (
                                            <EntryRow key={entry.doc_id} entry={entry} />
                                        ))}
                                    </div>
                                ))
                            )}
                        </>
                    )}
                </div>
            </div>
        </>
    );
};

export default FoodPage;
