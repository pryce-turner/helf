import { useState } from "react";
import { differenceInCalendarDays, format, parseISO } from "date-fns";
import type { LucideIcon } from "lucide-react";
import { Bluetooth, Weight, TrendingDown, TrendingUp } from "lucide-react";
import Navigation from "@/components/Navigation";
import BodySectionTabs from "@/components/BodySectionTabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    useBodyCompositions,
    useBodyCompositionStats,
    useBodyCompositionTrends,
    useDeleteBodyComposition,
    useScaleDrain,
    useSyncBodySpec,
} from "@/hooks/useBodyComposition";
import {
    isSupported as bluetoothSupported,
    loadCredentials,
    saveCredentials,
} from "@/lib/scale";
import type { ScaleCredentials } from "@/lib/scale";
import {
    ComposedChart,
    LineChart,
    Line,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from "recharts";

// openScale is a line; BodySpec is scatter only. This is the whole point of
// plotting them together: bioimpedance is precise but not accurate, so its
// curve carries *shape*, while four DEXA points a year carry *level*. A line
// through the DEXA points would fabricate the months between them.
//
// The pair is validated for colour-vision deficiency in
// docs/plans/0003-units-and-metrics.md §4a (deutan dE 27.5). It replaces the
// per-metric hues on these two charts deliberately: which instrument produced
// a point is semantic, where the metric's hue was decorative - the card title
// already names it. Reusing the metric hues would also have put a green DEXA
// scatter on top of a red body-fat line, the classic deutan collision.
const SCALE_COLOR = "var(--chart-2)";
const DEXA_COLOR = "#16a34a";

/**
 * Format one tooltip value, defensively, because Recharts does not hand these
 * formatters a number.
 *
 * The signature is `number | string | Array<number | string>` — and the two
 * charts here that pair a `<Line>` with a `<Scatter>` do produce the array
 * form, because a scatter point carries its whole coordinate pair. Every
 * formatter on this page was annotated `(value: number | undefined)`, which
 * satisfied the compiler by asserting something untrue, then called
 * `value.toFixed(1)` on an array at runtime.
 *
 * The consequence was far worse than a broken tooltip: the throw happened
 * during render, so React unmounted the whole tree and the page went black
 * with no message, recoverable only by reloading. It looked random because it
 * needed a tooltip to be showing, and it was worst on a phone in landscape,
 * where scrolling drags a finger across the charts continuously.
 *
 * `unknown` in the signature is deliberate. Narrowing is the entire job here,
 * and a narrower parameter type would just recreate the original lie.
 */
export const formatChartValue = (
    value: unknown,
    unit: string,
    label: string,
): [string, string] => {
    // A scatter point arrives as its coordinate pair; the measurement is last.
    const raw = Array.isArray(value) ? value[value.length - 1] : value;
    const n = typeof raw === "number" ? raw : Number(raw);
    if (raw === null || raw === undefined || raw === "" || !Number.isFinite(n)) {
        return ["N/A", label];
    }
    return [`${n.toFixed(1)}${unit}`, label];
};


/**
 * What to call an instrument in front of a person.
 *
 * `observation.source` is one of three machine names and two technologies. The
 * distinction that matters to a reader is bioimpedance vs DEXA — which of the
 * two numbers to trust for level — not which DEXA clinic produced a scan.
 */
const sourceLabel = (source: string | null): string => {
    if (source === "openscale") return "the scale (bioimpedance)";
    if (source === "bodyspec" || source === "dexafit") return "a DEXA scan";
    return "an unknown instrument";
};

// The sparse series gets the heavier mark. Visual weight is inverted against
// data volume on purpose, because the sparse series is the accurate one. The
// surface-coloured ring keeps a dot legible where it lands on the line.
const DexaDot = (props: { cx?: number; cy?: number }) => {
    const { cx, cy } = props;
    if (cx == null || cy == null) return null;
    return (
        <circle
            cx={cx}
            cy={cy}
            r={5}
            fill={DEXA_COLOR}
            stroke="var(--bg-secondary)"
            strokeWidth={2}
        />
    );
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

/**
 * Paste-a-token BodySpec import.
 *
 * The token lives in local component state and nowhere else - not in React
 * Query's cache, not in localStorage, not in a context. It is cleared on
 * success, and unmounting the page discards it. That mirrors the backend,
 * where its whole lifetime is one request
 * (docs/plans/0008-bodyspec-integration.md §3).
 *
 * `type="password"` so it is not shoulder-surfable or captured in a
 * screenshot.
 */
const BodySpecSync = () => {
    const [token, setToken] = useState("");
    const sync = useSyncBodySpec();

    const submit = (event: React.FormEvent) => {
        event.preventDefault();
        if (!token.trim()) return;
        sync.mutate(token.trim(), { onSuccess: () => setToken("") });
    };

    const failed = sync.error as { response?: { status?: number; data?: { detail?: string } } } | null;
    const expired = failed?.response?.status === 401;

    return (
        <Card className="animate-in section">
            <CardHeader style={{ paddingBottom: 0 }}>
                <CardTitle style={{ fontSize: '14px', fontWeight: 600, color: DEXA_COLOR, letterSpacing: '0.03em', textTransform: 'uppercase' }}>
                    Import DEXA scans
                </CardTitle>
            </CardHeader>
            <CardContent>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
                    Paste an access token from{" "}
                    <a
                        href="https://app.bodyspec.com/docs#description/introduction"
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: 'var(--accent)' }}
                    >
                        app.bodyspec.com/docs
                    </a>
                    {" "}(the Authorize button). Tokens last 60 minutes and are never stored.
                </p>
                <form onSubmit={submit} style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                    <Input
                        type="password"
                        value={token}
                        onChange={(e) => setToken(e.target.value)}
                        placeholder="BodySpec access token"
                        autoComplete="off"
                        style={{ flex: '1 1 260px' }}
                    />
                    <Button type="submit" disabled={!token.trim() || sync.isPending}>
                        {sync.isPending ? "Syncing..." : "Sync"}
                    </Button>
                </form>

                {sync.data && (
                    <p style={{ fontSize: '12px', color: 'var(--success)', marginTop: 'var(--space-3)' }}>
                        {sync.data.imported > 0
                            ? `Imported ${sync.data.imported} scan${sync.data.imported === 1 ? "" : "s"} (${sync.data.metrics_written} measurements).`
                            : "Already up to date"}
                        {sync.data.skipped > 0 && ` ${sync.data.skipped} already held.`}
                    </p>
                )}
                {sync.isError && (
                    <p style={{ fontSize: '12px', color: 'var(--error)', marginTop: 'var(--space-3)' }}>
                        {expired
                            ? "That token was rejected - they expire after 60 minutes. Paste a fresh one."
                            : failed?.response?.data?.detail ?? "Sync failed."}
                    </p>
                )}
            </CardContent>
        </Card>
    );
};

