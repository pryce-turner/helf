import { useState, useMemo, useEffect, useCallback } from 'react';
import { format } from 'date-fns';
import { Calendar as CalendarIcon, Trash2, ArrowRight, Dumbbell, Check, X, Weight, Hash, MessageSquare, Edit3, Loader2 } from 'lucide-react';
import Navigation from '@/components/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Calendar } from '@/components/ui/calendar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import LiftoscriptEditor from '@/components/LiftoscriptEditor';
import PresetSelector from '@/components/PresetSelector';
import {
  useUpcomingWorkouts,
  useDeleteUpcomingSession,
  useTransferSession,
  useWendlerMaxes,
  usePresets,
  usePreset,
  useLiftoscriptGenerate,
} from '@/hooks/useUpcoming';
import type { PresetInfo } from '@/types/upcoming';

// Predefined colors for common categories (matching WorkoutSession)
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

const Upcoming = () => {
  const { data: upcomingWorkouts, isLoading } = useUpcomingWorkouts();
  const { data: wendlerMaxes } = useWendlerMaxes();
  const { data: presets } = usePresets();
  const deleteSession = useDeleteUpcomingSession();
  const transferSession = useTransferSession();
  const generateLiftoscript = useLiftoscriptGenerate();

  const [selectedSession, setSelectedSession] = useState<number | null>(null);
  const [transferDate, setTransferDate] = useState<Date | undefined>(new Date());
  const [showCalendar, setShowCalendar] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);

  // Program editor state
  const [showEditor, setShowEditor] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string>('custom');
  const [scriptContent, setScriptContent] = useState<string>('');
  const [numCycles, setNumCycles] = useState(4);
  const [squatMax, setSquatMax] = useState<string>('');
  const [benchMax, setBenchMax] = useState<string>('');
  const [deadliftMax, setDeadliftMax] = useState<string>('');
  const [editorError, setEditorError] = useState<string>('');
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  // Fetch preset content when a preset is selected
  const { data: presetContent } = usePreset(selectedPreset !== 'custom' ? selectedPreset : '');

  // Find the current preset info
  const currentPresetInfo = useMemo<PresetInfo | null>(() => {
    if (selectedPreset === 'custom' || !presets) return null;
    return presets.find(p => p.name === selectedPreset) || null;
  }, [selectedPreset, presets]);

  // Update script content when preset content is loaded
  useEffect(() => {
    if (presetContent?.script) {
      setScriptContent(presetContent.script);
    }
  }, [presetContent]);

  // Update 1RM inputs when maxes are loaded
  useEffect(() => {
    if (wendlerMaxes) {
      if (wendlerMaxes.squat) setSquatMax(String(Math.round(wendlerMaxes.squat)));
      if (wendlerMaxes.bench) setBenchMax(String(Math.round(wendlerMaxes.bench)));
      if (wendlerMaxes.deadlift) setDeadliftMax(String(Math.round(wendlerMaxes.deadlift)));
    }
  }, [wendlerMaxes]);

  // Auto-cancel delete confirmation after 3 seconds
  useEffect(() => {
    if (confirmingDelete !== null) {
      const timer = setTimeout(() => setConfirmingDelete(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [confirmingDelete]);

  const handleDeleteClick = useCallback((session: number) => {
    setConfirmingDelete(session);
  }, []);

  const handleDeleteConfirm = useCallback(async (session: number) => {
    await deleteSession.mutateAsync(session);
    setConfirmingDelete(null);
  }, [deleteSession]);

  const handleDeleteCancel = useCallback(() => {
    setConfirmingDelete(null);
  }, []);

  const handlePresetChange = (presetName: string) => {
    setSelectedPreset(presetName);
    if (presetName === 'custom') {
      setScriptContent('');
    }
    setEditorError('');
  };

  const handleGenerateClick = () => {
    if (!scriptContent.trim()) {
      setEditorError('Please enter a program script');
      return;
    }
    
    // Check if we need to show confirmation dialog
    if (upcomingWorkouts && upcomingWorkouts.length > 0) {
      setShowConfirmDialog(true);
    } else {
      performGenerate();
    }
  };

  const performGenerate = async () => {
    setEditorError('');
    try {
      await generateLiftoscript.mutateAsync({
        script: scriptContent,
        squat_max: squatMax ? parseFloat(squatMax) : null,
        bench_max: benchMax ? parseFloat(benchMax) : null,
        deadlift_max: deadliftMax ? parseFloat(deadliftMax) : null,
        num_cycles: numCycles,
      });
      setShowEditor(false);
      setShowConfirmDialog(false);
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const message = axiosError?.response?.data?.detail || 'Failed to generate workouts';
      setEditorError(message);
      setShowConfirmDialog(false);
    }
  };

  // Group workouts by session
  const sessionGroups = useMemo(() => {
    if (!upcomingWorkouts) return [];

    const groups = new Map<number, typeof upcomingWorkouts>();
    upcomingWorkouts.forEach(workout => {
      if (!groups.has(workout.session)) {
        groups.set(workout.session, []);
      }
      groups.get(workout.session)!.push(workout);
    });

    return Array.from(groups.entries())
      .sort(([a], [b]) => a - b)
      .map(([session, workouts]) => ({
        session,
        workouts: workouts.sort((a, b) => a.doc_id - b.doc_id),
      }));
  }, [upcomingWorkouts]);

  const handleTransferSession = async (session: number) => {
    if (!transferDate) {
      alert('Please select a date');
      return;
    }

    const dateStr = format(transferDate, 'yyyy-MM-dd');
    await transferSession.mutateAsync({ session, date: dateStr });
    setSelectedSession(null);
    setShowCalendar(false);
  };

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content">
          {/* Header */}
          <div className="page__header animate-in">
            <div className="flex items-start justify-between flex-wrap" style={{ gap: 'var(--space-4)' }}>
              <div>
                <h1 className="page__title">UPCOMING WORKOUTS</h1>
                <p className="page__subtitle">Plan and manage your future training sessions</p>
              </div>
              <Button onClick={() => setShowEditor(!showEditor)}>
                <Edit3 style={{ width: '18px', height: '18px' }} />
                {showEditor ? 'Close Editor' : 'Edit Program'}
              </Button>
            </div>
          </div>

          {/* Program Editor */}
          {showEditor && (
            <Card className="animate-in" style={{ marginBottom: 'var(--space-6)' }}>
              <CardHeader>
                <CardTitle className="font-display text-xl tracking-tight">
                  PROGRAM EDITOR
                </CardTitle>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                  Write or select a program template to generate upcoming workouts
                </p>
              </CardHeader>
              <CardContent>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
                  {/* Preset and Cycles Row */}
                  <div style={{ display: 'flex', alignItems: 'flex-end', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
                    <div>
                      <Label style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                        Preset
                      </Label>
                      <PresetSelector
                        value={selectedPreset}
                        onChange={handlePresetChange}
                        presets={presets || []}
                      />
                    </div>
                    {currentPresetInfo?.requires_maxes && (
                      <div>
                        <Label htmlFor="num-cycles" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                          Cycles
                        </Label>
                        <Input
                          id="num-cycles"
                          type="number"
                          min={1}
                          max={12}
                          value={numCycles}
                          onChange={(e) => setNumCycles(parseInt(e.target.value) || 4)}
                          style={{ maxWidth: '80px' }}
                        />
                      </div>
                    )}
                  </div>

                  {/* 1RM Overrides - only show when preset requires maxes */}
                  {currentPresetInfo?.requires_maxes && (
                    <div
                      style={{
                        padding: 'var(--space-4)',
                        background: 'var(--bg-tertiary)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-subtle)',
                      }}
                    >
                      <p
                        style={{
                          fontSize: '12px',
                          fontWeight: 600,
                          color: 'var(--text-muted)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.05em',
                          marginBottom: 'var(--space-3)',
                        }}
                      >
                        1RM Overrides
                      </p>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 'var(--space-4)' }}>
                        <div>
                          <Label htmlFor="squat-max" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                            Squat (lbs)
                          </Label>
                          <Input
                            id="squat-max"
                            type="number"
                            placeholder={wendlerMaxes?.squat ? `${Math.round(wendlerMaxes.squat)}` : 'Enter'}
                            value={squatMax}
                            onChange={(e) => setSquatMax(e.target.value)}
                          />
                        </div>
                        <div>
                          <Label htmlFor="bench-max" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                            Bench (lbs)
                          </Label>
                          <Input
                            id="bench-max"
                            type="number"
                            placeholder={wendlerMaxes?.bench ? `${Math.round(wendlerMaxes.bench)}` : 'Enter'}
                            value={benchMax}
                            onChange={(e) => setBenchMax(e.target.value)}
                          />
                        </div>
                        <div>
                          <Label htmlFor="deadlift-max" style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                            Deadlift (lbs)
                          </Label>
                          <Input
                            id="deadlift-max"
                            type="number"
                            placeholder={wendlerMaxes?.deadlift ? `${Math.round(wendlerMaxes.deadlift)}` : 'Enter'}
                            value={deadliftMax}
                            onChange={(e) => setDeadliftMax(e.target.value)}
                          />
                        </div>
                      </div>
                      <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                        Auto-detected from workout history
                      </p>
                    </div>
                  )}

                  {/* Editor */}
                  <LiftoscriptEditor
                    value={scriptContent}
                    onChange={(value) => {
                      setScriptContent(value);
                      setEditorError('');
                    }}
                    error={editorError}
                  />

                  {/* Actions */}
                  <div className="flex" style={{ gap: 'var(--space-3)', justifyContent: 'flex-end' }}>
                    <Button variant="secondary" onClick={() => setShowEditor(false)}>
                      Cancel
                    </Button>
                    <Button
                      onClick={handleGenerateClick}
                      disabled={generateLiftoscript.isPending || !scriptContent.trim()}
                    >
                      {generateLiftoscript.isPending ? (
                        <>
                          <Loader2 style={{ width: '18px', height: '18px' }} className="animate-spin" />
                          Generating...
                        </>
                      ) : (
                        'Generate'
                      )}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Confirmation Dialog */}
          {showConfirmDialog && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0, 0, 0, 0.7)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
                padding: 'var(--space-4)',
              }}
              onClick={() => setShowConfirmDialog(false)}
            >
              <Card
                className="animate-in"
                style={{ maxWidth: '450px', width: '100%' }}
                onClick={(e) => e.stopPropagation()}
              >
                <CardHeader>
                  <CardTitle className="font-display text-xl tracking-tight">
                    Overwrite Upcoming Workouts?
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-4)', lineHeight: 1.6 }}>
                    This will delete all {upcomingWorkouts?.length || 0} upcoming workouts and generate new ones from your program.
                  </p>
                  <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: 'var(--space-6)' }}>
                    This action cannot be undone.
                  </p>
                  <div className="flex" style={{ gap: 'var(--space-3)', justifyContent: 'flex-end' }}>
                    <Button variant="secondary" onClick={() => setShowConfirmDialog(false)}>
                      Cancel
                    </Button>
                    <Button
                      onClick={performGenerate}
                      disabled={generateLiftoscript.isPending}
                    >
                      {generateLiftoscript.isPending ? (
                        <>
                          <Loader2 style={{ width: '18px', height: '18px' }} className="animate-spin" />
                          Generating...
                        </>
                      ) : (
                        'Confirm Generate'
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {isLoading ? (
            <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
              <div className="loading-spinner inline-block" />
              <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
                Loading upcoming workouts...
              </p>
            </div>
          ) : sessionGroups.length > 0 ? (
            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
              {sessionGroups.map(({ session, workouts }, sessionIndex) => (
                <Card key={session} className="animate-in" style={{ animationDelay: `${sessionIndex * 50}ms` }}>
                  <CardHeader>
                    <div className="flex items-center justify-between flex-wrap" style={{ gap: 'var(--space-4)' }}>
                      <div className="flex items-center" style={{ gap: 'var(--space-3)' }}>
                        <div className="workout-order" style={{ width: '44px', height: '44px', fontSize: '18px' }}>
                          {session}
                        </div>
                        <div>
                          <CardTitle className="font-display text-xl tracking-tight">
                            SESSION {session}
                          </CardTitle>
                          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                            {workouts.length} exercise{workouts.length !== 1 ? 's' : ''} planned
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            setSelectedSession(session);
                            setShowCalendar(!showCalendar || selectedSession !== session);
                          }}
                        >
                          <CalendarIcon style={{ width: '16px', height: '16px' }} />
                          Transfer
                        </Button>
                        {confirmingDelete === session ? (
                          <div className="flex" style={{ gap: 'var(--space-1)' }}>
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => handleDeleteConfirm(session)}
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
                            onClick={() => handleDeleteClick(session)}
                          >
                            <Trash2 style={{ width: '16px', height: '16px' }} />
                            Delete
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {showCalendar && selectedSession === session && (
                      <div
                        style={{
                          marginBottom: 'var(--space-6)',
                          padding: 'var(--space-5)',
                          background: 'var(--bg-tertiary)',
                          borderRadius: 'var(--radius-lg)',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        <p
                          style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: 'var(--text-muted)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                            marginBottom: 'var(--space-4)',
                            textAlign: 'center',
                          }}
                        >
                          Select transfer date
                        </p>
                        <div className="flex flex-col items-center" style={{ gap: 'var(--space-4)' }}>
                          <Calendar
                            mode="single"
                            selected={transferDate}
                            onSelect={setTransferDate}
                            className="rounded-[var(--radius-md)] border border-[var(--border)]"
                          />
                          <Button
                            onClick={() => handleTransferSession(session)}
                            disabled={!transferDate}
                          >
                            <ArrowRight style={{ width: '18px', height: '18px' }} />
                            Transfer to {transferDate && format(transferDate, 'MMM d, yyyy')}
                          </Button>
                        </div>
                      </div>
                    )}

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                      {workouts.map((workout, workoutIndex) => {
                        const catColor = getCategoryColor(workout.category);
                        return (
                          <div
                            key={workout.doc_id}
                            style={{
                              padding: 'var(--space-4)',
                              background: 'var(--bg-tertiary)',
                              borderRadius: 'var(--radius-md)',
                              border: '1px solid var(--border-subtle)',
                            }}
                          >
                            <div className="flex items-start" style={{ gap: 'var(--space-4)' }}>
                              <div
                                className="workout-order"
                                style={{
                                  width: '36px',
                                  height: '36px',
                                  fontSize: '14px',
                                  background: 'rgba(234, 179, 8, 0.1)',
                                  color: 'var(--warning)',
                                }}
                              >
                                {workoutIndex + 1}
                              </div>
                              <div className="flex-1">
                                <div className="flex items-center flex-wrap" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
                                  <h3
                                    style={{
                                      fontFamily: 'var(--font-body)',
                                      fontSize: '16px',
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
                                <div className="flex flex-wrap" style={{ gap: 'var(--space-2)' }}>
                                  {workout.weight && (
                                    <div className="workout-chip">
                                      <Weight style={{ width: '14px', height: '14px', color: 'var(--warning)' }} />
                                      <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                        {workout.weight} {workout.weight_unit}
                                      </span>
                                    </div>
                                  )}
                                  {workout.reps && (
                                    <div className="workout-chip">
                                      <Hash style={{ width: '14px', height: '14px', color: 'var(--warning)' }} />
                                      <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                        {workout.reps} reps
                                      </span>
                                    </div>
                                  )}
                                  {workout.distance && (
                                    <div className="workout-chip">
                                      <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                        {workout.distance} {workout.distance_unit}
                                      </span>
                                    </div>
                                  )}
                                  {workout.time && (
                                    <div className="workout-chip">
                                      <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                        {workout.time}
                                      </span>
                                    </div>
                                  )}
                                  {workout.comment && (
                                    <div className="workout-chip">
                                      <MessageSquare style={{ width: '14px', height: '14px', color: 'var(--text-muted)' }} />
                                      <span className="workout-chip__comment" style={{ fontSize: '13px' }}>
                                        {workout.comment}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
              <CardContent className="empty-state">
                <div className="empty-state__icon">
                  <Dumbbell style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
                </div>
                <h3 className="empty-state__title">NO UPCOMING WORKOUTS</h3>
                <p className="empty-state__text">No upcoming workouts planned.</p>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                  Use the program editor to generate workouts from a template.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
};

export default Upcoming;
