import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { Weight, Hash, MessageSquare, TrendingUp } from "lucide-react";
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
    const [selectedExercise, setSelectedExercise] = useState(urlExercise || "");
    const [includeUpcoming, setIncludeUpcoming] = useState(true);

    const { data: exercises } = useProgressionExercises();

    // Auto-select first exercise when list loads (if no URL param or selection)
    useEffect(() => {
        if (!selectedExercise && exercises && exercises.length > 0) {
            setSelectedExercise(exercises[0]);
        }
    }, [exercises, selectedExercise]);
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
              (a, b) => parseISO(a.date).getTime() - parseISO(b.date).getTime(),
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
            const pointDate = parseISO(point.date);
            const windowStart = new Date(pointDate);
            windowStart.setDate(windowStart.getDate() - windowDays);

            const windowData = historicalData
                .slice(0, index + 1)
                .filter((d) => {
                    const dDate = parseISO(d.date);
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
                                    <SelectTrigger>
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
                                    className="checkbox"
                                    checked={includeUpcoming}
                                    onChange={(e) =>
                                        setIncludeUpcoming(e.target.checked)
                                    }
                                />
                                <label
                                    htmlFor="includeUpcoming"
                                    className="checkbox-label"
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
                                                    format(parseISO(date), "MMM d")
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
                                                        parseISO(date),
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
                                                    label={{ value: "Today", fill: 'var(--text-muted)', fontSize: 12 }}
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

                            <div className="grid grid-cols-1 lg:grid-cols-2" style={{ gap: 'var(--space-6)' }}>
                                <Card className="animate-in">
                                    <CardHeader>
                                        <CardTitle className="font-display text-xl tracking-tight">
                                            HISTORICAL DATA
                                        </CardTitle>
                                        <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                                            {progressionData.historical.length} completed session{progressionData.historical.length !== 1 ? 's' : ''}
                                        </p>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="stagger-children hide-scrollbar" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', maxHeight: '400px', overflowY: 'auto' }}>
                                            {progressionData.historical
                                                .sort((a, b) => parseISO(b.date).getTime() - parseISO(a.date).getTime())
                                                .map((point, index) => (
                                                    <div
                                                        key={index}
                                                        className="animate-in"
                                                        style={{
                                                            padding: 'var(--space-4)',
                                                            background: 'var(--bg-tertiary)',
                                                            borderRadius: 'var(--radius-md)',
                                                            border: '1px solid var(--border-subtle)',
                                                            animationDelay: `${index * 30}ms`,
                                                        }}
                                                    >
                                                        <div className="flex items-start" style={{ gap: 'var(--space-4)' }}>
                                                            <div
                                                                className="workout-order"
                                                                style={{
                                                                    width: '36px',
                                                                    height: '36px',
                                                                    fontSize: '14px',
                                                                    background: 'var(--success-subtle)',
                                                                    color: 'var(--success)',
                                                                }}
                                                            >
                                                                {progressionData.historical.length - index}
                                                            </div>
                                                            <div className="flex-1">
                                                                <div className="flex items-center flex-wrap" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
                                                                    <h3
                                                                        style={{
                                                                            fontFamily: 'var(--font-body)',
                                                                            fontSize: '15px',
                                                                            fontWeight: 600,
                                                                            color: 'var(--text-primary)',
                                                                        }}
                                                                    >
                                                                        {format(parseISO(point.date), "MMM d, yyyy")}
                                                                    </h3>
                                                                </div>
                                                                <div className="flex flex-wrap" style={{ gap: 'var(--space-2)' }}>
                                                                    {point.weight && (
                                                                        <div className="workout-chip">
                                                                            <Weight style={{ width: '14px', height: '14px', color: 'var(--success)' }} />
                                                                            <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                                                                {point.weight} {point.weight_unit}
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                    {point.reps && (
                                                                        <div className="workout-chip">
                                                                            <Hash style={{ width: '14px', height: '14px', color: 'var(--success)' }} />
                                                                            <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                                                                {point.reps} reps
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                    <div className="workout-chip">
                                                                        <TrendingUp style={{ width: '14px', height: '14px', color: 'var(--accent)' }} />
                                                                        <span className="workout-chip__value" style={{ fontSize: '13px', color: 'var(--accent)' }}>
                                                                            {point.estimated_1rm.toFixed(1)} 1RM
                                                                        </span>
                                                                    </div>
                                                                    {point.comment && (
                                                                        <div className="workout-chip">
                                                                            <MessageSquare style={{ width: '14px', height: '14px', color: 'var(--text-muted)' }} />
                                                                            <span className="workout-chip__comment" style={{ fontSize: '13px' }}>
                                                                                {point.comment}
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
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
                                            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
                                                {progressionData.upcoming.length} planned session{progressionData.upcoming.length !== 1 ? 's' : ''}
                                            </p>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="stagger-children hide-scrollbar" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', maxHeight: '400px', overflowY: 'auto' }}>
                                                {progressionData.upcoming.map((point, index) => (
                                                    <div
                                                        key={index}
                                                        className="animate-in"
                                                        style={{
                                                            padding: 'var(--space-4)',
                                                            background: 'var(--bg-tertiary)',
                                                            borderRadius: 'var(--radius-md)',
                                                            border: '1px solid var(--border-subtle)',
                                                            animationDelay: `${index * 30}ms`,
                                                        }}
                                                    >
                                                        <div className="flex items-start" style={{ gap: 'var(--space-4)' }}>
                                                            <div
                                                                className="workout-order"
                                                                style={{
                                                                    width: '36px',
                                                                    height: '36px',
                                                                    fontSize: '14px',
                                                                    background: 'var(--warning-subtle)',
                                                                    color: 'var(--warning)',
                                                                }}
                                                            >
                                                                {point.session}
                                                            </div>
                                                            <div className="flex-1">
                                                                <div className="flex items-center flex-wrap" style={{ gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
                                                                    <h3
                                                                        style={{
                                                                            fontFamily: 'var(--font-body)',
                                                                            fontSize: '15px',
                                                                            fontWeight: 600,
                                                                            color: 'var(--text-primary)',
                                                                        }}
                                                                    >
                                                                        Session {point.session}
                                                                    </h3>
                                                                    <span
                                                                        style={{
                                                                            fontSize: '12px',
                                                                            color: 'var(--text-secondary)',
                                                                        }}
                                                                    >
                                                                        {format(parseISO(point.projected_date), "MMM d, yyyy")}
                                                                    </span>
                                                                </div>
                                                                <div className="flex flex-wrap" style={{ gap: 'var(--space-2)' }}>
                                                                    {point.weight && (
                                                                        <div className="workout-chip">
                                                                            <Weight style={{ width: '14px', height: '14px', color: 'var(--warning)' }} />
                                                                            <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                                                                {point.weight} {point.weight_unit}
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                    {point.reps && (
                                                                        <div className="workout-chip">
                                                                            <Hash style={{ width: '14px', height: '14px', color: 'var(--warning)' }} />
                                                                            <span className="workout-chip__value" style={{ fontSize: '13px' }}>
                                                                                {point.reps} reps
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                    <div className="workout-chip">
                                                                        <TrendingUp style={{ width: '14px', height: '14px', color: 'var(--warning)' }} />
                                                                        <span className="workout-chip__value" style={{ fontSize: '13px', color: 'var(--warning)' }}>
                                                                            {point.estimated_1rm.toFixed(1)} 1RM
                                                                        </span>
                                                                    </div>
                                                                    {point.comment && (
                                                                        <div className="workout-chip">
                                                                            <MessageSquare style={{ width: '14px', height: '14px', color: 'var(--text-muted)' }} />
                                                                            <span className="workout-chip__comment" style={{ fontSize: '13px' }}>
                                                                                {point.comment}
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
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
                        <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
                            <CardContent className="empty-state">
                                <div className="empty-state__icon">
                                    <TrendingUp style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
                                </div>
                                <h3 className="empty-state__title">NO PROGRESSION DATA</h3>
                                <p className="empty-state__text">
                                    No progression data available for this exercise.
                                </p>
                                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                                    Complete workouts with this exercise to see your progression over time.
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