/**
 * Pairing for the BF720 - plan 0015.
 *
 * Config only. The drain button itself lives in `ScaleTile`, up beside the
 * stats, because reading the scale is a thing you do every few days and
 * entering a consent code is a thing you do once. Two buttons would also mean
 * two `useScaleDrain` mutations and so two pending states, and Web Bluetooth
 * grants one connection per gesture - the second tap would fail.
 *
 * The whole control hides where `navigator.bluetooth` is missing rather than
 * offering a button that cannot work. That is Firefox always, and Brave until
 * Web Bluetooth is enabled at brave://flags.
 */
const ScaleDrain = ({
    credentials,
    onCredentials,
    busy,
}: {
    credentials: ScaleCredentials | null;
    onCredentials: (next: ScaleCredentials | null) => void;
    busy: boolean;
}) => {
    const supported = bluetoothSupported();
    const [slot, setSlot] = useState("1");
    const [code, setCode] = useState("");

    if (!supported) return null;

    const pair = (event: React.FormEvent) => {
        event.preventDefault();
        const userIndex = Number(slot);
        const consentCode = Number(code);
        if (!Number.isInteger(userIndex) || !Number.isInteger(consentCode)) return;
        onCredentials({ userIndex, consentCode });
    };

    return (
        <Card className="animate-in section">
            <CardHeader style={{ paddingBottom: 0 }}>
                <CardTitle style={{ fontSize: '14px', fontWeight: 600, color: SCALE_COLOR, letterSpacing: '0.03em', textTransform: 'uppercase' }}>
                    Read scale
                </CardTitle>
            </CardHeader>
            <CardContent>
                {credentials ? (
                    <>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
                            Paired to slot {credentials.userIndex}. The scale
                            stores its last 30 weighings, so weigh whenever and
                            read them all at once with the button above.
                        </p>
                        <Button
                            variant="ghost"
                            onClick={() => onCredentials(null)}
                            disabled={busy}
                        >
                            Change slot
                        </Button>
                    </>
                ) : (
                    <>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
                            The BF720 will not release measurements until it is
                            given the consent code for a user slot. Both are set
                            on the scale, under its user memory.
                        </p>
                        <form onSubmit={pair} style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                            <Input
                                type="number"
                                min={1}
                                max={8}
                                value={slot}
                                onChange={(e) => setSlot(e.target.value)}
                                placeholder="Slot"
                                aria-label="Scale user slot"
                                style={{ flex: '0 0 90px' }}
                            />
                            <Input
                                type="number"
                                value={code}
                                onChange={(e) => setCode(e.target.value)}
                                placeholder="Consent code"
                                aria-label="Consent code"
                                style={{ flex: '1 1 160px' }}
                            />
                            <Button type="submit" disabled={!code.trim()}>
                                Save
                            </Button>
                        </form>
                    </>
                )}
            </CardContent>
        </Card>
    );
};

