import { useState, useMemo } from 'react';
import { format } from 'date-fns';
import { Calendar as CalendarIcon, Trash2, ArrowRight, Dumbbell } from 'lucide-react';
import Navigation from '@/components/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Calendar } from '@/components/ui/calendar';
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

  const handleDeleteSession = async (session: number) => {
    if (confirm(`Are you sure you want to delete session ${session}?`)) {
      await deleteSession.mutateAsync(session);
    }
  };

  const handleTransferSession = async (session: number) => {
    if (!transferDate) {
      alert('Please select a date');
      return;
    }

    const dateStr = format(transferDate, 'yyyy-MM-dd');

    if (confirm(`Transfer session ${session} to ${format(transferDate, 'MMM d, yyyy')}?`)) {
      await transferSession.mutateAsync({ session, date: dateStr });
      setSelectedSession(null);
      setShowCalendar(false);
    }
  };

  return (
    <>
      <Navigation />
      <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
        <div className="max-w-7xl mx-auto" style={{ padding: 'var(--space-6)' }}>
          {/* Header */}
          <div className="animate-in" style={{ marginBottom: 'var(--space-6)' }}>
            <h1
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: '24px',
                fontWeight: 600,
                color: 'var(--text-primary)',
                letterSpacing: '-0.01em',
                marginBottom: 'var(--space-2)',
              }}
            >
              UPCOMING WORKOUTS
            </h1>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Plan and manage your future training sessions
            </p>
          </div>

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
                Loading upcoming workouts...
              </p>
            </div>
          ) : sessionGroups.length > 0 ? (
            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
              {sessionGroups.map(({ session, workouts }, index) => (
                <Card key={session} className="animate-in" style={{ animationDelay: `${index * 50}ms` }}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle style={{ fontFamily: 'var(--font-display)', fontSize: '18px' }}>
                        SESSION {session}
                      </CardTitle>
                      <div className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                        <button
                          className="btn-secondary"
                          style={{ fontSize: '13px', padding: '8px 14px' }}
                          onClick={() => {
                            setSelectedSession(session);
                            setShowCalendar(!showCalendar || selectedSession !== session);
                          }}
                        >
                          <CalendarIcon style={{ width: '16px', height: '16px', marginRight: 'var(--space-2)' }} />
                          Transfer
                        </button>
                        <button
                          style={{
                            fontSize: '13px',
                            padding: '8px 14px',
                            background: 'var(--bg-tertiary)',
                            color: 'var(--error)',
                            border: '1px solid var(--error)',
                            borderRadius: 'var(--radius-sm)',
                            fontWeight: 600,
                            cursor: 'pointer',
                            transition: 'all var(--duration-normal)',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'var(--error)';
                            e.currentTarget.style.color = '#fff';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'var(--bg-tertiary)';
                            e.currentTarget.style.color = 'var(--error)';
                          }}
                          onClick={() => handleDeleteSession(session)}
                        >
                          <Trash2 style={{ width: '16px', height: '16px', display: 'inline', marginRight: 'var(--space-2)' }} />
                          Delete
                        </button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {showCalendar && selectedSession === session && (
                      <div style={{ marginBottom: 'var(--space-6)', padding: 'var(--space-4)', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-lg)' }}>
                        <div className="flex flex-col items-center" style={{ gap: 'var(--space-4)' }}>
                          <Calendar
                            mode="single"
                            selected={transferDate}
                            onSelect={setTransferDate}
                            style={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}
                          />
                          <button
                            className="btn-primary"
                            onClick={() => handleTransferSession(session)}
                            disabled={!transferDate}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 'var(--space-2)',
                              opacity: !transferDate ? 0.5 : 1,
                            }}
                          >
                            <ArrowRight style={{ width: '18px', height: '18px' }} />
                            Transfer to {transferDate && format(transferDate, 'MMM d, yyyy')}
                          </button>
                        </div>
                      </div>
                    )}

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                      {workouts.map((workout, workoutIndex) => (
                        <div
                          key={workout.doc_id}
                          style={{
                            padding: 'var(--space-4)',
                            background: 'var(--bg-tertiary)',
                            borderRadius: 'var(--radius-md)',
                          }}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center" style={{ gap: 'var(--space-3)' }}>
                                <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600 }}>
                                  #{workoutIndex + 1}
                                </span>
                                <div>
                                  <h3 style={{ fontWeight: 600, fontSize: '16px', color: 'var(--text-primary)' }}>
                                    {workout.exercise}
                                  </h3>
                                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                                    {workout.category}
                                  </p>
                                </div>
                              </div>
                              <div className="flex flex-wrap" style={{ marginTop: 'var(--space-2)', gap: 'var(--space-4)', fontSize: '13px' }}>
                                {workout.weight && (
                                  <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                                    {workout.weight} {workout.weight_unit}
                                  </span>
                                )}
                                {workout.reps && (
                                  <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                                    {workout.reps} reps
                                  </span>
                                )}
                                {workout.distance && (
                                  <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                                    {workout.distance} {workout.distance_unit}
                                  </span>
                                )}
                                {workout.time && (
                                  <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                                    {workout.time}
                                  </span>
                                )}
                                {workout.comment && (
                                  <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                                    {workout.comment}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div style={{ marginTop: 'var(--space-4)', fontSize: '13px', color: 'var(--text-muted)' }}>
                      {workouts.length} exercise{workouts.length > 1 ? 's' : ''} in this session
                    </div>
                  </CardContent>
                </Card>
              ))}
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
                  NO UPCOMING WORKOUTS
                </h3>
                <p style={{ color: 'var(--text-secondary)' }}>
                  No upcoming workouts planned.
                </p>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
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
