import {
  useState,
  useEffect,
  useLayoutEffect,
  useCallback,
  useMemo,
  useRef,
  memo,
  Fragment,
  type ReactNode,
} from "react";
import { useParams, useNavigate } from "react-router-dom";
import { format, parseISO } from "date-fns";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  ArrowLeft,
  ArrowRight,
  Plus,
  Trash2,
  GripVertical,
  Dumbbell,
  Weight,
  Hash,
  MessageSquare,
  Pencil,
  X,
  Check,
  CheckCircle2,
  Circle,
  Calendar as CalendarIcon,
  History,
  Copy,
  Coffee,
  Play,
  StretchHorizontal,
  Timer,
  RotateCcw,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import RestDivider from "@/components/RestDivider";
import WorkoutFields from "@/components/WorkoutFields";
import ExerciseSearch from "@/components/ExerciseSearch";
import WorkoutPlayerControls from "@/components/WorkoutPlayerControls";
import { useWorkoutPlayer } from "@/hooks/useWorkoutPlayer";
import {
  defaultsFromExercise,
  formatDuration,
  formatSeconds,
  timedWorkSeconds,
} from "@/lib/setTiles";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Calendar } from "@/components/ui/calendar";
import {
  useCountFull,
  useToggleComplete,
  useMoveToDate,
  useCopyToDate,
  useSetDayMobility,
} from "@/hooks/useWorkouts";
import {
  TileSourceContext,
  useDayTileSource,
  useTileSourceContext,
  type TileSource,
} from "@/hooks/useTileSource";
import type { Workout } from "@/types/workout";
import { useExercises, useMovementBreakPool, useRecentExercises } from "@/hooks/useExercises";
import { useProgression } from "@/hooks/useProgression";
import { useSuggestMovementBreak } from "@/hooks/useMobility";
import type { WorkoutCreate } from "@/types/workout";

// The inline edit form owns its own state. Typing a digit re-renders this
// form and nothing else; while the state lived in WorkoutSession, every
// keystroke re-rendered the page and every card on it.
interface InlineEditFormProps {
  workout: Workout;
  onClose: () => void;
}

const InlineEditForm = ({ workout, onClose }: InlineEditFormProps) => {
  const { data: exercises } = useExercises();
  // A day's tile or a preset's: the form is the same, the store is not.
  const source = useTileSourceContext();
  // Clearing a Stop (only a day's tiles are ever performed): count the set
  // as run to the end, or reset it to planned so Play runs it again.
  const countFull = useCountFull();
  const toggleComplete = useToggleComplete();
  const stopped = workout.ended_early && workout.completed_at != null;
  const [showRecentWeights, setShowRecentWeights] = useState(false);

  // Seeded once from the set being edited. A refetch of the day while the
  // form is open must not overwrite what is being typed.
  const [formData, setFormData] = useState<WorkoutCreate>(() => ({
    date: workout.date,
    exercise: workout.exercise,
    // The exercise's actual category, in case the set's copy is stale
    category:
      exercises?.find((e) => e.name === workout.exercise)?.category ||
      workout.category,
    weight: workout.weight,
    weight_unit: workout.weight_unit || "lbs",
    reps: workout.reps,
    distance: workout.distance,
    distance_unit: workout.distance_unit,
    time: workout.time,
    comment: workout.comment,
    work_seconds: workout.work_seconds,
    rest_seconds: workout.rest_seconds,
    rest_after_seconds: workout.rest_after_seconds,
  }));

  // Which inputs the tile offers: the exercise's configuration, with the
  // tile's own values kept visible wherever the group has since been
  // disabled (changing an exercise never rewrites history, plan 0018).
  const exerciseConfig = exercises?.find((e) => e.name === formData.exercise);

  // Fetch progression data only when the toggle is on
  const { data: progressionData } = useProgression(
    showRecentWeights ? workout.exercise : "",
    false,
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.exercise || !formData.category) return;

    await source.updateAsync(workout.doc_id, formData);
    onClose();
  };

  const handleDuplicate = async () => {
    if (!formData.exercise || !formData.category) return;

    // A duplicate of a mobility tile is mobility work too — the intent
    // travels, the performance does not (the new tile is planned, so
    // completion and actuals reset server-side).
    await source.create({
      ...formData,
      is_mobility: workout.is_mobility,
    });
    onClose();
  };

  return (

        <div
          className="animate-in"
          style={{
            marginTop: "var(--space-5)",
            padding: "var(--space-5)",
            borderTop: "1px solid var(--border-subtle)",
            background: "var(--bg-tertiary)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <form
            onSubmit={handleSubmit}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-4)",
            }}
          >
            {stopped && (
              <div className="ended-early">
                <p className="ended-early__text">
                  Ended early
                  {workout.completed_reps != null && workout.reps != null
                    ? ` at ${workout.completed_reps} / ${workout.reps} reps`
                    : ""}
                </p>
                <div className="grid grid-cols-2" style={{ gap: "var(--space-3)" }}>
                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full justify-center"
                    disabled={countFull.isPending}
                    onClick={async () => {
                      await countFull.mutateAsync(workout.doc_id);
                      onClose();
                    }}
                  >
                    <Check style={{ width: "16px", height: "16px" }} />
                    Count as full
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full justify-center"
                    disabled={toggleComplete.isPending}
                    onClick={async () => {
                      await toggleComplete.mutateAsync({
                        id: workout.doc_id,
                        completed: false,
                      });
                      onClose();
                    }}
                  >
                    <RotateCcw style={{ width: "16px", height: "16px" }} />
                    Reset to not done
                  </Button>
                </div>
              </div>
            )}

            <WorkoutFields
              exercise={exerciseConfig}
              values={formData}
              onChange={(patch) => setFormData({ ...formData, ...patch })}
              idPrefix={`edit-${workout.doc_id}`}
            />

            <div className="form-field">
              <Label htmlFor="comment-edit" className="form-label">
                <MessageSquare style={{ width: "16px", height: "16px" }} />
                Comment
              </Label>
              <Input
                id="comment-edit"
                type="text"
                placeholder="Optional comment"
                value={formData.comment || ""}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormData({
                    ...formData,
                    comment: e.target.value || null,
                  })
                }
              />
            </div>

            {/* Action buttons - 2x2 grid */}
            <div
              className="grid grid-cols-2"
              style={{ gap: "var(--space-3)" }}
            >
              <Button
                type="button"
                variant={showRecentWeights ? "default" : "secondary"}
                onClick={() => setShowRecentWeights(!showRecentWeights)}
                className="w-full justify-center"
              >
                <History style={{ width: "16px", height: "16px" }} />
                Recent
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={handleDuplicate}
                className="w-full justify-center"
              >
                <Copy style={{ width: "16px", height: "16px" }} />
                Duplicate
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={onClose}
                className="w-full justify-center"
              >
                <X style={{ width: "16px", height: "16px" }} />
                Cancel
              </Button>
              <Button type="submit" className="w-full justify-center">
                <Check style={{ width: "16px", height: "16px" }} />
                Save
              </Button>
            </div>

            {/* Recent weights dropdown */}
            {showRecentWeights &&
              progressionData?.historical &&
              progressionData.historical.length > 0 && (
                <div
                  style={{
                    padding: "var(--space-3)",
                    background: "var(--bg-secondary)",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "var(--space-2)",
                      maxHeight: "150px",
                      overflowY: "auto",
                    }}
                  >
                    {progressionData.historical
                      .slice(-5)
                      .reverse()
                      .map((entry, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => {
                            setFormData({
                              ...formData,
                              weight: entry.weight,
                              reps: entry.reps,
                            });
                          }}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "var(--space-2)",
                            background: "var(--bg-tertiary)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: "var(--radius-sm)",
                            cursor: "pointer",
                            transition: "background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease",
                            textAlign: "left",
                          }}
                          onMouseOver={(e) => {
                            e.currentTarget.style.background =
                              "var(--bg-hover)";
                            e.currentTarget.style.borderColor =
                              "var(--accent-muted)";
                          }}
                          onMouseOut={(e) => {
                            e.currentTarget.style.background =
                              "var(--bg-tertiary)";
                            e.currentTarget.style.borderColor =
                              "var(--border-subtle)";
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "13px",
                              color: "var(--text-primary)",
                            }}
                          >
                            {entry.weight} {entry.weight_unit} × {entry.reps}
                          </span>
                          <span
                            style={{
                              fontSize: "12px",
                              color: "var(--text-muted)",
                            }}
                          >
                            {entry.date}
                          </span>
                        </button>
                      ))}
                  </div>
                </div>
              )}

            {showRecentWeights &&
              (!progressionData?.historical ||
                progressionData.historical.length === 0) && (
                <p
                  style={{
                    fontSize: "13px",
                    color: "var(--text-muted)",
                  }}
                >
                  No previous entries for this exercise
                </p>
              )}
          </form>
        </div>
  );
};

