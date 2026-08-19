import { useState, useEffect, useCallback } from "react";
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
  Minus,
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
  StretchHorizontal,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import {
  useWorkouts,
  useCreateWorkout,
  useUpdateWorkout,
  useDeleteWorkout,
  useBulkReorderWorkouts,
  useToggleComplete,
  useMoveToDate,
  useCopyToDate,
  useSetDayMobility,
} from "@/hooks/useWorkouts";
import type { Workout } from "@/types/workout";
import { useCategories, useExercises, useRecentExercises } from "@/hooks/useExercises";
import { useProgression } from "@/hooks/useProgression";
import type { WorkoutCreate } from "@/types/workout";

// Get weight increment based on current weight value
const getWeightIncrement = (weight: number): number => {
  if (weight < 100) return 2.5;
  if (weight <= 300) return 5;
  return 10;
};

// Sortable workout card component
interface SortableWorkoutCardProps {
  workout: Workout;
  index: number;
  editingWorkout: Workout | null;
  confirmingDelete: number | null;
  formData: WorkoutCreate;
  getCategoryColor: (category: string) => {
    bg: string;
    text: string;
    border: string;
  };
  handleEditWorkout: (workout: Workout) => void;
  toggleComplete: ReturnType<typeof useToggleComplete>;
  handleToggleMobility: (workout: Workout) => void;
  handleDeleteClick: (id: number) => void;
  handleDeleteConfirm: (id: number) => void;
  handleDeleteCancel: () => void;
  setFormData: React.Dispatch<React.SetStateAction<WorkoutCreate>>;
  handleSubmit: (e: React.FormEvent) => void;
  handleDuplicate: () => void;
  resetForm: () => void;
}

