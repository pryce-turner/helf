import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Plus, Dumbbell } from "lucide-react";
import Navigation from "@/components/Navigation";
import { useCalendar } from "@/hooks/useWorkouts";
import { Button } from "@/components/ui/button";

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

    const days = [];
    for (let i = 0; i < firstDay; i++) {
        days.push(
            <div
                key={`empty-${i}`}
                style={{
                    aspectRatio: '1/1',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--bg-tertiary)',
                    opacity: 0.3,
                }}
            />,
        );
    }

    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${currentYear}-${String(currentMonth).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const count = workoutCounts[dateStr] || 0;
        const isToday =
            day === today.getDate() &&
            currentMonth === today.getMonth() + 1 &&
            currentYear === today.getFullYear();

        days.push(
            <div
                key={day}
                onClick={() => handleDayClick(day)}
                className="animate-in stagger-children"
                style={{
                    aspectRatio: '1/1',
                    borderRadius: 'var(--radius-md)',
                    background: count > 0 ? 'var(--accent-subtle)' : 'var(--bg-tertiary)',
                    border: `${isToday ? '2px' : '1px'} solid ${isToday ? 'var(--accent)' : count > 0 ? 'var(--accent-muted)' : 'var(--border-subtle)'}`,
                    padding: 'var(--space-3)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'all var(--duration-normal) var(--ease-default)',
                    boxShadow: isToday ? 'var(--shadow-glow)' : 'none',
                }}
                onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-2px)';
                    e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                    e.currentTarget.style.background = count > 0 ? 'var(--accent-glow)' : 'var(--bg-hover)';
                }}
                onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.boxShadow = isToday ? 'var(--shadow-glow)' : 'none';
                    e.currentTarget.style.background = count > 0 ? 'var(--accent-subtle)' : 'var(--bg-tertiary)';
                }}
            >
                <div
                    style={{
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 700,
                        fontSize: '14px',
                        color: isToday ? 'var(--accent)' : count > 0 ? 'var(--accent)' : 'var(--text-secondary)',
                    }}
                >
                    {day}
                </div>
                {count > 0 && (
                    <div className="mt-auto flex items-center gap-1">
                        <Dumbbell style={{ width: '12px', height: '12px', color: 'var(--accent)' }} />
                        <span style={{
                            fontSize: '11px',
                            fontWeight: 600,
                            color: 'var(--accent)',
                            fontFamily: 'var(--font-mono)',
                        }}>
                            {count}
                        </span>
                    </div>
                )}
                {count === 0 && (
                    <div className="mt-auto opacity-0 transition-opacity" style={{ transitionDuration: 'var(--duration-normal)' }}
                        onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                        onMouseLeave={(e) => e.currentTarget.style.opacity = '0'}
                    >
                        <Plus style={{ width: '14px', height: '14px', color: 'var(--text-muted)' }} />
                    </div>
                )}
            </div>,
        );
    }

    return (
        <>
            <Navigation />
            <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
                <div className="max-w-7xl mx-auto" style={{ padding: 'var(--space-6)' }}>
                {/* Calendar Card */}
                <div
                    className="card animate-in"
                    style={{
                        marginBottom: 'var(--space-6)',
                        animationDelay: '0ms',
                    }}
                >
                    {/* Month Navigation */}
                    <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-6)' }}>
                        <Button
                            onClick={previousMonth}
                            variant="outline"
                            size="icon"
                            style={{
                                width: '44px',
                                height: '44px',
                                borderRadius: 'var(--radius-sm)',
                                background: 'var(--bg-tertiary)',
                                border: '1px solid var(--border)',
                                color: 'var(--text-primary)',
                                cursor: 'pointer',
                                transition: 'all var(--duration-normal)',
                            }}
                            onMouseEnter={(e: React.MouseEvent<HTMLButtonElement>) => {
                                e.currentTarget.style.background = 'var(--bg-hover)';
                                e.currentTarget.style.transform = 'translateY(-1px)';
                            }}
                            onMouseLeave={(e: React.MouseEvent<HTMLButtonElement>) => {
                                e.currentTarget.style.background = 'var(--bg-tertiary)';
                                e.currentTarget.style.transform = 'translateY(0)';
                            }}
                        >
                            <ChevronLeft style={{ width: '20px', height: '20px' }} />
                        </Button>

                        <div className="text-center">
                            <h2
                                style={{
                                    fontFamily: 'var(--font-display)',
                                    fontSize: '24px',
                                    fontWeight: 600,
                                    color: 'var(--text-primary)',
                                    letterSpacing: '-0.01em',
                                }}
                            >
                                {monthName.toUpperCase()}
                            </h2>
                            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                                Your workout calendar
                            </p>
                        </div>

                        <Button
                            onClick={nextMonth}
                            variant="outline"
                            size="icon"
                            style={{
                                width: '44px',
                                height: '44px',
                                borderRadius: 'var(--radius-sm)',
                                background: 'var(--bg-tertiary)',
                                border: '1px solid var(--border)',
                                color: 'var(--text-primary)',
                                cursor: 'pointer',
                                transition: 'all var(--duration-normal)',
                            }}
                            onMouseEnter={(e: React.MouseEvent<HTMLButtonElement>) => {
                                e.currentTarget.style.background = 'var(--bg-hover)';
                                e.currentTarget.style.transform = 'translateY(-1px)';
                            }}
                            onMouseLeave={(e: React.MouseEvent<HTMLButtonElement>) => {
                                e.currentTarget.style.background = 'var(--bg-tertiary)';
                                e.currentTarget.style.transform = 'translateY(0)';
                            }}
                        >
                            <ChevronRight style={{ width: '20px', height: '20px' }} />
                        </Button>
                    </div>

                    {/* Day Headers */}
                    <div className="grid grid-cols-7" style={{ gap: 'var(--space-1)', marginBottom: 'var(--space-4)' }}>
                        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(
                            (day, index) => (
                                <div
                                    key={day}
                                    style={{
                                        textAlign: 'center',
                                        fontSize: '12px',
                                        fontWeight: 600,
                                        color: index === 0 || index === 6 ? 'var(--text-secondary)' : 'var(--text-muted)',
                                        padding: 'var(--space-2)',
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.05em',
                                    }}
                                >
                                    <span className="hidden sm:inline">
                                        {day}
                                    </span>
                                    <span className="sm:hidden">
                                        {day.charAt(0)}
                                    </span>
                                </div>
                            ),
                        )}
                    </div>

                    {/* Calendar Grid */}
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
                                Loading calendar...
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-7 stagger-children" style={{ gap: 'var(--space-1)' }}>
                            {days}
                        </div>
                    )}
                </div>

                {/* Quick Stats */}
                <div className="grid grid-cols-1 sm:grid-cols-3 stagger-children" style={{ gap: 'var(--space-4)' }}>
                    <div
                        className="stat-card animate-in"
                        style={{ animationDelay: '100ms' }}
                    >
                        <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: 'var(--space-2)' }}>
                            THIS MONTH
                        </div>
                        <div className="stat-card__value">
                            {Object.values(workoutCounts).reduce(
                                (a, b) => a + b,
                                0,
                            )}
                        </div>
                        <div className="stat-card__label">
                            Total Workouts
                        </div>
                    </div>

                    <div
                        className="stat-card animate-in"
                        style={{ animationDelay: '150ms' }}
                    >
                        <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: 'var(--space-2)' }}>
                            ACTIVE DAYS
                        </div>
                        <div className="stat-card__value">
                            {
                                Object.values(workoutCounts).filter(
                                    (c) => c > 0,
                                ).length
                            }
                        </div>
                        <div className="stat-card__label">
                            Days with workouts
                        </div>
                    </div>

                    <div
                        className="stat-card animate-in"
                        style={{ animationDelay: '200ms' }}
                    >
                        <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: 'var(--space-2)' }}>
                            STREAK
                        </div>
                        <div className="stat-card__value" style={{ fontSize: '28px' }}>
                            🔥
                        </div>
                        <div className="stat-card__label">
                            Keep it up!
                        </div>
                    </div>
                </div>
            </div>
            </div>
        </>
    );
};

export default Calendar;
