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
} from "@/hooks/useWorkouts";
import type { Workout } from "@/types/workout";
import { useCategories, useExercises } from "@/hooks/useExercises";
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
    getCategoryColor: (category: string) => { bg: string; text: string; border: string };
    handleEditWorkout: (workout: Workout) => void;
    toggleComplete: ReturnType<typeof useToggleComplete>;
    handleDeleteClick: (id: number) => void;
    handleDeleteConfirm: (id: number) => void;
    handleDeleteCancel: () => void;
    setFormData: React.Dispatch<React.SetStateAction<WorkoutCreate>>;
    handleSubmit: (e: React.FormEvent) => void;
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
    handleDeleteClick,
    handleDeleteConfirm,
    handleDeleteCancel,
    setFormData,
    handleSubmit,
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
        false
    );

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        animationDelay: `${index * 50}ms`,
    };

    const catColor = getCategoryColor(workout.category);

    return (
        <Card
            ref={setNodeRef}
            style={style}
            className="card-hover animate-in"
        >
            <CardContent style={{ padding: 'var(--space-5)' }}>
                <div className="flex items-start justify-between" style={{ gap: 'var(--space-4)' }}>
                    {/* Drag handle */}
                    <button
                        className="action-btn drag-handle"
                        style={{
                            cursor: isDragging ? 'grabbing' : 'grab',
                            touchAction: 'none',
                        }}
                        {...attributes}
                        {...listeners}
                    >
                        <GripVertical style={{ width: '20px', height: '20px' }} />
                    </button>

                    <div
                        className="flex-1"
                        onClick={() => !editingWorkout || editingWorkout.doc_id !== workout.doc_id ? handleEditWorkout(workout) : undefined}
                        style={{ cursor: !editingWorkout || editingWorkout.doc_id !== workout.doc_id ? 'pointer' : 'default' }}
                    >
                        <div className="flex items-start" style={{ gap: 'var(--space-3)' }}>
                            <button
                                className="workout-checkbox"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    toggleComplete.mutate({
                                        id: workout.doc_id,
                                        completed: !workout.completed_at
                                    });
                                }}
                                title={workout.completed_at ? "Mark incomplete" : "Mark complete"}
                                style={{
                                    color: workout.completed_at ? 'var(--accent)' : 'var(--text-muted)',
                                    opacity: workout.completed_at ? 1 : 0.5,
                                }}
                            >
                                {workout.completed_at ? (
                                    <CheckCircle2 style={{ width: '24px', height: '24px' }} />
                                ) : (
                                    <Circle style={{ width: '24px', height: '24px' }} />
                                )}
                            </button>
                            <div className="workout-order">
                                {index + 1}
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center flex-wrap" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
                                    <h3
                                        style={{
                                            fontFamily: 'var(--font-body)',
                                            fontSize: '18px',
                                            fontWeight: 600,
                                            color: 'var(--text-primary)',
                                        }}
                                    >
                                        {workout.exercise}
                                    </h3>
                                    <span
                                        className="category-badge"
                                        style={{
                                            border: `1px solid ${catColor.border}`,
                                            color: catColor.text,
                                            background: `${catColor.bg}20`,
                                        }}
                                    >
                                        {workout.category}
                                    </span>
                                </div>
                                <div className="flex flex-wrap" style={{ gap: 'var(--space-3)' }}>
                                    {workout.weight && (
                                        <div className="workout-chip">
                                            <Weight style={{ width: '16px', height: '16px', color: 'var(--accent)' }} />
                                            <span className="workout-chip__value">
                                                {workout.weight} {workout.weight_unit}
                                            </span>
                                        </div>
                                    )}
                                    {workout.reps && (
                                        <div className="workout-chip">
                                            <Hash style={{ width: '16px', height: '16px', color: 'var(--accent)' }} />
                                            <span className="workout-chip__value">
                                                {workout.reps} reps
                                            </span>
                                        </div>
                                    )}
                                    {workout.comment && (
                                        <div className="workout-chip">
                                            <MessageSquare style={{ width: '16px', height: '16px', color: 'var(--text-muted)' }} />
                                            <span className="workout-chip__comment">
                                                {workout.comment}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="flex flex-col" style={{ gap: 'var(--space-1)' }}>
                        {confirmingDelete === workout.doc_id ? (
                            <div className="flex" style={{ gap: '2px' }}>
                                <button
                                    className="action-btn action-btn--danger"
                                    onClick={() => handleDeleteConfirm(workout.doc_id)}
                                    title="Confirm delete"
                                >
                                    <Check style={{ width: '18px', height: '18px' }} />
                                </button>
                                <button
                                    className="action-btn"
                                    onClick={handleDeleteCancel}
                                    title="Cancel"
                                >
                                    <X style={{ width: '18px', height: '18px' }} />
                                </button>
                            </div>
                        ) : (
                            <button
                                className="action-btn action-btn--danger"
                                onClick={() => handleDeleteClick(workout.doc_id)}
                            >
                                <Trash2 style={{ width: '18px', height: '18px' }} />
                            </button>
                        )}
                    </div>
                </div>

                {/* Inline Edit Form */}
                {editingWorkout?.doc_id === workout.doc_id && (
                    <div
                        className="animate-in"
                        style={{
                            marginTop: 'var(--space-5)',
                            padding: 'var(--space-5)',
                            borderTop: '1px solid var(--border-subtle)',
                            background: 'linear-gradient(135deg, var(--accent-glow) 0%, transparent 100%)',
                            borderRadius: 'var(--radius-md)',
                        }}
                    >
                        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                            <div className="grid grid-cols-1 md:grid-cols-2" style={{ gap: 'var(--space-4)' }}>
                                <div className="form-field">
                                    <Label htmlFor="weight-edit" className="form-label">
                                        <Weight style={{ width: '14px', height: '14px' }} />
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
                                            <Minus style={{ width: '18px', height: '18px' }} />
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
                                                    weight: e.target.value ? parseFloat(e.target.value) : null,
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
                                            <Plus style={{ width: '18px', height: '18px' }} />
                                        </button>
                                        <span className="stepper__unit">{formData.weight_unit || 'lbs'}</span>
                                    </div>
                                </div>

                                <div className="form-field">
                                    <Label htmlFor="reps-edit" className="form-label">
                                        <Hash style={{ width: '14px', height: '14px' }} />
                                        Reps
                                    </Label>
                                    <Input
                                        id="reps-edit"
                                        type="text"
                                        inputMode="numeric"
                                        placeholder="e.g., 5 or 5+"
                                        className="input--mono"
                                        value={formData.reps || ""}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                            setFormData({
                                                ...formData,
                                                reps: e.target.value || null,
                                            })
                                        }
                                    />
                                </div>
                            </div>

                            <div className="form-field">
                                <Label htmlFor="comment-edit" className="form-label">
                                    <MessageSquare style={{ width: '14px', height: '14px' }} />
                                    Comment
                                </Label>
                                <Input
                                    id="comment-edit"
                                    type="text"
                                    placeholder="Optional note"
                                    value={formData.comment || ""}
                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                        setFormData({
                                            ...formData,
                                            comment: e.target.value || null,
                                        })
                                    }
                                />
                            </div>

                            {/* Recent Weights Toggle */}
                            <div>
                                <button
                                    type="button"
                                    onClick={() => setShowRecentWeights(!showRecentWeights)}
                                    className="flex items-center"
                                    style={{
                                        gap: 'var(--space-2)',
                                        padding: 'var(--space-2) var(--space-3)',
                                        background: showRecentWeights ? 'var(--accent-glow)' : 'var(--bg-secondary)',
                                        border: `1px solid ${showRecentWeights ? 'var(--accent-muted)' : 'var(--border)'}`,
                                        borderRadius: 'var(--radius-sm)',
                                        color: showRecentWeights ? 'var(--accent)' : 'var(--text-secondary)',
                                        fontSize: '13px',
                                        fontFamily: 'var(--font-body)',
                                        cursor: 'pointer',
                                        transition: 'all 0.15s ease',
                                    }}
                                >
                                    <History style={{ width: '14px', height: '14px' }} />
                                    Recent weights
                                </button>

                                {showRecentWeights && progressionData?.historical && progressionData.historical.length > 0 && (
                                    <div
                                        style={{
                                            marginTop: 'var(--space-3)',
                                            padding: 'var(--space-3)',
                                            background: 'var(--bg-secondary)',
                                            borderRadius: 'var(--radius-sm)',
                                            border: '1px solid var(--border)',
                                        }}
                                    >
                                        <div
                                            style={{
                                                display: 'flex',
                                                flexDirection: 'column',
                                                gap: 'var(--space-2)',
                                                maxHeight: '150px',
                                                overflowY: 'auto',
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
                                                            display: 'flex',
                                                            justifyContent: 'space-between',
                                                            alignItems: 'center',
                                                            padding: 'var(--space-2)',
                                                            background: 'var(--bg-tertiary)',
                                                            border: '1px solid var(--border-subtle)',
                                                            borderRadius: 'var(--radius-sm)',
                                                            cursor: 'pointer',
                                                            transition: 'all 0.15s ease',
                                                            textAlign: 'left',
                                                        }}
                                                        onMouseOver={(e) => {
                                                            e.currentTarget.style.background = 'var(--bg-hover)';
                                                            e.currentTarget.style.borderColor = 'var(--accent-muted)';
                                                        }}
                                                        onMouseOut={(e) => {
                                                            e.currentTarget.style.background = 'var(--bg-tertiary)';
                                                            e.currentTarget.style.borderColor = 'var(--border-subtle)';
                                                        }}
                                                    >
                                                        <span
                                                            style={{
                                                                fontFamily: 'var(--font-mono)',
                                                                fontSize: '13px',
                                                                color: 'var(--text-primary)',
                                                            }}
                                                        >
                                                            {entry.weight} {entry.weight_unit} × {entry.reps}
                                                        </span>
                                                        <span
                                                            style={{
                                                                fontSize: '12px',
                                                                color: 'var(--text-muted)',
                                                            }}
                                                        >
                                                            {entry.date}
                                                        </span>
                                                    </button>
                                                ))}
                                        </div>
                                    </div>
                                )}

                                {showRecentWeights && (!progressionData?.historical || progressionData.historical.length === 0) && (
                                    <p
                                        style={{
                                            marginTop: 'var(--space-3)',
                                            fontSize: '13px',
                                            color: 'var(--text-muted)',
                                            fontStyle: 'italic',
                                        }}
                                    >
                                        No previous entries for this exercise
                                    </p>
                                )}
                            </div>

                            <div className="flex justify-end" style={{ gap: 'var(--space-3)' }}>
                                <Button
                                    type="button"
                                    variant="secondary"
                                    onClick={resetForm}
                                >
                                    <X style={{ width: '18px', height: '18px' }} />
                                    Cancel
                                </Button>
                                <Button type="submit">
                                    <Check style={{ width: '18px', height: '18px' }} />
                                    Save Changes
                                </Button>
                            </div>
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

    const createWorkout = useCreateWorkout();
    const updateWorkout = useUpdateWorkout();
    const deleteWorkout = useDeleteWorkout();
    const bulkReorderWorkouts = useBulkReorderWorkouts();
    const toggleComplete = useToggleComplete();
    const moveToDate = useMoveToDate();

    // Drag and drop sensors
    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: {
                distance: 8,
            },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    const [showForm, setShowForm] = useState(false);
    const [editingWorkout, setEditingWorkout] = useState<Workout | null>(null);
    const [selectedCategory, setSelectedCategory] = useState("");
    const [selectedExercise, setSelectedExercise] = useState("");
    const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
    const [showMoveCalendar, setShowMoveCalendar] = useState(false);
    const [targetDate, setTargetDate] = useState<Date | undefined>(new Date());
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

    const resetForm = () => {
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
    };

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
    useEffect(() => {
        if (editingWorkout && exercises) {
            // Look up the exercise's actual category
            const exerciseData = exercises.find(e => e.name === editingWorkout.exercise);
            if (exerciseData) {
                const actualCategory = exerciseData.category;
                if (selectedCategory !== actualCategory) {
                    setSelectedCategory(actualCategory);
                }
                if (selectedExercise !== editingWorkout.exercise) {
                    setSelectedExercise(editingWorkout.exercise);
                }
            }
        }
    }, [editingWorkout, exercises, selectedCategory, selectedExercise]);

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

    const handleDeleteConfirm = useCallback(async (id: number) => {
        await deleteWorkout.mutateAsync(id);
        setConfirmingDelete(null);
    }, [deleteWorkout]);

    const handleDeleteCancel = useCallback(() => {
        setConfirmingDelete(null);
    }, []);

    const handleDragEnd = useCallback(
        (event: DragEndEvent) => {
            const { active, over } = event;

            if (over && active.id !== over.id && workouts) {
                const sortedWorkouts = [...workouts].sort((a, b) => a.order - b.order);
                const oldIndex = sortedWorkouts.findIndex((w) => w.doc_id === active.id);
                const newIndex = sortedWorkouts.findIndex((w) => w.doc_id === over.id);

                if (oldIndex !== -1 && newIndex !== -1) {
                    const reordered = arrayMove(sortedWorkouts, oldIndex, newIndex);
                    const workoutIds = reordered.map((w) => w.doc_id);
                    bulkReorderWorkouts.mutate(workoutIds);
                }
            }
        },
        [workouts, bulkReorderWorkouts]
    );

    const handleMoveToDate = useCallback(async () => {
        if (!date || !targetDate) return;
        const targetDateStr = format(targetDate, "yyyy-MM-dd");
        await moveToDate.mutateAsync({ sourceDate: date, targetDate: targetDateStr });
        setShowMoveCalendar(false);
        navigate(`/workout/${targetDateStr}`);
    }, [date, targetDate, moveToDate, navigate]);

    const categoryExercises =
        exercises?.filter((e) => e.category === selectedCategory) || [];
    const formattedDate = date ? format(parseISO(date), "MMMM d, yyyy") : "";

    const getCategoryColor = (category: string) => {
        // Predefined colors for common categories
        const predefined: Record<string, string> = {
            Push: 'var(--chart-2)',    // Blue
            Pull: 'var(--accent)',      // Green
            Legs: 'var(--chart-3)',     // Purple
            Core: 'var(--chart-4)',     // Orange
            Cardio: 'var(--error)',     // Red
        };

        // Color palette for hash-based assignment
        const palette = [
            'var(--chart-1)',  // Green
            'var(--chart-2)',  // Blue
            'var(--chart-3)',  // Purple
            'var(--chart-4)',  // Orange
            'var(--chart-5)',  // Yellow
            'var(--info)',     // Light blue
            'var(--error)',    // Red
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
                <div className="page__content">
                {/* Header */}
                <div
                    className="flex flex-col sm:flex-row sm:items-center justify-between animate-in"
                    style={{ gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}
                >
                    <div className="flex items-center" style={{ gap: 'var(--space-4)' }}>
                        <Button
                            variant="secondary"
                            size="icon"
                            onClick={() => navigate("/")}
                            className="icon-btn"
                        >
                            <ArrowLeft style={{ width: '20px', height: '20px' }} />
                        </Button>
                        <div>
                            <h1 className="page__title page__title--compact">
                                {formattedDate.toUpperCase()}
                            </h1>
                            <p className="page__subtitle">
                                {workouts?.length || 0} exercise{workouts?.length !== 1 ? "s" : ""} logged
                            </p>
                        </div>
                    </div>

                    <div className="flex" style={{ gap: 'var(--space-2)' }}>
                        {workouts && workouts.length > 0 && (
                            <Button
                                variant="secondary"
                                onClick={() => setShowMoveCalendar(!showMoveCalendar)}
                            >
                                <CalendarIcon style={{ width: '18px', height: '18px' }} />
                                Move All
                            </Button>
                        )}
                        <Button
                            onClick={() => {
                                if (showForm) {
                                    resetForm();
                                } else {
                                    setShowForm(true);
                                }
                            }}
                        >
                            <Plus style={{ width: '20px', height: '20px' }} />
                            Add Exercise
                        </Button>
                    </div>
                </div>

                {/* Move to Date Calendar */}
                {showMoveCalendar && (
                    <Card
                        className="animate-in"
                        style={{
                            marginBottom: 'var(--space-6)',
                            border: '1px solid var(--border)',
                        }}
                    >
                        <CardContent style={{ padding: 'var(--space-5)' }}>
                            <p
                                style={{
                                    fontFamily: 'var(--font-display)',
                                    fontSize: '14px',
                                    color: 'var(--text-secondary)',
                                    marginBottom: 'var(--space-4)',
                                    textTransform: 'uppercase',
                                    letterSpacing: '0.05em',
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
                            <div className="flex justify-end" style={{ marginTop: 'var(--space-4)', gap: 'var(--space-2)' }}>
                                <Button
                                    variant="secondary"
                                    onClick={() => setShowMoveCalendar(false)}
                                >
                                    Cancel
                                </Button>
                                <Button
                                    onClick={handleMoveToDate}
                                    disabled={!targetDate || format(targetDate, "yyyy-MM-dd") === date}
                                >
                                    <ArrowRight style={{ width: '18px', height: '18px' }} />
                                    Move to {targetDate && format(targetDate, "MMM d, yyyy")}
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
                            marginBottom: 'var(--space-6)',
                            border: '1px solid var(--accent-muted)',
                            boxShadow: '0 0 20px var(--accent-glow)',
                        }}
                    >
                        <CardHeader
                            style={{
                                background: 'linear-gradient(135deg, var(--accent-glow) 0%, transparent 100%)',
                                borderBottom: '1px solid var(--border-subtle)',
                            }}
                        >
                            <CardTitle
                                className="flex items-center"
                                style={{ gap: 'var(--space-2)', fontFamily: 'var(--font-display)', fontSize: '18px' }}
                            >
                                {editingWorkout ? (
                                    <Pencil style={{ width: '20px', height: '20px', color: 'var(--accent)' }} />
                                ) : (
                                    <Dumbbell style={{ width: '20px', height: '20px', color: 'var(--accent)' }} />
                                )}
                                {editingWorkout ? 'EDIT EXERCISE' : 'ADD EXERCISE'}
                            </CardTitle>
                        </CardHeader>
                        <CardContent style={{ padding: 'var(--space-6)' }}>
                            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
                                <div className="grid grid-cols-1 md:grid-cols-2" style={{ gap: 'var(--space-6)' }}>
                                    <div className="form-field">
                                        <Label htmlFor="category" className="form-label">
                                            <Hash style={{ width: '14px', height: '14px' }} />
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
                                                    <SelectItem
                                                        key={cat.doc_id}
                                                        value={cat.name}
                                                    >
                                                        {cat.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <div className="form-field">
                                        <Label htmlFor="exercise" className="form-label">
                                            <Dumbbell style={{ width: '14px', height: '14px' }} />
                                            Exercise
                                        </Label>
                                        <Select
                                            key={selectedCategory}
                                            value={categoryExercises.some(e => e.name === selectedExercise) ? selectedExercise : undefined}
                                            onValueChange={handleExerciseChange}
                                            disabled={!selectedCategory}
                                        >
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select exercise" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {categoryExercises.map((ex) => (
                                                    <SelectItem
                                                        key={ex.doc_id}
                                                        value={ex.name}
                                                    >
                                                        {ex.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="form-field">
                                    <Label htmlFor="weight" className="form-label">
                                        <Weight style={{ width: '14px', height: '14px' }} />
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
                                            <Minus style={{ width: '18px', height: '18px' }} />
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
                                                    weight: e.target.value ? parseFloat(e.target.value) : null,
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
                                            <Plus style={{ width: '18px', height: '18px' }} />
                                        </button>
                                        <span className="stepper__unit">{formData.weight_unit || 'lbs'}</span>
                                    </div>
                                </div>

                                <div className="form-field">
                                    <Label htmlFor="reps" className="form-label">
                                        <Hash style={{ width: '14px', height: '14px' }} />
                                        Reps
                                    </Label>
                                    <Input
                                        id="reps"
                                        type="text"
                                        inputMode="numeric"
                                        placeholder="e.g., 5 or 5+"
                                        className="input--mono"
                                        value={formData.reps || ""}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                            setFormData({
                                                ...formData,
                                                reps: e.target.value || null,
                                            })
                                        }
                                    />
                                </div>

                                <div className="form-field" style={{ overflow: 'hidden' }}>
                                    <Label htmlFor="comment" className="form-label">
                                        <MessageSquare style={{ width: '14px', height: '14px' }} />
                                        Comment
                                    </Label>
                                    <Input
                                        id="comment"
                                        type="text"
                                        placeholder="Optional note"
                                        value={formData.comment || ""}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                            setFormData({
                                                ...formData,
                                                comment: e.target.value || null,
                                            })
                                        }
                                    />
                                </div>

                                <div className="flex justify-end" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-4)' }}>
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        onClick={resetForm}
                                    >
                                        Cancel
                                    </Button>
                                    <Button
                                        type="submit"
                                        disabled={
                                            !formData.exercise ||
                                            !formData.category
                                        }
                                    >
                                        {editingWorkout ? (
                                            <Pencil style={{ width: '20px', height: '20px' }} />
                                        ) : (
                                            <Plus style={{ width: '20px', height: '20px' }} />
                                        )}
                                        {editingWorkout ? 'Save Changes' : 'Add Workout'}
                                    </Button>
                                </div>
                            </form>
                        </CardContent>
                    </Card>
                )}

                {/* Workout List */}
                {isLoading ? (
                    <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
                        <div className="loading-spinner inline-block" />
                        <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
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
                            items={workouts.sort((a, b) => a.order - b.order).map((w) => w.doc_id)}
                            strategy={verticalListSortingStrategy}
                        >
                            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
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
                                            handleDeleteClick={handleDeleteClick}
                                            handleDeleteConfirm={handleDeleteConfirm}
                                            handleDeleteCancel={handleDeleteCancel}
                                            setFormData={setFormData}
                                            handleSubmit={handleSubmit}
                                            resetForm={resetForm}
                                        />
                                    ))}
                            </div>
                        </SortableContext>
                    </DndContext>
                ) : (
                    <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
                        <CardContent className="empty-state">
                            <div className="empty-state__icon">
                                <Dumbbell style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
                            </div>
                            <h3 className="empty-state__title">
                                NO WORKOUTS YET
                            </h3>
                            <p className="empty-state__text">
                                Start your training session by adding your first
                                exercise
                            </p>
                            <Button onClick={() => setShowForm(true)}>
                                <Plus style={{ width: '20px', height: '20px' }} />
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
