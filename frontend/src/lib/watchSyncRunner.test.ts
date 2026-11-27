import { describe, expect, it } from "vitest";

import { FakeWatch } from "./fakeWatch";
import { FtsClient, crc32 } from "./fts";
import type { NativeBackground } from "./nativeBackground";
import type { ManifestEntry, WatchApi, WatchFile, WatchSession } from "./unaSync";
import { WatchUnreachableError } from "./unaSync";
import { WatchSyncRunner } from "./watchSyncRunner";

class MemoryApi implements WatchApi {
    held = new Map<string, ManifestEntry>();
    async manifest() {
        return [...this.held.values()];
    }
    async upload(file: WatchFile, bytes: Uint8Array, crc: number) {
        expect(crc32(bytes)).toBe(crc);
        this.held.set(file.path, { ...file, crc32: crc });
        return { status: "stored" };
    }
}

function fakeBackground() {
    const calls: string[] = [];
    let stopListener: (() => void) | null = null;
    const bg = {
        start: async (body: string) => void calls.push(`start ${body}`),
        update: async (body: string) => void calls.push(`update ${body}`),
        stop: async () => void calls.push("stop"),
        onStop: async (fn: () => void) => {
            stopListener = fn;
            return () => {};
        },
    };
    return { bg: bg as unknown as NativeBackground, calls, pressStop: () => stopListener?.() };
}

function setup(opts: { reachable?: boolean } = {}) {
    const watch = new FakeWatch()
        .addText("/DailyHealth/202611/dh_20261126.json", '{"dailySteps":9000}')
        .add("/Apps/SleepLog/Sleep/20261127/025307.bin", { data: new Uint8Array(15_000).map((_, i) => i % 251) });
    const api = new MemoryApi();
    const connect = async (): Promise<WatchSession> => {
        if (opts.reachable === false) throw new WatchUnreachableError("out of range");
        return { client: new FtsClient(watch.transport()), version: 5, disconnect: () => {} };
    };
    const background = fakeBackground();
    const runner = new WatchSyncRunner(
        { connect, api, background: background.bg, now: () => new Date("2026-11-27T10:00:00Z") },
        30,
    );
    return { runner, api, background };
}

function nextOutcome(runner: WatchSyncRunner): Promise<void> {
    const before = runner.getState().lastOutcome;
    return new Promise((resolve) => {
        const off = runner.subscribe(() => {
            if (runner.getState().lastOutcome !== before) {
                off();
                resolve();
            }
        });
    });
}

describe("WatchSyncRunner", () => {
    it("polls under the foreground service and keeps its notification current", async () => {
        const { runner, api, background } = setup();
        const done = nextOutcome(runner);
        runner.start();
        expect(runner.getState().polling).toBe(true);
        await done;
        expect(api.held.size).toBe(2);
        expect(background.calls[0]).toBe("start Every 30 min");
        expect(background.calls.at(-1)).toMatch(/^update Last sync .*: 2 files uploaded, 2 on the watch$/);
        expect(runner.getState().log[0].text).toBe("2 files uploaded, 2 on the watch");
        expect(runner.getState().progress).toBeNull();
        runner.stop();
        expect(runner.getState().polling).toBe(false);
        expect(background.calls.at(-1)).toBe("stop");
    });

    it("reports progress while a sync runs, and clears it after", async () => {
        const { runner } = setup();
        const phases = new Set<string>();
        runner.subscribe(() => {
            const p = runner.getState().progress;
            if (p) phases.add(p.phase);
        });
        await runner.syncNow();
        expect(phases).toEqual(new Set(["listing", "fetching"]));
        expect(runner.getState().progress).toBeNull();
        expect(runner.getState().busy).toBe(false);
    });

    it("stops from the notification's Stop button", async () => {
        const { runner, background } = setup({ reachable: false });
        const done = nextOutcome(runner);
        runner.start();
        await done;
        background.pressStop();
        expect(runner.getState().polling).toBe(false);
        expect(runner.getState().log[0].text).toBe("Stopped from the notification.");
    });

    it("does not Sync now on top of a poll, or start twice", async () => {
        const { runner, background } = setup({ reachable: false });
        runner.start();
        runner.start();
        expect(background.calls.filter((c) => c.startsWith("start"))).toHaveLength(1);
        expect(await runner.syncNow()).toBeNull();
        runner.stop();
    });

    it("keeps a restarted loop when the old one finishes late", async () => {
        const { runner } = setup({ reachable: false });
        runner.start();
        runner.stop();
        runner.start();
        await new Promise((r) => setTimeout(r, 20));
        expect(runner.getState().polling).toBe(true);
        runner.stop();
    });

    it("only changes the interval while stopped", () => {
        const { runner } = setup();
        runner.setInterval(60);
        expect(runner.getState().intervalMin).toBe(60);
        runner.setInterval(7);
        expect(runner.getState().intervalMin).toBe(60);
    });
});
