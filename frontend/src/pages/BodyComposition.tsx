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
        trendDirection = 'neutral',
    }: {
        title: string;
        value: number | null;
        unit: string;
        change: number | null;
        icon: any;
        trendDirection?: 'up-good' | 'down-good' | 'neutral';
    }) => {
        // Determine color based on trend direction preference
        const getTrendColor = () => {
            if (trendDirection === 'neutral' || change === null) return 'var(--text-secondary)';
            const isIncrease = change > 0;
            if (trendDirection === 'up-good') {
                return isIncrease ? 'var(--success)' : 'var(--error)';
            } else { // down-good
                return isIncrease ? 'var(--error)' : 'var(--success)';
            }
        };

        return (
            <div className="stat-card animate-in">
                <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-3)' }}>
                    <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {title}
                    </div>
                    <Icon style={{ width: '20px', height: '20px', color: 'var(--text-muted)' }} />
                </div>
                <div className="stat-card__value">
                    {value !== null ? `${value.toFixed(1)} ${unit}` : "N/A"}
                </div>
                {change !== null && change !== 0 && (
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 'var(--space-1)',
                            fontSize: '12px',
                            marginTop: 'var(--space-2)',
                            color: getTrendColor(),
                        }}
                    >
                        {change > 0 ? (
                            <TrendingUp style={{ width: '14px', height: '14px' }} />
                        ) : (
                            <TrendingDown style={{ width: '14px', height: '14px' }} />
                        )}
                        {Math.abs(change).toFixed(1)} {unit} from previous
                    </div>
                )}
            </div>
        );
    };

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content">
                    {/* Header */}
                    <div className="page__header animate-in">
                        <h1 className="page__title">BODY COMPOSITION</h1>
                        <p className="page__subtitle">Track your weight, body fat, and muscle mass over time</p>
                    </div>

                    {statsLoading ? (
                        <div className="text-center" style={{ padding: 'var(--space-16) 0' }}>
                            <div className="loading-spinner inline-block" />
                            <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
                                Loading stats...
                            </p>
                        </div>
                    ) : stats ? (
                        <>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 section">
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
                                    trendDirection="neutral"
                                />
                                <StatCard
                                    title="Body Fat %"
                                    value={stats.latest_body_fat}
                                    unit="%"
                                    change={stats.body_fat_change}
                                    icon={TrendingDown}
                                    trendDirection="down-good"
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
                                    trendDirection="up-good"
                                />
                                <div className="stat-card animate-in">
                                    <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-3)' }}>
                                        Total Measurements
                                    </div>
                                    <div className="stat-card__value">
                                        {stats.total_measurements}
                                    </div>
                                    {stats.first_date && stats.latest_date && (
                                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
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
                                </div>
                            </div>

                            <Card className="animate-in">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle className="font-display text-xl tracking-tight">
                                        TRENDS
                                    </CardTitle>
                                    <div className="flex items-center gap-2">
                                        <label className="text-[13px] text-[var(--text-muted)]">
                                            Period:
                                        </label>
                                        <select
                                            value={trendDays}
                                            onChange={(e) => setTrendDays(parseInt(e.target.value))}
                                            className="input text-[13px] py-1.5 px-3"
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
                                        <div className="text-center py-12">
                                            <div className="loading-spinner inline-block" style={{ width: '40px', height: '40px' }} />
                                            <p className="mt-4 text-[var(--text-muted)]">Loading trends...</p>
                                        </div>
                                    ) : chartData.length > 0 ? (
                                        <ResponsiveContainer
                                            width="100%"
                                            height={400}
                                        >
                                            <LineChart data={chartData}>
                                                <CartesianGrid
                                                    strokeDasharray="3 3"
                                                    stroke="var(--border)"
                                                />
                                                <XAxis
                                                    dataKey="date"
                                                    stroke="var(--text-muted)"
                                                    style={{ fontSize: '12px' }}
                                                    tickFormatter={(date) =>
                                                        format(
                                                            new Date(date),
                                                            "MMM d",
                                                        )
                                                    }
                                                />
                                                <YAxis
                                                    yAxisId="weight"
                                                    stroke="var(--text-muted)"
                                                    style={{ fontSize: '12px' }}
                                                    label={{
                                                        value: "Weight (lbs)",
                                                        angle: -90,
                                                        position: "insideLeft",
                                                        style: { fill: 'var(--text-muted)' },
                                                    }}
                                                />
                                                <YAxis
                                                    yAxisId="percentage"
                                                    orientation="right"
                                                    stroke="var(--text-muted)"
                                                    style={{ fontSize: '12px' }}
                                                    label={{
                                                        value: "Percentage (%)",
                                                        angle: 90,
                                                        position: "insideRight",
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
                                                    stroke="var(--chart-2)"
                                                    name="Weight"
                                                    strokeWidth={2}
                                                    dot={{ r: 3 }}
                                                    connectNulls
                                                />
                                                <Line
                                                    yAxisId="percentage"
                                                    type="monotone"
                                                    dataKey="bodyFat"
                                                    stroke="var(--error)"
                                                    name="Body Fat %"
                                                    strokeWidth={2}
                                                    dot={{ r: 3 }}
                                                    connectNulls
                                                />
                                                <Line
                                                    yAxisId="weight"
                                                    type="monotone"
                                                    dataKey="muscleMass"
                                                    stroke="var(--accent)"
                                                    name="Muscle Mass"
                                                    strokeWidth={2}
                                                    dot={{ r: 3 }}
                                                    connectNulls
                                                />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    ) : (
                                        <div className="text-center py-12 text-[var(--text-secondary)]">
                                            No trend data available for this period
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </>
                    ) : (
                        <Card className="border-2 border-dashed border-[var(--border)] bg-transparent">
                            <CardContent className="p-12 text-center">
                                <p className="text-[var(--text-secondary)]">
                                    No body composition data available.
                                </p>
                                <p className="text-[13px] text-[var(--text-muted)] mt-2">
                                    Connect your smart scale via MQTT to automatically track measurements.
                                </p>
                            </CardContent>
                        </Card>
                    )}
                </div>
            </div>
        </>
    );
};

export default BodyComposition;
