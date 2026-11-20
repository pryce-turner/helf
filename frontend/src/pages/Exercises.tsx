import { useState, useMemo, useEffect, useCallback } from 'react';
import { Dumbbell, Plus, Check, X, Trash2, Edit3, Hash, FileText, Lightbulb, Sparkles, ChevronDown, Coffee } from 'lucide-react';
import Navigation from '@/components/Navigation';
import ExerciseSectionTabs from '@/components/ExerciseSectionTabs';
import CategoryField from '@/components/CategoryField';
import StarRating from '@/components/StarRating';
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
  useSeedExercises,
} from '@/hooks/useExercises';
import type { Exercise } from '@/types/exercise';

/** What the toggle gives a movement it is adding to the pool. */
const DEFAULT_BREAK_SECONDS = 30;

/**
 * The edit form's draft of the four field groups. Text inputs hold strings;
 * parsing happens at save, where a blank becomes an explicit null — clearing
 * a default is a real edit, not an omitted key.
 */
interface FieldConfigDraft {
  reps_enabled: boolean;
  default_reps: string;
  weight_enabled: boolean;
  default_weight_lb: string;
  distance_enabled: boolean;
  default_distance: string;
  default_distance_unit: string;
  time_enabled: boolean;
  default_work_seconds: string;
  default_rest_seconds: string;
  default_rest_after_seconds: string;
}

const draftFromExercise = (exercise: Exercise): FieldConfigDraft => ({
  reps_enabled: exercise.reps_enabled,
  default_reps: exercise.default_reps?.toString() ?? '',
  weight_enabled: exercise.weight_enabled,
  default_weight_lb: exercise.default_weight_lb?.toString() ?? '',
  distance_enabled: exercise.distance_enabled,
  default_distance: exercise.default_distance?.toString() ?? '',
  default_distance_unit: exercise.default_distance_unit ?? '',
  time_enabled: exercise.time_enabled,
  default_work_seconds: exercise.default_work_seconds?.toString() ?? '',
  default_rest_seconds: exercise.default_rest_seconds?.toString() ?? '',
  default_rest_after_seconds: exercise.default_rest_after_seconds?.toString() ?? '',
});

const parseSeconds = (raw: string): number | null => {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parsed = parseInt(trimmed, 10);
  return Number.isFinite(parsed) ? parsed : null;
};

