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
                        color: change > 0 ? 'var(--error)' : 'var(--success)',
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

    return (
        <>
            <Navigation />
            <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
                <div className="max-w-7xl mx-auto" style={{ padding: 'var(--space-6)' }}>
                    {/* Header */}
                    <div className="animate-in" style={{ marginBottom: 'var(--space-6)' }}>
                        <h1
                            style={{
                                fontFamily: 'var(--font-display)',
                                fontSize: '24px',
                                fontWeight: 600,
                                color: 'var(--text-primary)',
                                letterSpacing: '-0.01em',
                                marginBottom: 'var(--space-2)',
                            }}
                        >
                            BODY COMPOSITION
                        </h1>
                        <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                            Track your weight, body fat, and muscle mass over time
                        </p>
                    </div>

                    {statsLoading ? (
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
                                Loading stats...
                            </p>
                        </div>
                    ) : stats ? (
                        <>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 stagger-children" style={{ gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
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

                            <Card className="animate-in" style={{ animationDelay: '100ms' }}>
                                <CardHeader className="flex flex-row items-center justify-between" style={{ paddingBottom: 'var(--space-4)' }}>
                                    <CardTitle style={{ fontFamily: 'var(--font-display)', fontSize: '18px' }}>
                                        TRENDS
                                    </CardTitle>
                                    <div className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                                        <label style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                                            Period:
                                        </label>
                                        <select
                                            value={trendDays}
                                            onChange={(e) =>
                                                setTrendDays(
                                                    parseInt(e.target.value),
                                                )
                                            }
                                            className="input"
                                            style={{
                                                padding: '6px 12px',
                                                fontSize: '13px',
                                            }}
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
                                        <div className="text-center" style={{ padding: 'var(--space-12) 0' }}>
                                            <div
                                                className="inline-block animate-spin rounded-full border-4 border-t-transparent"
                                                style={{
                                                    width: '40px',
                                                    height: '40px',
                                                    borderColor: 'var(--accent)',
                                                    borderTopColor: 'transparent',
                                                }}
                                            />
                                            <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>
                                                Loading trends...
                                            </p>
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
                                        <div className="text-center" style={{ padding: 'var(--space-12) 0', color: 'var(--text-secondary)' }}>
                                            No trend data available for this period
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </>
                    ) : (
                        <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
                            <CardContent style={{ padding: 'var(--space-12)', textAlign: 'center' }}>
                                <p style={{ color: 'var(--text-secondary)' }}>
                                    No body composition data available.
                                </p>
                                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                                    Connect your smart scale via MQTT to
                                    automatically track measurements.
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
