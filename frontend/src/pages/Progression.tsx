import { useState } from "react";
import { useParams } from "react-router-dom";
import { format } from "date-fns";
import Navigation from "@/components/Navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    useProgression,
    useProgressionExercises,
} from "@/hooks/useProgression";
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine,
} from "recharts";

const Progression = () => {
    const { exercise: urlExercise } = useParams<{ exercise?: string }>();
    const [selectedExercise, setSelectedExercise] = useState(
        urlExercise || "Barbell Squat",
    );
    const [includeUpcoming, setIncludeUpcoming] = useState(true);

    const { data: exercises } = useProgressionExercises();
    const { data: progressionData, isLoading } = useProgression(
        selectedExercise,
        includeUpcoming,
    );

    // Prepare chart data
    const chartData = progressionData
        ? [
              ...progressionData.historical.map((point) => ({
                  date: point.date,
                  estimated_1rm: point.estimated_1rm,
                  weight: point.weight,
                  reps: point.reps,
                  comment: point.comment,
                  type: "historical" as const,
              })),
              ...(includeUpcoming
                  ? progressionData.upcoming.map((point) => ({
                        date: point.projected_date,
                        estimated_1rm: point.estimated_1rm,
                        weight: point.weight,
                        reps: point.reps,
                        comment: point.comment,
                        type: "upcoming" as const,
                    }))
                  : []),
          ].sort(
              (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
          )
        : [];

    // Calculate moving average (30 days)
    const calculateMovingAverage = (
        data: typeof chartData,
        windowDays: number = 30,
    ) => {
        const result: Array<{ date: string; ma: number }> = [];
        const historicalData = data.filter((d) => d.type === "historical");

        historicalData.forEach((point, index) => {
            const pointDate = new Date(point.date);
            const windowStart = new Date(pointDate);
            windowStart.setDate(windowStart.getDate() - windowDays);

            const windowData = historicalData
                .slice(0, index + 1)
                .filter((d) => {
                    const dDate = new Date(d.date);
                    return dDate >= windowStart && dDate <= pointDate;
                });

            if (windowData.length > 0) {
                const avg =
                    windowData.reduce((sum, d) => sum + d.estimated_1rm, 0) /
                    windowData.length;
                result.push({ date: point.date, ma: avg });
            }
        });

        return result;
    };

    const movingAverageData =
        chartData.length > 0 ? calculateMovingAverage(chartData) : [];

    // Merge MA data with chart data
    const combinedData = chartData.map((point) => {
        const maPoint = movingAverageData.find((ma) => ma.date === point.date);
        return {
            ...point,
            ma: maPoint?.ma,
        };
    });

    const today = format(new Date(), "yyyy-MM-dd");
    const todayIndex = combinedData.findIndex((d) => d.date === today);

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content">
                    {/* Header */}
                    <div className="page__header animate-in">
                        <h1 className="page__title">PROGRESSION TRACKING</h1>
                        <p className="page__subtitle">Track your strength gains over time</p>
                    </div>

                    {/* Controls */}
                    <div className="card animate-in section">
                        <div className="flex flex-col sm:flex-row gap-4">
                            <div className="flex-1">
                                <Select
                                    value={selectedExercise}
                                    onValueChange={setSelectedExercise}
                                >
                                    <SelectTrigger className="input">
                                        <SelectValue placeholder="Select exercise" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {exercises?.map((exercise) => (
                                            <SelectItem
                                                key={exercise}
                                                value={exercise}
                                            >
                                                {exercise}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                                <input
                                    type="checkbox"
                                    id="includeUpcoming"
                                    checked={includeUpcoming}
                                    onChange={(e) =>
                                        setIncludeUpcoming(e.target.checked)
                                    }
                                    style={{
                                        width: '16px',
                                        height: '16px',
                                        accentColor: 'var(--accent)',
                                    }}
                                />
                                <label
                                    htmlFor="includeUpcoming"
                                    style={{
                                        fontSize: '13px',
                                        color: 'var(--text-secondary)',
                                        cursor: 'pointer',
                                    }}
                                >
                                    Include upcoming workouts
                                </label>
                            </div>
                        </div>
                    </div>

                    {isLoading ? (
                        <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
                            <div className="loading-spinner inline-block" />
                            <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
                                Loading progression data...
                            </p>
                        </div>
                    ) : progressionData && combinedData.length > 0 ? (
                        <>
                            <Card className="animate-in section">
                                <CardHeader>
                                    <CardTitle className="font-display text-xl tracking-tight">
                                        ESTIMATED 1RM OVER TIME
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <ResponsiveContainer width="100%" height={400}>
                                        <LineChart data={combinedData}>
                                            <CartesianGrid
                                                strokeDasharray="3 3"
                                                stroke="var(--border)"
                                            />
                                            <XAxis
                                                dataKey="date"
                                                stroke="var(--text-muted)"
                                                style={{ fontSize: '12px' }}
                                                tickFormatter={(date) =>
                                                    format(new Date(date), "MMM d")
                                                }
                                            />
                                            <YAxis
                                                stroke="var(--text-muted)"
                                                style={{ fontSize: '12px' }}
                                                label={{
                                                    value: "1RM (lbs)",
                                                    angle: -90,
                                                    position: "insideLeft",
                                                    style: { fill: 'var(--text-muted)' },
                                                }}
                                            />
                                            <Tooltip
                                                contentStyle={{
                                                    backgroundColor: "var(--bg-tertiary)",
                                                    border: "1px solid var(--border)",
                                                    borderRadius: 'var(--radius-md)',
                                                    color: 'var(--text-primary)',
                                                }}
                                                labelFormatter={(date) =>
                                                    format(
                                                        new Date(date),
                                                        "MMM d, yyyy",
                                                    )
                                                }
                                                formatter={(
                                                    value: any,
                                                    name?: string,
                                                ) => {
                                                    if (name === "Estimated 1RM")
                                                        return [
                                                            value.toFixed(1),
                                                            name,
                                                        ];
                                                    if (name === "30-day MA")
                                                        return [
                                                            value.toFixed(1),
                                                            name,
                                                        ];
                                                    return [value, name];
                                                }}
                                            />
                                            <Legend />
                                            {todayIndex >= 0 && (
                                                <ReferenceLine
                                                    x={today}
                                                    stroke="var(--accent)"
                                                    strokeDasharray="3 3"
                                                    label="Today"
                                                />
                                            )}
                                            <Line
                                                type="monotone"
                                                dataKey="estimated_1rm"
                                                stroke="var(--chart-2)"
                                                name="Estimated 1RM"
                                                strokeWidth={2}
                                                dot={(props: any) => {
                                                    const { cx, cy, payload } =
                                                        props;
                                                    return (
                                                        <circle
                                                            cx={cx}
                                                            cy={cy}
                                                            r={4}
                                                            fill={
                                                                payload.type ===
                                                                "upcoming"
                                                                    ? "var(--warning)"
                                                                    : "var(--chart-2)"
                                                            }
                                                            stroke="none"
                                                        />
                                                    );
                                                }}
                                            />
                                            <Line
                                                type="monotone"
                                                dataKey="ma"
                                                stroke="var(--accent)"
                                                name="30-day MA"
                                                strokeWidth={2}
                                                dot={false}
                                            />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </CardContent>
                            </Card>

                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                <Card className="animate-in">
                                    <CardHeader>
                                        <CardTitle className="font-display text-xl tracking-tight">
                                            HISTORICAL DATA
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="flex flex-col gap-3" style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: 'var(--space-2)' }}>
                                            {progressionData.historical
                                                .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
                                                .map((point, index) => (
                                                    <div
                                                        key={index}
                                                        className="data-item"
                                                        style={{
                                                            background: 'rgba(34, 197, 94, 0.08)',
                                                            border: '1px solid rgba(34, 197, 94, 0.15)',
                                                        }}
                                                    >
                                                        <div>
                                                            <div className="font-semibold text-[var(--text-primary)] text-[15px]">
                                                                {format(new Date(point.date), "MMM d, yyyy")}
                                                            </div>
                                                            <div className="text-[13px] text-[var(--text-muted)] font-mono mt-1.5">
                                                                {point.weight} {point.weight_unit} × {point.reps} reps
                                                            </div>
                                                            {point.comment && (
                                                                <div className="text-xs text-[var(--text-muted)] italic mt-2">
                                                                    {point.comment}
                                                                </div>
                                                            )}
                                                        </div>
                                                        <div className="text-right">
                                                            <div className="text-xl font-bold text-[var(--accent)] font-mono">
                                                                {point.estimated_1rm.toFixed(1)}
                                                            </div>
                                                            <div className="text-[11px] text-[var(--text-muted)] mt-1">1RM</div>
                                                        </div>
                                                    </div>
                                                ))}
                                        </div>
                                    </CardContent>
                                </Card>

                                {includeUpcoming && progressionData.upcoming.length > 0 && (
                                    <Card className="animate-in">
                                        <CardHeader>
                                            <CardTitle className="font-display text-xl tracking-tight">
                                                UPCOMING WORKOUTS
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="flex flex-col gap-3" style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: 'var(--space-2)' }}>
                                                {progressionData.upcoming.map((point, index) => (
                                                    <div
                                                        key={index}
                                                        className="data-item"
                                                        style={{
                                                            background: 'rgba(234, 179, 8, 0.1)',
                                                            border: '1px solid rgba(234, 179, 8, 0.2)',
                                                        }}
                                                    >
                                                        <div>
                                                            <div className="font-semibold text-[var(--text-primary)] text-[15px]">
                                                                Session {point.session}
                                                            </div>
                                                            <div className="text-[13px] text-[var(--text-secondary)] mt-1">
                                                                {format(new Date(point.projected_date), "MMM d, yyyy")}
                                                            </div>
                                                            <div className="text-[13px] text-[var(--text-muted)] font-mono mt-1.5">
                                                                {point.weight} {point.weight_unit} × {point.reps} reps
                                                            </div>
                                                            {point.comment && (
                                                                <div className="text-xs text-[var(--text-muted)] italic mt-2">
                                                                    {point.comment}
                                                                </div>
                                                            )}
                                                        </div>
                                                        <div className="text-right">
                                                            <div className="text-xl font-bold text-[var(--warning)] font-mono">
                                                                {point.estimated_1rm.toFixed(1)}
                                                            </div>
                                                            <div className="text-[11px] text-[var(--text-muted)] mt-1">1RM</div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}
                            </div>
                        </>
                    ) : (
                        <Card className="border-2 border-dashed border-[var(--border)] bg-transparent">
                            <CardContent className="p-12 text-center">
                                <p className="text-[var(--text-secondary)]">
                                    No progression data available for this exercise.
                                </p>
                            </CardContent>
                        </Card>
                    )}
                </div>
            </div>
        </>
    );
};

export default Progression;
