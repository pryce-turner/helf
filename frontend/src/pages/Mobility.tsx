import { useMemo, useState } from 'react';
import { format } from 'date-fns';
import {
  ArrowRight,
  CalendarDays,
  Check,
  MessageSquare,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import Navigation from '@/components/Navigation';
import TrainingSectionTabs from '@/components/TrainingSectionTabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Calendar } from '@/components/ui/calendar';
import { Button } from '@/components/ui/button';
import {
  useMobilityPending,
  useTransferMobility,
  useClearMobilityPending,
} from '@/hooks/useMobility';
import type { MobilityPendingSession, MobilityLastSession } from '@/types/mobility';
import type { UpcomingWorkout } from '@/types/upcoming';

/**
 * A movement as it reads in a routine, collapsed back from its rows.
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

/** The last session that was run, and everything that was said about it. */
const LastSessionCard = ({ session }: { session: MobilityLastSession }) => {
  const commented = session.sets.filter((s) => s.comment);

  return (
    <Card className="animate-in">
      <CardHeader>
        <CardTitle className="font-display text-lg tracking-tight">
          LAST SESSION
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
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
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
                    width: '15px',
                    height: '15px',
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
 * One pending session, with its own Copy-to-calendar and Discard.
 *
 * Its state is local on purpose. Several sessions can be pending — rehabbing a
 * low back and a shoulder means two prescriptions alive at once — and shared
 * state would open every card's calendar at once and arm every card's discard
 * from one tap.
 */
const PendingSessionCard = ({ session }: { session: MobilityPendingSession }) => {
  const transfer = useTransferMobility();
  const clearPending = useClearMobilityPending();

  const [transferDate, setTransferDate] = useState<Date | undefined>(new Date());
  const [showCalendar, setShowCalendar] = useState(false);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);

  const movements = useMemo(() => foldMovements(session.items), [session.items]);

  const handleTransfer = async () => {
    if (!transferDate) return;
    // Local time, never `toISOString()`. `workouts.date` is a string prefix,
    // so a UTC date puts an evening session on tomorrow west of Greenwich.
    await transfer.mutateAsync({
      date: format(transferDate, 'yyyy-MM-dd'),
      session: session.session,
    });
    setShowCalendar(false);
  };

  return (
    <Card className="animate-in">
      <CardHeader>
        <div
          className="flex items-start justify-between flex-wrap"
          style={{ gap: 'var(--space-4)' }}
        >
          <div>
            <CardTitle className="font-display text-xl tracking-tight">
              {session.label.toUpperCase()}
            </CardTitle>
            <p
              style={{
                fontSize: '13px',
                color: 'var(--text-muted)',
                marginTop: 'var(--space-1)',
              }}
            >
              {movements.length} movement{movements.length !== 1 ? 's' : ''}
              {session.generated_at
                ? ` · written ${format(new Date(session.generated_at), 'MMM d')}`
                : ''}
            </p>
          </div>
          <div className="flex items-center" style={{ gap: 'var(--space-2)' }}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowCalendar(!showCalendar)}
            >
              <CalendarDays style={{ width: '16px', height: '16px' }} />
              Copy to calendar
            </Button>
            {confirmingDiscard ? (
              <>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={async () => {
                    await clearPending.mutateAsync(session.session);
                    setConfirmingDiscard(false);
                  }}
                >
                  <Check style={{ width: '16px', height: '16px' }} />
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setConfirmingDiscard(false)}
                >
                  <X style={{ width: '16px', height: '16px' }} />
                </Button>
              </>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingDiscard(true)}
                aria-label="Discard session"
              >
                <Trash2 style={{ width: '16px', height: '16px' }} />
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
            <div
              className="flex flex-col items-center"
              style={{ gap: 'var(--space-4)' }}
            >
              <Calendar
                mode="single"
                selected={transferDate}
                onSelect={setTransferDate}
                className="rounded-[var(--radius-md)] border border-[var(--border)]"
              />
              <Button
                onClick={handleTransfer}
                disabled={!transferDate || transfer.isPending}
              >
                <ArrowRight style={{ width: '18px', height: '18px' }} />
                Copy to {transferDate && format(transferDate, 'MMM d, yyyy')}
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

        <div
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
        >
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
                  style={{
                    fontWeight: 600,
                    fontSize: '15px',
                    color: 'var(--text-primary)',
                  }}
                >
                  {movement.exercise}
                </div>
                {movement.comment && (
                  <div
                    style={{
                      fontSize: '13px',
                      color: 'var(--text-secondary)',
                      fontStyle: 'italic',
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
      </CardContent>
    </Card>
  );
};

const Mobility = () => {
  const { data, isLoading } = useMobilityPending();

  return (
    <>
      <Navigation />
      <div className="page">
        <div className="page__content page__content--narrow">
          <div className="page__header animate-in">
            <h1 className="page__title">UPCOMING MOBILITY</h1>
            <p className="page__subtitle">
              Sessions the agent has written, ready to run
            </p>
          </div>

          <TrainingSectionTabs />

          {isLoading ? (
            <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
              <div className="loading-spinner inline-block" />
              <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
                Loading mobility sessions...
              </p>
            </div>
          ) : data?.ready ? (
            /* State 1 — one or more sessions are waiting to be run. */
            <div
              className="stagger-children"
              style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}
            >
              {data.sessions.map((session) => (
                <PendingSessionCard key={session.session} session={session} />
              ))}

              {data.last_session && <LastSessionCard session={data.last_session} />}
            </div>
          ) : (
            /* State 2 — nothing pending; the next session has to be written. */
            <div
              className="stagger-children"
              style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}
            >
              <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
                <CardContent className="empty-state">
                  <div className="empty-state__icon">
                    <Sparkles
                      style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }}
                    />
                  </div>
                  <h3 className="empty-state__title">NO SESSION READY</h3>
                  <p className="empty-state__text">
                    The next mobility session hasn't been written yet.
                  </p>
                  <p
                    style={{
                      fontSize: '13px',
                      color: 'var(--text-muted)',
                      marginTop: 'var(--space-2)',
                    }}
                  >
                    {data?.last_session
                      ? 'Ask the agent to generate it — it reads the notes below and adjusts.'
                      : 'Ask the agent to generate one from the mobility exercise pool.'}
                  </p>
                </CardContent>
              </Card>

              {data?.last_session && <LastSessionCard session={data.last_session} />}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default Mobility;