const getCategoryColor = (category: string) => {
  // Predefined colors for common categories
  const predefined: Record<string, string> = {
    Push: "var(--chart-2)", // Blue
    Pull: "var(--accent)", // Green
    Legs: "var(--chart-3)", // Purple
    Core: "var(--chart-4)", // Orange
    Cardio: "var(--error)", // Red
  };

  // Color palette for hash-based assignment
  const palette = [
    "var(--chart-1)", // Green
    "var(--chart-2)", // Blue
    "var(--chart-3)", // Purple
    "var(--chart-4)", // Orange
    "var(--chart-5)", // Yellow
    "var(--info)", // Light blue
    "var(--error)", // Red
  ];

  let color = predefined[category];
  if (!color) {
    // Simple hash function for consistent color assignment
    let hash = 0;
    for (let i = 0; i < category.length; i++) {
      hash = category.charCodeAt(i) + ((hash << 5) - hash);
    }
    color = palette[Math.abs(hash) % palette.length];
  }

  return { bg: color, text: color, border: color };
};

// Sortable workout card component.
//
// Memoized, so every prop must be stable across unrelated parent renders:
// booleans rather than the parent's edit/delete state, and callbacks from
// useCallback. A card then re-renders only when its own set changes.
interface SortableWorkoutCardProps {
  workout: Workout;
  index: number;
  isEditing: boolean;
  isConfirmingDelete: boolean;
  /** In the active run's snapshot: locked against edits underneath it. */
  isLocked: boolean;
  /** The tile the player is on right now: highlighted. */
  isActiveTile: boolean;
  /** A day's tiles can be ticked done; a preset's are never performed. */
  showCompletion: boolean;
  handleEditWorkout: (workout: Workout) => void;
  handleToggleComplete: (workout: Workout) => void;
  handleToggleMobility: (workout: Workout) => void;
  handleDeleteClick: (id: number) => void;
  handleDeleteConfirm: (id: number) => void;
  handleDeleteCancel: () => void;
  onCloseEdit: () => void;
}

const SortableWorkoutCard = memo(function SortableWorkoutCard({
  index,
  ...contentProps
}: SortableWorkoutCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: contentProps.workout.doc_id });

  // dnd-kit builds new listener functions on every DndContext render, which
  // would defeat WorkoutCardContent's memo. Hand it stable handlers that call
  // the latest ones instead. The names match the sensors WorkoutSession sets
  // up: PointerSensor activates on pointerdown, KeyboardSensor on keydown.
  const listenersRef = useRef(listeners);
  useLayoutEffect(() => {
    listenersRef.current = listeners;
  });
  const stableListeners = useMemo(
    () => ({
      onPointerDown: (e: React.PointerEvent) =>
        listenersRef.current?.onPointerDown?.(e),
      onKeyDown: (e: React.KeyboardEvent) =>
        listenersRef.current?.onKeyDown?.(e),
    }),
    [],
  );

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    animationDelay: `${index * 50}ms`,
  };

  return (
    <Card ref={setNodeRef} style={style} className="card-hover animate-in">
      <WorkoutCardContent
        {...contentProps}
        isDragging={isDragging}
        dragAttributes={attributes}
        dragListeners={stableListeners}
      />
    </Card>
  );
});

// What a card shows. Split from SortableWorkoutCard because useSortable
// re-renders every card whenever DndContext does, which memo cannot stop;
// keeping the subscription in that thin wrapper lets this part skip.
type WorkoutCardContentProps = Omit<SortableWorkoutCardProps, "index"> & {
  isDragging: boolean;
  dragAttributes: ReturnType<typeof useSortable>["attributes"];
  dragListeners: {
    onPointerDown: (e: React.PointerEvent) => void;
    onKeyDown: (e: React.KeyboardEvent) => void;
  };
};

