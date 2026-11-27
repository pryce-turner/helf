import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Bluetooth, GlassWater, Moon, Watch as WatchIcon, type LucideIcon } from "lucide-react";
import Navigation from "@/components/Navigation";
import BodySectionTabs from "@/components/BodySectionTabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { watchApi, watchAppApi } from "@/lib/api";
import type { SyncProgress } from "@/lib/unaSync";
import { installWatchApp, restartWatch } from "@/lib/watchAppInstall";
import { getWatchConnector, isSyncEnabled, setSyncEnabled } from "@/lib/watchConnector";
import { getWatchSync, needsAppUpdateForBackground } from "@/lib/watchSync";
import { INTERVALS } from "@/lib/watchSyncRunner";
import type { WatchAppInfo } from "@/types/watchApp";

/**
 * The UNA Watch: pairing, the sync switch, the sync's state, and installing
 * Helf's watch apps (plans 0023, 0025, 0026).
 *
 * The sync itself is the app's (`lib/watchSync.ts`), not this page's: in the
 * native app it starts at launch and keeps running under a foreground service
 * whichever page is open. In a browser it runs while Helf is open and in
 * front (Web Bluetooth has no background mode), with a screen wake lock.
 */

function kb(bytes: number): string {
    return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
}

/** What the bar says: "Looking for new files", or "12 of 58 files · 180 of 900 KB". */
function progressText(p: SyncProgress): string {
    if (p.phase === "listing") return "Looking for new files on the watch";
    if (p.total === 0) return "Nothing new";
    return `${Math.min(p.done + 1, p.total)} of ${p.total} file${p.total === 1 ? "" : "s"} · ${kb(p.bytesDone)} of ${kb(p.bytesTotal)}`;
}

type WakeLockSentinelLike = { release(): Promise<void> };

/** What each app Helf builds is for, by its folder on the watch. */
const WATCH_APP_ABOUT: Record<string, { icon: LucideIcon; text: string }> = {
    SleepLog: {
        icon: Moon,
        text: "Records heart rate and wrist motion while you sleep, for Helf to fetch. Starts by itself at boot, with a status tile on the glances screen.",
    },
    Drinks: {
        icon: GlassWater,
        text: "Log drinks by volume and strength and see an estimated BAC, coloured by level. Open it from the watch's app list; Helf fetches what you log.",
    },
};