const parseNumber = (raw: string): number | null => {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const parsed = parseFloat(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
};

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
  const seedExercises = useSeedExercises();

  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [newForm, setNewForm] = useState('');
  const [newApplication, setNewApplication] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [editForm, setEditForm] = useState('');
  const [editApplication, setEditApplication] = useState('');
  const [editConfig, setEditConfig] = useState<FieldConfigDraft | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());

  const toggleCategory = useCallback((category: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  }, []);

  // Auto-hide seed message after 4 seconds
  useEffect(() => {
    if (seedMessage) {
      const timer = setTimeout(() => setSeedMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [seedMessage]);

  const handleSeedExercises = async () => {
    const result = await seedExercises.mutateAsync();
    setSeedMessage(result.message);
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
      form: newForm.trim() || undefined,
      application: newApplication.trim() || undefined,
    });
    setNewName('');
    setNewCategory('');
    setNewForm('');
    setNewApplication('');
    setShowAddForm(false);
  };

  const startEditing = (exercise: Exercise) => {
    setEditingId(exercise.doc_id);
    setEditName(exercise.name);
    setEditCategory(exercise.category);
    setEditForm(exercise.form || '');
    setEditApplication(exercise.application || '');
    setEditConfig(draftFromExercise(exercise));
  };

  /**
   * In or out of the movement break pool. Joining also turns the Time group
   * on and seeds the default bout — a pool member is a timed movement by
   * definition — but keeps a bout the movement already has.
   */
  const toggleMovementBreak = (exercise: Exercise) => {
    if (exercise.movement_break_enabled) {
      updateExercise.mutate({
        id: exercise.doc_id,
        data: { movement_break_enabled: false },
      });
      return;
    }
    updateExercise.mutate({
      id: exercise.doc_id,
      data: {
        movement_break_enabled: true,
        time_enabled: true,
        default_work_seconds: exercise.default_work_seconds ?? DEFAULT_BREAK_SECONDS,
      },
    });
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditName('');
    setEditCategory('');
    setEditForm('');
    setEditApplication('');
    setEditConfig(null);
  };

  const saveEditing = async () => {
    if (editingId === null || !editName.trim() || !editCategory.trim() || !editConfig) return;
    await updateExercise.mutateAsync({
      id: editingId,
      data: {
        name: editName.trim(),
        category: editCategory.trim(),
        form: editForm.trim() || '',
        application: editApplication.trim() || '',
        // The whole configuration is sent every save: blanks go as explicit
        // nulls, which is how a default gets cleared — an omitted key would
        // leave it alone.
        reps_enabled: editConfig.reps_enabled,
        default_reps: parseSeconds(editConfig.default_reps),
        weight_enabled: editConfig.weight_enabled,
        default_weight_lb: parseNumber(editConfig.default_weight_lb),
        distance_enabled: editConfig.distance_enabled,
        default_distance: parseNumber(editConfig.default_distance),
        default_distance_unit: editConfig.default_distance_unit || null,
        time_enabled: editConfig.time_enabled,
        default_work_seconds: parseSeconds(editConfig.default_work_seconds),
        default_rest_seconds: parseSeconds(editConfig.default_rest_seconds),
        default_rest_after_seconds: parseSeconds(editConfig.default_rest_after_seconds),
      },
    });
    cancelEditing();
  };

  // Every category that exists, whether or not it currently holds an exercise
  // — an empty one is still a place to file the next movement.
  const categoryNames = useMemo(
    () => (categories ?? []).map((c) => c.name).sort((a, b) => a.localeCompare(b)),
    [categories],
  );

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
              <div className="flex flex-wrap" style={{ gap: 'var(--space-2)' }}>
                <Button
                  variant="secondary"
                  onClick={handleSeedExercises}
                  disabled={seedExercises.isPending}
                >
                  <Sparkles style={{ width: '18px', height: '18px' }} />
                  {seedExercises.isPending ? 'Seeding...' : 'Seed Presets'}
                </Button>
                <Button onClick={() => setShowAddForm(!showAddForm)}>
                  <Plus style={{ width: '18px', height: '18px' }} />
                  {showAddForm ? 'Cancel' : 'Add Exercise'}
                </Button>
              </div>
            </div>
            {seedMessage && (
              <div
                className="animate-in"
                style={{
                  marginTop: 'var(--space-4)',
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'var(--accent)15',
                  border: '1px solid var(--accent)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--accent)',
                  fontSize: '14px',
                }}
              >
                {seedMessage}
              </div>
            )}
          </div>

          <ExerciseSectionTabs />

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
                        autoFocus
                      />
                    </div>
                    <div style={{ flex: '1 1 200px' }}>
                      <Label htmlFor="new-category" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                        Category
                      </Label>
                      <CategoryField
                        id="new-category"
                        value={newCategory}
                        onChange={setNewCategory}
                        categories={categoryNames}
                      />
                    </div>
                  </div>
                  <div>
                    <Label htmlFor="new-form" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                      Form <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(how to perform it)</span>
                    </Label>
                    <textarea
                      id="new-form"
                      className="input"
                      value={newForm}
                      onChange={(e) => setNewForm(e.target.value)}
                      placeholder="e.g., Keep elbows tucked, drive feet into floor"
                      rows={2}
                      style={{ resize: 'vertical', minHeight: '60px' }}
                    />
                  </div>
                  <div>
                    <Label htmlFor="new-application" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                      Application <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(symptom &rarr; cause &rarr; what to change)</span>
                    </Label>
                    <textarea
                      id="new-application"
                      className="input"
                      value={newApplication}
                      onChange={(e) => setNewApplication(e.target.value)}
                      placeholder="e.g., Second set drops 3+ reps &rarr; load too high to hold &rarr; take 5lb off rather than cutting the set"
                      rows={2}
                      style={{ resize: 'vertical', minHeight: '60px' }}
                    />
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
            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              {sortedCategories.map((category, categoryIndex) => {
                const catColor = getCategoryColor(category);
                const categoryExercises = exercisesByCategory[category];
                const isExpanded = expandedCategories.has(category);

                return (
                  <Card key={category} className="animate-in" style={{ animationDelay: `${categoryIndex * 50}ms`, overflow: 'hidden' }}>
                    <button
                      type="button"
                      onClick={() => toggleCategory(category)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        width: '100%',
                        padding: 'var(--space-4) var(--space-5)',
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: 'inherit',
                        textAlign: 'left',
                      }}
                    >
                      <div className="flex items-center" style={{ gap: 'var(--space-3)' }}>
                        <div
                          className="workout-order"
                          style={{
                            width: '40px',
                            height: '40px',
                            fontSize: '16px',
                            flexShrink: 0,
                            background: `${catColor.bg}15`,
                            color: catColor.text,
                          }}
                        >
                          <Dumbbell style={{ width: '18px', height: '18px' }} />
                        </div>
                        <div>
                          <span
                            className="font-display"
                            style={{
                              fontSize: '17px',
                              fontWeight: 700,
                              letterSpacing: '0.02em',
                              color: 'var(--text-primary)',
                            }}
                          >
                            {category.toUpperCase()}
                          </span>
                          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '2px' }}>
                            {categoryExercises.length} exercise{categoryExercises.length !== 1 ? 's' : ''}
                          </p>
                        </div>
                      </div>
                      <ChevronDown
                        style={{
                          width: '20px',
                          height: '20px',
                          color: 'var(--text-muted)',
                          flexShrink: 0,
                          transition: 'transform var(--duration-normal) var(--ease-default)',
                          transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                        }}
                      />
                    </button>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateRows: isExpanded ? '1fr' : '0fr',
                        transition: 'grid-template-rows var(--duration-normal) var(--ease-default)',
                      }}
                    >
                      <div style={{ overflow: 'hidden' }}>
                        <div style={{ padding: '0 var(--space-5) var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                        {categoryExercises.map((exercise, exerciseIndex) => (
                          <div
                            key={exercise.doc_id}
                            className="interactive-item"
                            style={{
                              padding: 'var(--space-3) var(--space-4)',
                              background: 'var(--bg-tertiary)',
                              borderRadius: 'var(--radius-md)',
                              border: '1px solid var(--border-subtle)',
                              transition: 'all var(--duration-normal) var(--ease-default)',
                              overflow: 'hidden',
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
                                  {/* Same control as the add form: a category
                                      picked one way and typed the other is how
                                      a duplicate gets in. */}
                                  <div style={{ flex: '1 1 150px' }}>
                                    <CategoryField
                                      value={editCategory}
                                      onChange={setEditCategory}
                                      categories={categoryNames}
                                    />
                                  </div>
                                </div>
                                <textarea
                                  className="input"
                                  aria-label="Form"
                                  value={editForm}
                                  onChange={(e) => setEditForm(e.target.value)}
                                  placeholder="Form — how to perform it..."
                                  rows={2}
                                  style={{ resize: 'vertical', minHeight: '60px' }}
                                />
                                <textarea
                                  className="input"
                                  aria-label="Application"
                                  value={editApplication}
                                  onChange={(e) => setEditApplication(e.target.value)}
                                  placeholder="Application — symptom, likely cause, what to change..."
                                  rows={2}
                                  style={{ resize: 'vertical', minHeight: '60px' }}
                                />
                                {/* The four field groups (plan 0018): what a
                                    new set tile for this movement offers, and
                                    with what defaults. Disabled groups hide
                                    their inputs but keep their values, so
                                    re-enabling restores the configuration. */}
                                {editConfig && (
                                  <div className="field-config">
                                    <p className="field-config__title">Set tile fields</p>

                                    <div className="field-config__group">
                                      <label className="field-config__toggle">
                                        <input
                                          type="checkbox"
                                          checked={editConfig.reps_enabled}
                                          onChange={(e) => setEditConfig({ ...editConfig, reps_enabled: e.target.checked })}
                                        />
                                        Reps
                                      </label>
                                      {editConfig.reps_enabled && (
                                        <span className="field-config__defaults">
                                          <Label htmlFor="edit-default-reps">Default reps</Label>
                                          <Input
                                            id="edit-default-reps"
                                            type="number"
                                            inputMode="numeric"
                                            className="input--mono"
                                            value={editConfig.default_reps}
                                            onChange={(e) => setEditConfig({ ...editConfig, default_reps: e.target.value })}
                                            placeholder="blank"
                                            min={1}
                                            max={500}
                                          />
                                        </span>
                                      )}
                                    </div>

                                    <div className="field-config__group">
                                      <label className="field-config__toggle">
                                        <input
                                          type="checkbox"
                                          checked={editConfig.weight_enabled}
                                          onChange={(e) => setEditConfig({ ...editConfig, weight_enabled: e.target.checked })}
                                        />
                                        Weight
                                      </label>
                                      {editConfig.weight_enabled && (
                                        <span className="field-config__defaults">
                                          <Label htmlFor="edit-default-weight">Default weight</Label>
                                          <Input
                                            id="edit-default-weight"
                                            type="number"
                                            inputMode="decimal"
                                            className="input--mono"
                                            value={editConfig.default_weight_lb}
                                            onChange={(e) => setEditConfig({ ...editConfig, default_weight_lb: e.target.value })}
                                            placeholder="blank"
                                            min={0}
                                            max={2000}
                                          />
                                          <span className="field-config__unit">lb total</span>
                                        </span>
                                      )}
                                    </div>

                                    <div className="field-config__group">
                                      <label className="field-config__toggle">
                                        <input
                                          type="checkbox"
                                          checked={editConfig.distance_enabled}
                                          onChange={(e) => setEditConfig({ ...editConfig, distance_enabled: e.target.checked })}
                                        />
                                        Distance
                                      </label>
                                      {editConfig.distance_enabled && (
                                        <span className="field-config__defaults">
                                          <Label htmlFor="edit-default-distance">Default distance</Label>
                                          <Input
                                            id="edit-default-distance"
                                            type="number"
                                            inputMode="decimal"
                                            className="input--mono"
                                            value={editConfig.default_distance}
                                            onChange={(e) => setEditConfig({ ...editConfig, default_distance: e.target.value })}
                                            placeholder="blank"
                                            min={0}
                                          />
                                          <select
                                            aria-label="Distance unit"
                                            className="input"
                                            value={editConfig.default_distance_unit}
                                            onChange={(e) => setEditConfig({ ...editConfig, default_distance_unit: e.target.value })}
                                          >
                                            <option value="">unit</option>
                                            <option value="m">m</option>
                                            <option value="km">km</option>
                                            <option value="mi">mi</option>
                                            <option value="yd">yd</option>
                                          </select>
                                        </span>
                                      )}
                                    </div>

                                    <div className="field-config__group">
                                      <label className="field-config__toggle">
                                        <input
                                          type="checkbox"
                                          checked={editConfig.time_enabled}
                                          onChange={(e) => setEditConfig({ ...editConfig, time_enabled: e.target.checked })}
                                        />
                                        Time
                                      </label>
                                      {editConfig.time_enabled && (
                                        <span className="field-config__defaults">
                                          <Label htmlFor="edit-default-work">Work seconds</Label>
                                          <Input
                                            id="edit-default-work"
                                            type="number"
                                            inputMode="numeric"
                                            className="input--mono"
                                            value={editConfig.default_work_seconds}
                                            onChange={(e) => setEditConfig({ ...editConfig, default_work_seconds: e.target.value })}
                                            placeholder="blank"
                                            min={1}
                                            max={3600}
                                          />
                                          <Label htmlFor="edit-default-rest">Rest seconds</Label>
                                          <Input
                                            id="edit-default-rest"
                                            type="number"
                                            inputMode="numeric"
                                            className="input--mono"
                                            value={editConfig.default_rest_seconds}
                                            onChange={(e) => setEditConfig({ ...editConfig, default_rest_seconds: e.target.value })}
                                            placeholder="blank"
                                            min={0}
                                            max={3600}
                                          />
                                          <Label htmlFor="edit-default-rest-after">Rest after set seconds</Label>
                                          <Input
                                            id="edit-default-rest-after"
                                            type="number"
                                            inputMode="numeric"
                                            className="input--mono"
                                            value={editConfig.default_rest_after_seconds}
                                            onChange={(e) => setEditConfig({ ...editConfig, default_rest_after_seconds: e.target.value })}
                                            placeholder="blank"
                                            min={0}
                                            max={3600}
                                          />
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                )}
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
                              <div className="exercise-row">
                                <div className="flex items-start" style={{ gap: 'var(--space-3)', minWidth: 0, flex: '1 1 auto' }}>
                                  <div
                                    className="workout-order"
                                    style={{
                                      width: '36px',
                                      height: '36px',
                                      fontSize: '14px',
                                      flexShrink: 0,
                                      background: `${catColor.bg}15`,
                                      color: catColor.text,
                                    }}
                                  >
                                    {exerciseIndex + 1}
                                  </div>
                                  <div style={{ flex: '1 1 0', minWidth: 0 }}>
                                    <h3
                                      style={{
                                        fontFamily: 'var(--font-body)',
                                        fontSize: '16px',
                                        fontWeight: 600,
                                        color: 'var(--text-primary)',
                                        marginBottom: (exercise.use_count > 0 || exercise.form || exercise.application) ? 'var(--space-2)' : 0,
                                        wordBreak: 'break-word',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 'var(--space-2)',
                                        flexWrap: 'wrap',
                                      }}
                                    >
                                      {exercise.name}
                                    </h3>
                                    {/* Two fields, shown separately and
                                        labelled, because they answer different
                                        questions: form is how to perform the
                                        movement, application is what to change
                                        when something goes wrong. The agent
                                        writes the second one. */}
                                    {exercise.form && (
                                      <div
                                        className="flex items-start"
                                        style={{
                                          gap: 'var(--space-2)',
                                          marginBottom: 'var(--space-2)',
                                          padding: 'var(--space-2) var(--space-3)',
                                          background: 'var(--bg-secondary)',
                                          borderRadius: 'var(--radius-sm)',
                                          borderLeft: `3px solid ${catColor.border}`,
                                        }}
                                      >
                                        <FileText style={{ width: '14px', height: '14px', color: 'var(--text-muted)', flexShrink: 0, marginTop: '2px' }} />
                                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                                          {exercise.form}
                                        </p>
                                      </div>
                                    )}
                                    {exercise.application && (
                                      <div
                                        className="flex items-start"
                                        style={{
                                          gap: 'var(--space-2)',
                                          marginBottom: exercise.use_count > 0 ? 'var(--space-2)' : 0,
                                          padding: 'var(--space-2) var(--space-3)',
                                          background: 'var(--bg-secondary)',
                                          borderRadius: 'var(--radius-sm)',
                                          borderLeft: '3px solid var(--accent)',
                                        }}
                                      >
                                        <Lightbulb style={{ width: '14px', height: '14px', color: 'var(--accent)', flexShrink: 0, marginTop: '2px' }} />
                                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                                          {exercise.application}
                                        </p>
                                      </div>
                                    )}
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
                                </div>
                                <div className="exercise-row__actions flex items-center flex-wrap" style={{ gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
                                  {/* Whether a movement is in the movement break
                                      pool, with its default bout when it has
                                      one. Not a mobility flag — that
                                      judgement depends on the objective that
                                      day and is set per set on the day view
                                      (d7e4f2a91b83). This only says the
                                      movement needs no equipment and can be
                                      done for a timed interval. */}
                                  <button
                                    type="button"
                                    className={`movement-break-toggle${exercise.movement_break_enabled ? ' movement-break-toggle--on' : ''}`}
                                    aria-pressed={exercise.movement_break_enabled}
                                    aria-label={
                                      exercise.movement_break_enabled
                                        ? `Remove ${exercise.name} from movement breaks`
                                        : `Add ${exercise.name} to movement breaks`
                                    }
                                    disabled={updateExercise.isPending}
                                    onClick={() => toggleMovementBreak(exercise)}
                                  >
                                    <Coffee style={{ width: '14px', height: '14px' }} />
                                    {exercise.movement_break_enabled
                                      ? exercise.default_work_seconds != null
                                        ? `${exercise.default_work_seconds}s`
                                        : 'Break'
                                      : 'Break'}
                                  </button>
                                  {/* The rating saves on the spot: one
                                      click, where putting it behind Edit/Save
                                      would make judging a movement a
                                      three-step transaction. There is no
                                      mobility toggle here — whether a movement
                                      is mobility work depends on the objective
                                      that day, so it is set per set on the day
                                      view. */}
                                  <StarRating
                                    name={exercise.name}
                                    value={exercise.rating}
                                    disabled={updateExercise.isPending}
                                    onChange={(rating) =>
                                      updateExercise.mutate({
                                        id: exercise.doc_id,
                                        data: { rating },
                                      })
                                    }
                                  />
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
                      </div>
                    </div>
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
