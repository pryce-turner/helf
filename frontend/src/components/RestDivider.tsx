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
  /** Omitted, the divider is read-only — the upcoming queue shows it but has
   *  no editor to open. */
  onEdit?: () => void;
  /** Locked while a run includes the tile it belongs to. */
  disabled?: boolean;
}

const RestDivider = ({ seconds, onEdit, disabled }: RestDividerProps) =>
  onEdit ? (
  <button
    type="button"
    className="rest-divider"
    onClick={onEdit}
    disabled={disabled}
    aria-label={`Rest ${formatSeconds(seconds)} — edit`}
    title={
      disabled
        ? "Locked while a run includes it"
        : "Rest after the set above — tap to edit it there"
    }
  >
    <span className="rest-divider__line" />
    <span className="rest-divider__label">Rest {formatSeconds(seconds)}</span>
    <span className="rest-divider__line" />
  </button>
  ) : (
    <div className="rest-divider rest-divider--static" role="separator" aria-label={`Rest ${formatSeconds(seconds)}`}>
      <span className="rest-divider__line" />
      <span className="rest-divider__label">Rest {formatSeconds(seconds)}</span>
      <span className="rest-divider__line" />
    </div>
  );

export default RestDivider;
