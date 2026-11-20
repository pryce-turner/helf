import { formatSeconds } from "@/lib/setTiles";

/**
 * The rest after a set tile, rendered as a divider rather than a row
 * (plan 0018). The value belongs to the *preceding* tile — the divider is
 * how it looks between two tiles, and pressing it opens that tile's editor,
 * because it has no state of its own. It is not an exercise: no actions, no
 * count, no drag handle.
 */
interface RestDividerProps {
  seconds: number;
  onEdit: () => void;
}

const RestDivider = ({ seconds, onEdit }: RestDividerProps) => (
  <button
    type="button"
    className="rest-divider"
    onClick={onEdit}
    aria-label={`Rest ${formatSeconds(seconds)} — edit`}
    title="Rest after the set above — tap to edit it there"
  >
    <span className="rest-divider__line" />
    <span className="rest-divider__label">Rest {formatSeconds(seconds)}</span>
    <span className="rest-divider__line" />
  </button>
);

export default RestDivider;
