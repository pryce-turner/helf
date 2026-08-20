import { useState } from "react";
import { format, parseISO } from "date-fns";
import { Check, Pencil, Pill, Plus, Trash2, X } from "lucide-react";
import SupplementEditor from "@/components/SupplementEditor";
import Navigation from "@/components/Navigation";
import BodySectionTabs from "@/components/BodySectionTabs";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    useDeleteFoodLog,
    useFoodSearch,
    useSupplementCatalog,
    useSupplementLog,
} from "@/hooks/useFood";
import {
    useCreateStack,
    useDeleteStack,
    useLogStack,
    useStacks,
    useUpdateStack,
} from "@/hooks/useStacks";
import type { Food } from "@/types/food";
import type { Stack, StackItem, StackItemCreate } from "@/types/stack";

/** A row being edited: either an existing catalog entry or a new one. */
interface DraftItem {
    key: string;
    food_id?: number;
    name: string;
    serving_desc: string;
    servings: string;
}

const draftFrom = (item: StackItem): DraftItem => ({
    key: `existing-${item.doc_id}`,
    food_id: item.food_id,
    name: item.name,
    serving_desc: item.serving_desc ?? "",
    servings: String(item.servings),
});

const blankDraft = (): DraftItem => ({
    key: `new-${Math.random().toString(36).slice(2)}`,
    name: "",
    serving_desc: "",
    servings: "1",
});

const toPayload = (drafts: DraftItem[]): StackItemCreate[] =>
    drafts
        .filter((d) => d.name.trim() !== "")
        .map((d) => ({
            // An existing food is referenced by id so its catalog entry is
            // reused; a new one is created by name. `kind` is always
            // "supplement" here — the food page owns meals.
            ...(d.food_id != null
                ? { food_id: d.food_id }
                : {
                      food: {
                          name: d.name.trim(),
                          kind: "supplement" as const,
                          serving_desc: d.serving_desc.trim() || null,
                      },
                  }),
            servings: Number(d.servings) || 1,
        }));

/**
 * Typeahead over the supplement catalog only.
 *
 * Picking an existing entry matters more than it looks: it's what keeps one
 * bottle of omega from becoming "Omega 3", "Omega-3" and "omega3" across three
 * stacks, each with its own adherence history.
 */
const ItemRow = ({
    draft,
    onChange,
    onRemove,
}: {
    draft: DraftItem;
    onChange: (next: DraftItem) => void;
    onRemove: () => void;
}) => {
    const [query, setQuery] = useState("");
    const { data: matches } = useFoodSearch(query, "supplement");

    return (
        <div className="stack-edit-row">
            <div style={{ flex: "1 1 200px", minWidth: 0 }}>
                <Input
                    value={draft.name}
                    placeholder="Supplement name"
                    onChange={(e) => {
                        setQuery(e.target.value);
                        onChange({ ...draft, name: e.target.value, food_id: undefined });
                    }}
                    autoComplete="off"
                />
                {draft.food_id == null && matches && matches.length > 0 && (
                    <div className="food-suggestions" data-testid="food-suggestions">
                        {matches.slice(0, 5).map((food) => (
                            <button
                                key={food.doc_id}
                                type="button"
                                className="food-suggestion"
                                onClick={() => {
                                    setQuery("");
                                    onChange({
                                        ...draft,
                                        food_id: food.doc_id,
                                        name: food.name,
                                        serving_desc: food.serving_desc ?? "",
                                    });
                                }}
                            >
                                <span>{food.name}</span>
                                <span style={{ color: "var(--text-muted)" }}>
                                    {food.serving_desc ?? "—"}
                                </span>
                            </button>
                        ))}
                    </div>
                )}
            </div>

            <Input
                value={draft.serving_desc}
                placeholder="1 softgel, 1000mg"
                disabled={draft.food_id != null}
                onChange={(e) => onChange({ ...draft, serving_desc: e.target.value })}
                style={{ flex: "1 1 160px" }}
            />

            <Input
                type="number"
                inputMode="decimal"
                step="0.5"
                min="0.5"
                className="input--mono input--center"
                value={draft.servings}
                onChange={(e) => onChange({ ...draft, servings: e.target.value })}
                style={{ flex: "0 0 72px" }}
            />

            <button
                type="button"
                className="action-btn action-btn--danger"
                aria-label={`Remove ${draft.name || "item"}`}
                onClick={onRemove}
            >
                <X style={{ width: "15px", height: "15px" }} />
            </button>
        </div>
    );
};

