import { useState, useMemo, useEffect, useCallback } from 'react';
import { format } from 'date-fns';
import { Calendar as CalendarIcon, Trash2, ArrowRight, Dumbbell, Check, X } from 'lucide-react';
import Navigation from '@/components/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Calendar } from '@/components/ui/calendar';
import { Button } from '@/components/ui/button';
import {
  useUpcomingWorkouts,
  useDeleteUpcomingSession,
  useTransferSession
} from '@/hooks/useUpcoming';

const Upcoming = () => {
  const { data: upcomingWorkouts, isLoading } = useUpcomingWorkouts();
  const deleteSession = useDeleteUpcomingSession();
  const transferSession = useTransferSession();

  const [selectedSession, setSelectedSession] = useState<number | null>(null);
  const [transferDate, setTransferDate] = useState<Date | undefined>(new Date());
  const [showCalendar, setShowCalendar] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);

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
            <h1 className="page__title">UPCOMING WORKOUTS</h1>
            <p className="page__subtitle">Plan and manage your future training sessions</p>
          </div>

          {isLoading ? (
            <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
              <div className="loading-spinner inline-block" />
              <p className="mt-4 text-[var(--text-muted)]">Loading upcoming workouts...</p>
            </div>
          ) : sessionGroups.length > 0 ? (
            <div className="flex flex-col gap-6">
              {sessionGroups.map(({ session, workouts }) => (
                <Card key={session} className="animate-in">
                  <CardHeader>
                    <div className="flex items-center justify-between flex-wrap gap-4">
                      <CardTitle className="font-display text-xl tracking-tight">
                        SESSION {session}
                      </CardTitle>
                      <div className="flex items-center gap-3">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            setSelectedSession(session);
                            setShowCalendar(!showCalendar || selectedSession !== session);
                          }}
                        >
                          <CalendarIcon className="w-4 h-4" />
                          Transfer
                        </Button>
                        {confirmingDelete === session ? (
                          <div className="flex" style={{ gap: '4px' }}>
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => handleDeleteConfirm(session)}
                            >
                              <Check className="w-4 h-4" />
                              Confirm
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={handleDeleteCancel}
                            >
                              <X className="w-4 h-4" />
                            </Button>
                          </div>
                        ) : (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => handleDeleteClick(session)}
                          >
                            <Trash2 className="w-4 h-4" />
                            Delete
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {showCalendar && selectedSession === session && (
                      <div className="mb-6 p-4 bg-[var(--bg-tertiary)] rounded-[var(--radius-lg)]">
                        <div className="flex flex-col items-center gap-4">
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
                            <ArrowRight className="w-[18px] h-[18px]" />
                            Transfer to {transferDate && format(transferDate, 'MMM d, yyyy')}
                          </Button>
                        </div>
                      </div>
                    )}

                    <div className="flex flex-col gap-3">
                      {workouts.map((workout, workoutIndex) => (
                        <div key={workout.doc_id} className="data-item">
                          <div className="flex items-start justify-between w-full">
                            <div className="flex-1">
                              <div className="flex items-center gap-4">
                                <span className="text-[var(--text-muted)] font-mono text-sm font-semibold min-w-[28px]">
                                  #{workoutIndex + 1}
                                </span>
                                <div>
                                  <h3 className="font-semibold text-base text-[var(--text-primary)]">
                                    {workout.exercise}
                                  </h3>
                                  <p className="text-[13px] text-[var(--text-muted)] mt-1">
                                    {workout.category}
                                  </p>
                                </div>
                              </div>
                              <div className="flex flex-wrap mt-3 gap-5 text-[13px]">
                                {workout.weight && (
                                  <span className="font-semibold font-mono text-[var(--text-secondary)]">
                                    {workout.weight} {workout.weight_unit}
                                  </span>
                                )}
                                {workout.reps && (
                                  <span className="font-semibold font-mono text-[var(--text-secondary)]">
                                    {workout.reps} reps
                                  </span>
                                )}
                                {workout.distance && (
                                  <span className="font-semibold font-mono text-[var(--text-secondary)]">
                                    {workout.distance} {workout.distance_unit}
                                  </span>
                                )}
                                {workout.time && (
                                  <span className="font-semibold font-mono text-[var(--text-secondary)]">
                                    {workout.time}
                                  </span>
                                )}
                                {workout.comment && (
                                  <span className="text-[var(--text-muted)] italic">
                                    {workout.comment}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="mt-5 text-[13px] text-[var(--text-muted)]">
                      {workouts.length} exercise{workouts.length > 1 ? 's' : ''} in this session
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="border-2 border-dashed border-[var(--border)] bg-transparent">
              <CardContent className="p-12 text-center">
                <div className="w-20 h-20 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
                  <Dumbbell className="w-10 h-10 text-[var(--text-muted)]" />
                </div>
                <h3 className="font-display text-lg font-semibold mb-2">
                  NO UPCOMING WORKOUTS
                </h3>
                <p className="text-[var(--text-secondary)]">
                  No upcoming workouts planned.
                </p>
                <p className="text-[13px] text-[var(--text-muted)] mt-2">
                  Use the Wendler 5/3/1 generator or import workouts via CSV to plan your training.
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
