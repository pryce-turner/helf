import { describe, expect, it } from "vitest";

import { type ForegroundApi, NativeBackground } from "./nativeBackground";

function fakePlugin(display: "granted" | "prompt" | "denied" = "granted") {
    const calls: string[] = [];
    const starts: Record<string, unknown>[] = [];
    let listener: ((e: { buttonId: number }) => void) | null = null;
    const fs: ForegroundApi = {
        checkPermissions: async () => {
            calls.push("check");
            return { display } as never;
        },
        requestPermissions: async () => {
            calls.push("request");
            return { display: "granted" } as never;
        },
        createNotificationChannel: async (o) => void calls.push(`channel ${o.id} ${o.importance}`),
        startForegroundService: async (o) => {
            calls.push("start");
            starts.push(o as never);
        },
        updateForegroundService: async (o) => {
            calls.push("update");
            starts.push(o as never);
        },
        stopForegroundService: async () => void calls.push("stop"),
        addListener: (async (_name: string, fn: (e: { buttonId: number }) => void) => {
            listener = fn;
            return { remove: async () => void (listener = null) };
        }) as never,
    };
    return { fs, calls, starts, press: (id: number) => listener?.({ buttonId: id }) };
}

describe("NativeBackground", () => {
    it("starts a quiet connectedDevice service once, then updates it", async () => {
        const p = fakePlugin();
        const bg = new NativeBackground(p.fs);
        await bg.start("Every 30 min");
        await bg.update("Last sync 2:10 AM: nothing new");
        expect(p.calls).toEqual(["check", "channel helf-watch-sync 2", "start", "check", "update"]);
        expect(p.starts[0]).toMatchObject({
            serviceType: 16,
            smallIcon: "ic_stat_watch_sync",
            notificationChannelId: "helf-watch-sync",
            silent: true,
        });
        expect(p.starts[1]).toMatchObject({ body: "Last sync 2:10 AM: nothing new" });
        expect(bg.isRunning).toBe(true);
    });

    it("asks for notification permission, and runs without it", async () => {
        const p = fakePlugin("prompt");
        const bg = new NativeBackground(p.fs);
        await bg.start("x");
        expect(p.calls.slice(0, 2)).toEqual(["check", "request"]);
        expect(bg.isRunning).toBe(true);
    });

    it("does not update or stop a service it never started", async () => {
        const p = fakePlugin();
        const bg = new NativeBackground(p.fs);
        await bg.update("x");
        await bg.stop();
        expect(p.calls).toEqual([]);
    });

    it("stops, and hears the notification's Stop button", async () => {
        const p = fakePlugin();
        const bg = new NativeBackground(p.fs);
        let stopped = 0;
        const off = await bg.onStop(() => stopped++);
        await bg.start("x");
        p.press(99);
        p.press(1);
        expect(stopped).toBe(1);
        await bg.stop();
        expect(bg.isRunning).toBe(false);
        expect(p.calls.at(-1)).toBe("stop");
        off();
    });
});
