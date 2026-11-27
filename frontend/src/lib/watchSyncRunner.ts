/**
 * The watch sync, owned by the app rather than a page (plan 0025 phase 3).
 *
 * The poll loop used to live in the Watch page: it started only when that
 * page was opened and was aborted when it was left, so "polling every 30
 * minutes" quietly meant "while the Watch page is on screen". Here it is one
 * object for the life of the app. In the native app it starts at launch when
 * this phone has sync switched on, whatever page Helf opens on, and runs under
 * an Android foreground service (`nativeBackground.ts`) so it keeps going with
 * the screen off. The Watch page shows and steers it.
 *
 * A small store (`subscribe` / `getState`) for `useSyncExternalStore`.
 */

import type { NativeBackground } from "./nativeBackground";
import {
    type PollOutcome,
    type SyncProgress,
    type WatchApi,
    type WatchSession,
    pollLoop,
    pollOnce,
} from "./unaSync";

export interface LogLine {
    at: Date;
    text: string;
    color: string;
}

export interface RunnerState {
    polling: boolean;
    intervalMin: number;
    /** A Sync now in flight. */
    busy: boolean;
    /** The sync in flight, for the progress bar; null between syncs. */
    progress: SyncProgress | null;
    /** Newest first, capped. */
    log: LogLine[];
    lastOutcome: PollOutcome | null;
}

export const INTERVALS = [5, 15, 30, 60];
const INTERVAL_KEY = "helf.watch.intervalMinutes";
const LOG_LINES = 40;

export function loadInterval(): number {
    try {
        const v = Number(localStorage.getItem(INTERVAL_KEY));
        return INTERVALS.includes(v) ? v : 15;
    } catch {
        return 15;
    }
}

function saveInterval(m: number): void {
    try {
        localStorage.setItem(INTERVAL_KEY, String(m));
    } catch {
        // Private mode: the default comes back next time.
    }
}

export function describe(o: PollOutcome): string {
    switch (o.kind) {
        case "synced": {
            const { fetched, listed, skipped } = o.report;
            const parts = [
                fetched.length ? `${fetched.length} file${fetched.length === 1 ? "" : "s"} uploaded` : "nothing new",
                `${listed} on the watch`,
            ];
            if (skipped.length) parts.push(`${skipped.length} skipped`);
            return parts.join(", ");
        }
        default:
            return o.message;
    }
}

export const OUTCOME_COLORS: Record<PollOutcome["kind"], string> = {
    synced: "var(--success)",
    // The expected state of a watch on someone's wrist away from the phone,
    // so plain text, not an error colour.
    unreachable: "var(--text-secondary)",
    unpaired: "var(--warning)",
    unsupported: "var(--error)",
    error: "var(--error)",
};

function clock(d: Date): string {
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export interface RunnerDeps {
    connect: () => Promise<WatchSession>;
    api: WatchApi;
    /** The Android foreground service; null in a browser. */
    background: NativeBackground | null;
    now?: () => Date;
}

export class WatchSyncRunner {
    private readonly deps: RunnerDeps;
    private state: RunnerState;
    private readonly listeners = new Set<() => void>();
    private abort: AbortController | null = null;
    private lastProgressAt = 0;

    constructor(deps: RunnerDeps, intervalMin = loadInterval()) {
        this.deps = deps;
        this.state = { polling: false, intervalMin, busy: false, progress: null, log: [], lastOutcome: null };
        void deps.background?.onStop(() => this.stop("Stopped from the notification."));
    }

    // ------------------------------------------------------------- store

    subscribe = (listener: () => void): (() => void) => {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    };

    getState = (): RunnerState => this.state;

    private set(patch: Partial<RunnerState>): void {
        this.state = { ...this.state, ...patch };
        for (const l of this.listeners) l();
    }

    private now(): Date {
        return this.deps.now?.() ?? new Date();
    }

    log = (text: string, color = "var(--text-muted)"): void => {
        this.set({ log: [{ at: this.now(), text, color }, ...this.state.log].slice(0, LOG_LINES) });
    };

    // ------------------------------------------------------------ events

    /** Byte updates arrive per packet; a few a second is plenty. Phase or file changes show at once. */
    private onProgress = (p: SyncProgress): void => {
        const prev = this.state.progress;
        const at = this.now().getTime();
        const changed = !prev || prev.phase !== p.phase || prev.done !== p.done || prev.total !== p.total;
        if (!changed && at - this.lastProgressAt < 150) return;
        this.lastProgressAt = at;
        this.set({ progress: p });
    };

    private onOutcome = (o: PollOutcome): void => {
        this.set({ progress: null, lastOutcome: o });
        this.log(describe(o), OUTCOME_COLORS[o.kind]);
        if (o.kind === "synced") {
            for (const s of o.report.skipped) this.log(`skipped ${s.path}: ${s.reason}`, "var(--warning)");
        }
        void this.deps.background?.update(`Last sync ${clock(this.now())}: ${describe(o)}`).catch(() => {});
    };

    private syncDeps() {
        return {
            connect: this.deps.connect,
            api: this.deps.api,
            log: (m: string) => this.log(m),
            onProgress: this.onProgress,
            now: () => this.now(),
        };
    }

    // ----------------------------------------------------------- control

    setInterval(min: number): void {
        if (this.state.polling || !INTERVALS.includes(min)) return;
        saveInterval(min);
        this.set({ intervalMin: min });
    }

    start(): void {
        if (this.state.polling) return;
        const controller = new AbortController();
        this.abort = controller;
        const minutes = this.state.intervalMin;
        this.set({ polling: true });
        this.log(`Polling every ${minutes} min.`);
        void this.deps.background
            ?.start(`Every ${minutes} min`)
            .catch((e) => this.log(`Could not start background sync: ${(e as Error).message}`, "var(--warning)"));
        void pollLoop(
            { ...this.syncDeps(), onOutcome: this.onOutcome },
            { intervalMs: minutes * 60_000, signal: controller.signal },
        ).finally(() => {
            // Only the loop this start() made: a stop-then-start must not be
            // undone by the old loop finishing late.
            if (this.abort === controller || this.abort === null) {
                this.set({ polling: false, progress: null });
            }
        });
    }

    stop(reason = "Stopped polling."): void {
        if (!this.state.polling) return;
        this.abort?.abort();
        this.abort = null;
        this.set({ polling: false, progress: null });
        this.log(reason);
        void this.deps.background?.stop().catch(() => {});
    }

    async syncNow(): Promise<PollOutcome | null> {
        if (this.state.busy || this.state.polling) return null;
        this.set({ busy: true });
        try {
            const outcome = await pollOnce(this.syncDeps());
            this.onOutcome(outcome);
            return outcome;
        } finally {
            this.set({ busy: false, progress: null });
        }
    }
}
