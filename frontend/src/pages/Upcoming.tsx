import { useState, useMemo, useEffect } from 'react';
import { format } from 'date-fns';
import { Calendar as CalendarIcon, Trash2, ArrowRight, Dumbbell, Check, X, Weight, Hash, MessageSquare, Edit3, Loader2, Activity } from 'lucide-react';
import Navigation from '@/components/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Calendar } from '@/components/ui/calendar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import LiftoscriptEditor from '@/components/LiftoscriptEditor';
import PresetSelector from '@/components/PresetSelector';
import WorkoutSectionTabs from '@/components/WorkoutSectionTabs';
import {
  useUpcomingWorkouts,
  useDeleteUpcomingSession,
  useTransferSession,
  usePresets,
  usePreset,
  useLiftoscriptGenerate,
  useLastLiftoscriptProgram,
} from '@/hooks/useUpcoming';
import { useLastMobilitySession } from '@/hooks/useMobility';
import type { UpcomingSession, UpcomingWorkout } from '@/types/upcoming';
import type { MobilityLastSession } from '@/types/mobility';

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

/**
 * A movement as it reads in a routine, folded back from its rows.
 *
 * Storage is one row per set, because that is the grain the user logs against
 * — "8 and then 10 reps" needs two rows to land in. A routine is read as
 * "2 x 8" though, so consecutive rows for the same movement are folded here
 * for display only. Consecutive, not grouped: a movement that legitimately
 * appears twice in a session stays two entries.
 */
interface Movement {
  exercise: string;
  category: string;
  is_mobility: boolean;
  sets: number;
  reps: number | null;
  weight: number | null;
  comment: string | null;
}

const foldMovements = (items: UpcomingWorkout[]): Movement[] =>
  items.reduce<Movement[]>((movements, item) => {
    const last = movements[movements.length - 1];
    const sameAsLast =
      last &&
      last.exercise === item.exercise &&
      last.is_mobility === item.is_mobility &&
      last.reps === item.reps &&
      last.weight === item.weight &&
      last.comment === item.comment;

    if (sameAsLast) {
      last.sets += 1;
      return movements;
    }

    movements.push({
      exercise: item.exercise,
      category: item.category,
      is_mobility: item.is_mobility,
      sets: 1,
      reps: item.reps,
      weight: item.weight,
      comment: item.comment,
    });
    return movements;
  }, []);

const prescription = (movement: Movement) => {
  const scheme =
    movement.reps != null ? `${movement.sets} x ${movement.reps}` : `${movement.sets} sets`;
  return movement.weight != null ? `${scheme} @ ${movement.weight}lb` : scheme;
};

/** The flag rendered small: which sets of the workout are the mobility element. */
const MobilityBadge = () => (
  <span
    className="category-badge"
    style={{
      border: '1px solid var(--warning)',
      color: 'var(--warning)',
      background: 'rgba(234, 179, 8, 0.1)',
    }}
  >
    mobility
  </span>
);