const SortableWorkoutCard = ({
  workout,
  index,
  editingWorkout,
  confirmingDelete,
  formData,
  getCategoryColor,
  handleEditWorkout,
  toggleComplete,
  handleToggleMobility,
  handleDeleteClick,
  handleDeleteConfirm,
  handleDeleteCancel,
  setFormData,
  handleSubmit,
  handleDuplicate,
  resetForm,
}: SortableWorkoutCardProps) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: workout.doc_id });

  const [showRecentWeights, setShowRecentWeights] = useState(false);
  const isEditing = editingWorkout?.doc_id === workout.doc_id;

  // Fetch progression data only when editing and toggle is on
  const { data: progressionData } = useProgression(
    isEditing && showRecentWeights ? workout.exercise : "",
    false,
  );

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    animationDelay: `${index * 50}ms`,
  };

  const catColor = getCategoryColor(workout.category);

  return (
    <Card ref={setNodeRef} style={style} className="card-hover animate-in">
      <CardContent className="set-row">
        {isEditing && (
          <button
            type="button"
            className="action-btn"
            onClick={(e) => {
              e.stopPropagation();
              resetForm();
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
            <X style={{ width: "20px", height: "20px" }} />
          </button>
        )}
        {!isEditing && (
          <div className="set-row__actions">
            {/* Completion checkbox */}
            <button
              className="action-btn"
              onClick={(e) => {
                e.stopPropagation();
                toggleComplete.mutate({
                  id: workout.doc_id,
                  completed: !workout.completed_at,
                });
              }}
              title={workout.completed_at ? "Mark incomplete" : "Mark complete"}
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
              style={{
                cursor: isDragging ? "grabbing" : "grab",
                touchAction: "none",
                padding: "4px",
              }}
              {...attributes}
              {...listeners}
            >
              <GripVertical className="set-row__icon" />
            </button>

            {/* Delete button */}
            {confirmingDelete === workout.doc_id ? (
              <div
                className="flex"
                style={{ gap: "4px", gridColumn: "1 / -1" }}
              >
                <button
                  className="action-btn action-btn--danger"
                  onClick={() => handleDeleteConfirm(workout.doc_id)}
                  title="Confirm delete"
                  style={{ padding: "4px" }}
                >
                  <Check className="set-row__icon" />
                </button>
                <button
                  className="action-btn"
                  onClick={handleDeleteCancel}
                  title="Cancel"
                  style={{ padding: "4px" }}
                >
                  <X className="set-row__icon" />
                </button>
              </div>
            ) : (
              <button
                className="action-btn action-btn--danger"
                onClick={() => handleDeleteClick(workout.doc_id)}
                style={{ padding: "4px" }}
              >
                <Trash2 className="set-row__icon" />
              </button>
            )}
          </div>
        )}

        {/* Main content - clickable area */}
        <div
          className="set-row__body log-line"
          onClick={() =>
            !editingWorkout || editingWorkout.doc_id !== workout.doc_id
              ? handleEditWorkout(workout)
              : undefined
          }
          style={{
            cursor:
              !editingWorkout || editingWorkout.doc_id !== workout.doc_id
                ? "pointer"
                : "default",
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
                    width: "14px",
                    height: "14px",
                    color: "var(--accent)",
                  }}
                />
                <span className="workout-chip__value" style={{ fontSize: "14px" }}>
                  {workout.weight} {workout.weight_unit}
                </span>
              </div>
            )}
            {workout.reps && (
              <div className="workout-chip">
                <Hash
                  style={{
                    width: "14px",
                    height: "14px",
                    color: "var(--accent)",
                  }}
                />
                <span className="workout-chip__value" style={{ fontSize: "14px" }}>
                  {workout.reps} reps
                </span>
              </div>
            )}
            {workout.comment && (
              <div className="workout-chip">
                <MessageSquare
                  style={{
                    width: "14px",
                    height: "14px",
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

        {/* Inline Edit Form */}
        {editingWorkout?.doc_id === workout.doc_id && (
          <div
            className="animate-in"
            style={{
              marginTop: "var(--space-5)",
              padding: "var(--space-5)",
              borderTop: "1px solid var(--border-subtle)",
              background:
                "linear-gradient(135deg, var(--accent-glow) 0%, transparent 100%)",
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
              <div
                className="grid grid-cols-1 md:grid-cols-2"
                style={{ gap: "var(--space-4)" }}
              >
                <div className="form-field">
                  <Label htmlFor="weight-edit" className="form-label">
                    <Weight style={{ width: "14px", height: "14px" }} />
                    Weight
                  </Label>
                  <div className="stepper">
                    <button
                      type="button"
                      className="stepper__btn stepper__btn--start"
                      onClick={() => {
                        const current = formData.weight || 0;
                        const increment = getWeightIncrement(current);
                        setFormData({
                          ...formData,
                          weight: Math.max(0, current - increment),
                        });
                      }}
                    >
                      <Minus style={{ width: "18px", height: "18px" }} />
                    </button>
                    <input
                      id="weight-edit"
                      type="number"
                      inputMode="decimal"
                      step="0.1"
                      placeholder="0"
                      className="input--stepper"
                      value={formData.weight || ""}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setFormData({
                          ...formData,
                          weight: e.target.value
                            ? parseFloat(e.target.value)
                            : null,
                        })
                      }
                    />
                    <button
                      type="button"
                      className="stepper__btn stepper__btn--end"
                      onClick={() => {
                        const current = formData.weight || 0;
                        const increment = getWeightIncrement(current);
                        setFormData({
                          ...formData,
                          weight: current + increment,
                        });
                      }}
                    >
                      <Plus style={{ width: "18px", height: "18px" }} />
                    </button>
                    <span className="stepper__unit">
                      {formData.weight_unit || "lbs"}
                    </span>
                  </div>
                </div>

                <div className="form-field">
                  <Label htmlFor="reps-edit" className="form-label">
                    <Hash style={{ width: "14px", height: "14px" }} />
                    Reps
                  </Label>
                  <div className="stepper">
                    <button
                      type="button"
                      className="stepper__btn stepper__btn--start"
                      onClick={() => {
                        const currentReps = formData.reps || 0;
                        const newValue = Math.max(0, currentReps - 1);
                        setFormData({
                          ...formData,
                          reps: newValue > 0 ? newValue : null,
                        });
                      }}
                    >
                      <Minus style={{ width: "18px", height: "18px" }} />
                    </button>
                    <input
                      id="reps-edit"
                      type="number"
                      inputMode="numeric"
                      placeholder="e.g., 5"
                      className="input--stepper input--mono"
                      value={formData.reps || ""}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                        const value = e.target.value ? parseInt(e.target.value) : null;
                        setFormData({
                          ...formData,
                          reps: value,
                        });
                      }}
                    />
                    <button
                      type="button"
                      className="stepper__btn stepper__btn--end"
                      onClick={() => {
                        const currentReps = formData.reps || 0;
                        const newValue = currentReps + 1;
                        setFormData({
                          ...formData,
                          reps: newValue,
                        });
                      }}
                    >
                      <Plus style={{ width: "18px", height: "18px" }} />
                    </button>
                  </div>
                </div>
              </div>

              <div className="form-field">
                <Label htmlFor="comment-edit" className="form-label">
                  <MessageSquare style={{ width: "14px", height: "14px" }} />
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
                  <History style={{ width: "18px", height: "18px" }} />
                  Recent
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleDuplicate}
                  className="w-full justify-center"
                >
                  <Copy style={{ width: "18px", height: "18px" }} />
                  Duplicate
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={resetForm}
                  className="w-full justify-center"
                >
                  <X style={{ width: "18px", height: "18px" }} />
                  Cancel
                </Button>
                <Button type="submit" className="w-full justify-center">
                  <Check style={{ width: "18px", height: "18px" }} />
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
                              transition: "all 0.15s ease",
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
                      fontStyle: "italic",
                    }}
                  >
                    No previous entries for this exercise
                  </p>
                )}
            </form>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const WorkoutSession = () => {
  const { date } = useParams<{ date: string }>();
  const navigate = useNavigate();

  const { data: workouts, isLoading } = useWorkouts({ date });
  const { data: categories } = useCategories();
  const { data: exercises } = useExercises();
  const { data: recentExercises } = useRecentExercises(8);

  const createWorkout = useCreateWorkout();
  const updateWorkout = useUpdateWorkout();
  const deleteWorkout = useDeleteWorkout();
  const bulkReorderWorkouts = useBulkReorderWorkouts();
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
  const [editingWorkout, setEditingWorkout] = useState<Workout | null>(null);
  const [selectedCategory, setSelectedCategory] = useState("");
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

  const handleCategoryChange = (category: string) => {
    setSelectedCategory(category);
    setFormData({ ...formData, category });
  };

  const handleExerciseChange = (exercise: string) => {
    const exerciseData = exercises?.find((e) => e.name === exercise);
    setSelectedExercise(exercise);
    setFormData({
      ...formData,
      exercise,
      category: exerciseData?.category || formData.category,
    });
  };

  const handleEditWorkout = (workout: Workout) => {
    setEditingWorkout(workout);

    // Look up the exercise's actual category (in case workout data is stale)
    const exerciseData = exercises?.find((e) => e.name === workout.exercise);
    const actualCategory = exerciseData?.category || workout.category;

    setSelectedCategory(actualCategory);
    setSelectedExercise(workout.exercise);
    setFormData({
      date: workout.date,
      exercise: workout.exercise,
      category: actualCategory,
      weight: workout.weight,
      weight_unit: workout.weight_unit || "lbs",
      reps: workout.reps,
      distance: workout.distance,
      distance_unit: workout.distance_unit,
      time: workout.time,
      comment: workout.comment,
    });
    // Don't show the top form when editing
    setShowForm(false);
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
    });
    setSelectedCategory("");
    setSelectedExercise("");
    setEditingWorkout(null);
    setShowForm(false);
    setShowAddRecent(false);
  }, [date]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.exercise || !formData.category) {
      return;
    }

    if (editingWorkout) {
      await updateWorkout.mutateAsync({
        id: editingWorkout.doc_id,
        workout: formData,
      });
    } else {
      await createWorkout.mutateAsync(formData);
    }

    resetForm();
  };

  // Sync exercise selection when editing and exercises data is available
  const [lastSyncedEdit, setLastSyncedEdit] = useState<number | null>(null);
  if (editingWorkout && exercises && lastSyncedEdit !== editingWorkout.doc_id) {
    const exerciseData = exercises.find(
      (e) => e.name === editingWorkout.exercise,
    );
    if (exerciseData) {
      setSelectedCategory(exerciseData.category);
      setSelectedExercise(editingWorkout.exercise);
      setLastSyncedEdit(editingWorkout.doc_id);
    }
  }
  if (!editingWorkout && lastSyncedEdit !== null) {
    setLastSyncedEdit(null);
  }

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

  const handleDeleteConfirm = useCallback(
    async (id: number) => {
      await deleteWorkout.mutateAsync(id);
      setConfirmingDelete(null);
    },
    [deleteWorkout],
  );

  const handleDeleteCancel = useCallback(() => {
    setConfirmingDelete(null);
  }, []);

  const handleDuplicate = useCallback(async () => {
    if (!formData.exercise || !formData.category || !date) return;

    await createWorkout.mutateAsync({
      ...formData,
      date,
    });
    resetForm();
  }, [formData, date, createWorkout, resetForm]);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;

      if (over && active.id !== over.id && workouts) {
        const sortedWorkouts = [...workouts].sort((a, b) => a.order - b.order);
        const oldIndex = sortedWorkouts.findIndex(
          (w) => w.doc_id === active.id,
        );
        const newIndex = sortedWorkouts.findIndex((w) => w.doc_id === over.id);

        if (oldIndex !== -1 && newIndex !== -1) {
          const reordered = arrayMove(sortedWorkouts, oldIndex, newIndex);
          const workoutIds = reordered.map((w) => w.doc_id);
          bulkReorderWorkouts.mutate(workoutIds);
        }
      }
    },
    [workouts, bulkReorderWorkouts],
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
  const handleToggleMobility = useCallback(
    (workout: Workout) => {
      updateWorkout.mutate({
        id: workout.doc_id,
        workout: {
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
        },
      });
    },
    [updateWorkout],
  );

  // Progression data for add form's selected exercise
  const { data: addFormProgression } = useProgression(
    showAddRecent && selectedExercise && !editingWorkout ? selectedExercise : "",
    false,
  );

  const categoryExercises =
    exercises?.filter((e) => e.category === selectedCategory) || [];
  const formattedDate = date ? format(parseISO(date), "MMMM d, yyyy") : "";

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

  return (
    <>
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
                onClick={() => navigate("/")}
                className="icon-btn"
              >
                <ArrowLeft style={{ width: "20px", height: "20px" }} />
              </Button>
              <div>
                <h1 className="page__title page__title--compact">
                  {formattedDate.toUpperCase()}
                </h1>
                <p className="page__subtitle">
                  {workouts?.length || 0} exercise
                  {workouts?.length !== 1 ? "s" : ""} logged
                </p>
              </div>
            </div>

            <div className="flex flex-wrap" style={{ gap: "var(--space-2)" }}>
              {workouts && workouts.length > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowMoveCalendar(!showMoveCalendar)}
                >
                  <CalendarIcon style={{ width: "16px", height: "16px" }} />
                  Move
                </Button>
              )}
              {workouts && workouts.length > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowCopyCalendar(!showCopyCalendar)}
                >
                  <Copy style={{ width: "16px", height: "16px" }} />
                  Copy
                </Button>
              )}
              {workouts && workouts.length > 0 && (
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
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
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
                    <ArrowRight style={{ width: "18px", height: "18px" }} />
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
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
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
                    <Copy style={{ width: "18px", height: "18px" }} />
                    Copy to{" "}
                    {copyTargetDate && format(copyTargetDate, "MMM d, yyyy")}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Add Exercise Form - Only show at top for new exercises */}
          {showForm && !editingWorkout && (
            <Card
              className="animate-in"
              style={{
                marginBottom: "var(--space-6)",
                border: "1px solid var(--accent-muted)",
                boxShadow: "0 0 20px var(--accent-glow)",
              }}
            >
              <CardHeader
                className="flex items-center"
                style={{
                  background:
                    "linear-gradient(135deg, var(--accent-glow) 0%, transparent 100%)",
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
                  {editingWorkout ? (
                    <Pencil
                      style={{
                        width: "20px",
                        height: "20px",
                        color: "var(--accent)",
                      }}
                    />
                  ) : (
                    <Dumbbell
                      style={{
                        width: "20px",
                        height: "20px",
                        color: "var(--accent)",
                      }}
                    />
                  )}
                  {editingWorkout ? "EDIT EXERCISE" : "ADD EXERCISE"}
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
                  <X style={{ width: "20px", height: "20px" }} />
                </button>
              </CardHeader>
              <CardContent style={{ padding: "var(--space-6)" }}>
                {/* Recent Exercises */}
                {recentExercises && recentExercises.length > 0 && (
                  <div style={{ marginBottom: "var(--space-6)" }}>
                    <Label className="form-label" style={{ marginBottom: "var(--space-3)" }}>
                      <History style={{ width: "14px", height: "14px" }} />
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
                              setSelectedCategory(ex.category);
                              setSelectedExercise(ex.name);
                              setFormData({
                                ...formData,
                                exercise: ex.name,
                                category: ex.category,
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
                              transition: "all 0.15s ease",
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
                  <div
                    className="grid grid-cols-1 md:grid-cols-2"
                    style={{ gap: "var(--space-6)" }}
                  >
                    <div className="form-field">
                      <Label htmlFor="category" className="form-label">
                        <Hash style={{ width: "14px", height: "14px" }} />
                        Category
                      </Label>
                      <Select
                        value={selectedCategory}
                        onValueChange={handleCategoryChange}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select category" />
                        </SelectTrigger>
                        <SelectContent>
                          {categories?.map((cat) => (
                            <SelectItem key={cat.doc_id} value={cat.name}>
                              {cat.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="form-field">
                      <Label htmlFor="exercise" className="form-label">
                        <Dumbbell style={{ width: "14px", height: "14px" }} />
                        Exercise
                      </Label>
                      <Select
                        key={selectedCategory}
                        value={
                          categoryExercises.some(
                            (e) => e.name === selectedExercise,
                          )
                            ? selectedExercise
                            : undefined
                        }
                        onValueChange={handleExerciseChange}
                        disabled={!selectedCategory}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select exercise" />
                        </SelectTrigger>
                        <SelectContent>
                          {categoryExercises.map((ex) => (
                            <SelectItem key={ex.doc_id} value={ex.name}>
                              {ex.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="form-field">
                    <Label htmlFor="weight" className="form-label">
                      <Weight style={{ width: "14px", height: "14px" }} />
                      Weight
                    </Label>
                    <div className="stepper">
                      <button
                        type="button"
                        className="stepper__btn stepper__btn--start"
                        onClick={() => {
                          const current = formData.weight || 0;
                          const increment = getWeightIncrement(current);
                          setFormData({
                            ...formData,
                            weight: Math.max(0, current - increment),
                          });
                        }}
                      >
                        <Minus style={{ width: "18px", height: "18px" }} />
                      </button>
                      <input
                        id="weight"
                        type="number"
                        inputMode="decimal"
                        step="0.1"
                        placeholder="0"
                        className="input--stepper"
                        value={formData.weight || ""}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setFormData({
                            ...formData,
                            weight: e.target.value
                              ? parseFloat(e.target.value)
                              : null,
                          })
                        }
                      />
                      <button
                        type="button"
                        className="stepper__btn stepper__btn--end"
                        onClick={() => {
                          const current = formData.weight || 0;
                          const increment = getWeightIncrement(current);
                          setFormData({
                            ...formData,
                            weight: current + increment,
                          });
                        }}
                      >
                        <Plus style={{ width: "18px", height: "18px" }} />
                      </button>
                      <span className="stepper__unit">
                        {formData.weight_unit || "lbs"}
                      </span>
                    </div>
                  </div>

                  <div className="form-field">
                    <Label htmlFor="reps" className="form-label">
                      <Hash style={{ width: "14px", height: "14px" }} />
                      Reps
                    </Label>
                    <div className="stepper">
                      <button
                        type="button"
                        className="stepper__btn stepper__btn--start"
                        onClick={() => {
                          const currentReps = formData.reps || 0;
                          const newValue = Math.max(0, currentReps - 1);
                          setFormData({
                            ...formData,
                            reps: newValue > 0 ? newValue : null,
                          });
                        }}
                      >
                        <Minus style={{ width: "18px", height: "18px" }} />
                      </button>
                      <input
                        id="reps"
                        type="number"
                        inputMode="numeric"
                        placeholder="e.g., 5"
                        className="input--stepper input--mono"
                        value={formData.reps || ""}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                          const value = e.target.value ? parseInt(e.target.value) : null;
                          setFormData({
                            ...formData,
                            reps: value,
                          });
                        }}
                      />
                      <button
                        type="button"
                        className="stepper__btn stepper__btn--end"
                        onClick={() => {
                          const currentReps = formData.reps || 0;
                          const newValue = currentReps + 1;
                          setFormData({
                            ...formData,
                            reps: newValue,
                          });
                        }}
                      >
                        <Plus style={{ width: "18px", height: "18px" }} />
                      </button>
                    </div>
                  </div>

                  <div className="form-field" style={{ overflow: "hidden" }}>
                    <Label htmlFor="comment" className="form-label">
                      <MessageSquare
                        style={{ width: "14px", height: "14px" }}
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
                        <History style={{ width: "18px", height: "18px" }} />
                        Recent
                      </Button>
                    )}
                    <Button
                      type="submit"
                      disabled={!formData.exercise || !formData.category}
                    >
                      {editingWorkout ? (
                        <Pencil style={{ width: "20px", height: "20px" }} />
                      ) : (
                        <Plus style={{ width: "20px", height: "20px" }} />
                      )}
                      {editingWorkout ? "Save" : "Add Workout"}
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
                                  transition: "all 0.15s ease",
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
                          fontStyle: "italic",
                        }}
                      >
                        No previous entries for this exercise
                      </p>
                    )}
                </form>
              </CardContent>
            </Card>
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
                items={workouts
                  .sort((a, b) => a.order - b.order)
                  .map((w) => w.doc_id)}
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
                  {workouts
                    .sort((a, b) => a.order - b.order)
                    .map((workout, index) => (
                      <SortableWorkoutCard
                        key={workout.doc_id}
                        workout={workout}
                        index={index}
                        editingWorkout={editingWorkout}
                        confirmingDelete={confirmingDelete}
                        formData={formData}
                        getCategoryColor={getCategoryColor}
                        handleEditWorkout={handleEditWorkout}
                        toggleComplete={toggleComplete}
                        handleToggleMobility={handleToggleMobility}
                        handleDeleteClick={handleDeleteClick}
                        handleDeleteConfirm={handleDeleteConfirm}
                        handleDeleteCancel={handleDeleteCancel}
                        setFormData={setFormData}
                        handleSubmit={handleSubmit}
                        handleDuplicate={handleDuplicate}
                        resetForm={resetForm}
                      />
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
                <h3 className="empty-state__title">NO WORKOUTS YET</h3>
                <p className="empty-state__text">
                  Start your training session by adding your first exercise
                </p>
                <Button onClick={() => setShowForm(true)}>
                  <Plus style={{ width: "20px", height: "20px" }} />
                  Add Your First Exercise
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
};

export default WorkoutSession;
