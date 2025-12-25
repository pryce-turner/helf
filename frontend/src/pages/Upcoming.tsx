import { useState, useMemo } from 'react';
import { format } from 'date-fns';
import { Calendar as CalendarIcon, Trash2, ArrowRight } from 'lucide-react';
import Navigation from '@/components/Navigation';
import { Button } from '@/components/ui/button';
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
        workouts: workouts.sort((a, b) => a.id - b.id),
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
    <div className="min-h-screen">
      <Navigation />

      <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-2">Upcoming Workouts</h1>
          <p className="text-muted-foreground">
            Plan and manage your future training sessions
          </p>
        </div>

        {isLoading ? (
          <div className="text-center py-12 text-muted-foreground">Loading upcoming workouts...</div>
        ) : sessionGroups.length > 0 ? (
          <div className="space-y-6">
            {sessionGroups.map(({ session, workouts }) => (
              <Card key={session}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Session {session}</CardTitle>
                    <div className="flex items-center space-x-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setSelectedSession(session);
                          setShowCalendar(!showCalendar || selectedSession !== session);
                        }}
                      >
                        <CalendarIcon className="h-4 w-4 mr-2" />
                        Transfer to Date
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDeleteSession(session)}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete Session
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {showCalendar && selectedSession === session && (
                    <div className="mb-6 p-4 bg-accent/50 rounded-lg">
                      <div className="flex flex-col items-center space-y-4">
                        <Calendar
                          mode="single"
                          selected={transferDate}
                          onSelect={setTransferDate}
                          className="rounded-md border"
                        />
                        <Button
                          onClick={() => handleTransferSession(session)}
                          disabled={!transferDate}
                        >
                          <ArrowRight className="h-4 w-4 mr-2" />
                          Transfer to {transferDate && format(transferDate, 'MMM d, yyyy')}
                        </Button>
                      </div>
                    </div>
                  )}

                  <div className="space-y-2">
                    {workouts.map((workout, index) => (
                      <div
                        key={workout.id}
                        className="p-4 bg-accent/30 rounded-lg"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center space-x-3">
                              <span className="text-muted-foreground font-mono">#{index + 1}</span>
                              <div>
                                <h3 className="font-semibold text-lg">{workout.exercise}</h3>
                                <p className="text-sm text-muted-foreground">{workout.category}</p>
                              </div>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-4 text-sm">
                              {workout.weight && (
                                <span className="font-medium">
                                  {workout.weight} {workout.weight_unit}
                                </span>
                              )}
                              {workout.reps && (
                                <span className="font-medium">
                                  {workout.reps} reps
                                </span>
                              )}
                              {workout.distance && (
                                <span className="font-medium">
                                  {workout.distance} {workout.distance_unit}
                                </span>
                              )}
                              {workout.time && (
                                <span className="font-medium">
                                  {workout.time}
                                </span>
                              )}
                              {workout.comment && (
                                <span className="text-muted-foreground italic">
                                  {workout.comment}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 text-sm text-muted-foreground">
                    {workouts.length} exercise{workouts.length > 1 ? 's' : ''} in this session
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="p-12 text-center">
              <p className="text-muted-foreground">No upcoming workouts planned.</p>
              <p className="text-sm text-muted-foreground mt-2">
                Use the Wendler 5/3/1 generator or import workouts via CSV to plan your training.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default Upcoming;