/** The last mobility session that was run, and everything that was said about it. */
const LastSessionCard = ({ session }: { session: MobilityLastSession }) => {
  const commented = session.sets.filter((s) => s.comment);

  return (
    <Card className="animate-in" style={{ marginTop: 'var(--space-6)' }}>
      <CardHeader>
        <CardTitle className="font-display text-lg tracking-tight">
          Last mobility session
        </CardTitle>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
          {format(new Date(`${session.date}T12:00:00`), 'EEEE, MMMM d')} &middot;{' '}
          {session.sets.length} set{session.sets.length !== 1 ? 's' : ''} logged
        </p>
      </CardHeader>
      <CardContent>
        {commented.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <p
              style={{
                fontSize: '12px',
                fontWeight: 600,
                color: 'var(--text-muted)',
              }}
            >
              What you noted
            </p>
            {commented.map((set, index) => (
              <div
                key={index}
                className="flex items-start"
                style={{ gap: 'var(--space-3)' }}
              >
                <MessageSquare
                  style={{
                    width: '16px',
                    height: '16px',
                    color: 'var(--text-muted)',
                    flexShrink: 0,
                    marginTop: '3px',
                  }}
                />
                <div style={{ minWidth: 0 }}>
                  <span style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
                    {set.comment}
                  </span>
                  <span
                    style={{
                      fontSize: '12px',
                      color: 'var(--text-muted)',
                      marginLeft: 'var(--space-2)',
                    }}
                  >
                    &mdash; {set.exercise}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
            Nothing was noted on this session. Comments on logged sets are what the
            next one gets written from.
          </p>
        )}
      </CardContent>
    </Card>
  );
};

/**
 * One session of the queue, whatever its author.
 *
 * Both authors' sessions share the card, the calendar popover and the delete
 * confirm; what differs is the middle. An agent-written session shows its
 * rationale and reads as a routine ("2 x 8 @ 30lb") — the agent writes it to
 * be read. A generated session shows every row with its chips — the program
 * editor is its explanation, and the rows are all that is there.
 */
const SessionCard = ({ session }: { session: UpcomingSession }) => {
  const deleteSession = useDeleteUpcomingSession();
  const transferSession = useTransferSession();

  const [transferDate, setTransferDate] = useState<Date | undefined>(new Date());
  const [showCalendar, setShowCalendar] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const movements = useMemo(() => foldMovements(session.items), [session.items]);
  const isAgentSession = session.label !== null;

  // Auto-cancel delete confirmation after 3 seconds
  useEffect(() => {
    if (confirmingDelete) {
      const timer = setTimeout(() => setConfirmingDelete(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [confirmingDelete]);

  const handleTransfer = async () => {
    if (!transferDate) return;
    // Local time, never `toISOString()`. `workouts.date` is a string prefix,
    // so a UTC date puts an evening session on tomorrow west of Greenwich.
    await transferSession.mutateAsync({
      session: session.session,
      date: format(transferDate, 'yyyy-MM-dd'),
    });
    setShowCalendar(false);
  };

  return (
    <Card className="animate-in">
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap" style={{ gap: 'var(--space-4)' }}>
          <div className="flex items-center" style={{ gap: 'var(--space-3)' }}>
            <div className="workout-order" style={{ width: '44px', height: '44px', fontSize: '18px' }}>
              {session.session}
            </div>
            <div>
              <CardTitle className="font-display text-xl tracking-tight">
                {isAgentSession ? session.label : `Session ${session.session}`}
              </CardTitle>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                {isAgentSession
                  ? `${movements.length} movement${movements.length !== 1 ? 's' : ''}`
                  : `${session.items.length} exercise${session.items.length !== 1 ? 's' : ''} planned`}
                {session.generated_at
                  ? ` · written ${format(new Date(session.generated_at), 'MMM d')}`
                  : ''}
              </p>
            </div>
          </div>
          <div className="flex items-center" style={{ gap: 'var(--space-2)' }}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowCalendar(!showCalendar)}
            >
              <CalendarIcon style={{ width: '16px', height: '16px' }} />
              Transfer
            </Button>
            {confirmingDelete ? (
              <div className="flex" style={{ gap: 'var(--space-1)' }}>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={async () => {
                    await deleteSession.mutateAsync(session.session);
                    setConfirmingDelete(false);
                  }}
                >
                  <Check style={{ width: '16px', height: '16px' }} />
                  Confirm
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setConfirmingDelete(false)}
                >
                  <X style={{ width: '16px', height: '16px' }} />
                </Button>
              </div>
            ) : (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setConfirmingDelete(true)}
              >
                <Trash2 style={{ width: '16px', height: '16px' }} />
                Delete
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {showCalendar && (
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
                onClick={handleTransfer}
                disabled={!transferDate || transferSession.isPending}
              >
                <ArrowRight style={{ width: '16px', height: '16px' }} />
                Transfer to {transferDate && format(transferDate, 'MMM d, yyyy')}
              </Button>
            </div>
          </div>
        )}

        {session.rationale && (
          <div
            style={{
              marginBottom: 'var(--space-6)',
              padding: 'var(--space-4)',
              background: 'var(--bg-tertiary)',
              borderRadius: 'var(--radius-md)',
              borderLeft: '3px solid var(--accent)',
            }}
          >
            <p
              style={{
                fontSize: '14px',
                color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap',
                lineHeight: 1.6,
              }}
            >
              {session.rationale}
            </p>
          </div>
        )}

        {isAgentSession ? (
          /* The agent's routine: folded to the way it is read, "2 x 8". */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {movements.map((movement, index) => (
              <div
                key={`${movement.exercise}-${index}`}
                className="flex items-center"
                style={{
                  gap: 'var(--space-3)',
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                <div className="workout-order-compact">{index + 1}</div>
                <div style={{ minWidth: 0, flex: '1 1 auto' }}>
                  <div
                    className="flex items-center flex-wrap"
                    style={{ gap: 'var(--space-2)' }}
                  >
                    <span
                      style={{
                        fontWeight: 600,
                        fontSize: '15px',
                        color: 'var(--text-primary)',
                      }}
                    >
                      {movement.exercise}
                    </span>
                    {movement.is_mobility && <MobilityBadge />}
                  </div>
                  {movement.comment && (
                    <div
                      style={{
                        fontSize: '13px',
                        color: 'var(--text-secondary)',
                        marginTop: '2px',
                      }}
                    >
                      {movement.comment}
                    </div>
                  )}
                </div>
                <div
                  className="workout-chip-compact"
                  style={{ flexShrink: 0 }}
                >
                  <span className="workout-chip__value">
                    {prescription(movement)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* A generated session: every row, with its chips. */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {session.items.map((workout, workoutIndex) => {
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
                    <div className="flex-1 log-line" style={{ minWidth: 0 }}>
                      <div className="log-line__title">
                        <h3
                          style={{
                            fontFamily: 'var(--font-body)',
                            fontSize: '16px',
                            fontWeight: 600,
                            color: 'var(--text-primary)',
                            whiteSpace: 'nowrap',
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
                        {workout.is_mobility && <MobilityBadge />}
                      </div>
                      <div className="log-line__chips">
                        {workout.weight && (
                          <div className="workout-chip">
                            <Weight style={{ width: '16px', height: '16px', color: 'var(--text-muted)' }} />
                            <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                              {workout.weight} {workout.weight_unit}
                            </span>
                          </div>
                        )}
                        {workout.reps && (
                          <div className="workout-chip">
                            <Hash style={{ width: '16px', height: '16px', color: 'var(--text-muted)' }} />
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
                            <MessageSquare style={{ width: '16px', height: '16px', color: 'var(--text-muted)' }} />
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
        )}
      </CardContent>
    </Card>
  );
};

const Upcoming = () => {
  const { data: sessions, isLoading } = useUpcomingWorkouts();
  const { data: lastSession } = useLastMobilitySession();
  const { data: presets } = usePresets();
  const { data: lastProgram } = useLastLiftoscriptProgram();
  const generateLiftoscript = useLiftoscriptGenerate();

  const [showEditor, setShowEditor] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string>('custom');
  const [scriptContent, setScriptContent] = useState<string>('');
  const [numCycles, setNumCycles] = useState('4');
  const [editorError, setEditorError] = useState<string>('');
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [lastAppliedPreset, setLastAppliedPreset] = useState<string>('');

  const { data: presetContent } = usePreset(selectedPreset !== 'custom' ? selectedPreset : '');

  // Update script content when preset content is loaded
  if (presetContent?.script && presetContent.name !== lastAppliedPreset) {
    setScriptContent(presetContent.script);
    setLastAppliedPreset(presetContent.name);
  }

  const handlePresetChange = (presetName: string) => {
    setSelectedPreset(presetName);
    if (presetName === 'custom') {
      // Custom is the program behind the queue, when there is one.
      setScriptContent(lastProgram?.script ?? '');
    }
    setEditorError('');
  };

  // The editor opens on the last generated program rather than an empty box.
  // Only into an empty Custom editor: anything typed this visit, or a
  // built-in program picked, is left alone.
  const toggleEditor = () => {
    if (!showEditor && selectedPreset === 'custom' && !scriptContent && lastProgram) {
      setScriptContent(lastProgram.script);
      setNumCycles(String(lastProgram.num_cycles));
    }
    setShowEditor(!showEditor);
  };

  const showingLastProgram =
    selectedPreset === 'custom' && !!lastProgram && scriptContent === lastProgram.script;
  const lastGeneratedOn = lastProgram
    ? format(new Date(`${lastProgram.generated_at.replace(' ', 'T')}Z`), 'MMM d, yyyy')
    : '';

  const handleGenerateClick = () => {
    if (!scriptContent.trim()) {
      setEditorError('Please enter a program script');
      return;
    }

    // Check if we need to show confirmation dialog
    if (sessions && sessions.length > 0) {
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
        num_cycles: parseInt(numCycles) || 4,
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

  const totalSets = sessions?.reduce((n, s) => n + s.items.length, 0) ?? 0;
  // Named in the warning: generating wipes these along with everything else.
  const agentLabels = sessions?.filter((s) => s.label).map((s) => s.label!) ?? [];

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          {/* Header */}
          <div className="page__header animate-in">
            <div className="flex items-start justify-between flex-wrap" style={{ gap: 'var(--space-4)' }}>
              <div>
                <h1 className="page__title">Upcoming</h1>
                <p className="page__subtitle">Plan and manage your future training sessions</p>
              </div>
              <Button onClick={toggleEditor}>
                <Edit3 style={{ width: '16px', height: '16px' }} />
                {showEditor ? 'Close editor' : 'Edit program'}
              </Button>
            </div>
          </div>

          <WorkoutSectionTabs />

          {/* Program Editor */}
          {showEditor && (
            <Card className="animate-in" style={{ marginBottom: 'var(--space-6)' }}>
              <CardHeader>
                <CardTitle className="font-display text-xl tracking-tight">
                  Program editor
                </CardTitle>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                  {showingLastProgram
                    ? `The program last generated, on ${lastGeneratedOn}`
                    : 'Write or select a program template to generate upcoming workouts'}
                </p>
              </CardHeader>
              <CardContent>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
                  {/* Built-in program and cycles row */}
                  <div style={{ display: 'flex', alignItems: 'flex-end', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
                    <div>
                      <Label style={{ marginBottom: 'var(--space-2)', display: 'block' }}>
                        Built-in program
                      </Label>
                      <PresetSelector
                        value={selectedPreset}
                        onChange={handlePresetChange}
                        presets={presets || []}
                      />
                    </div>
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
                        onChange={(e) => setNumCycles(e.target.value)}
                        onBlur={(e) => {
                          const val = parseInt(e.target.value);
                          if (isNaN(val) || val < 1) setNumCycles('1');
                          else if (val > 12) setNumCycles('12');
                        }}
                        style={{ maxWidth: '80px' }}
                      />
                    </div>
                  </div>

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
                          <Loader2 style={{ width: '16px', height: '16px' }} className="animate-spin" />
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
                    Overwrite upcoming workouts?
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-4)', lineHeight: 1.6 }}>
                    This will delete all {totalSets} planned sets across {sessions?.length || 0}{' '}
                    session{(sessions?.length || 0) !== 1 ? 's' : ''} and generate new ones from
                    your program.
                  </p>
                  {agentLabels.length > 0 && (
                    <p style={{ color: 'var(--warning)', fontSize: '14px', marginBottom: 'var(--space-4)', lineHeight: 1.6 }}>
                      <Activity style={{ width: '16px', height: '16px', display: 'inline', verticalAlign: '-2px' }} />{' '}
                      Including the agent-written {agentLabels.length === 1 ? 'session' : 'sessions'}{' '}
                      {agentLabels.map((l) => `'${l}'`).join(', ')} — generating does not spare it.
                    </p>
                  )}
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
                          <Loader2 style={{ width: '16px', height: '16px' }} className="animate-spin" />
                          Generating...
                        </>
                      ) : (
                        'Generate and overwrite'
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
          ) : sessions && sessions.length > 0 ? (
            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
              {sessions.map((session) => (
                <SessionCard key={session.session} session={session} />
              ))}
            </div>
          ) : (
            <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
              <CardContent className="empty-state">
                <div className="empty-state__icon">
                  <Dumbbell style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
                </div>
                <h3 className="empty-state__title">No upcoming workouts</h3>
                <p className="empty-state__text">No upcoming workouts planned.</p>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                  Use the program editor to generate workouts from a template, or ask
                  the agent to write a mobility session.
                </p>
              </CardContent>
            </Card>
          )}

          {lastSession && <LastSessionCard session={lastSession} />}
        </div>
      </div>
    </>
  );
};

export default Upcoming;