const WorkoutCardContent = memo(function WorkoutCardContent({
  workout,
  isEditing,
  isConfirmingDelete,
  isLocked,
  isActiveTile,
  showCompletion,
  handleEditWorkout,
  handleToggleComplete,
  handleToggleMobility,
  handleDeleteClick,
  handleDeleteConfirm,
  handleDeleteCancel,
  onCloseEdit,
  isDragging,
  dragAttributes,
  dragListeners,
}: WorkoutCardContentProps) {
  const catColor = getCategoryColor(workout.category);

  return (
    <CardContent
      className={`set-row${isActiveTile ? " set-row--active" : ""}`}
    >
      {isEditing && (
        <button
          type="button"
          className="action-btn"
          onClick={(e) => {
            e.stopPropagation();
            onCloseEdit();
          }}
          title="Close edit"
          aria-label="Close edit"
          style={{
            position: "absolute",
            top: "var(--space-3)",
            right: "var(--space-3)",
            zIndex: 2,
            width: "36px",
            height: "36px",
          }}
        >
          <X style={{ width: "16px", height: "16px" }} />
        </button>
      )}
      {!isEditing && (
        <div className="set-row__actions">
          {/* Completion checkbox. A preset keeps its cell empty, so the
              other controls sit where they do on a day. */}
          {!showCompletion && <span aria-hidden="true" />}
          {showCompletion && (
          <button
            className="action-btn"
            disabled={isLocked}
            onClick={(e) => {
              e.stopPropagation();
              handleToggleComplete(workout);
            }}
            title={
              isLocked
                ? "Locked while a run includes it"
                : workout.completed_at
                  ? "Mark incomplete"
                  : "Mark complete"
            }
            style={{
              color: workout.completed_at
                ? "var(--accent)"
                : "var(--text-muted)",
              opacity: workout.completed_at ? 1 : 0.5,
              padding: "4px",
            }}
          >
            {workout.completed_at ? (
              <CheckCircle2 className="set-row__icon" />
            ) : (
              <Circle className="set-row__icon" />
            )}
          </button>
          )}

          {/* Mobility toggle.
              Whether a set was mobility work is a property of *that set*:
              the same movement is a lift one day and a loaded stretch the
              next, so it cannot be answered on the exercise. The most
              recent day carrying any flagged set is the session the agent
              writes the next prescription from, which is why this is one
              tap and sits beside completion rather than behind Edit. */}
          <button
            className="action-btn"
            role="checkbox"
            aria-checked={!!workout.is_mobility}
            aria-label="Mobility work"
            disabled={isLocked}
            onClick={(e) => {
              e.stopPropagation();
              handleToggleMobility(workout);
            }}
            title={
              workout.is_mobility
                ? "Mobility work — feeds the next mobility session"
                : "Mark as mobility work"
            }
            style={{
              color: workout.is_mobility
                ? "var(--accent)"
                : "var(--text-muted)",
              opacity: workout.is_mobility ? 1 : 0.5,
              padding: "4px",
            }}
          >
            <StretchHorizontal className="set-row__icon" />
          </button>

          {/* Drag handle */}
          <button
            className="action-btn drag-handle"
            disabled={isLocked}
            style={{
              cursor: isDragging ? "grabbing" : "grab",
              touchAction: "none",
              padding: "4px",
            }}
            {...(isLocked ? {} : dragAttributes)}
            {...(isLocked ? {} : dragListeners)}
          >
            <GripVertical className="set-row__icon" />
          </button>

          {/* Delete button */}
          {isConfirmingDelete ? (
            <div
              className="flex"
              style={{ gap: "4px", gridColumn: "1 / -1" }}
            >
              <button
                className="action-btn action-btn--danger"
                onClick={() => handleDeleteConfirm(workout.doc_id)}
                title="Confirm delete"
                disabled={isLocked}
                style={{ padding: "4px" }}
              >
                <Check className="set-row__icon" />
              </button>
              <button
                className="action-btn"
                onClick={handleDeleteCancel}
                title="Cancel"
                disabled={isLocked}
                style={{ padding: "4px" }}
              >
                <X className="set-row__icon" />
              </button>
            </div>
          ) : (
            <button
              className="action-btn action-btn--danger"
              disabled={isLocked}
              onClick={() => handleDeleteClick(workout.doc_id)}
              style={{ padding: "4px" }}
            >
              <Trash2 className="set-row__icon" />
            </button>
          )}
        </div>
      )}

      {/* Main content - clickable area. The active tile is locked against
          edits while the player is on it: the run writes from its snapshot,
          and an edit underneath it would read as if it counted. */}
      <div
        className="set-row__body log-line"
        onClick={() =>
          !isEditing && !isLocked ? handleEditWorkout(workout) : undefined
        }
        style={{
          cursor: !isEditing && !isLocked ? "pointer" : "default",
        }}
      >
        {/* Exercise name and category - inline */}
        <div className="log-line__title">
          <h3
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "18px",
              fontWeight: 600,
              color: "var(--text-primary)",
              margin: 0,
            }}
          >
            {workout.exercise}
          </h3>
          <span
            style={{
              padding: "4px 10px",
              borderRadius: "var(--radius-sm)",
              border: `1px solid ${catColor.border}`,
              color: catColor.text,
              background: `${catColor.bg}20`,
              fontSize: "13px",
              fontWeight: 500,
            }}
          >
            {workout.category}
          </span>
        </div>

        {/* Data chips */}
        <div className="log-line__chips">
          {workout.weight && (
            <div className="workout-chip">
              <Weight
                style={{
                  width: "16px",
                  height: "16px",
                  color: "var(--text-muted)",
                }}
              />
              <span className="workout-chip__value" style={{ fontSize: "14px" }}>
                {workout.weight} {workout.weight_unit}
              </span>
            </div>
          )}
          {workout.reps != null && (
            <div className="workout-chip">
              <Hash
                style={{
                  width: "16px",
                  height: "16px",
                  color: "var(--text-muted)",
                }}
              />
              <span className="workout-chip__value" style={{ fontSize: "14px" }}>
                {/* A stopped tile reads target versus actual; anything else
                    is just the target. */}
                {workout.ended_early && workout.completed_reps != null
                  ? `${workout.completed_reps} / ${workout.reps} reps`
                  : `${workout.reps} reps`}
              </span>
            </div>
          )}
          {/* Timed tiles. Natural completions show the one concise result;
              a Stop shows what was measured against what was planned. */}
          {workout.work_seconds != null && (
            <div className="workout-chip">
              <Timer
                style={{
                  width: "16px",
                  height: "16px",
                  color: "var(--text-muted)",
                }}
              />
              <span className="workout-chip__value" style={{ fontSize: "14px" }}>
                {workout.ended_early && workout.actual_work_seconds != null
                  ? `${formatSeconds(workout.actual_work_seconds)} / ${formatSeconds(workout.work_seconds)}`
                  : formatSeconds(workout.work_seconds)}
              </span>
            </div>
          )}
          {workout.ended_early && (
            <div className="workout-chip">
              <span
                className="workout-chip__value"
                style={{ fontSize: "12px", color: "var(--warning)" }}
              >
                ended early
              </span>
            </div>
          )}
          {/* A legacy timed set — written before the numeric fields, kept so
              old rows still say what they always said. */}
          {!workout.work_seconds && workout.time && (
            <div className="workout-chip">
              <Timer
                style={{
                  width: "16px",
                  height: "16px",
                  color: "var(--text-muted)",
                }}
              />
              <span className="workout-chip__value" style={{ fontSize: "14px" }}>
                {workout.time}
              </span>
            </div>
          )}
          {workout.comment && (
            <div className="workout-chip">
              <MessageSquare
                style={{
                  width: "16px",
                  height: "16px",
                  color: "var(--text-muted)",
                }}
              />
              <span className="workout-chip__comment">
                {workout.comment}
              </span>
            </div>
          )}
        </div>
      </div>

      {isEditing && (
        <InlineEditForm workout={workout} onClose={onCloseEdit} />
      )}
    </CardContent>
  );
});

