import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Plus, Dumbbell, Flame } from "lucide-react";
import Navigation from "@/components/Navigation";
import { useCalendar } from "@/hooks/useWorkouts";

/**
 * Calculate workout streak allowing every-other-day training.
 * A streak breaks when there are 2+ consecutive rest days.
 */
const calculateStreak = (workoutCounts: Record<string, number>): number => {
    // Get all dates with workouts, sorted descending (most recent first)
    const workoutDates = Object.entries(workoutCounts)
        .filter(([_, count]) => count > 0)
        .map(([date]) => new Date(date + 'T00:00:00'))
        .sort((a, b) => b.getTime() - a.getTime());

    if (workoutDates.length === 0) return 0;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const twoDaysAgo = new Date(today);
    twoDaysAgo.setDate(twoDaysAgo.getDate() - 2);

    // If most recent workout is more than 2 days ago, streak is broken
    const mostRecent = workoutDates[0];
    if (mostRecent.getTime() < twoDaysAgo.getTime()) {
        return 0;
    }

    // Count streak - each workout day counts as 1
    let streak = 1;
    for (let i = 1; i < workoutDates.length; i++) {
        const current = workoutDates[i - 1];
        const previous = workoutDates[i];

        const daysDiff = Math.floor(
            (current.getTime() - previous.getTime()) / (1000 * 60 * 60 * 24)
        );

        // If gap is more than 2 days, streak is broken
        if (daysDiff > 2) {
            break;
        }
        streak++;
    }

    return streak;
};