/**
 * The drain, sitting in the stats grid where the measurement count used to be.
 *
 * It takes the fourth tile only once the scale is paired; unpaired, the grid
 * runs to three and the pairing form below is the only scale control on the
 * page. There is no automatic version of this and there cannot be: Web
 * Bluetooth requires a user gesture per connection and is absent from service
 * workers, so a drain happens on a tap or not at all. The scale's 30-reading
 * ring is what makes that sufficient - weigh whenever, drain occasionally.
 *
 * The outcome of the last drain reads out here rather than beside the pairing
 * form, next to the button that caused it.
 */
const ScaleTile = ({
    credentials,
    drain,
}: {
    credentials: ScaleCredentials | null;
    drain: ReturnType<typeof useScaleDrain>;
}) => {
    if (!bluetoothSupported() || !credentials) return null;

    const failed = drain.error as Error | null;

    return (
        <div className="stat-card animate-in">
            <div className="flex items-center justify-between stat-card__header">
                <span>Scale</span>
                <Bluetooth style={{ width: '18px', height: '18px', color: 'var(--text-muted)' }} />
            </div>
            <Button
                onClick={() => drain.mutate(credentials)}
                disabled={drain.isPending}
                style={{ width: '100%', marginTop: 'var(--space-2)' }}
            >
                {drain.isPending ? "Reading..." : "Read scale"}
            </Button>
            {drain.data && !drain.isPending && (
                <div style={{ fontSize: '11px', color: 'var(--success)', marginTop: 'var(--space-2)' }}>
                    {drain.data.readings_received === 0
                        ? "The scale had nothing stored."
                        : `${drain.data.readings_received} reading${drain.data.readings_received === 1 ? "" : "s"} - ${drain.data.imported} new, ${drain.data.skipped} already held.`}
                </div>
            )}
            {drain.isError && !drain.isPending && (
                <div style={{ fontSize: '11px', color: 'var(--error)', marginTop: 'var(--space-2)' }}>
                    {failed?.message ?? "Could not read the scale."}
                </div>
            )}
        </div>
    );
};

/**
 * Every measurement, newest *ingestion* first, with a way to delete one.
 *
 * Ordered by when the row arrived rather than when the weighing happened,
 * because that is the order that surfaces bad rows. A scale that has been
 * reset reports its factory clock: the BF720 filed a reading taken in August
 * 2026 under 2025-01-01, which in observed order sits buried mid-history where
 * nobody would ever scroll. Both timestamps are shown side by side so the gap
 * is the visible thing.
 */
