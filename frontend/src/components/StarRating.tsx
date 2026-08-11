import { Star } from "lucide-react";

/**
 * How good a movement is, 1 to 5.
 *
 * `null` is unrated, and that is a different fact from a bad rating — an
 * exercise nobody has judged yet should not read as one star. So the empty
 * state is five outlines, and clicking the star a movement already sits on
 * clears it back to unrated rather than leaving no way out of a rating given
 * by accident.
 */
const STARS = [1, 2, 3, 4, 5];

export function StarRating({
    value,
    onChange,
    name,
    disabled = false,
}: {
    value: number | null;
    onChange: (next: number | null) => void;
    /** Names the exercise in the accessible label, since a page has many. */
    name: string;
    disabled?: boolean;
}) {
    return (
        <div
            className="star-rating"
            role="group"
            aria-label={`Rating for ${name}`}
        >
            {STARS.map((star) => {
                const filled = value != null && star <= value;
                return (
                    <button
                        key={star}
                        type="button"
                        className="star-rating__star"
                        disabled={disabled}
                        aria-pressed={filled}
                        aria-label={
                            value === star
                                ? `Clear the rating for ${name}`
                                : `Rate ${name} ${star} of 5`
                        }
                        title={
                            value === star
                                ? "Click again to clear"
                                : `${star} of 5`
                        }
                        onClick={() => onChange(value === star ? null : star)}
                    >
                        <Star
                            style={{ width: "16px", height: "16px" }}
                            fill={filled ? "currentColor" : "none"}
                        />
                    </button>
                );
            })}
        </div>
    );
}

export default StarRating;
