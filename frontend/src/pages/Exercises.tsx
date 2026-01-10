import { useState, useMemo, useEffect, useCallback } from 'react';
import { Dumbbell, Plus, Check, X, Trash2, Edit3, Hash } from 'lucide-react';
import Navigation from '@/components/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  useExercises,
  useCategories,
  useCreateExercise,
  useUpdateExercise,
  useDeleteExercise,
} from '@/hooks/useExercises';
import type { Exercise } from '@/types/exercise';

// Predefined colors for common categories (matching WorkoutSession/Upcoming)
const getCategoryColor = (category: string) => {
  const predefined: Record<string, string> = {
    Push: 'var(--chart-2)',
    Pull: 'var(--accent)',
    Legs: 'var(--chart-3)',
    Core: 'var(--chart-4)',
    Cardio: 'var(--error)',
  };

  const palette = [
    'var(--chart-1)',
    'var(--chart-2)',
    'var(--chart-3)',
    'var(--chart-4)',
    'var(--chart-5)',
    'var(--info)',
    'var(--error)',
  ];

  let color = predefined[category];
  if (!color) {
    let hash = 0;
    for (let i = 0; i < category.length; i++) {
      hash = category.charCodeAt(i) + ((hash << 5) - hash);
    }
    color = palette[Math.abs(hash) % palette.length];
  }

  return { bg: color, text: color, border: color };
};