export default function Watch() {
    const connector = getWatchConnector();
    const native = connector.kind === "native";
    const supported = connector.isSupported();
    const runner = getWatchSync();
    const { polling, busy, intervalMin, progress, log, lastOutcome } = useSyncExternalStore(
        runner.subscribe,
        runner.getState,
    );
    const append = runner.log;
    const [device, setDevice] = useState<{ name: string } | null>(null);
    const [syncOn, setSyncOn] = useState(isSyncEnabled);
    const [held, setHeld] = useState<number | null>(null);
    const [watchApps, setWatchApps] = useState<WatchAppInfo[]>([]);
    /** The app being installed (or the watch restarted for) and what is happening, or null when idle. */
    const [installing, setInstalling] = useState<{ folder: string; text: string } | null>(null);
    /** An app was installed since the last restart: the watch registers apps only at boot. */
    const [needsRestart, setNeedsRestart] = useState<WatchAppInfo | null>(null);
    const wakeLock = useRef<WakeLockSentinelLike | null>(null);

    const refreshHeld = useCallback(() => {
        watchApi
            .manifest()
            .then((files) => setHeld(files.length))
            .catch(() => setHeld(null));
    }, []);

    useEffect(() => {
        if (!supported) return;
        connector.remembered().then((d) => d && setDevice(d));
        watchAppApi
            .list()
            .then(setWatchApps)
            .catch(() => setWatchApps([]));
    }, [supported, connector]);

    // On open, and after every sync the runner finishes, wherever it ran.
    useEffect(() => {
        if (supported) refreshHeld();
    }, [supported, lastOutcome, refreshHeld]);

    // In a browser, keep the screen on while polling, and take the lock back
    // when the page returns to the front: Android drops it whenever the page
    // is hidden. The native app keeps running with the screen off.
    useEffect(() => {
        if (!polling || native) return;
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
    }, [polling, native, append]);

    const pair = async () => {
        // First thing in the tap: the chooser needs transient activation.
        try {
            const d = await connector.pair();
            setDevice(d);
            append(`Paired with ${d.name ?? "the watch"}.`, "var(--success)");
        } catch (e) {
            append((e as Error).message, "var(--error)");
        }
    };

    const syncNow = () => void runner.syncNow();
    const start = () => runner.start();
    const stop = () => runner.stop();

    const toggleSync = (on: boolean) => {
        setSyncEnabled(on);
        setSyncOn(on);
        if (!on) runner.stop();
        // Native: switching on is the opt-in for background polling, so start it.
        else if (native && device) runner.start();
    };

    // Install and restart queue behind a running poll (watchConnector's
    // `exclusive`), so they need no polling switch of their own.
    const installApp = async (app: WatchAppInfo) => {
        const folder = app.folder ?? "";
        setInstalling({ folder, text: "Downloading" });
        try {
            const result = await installWatchApp(app, {
                download: watchAppApi.download,
                connect: (options) => connector.connect(options),
                onStep: (s) => {
                    setInstalling({ folder, text: s.message });
                    append(s.message);
                },
                onProgress: (n, total) => setInstalling({ folder, text: `Sending ${Math.round((100 * n) / total)}%` }),
            });
            for (const w of result.warnings) append(w, "var(--warning)");
            for (const p of result.removed) append(`Removed ${p}`);
            append(`${app.name} installed. It starts when the watch restarts.`, "var(--success)");
            setNeedsRestart(app);
        } catch (e) {
            append((e as Error).message, "var(--error)");
        } finally {
            setInstalling(null);
        }
    };

    const restart = async () => {
        if (!needsRestart) return;
        const app = needsRestart;
        setInstalling({ folder: app.folder ?? "", text: "Restarting the watch" });
        try {
            await restartWatch(app, (options) => connector.connect(options));
            setNeedsRestart(null);
            append("The watch is restarting; new apps are there when it is back.", "var(--success)");
        } catch (e) {
            append((e as Error).message, "var(--error)");
        } finally {
            setInstalling(null);
        }
    };

    const chooseInterval = (m: number) => runner.setInterval(m);

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

                                <label
                                    className="flex items-center gap-2"
                                    style={{ fontSize: 13, marginBottom: "var(--space-3)" }}
                                >
                                    <input
                                        type="checkbox"
                                        checked={syncOn}
                                        onChange={(e) => toggleSync(e.target.checked)}
                                    />
                                    This {native ? "phone" : "browser"} syncs the watch
                                    <span style={{ color: "var(--text-muted)" }}>
                                        (one device only: the watch takes one connection at a time)
                                    </span>
                                </label>

                                {!connector.canReconnectSilently() && (
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
                                    <Button variant="outline" onClick={syncNow} disabled={!syncOn || !device || busy || polling}>
                                        {busy ? "Syncing…" : "Sync now"}
                                    </Button>
                                    {polling ? (
                                        <Button onClick={stop}>Stop polling</Button>
                                    ) : (
                                        <Button onClick={start} disabled={!syncOn || !device || busy}>
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

                                {progress && (
                                    <div style={{ marginTop: "var(--space-3)" }} aria-live="polite">
                                        <div
                                            className="flex justify-between"
                                            style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}
                                        >
                                            <span>{progressText(progress)}</span>
                                            {progress.phase === "fetching" && progress.bytesTotal > 0 && (
                                                <span>{Math.floor((100 * progress.bytesDone) / progress.bytesTotal)}%</span>
                                            )}
                                        </div>
                                        <div
                                            role="progressbar"
                                            aria-valuemin={0}
                                            aria-valuemax={progress.bytesTotal || 1}
                                            aria-valuenow={progress.bytesDone}
                                            style={{
                                                height: 6,
                                                borderRadius: 3,
                                                background: "var(--border)",
                                                overflow: "hidden",
                                            }}
                                        >
                                            <div
                                                className={progress.phase === "listing" ? "animate-pulse" : undefined}
                                                style={{
                                                    height: "100%",
                                                    borderRadius: 3,
                                                    background: "var(--accent)",
                                                    width:
                                                        progress.phase === "listing"
                                                            ? "30%"
                                                            : `${progress.bytesTotal ? (100 * progress.bytesDone) / progress.bytesTotal : 100}%`,
                                                    transition: "width 150ms linear",
                                                }}
                                            />
                                        </div>
                                        {progress.current && (
                                            <div
                                                style={{
                                                    fontSize: 11,
                                                    color: "var(--text-muted)",
                                                    marginTop: 4,
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {progress.current}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {native && needsAppUpdateForBackground() && (
                                    <p style={{ fontSize: 12, color: "var(--warning)", marginTop: "var(--space-3)" }}>
                                        This version of the Helf app cannot sync in the background, so polling stops when
                                        Helf is not on screen. To update, open{" "}
                                        <span style={{ userSelect: "all", wordBreak: "break-all" }}>
                                            {window.location.origin}/download/helf.apk
                                        </span>{" "}
                                        in Chrome (this app cannot download it itself), install it over this one, then
                                        open Helf and allow notifications.
                                    </p>
                                )}

                                {polling &&
                                    (native && !needsAppUpdateForBackground() ? (
                                        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: "var(--space-3)" }}>
                                            Syncing in the background, with a notification while it does. Leave Helf in
                                            recent apps (swiping it away stops it), and set Settings → Apps → Helf →
                                            Battery to Unrestricted.
                                        </p>
                                    ) : (
                                        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: "var(--space-3)" }}>
                                            Keep this page open and in front, with the phone on a charger. Polling stops
                                            if the page is closed.
                                        </p>
                                    ))}
                            </CardContent>
                        </Card>
                    )}

                    {supported &&
                        watchApps.map((app) => {
                            const about = WATCH_APP_ABOUT[app.folder ?? ""];
                            const Icon = about?.icon ?? WatchIcon;
                            const mine = installing !== null && installing.folder === app.folder;
                            return (
                                <Card key={app.folder} className="animate-in section">
                                    <CardContent style={{ paddingTop: "var(--space-4)" }}>
                                        <div
                                            className="flex items-center justify-between"
                                            style={{ marginBottom: "var(--space-3)" }}
                                        >
                                            <span className="flex items-center gap-2" style={{ fontWeight: 600 }}>
                                                <Icon style={{ width: 16, height: 16 }} />
                                                {app.name} on the watch
                                            </span>
                                            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                                                {app.size_bytes != null && `${Math.round(app.size_bytes / 1024)} KB`}
                                                {app.built_at && ` · built ${new Date(app.built_at).toLocaleDateString()}`}
                                            </span>
                                        </div>

                                        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
                                            {about?.text ?? "A watch app built by Helf."} Installs over Bluetooth into
                                            /Apps/{app.folder}.
                                        </p>

                                        <div className="flex flex-wrap gap-2">
                                            <Button
                                                variant={needsRestart ? "outline" : "default"}
                                                onClick={() => installApp(app)}
                                                disabled={!device || installing !== null}
                                            >
                                                {mine ? installing.text : "Install on watch"}
                                            </Button>
                                            {needsRestart?.folder === app.folder && (
                                                <Button onClick={restart} disabled={installing !== null}>
                                                    Restart watch
                                                </Button>
                                            )}
                                        </div>

                                        {!device && (
                                            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: "var(--space-3)" }}>
                                                Pair the watch first.
                                            </p>
                                        )}
                                    </CardContent>
                                </Card>
                            );
                        })}

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