const MeasurementLog = () => {
    const { data: measurements, isLoading } = useBodyCompositions({
        limit: 50,
        sort: "ingested",
    });
    // Shares the page's cached stats query - the count and span are one line
    // of context on the table they describe, not a tile's worth of screen.
    const { data: stats } = useBodyCompositionStats();
    const remove = useDeleteBodyComposition();
    const [confirming, setConfirming] = useState<number | null>(null);

    if (isLoading || !measurements?.length) return null;

    const cell: React.CSSProperties = {
        padding: "var(--space-2) var(--space-3)",
        borderBottom: "1px solid var(--border)",
        whiteSpace: "nowrap",
    };
    const head: React.CSSProperties = {
        ...cell,
        fontSize: "11px",
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        textAlign: "left",
        // The body scrolls under this now, so it has to stay put — and it
        // needs its own background or the rows show through it.
        position: "sticky",
        top: 0,
        background: "var(--bg-secondary)",
        zIndex: 1,
    };
    const num = (v: number | null | undefined, dp = 1) =>
        v == null ? "—" : v.toFixed(dp);

    return (
        <Card className="animate-in section">
            <CardHeader style={{ paddingBottom: 0 }}>
                <div className="flex items-center justify-between" style={{ gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                    <CardTitle style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-secondary)', letterSpacing: '0.03em', textTransform: 'uppercase' }}>
                        All measurements
                    </CardTitle>
                    {stats && (
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)', whiteSpace: 'nowrap' }}>
                            {stats.total_measurements} total
                            {stats.first_date && stats.latest_date && (
                                <>
                                    {" \u00b7 "}
                                    {format(parseISO(stats.first_date), "MMM d, yyyy")}
                                    {" \u2013 "}
                                    {format(parseISO(stats.latest_date), "MMM d, yyyy")}
                                </>
                            )}
                        </span>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 'var(--space-3)' }}>
                    Newest first by when it was ingested, not when it was
                    weighed — a scale with a wrong clock files a reading years
                    out of place, and this is where you find it.
                </p>
                {/* Scrolls inside its own box, in both directions, and the
                    vertical cap is not cosmetic. Fifty rows made this table
                    65% of a 3528px document, and the app has two fixed
                    `backdrop-filter: blur(16px)` navs sitting over it — a
                    combination Chrome and Safari both mis-composite, blanking
                    the viewport to the page background at random while
                    scrolling, with no JS error and no recovery short of a
                    reload. Keeping the document short keeps the compositor out
                    of that state, and 162 measurements read better in a pane
                    than as an endless page anyway. */}
                <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: "60vh", overscrollBehavior: "contain" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                        <thead>
                            <tr>
                                <th style={head}>Weighed</th>
                                <th style={head}>Ingested</th>
                                <th style={head}>Source</th>
                                <th style={{ ...head, textAlign: "right" }}>Weight</th>
                                <th style={{ ...head, textAlign: "right" }}>Fat %</th>
                                <th style={{ ...head, textAlign: "right" }}>Muscle %</th>
                                <th style={{ ...head, textAlign: "right" }}>Water %</th>
                                <th style={head} aria-label="Actions" />
                            </tr>
                        </thead>
                        <tbody>
                            {measurements.map((m) => {
                                // A gap of more than a day between weighing and
                                // ingestion is either a late drain or a bad
                                // clock. Both are worth seeing at a glance.
                                const skewed =
                                    Math.abs(
                                        differenceInCalendarDays(
                                            parseISO(m.created_at as unknown as string),
                                            parseISO(m.timestamp as unknown as string),
                                        ),
                                    ) > 1;
                                return (
                                    <tr key={m.doc_id}>
                                        <td style={{ ...cell, color: skewed ? "var(--warning)" : undefined, fontFamily: "var(--font-mono, monospace)" }}>
                                            {format(parseISO(m.timestamp as unknown as string), "yyyy-MM-dd HH:mm")}
                                        </td>
                                        <td style={{ ...cell, color: "var(--text-secondary)", fontFamily: "var(--font-mono, monospace)" }}>
                                            {format(parseISO(m.created_at as unknown as string), "yyyy-MM-dd HH:mm")}
                                        </td>
                                        <td style={{ ...cell, color: "var(--text-secondary)" }}>{m.source}</td>
                                        <td style={{ ...cell, textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>{num(m.weight)}</td>
                                        <td style={{ ...cell, textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>{num(m.body_fat_pct)}</td>
                                        <td style={{ ...cell, textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>{num(m.muscle_mass)}</td>
                                        <td style={{ ...cell, textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>{num(m.water_pct)}</td>
                                        <td style={{ ...cell, textAlign: "right" }}>
                                            {/* Two taps, not a browser confirm(): a
                                                native dialog blocks everything and
                                                cannot be styled or dismissed here. */}
                                            {confirming === m.doc_id ? (
                                                <span style={{ display: "inline-flex", gap: "var(--space-2)" }}>
                                                    <Button
                                                        style={{ background: "var(--error)", height: "28px", padding: "0 10px" }}
                                                        onClick={() => {
                                                            remove.mutate(m.doc_id);
                                                            setConfirming(null);
                                                        }}
                                                    >
                                                        Delete
                                                    </Button>
                                                    <Button variant="ghost" style={{ height: "28px", padding: "0 10px" }} onClick={() => setConfirming(null)}>
                                                        Cancel
                                                    </Button>
                                                </span>
                                            ) : (
                                                <Button variant="ghost" style={{ height: "28px", padding: "0 10px", color: "var(--text-muted)" }} onClick={() => setConfirming(m.doc_id)}>
                                                    Delete
                                                </Button>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </CardContent>
        </Card>
    );
};

const BodyComposition = () => {
    const [trendDays, setTrendDays] = useState(30);

    // Held here because two children read it: the tile that drains the scale
    // and the form that pairs it. Saving from the form has to make the tile
    // appear in the same render.
    const [credentials, setStoredCredentials] = useState(() => loadCredentials());
    const drain = useScaleDrain();

    const setCredentials = (next: ScaleCredentials | null) => {
        if (next) saveCredentials(next);
        setStoredCredentials(next);
    };

    const { data: stats, isLoading: statsLoading } = useBodyCompositionStats();
    const { data: trends, isLoading: trendsLoading } =
        useBodyCompositionTrends(trendDays);

    // Weight and body fat are split by instrument; muscle % and water % are
    // not, because only those two quantities are genuinely dual-source. DEXA
    // reports `lean_mass_kg`, a mass, where openScale reports a percentage of
    // a different model - they share no axis and neither refines the other.
    const chartData = trends
        ? trends.dates.map((date, index) => {
              const isDexa = trends.sources[index] === "bodyspec";
              return {
                  date,
                  weight: trends.weights[index],
                  bodyFat: trends.body_fat_pcts[index],
                  weightScale: isDexa ? null : trends.weights[index],
                  weightDexa: isDexa ? trends.weights[index] : null,
                  bodyFatScale: isDexa ? null : trends.body_fat_pcts[index],
                  bodyFatDexa: isDexa ? trends.body_fat_pcts[index] : null,
                  muscleMass: trends.muscle_masses[index],
                  water: trends.water_pcts[index],
              };
          })
        : [];

    const hasDexa = chartData.some((d) => d.weightDexa != null || d.bodyFatDexa != null);

    // The shortest offered period that would reach the last measurement. Null
    // when the current period already reaches it, or when a year does not.
    const PERIODS = [7, 30, 60, 90, 180, 365];
    const daysSinceLatest = stats?.latest_date
        ? differenceInCalendarDays(new Date(), parseISO(stats.latest_date))
        : null;
    const periodShowingLatest =
        daysSinceLatest != null
            ? (PERIODS.find((d) => d > daysSinceLatest && d > trendDays) ?? null)
            : null;

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content">
                    {/* Header */}
                    <div className="page__header animate-in">
                        <h1 className="page__title">BODY</h1>
                        <p className="page__subtitle">Track your weight, body fat, and muscle mass over time</p>
                    </div>

                    <BodySectionTabs />

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
                                {/* Weight is stored in lbs (ADR-0003) - no conversion. */}
                                <StatCard
                                    title="Current Weight"
                                    value={stats.latest_weight}
                                    unit="lbs"
                                    change={stats.weight_change}
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
                                {/* `muscle_mass` is a PERCENTAGE despite the name - openScale
                                    reports muscle as a fraction of body mass. It used to be run
                                    through kgToLbs, rendering 39.1% as "86.2 lbs", which looked
                                    plausible for a ~195 lb man and so went unnoticed. */}
                                <StatCard
                                    title="Muscle"
                                    value={stats.latest_muscle_mass}
                                    unit="%"
                                    change={stats.muscle_mass_change}
                                    icon={TrendingUp}
                                    trendDirection="up-good"
                                />
                                {/* The measurement count used to sit here. It
                                    is a fact you read once and then never
                                    again, so it moved to a line on the table
                                    it describes, and the tile went to the one
                                    control on this page you press repeatedly. */}
                                <ScaleTile credentials={credentials} drain={drain} />
                            </div>

                            {/* The stats describe one instrument's series, and
                                which one is not cosmetic: the scale read 6.15
                                points of body fat above the DEXA scan taken the
                                same day. `primary_source` is on the response
                                precisely so a reader knows which series a delta
                                belongs to, and it was going unrendered. */}
                            {stats.latest_source && (
                                <p
                                    className="section"
                                    style={{
                                        fontSize: '12px',
                                        color: 'var(--text-muted)',
                                        marginTop: 'calc(-1 * var(--space-2))',
                                    }}
                                >
                                    Latest from {sourceLabel(stats.latest_source)}
                                    {stats.latest_date &&
                                        ` on ${format(parseISO(stats.latest_date), "MMM d, yyyy")}`}
                                    . Changes compare the two most recent readings from{" "}
                                    {sourceLabel(stats.primary_source)} — never across
                                    instruments.
                                </p>
                            )}

                            {/* Period selector */}
                            <div className="flex items-center justify-between animate-in" style={{ marginBottom: 'var(--space-4)' }}>
                                <h2 className="page__title page__title--compact" style={{ fontSize: '20px' }}>TRENDS</h2>
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
                            </div>

                            {trendsLoading ? (
                                <div className="text-center" style={{ padding: 'var(--space-12) 0' }}>
                                    <div className="loading-spinner inline-block" style={{ width: '40px', height: '40px' }} />
                                    <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)' }}>Loading trends...</p>
                                </div>
                            ) : chartData.length > 0 ? (
                                <div className="chart-grid">
                                    {/* Only worth the space once both instruments are
                                        present; with one source the marks need no
                                        explaining. */}
                                    {hasDexa && (
                                        <div className="chart-grid__legend flex items-center animate-in" style={{ gap: 'var(--space-4)', fontSize: '11px', color: 'var(--text-secondary)' }}>
                                            <span className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                                                <span style={{ display: 'inline-block', width: '16px', height: '2px', backgroundColor: SCALE_COLOR }} />
                                                Scale (bioimpedance)
                                            </span>
                                            <span className="flex items-center" style={{ gap: 'var(--space-2)' }}>
                                                <span style={{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', backgroundColor: DEXA_COLOR, border: '2px solid var(--bg-secondary)' }} />
                                                DEXA — points only, never joined
                                            </span>
                                        </div>
                                    )}

                                    {/* Weight Chart */}
                                    {chartData.some(d => d.weight != null) && (
                                        <Card className="animate-in">
                                            <CardHeader style={{ paddingBottom: 0 }}>
                                                <CardTitle style={{ fontSize: '14px', fontWeight: 600, color: 'var(--chart-2)', letterSpacing: '0.03em', textTransform: 'uppercase' }}>
                                                    Weight
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <ResponsiveContainer width="100%" height={220}>
                                                    <ComposedChart data={chartData}>
                                                        <CartesianGrid stroke="var(--border)" />
                                                        <XAxis
                                                            dataKey="date"
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            tickFormatter={(date) => format(parseISO(date), "MMM d")}
                                                        />
                                                        <YAxis
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            domain={['auto', 'auto']}
                                                            tickFormatter={(v) => v.toFixed(0)}
                                                            padding={{ top: 10, bottom: 10 }}
                                                        />
                                                        <Tooltip
                                                            contentStyle={{
                                                                backgroundColor: "var(--bg-tertiary)",
                                                                border: "1px solid var(--border)",
                                                                borderRadius: 'var(--radius-md)',
                                                                color: 'var(--text-primary)',
                                                            }}
                                                            labelFormatter={(date) => format(parseISO(date), "MMM d, yyyy")}
                                                            formatter={(value, name) =>
                                                                formatChartValue(value, " lbs", (name as string) ?? "Weight")
                                                            }
                                                        />
                                                        {/* One y-axis, deliberately. Two scales would
                                                            make the offset between the instruments
                                                            unreadable, and that offset is the most
                                                            useful thing this chart shows. */}
                                                        <Line
                                                            type="monotone"
                                                            dataKey="weightScale"
                                                            stroke={SCALE_COLOR}
                                                            name="Scale"
                                                            strokeWidth={2}
                                                            dot={false}
                                                            connectNulls
                                                        />
                                                        <Scatter
                                                            dataKey="weightDexa"
                                                            name="DEXA"
                                                            fill={DEXA_COLOR}
                                                            shape={<DexaDot />}
                                                        />
                                                    </ComposedChart>
                                                </ResponsiveContainer>
                                            </CardContent>
                                        </Card>
                                    )}

                                    {/* Body Fat % Chart */}
                                    {chartData.some(d => d.bodyFat != null) && (
                                        <Card className="animate-in">
                                            <CardHeader style={{ paddingBottom: 0 }}>
                                                <CardTitle style={{ fontSize: '14px', fontWeight: 600, color: 'var(--error)', letterSpacing: '0.03em', textTransform: 'uppercase' }}>
                                                    Body Fat %
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <ResponsiveContainer width="100%" height={220}>
                                                    <ComposedChart data={chartData}>
                                                        <CartesianGrid stroke="var(--border)" />
                                                        <XAxis
                                                            dataKey="date"
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            tickFormatter={(date) => format(parseISO(date), "MMM d")}
                                                        />
                                                        <YAxis
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            domain={['auto', 'auto']}
                                                            tickFormatter={(v) => v.toFixed(1) + "%"}
                                                            padding={{ top: 10, bottom: 10 }}
                                                        />
                                                        <Tooltip
                                                            contentStyle={{
                                                                backgroundColor: "var(--bg-tertiary)",
                                                                border: "1px solid var(--border)",
                                                                borderRadius: 'var(--radius-md)',
                                                                color: 'var(--text-primary)',
                                                            }}
                                                            labelFormatter={(date) => format(parseISO(date), "MMM d, yyyy")}
                                                            formatter={(value, name) =>
                                                                formatChartValue(value, "%", (name as string) ?? "Body Fat")
                                                            }
                                                        />
                                                        {/* The two disagree by several points and
                                                            always will - bioimpedance reads high.
                                                            Keeping them as separate marks is what
                                                            stops that gap reading as fat lost. */}
                                                        <Line
                                                            type="monotone"
                                                            dataKey="bodyFatScale"
                                                            stroke={SCALE_COLOR}
                                                            name="Scale"
                                                            strokeWidth={2}
                                                            dot={false}
                                                            connectNulls
                                                        />
                                                        <Scatter
                                                            dataKey="bodyFatDexa"
                                                            name="DEXA"
                                                            fill={DEXA_COLOR}
                                                            shape={<DexaDot />}
                                                        />
                                                    </ComposedChart>
                                                </ResponsiveContainer>
                                            </CardContent>
                                        </Card>
                                    )}

                                    {/* Muscle Mass Chart */}
                                    {chartData.some(d => d.muscleMass != null) && (
                                        <Card className="animate-in">
                                            <CardHeader style={{ paddingBottom: 0 }}>
                                                <CardTitle style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent)', letterSpacing: '0.03em', textTransform: 'uppercase' }}>
                                                    Muscle %
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <ResponsiveContainer width="100%" height={220}>
                                                    <LineChart data={chartData}>
                                                        <CartesianGrid stroke="var(--border)" />
                                                        <XAxis
                                                            dataKey="date"
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            tickFormatter={(date) => format(parseISO(date), "MMM d")}
                                                        />
                                                        <YAxis
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            domain={['auto', 'auto']}
                                                            tickFormatter={(v) => v.toFixed(1) + "%"}
                                                            padding={{ top: 10, bottom: 10 }}
                                                        />
                                                        <Tooltip
                                                            contentStyle={{
                                                                backgroundColor: "var(--bg-tertiary)",
                                                                border: "1px solid var(--border)",
                                                                borderRadius: 'var(--radius-md)',
                                                                color: 'var(--text-primary)',
                                                            }}
                                                            labelFormatter={(date) => format(parseISO(date), "MMM d, yyyy")}
                                                            formatter={(value) =>
                                                                formatChartValue(value, " %", "Muscle %")
                                                            }
                                                        />
                                                        <Line
                                                            type="monotone"
                                                            dataKey="muscleMass"
                                                            stroke="var(--accent)"
                                                            name="Muscle Mass"
                                                            strokeWidth={2}
                                                            dot={false}
                                                            connectNulls
                                                        />
                                                    </LineChart>
                                                </ResponsiveContainer>
                                            </CardContent>
                                        </Card>
                                    )}

                                    {/* Water % Chart */}
                                    {chartData.some(d => d.water != null) && (
                                        <Card className="animate-in">
                                            <CardHeader style={{ paddingBottom: 0 }}>
                                                <CardTitle style={{ fontSize: '14px', fontWeight: 600, color: 'var(--info)', letterSpacing: '0.03em', textTransform: 'uppercase' }}>
                                                    Water %
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <ResponsiveContainer width="100%" height={220}>
                                                    <LineChart data={chartData}>
                                                        <CartesianGrid stroke="var(--border)" />
                                                        <XAxis
                                                            dataKey="date"
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            tickFormatter={(date) => format(parseISO(date), "MMM d")}
                                                        />
                                                        <YAxis
                                                            stroke="var(--text-muted)"
                                                            style={{ fontSize: '11px' }}
                                                            domain={['auto', 'auto']}
                                                            tickFormatter={(v) => v.toFixed(1) + "%"}
                                                            padding={{ top: 10, bottom: 10 }}
                                                        />
                                                        <Tooltip
                                                            contentStyle={{
                                                                backgroundColor: "var(--bg-tertiary)",
                                                                border: "1px solid var(--border)",
                                                                borderRadius: 'var(--radius-md)',
                                                                color: 'var(--text-primary)',
                                                            }}
                                                            labelFormatter={(date) => format(parseISO(date), "MMM d, yyyy")}
                                                            formatter={(value) =>
                                                                formatChartValue(value, "%", "Water")
                                                            }
                                                        />
                                                        <Line
                                                            type="monotone"
                                                            dataKey="water"
                                                            stroke="var(--info)"
                                                            name="Water %"
                                                            strokeWidth={2}
                                                            dot={false}
                                                            connectNulls
                                                        />
                                                    </LineChart>
                                                </ResponsiveContainer>
                                            </CardContent>
                                        </Card>
                                    )}
                                </div>
                            ) : (
                                /* An empty window is the default view whenever
                                   the last measurement is more than 30 days old,
                                   which is most of the time between DEXA scans.
                                   Say what is actually true and offer the period
                                   that would show something, rather than leaving
                                   a bare sentence and a period menu to guess at. */
                                <div
                                    className="empty-state"
                                    style={{ padding: 'var(--space-12) 0' }}
                                >
                                    <div className="empty-state__title">
                                        Nothing measured in this period
                                    </div>
                                    {stats.latest_date && (
                                        <p className="empty-state__text">
                                            The most recent measurement is from{" "}
                                            {format(
                                                parseISO(stats.latest_date),
                                                "MMMM d, yyyy",
                                            )}
                                            .
                                        </p>
                                    )}
                                    {periodShowingLatest && (
                                        <Button
                                            variant="ghost"
                                            style={{ marginTop: 'var(--space-4)' }}
                                            onClick={() => setTrendDays(periodShowingLatest)}
                                        >
                                            Show the last {periodShowingLatest} days
                                        </Button>
                                    )}
                                </div>
                            )}
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
                                    Read your scale over Bluetooth below, or import a DEXA scan.
                                </p>
                            </CardContent>
                        </Card>
                    )}

                    {/* Setup, not daily use: below the trends they feed, and
                        outside the stats branch so an empty database still
                        offers the two ways to fill it. */}
                    <ScaleDrain
                        credentials={credentials}
                        onCredentials={setCredentials}
                        busy={drain.isPending}
                    />
                    <BodySpecSync />

                    <MeasurementLog />
                </div>
            </div>
        </>
    );
};

export default BodyComposition;
