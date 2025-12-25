import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
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

    const days = [];
    for (let i = 0; i < firstDay; i++) {
        days.push(<div key={`empty-${i}`} className="h-20 sm:h-24" />);
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
                className={`h-20 sm:h-24 border border-border rounded-lg p-2 cursor-pointer transition-colors ${
                    count > 0
                        ? "bg-green-900/20 hover:bg-green-900/30"
                        : "hover:bg-accent"
                } ${isToday ? "ring-2 ring-primary" : ""}`}
            >
                <div className="font-semibold text-sm sm:text-base">{day}</div>
                {count > 0 && (
                    <div className="text-xs text-green-400 mt-1">
                        {count} workout{count > 1 ? "s" : ""}
                    </div>
                )}
            </div>,
        );
    }

    return (
        <div className="min-h-screen">
            <Navigation />

            <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
                <div className="bg-card rounded-lg shadow-lg p-6">
                    <div className="flex items-center justify-between mb-6">
                        <button
                            onClick={previousMonth}
                            className="p-2 rounded-md hover:bg-accent transition-colors"
                        >
                            <ChevronLeft className="h-6 w-6" />
                        </button>

                        <h2 className="text-2xl font-bold">{monthName}</h2>

                        <button
                            onClick={nextMonth}
                            className="p-2 rounded-md hover:bg-accent transition-colors"
                        >
                            <ChevronRight className="h-6 w-6" />
                        </button>
                    </div>

                    <div className="grid grid-cols-7 gap-2 mb-2">
                        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(
                            (day) => (
                                <div
                                    key={day}
                                    className="text-center font-bold text-sm text-muted-foreground"
                                >
                                    {day}
                                </div>
                            ),
                        )}
                    </div>

                    {isLoading ? (
                        <div className="text-center py-12 text-muted-foreground">
                            Loading calendar...
                        </div>
                    ) : (
                        <div className="grid grid-cols-7 gap-2">{days}</div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Calendar;
