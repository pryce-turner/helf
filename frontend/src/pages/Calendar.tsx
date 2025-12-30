import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Plus, Dumbbell } from "lucide-react";
import Navigation from "@/components/Navigation";
import { useCalendar } from "@/hooks/useWorkouts";

const Calendar = () => {
    const navigate = useNavigate();
    const today = new Date();
    const [currentYear, setCurrentYear] = useState(today.getFullYear());
    const [currentMonth, setCurrentMonth] = useState(today.getMonth() + 1);

    const { data: calendarData, isLoading } = useCalendar(
        currentYear,
        currentMonth,
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
                            <div className="stat-card__value" style={{ fontSize: '28px' }}>
                                🔥
                            </div>
                            <div className="stat-card__label">Keep it up!</div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
};

export default Calendar;
