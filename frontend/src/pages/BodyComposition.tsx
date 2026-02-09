import { useState } from "react";
import { format, parseISO } from "date-fns";
import type { LucideIcon } from "lucide-react";
import { Weight, TrendingDown, TrendingUp } from "lucide-react";
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
    icon: LucideIcon;
    trendDirection?: 'up-good' | 'down-good' | 'neutral';
}) => {
    const getTrendColor = () => {
        if (trendDirection === 'neutral' || change === null) return 'var(--text-secondary)';
        const isIncrease = change > 0;
        if (trendDirection === 'up-good') {
            return isIncrease ? 'var(--success)' : 'var(--error)';
        } else {
            return isIncrease ? 'var(--error)' : 'var(--success)';
        }
    };

    return (
        <div className="stat-card animate-in">
            <div className="flex items-center justify-between stat-card__header">
                <span>{title}</span>
                <Icon style={{ width: '18px', height: '18px', color: 'var(--text-muted)' }} />
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

const BodyComposition = () => {
    const [trendDays, setTrendDays] = useState(30);

    const { data: stats, isLoading: statsLoading } = useBodyCompositionStats();
    const { data: trends, isLoading: trendsLoading } =
        useBodyCompositionTrends(trendDays);

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
                            <div className="grid grid-cols-2 lg:grid-cols-4 section" style={{ gap: 'var(--space-3)' }}>
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
                                    <div className="stat-card__header">
                                        Total Measurements
                                    </div>
                                    <div className="stat-card__value">
                                        {stats.total_measurements}
                                    </div>
                                    {stats.first_date && stats.latest_date && (
                                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
                                            {format(
                                                parseISO(stats.first_date),
                                                "MMM d, yyyy",
                                            )}{" "}
                                            -{" "}
                                            {format(
                                                parseISO(stats.latest_date),
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
                                    <div style={{ width: '130px' }}>
                                        <Select
                                            value={String(trendDays)}
                                            onValueChange={(v) => setTrendDays(Number(v))}
                                        >
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="7">7 days</SelectItem>
                                                <SelectItem value="30">30 days</SelectItem>
                                                <SelectItem value="60">60 days</SelectItem>
                                                <SelectItem value="90">90 days</SelectItem>
                                                <SelectItem value="180">180 days</SelectItem>
                                                <SelectItem value="365">1 year</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    {trendsLoading ? (
                                        <div className="text-center" style={{ padding: 'var(--space-12) 0' }}>
                                            <div className="loading-spinner inline-block" style={{ width: '40px', height: '40px' }} />
                                            <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>Loading trends...</p>
                                        </div>
                                    ) : chartData.length > 0 ? (
                                        <ResponsiveContainer
                                            width="100%"
                                            height={320}
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
                                                            parseISO(date),
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
                                                            parseISO(date),
                                                            "MMM d, yyyy",
                                                        )
                                                    }
                                                    formatter={(
                                                        value: number | undefined,
                                                        name?: string,
                                                    ) => {
                                                        if (value == null)
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
                                        <div style={{ textAlign: 'center', padding: 'var(--space-12) 0', color: 'var(--text-secondary)' }}>
                                            No trend data available for this period
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </>
                    ) : (
                        <Card style={{ border: '2px dashed var(--border)', background: 'transparent' }}>
                            <CardContent className="empty-state">
                                <div className="empty-state__icon">
                                    <Weight style={{ width: '40px', height: '40px', color: 'var(--text-muted)' }} />
                                </div>
                                <h3 className="empty-state__title">NO DATA YET</h3>
                                <p className="empty-state__text">
                                    No body composition data available.
                                </p>
                                <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
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
