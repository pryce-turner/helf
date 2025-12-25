import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { ArrowLeft, Plus, Trash2, ChevronUp, ChevronDown } from "lucide-react";
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
    useDeleteWorkout,
    useReorderWorkout,
} from "@/hooks/useWorkouts";
import { useCategories, useExercises } from "@/hooks/useExercises";
import type { WorkoutCreate } from "@/types/workout";

const WorkoutSession = () => {
    const { date } = useParams<{ date: string }>();
    const navigate = useNavigate();

    const { data: workouts, isLoading } = useWorkouts({ date });
    const { data: categories } = useCategories();
    const { data: exercises } = useExercises();

    const createWorkout = useCreateWorkout();
    const deleteWorkout = useDeleteWorkout();
    const reorderWorkout = useReorderWorkout();

    const [showForm, setShowForm] = useState(false);
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

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!formData.exercise || !formData.category) {
            return;
        }

        await createWorkout.mutateAsync(formData);

        // Reset form
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
        setShowForm(false);
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

    return (
        <div className="min-h-screen">
            <Navigation />

            <div className="max-w-4xl mx-auto p-4 sm:p-6 lg:p-8">
                <div className="mb-6 flex items-center justify-between">
                    <div className="flex items-center space-x-4">
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={() => navigate("/")}
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <h1 className="text-3xl font-bold">{formattedDate}</h1>
                    </div>

                    <Button onClick={() => setShowForm(!showForm)}>
                        <Plus className="h-5 w-5 mr-2" />
                        Add Exercise
                    </Button>
                </div>

                {showForm && (
                    <Card className="mb-6">
                        <CardHeader>
                            <CardTitle>Add Exercise</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="category">
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
                                                        key={cat.id}
                                                        value={cat.name}
                                                    >
                                                        {cat.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="exercise">
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
                                                        key={ex.id}
                                                        value={ex.name}
                                                    >
                                                        {ex.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="weight">Weight</Label>
                                        <div className="flex space-x-2">
                                            <Input
                                                id="weight"
                                                type="number"
                                                step="0.1"
                                                value={formData.weight || ""}
                                                onChange={(
                                                    e: React.ChangeEvent<HTMLInputElement>,
                                                ) =>
                                                    setFormData({
                                                        ...formData,
                                                        weight: e.target.value
                                                            ? parseFloat(
                                                                  e.target
                                                                      .value,
                                                              )
                                                            : null,
                                                    })
                                                }
                                            />
                                            <Select
                                                value={formData.weight_unit}
                                                onValueChange={(
                                                    value: string,
                                                ) =>
                                                    setFormData({
                                                        ...formData,
                                                        weight_unit: value,
                                                    })
                                                }
                                            >
                                                <SelectTrigger className="w-20">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="lbs">
                                                        lbs
                                                    </SelectItem>
                                                    <SelectItem value="kg">
                                                        kg
                                                    </SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="reps">Reps</Label>
                                        <Input
                                            id="reps"
                                            type="text"
                                            placeholder="e.g., 5 or 5+"
                                            value={formData.reps || ""}
                                            onChange={(
                                                e: React.ChangeEvent<HTMLInputElement>,
                                            ) =>
                                                setFormData({
                                                    ...formData,
                                                    reps:
                                                        e.target.value || null,
                                                })
                                            }
                                        />
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="comment">Comment</Label>
                                        <Input
                                            id="comment"
                                            type="text"
                                            value={formData.comment || ""}
                                            onChange={(
                                                e: React.ChangeEvent<HTMLInputElement>,
                                            ) =>
                                                setFormData({
                                                    ...formData,
                                                    comment:
                                                        e.target.value || null,
                                                })
                                            }
                                        />
                                    </div>
                                </div>

                                <div className="flex justify-end space-x-2">
                                    <Button
                                        type="button"
                                        variant="outline"
                                        onClick={() => setShowForm(false)}
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
                                        Add Workout
                                    </Button>
                                </div>
                            </form>
                        </CardContent>
                    </Card>
                )}

                {isLoading ? (
                    <div className="text-center py-12 text-muted-foreground">
                        Loading workouts...
                    </div>
                ) : workouts && workouts.length > 0 ? (
                    <div className="space-y-4">
                        {workouts
                            .sort((a, b) => a.order - b.order)
                            .map((workout, index) => (
                                <Card key={workout.id}>
                                    <CardContent className="p-4">
                                        <div className="flex items-center justify-between">
                                            <div className="flex-1">
                                                <div className="flex items-center space-x-3">
                                                    <span className="text-muted-foreground font-mono">
                                                        #{index + 1}
                                                    </span>
                                                    <div>
                                                        <h3 className="font-semibold text-lg">
                                                            {workout.exercise}
                                                        </h3>
                                                        <p className="text-sm text-muted-foreground">
                                                            {workout.category}
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="mt-2 flex flex-wrap gap-4 text-sm">
                                                    {workout.weight && (
                                                        <span className="font-medium">
                                                            {workout.weight}{" "}
                                                            {
                                                                workout.weight_unit
                                                            }
                                                        </span>
                                                    )}
                                                    {workout.reps && (
                                                        <span className="font-medium">
                                                            {workout.reps} reps
                                                        </span>
                                                    )}
                                                    {workout.comment && (
                                                        <span className="text-muted-foreground italic">
                                                            {workout.comment}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>

                                            <div className="flex items-center space-x-2">
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    onClick={() =>
                                                        handleReorder(
                                                            workout.id,
                                                            "up",
                                                        )
                                                    }
                                                    disabled={index === 0}
                                                >
                                                    <ChevronUp className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    onClick={() =>
                                                        handleReorder(
                                                            workout.id,
                                                            "down",
                                                        )
                                                    }
                                                    disabled={
                                                        index ===
                                                        workouts.length - 1
                                                    }
                                                >
                                                    <ChevronDown className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    onClick={() =>
                                                        handleDelete(workout.id)
                                                    }
                                                >
                                                    <Trash2 className="h-4 w-4 text-destructive" />
                                                </Button>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                    </div>
                ) : (
                    <Card>
                        <CardContent className="p-12 text-center">
                            <p className="text-muted-foreground">
                                No workouts recorded for this date.
                            </p>
                            <Button
                                className="mt-4"
                                onClick={() => setShowForm(true)}
                            >
                                <Plus className="h-5 w-5 mr-2" />
                                Add Your First Exercise
                            </Button>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
};

export default WorkoutSession;