const StackEditor = ({
    stack,
    onDone,
}: {
    stack: Stack | null;
    onDone: () => void;
}) => {
    const [name, setName] = useState(stack?.name ?? "");
    const [drafts, setDrafts] = useState<DraftItem[]>(
        stack ? stack.items.map(draftFrom) : [blankDraft()],
    );
    const create = useCreateStack();
    const update = useUpdateStack();
    const pending = create.isPending || update.isPending;
    const failed = (create.error ?? update.error) as
        | { response?: { data?: { detail?: string } } }
        | null;

    const submit = (event: React.FormEvent) => {
        event.preventDefault();
        if (!name.trim()) return;
        const items = toPayload(drafts);

        if (stack) {
            // `items` replaces the membership wholesale — that is the API's
            // contract, and it is what makes removing a row here actually
            // remove it.
            update.mutate(
                { id: stack.doc_id, changes: { name: name.trim(), items } },
                { onSuccess: onDone },
            );
        } else {
            create.mutate({ name: name.trim(), items }, { onSuccess: onDone });
        }
    };

    return (
        <Card className="animate-in section">
            <CardContent style={{ paddingTop: "var(--space-5)" }}>
                <form onSubmit={submit}>
                    <div className="form-field section">
                        <label className="form-label" htmlFor="stack-name">
                            Group name
                        </label>
                        <Input
                            id="stack-name"
                            value={name}
                            placeholder="Morning"
                            onChange={(e) => setName(e.target.value)}
                            autoComplete="off"
                            autoFocus
                        />
                    </div>

                    <div className="stack-edit-header">
                        <span style={{ flex: "1 1 200px" }}>Supplement</span>
                        <span style={{ flex: "1 1 160px" }}>Serving</span>
                        <span style={{ flex: "0 0 72px", textAlign: "center" }}>×</span>
                        <span style={{ flex: "0 0 34px" }} />
                    </div>

                    {drafts.map((draft, index) => (
                        <ItemRow
                            key={draft.key}
                            draft={draft}
                            onChange={(next) =>
                                setDrafts(drafts.map((d, i) => (i === index ? next : d)))
                            }
                            onRemove={() =>
                                setDrafts(drafts.filter((_, i) => i !== index))
                            }
                        />
                    ))}

                    <Button
                        type="button"
                        variant="ghost"
                        className="section"
                        onClick={() => setDrafts([...drafts, blankDraft()])}
                    >
                        <Plus style={{ width: "15px", height: "15px", marginRight: "var(--space-2)" }} />
                        Add supplement
                    </Button>

                    <div className="flex" style={{ gap: "var(--space-2)" }}>
                        <Button type="submit" disabled={!name.trim() || pending}>
                            {pending ? "Saving..." : stack ? "Save changes" : "Create group"}
                        </Button>
                        <Button type="button" variant="ghost" onClick={onDone}>
                            Cancel
                        </Button>
                    </div>

                    {failed && (
                        <p
                            style={{
                                fontSize: "12px",
                                color: "var(--error)",
                                marginTop: "var(--space-3)",
                            }}
                        >
                            {failed.response?.data?.detail ?? "Could not save that group."}
                        </p>
                    )}
                </form>
            </CardContent>
        </Card>
    );
};

const StackCard = ({ stack }: { stack: Stack }) => {
    const [editing, setEditing] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const log = useLogStack();
    const remove = useDeleteStack();

    if (editing) {
        return <StackEditor stack={stack} onDone={() => setEditing(false)} />;
    }

    return (
        <Card className="animate-in section">
            <CardContent style={{ paddingTop: "var(--space-5)" }}>
                <div
                    className="flex items-start justify-between"
                    style={{ gap: "var(--space-3)", marginBottom: "var(--space-3)" }}
                >
                    <div style={{ minWidth: 0 }}>
                        <div className="stack-card__name">
                            {stack.name}
                            {stack.taken_today && (
                                <span className="stack-badge">
                                    <Check style={{ width: "12px", height: "12px" }} />
                                    Taken today
                                </span>
                            )}
                        </div>
                        {/* Derived from the log, so it is true whether the
                            button was used or the items entered by hand. */}
                        {!stack.taken_today && stack.last_taken && (
                            <div
                                style={{
                                    fontSize: "11px",
                                    color: "var(--text-muted)",
                                    marginTop: "var(--space-1)",
                                }}
                            >
                                Last taken{" "}
                                {format(parseISO(stack.last_taken), "EEE d MMM")}
                            </div>
                        )}
                    </div>

                    <div className="flex" style={{ gap: "var(--space-1)" }}>
                        <button
                            type="button"
                            className="action-btn"
                            aria-label={`Edit ${stack.name}`}
                            onClick={() => setEditing(true)}
                        >
                            <Pencil style={{ width: "15px", height: "15px" }} />
                        </button>
                        <button
                            type="button"
                            className="action-btn action-btn--danger"
                            aria-label={`Delete ${stack.name}`}
                            onClick={() => setConfirmDelete(true)}
                        >
                            <Trash2 style={{ width: "15px", height: "15px" }} />
                        </button>
                    </div>
                </div>

                <div className="section">
                    {stack.items.map((item) => (
                        <div key={item.doc_id} className="stack-item">
                            <span className="stack-item__name">{item.name}</span>
                            <span className="stack-item__dose">
                                {item.servings}
                                {item.serving_desc ? ` × ${item.serving_desc}` : "×"}
                            </span>
                        </div>
                    ))}
                    {stack.items.length === 0 && (
                        <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                            Nothing in this group yet.
                        </p>
                    )}
                </div>

                {confirmDelete ? (
                    <div
                        className="flex items-center"
                        style={{ gap: "var(--space-2)", flexWrap: "wrap" }}
                    >
                        <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                            Delete “{stack.name}”? Past entries are kept.
                        </span>
                        <Button
                            variant="destructive"
                            onClick={() => remove.mutate(stack.doc_id)}
                            disabled={remove.isPending}
                        >
                            Delete
                        </Button>
                        <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                            Cancel
                        </Button>
                    </div>
                ) : (
                    <Button
                        onClick={() => log.mutate(stack.doc_id)}
                        disabled={log.isPending || stack.items.length === 0}
                    >
                        {log.isPending
                            ? "Logging..."
                            : stack.taken_today
                              ? "Log again"
                              : `Log all ${stack.items.length}`}
                    </Button>
                )}

                {log.isError && (
                    <p
                        style={{
                            fontSize: "12px",
                            color: "var(--error)",
                            marginTop: "var(--space-3)",
                        }}
                    >
                        Could not log that group.
                    </p>
                )}
            </CardContent>
        </Card>
    );
};