interface DayEditorProps {
  /** Where the tiles live: a dated day, or a preset (plan 0020). */
  source: TileSource;
  /** The day being edited. Absent for a preset, which has no date. */
  date?: string;
  title: ReactNode;
  subtitle: ReactNode;
  onBack: () => void;
  /** Buttons beside Add — a preset's Apply and Delete. */
  extraActions?: ReactNode;
  /** Cards under the header, above the add form — a preset's apply calendar. */
  extraPanels?: ReactNode;
  emptyTitle: string;
  emptyText: string;
}

/**
 * The tile editor: add form, cards, inline edit, drag reorder, delete.
 *
 * One editor for a day and for a preset, so the two cannot drift. What only a
 * dated day has — completion, the day player, move/copy, the bulk mobility
 * flag, a movement break suggestion — renders only when the source is a day.
 */
export const DayEditor = ({
  source,
  date,
  title,
  subtitle,
  onBack,
  extraActions,
  extraPanels,
  emptyTitle,
  emptyText,
}: DayEditorProps) => {
  const navigate = useNavigate();
  const isDay = source.kind === "day";

  const workouts = source.tiles;
  const isLoading = source.isLoading;
  const { data: exercises } = useExercises();
  const { data: recentExercises } = useRecentExercises(8);
  const { data: movementBreakPool } = useMovementBreakPool();
  const suggestMovementBreak = useSuggestMovementBreak();

  const toggleComplete = useToggleComplete();
  const moveToDate = useMoveToDate();
  const copyToDate = useCopyToDate();
  const setDayMobility = useSetDayMobility();

  // Drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedExercise, setSelectedExercise] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
  const [showAddRecent, setShowAddRecent] = useState(false);
  const [showMoveCalendar, setShowMoveCalendar] = useState(false);
  const [targetDate, setTargetDate] = useState<Date | undefined>(new Date());
  const [showCopyCalendar, setShowCopyCalendar] = useState(false);
  const [copyTargetDate, setCopyTargetDate] = useState<Date | undefined>(undefined);
  const [formData, setFormData] = useState<WorkoutCreate>({
    date: date || format(new Date(), "yyyy-MM-dd"),
    exercise: "",
    category: "",
    weight: null,
    weight_unit: "lbs",
    reps: null,
    distance: null,
    distance_unit: null,
    time: null,
    comment: null,
  });

  const handleExerciseChange = (exercise: string) => {
    const exerciseData = exercises?.find((e) => e.name === exercise);
    setSelectedExercise(exercise);
    // The tile's values start as the exercise's defaults (plan 0018):
    // enabled-with-blank-default starts blank, and a disabled group's
    // default is never applied.
    setFormData({
      ...formData,
      exercise,
      category: exerciseData?.category || formData.category,
      ...(exerciseData ? defaultsFromExercise(exerciseData) : {}),
    });
  };

  const resetForm = useCallback(() => {
    setFormData({
      date: date || format(new Date(), "yyyy-MM-dd"),
      exercise: "",
      category: "",
      weight: null,
      weight_unit: "lbs",
      reps: null,
      distance: null,
      distance_unit: null,
      time: null,
      comment: null,
      work_seconds: null,
      rest_seconds: null,
      rest_after_seconds: null,
    });
    setSelectedExercise("");
    setEditingId(null);
    setShowForm(false);
    setShowAddRecent(false);
  }, [date]);

  // Opening a set for editing closes and clears the add form; the edit
  // itself lives in that card's InlineEditForm.
  const handleEditWorkout = useCallback(
    (workout: Workout) => {
      resetForm();
      setEditingId(workout.doc_id);
    },
    [resetForm],
  );

  const handleCloseEdit = useCallback(() => setEditingId(null), []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.exercise || !formData.category) {
      return;
    }

    await source.create(formData);
    resetForm();
  };

  // Auto-cancel delete confirmation after 3 seconds
  useEffect(() => {
    if (confirmingDelete !== null) {
      const timer = setTimeout(() => setConfirmingDelete(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [confirmingDelete]);

  const handleDeleteClick = useCallback((id: number) => {
    setConfirmingDelete(id);
  }, []);

  // The mutation objects change identity with their own pending state, so
  // the callbacks depend on `mutate`/`mutateAsync`, which are stable. That
  // keeps one card's toggle from re-rendering every other card.
  const { remove: removeTile } = source;
  const handleDeleteConfirm = useCallback(
    async (id: number) => {
      await removeTile(id);
      setConfirmingDelete(null);
    },
    [removeTile],
  );

  const handleDeleteCancel = useCallback(() => {
    setConfirmingDelete(null);
  }, []);

  const { mutate: toggleCompleteMutate } = toggleComplete;
  const handleToggleComplete = useCallback(
    (workout: Workout) => {
      toggleCompleteMutate({
        id: workout.doc_id,
        completed: !workout.completed_at,
      });
    },
    [toggleCompleteMutate],
  );

  // Sorted once per change of the day's sets, into a new array. Sorting
  // `workouts` in place, as render used to, mutated React Query's cache.
  const sortedWorkouts = useMemo(
    () => (workouts ? [...workouts].sort((a, b) => a.order - b.order) : []),
    [workouts],
  );

  // What Play runs: the timed sets from the first incomplete timed one,
  // up to the next incomplete *untimed* set. The player is a timer — an
  // untimed set (a lift) has nothing to count down, and offering a check
  // for it at the end of a timed run ticked off sets that were never done.
  // So a run stops there; tick the lift off, and Play picks up after it.
  // Completed sets in between are passed over, not a reason to stop.
  const playableTiles = useMemo(() => {
    const start = sortedWorkouts.findIndex(
      (w) => !w.completed_at && w.work_seconds != null,
    );
    if (start === -1) return [];
    const block: Workout[] = [];
    for (const w of sortedWorkouts.slice(start)) {
      if (w.completed_at) continue;
      if (w.work_seconds == null) break;
      block.push(w);
    }
    return block;
  }, [sortedWorkouts]);

  // The day player (plan 0018). It runs the playable tiles in order from an
  // immutable snapshot taken at Play; the write for each tile lands before
  // the run advances. It watches the playable list so a suggestion landing
  // after a finished run re-arms it.
  const player = useWorkoutPlayer(playableTiles);
  // A finished run closes: the player is shown while a run is live (or
  // failed), never as a "done" screen to dismiss.
  const playing = player.status !== "idle" && player.status !== "done";
  // A finished run is not terminal: Play re-arms whenever timed sets remain.
  const canPlay =
    (player.status === "idle" || player.status === "done") &&
    playableTiles.length > 0;
  // A failed write is not a released snapshot either: the tiles stay locked
  // in `error` until Retry lands or the run is discarded.
  const runLive =
    player.status === "running" ||
    player.status === "paused" ||
    player.status === "saving" ||
    player.status === "error";
  // Every tile in the snapshot is locked while the run is live, not just the
  // one playing: a queued tile deleted or ticked underneath the run is a 404
  // Retry loop or a double count.
  const lockedTileIds = useMemo(
    () => new Set(runLive ? player.tiles.map((t) => t.doc_id) : []),
    [runLive, player.tiles],
  );
  // Every card's useSortable subscribes to SortableContext, which memo does
  // not block, and the context changes whenever `items` is a new array. So
  // the id list keeps its identity until the order itself changes; otherwise
  // ticking one set re-renders every card on the day.
  const sortedIdsKey = sortedWorkouts.map((w) => w.doc_id).join(",");
  const sortedIds = useMemo(
    () => (sortedIdsKey ? sortedIdsKey.split(",").map(Number) : []),
    [sortedIdsKey],
  );

  const { reorder: bulkReorderMutate } = source;
  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;

      if (over && active.id !== over.id) {
        const oldIndex = sortedWorkouts.findIndex(
          (w) => w.doc_id === active.id,
        );
        const newIndex = sortedWorkouts.findIndex((w) => w.doc_id === over.id);

        if (oldIndex !== -1 && newIndex !== -1) {
          const reordered = arrayMove(sortedWorkouts, oldIndex, newIndex);
          const workoutIds = reordered.map((w) => w.doc_id);
          bulkReorderMutate(workoutIds);
        }
      }
    },
    [sortedWorkouts, bulkReorderMutate],
  );

  const handleMoveToDate = useCallback(async () => {
    if (!date || !targetDate) return;
    const targetDateStr = format(targetDate, "yyyy-MM-dd");
    await moveToDate.mutateAsync({
      sourceDate: date,
      targetDate: targetDateStr,
    });
    setShowMoveCalendar(false);
    navigate(`/workout/${targetDateStr}`);
  }, [date, targetDate, moveToDate, navigate]);

  const handleCopyToDate = useCallback(async () => {
    if (!date || !copyTargetDate) return;
    const targetDateStr = format(copyTargetDate, "yyyy-MM-dd");
    await copyToDate.mutateAsync({
      sourceDate: date,
      targetDate: targetDateStr,
    });
    setShowCopyCalendar(false);
    // Stay on current page (unlike move which navigates)
  }, [date, copyTargetDate, copyToDate]);

  // Whether every set on this day is already mobility work — which is what
  // decides the bulk button's direction. Derived from the rows, never stored:
  // there is no day-level fact here, and a day whose sets disagree is a valid
  // state the button simply moves out of (plan 0013 §6).
  const allMobility =
    (workouts?.length ?? 0) > 0 && (workouts ?? []).every((w) => w.is_mobility);

  const handleToggleDayMobility = useCallback(() => {
    if (!date || !workouts?.length) return;
    setDayMobility.mutate({ date, isMobility: !allMobility });
  }, [date, workouts, allMobility, setDayMobility]);

  // Flipping one set's mobility flag.
  //
  // A full-shape PUT because that is what the endpoint takes; `is_mobility` is
  // the only field that changes. The backend leaves the flag alone when the
  // key is absent, so sending it explicitly is what makes this a deliberate
  // edit rather than a side effect of some other save.
  const { update: updateTile } = source;
  const handleToggleMobility = useCallback(
    (workout: Workout) => {
      updateTile(workout.doc_id, {
          date: workout.date,
          exercise: workout.exercise,
          category: workout.category,
          weight: workout.weight,
          reps: workout.reps,
          distance: workout.distance,
          distance_unit: workout.distance_unit,
          time: workout.time,
          comment: workout.comment,
          completed_at: workout.completed_at,
          order: workout.order,
          is_mobility: !workout.is_mobility,
          // Targets round-trip too: a PUT is a full replace for them, and a
          // toggle that dropped the timing would erase the tile's plan.
          work_seconds: workout.work_seconds,
          rest_seconds: workout.rest_seconds,
          rest_after_seconds: workout.rest_after_seconds,
      });
    },
    [updateTile],
  );

  // Progression data for add form's selected exercise
  const { data: addFormProgression } = useProgression(
    showAddRecent && selectedExercise && editingId === null
      ? selectedExercise
      : "",
    false,
  );


  return (
    <TileSourceContext.Provider value={source}>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          {/* Header */}
          <div
            className="flex flex-col sm:flex-row sm:items-center justify-between animate-in"
            style={{ gap: "var(--space-4)", marginBottom: "var(--space-6)" }}
          >
            <div
              className="flex items-center"
              style={{ gap: "var(--space-4)" }}
            >
              <Button
                variant="secondary"
                size="icon"
                onClick={onBack}
                className="icon-btn"
                aria-label="Back"
              >
                <ArrowLeft style={{ width: "16px", height: "16px" }} />
              </Button>
              <div style={{ minWidth: 0 }}>
                <h1 className="page__title page__title--compact">{title}</h1>
                <p className="page__subtitle">{subtitle}</p>
              </div>
            </div>

            <div className="flex flex-wrap" style={{ gap: "var(--space-2)" }}>
              {isDay && workouts && workouts.length > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowMoveCalendar(!showMoveCalendar)}
                >
                  <CalendarIcon style={{ width: "16px", height: "16px" }} />
                  Move
                </Button>
              )}
              {isDay && workouts && workouts.length > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowCopyCalendar(!showCopyCalendar)}
                >
                  <Copy style={{ width: "16px", height: "16px" }} />
                  Copy
                </Button>
              )}
              {isDay && workouts && workouts.length > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleToggleDayMobility}
                  disabled={setDayMobility.isPending}
                  title={
                    allMobility
                      ? "Clear the mobility flag on every set of this day"
                      : "Flag every set of this day as mobility work — this is what the agent reads the next session back from"
                  }
                  style={{
                    color: allMobility ? "var(--accent)" : undefined,
                  }}
                >
                  <StretchHorizontal style={{ width: "16px", height: "16px" }} />
                  {allMobility ? "Unmark all" : "Mark all mobility"}
                </Button>
              )}
              {/* The day player runs the incomplete tiles from the first one
                  on. A finished run is not terminal: Play re-arms whenever
                  incomplete tiles remain. */}
              {isDay && canPlay && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    // Play owns the snapshot: anything pre-opened — an edit
                    // form, a delete confirm — must not act under it.
                    setConfirmingDelete(null);
                    setEditingId(null);
                    player.play(playableTiles);
                  }}
                  title="Play the timed sets, from the first incomplete one up to the next untimed set"
                >
                  <Play style={{ width: "16px", height: "16px" }} />
                  Play
                </Button>
              )}
              {/* A movement break is inserted as an ordinary planned tile on
                  this date (plan 0018) — editable and deletable like any
                  other, and not work until it is played. Hidden when the
                  pool is empty; the Mobility page is where it gets filled. */}
              {isDay && (movementBreakPool?.length ?? 0) > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => date && suggestMovementBreak.mutate(date)}
                  disabled={suggestMovementBreak.isPending}
                  title="Suggest an equipment-free movement onto this day"
                >
                  <Coffee style={{ width: "16px", height: "16px" }} />
                  Movement break
                </Button>
              )}
              {extraActions}
              <Button
                size="sm"
                onClick={() => {
                  if (showForm) {
                    resetForm();
                  } else {
                    setShowForm(true);
                  }
                }}
              >
                <Plus style={{ width: "16px", height: "16px" }} />
                Add
              </Button>
            </div>
          </div>

          {extraPanels}

          {/* Move to Date Calendar */}
          {showMoveCalendar && (
            <Card
              className="animate-in"
              style={{
                marginBottom: "var(--space-6)",
                border: "1px solid var(--border)",
              }}
            >
              <CardContent style={{ padding: "var(--space-5)" }}>
                <p
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "14px",
                    color: "var(--text-secondary)",
                    marginBottom: "var(--space-4)",
                  }}
                >
                  Select target date
                </p>
                <Calendar
                  mode="single"
                  selected={targetDate}
                  onSelect={setTargetDate}
                  className="rounded-[var(--radius-md)] border border-[var(--border)]"
                />
                <div
                  className="flex justify-end"
                  style={{ marginTop: "var(--space-4)", gap: "var(--space-2)" }}
                >
                  <Button
                    variant="secondary"
                    onClick={() => setShowMoveCalendar(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleMoveToDate}
                    disabled={
                      !targetDate || format(targetDate, "yyyy-MM-dd") === date
                    }
                  >
                    <ArrowRight style={{ width: "16px", height: "16px" }} />
                    Move to {targetDate && format(targetDate, "MMM d, yyyy")}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Copy to Date Calendar */}
          {showCopyCalendar && (
            <Card
              className="animate-in"
              style={{
                marginBottom: "var(--space-6)",
                border: "1px solid var(--border)",
              }}
            >
              <CardContent style={{ padding: "var(--space-5)" }}>
                <p
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "14px",
                    color: "var(--text-secondary)",
                    marginBottom: "var(--space-4)",
                  }}
                >
                  Select target date
                </p>
                <Calendar
                  mode="single"
                  selected={copyTargetDate}
                  onSelect={setCopyTargetDate}
                  className="rounded-[var(--radius-md)] border border-[var(--border)]"
                />
                <div
                  className="flex justify-end"
                  style={{ marginTop: "var(--space-4)", gap: "var(--space-2)" }}
                >
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowCopyCalendar(false);
                      setCopyTargetDate(undefined);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleCopyToDate}
                    disabled={
                      !copyTargetDate ||
                      format(copyTargetDate, "yyyy-MM-dd") === date
                    }
                  >
                    <Copy style={{ width: "16px", height: "16px" }} />
                    Copy to{" "}
                    {copyTargetDate && format(copyTargetDate, "MMM d, yyyy")}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Add Exercise Form - Only show at top for new exercises */}
          {showForm && editingId === null && (
            <Card
              className="animate-in"
              style={{
                marginBottom: "var(--space-6)",
              }}
            >
              <CardHeader
                className="flex items-center"
                style={{
                  borderBottom: "1px solid var(--border-subtle)",
                  flexDirection: "row",
                  justifyContent: "space-between",
                  gap: "var(--space-3)",
                }}
              >
                <CardTitle
                  className="flex items-center"
                  style={{
                    gap: "var(--space-2)",
                    fontFamily: "var(--font-display)",
                    fontSize: "18px",
                    minWidth: 0,
                  }}
                >
                  {editingId !== null ? (
                    <Pencil
                      style={{
                        width: "16px",
                        height: "16px",
                        color: "var(--accent)",
                      }}
                    />
                  ) : (
                    <Dumbbell
                      style={{
                        width: "16px",
                        height: "16px",
                        color: "var(--accent)",
                      }}
                    />
                  )}
                  {editingId !== null ? "Edit exercise" : "Add exercise"}
                </CardTitle>
                {/* Closing lives here rather than as a third footer button.
                    Three buttons on one justify-end row do not fit a phone,
                    and with no wrapping the first one was pushed out of the
                    left edge of the card. */}
                <button
                  type="button"
                  className="action-btn"
                  onClick={resetForm}
                  title="Close"
                  aria-label="Close"
                  style={{
                    flexShrink: 0,
                    width: "36px",
                    height: "36px",
                    color: "var(--text-secondary)",
                  }}
                >
                  <X style={{ width: "16px", height: "16px" }} />
                </button>
              </CardHeader>
              <CardContent style={{ padding: "var(--space-6)" }}>
                {/* Recent Exercises */}
                {recentExercises && recentExercises.length > 0 && (
                  <div style={{ marginBottom: "var(--space-6)" }}>
                    <Label className="form-label" style={{ marginBottom: "var(--space-3)" }}>
                      <History style={{ width: "16px", height: "16px" }} />
                      Recents
                    </Label>
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "var(--space-2)",
                      }}
                    >
                      {recentExercises.map((ex) => {
                        const isSelected = selectedExercise === ex.name;
                        const catColor = getCategoryColor(ex.category);
                        return (
                          <button
                            key={ex.doc_id}
                            type="button"
                            onClick={() => {
                              setSelectedExercise(ex.name);
                              setFormData({
                                ...formData,
                                exercise: ex.name,
                                category: ex.category,
                                ...defaultsFromExercise(ex),
                              });
                            }}
                            style={{
                              padding: "8px 14px",
                              borderRadius: "var(--radius-sm)",
                              border: isSelected
                                ? "1px solid var(--accent)"
                                : `1px solid ${catColor.border}40`,
                              background: isSelected
                                ? "var(--accent-glow)"
                                : `${catColor.bg}10`,
                              color: isSelected ? "var(--accent)" : "var(--text-primary)",
                              fontSize: "13px",
                              fontWeight: 500,
                              cursor: "pointer",
                              transition: "background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease",
                              fontFamily: "var(--font-body)",
                            }}
                          >
                            {ex.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                <form
                  onSubmit={handleSubmit}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-6)",
                  }}
                >
                  {/* One search across every movement, results live with
                      their category — not a category dropdown and then an
                      exercise dropdown inside it. */}
                  <div className="form-field">
                    <Label htmlFor="exercise-search" className="form-label">
                      <Dumbbell style={{ width: "16px", height: "16px" }} />
                      Exercise
                    </Label>
                    <ExerciseSearch
                      id="exercise-search"
                      exercises={exercises ?? []}
                      value={selectedExercise}
                      onSelect={(exercise) => handleExerciseChange(exercise.name)}
                      onClear={() => {
                        setSelectedExercise("");
                        setFormData({ ...formData, exercise: "", category: "" });
                      }}
                    />
                  </div>

                  {/* The exercise's configuration decides which of these
                      exist (plan 0018): nothing renders for a disabled group,
                      and its defaults arrive with the selection. */}
                  <WorkoutFields
                    exercise={exercises?.find(
                      (e) => e.name === formData.exercise,
                    )}
                    values={formData}
                    onChange={(patch) =>
                      setFormData({ ...formData, ...patch })
                    }
                    idPrefix="add"
                  />

                  <div className="form-field" style={{ overflow: "hidden" }}>
                    <Label htmlFor="comment" className="form-label">
                      <MessageSquare
                        style={{ width: "16px", height: "16px" }}
                      />
                      Comment
                    </Label>
                    <Input
                      id="comment"
                      type="text"
                      placeholder="Optional comment"
                      value={formData.comment || ""}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setFormData({
                          ...formData,
                          comment: e.target.value || null,
                        })
                      }
                    />
                  </div>

                  <div
                    className="flex justify-end flex-wrap"
                    style={{
                      gap: "var(--space-3)",
                      marginTop: "var(--space-4)",
                    }}
                  >
                    {selectedExercise && (
                      <Button
                        type="button"
                        variant={showAddRecent ? "default" : "secondary"}
                        onClick={() => setShowAddRecent(!showAddRecent)}
                      >
                        <History style={{ width: "16px", height: "16px" }} />
                        Recent
                      </Button>
                    )}
                    <Button
                      type="submit"
                      disabled={!formData.exercise || !formData.category}
                    >
                      {editingId !== null ? (
                        <Pencil style={{ width: "16px", height: "16px" }} />
                      ) : (
                        <Plus style={{ width: "16px", height: "16px" }} />
                      )}
                      {editingId !== null ? "Save" : "Add workout"}
                    </Button>
                  </div>

                  {showAddRecent &&
                    selectedExercise &&
                    addFormProgression?.historical &&
                    addFormProgression.historical.length > 0 && (
                      <div
                        style={{
                          padding: "var(--space-3)",
                          background: "var(--bg-secondary)",
                          borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: "var(--space-2)",
                            maxHeight: "150px",
                            overflowY: "auto",
                          }}
                        >
                          {addFormProgression.historical
                            .slice(-5)
                            .reverse()
                            .map((entry, i) => (
                              <button
                                key={i}
                                type="button"
                                onClick={() => {
                                  setFormData({
                                    ...formData,
                                    weight: entry.weight,
                                    reps: entry.reps,
                                  });
                                }}
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center",
                                  padding: "var(--space-2)",
                                  background: "var(--bg-tertiary)",
                                  border: "1px solid var(--border-subtle)",
                                  borderRadius: "var(--radius-sm)",
                                  cursor: "pointer",
                                  transition: "background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease",
                                  textAlign: "left",
                                }}
                                onMouseOver={(e) => {
                                  e.currentTarget.style.background =
                                    "var(--bg-hover)";
                                  e.currentTarget.style.borderColor =
                                    "var(--accent-muted)";
                                }}
                                onMouseOut={(e) => {
                                  e.currentTarget.style.background =
                                    "var(--bg-tertiary)";
                                  e.currentTarget.style.borderColor =
                                    "var(--border-subtle)";
                                }}
                              >
                                <span
                                  style={{
                                    fontFamily: "var(--font-mono)",
                                    fontSize: "13px",
                                    color: "var(--text-primary)",
                                  }}
                                >
                                  {entry.weight} {entry.weight_unit} × {entry.reps}
                                </span>
                                <span
                                  style={{
                                    fontSize: "12px",
                                    color: "var(--text-muted)",
                                  }}
                                >
                                  {entry.date}
                                </span>
                              </button>
                            ))}
                        </div>
                      </div>
                    )}

                  {showAddRecent &&
                    selectedExercise &&
                    (!addFormProgression?.historical ||
                      addFormProgression.historical.length === 0) && (
                      <p
                        style={{
                          fontSize: "13px",
                          color: "var(--text-muted)",
                        }}
                      >
                        No previous entries for this exercise
                      </p>
                    )}
                </form>
              </CardContent>
            </Card>
          )}

          {/* The player hero, while a run is live (or just after one). */}
          {playing && (
            <WorkoutPlayerControls
              status={player.status}
              phaseKind={player.phase?.kind ?? null}
              exerciseName={
                player.activeTileId != null
                  ? (sortedWorkouts.find((w) => w.doc_id === player.activeTileId)
                      ?.exercise ??
                    player.tiles.find((t) => t.doc_id === player.activeTileId)
                      ?.exercise ??
                    null)
                  : null
              }
              progressLabel={
                player.status === "saving" ? "Saving…" : player.progressLabel
              }
              remainingMs={player.remainingMs}
              onPause={player.pause}
              onResume={player.resume}
              onStop={player.stop}
              onCompleteSet={player.completeSet}
              onRetry={player.retry}
              onCancel={player.cancel}
              onRestartPhase={player.restartPhase}
              onSkipPhase={player.skipPhase}
            />
          )}

          {/* Workout List */}
          {isLoading ? (
            <div
              className="text-center"
              style={{ padding: "var(--space-16) 0" }}
            >
              <div className="loading-spinner inline-block" />
              <p
                style={{
                  marginTop: "var(--space-4)",
                  color: "var(--text-muted)",
                }}
              >
                Loading workouts...
              </p>
            </div>
          ) : workouts && workouts.length > 0 ? (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={sortedIds}
                strategy={verticalListSortingStrategy}
              >
                <div
                  className="stagger-children"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-4)",
                  }}
                >
                  {sortedWorkouts.map((workout, index) => (
                    <Fragment key={workout.doc_id}>
                      <SortableWorkoutCard
                        workout={workout}
                        index={index}
                        isEditing={editingId === workout.doc_id}
                        isConfirmingDelete={confirmingDelete === workout.doc_id}
                        isLocked={lockedTileIds.has(workout.doc_id)}
                        isActiveTile={
                          runLive && player.activeTileId === workout.doc_id
                        }
                        showCompletion={isDay}
                        handleEditWorkout={handleEditWorkout}
                        handleToggleComplete={handleToggleComplete}
                        handleToggleMobility={handleToggleMobility}
                        handleDeleteClick={handleDeleteClick}
                        handleDeleteConfirm={handleDeleteConfirm}
                        handleDeleteCancel={handleDeleteCancel}
                        onCloseEdit={handleCloseEdit}
                      />
                      {/* The rest after a tile is *its* rest-after value,
                          rendered as a divider rather than a row (plan
                          0018): not an exercise, not counted, edited through
                          the tile it follows. Zero means no rest. */}
                      {workout.rest_after_seconds != null &&
                        workout.rest_after_seconds > 0 && (
                          <RestDivider
                            seconds={workout.rest_after_seconds}
                            onEdit={() => handleEditWorkout(workout)}
                            disabled={lockedTileIds.has(workout.doc_id)}
                          />
                        )}
                    </Fragment>
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          ) : (
            <Card
              style={{
                border: "2px dashed var(--border)",
                background: "transparent",
              }}
            >
              <CardContent className="empty-state">
                <div className="empty-state__icon">
                  <Dumbbell
                    style={{
                      width: "40px",
                      height: "40px",
                      color: "var(--text-muted)",
                    }}
                  />
                </div>
                <h3 className="empty-state__title">{emptyTitle}</h3>
                <p className="empty-state__text">{emptyText}</p>
                <Button onClick={() => setShowForm(true)}>
                  <Plus style={{ width: "16px", height: "16px" }} />
                  Add your first exercise
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </TileSourceContext.Provider>
  );
};

const WorkoutSession = () => {
  const { date } = useParams<{ date: string }>();
  const navigate = useNavigate();
  const source = useDayTileSource(date);
  const workouts = source.tiles;

  const formattedDate = date ? format(parseISO(date), "MMMM d, yyyy") : "";
  // Performed tiles are logged work; planned ones — a suggestion included —
  // are named as such rather than counted into the log (plan 0018).
  const performedCount = (workouts ?? []).filter((w) => w.completed_at).length;
  const plannedCount = (workouts?.length ?? 0) - performedCount;
  // Every timed set on the day, performed or planned (plan 0018 totals).
  const timedSeconds = timedWorkSeconds(workouts ?? []);

  return (
    <DayEditor
      source={source}
      date={date}
      title={formattedDate}
      subtitle={
        <>
          {/* Performed tiles only: a planned tile — a suggestion — is not
              logged work (plan 0018), and the count must not call it one. */}
          {performedCount} exercise
          {performedCount !== 1 ? "s" : ""} logged
          {plannedCount > 0 ? ` · ${plannedCount} planned` : ""}
          {timedSeconds > 0 ? ` · ${formatDuration(timedSeconds)} timed` : ""}
        </>
      }
      onBack={() => navigate("/")}
      emptyTitle="No workouts yet"
      emptyText="Start your training session by adding your first exercise"
    />
  );
};

export default WorkoutSession;
