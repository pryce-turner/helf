import { describe, expect, it } from "vitest";
import { FakeWatch } from "./fakeWatch";
import { FtsClient, crc32 } from "./fts";
import {
    type ManifestEntry,
    type PollOutcome,
    type WatchApi,
    type WatchFile,
    WatchNotPairedError,
    WatchUnreachableError,
    discover,
    needsFetch,
    pollLoop,
    pollOnce,
    syncOnce,
} from "./unaSync";

function seededWatch(): FakeWatch {
    return new FakeWatch()
        .addText("/settings.json", "{}")
        .addText("/DailyHealth/202611/dh_20261120.json", '{"dailySteps":9000}', 1_763_700_000)
        .addText("/DailyHealth/202611/dh_20261121.json", '{"dailySteps":7000}', 1_763_790_000)
        .add("/DailyHealth/dh.tmp", { data: new Uint8Array([1, 2, 3]) })
        .addText("/DailyHealth/200005/dh_20000501.json", "{}", 957_000_000)
        .addText("/Apps/Running/Activity/summary.json", "{}")
        .addText("/Apps/Running/Activity/202611/activity_1.fit", "FIT-done")
        .addText("/Apps/Running/Activity/202611/activity_2.fit", "FIT-open")
        .addText("/Apps/Running/Activity/.recording", "Activity/202611/activity_2.fit\n123\n")
        .addText("/Apps/Running/Settings/x.json", "{}")
        .add("/Apps/Alarm", { dir: true })
        .addText("/Workouts/Schedule/2026-11-25.fit", "plan")
        .add("/Apps/SleepLog/Sleep/20261123/231500.bin", { data: new Uint8Array([0x55, 0x53, 0x4c, 0x31]) })
        .add("/Apps/SleepLog/Sleep/20261123/232500-1.bin", { data: new Uint8Array([1]) })
        .add("/Apps/SleepLog/Sleep/20261123/233500.part", { data: new Uint8Array([2]) });
}

class MemoryApi implements WatchApi {
    held = new Map<string, ManifestEntry>();
    uploads: string[] = [];
    failUploads = false;
    async manifest() {
        return [...this.held.values()];
    }
    async upload(file: WatchFile, bytes: Uint8Array, crc: number) {
        if (this.failUploads) throw new Error("Network Error");
        expect(crc32(bytes)).toBe(crc);
        this.held.set(file.path, { ...file, crc32: crc });
        this.uploads.push(file.path);
        return { status: "stored" };
    }
}

describe("needsFetch", () => {
    const held = new Map([["/a", { path: "/a", size: 3, mtime: "10", crc32: 1 }]]);
    it("fetches unknown, resized or re-stamped files only", () => {
        expect(needsFetch({ path: "/b", size: 3, mtime: "10" }, held)).toBe(true);
        expect(needsFetch({ path: "/a", size: 4, mtime: "10" }, held)).toBe(true);
        expect(needsFetch({ path: "/a", size: 3, mtime: "11" }, held)).toBe(true);
        expect(needsFetch({ path: "/a", size: 3, mtime: "10" }, held)).toBe(false);
    });
});

describe("discover", () => {
    it("finds archived days and finished workouts, and nothing else", async () => {
        const w = seededWatch();
        const client = new FtsClient(w.transport());
        const paths = (await discover(client)).map((f) => f.path).sort();
        expect(paths).toEqual([
            "/Apps/Running/Activity/202611/activity_1.fit",
            "/Apps/Running/Activity/summary.json",
            "/Apps/SleepLog/Sleep/20261123/231500.bin",
            "/Apps/SleepLog/Sleep/20261123/232500-1.bin",
            "/DailyHealth/200005/dh_20000501.json",
            "/DailyHealth/202611/dh_20261120.json",
            "/DailyHealth/202611/dh_20261121.json",
        ]);
    });
});