/**
 * Every supplement, not just the ones in a group.
 *
 * The groups above are how you *log*; this is how you fix what a supplement
 * is. They are separate because `serving_desc` and macros belong to the
 * catalog entry while `servings` belongs to a membership — and because a
 * supplement you have stopped taking still needs to be reachable.
 */
const Catalog = () => {
    const [editing, setEditing] = useState<Food | null>(null);
    const { data: supplements } = useSupplementCatalog();

    if (!supplements || supplements.length === 0) return null;

    return (
        <>
            <div className="section-heading">All supplements</div>
            {editing && (
                <SupplementEditor food={editing} onDone={() => setEditing(null)} />
            )}
            <Card className="animate-in">
                <CardContent style={{ padding: "var(--space-2)" }}>
                    {supplements.map((food) => (
                        <div key={food.doc_id} className="catalog-row">
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div className="catalog-row__name">
                                    {food.name}
                                    {food.brand && (
                                        <span style={{ color: "var(--text-muted)" }}>
                                            {" "}· {food.brand}
                                        </span>
                                    )}
                                </div>
                                <div className="catalog-row__meta">
                                    {food.serving_desc ?? "no serving described"}
                                    {food.kcal_per_serving != null &&
                                        ` · ${food.kcal_per_serving} kcal`}
                                </div>
                            </div>
                            <button
                                type="button"
                                className="action-btn"
                                aria-label={`Edit ${food.name}`}
                                onClick={() => setEditing(food)}
                            >
                                <Pencil style={{ width: "15px", height: "15px" }} />
                            </button>
                        </div>
                    ))}
                </CardContent>
            </Card>
        </>
    );
};

/**
 * What was actually swallowed, newest first — the counterpart of the body
 * page's measurement log.
 *
 * Not scoped to a day. `taken_today` answers "did I take it this morning",
 * which is the question the groups above are for; this answers "what did I
 * take, and was that right", and the mistake it exists to catch is a dose
 * filed against the wrong date — invisible to any per-day view.
 *
 * Reads across every supplement, not just the ones in a group: a product
 * logged by hand and a product logged by tapping a group produce the same row,
 * which is the reason `food_log` carries no `stack_id`.
 */
