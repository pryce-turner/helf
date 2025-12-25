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
        <div className="min-h-screen">
            <Navigation />

            <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
                <div className="mb-6">
                    <h1 className="text-3xl font-bold mb-4">
                        Progression Tracking
                    </h1>

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

                        <div className="flex items-center space-x-2">
                            <input
                                type="checkbox"
                                id="includeUpcoming"
                                checked={includeUpcoming}
                                onChange={(e) =>
                                    setIncludeUpcoming(e.target.checked)
                                }
                                className="h-4 w-4"
                            />
                            <label
                                htmlFor="includeUpcoming"
                                className="text-sm"
                            >
                                Include upcoming workouts
                            </label>
                        </div>
                    </div>
                </div>

                {isLoading ? (
                    <div className="text-center py-12 text-muted-foreground">
                        Loading progression data...
                    </div>
                ) : progressionData && combinedData.length > 0 ? (
                    <>
                        <Card className="mb-6">
                            <CardHeader>
                                <CardTitle>Estimated 1RM Over Time</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ResponsiveContainer width="100%" height={400}>
                                    <LineChart data={combinedData}>
                                        <CartesianGrid
                                            strokeDasharray="3 3"
                                            stroke="#374151"
                                        />
                                        <XAxis
                                            dataKey="date"
                                            stroke="#9CA3AF"
                                            tickFormatter={(date) =>
                                                format(new Date(date), "MMM d")
                                            }
                                        />
                                        <YAxis
                                            stroke="#9CA3AF"
                                            label={{
                                                value: "1RM (lbs)",
                                                angle: -90,
                                                position: "insideLeft",
                                            }}
                                        />
                                        <Tooltip
                                            contentStyle={{
                                                backgroundColor: "#1F2937",
                                                border: "1px solid #374151",
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
                                                stroke="#10B981"
                                                strokeDasharray="3 3"
                                                label="Today"
                                            />
                                        )}
                                        <Line
                                            type="monotone"
                                            dataKey="estimated_1rm"
                                            stroke="#3B82F6"
                                            name="Estimated 1RM"
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
                                                                ? "#F59E0B"
                                                                : "#3B82F6"
                                                        }
                                                        stroke="none"
                                                    />
                                                );
                                            }}
                                        />
                                        <Line
                                            type="monotone"
                                            dataKey="ma"
                                            stroke="#10B981"
                                            name="30-day MA"
                                            strokeWidth={2}
                                            dot={false}
                                        />
                                    </LineChart>
                                </ResponsiveContainer>
                            </CardContent>
                        </Card>

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Historical Data</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-2 max-h-96 overflow-y-auto">
                                        {progressionData.historical
                                            .sort(
                                                (a, b) =>
                                                    new Date(b.date).getTime() -
                                                    new Date(a.date).getTime(),
                                            )
                                            .map((point, index) => (
                                                <div
                                                    key={index}
                                                    className="p-3 bg-accent/50 rounded-lg flex justify-between items-start"
                                                >
                                                    <div>
                                                        <div className="font-semibold">
                                                            {format(
                                                                new Date(
                                                                    point.date,
                                                                ),
                                                                "MMM d, yyyy",
                                                            )}
                                                        </div>
                                                        <div className="text-sm text-muted-foreground">
                                                            {point.weight}{" "}
                                                            {point.weight_unit}{" "}
                                                            × {point.reps} reps
                                                        </div>
                                                        {point.comment && (
                                                            <div className="text-xs text-muted-foreground italic mt-1">
                                                                {point.comment}
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div className="text-right">
                                                        <div className="text-lg font-bold text-primary">
                                                            {point.estimated_1rm.toFixed(
                                                                1,
                                                            )}
                                                        </div>
                                                        <div className="text-xs text-muted-foreground">
                                                            1RM
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                    </div>
                                </CardContent>
                            </Card>

                            {includeUpcoming &&
                                progressionData.upcoming.length > 0 && (
                                    <Card>
                                        <CardHeader>
                                            <CardTitle>
                                                Upcoming Workouts
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="space-y-2 max-h-96 overflow-y-auto">
                                                {progressionData.upcoming.map(
                                                    (point, index) => (
                                                        <div
                                                            key={index}
                                                            className="p-3 bg-amber-900/20 rounded-lg flex justify-between items-start"
                                                        >
                                                            <div>
                                                                <div className="font-semibold">
                                                                    Session{" "}
                                                                    {
                                                                        point.session
                                                                    }
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                    {format(
                                                                        new Date(
                                                                            point.projected_date,
                                                                        ),
                                                                        "MMM d, yyyy",
                                                                    )}
                                                                </div>
                                                                <div className="text-sm text-muted-foreground">
                                                                    {
                                                                        point.weight
                                                                    }{" "}
                                                                    {
                                                                        point.weight_unit
                                                                    }{" "}
                                                                    ×{" "}
                                                                    {point.reps}{" "}
                                                                    reps
                                                                </div>
                                                                {point.comment && (
                                                                    <div className="text-xs text-muted-foreground italic mt-1">
                                                                        {
                                                                            point.comment
                                                                        }
                                                                    </div>
                                                                )}
                                                            </div>
                                                            <div className="text-right">
                                                                <div className="text-lg font-bold text-amber-500">
                                                                    {point.estimated_1rm.toFixed(
                                                                        1,
                                                                    )}
                                                                </div>
                                                                <div className="text-xs text-muted-foreground">
                                                                    1RM
                                                                </div>
                                                            </div>
                                                        </div>
                                                    ),
                                                )}
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}
                        </div>
                    </>
                ) : (
                    <Card>
                        <CardContent className="p-12 text-center">
                            <p className="text-muted-foreground">
                                No progression data available for this exercise.
                            </p>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
};

export default Progression;