const Exercises = () => {
  const { data: exercises, isLoading } = useExercises();
  const { data: categories } = useCategories();
  const createExercise = useCreateExercise();
  const updateExercise = useUpdateExercise();
  const deleteExercise = useDeleteExercise();

  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);

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
    await deleteExercise.mutateAsync(id);
    setConfirmingDelete(null);
  }, [deleteExercise]);

  const handleDeleteCancel = useCallback(() => {
    setConfirmingDelete(null);
  }, []);

  const handleAddExercise = async () => {
    if (!newName.trim() || !newCategory.trim()) return;
    await createExercise.mutateAsync({
      name: newName.trim(),
      category: newCategory.trim(),
    });
    setNewName('');
    setNewCategory('');
    setShowAddForm(false);
  };

  const startEditing = (exercise: Exercise) => {
    setEditingId(exercise.doc_id);
    setEditName(exercise.name);
    setEditCategory(exercise.category);
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditName('');
    setEditCategory('');
  };

  const saveEditing = async () => {
    if (editingId === null || !editName.trim() || !editCategory.trim()) return;
    await updateExercise.mutateAsync({
      id: editingId,
      data: { name: editName.trim(), category: editCategory.trim() },
    });
    cancelEditing();
  };

  // Group exercises by category
  const exercisesByCategory = useMemo(() => {
    if (!exercises) return {};

    const grouped: Record<string, Exercise[]> = {};
    exercises.forEach(ex => {
      if (!grouped[ex.category]) {
        grouped[ex.category] = [];
      }
      grouped[ex.category].push(ex);
    });

    // Sort exercises within each category by name
    Object.keys(grouped).forEach(cat => {
      grouped[cat].sort((a, b) => a.name.localeCompare(b.name));
    });

    return grouped;
  }, [exercises]);

  const sortedCategories = useMemo(() => {
    return Object.keys(exercisesByCategory).sort();
  }, [exercisesByCategory]);

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content">
          {/* Header */}
          <div className="page__header animate-in">
            <div className="flex items-start justify-between flex-wrap" style={{ gap: 'var(--space-4)' }}>
              <div>
                <h1 className="page__title">EXERCISES</h1>
                <p className="page__subtitle">Manage your exercise library</p>
              </div>
              <Button onClick={() => setShowAddForm(!showAddForm)}>
                <Plus style={{ width: '18px', height: '18px' }} />
                {showAddForm ? 'Cancel' : 'Add Exercise'}
              </Button>
            </div>
          </div>

          {/* Add Exercise Form */}
          {showAddForm && (
            <Card className="animate-in" style={{ marginBottom: 'var(--space-6)' }}>
              <CardHeader>
                <CardTitle className="font-display text-xl tracking-tight">
                  ADD NEW EXERCISE
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
                    <div style={{ flex: '1 1 200px' }}>
                      <Label htmlFor="new-name" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                        Exercise Name
                      </Label>
                      <Input
                        id="new-name"
                        type="text"
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        placeholder="e.g., Bench Press"
                      />
                    </div>
                    <div style={{ flex: '1 1 200px' }}>
                      <Label htmlFor="new-category" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                        Category
                      </Label>
                      <Input
                        id="new-category"
                        type="text"
                        list="category-suggestions"
                        value={newCategory}
                        onChange={(e) => setNewCategory(e.target.value)}
                        placeholder="e.g., Push"
                      />
                      <datalist id="category-suggestions">
                        {categories?.map(cat => (
                          <option key={cat.doc_id} value={cat.name} />
                        ))}
                      </datalist>
                    </div>
                  </div>
                  <div className="flex" style={{ gap: 'var(--space-3)', justifyContent: 'flex-end' }}>
                    <Button variant="secondary" onClick={() => setShowAddForm(false)}>
                      Cancel
                    </Button>
                    <Button
                      onClick={handleAddExercise}
                      disabled={createExercise.isPending || !newName.trim() || !newCategory.trim()}
                    >
                      {createExercise.isPending ? 'Adding...' : 'Add Exercise'}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {isLoading ? (
            <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
              <div className="loading-spinner inline-block" />
              <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
                Loading exercises...
              </p>
            </div>
          ) : sortedCategories.length > 0 ? (
            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
              {sortedCategories.map((category, categoryIndex) => {
                const catColor = getCategoryColor(category);
                const categoryExercises = exercisesByCategory[category];

                return (
                  <Card key={category} className="animate-in" style={{ animationDelay: `${categoryIndex * 50}ms` }}>
                    <CardHeader>
                      <div className="flex items-center justify-between flex-wrap" style={{ gap: 'var(--space-4)' }}>
                        <div className="flex items-center" style={{ gap: 'var(--space-3)' }}>
                          <div
                            className="workout-order"
                            style={{
                              width: '44px',
                              height: '44px',
                              fontSize: '18px',
                              background: `${catColor.bg}15`,
                              color: catColor.text,
                            }}
                          >
                            <Dumbbell style={{ width: '20px', height: '20px' }} />
                          </div>
                          <div>
                            <CardTitle className="font-display text-xl tracking-tight">
                              {category.toUpperCase()}
                            </CardTitle>
                            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                              {categoryExercises.length} exercise{categoryExercises.length !== 1 ? 's' : ''}
                            </p>
                          </div>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                        {categoryExercises.map((exercise, exerciseIndex) => (
                          <div
                            key={exercise.doc_id}
                            className="interactive-item"
                            style={{
                              padding: 'var(--space-4)',
                              background: 'var(--bg-tertiary)',
                              borderRadius: 'var(--radius-md)',
                              border: '1px solid var(--border-subtle)',
                              transition: 'all var(--duration-normal) var(--ease-default)',
                            }}
                          >
                            {editingId === exercise.doc_id ? (
                              // Editing state
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
                                  <Input
                                    type="text"
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    placeholder="Exercise name"
                                    style={{ flex: '1 1 200px' }}
                                  />
                                  <Input
                                    type="text"
                                    list="edit-category-suggestions"
                                    value={editCategory}
                                    onChange={(e) => setEditCategory(e.target.value)}
                                    placeholder="Category"
                                    style={{ flex: '1 1 150px' }}
                                  />
                                  <datalist id="edit-category-suggestions">
                                    {categories?.map(cat => (
                                      <option key={cat.doc_id} value={cat.name} />
                                    ))}
                                  </datalist>
                                </div>
                                <div className="flex" style={{ gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={cancelEditing}
                                  >
                                    <X style={{ width: '16px', height: '16px' }} />
                                    Cancel
                                  </Button>
                                  <Button
                                    size="sm"
                                    onClick={saveEditing}
                                    disabled={updateExercise.isPending || !editName.trim() || !editCategory.trim()}
                                  >
                                    <Check style={{ width: '16px', height: '16px' }} />
                                    Save
                                  </Button>
                                </div>
                              </div>
                            ) : (
                              // Display state
                              <div className="flex items-start" style={{ gap: 'var(--space-4)' }}>
                                <div
                                  className="workout-order"
                                  style={{
                                    width: '36px',
                                    height: '36px',
                                    fontSize: '14px',
                                    background: `${catColor.bg}15`,
                                    color: catColor.text,
                                  }}
                                >
                                  {exerciseIndex + 1}
                                </div>
                                <div className="flex-1">
                                  <div className="flex items-center flex-wrap" style={{ gap: 'var(--space-3)', marginBottom: exercise.use_count > 0 ? 'var(--space-2)' : 0 }}>
                                    <h3
                                      style={{
                                        fontFamily: 'var(--font-body)',
                                        fontSize: '16px',
                                        fontWeight: 600,
                                        color: 'var(--text-primary)',
                                      }}
                                    >
                                      {exercise.name}
                                    </h3>
                                  </div>
                                  {exercise.use_count > 0 && (
                                    <div className="flex flex-wrap" style={{ gap: 'var(--space-2)' }}>
                                      <div className="workout-chip">
                                        <Hash style={{ width: '14px', height: '14px', color: catColor.text }} />
                                        <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                          {exercise.use_count}
                                        </span>
                                        <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                                          use{exercise.use_count !== 1 ? 's' : ''}
                                        </span>
                                      </div>
                                    </div>
                                  )}
                                </div>
                                <div className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={() => startEditing(exercise)}
                                  >
                                    <Edit3 style={{ width: '16px', height: '16px' }} />
                                    Edit
                                  </Button>
                                  {confirmingDelete === exercise.doc_id ? (
                                    <div className="flex" style={{ gap: 'var(--space-1)' }}>
                                      <Button
                                        variant="destructive"
                                        size="sm"
                                        onClick={() => handleDeleteConfirm(exercise.doc_id)}
                                      >
                                        <Check style={{ width: '16px', height: '16px' }} />
                                        Confirm
                                      </Button>
                                      <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={handleDeleteCancel}
                                      >
                                        <X style={{ width: '16px', height: '16px' }} />
                                      </Button>
                                    </div>
                                  ) : (
                                    <Button
                                      variant="destructive"
                                      size="sm"
                                      onClick={() => handleDeleteClick(exercise.doc_id)}
                                    >
                                      <Trash2 style={{ width: '16px', height: '16px' }} />
                                      Delete
                                    </Button>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        ))}
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
                <h3 className="empty-state__title">NO EXERCISES</h3>
                <p className="empty-state__text">No exercises in the library yet.</p>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
                  Add your first exercise to get started.
                </p>
                <Button onClick={() => setShowAddForm(true)}>
                  <Plus style={{ width: '18px', height: '18px' }} />
                  Add Exercise
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
};

export default Exercises;
