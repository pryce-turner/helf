import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { format } from "date-fns";
import {
    ArrowLeft,
    Plus,
    Minus,
    Trash2,
    ChevronUp,
    ChevronDown,
    Dumbbell,
    Weight,
    Hash,
    MessageSquare,
    Pencil,
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
import {
    useWorkouts,
    useCreateWorkout,
    useUpdateWorkout,
    useDeleteWorkout,
    useReorderWorkout,
} from "@/hooks/useWorkouts";
import type { Workout } from "@/types/workout";
import { useCategories, useExercises } from "@/hooks/useExercises";
import type { WorkoutCreate } from "@/types/workout";

const WorkoutSession = () => {
    const { date } = useParams<{ date: string }>();
    const navigate = useNavigate();

    const { data: workouts, isLoading } = useWorkouts({ date });
    const { data: categories } = useCategories();
    const { data: exercises } = useExercises();

    const createWorkout = useCreateWorkout();
    const updateWorkout = useUpdateWorkout();
    const deleteWorkout = useDeleteWorkout();
    const reorderWorkout = useReorderWorkout();

    const [showForm, setShowForm] = useState(false);
    const [editingWorkout, setEditingWorkout] = useState<Workout | null>(null);
    const [selectedCategory, setSelectedCategory] = useState("");
    const [selectedExercise, setSelectedExercise] = useState("");
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
        setSelectedCategory(workout.category);
        setSelectedExercise(workout.exercise);
        setFormData({
            date: workout.date,
            exercise: workout.exercise,
            category: workout.category,
            weight: workout.weight,
            weight_unit: workout.weight_unit || "lbs",
            reps: workout.reps,
            distance: workout.distance,
            distance_unit: workout.distance_unit,
            time: workout.time,
            comment: workout.comment,
        });
        setShowForm(true);
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

    const handleDelete = async (id: number) => {
        if (confirm("Are you sure you want to delete this workout?")) {
            await deleteWorkout.mutateAsync(id);
        }
    };

    const handleReorder = async (id: number, direction: "up" | "down") => {
        await reorderWorkout.mutateAsync({ id, direction });
    };

    const categoryExercises =
        exercises?.filter((e) => e.category === selectedCategory) || [];
    const formattedDate = date ? format(new Date(date), "MMMM d, yyyy") : "";

    const getCategoryColor = (category: string) => {
        const colors: Record<string, { bg: string; text: string; border: string }> = {
            Push: { bg: 'var(--chart-2)', text: 'var(--chart-2)', border: 'var(--chart-2)' },
            Pull: { bg: 'var(--accent)', text: 'var(--accent)', border: 'var(--accent)' },
            Legs: { bg: 'var(--chart-3)', text: 'var(--chart-3)', border: 'var(--chart-3)' },
            Core: { bg: 'var(--chart-4)', text: 'var(--chart-4)', border: 'var(--chart-4)' },
            Cardio: { bg: 'var(--error)', text: 'var(--error)', border: 'var(--error)' },
        };
        return colors[category] || { bg: 'var(--text-muted)', text: 'var(--text-muted)', border: 'var(--border)' };
    };

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content" style={{ maxWidth: '680px' }}>
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

                {/* Add Exercise Form */}
                {showForm && (
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
                                            value={selectedExercise}
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
                                            onClick={() => setFormData({
                                                ...formData,
                                                weight: Math.max(0, (formData.weight || 0) - 5),
                                            })}
                                        >
                                            <Minus style={{ width: '18px', height: '18px' }} />
                                        </button>
                                        <input
                                            id="weight"
                                            type="number"
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
                                            onClick={() => setFormData({
                                                ...formData,
                                                weight: (formData.weight || 0) + 5,
                                            })}
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
                    <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                        {workouts
                            .sort((a, b) => a.order - b.order)
                            .map((workout, index) => {
                                const catColor = getCategoryColor(workout.category);
                                return (
                                    <Card
                                        key={workout.doc_id}
                                        className="card-hover animate-in"
                                        style={{ animationDelay: `${index * 50}ms` }}
                                    >
                                        <CardContent style={{ padding: 'var(--space-5)' }}>
                                            <div className="flex items-start justify-between" style={{ gap: 'var(--space-4)' }}>
                                                <div
                                                    className="flex-1"
                                                    onClick={() => handleEditWorkout(workout)}
                                                    style={{ cursor: 'pointer' }}
                                                >
                                                    <div className="flex items-start" style={{ gap: 'var(--space-4)' }}>
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
                                                    <button
                                                        className="action-btn"
                                                        onClick={() => handleReorder(workout.doc_id, "up")}
                                                        disabled={index === 0}
                                                    >
                                                        <ChevronUp style={{ width: '20px', height: '20px' }} />
                                                    </button>
                                                    <button
                                                        className="action-btn"
                                                        onClick={() => handleReorder(workout.doc_id, "down")}
                                                        disabled={index === workouts.length - 1}
                                                    >
                                                        <ChevronDown style={{ width: '20px', height: '20px' }} />
                                                    </button>
                                                    <button
                                                        className="action-btn action-btn--danger"
                                                        onClick={() => handleDelete(workout.doc_id)}
                                                    >
                                                        <Trash2 style={{ width: '18px', height: '18px' }} />
                                                    </button>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                );
                            })}
                    </div>
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