const SupplementLog = () => {
    const { data: entries, isLoading } = useSupplementLog();
    const remove = useDeleteFoodLog();
    const [confirming, setConfirming] = useState<number | null>(null);

    if (isLoading || !entries?.length) return null;

    const cell: React.CSSProperties = {
        padding: "var(--space-2) var(--space-3)",
        borderBottom: "1px solid var(--border)",
        whiteSpace: "nowrap",
    };
    const head: React.CSSProperties = {
        ...cell,
        fontSize: "11px",
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        textAlign: "left",
    };

    return (
        <>
            <div className="section-heading">Recent doses</div>
            <Card className="animate-in">
                <CardContent style={{ padding: "var(--space-2)" }}>
                    {/* Wide content scrolls inside its own box; the page must not. */}
                    <div style={{ overflowX: "auto" }}>
                        <table
                            style={{
                                width: "100%",
                                borderCollapse: "collapse",
                                fontSize: "13px",
                            }}
                        >
                            <thead>
                                <tr>
                                    <th style={head}>Taken</th>
                                    <th style={head}>Supplement</th>
                                    <th style={{ ...head, textAlign: "right" }}>Dose</th>
                                    <th style={head} aria-label="Actions" />
                                </tr>
                            </thead>
                            <tbody>
                                {entries.map((entry) => (
                                    <tr key={entry.doc_id}>
                                        <td
                                            style={{
                                                ...cell,
                                                fontFamily: "var(--font-mono, monospace)",
                                                color: "var(--text-secondary)",
                                            }}
                                        >
                                            {format(
                                                parseISO(entry.consumed_at),
                                                "yyyy-MM-dd HH:mm",
                                            )}
                                        </td>
                                        <td style={{ ...cell, whiteSpace: "normal" }}>
                                            {entry.name}
                                            {entry.brand && (
                                                <span style={{ color: "var(--text-muted)" }}>
                                                    {" "}· {entry.brand}
                                                </span>
                                            )}
                                            {/* A supplement with real calories still
                                                counts toward the day's intake even
                                                though it is not listed under a meal.
                                                Showing it here is the only place that
                                                is visible. */}
                                            {entry.kcal != null && entry.kcal > 0 && (
                                                <span style={{ color: "var(--text-muted)" }}>
                                                    {" "}· {Math.round(entry.kcal)} kcal
                                                </span>
                                            )}
                                        </td>
                                        <td
                                            style={{
                                                ...cell,
                                                textAlign: "right",
                                                fontFamily: "var(--font-mono, monospace)",
                                            }}
                                        >
                                            ×{entry.servings}
                                        </td>
                                        <td style={{ ...cell, textAlign: "right" }}>
                                            {/* Two taps, not a browser confirm(), for the
                                                same reason as the measurement log. */}
                                            {confirming === entry.doc_id ? (
                                                <span
                                                    style={{
                                                        display: "inline-flex",
                                                        gap: "var(--space-2)",
                                                    }}
                                                >
                                                    <Button
                                                        style={{
                                                            background: "var(--error)",
                                                            height: "28px",
                                                            padding: "0 10px",
                                                        }}
                                                        onClick={() => {
                                                            remove.mutate(entry.doc_id);
                                                            setConfirming(null);
                                                        }}
                                                    >
                                                        Delete
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        style={{ height: "28px", padding: "0 10px" }}
                                                        onClick={() => setConfirming(null)}
                                                    >
                                                        Cancel
                                                    </Button>
                                                </span>
                                            ) : (
                                                <button
                                                    type="button"
                                                    className="action-btn action-btn--danger"
                                                    aria-label={`Delete ${entry.name} logged ${entry.consumed_at}`}
                                                    onClick={() => setConfirming(entry.doc_id)}
                                                >
                                                    <Trash2
                                                        style={{ width: "15px", height: "15px" }}
                                                    />
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>
        </>
    );
};

const Supplements = () => {
    const [creating, setCreating] = useState(false);
    const { data: stacks, isLoading } = useStacks();

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content page__content--narrow">
                    <div className="page__header animate-in">
                        <h1 className="page__title">BODY</h1>
                        <p className="page__subtitle">
                            Groups you take together, logged in one tap
                        </p>
                    </div>

                    <BodySectionTabs />

                    {isLoading ? (
                        <div
                            className="text-center"
                            style={{ padding: "var(--space-16) 0" }}
                        >
                            <div className="loading-spinner inline-block" />
                        </div>
                    ) : (
                        <>
                            {creating ? (
                                <StackEditor
                                    stack={null}
                                    onDone={() => setCreating(false)}
                                />
                            ) : (
                                <Button
                                    className="section"
                                    onClick={() => setCreating(true)}
                                >
                                    <Plus
                                        style={{
                                            width: "16px",
                                            height: "16px",
                                            marginRight: "var(--space-2)",
                                        }}
                                    />
                                    New group
                                </Button>
                            )}

                            {(stacks ?? []).map((stack) => (
                                <StackCard key={stack.doc_id} stack={stack} />
                            ))}

                            <Catalog />

                            <SupplementLog />

                            {stacks && stacks.length === 0 && !creating && (
                                <div className="empty-state animate-in">
                                    <div className="empty-state__icon">
                                        <Pill style={{ width: "24px", height: "24px" }} />
                                    </div>
                                    <div className="empty-state__title">No groups yet</div>
                                    <p className="empty-state__text">
                                        A group is the things you take together — a
                                        morning stack, an evening one. Logging one writes
                                        an entry per item, and they show up in the log at
                                        the bottom of this page.
                                    </p>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </>
    );
};

export default Supplements;
