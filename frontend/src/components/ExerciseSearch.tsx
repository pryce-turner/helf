import { useId, useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import type { Exercise } from "@/types/exercise";
import { matchExercises } from "@/lib/exerciseSearch";

/**
 * Type to find a movement; matches list live, each with its category.
 *
 * Replaces the category-then-exercise pair of dropdowns: with two hundred
 * movements, scrolling a category list to find one is slower than typing three
 * letters of it, and a movement filed under an unexpected category could not
 * be found at all.
 *
 * Ranking lives in `lib/exerciseSearch.ts`: every typed term must match, so
 * "dumb row" finds Dumbbell Row and "row" alone lists every row.
 */
interface ExerciseSearchProps {
    exercises: Exercise[];
    /** The chosen movement's name, or "" for none. */
    value: string;
    onSelect: (exercise: Exercise) => void;
    /** Typing over a chosen movement unchooses it. */
    onClear: () => void;
    id?: string;
}

const ExerciseSearch = ({ exercises, value, onSelect, onClear, id }: ExerciseSearchProps) => {
    const generated = useId();
    const inputId = id ?? `exercise-search-${generated}`;
    const listId = `${inputId}-list`;
    // What is typed. A chosen movement shows its name; typing over it starts
    // a new search.
    const [query, setQuery] = useState(value);
    const [open, setOpen] = useState(false);
    const [active, setActive] = useState(0);

    // A choice made elsewhere (a Recents chip) shows here too. Adjusted during
    // render — React's "adjust state when a prop changes" pattern.
    const [seenValue, setSeenValue] = useState(value);
    // Only a *choice* syncs: when typing over a chosen movement clears it,
    // the text being typed must stay.
    if (value !== seenValue) {
        setSeenValue(value);
        if (value) {
            setQuery(value);
            setOpen(false);
        }
    }

    const results = useMemo(() => matchExercises(exercises, query), [exercises, query]);
    const showList = open && query.trim() !== "" && query !== value;

    const choose = (exercise: Exercise) => {
        setQuery(exercise.name);
        setSeenValue(exercise.name);
        setOpen(false);
        onSelect(exercise);
    };

    return (
        <div className="exercise-search">
            <div className="exercise-search__field">
                <Search className="exercise-search__icon" aria-hidden="true" />
                <input
                    id={inputId}
                    className="input exercise-search__input"
                    type="text"
                    role="combobox"
                    aria-label="Search exercises"
                    aria-expanded={showList}
                    aria-controls={listId}
                    aria-autocomplete="list"
                    aria-activedescendant={
                        showList && results[active] ? `${listId}-${results[active].doc_id}` : undefined
                    }
                    autoComplete="off"
                    placeholder="Search exercises"
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setActive(0);
                        setOpen(true);
                        if (value) onClear();
                    }}
                    onFocus={() => setOpen(true)}
                    // Delayed so a tap on a result lands before the list goes.
                    onBlur={() => setTimeout(() => setOpen(false), 150)}
                    onKeyDown={(e) => {
                        if (!showList) return;
                        if (e.key === "ArrowDown") {
                            e.preventDefault();
                            setActive((i) => Math.min(i + 1, results.length - 1));
                        } else if (e.key === "ArrowUp") {
                            e.preventDefault();
                            setActive((i) => Math.max(i - 1, 0));
                        } else if (e.key === "Enter" && results[active]) {
                            e.preventDefault();
                            choose(results[active]);
                        } else if (e.key === "Escape") {
                            setOpen(false);
                        }
                    }}
                />
                {query && (
                    <button
                        type="button"
                        className="exercise-search__clear"
                        aria-label="Clear search"
                        onClick={() => {
                            setQuery("");
                            setOpen(false);
                            if (value) onClear();
                        }}
                    >
                        <X style={{ width: "16px", height: "16px" }} />
                    </button>
                )}
            </div>
            {showList && (
                <ul id={listId} role="listbox" className="exercise-search__list">
                    {results.length === 0 ? (
                        <li className="exercise-search__empty">No exercise matches "{query.trim()}"</li>
                    ) : (
                        results.map((exercise, index) => (
                            <li
                                key={exercise.doc_id}
                                id={`${listId}-${exercise.doc_id}`}
                                role="option"
                                aria-selected={index === active}
                                className={`exercise-search__option${index === active ? " exercise-search__option--active" : ""}`}
                                // mousedown, not click: it fires before the
                                // input's blur would close the list.
                                onMouseDown={(e) => {
                                    e.preventDefault();
                                    choose(exercise);
                                }}
                                onMouseEnter={() => setActive(index)}
                            >
                                <span className="exercise-search__name">{exercise.name}</span>
                                <span className="exercise-search__category">{exercise.category}</span>
                            </li>
                        ))
                    )}
                </ul>
            )}
        </div>
    );
};

export default ExerciseSearch;
