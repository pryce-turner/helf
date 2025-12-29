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
                            variant="outline"
                            size="icon"
                            onClick={() => navigate("/")}
                            style={{
                                width: '44px',
                                height: '44px',
                                borderRadius: 'var(--radius-sm)',
                                background: 'var(--bg-tertiary)',
                                border: '1px solid var(--border)',
                                color: 'var(--text-primary)',
                                cursor: 'pointer',
                                transition: 'all var(--duration-normal)',
                            }}
                            onMouseEnter={(e: React.MouseEvent<HTMLButtonElement>) => {
                                e.currentTarget.style.background = 'var(--bg-hover)';
                                e.currentTarget.style.transform = 'translateY(-1px)';
                            }}
                            onMouseLeave={(e: React.MouseEvent<HTMLButtonElement>) => {
                                e.currentTarget.style.background = 'var(--bg-tertiary)';
                                e.currentTarget.style.transform = 'translateY(0)';
                            }}
                        >
                            <ArrowLeft style={{ width: '20px', height: '20px' }} />
                        </Button>
                        <div>
                            <h1
                                style={{
                                    fontFamily: 'var(--font-display)',
                                    fontSize: '24px',
                                    fontWeight: 600,
                                    color: 'var(--text-primary)',
                                    letterSpacing: '-0.01em',
                                }}
                            >
                                {formattedDate.toUpperCase()}
                            </h1>
                            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                                {workouts?.length || 0} exercise{workouts?.length !== 1 ? "s" : ""} logged
                            </p>
                        </div>
                    </div>

                    <button
                        onClick={() => {
                            if (showForm) {
                                resetForm();
                            } else {
                                setShowForm(true);
                            }
                        }}
                        className="btn-primary"
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 'var(--space-2)',
                        }}
                    >
                        <Plus style={{ width: '20px', height: '20px' }} />
                        Add Exercise
                    </button>
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
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                                        <Label
                                            htmlFor="category"
                                            style={{
                                                fontSize: '12px',
                                                fontWeight: 600,
                                                color: 'var(--text-muted)',
                                                textTransform: 'uppercase',
                                                letterSpacing: '0.05em',
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: 'var(--space-2)',
                                            }}
                                        >
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

                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                                        <Label
                                            htmlFor="exercise"
                                            style={{
                                                fontSize: '12px',
                                                fontWeight: 600,
                                                color: 'var(--text-muted)',
                                                textTransform: 'uppercase',
                                                letterSpacing: '0.05em',
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: 'var(--space-2)',
                                            }}
                                        >
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

                                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                                    <Label
                                        htmlFor="weight"
                                        style={{
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            color: 'var(--text-muted)',
                                            textTransform: 'uppercase',
                                            letterSpacing: '0.05em',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 'var(--space-2)',
                                        }}
                                    >
                                        <Weight style={{ width: '14px', height: '14px' }} />
                                        Weight
                                    </Label>
                                    <div className="flex" style={{ alignItems: 'stretch' }}>
                                        <button
                                            type="button"
                                            onClick={() => setFormData({
                                                ...formData,
                                                weight: Math.max(0, (formData.weight || 0) - 5),
                                            })}
                                            style={{
                                                width: '44px',
                                                height: '44px',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                background: 'var(--bg-tertiary)',
                                                border: '1px solid var(--border)',
                                                borderRight: 'none',
                                                borderRadius: 'var(--radius-sm) 0 0 var(--radius-sm)',
                                                color: 'var(--text-secondary)',
                                                cursor: 'pointer',
                                                transition: 'all var(--duration-fast)',
                                            }}
                                            onMouseEnter={(e) => {
                                                e.currentTarget.style.background = 'var(--bg-hover)';
                                                e.currentTarget.style.color = 'var(--text-primary)';
                                            }}
                                            onMouseLeave={(e) => {
                                                e.currentTarget.style.background = 'var(--bg-tertiary)';
                                                e.currentTarget.style.color = 'var(--text-secondary)';
                                            }}
                                        >
                                            <Minus style={{ width: '18px', height: '18px' }} />
                                        </button>
                                        <input
                                            id="weight"
                                            type="number"
                                            step="0.1"
                                            placeholder="0"
                                            style={{
                                                minWidth: 0,
                                                flex: 1,
                                                height: '44px',
                                                boxSizing: 'border-box',
                                                borderRadius: 0,
                                                textAlign: 'center',
                                                border: 'none',
                                                borderTop: '1px solid var(--border)',
                                                borderBottom: '1px solid var(--border)',
                                                background: 'var(--bg-secondary)',
                                                color: 'var(--text-primary)',
                                                fontFamily: 'var(--font-mono)',
                                                fontSize: '16px',
                                                outline: 'none',
                                            }}
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
                                            onClick={() => setFormData({
                                                ...formData,
                                                weight: (formData.weight || 0) + 5,
                                            })}
                                            style={{
                                                width: '44px',
                                                height: '44px',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                background: 'var(--bg-tertiary)',
                                                border: '1px solid var(--border)',
                                                borderLeft: 'none',
                                                borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                                                color: 'var(--text-secondary)',
                                                cursor: 'pointer',
                                                transition: 'all var(--duration-fast)',
                                            }}
                                            onMouseEnter={(e) => {
                                                e.currentTarget.style.background = 'var(--bg-hover)';
                                                e.currentTarget.style.color = 'var(--text-primary)';
                                            }}
                                            onMouseLeave={(e) => {
                                                e.currentTarget.style.background = 'var(--bg-tertiary)';
                                                e.currentTarget.style.color = 'var(--text-secondary)';
                                            }}
                                        >
                                            <Plus style={{ width: '18px', height: '18px' }} />
                                        </button>
                                        <span style={{ color: 'var(--text-muted)', fontSize: '14px', fontWeight: 500, marginLeft: 'var(--space-2)', display: 'flex', alignItems: 'center' }}>lbs</span>
                                    </div>
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                                    <Label
                                        htmlFor="reps"
                                        style={{
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            color: 'var(--text-muted)',
                                            textTransform: 'uppercase',
                                            letterSpacing: '0.05em',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 'var(--space-2)',
                                        }}
                                    >
                                        <Hash style={{ width: '14px', height: '14px' }} />
                                        Reps
                                    </Label>
                                    <input
                                        id="reps"
                                        type="text"
                                        placeholder="e.g., 5 or 5+"
                                        style={{
                                            width: '100%',
                                            height: '44px',
                                            boxSizing: 'border-box',
                                            padding: '0 12px',
                                            borderRadius: 'var(--radius-sm)',
                                            border: '1px solid var(--border)',
                                            background: 'var(--bg-secondary)',
                                            color: 'var(--text-primary)',
                                            fontFamily: 'var(--font-mono)',
                                            fontSize: '16px',
                                            outline: 'none',
                                        }}
                                        value={formData.reps || ""}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                            setFormData({
                                                ...formData,
                                                reps: e.target.value || null,
                                            })
                                        }
                                    />
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', overflow: 'hidden' }}>
                                    <Label
                                        htmlFor="comment"
                                        style={{
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            color: 'var(--text-muted)',
                                            textTransform: 'uppercase',
                                            letterSpacing: '0.05em',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 'var(--space-2)',
                                        }}
                                    >
                                        <MessageSquare style={{ width: '14px', height: '14px' }} />
                                        Comment
                                    </Label>
                                    <input
                                        id="comment"
                                        type="text"
                                        placeholder="Optional note"
                                        style={{
                                            width: '100%',
                                            height: '44px',
                                            boxSizing: 'border-box',
                                            padding: '0 12px',
                                            borderRadius: 'var(--radius-sm)',
                                            border: '1px solid var(--border)',
                                            background: 'var(--bg-secondary)',
                                            color: 'var(--text-primary)',
                                            fontFamily: 'var(--font-body)',
                                            fontSize: '16px',
                                            outline: 'none',
                                        }}
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
                                    <button
                                        type="button"
                                        className="btn-secondary"
                                        onClick={resetForm}
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        className="btn-primary"
                                        disabled={
                                            !formData.exercise ||
                                            !formData.category
                                        }
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 'var(--space-2)',
                                            opacity: (!formData.exercise || !formData.category) ? 0.5 : 1,
                                        }}
                                    >
                                        {editingWorkout ? (
                                            <Pencil style={{ width: '20px', height: '20px' }} />
                                        ) : (
                                            <Plus style={{ width: '20px', height: '20px' }} />
                                        )}
                                        {editingWorkout ? 'Save Changes' : 'Add Workout'}
                                    </button>
                                </div>
                            </form>
                        </CardContent>
                    </Card>
                )}

                {/* Workout List */}
                {isLoading ? (
                    <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
                        <div
                            className="inline-block animate-spin rounded-full border-4 border-t-transparent"
                            style={{
                                width: '48px',
                                height: '48px',
                                borderColor: 'var(--accent)',
                                borderTopColor: 'transparent',
                            }}
                        />
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
                                                        <div
                                                            style={{
                                                                background: 'var(--accent-subtle)',
                                                                color: 'var(--accent)',
                                                                fontWeight: 700,
                                                                fontSize: '16px',
                                                                width: '40px',
                                                                height: '40px',
                                                                borderRadius: 'var(--radius-md)',
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                justifyContent: 'center',
                                                                fontFamily: 'var(--font-mono)',
                                                                flexShrink: 0,
                                                            }}
                                                        >
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
                                                                    style={{
                                                                        padding: '4px 12px',
                                                                        borderRadius: 'var(--radius-full)',
                                                                        fontSize: '12px',
                                                                        fontWeight: 600,
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
                                                                    <div
                                                                        style={{
                                                                            display: 'flex',
                                                                            alignItems: 'center',
                                                                            gap: 'var(--space-2)',
                                                                            background: 'var(--bg-tertiary)',
                                                                            padding: '8px 16px',
                                                                            borderRadius: 'var(--radius-sm)',
                                                                        }}
                                                                    >
                                                                        <Weight style={{ width: '16px', height: '16px', color: 'var(--accent)' }} />
                                                                        <span
                                                                            style={{
                                                                                fontWeight: 600,
                                                                                fontFamily: 'var(--font-mono)',
                                                                                color: 'var(--text-primary)',
                                                                            }}
                                                                        >
                                                                            {workout.weight} {workout.weight_unit}
                                                                        </span>
                                                                    </div>
                                                                )}
                                                                {workout.reps && (
                                                                    <div
                                                                        style={{
                                                                            display: 'flex',
                                                                            alignItems: 'center',
                                                                            gap: 'var(--space-2)',
                                                                            background: 'var(--bg-tertiary)',
                                                                            padding: '8px 16px',
                                                                            borderRadius: 'var(--radius-sm)',
                                                                        }}
                                                                    >
                                                                        <Hash style={{ width: '16px', height: '16px', color: 'var(--accent)' }} />
                                                                        <span
                                                                            style={{
                                                                                fontWeight: 600,
                                                                                fontFamily: 'var(--font-mono)',
                                                                                color: 'var(--text-primary)',
                                                                            }}
                                                                        >
                                                                            {workout.reps} reps
                                                                        </span>
                                                                    </div>
                                                                )}
                                                                {workout.comment && (
                                                                    <div
                                                                        style={{
                                                                            display: 'flex',
                                                                            alignItems: 'center',
                                                                            gap: 'var(--space-2)',
                                                                            background: 'var(--bg-tertiary)',
                                                                            padding: '8px 16px',
                                                                            borderRadius: 'var(--radius-sm)',
                                                                        }}
                                                                    >
                                                                        <MessageSquare style={{ width: '16px', height: '16px', color: 'var(--text-muted)' }} />
                                                                        <span
                                                                            style={{
                                                                                color: 'var(--text-secondary)',
                                                                                fontStyle: 'italic',
                                                                            }}
                                                                        >
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
                                                        onClick={() => handleReorder(workout.doc_id, "up")}
                                                        disabled={index === 0}
                                                        style={{
                                                            width: '36px',
                                                            height: '36px',
                                                            padding: 0,
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'center',
                                                            background: 'transparent',
                                                            border: 'none',
                                                            borderRadius: 'var(--radius-sm)',
                                                            color: index === 0 ? 'var(--text-muted)' : 'var(--text-secondary)',
                                                            cursor: index === 0 ? 'not-allowed' : 'pointer',
                                                            transition: 'all var(--duration-fast)',
                                                            opacity: index === 0 ? 0.4 : 1,
                                                        }}
                                                        onMouseEnter={(e) => {
                                                            if (index !== 0) {
                                                                e.currentTarget.style.background = 'var(--bg-hover)';
                                                                e.currentTarget.style.color = 'var(--text-primary)';
                                                            }
                                                        }}
                                                        onMouseLeave={(e) => {
                                                            e.currentTarget.style.background = 'transparent';
                                                            e.currentTarget.style.color = index === 0 ? 'var(--text-muted)' : 'var(--text-secondary)';
                                                        }}
                                                    >
                                                        <ChevronUp style={{ width: '20px', height: '20px' }} />
                                                    </button>
                                                    <button
                                                        onClick={() => handleReorder(workout.doc_id, "down")}
                                                        disabled={index === workouts.length - 1}
                                                        style={{
                                                            width: '36px',
                                                            height: '36px',
                                                            padding: 0,
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'center',
                                                            background: 'transparent',
                                                            border: 'none',
                                                            borderRadius: 'var(--radius-sm)',
                                                            color: index === workouts.length - 1 ? 'var(--text-muted)' : 'var(--text-secondary)',
                                                            cursor: index === workouts.length - 1 ? 'not-allowed' : 'pointer',
                                                            transition: 'all var(--duration-fast)',
                                                            opacity: index === workouts.length - 1 ? 0.4 : 1,
                                                        }}
                                                        onMouseEnter={(e) => {
                                                            if (index !== workouts.length - 1) {
                                                                e.currentTarget.style.background = 'var(--bg-hover)';
                                                                e.currentTarget.style.color = 'var(--text-primary)';
                                                            }
                                                        }}
                                                        onMouseLeave={(e) => {
                                                            e.currentTarget.style.background = 'transparent';
                                                            e.currentTarget.style.color = index === workouts.length - 1 ? 'var(--text-muted)' : 'var(--text-secondary)';
                                                        }}
                                                    >
                                                        <ChevronDown style={{ width: '20px', height: '20px' }} />
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(workout.doc_id)}
                                                        style={{
                                                            width: '36px',
                                                            height: '36px',
                                                            padding: 0,
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'center',
                                                            background: 'transparent',
                                                            border: 'none',
                                                            borderRadius: 'var(--radius-sm)',
                                                            color: 'var(--text-muted)',
                                                            cursor: 'pointer',
                                                            transition: 'all var(--duration-fast)',
                                                        }}
                                                        onMouseEnter={(e) => {
                                                            e.currentTarget.style.background = 'var(--error-subtle)';
                                                            e.currentTarget.style.color = 'var(--error)';
                                                        }}
                                                        onMouseLeave={(e) => {
                                                            e.currentTarget.style.background = 'transparent';
                                                            e.currentTarget.style.color = 'var(--text-muted)';
                                                        }}
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
                        <CardContent style={{ padding: 'var(--space-12)', textAlign: 'center' }}>
                            <div
                                style={{
                                    background: 'var(--bg-tertiary)',
                                    width: '80px',
                                    height: '80px',
                                    borderRadius: 'var(--radius-full)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    margin: '0 auto var(--space-4)',
                                }}
                            >
                                <Dumbbell style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
                            </div>
                            <h3
                                style={{
                                    fontFamily: 'var(--font-display)',
                                    fontSize: '18px',
                                    fontWeight: 600,
                                    marginBottom: 'var(--space-2)',
                                }}
                            >
                                NO WORKOUTS YET
                            </h3>
                            <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-6)' }}>
                                Start your training session by adding your first
                                exercise
                            </p>
                            <button
                                className="btn-primary"
                                onClick={() => setShowForm(true)}
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 'var(--space-2)',
                                }}
                            >
                                <Plus style={{ width: '20px', height: '20px' }} />
                                Add Your First Exercise
                            </button>
                        </CardContent>
                    </Card>
                )}
            </div>
            </div>
        </>
    );
};

export default WorkoutSession;