const Calendar = () => {
    const navigate = useNavigate();
    const today = new Date();
    const [currentYear, setCurrentYear] = useState(today.getFullYear());
    const [currentMonth, setCurrentMonth] = useState(today.getMonth() + 1);

    // Fetch current month
    const { data: calendarData, isLoading } = useCalendar(
        currentYear,
        currentMonth,
    );

    // Calculate previous month for streak calculation
    const prevMonth = currentMonth === 1 ? 12 : currentMonth - 1;
    const prevYear = currentMonth === 1 ? currentYear - 1 : currentYear;

    // Fetch previous month for streak calculation (only when viewing current month)
    const isViewingCurrentMonth =
        currentMonth === today.getMonth() + 1 &&
        currentYear === today.getFullYear();

    const { data: prevMonthData } = useCalendar(
        prevYear,
        prevMonth,
    );

    const monthName = new Date(
        currentYear,
        currentMonth - 1,
    ).toLocaleDateString("en-US", {
        month: "long",
        year: "numeric",
    });

    const firstDay = new Date(currentYear, currentMonth - 1, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();

    const previousMonth = () => {
        if (currentMonth === 1) {
            setCurrentMonth(12);
            setCurrentYear(currentYear - 1);
        } else {
            setCurrentMonth(currentMonth - 1);
        }
    };

    const nextMonth = () => {
        if (currentMonth === 12) {
            setCurrentMonth(1);
            setCurrentYear(currentYear + 1);
        } else {
            setCurrentMonth(currentMonth + 1);
        }
    };

    const handleDayClick = (day: number) => {
        const date = `${currentYear}-${String(currentMonth).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        navigate(`/day/${date}`);
    };

    const workoutCounts = calendarData?.counts || {};

    // Calculate streak using combined data from current and previous month
    const streak = useMemo(() => {
        if (!isViewingCurrentMonth) return null;

        const combinedCounts: Record<string, number> = {
            ...(prevMonthData?.counts || {}),
            ...workoutCounts,
        };
        return calculateStreak(combinedCounts);
    }, [workoutCounts, prevMonthData?.counts, isViewingCurrentMonth]);

    const getDayClasses = (_day: number, count: number, isToday: boolean) => {
        const classes = ['calendar-day'];
        if (count > 0) classes.push('calendar-day--has-workout');
        if (isToday) classes.push('calendar-day--today');
        return classes.join(' ');
    };

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content">
                    {/* Calendar Card */}
                    <div className="card animate-in section">
                        {/* Month Navigation */}
                        <div className="flex items-center justify-between section">
                            <button onClick={previousMonth} className="icon-btn">
                                <ChevronLeft className="w-5 h-5" />
                            </button>

                            <div className="text-center">
                                <h2 className="page__title page__title--compact">
                                    {monthName.toUpperCase()}
                                </h2>
                                <p className="page__subtitle">Your workout calendar</p>
                            </div>

                            <button onClick={nextMonth} className="icon-btn">
                                <ChevronRight className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Day Headers */}
                        <div className="grid grid-cols-7 gap-1" style={{ marginBottom: 'var(--space-4)' }}>
                            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(
                                (day, index) => (
                                    <div
                                        key={day}
                                        className="text-center"
                                        style={{
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            color: index === 0 || index === 6 ? 'var(--text-secondary)' : 'var(--text-muted)',
                                            padding: 'var(--space-2)',
                                            textTransform: 'uppercase',
                                            letterSpacing: '0.05em',
                                        }}
                                    >
                                        <span className="hidden sm:inline">{day}</span>
                                        <span className="sm:hidden">{day.charAt(0)}</span>
                                    </div>
                                ),
                            )}
                        </div>

                        {/* Calendar Grid */}
                        {isLoading ? (
                            <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
                                <div className="loading-spinner inline-block" />
                                <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
                                    Loading calendar...
                                </p>
                            </div>
                        ) : (
                            <div className="grid grid-cols-7 gap-1">
                                {/* Empty cells for days before month starts */}
                                {Array.from({ length: firstDay }).map((_, i) => (
                                    <div key={`empty-${i}`} className="calendar-day calendar-day--empty" />
                                ))}

                                {/* Actual days */}
                                {Array.from({ length: daysInMonth }).map((_, i) => {
                                    const day = i + 1;
                                    const dateStr = `${currentYear}-${String(currentMonth).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                                    const count = workoutCounts[dateStr] || 0;
                                    const isToday = day === today.getDate() &&
                                        currentMonth === today.getMonth() + 1 &&
                                        currentYear === today.getFullYear();

                                    return (
                                        <div
                                            key={day}
                                            onClick={() => handleDayClick(day)}
                                            className={getDayClasses(day, count, isToday)}
                                        >
                                            <div className="calendar-day__number">{day}</div>
                                            {count > 0 ? (
                                                <div className="calendar-day__workout-count">
                                                    <Dumbbell className="w-3 h-3" />
                                                    <span>{count}</span>
                                                </div>
                                            ) : (
                                                <div className="calendar-day__add-icon">
                                                    <Plus className="w-3.5 h-3.5" />
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* Quick Stats */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-32">
                        <div className="stat-card animate-in">
                            <div className="stat-card__label" style={{ marginBottom: 'var(--space-2)' }}>
                                THIS MONTH
                            </div>
                            <div className="stat-card__value">
                                {Object.values(workoutCounts).reduce((a, b) => a + b, 0)}
                            </div>
                            <div className="stat-card__label">Total Workouts</div>
                        </div>

                        <div className="stat-card animate-in">
                            <div className="stat-card__label" style={{ marginBottom: 'var(--space-2)' }}>
                                ACTIVE DAYS
                            </div>
                            <div className="stat-card__value">
                                {Object.values(workoutCounts).filter((c) => c > 0).length}
                            </div>
                            <div className="stat-card__label">Days with workouts</div>
                        </div>

                        <div className="stat-card animate-in">
                            <div className="stat-card__label" style={{ marginBottom: 'var(--space-2)' }}>
                                STREAK
                            </div>
                            <div className="stat-card__value flex items-center justify-center" style={{ gap: 'var(--space-2)' }}>
                                {streak !== null ? (
                                    <>
                                        <span>{streak}</span>
                                        {streak > 0 && <Flame className="w-6 h-6" style={{ color: 'var(--chart-4)' }} />}
                                    </>
                                ) : (
                                    <span style={{ fontSize: '18px', color: 'var(--text-muted)' }}>—</span>
                                )}
                            </div>
                            <div className="stat-card__label">
                                {streak !== null
                                    ? streak > 0 ? 'Workout days' : 'Start today!'
                                    : 'View current month'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
};

export default Calendar;
