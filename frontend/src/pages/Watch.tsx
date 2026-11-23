import { useCallback, useEffect, useRef, useState } from "react";
import { Bluetooth, Watch as WatchIcon } from "lucide-react";
import Navigation from "@/components/Navigation";
import BodySectionTabs from "@/components/BodySectionTabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { watchApi } from "@/lib/api";
import { type PollOutcome, pollLoop, pollOnce } from "@/lib/unaSync";
import {
    canReconnectSilently,
    connectWatch,
    isSupported,
    pairWatch,
    rememberedWatch,
} from "@/lib/unaWatch";

/**
 * Polling the UNA Watch from an always-on phone (plan 0023).
 *
 * Runs only while this page is open and in front: Web Bluetooth has no
 * background mode. While polling it holds a screen wake lock so Android does
 * not throttle the page; the phone is expected to sit on a charger.
 */

const INTERVALS = [5, 15, 30, 60];
const INTERVAL_KEY = "helf.watch.intervalMinutes";

function loadInterval(): number {
    try {
        const v = Number(localStorage.getItem(INTERVAL_KEY));
        return INTERVALS.includes(v) ? v : 15;
    } catch {
        return 15;
    }
}

function describe(o: PollOutcome): string {
    switch (o.kind) {
        case "synced": {
            const { fetched, listed, skipped } = o.report;
            const parts = [
                fetched.length
                    ? `${fetched.length} file${fetched.length === 1 ? "" : "s"} uploaded`
                    : "nothing new",
                `${listed} on the watch`,
            ];
            if (skipped.length) parts.push(`${skipped.length} skipped`);
            return parts.join(", ");
        }
        default:
            return o.message;
    }
}

const COLORS: Record<PollOutcome["kind"], string> = {
    synced: "var(--success)",
    // The expected state of a watch on someone's wrist away from the phone,
    // so plain text, not an error colour.
    unreachable: "var(--text-secondary)",
    unpaired: "var(--warning)",
    unsupported: "var(--error)",
    error: "var(--error)",
};

type WakeLockSentinelLike = { release(): Promise<void> };