describe("syncOnce", () => {
    it("uploads everything once, then nothing", async () => {
        const w = seededWatch();
        const api = new MemoryApi();
        const first = await syncOnce(new FtsClient(w.transport()), api);
        expect(first.fetched).toHaveLength(7);
        expect(first.skipped).toEqual([]);

        const second = await syncOnce(new FtsClient(w.transport()), api);
        expect(second.fetched).toEqual([]);
        expect(second.unchanged).toBe(7);
    });

    it("fetches a file again when the watch rewrites it", async () => {
        const w = seededWatch();
        const api = new MemoryApi();
        await syncOnce(new FtsClient(w.transport()), api);
        w.addText("/Apps/Running/Activity/summary.json", '{"runs":2}', 1_763_900_000);
        const again = await syncOnce(new FtsClient(w.transport()), api);
        expect(again.fetched).toEqual(["/Apps/Running/Activity/summary.json"]);
    });

    it("stops at the first failed upload, so nothing is half-recorded", async () => {
        const api = new MemoryApi();
        api.failUploads = true;
        await expect(syncOnce(new FtsClient(seededWatch().transport()), api)).rejects.toThrow(
            /Network/,
        );
    });

    it("skips a file whose size changed between the listing and the read", async () => {
        const w = seededWatch();
        const api = new MemoryApi();
        let grown = false;
        w.beforeBurst = (path) => {
            if (path.endsWith("activity_1.fit") && !grown) {
                grown = true;
                w.addText("/Apps/Running/Activity/202611/activity_1.fit", "FIT-done-and-more");
            }
        };
        const report = await syncOnce(new FtsClient(w.transport()), api);
        expect(report.skipped.map((s) => s.path)).toContain(
            "/Apps/Running/Activity/202611/activity_1.fit",
        );
    });
});

describe("pollOnce", () => {
    const api = new MemoryApi();

    it("names the unreachable watch without throwing", async () => {
        const outcome = await pollOnce({
            api,
            connect: async () => {
                throw new WatchUnreachableError("silence");
            },
        });
        expect(outcome.kind).toBe("unreachable");
    });

    it("names a missing pairing", async () => {
        const outcome = await pollOnce({
            api,
            connect: async () => {
                throw new WatchNotPairedError("tap pair");
            },
        });
        expect(outcome.kind).toBe("unpaired");
    });

    it("refuses a watch without DIGEST, and still disconnects", async () => {
        let disconnected = false;
        const outcome = await pollOnce({
            api,
            connect: async () => ({
                client: new FtsClient(new FakeWatch().transport()),
                version: 4,
                disconnect: () => {
                    disconnected = true;
                },
            }),
        });
        expect(outcome.kind).toBe("unsupported");
        expect(disconnected).toBe(true);
    });

    it("reports a link lost mid-sync as unreachable, and disconnects", async () => {
        const w = seededWatch();
        w.drop = () => true;
        let disconnected = false;
        setTimeout(() => w.disconnect(), 10);
        const outcome = await pollOnce({
            api: new MemoryApi(),
            connect: async () => ({
                client: new FtsClient(w.transport()),
                version: 5,
                disconnect: () => {
                    disconnected = true;
                },
            }),
        });
        expect(outcome.kind).toBe("unreachable");
        expect(disconnected).toBe(true);
    });
});

describe("pollLoop", () => {
    it("polls until aborted, never overlapping", async () => {
        const controller = new AbortController();
        const outcomes: PollOutcome[] = [];
        await pollLoop(
            {
                api: new MemoryApi(),
                connect: async () => {
                    throw new WatchUnreachableError("away");
                },
                onOutcome: (o) => {
                    outcomes.push(o);
                    if (outcomes.length === 3) controller.abort();
                },
                wait: async () => {},
            },
            { intervalMs: 1, signal: controller.signal },
        );
        expect(outcomes.map((o) => o.kind)).toEqual(["unreachable", "unreachable", "unreachable"]);
    });
});

