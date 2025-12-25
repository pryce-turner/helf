import { useState } from "react";
import { format } from "date-fns";
import { Weight, TrendingDown, TrendingUp } from "lucide-react";
import Navigation from "@/components/Navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    useBodyCompositionStats,
    useBodyCompositionTrends,
} from "@/hooks/useBodyComposition";
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from "recharts";

const BodyComposition = () => {
    const [trendDays, setTrendDays] = useState(30);

    const { data: stats, isLoading: statsLoading } = useBodyCompositionStats();
    const { data: trends, isLoading: trendsLoading } =
        useBodyCompositionTrends(trendDays);

    // Prepare chart data
    const chartData = trends
        ? trends.dates.map((date, index) => ({
              date,
              weight: trends.weights[index],
              bodyFat: trends.body_fat_pcts[index],
              muscleMass: trends.muscle_masses[index],
              water: trends.water_pcts[index],
          }))
        : [];

    const kgToLbs = (kg: number | null) => {
        if (kg === null) return null;
        return kg * 2.20462;
    };

    const StatCard = ({
        title,
        value,
        unit,
        change,
        icon: Icon,
    }: {
        title: string;
        value: number | null;
        unit: string;
        change: number | null;
        icon: any;
    }) => (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">
                    {value !== null ? `${value.toFixed(1)} ${unit}` : "N/A"}
                </div>
                {change !== null && change !== 0 && (
                    <div
                        className={`flex items-center text-xs mt-1 ${change > 0 ? "text-red-500" : "text-green-500"}`}
                    >
                        {change > 0 ? (
                            <TrendingUp className="h-3 w-3 mr-1" />
                        ) : (
                            <TrendingDown className="h-3 w-3 mr-1" />
                        )}
                        {Math.abs(change).toFixed(1)} {unit} from previous
                    </div>
                )}
            </CardContent>
        </Card>
    );

    return (
        <div className="min-h-screen">
            <Navigation />

            <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
                <div className="mb-6">
                    <h1 className="text-3xl font-bold mb-2">
                        Body Composition
                    </h1>
                    <p className="text-muted-foreground">
                        Track your weight, body fat, and muscle mass over time
                    </p>
                </div>

                {statsLoading ? (
                    <div className="text-center py-12 text-muted-foreground">
                        Loading stats...
                    </div>
                ) : stats ? (
                    <>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                            <StatCard
                                title="Current Weight"
                                value={
                                    stats.latest_weight
                                        ? kgToLbs(stats.latest_weight)
                                        : null
                                }
                                unit="lbs"
                                change={
                                    stats.weight_change
                                        ? kgToLbs(stats.weight_change)
                                        : null
                                }
                                icon={Weight}
                            />
                            <StatCard
                                title="Body Fat %"
                                value={stats.latest_body_fat}
                                unit="%"
                                change={stats.body_fat_change}
                                icon={TrendingDown}
                            />
                            <StatCard
                                title="Muscle Mass"
                                value={
                                    stats.latest_muscle_mass
                                        ? kgToLbs(stats.latest_muscle_mass)
                                        : null
                                }
                                unit="lbs"
                                change={
                                    stats.muscle_mass_change
                                        ? kgToLbs(stats.muscle_mass_change)
                                        : null
                                }
                                icon={TrendingUp}
                            />
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Total Measurements
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">
                                        {stats.total_measurements}
                                    </div>
                                    {stats.first_date && stats.latest_date && (
                                        <div className="text-xs text-muted-foreground mt-1">
                                            {format(
                                                new Date(stats.first_date),
                                                "MMM d, yyyy",
                                            )}{" "}
                                            -{" "}
                                            {format(
                                                new Date(stats.latest_date),
                                                "MMM d, yyyy",
                                            )}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </div>

                        <Card className="mb-6">
                            <CardHeader className="flex flex-row items-center justify-between">
                                <CardTitle>Trends</CardTitle>
                                <div className="flex items-center space-x-2">
                                    <label className="text-sm text-muted-foreground">
                                        Period:
                                    </label>
                                    <select
                                        value={trendDays}
                                        onChange={(e) =>
                                            setTrendDays(
                                                parseInt(e.target.value),
                                            )
                                        }
                                        className="bg-background border border-border rounded-md px-3 py-1 text-sm"
                                    >
                                        <option value={7}>7 days</option>
                                        <option value={30}>30 days</option>
                                        <option value={90}>90 days</option>
                                        <option value={180}>180 days</option>
                                        <option value={365}>1 year</option>
                                    </select>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {trendsLoading ? (
                                    <div className="text-center py-12 text-muted-foreground">
                                        Loading trends...
                                    </div>
                                ) : chartData.length > 0 ? (
                                    <ResponsiveContainer
                                        width="100%"
                                        height={400}
                                    >
                                        <LineChart data={chartData}>
                                            <CartesianGrid
                                                strokeDasharray="3 3"
                                                stroke="#374151"
                                            />
                                            <XAxis
                                                dataKey="date"
                                                stroke="#9CA3AF"
                                                tickFormatter={(date) =>
                                                    format(
                                                        new Date(date),
                                                        "MMM d",
                                                    )
                                                }
                                            />
                                            <YAxis
                                                yAxisId="weight"
                                                stroke="#9CA3AF"
                                                label={{
                                                    value: "Weight (lbs)",
                                                    angle: -90,
                                                    position: "insideLeft",
                                                }}
                                            />
                                            <YAxis
                                                yAxisId="percentage"
                                                orientation="right"
                                                stroke="#9CA3AF"
                                                label={{
                                                    value: "Percentage (%)",
                                                    angle: 90,
                                                    position: "insideRight",
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
                                                    if (value === null)
                                                        return ["N/A", name];
                                                    if (name === "Weight")
                                                        return [
                                                            kgToLbs(
                                                                value,
                                                            )?.toFixed(1) +
                                                                " lbs",
                                                            name,
                                                        ];
                                                    if (name === "Muscle Mass")
                                                        return [
                                                            kgToLbs(
                                                                value,
                                                            )?.toFixed(1) +
                                                                " lbs",
                                                            name,
                                                        ];
                                                    return [
                                                        value.toFixed(1) + "%",
                                                        name,
                                                    ];
                                                }}
                                            />
                                            <Legend />
                                            <Line
                                                yAxisId="weight"
                                                type="monotone"
                                                dataKey="weight"
                                                stroke="#3B82F6"
                                                name="Weight"
                                                strokeWidth={2}
                                                dot={{ r: 3 }}
                                                connectNulls
                                            />
                                            <Line
                                                yAxisId="percentage"
                                                type="monotone"
                                                dataKey="bodyFat"
                                                stroke="#EF4444"
                                                name="Body Fat %"
                                                strokeWidth={2}
                                                dot={{ r: 3 }}
                                                connectNulls
                                            />
                                            <Line
                                                yAxisId="weight"
                                                type="monotone"
                                                dataKey="muscleMass"
                                                stroke="#10B981"
                                                name="Muscle Mass"
                                                strokeWidth={2}
                                                dot={{ r: 3 }}
                                                connectNulls
                                            />
                                        </LineChart>
                                    </ResponsiveContainer>
                                ) : (
                                    <div className="text-center py-12 text-muted-foreground">
                                        No trend data available for this period
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </>
                ) : (
                    <Card>
                        <CardContent className="p-12 text-center">
                            <p className="text-muted-foreground">
                                No body composition data available.
                            </p>
                            <p className="text-sm text-muted-foreground mt-2">
                                Connect your smart scale via MQTT to
                                automatically track measurements.
                            </p>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
};

export default BodyComposition;