export default function Watch() {
    const supported = isSupported();
    const [device, setDevice] = useState<BluetoothDevice | null>(null);
    const [intervalMin, setIntervalMin] = useState(loadInterval);
    const [polling, setPolling] = useState(false);
    const [busy, setBusy] = useState(false);
    const [log, setLog] = useState<{ at: Date; text: string; color: string }[]>([]);
    const [held, setHeld] = useState<number | null>(null);
    const abort = useRef<AbortController | null>(null);
    const wakeLock = useRef<WakeLockSentinelLike | null>(null);

    const append = useCallback((text: string, color = "var(--text-muted)") => {
        setLog((l) => [{ at: new Date(), text, color }, ...l].slice(0, 40));
    }, []);

    const refreshHeld = useCallback(() => {
        watchApi
            .manifest()
            .then((files) => setHeld(files.length))
            .catch(() => setHeld(null));
    }, []);

    useEffect(() => {
        if (!supported) return;
        rememberedWatch().then((d) => d && setDevice(d));
        refreshHeld();
    }, [supported, refreshHeld]);

    const onOutcome = useCallback(
        (o: PollOutcome) => {
            append(describe(o), COLORS[o.kind]);
            if (o.kind === "synced") {
                for (const s of o.report.skipped) append(`skipped ${s.path}: ${s.reason}`, "var(--warning)");
                refreshHeld();
            }
        },
        [append, refreshHeld],
    );

    const deps = useCallback(
        () => ({
            connect: () => connectWatch(device),
            api: watchApi,
            log: (m: string) => append(m),
        }),
        [device, append],
    );

    // Keep the screen on while polling, and take the lock back when the page
    // returns to the front: Android drops it whenever the page is hidden.
    useEffect(() => {
        if (!polling) return;
        const acquire = async () => {
            try {
                const wl = (navigator as Navigator & {
                    wakeLock?: { request(type: "screen"): Promise<WakeLockSentinelLike> };
                }).wakeLock;
                if (wl && document.visibilityState === "visible") {
                    wakeLock.current = await wl.request("screen");
                }
            } catch {
                append("Could not hold the screen on; polling may stall when it sleeps.", "var(--warning)");
            }
        };
        void acquire();
        const onVisible = () => document.visibilityState === "visible" && void acquire();
        document.addEventListener("visibilitychange", onVisible);
        return () => {
            document.removeEventListener("visibilitychange", onVisible);
            void wakeLock.current?.release().catch(() => {});
            wakeLock.current = null;
        };
    }, [polling, append]);

    useEffect(() => () => abort.current?.abort(), []);

    const pair = async () => {
        // First thing in the tap: the chooser needs transient activation.
        try {
            const d = await pairWatch();
            setDevice(d);
            append(`Paired with ${d.name ?? "the watch"}.`, "var(--success)");
        } catch (e) {
            append((e as Error).message, "var(--error)");
        }
    };

    const syncNow = async () => {
        setBusy(true);
        try {
            onOutcome(await pollOnce(deps()));
        } finally {
            setBusy(false);
        }
    };

    const start = () => {
        const controller = new AbortController();
        abort.current = controller;
        setPolling(true);
        append(`Polling every ${intervalMin} min.`);
        void pollLoop(
            {
                ...deps(),
                onOutcome: (o) => {
                    onOutcome(o);
                    setBusy(false);
                },
            },
            { intervalMs: intervalMin * 60_000, signal: controller.signal },
        ).finally(() => setPolling(false));
    };

    const stop = () => {
        abort.current?.abort();
        abort.current = null;
        setPolling(false);
        append("Stopped polling.");
    };

    const chooseInterval = (m: number) => {
        setIntervalMin(m);
        try {
            localStorage.setItem(INTERVAL_KEY, String(m));
        } catch {
            // Private mode: the default comes back next time.
        }
    };

    return (
        <>
            <Navigation />
            <div className="page">
                <div className="page__content">
                    <div className="page__header animate-in">
                        <h1 className="page__title">Watch</h1>
                        <p className="page__subtitle">
                            Daily health and workouts from the UNA Watch, over Bluetooth
                        </p>
                    </div>

                    <BodySectionTabs />

                    {!supported ? (
                        <Card className="animate-in section">
                            <CardContent style={{ paddingTop: "var(--space-4)", color: "var(--text-secondary)" }}>
                                This browser has no Web Bluetooth. Open Helf in Chrome on the Android phone.
                            </CardContent>
                        </Card>
                    ) : (
                        <Card className="animate-in section">
                            <CardContent style={{ paddingTop: "var(--space-4)" }}>
                                <div className="flex items-center justify-between" style={{ marginBottom: "var(--space-3)" }}>
                                    <span className="flex items-center gap-2" style={{ fontWeight: 600 }}>
                                        <WatchIcon style={{ width: 16, height: 16 }} />
                                        {device?.name ?? "No watch paired"}
                                    </span>
                                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                                        {held === null ? "" : `${held} file${held === 1 ? "" : "s"} held`}
                                    </span>
                                </div>

                                <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
                                    First sync on a new phone: the watch shows a six-digit code. Type it into
                                    Android&apos;s pairing prompt (check the notification shade). The watch
                                    cannot take input.
                                </p>

                                {!canReconnectSilently() && (
                                    <p style={{ fontSize: 12, color: "var(--warning)", marginBottom: "var(--space-3)" }}>
                                        No getDevices() here, so every poll would need a tap. Enable
                                        chrome://flags/#enable-web-bluetooth-new-permissions-backend.
                                    </p>
                                )}

                                <div className="flex flex-wrap gap-2">
                                    <Button variant={device ? "outline" : "default"} onClick={pair} disabled={polling}>
                                        <Bluetooth style={{ width: 16, height: 16 }} />
                                        {device ? "Pair again" : "Pair watch"}
                                    </Button>
                                    <Button variant="outline" onClick={syncNow} disabled={!device || busy || polling}>
                                        {busy ? "Syncing…" : "Sync now"}
                                    </Button>
                                    {polling ? (
                                        <Button onClick={stop}>Stop polling</Button>
                                    ) : (
                                        <Button onClick={start} disabled={!device || busy}>
                                            Start polling
                                        </Button>
                                    )}
                                </div>

                                <div className="flex items-center gap-2" style={{ marginTop: "var(--space-3)", fontSize: 12 }}>
                                    <span style={{ color: "var(--text-muted)" }}>Every</span>
                                    {INTERVALS.map((m) => (
                                        <Button
                                            key={m}
                                            size="sm"
                                            variant={m === intervalMin ? "default" : "outline"}
                                            disabled={polling}
                                            onClick={() => chooseInterval(m)}
                                        >
                                            {m} min
                                        </Button>
                                    ))}
                                </div>

                                {polling && (
                                    <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: "var(--space-3)" }}>
                                        Keep this page open and in front, with the phone on a charger. Polling stops if
                                        the page is closed.
                                    </p>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {log.length > 0 && (
                        <Card className="animate-in section">
                            <CardContent style={{ paddingTop: "var(--space-4)" }}>
                                <ul style={{ fontSize: 12, lineHeight: 1.6 }}>
                                    {log.map((l, i) => (
                                        <li key={i} style={{ color: l.color }}>
                                            <span style={{ color: "var(--text-muted)", marginRight: 8 }}>
                                                {l.at.toLocaleTimeString()}
                                            </span>
                                            {l.text}
                                        </li>
                                    ))}
                                </ul>
                            </CardContent>
                        </Card>
                    )}
                </div>
            </div>
        </>
    );
}
