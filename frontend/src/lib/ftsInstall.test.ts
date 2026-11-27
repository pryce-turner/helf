import { describe, expect, it } from "vitest";
import { FakeWatch } from "./fakeWatch";
import { Command, FtsClient, FtsError, crc32 } from "./fts";
import {
    FtsAppInstaller,
    deleteRequest,
    installApp,
    mkdirRequest,
    moveRequest,
    requestPaths,
    writeDataRequest,
    writeRequest,
} from "./ftsInstall";

function bytes(n: number, seed = 11): Uint8Array {
    const out = new Uint8Array(n);
    let x = seed;
    for (let i = 0; i < n; i++) {
        x = (x * 1103515245 + 12345) >>> 0;
        out[i] = x >>> 24;
    }
    return out;
}

const hex = (s: string) => s.split(/\s+/).filter(Boolean).map((h) => parseInt(h, 16));
const fast = { idleMs: 30 };
const APP = "/Apps/SleepLog";

function watchWithApps(): FakeWatch {
    return new FakeWatch().add("/Apps/Other/Other.uapp", { data: bytes(10) });
}

describe("encoders match FileTransferService.cpp's own test vectors", () => {
    it("WRITE and WRITE_DATA: Example 2, \"Hello\" into /write.txt", () => {
        expect([...writeRequest("/write.txt", 0, 5, 0n)]).toEqual(
            hex("20 00 0A 00 00 00 00 00 00 00 00 00 00 00 00 00 05 00 00 00 2F 77 72 69 74 65 2E 74 78 74"),
        );
        expect([...writeDataRequest(0, new TextEncoder().encode("Hello"))]).toEqual(
            hex("22 01 00 00 00 00 00 00 05 00 00 00 48 65 6C 6C 6F"),
        );
    });

    it("WRITE_DATA at an offset: Example 3", () => {
        expect([...writeDataRequest(8, Uint8Array.from([0x77, 0x88]))]).toEqual(
            hex("22 01 00 00 08 00 00 00 02 00 00 00 77 88"),
        );
    });

    it("DELETE", () => {
        expect([...deleteRequest("/write.txt")]).toEqual(hex("30 00 0A 00 2F 77 72 69 74 65 2E 74 78 74"));
    });

    it("MKDIR, time and all", () => {
        expect([...mkdirRequest("/Dir/dir", 0x0094dc8052c66e18n)]).toEqual(
            hex("40 00 08 00 00 00 00 00 18 6E C6 52 80 DC 94 00 2F 44 69 72 2F 64 69 72"),
        );
    });

    it("MOVE: header, old path, one separator byte, new path", () => {
        const m = moveRequest("/a", "/bc");
        expect([...m]).toEqual([0x60, 0, 2, 0, 3, 0, 0x2f, 0x61, 0, 0x2f, 0x62, 0x63]);
        expect(requestPaths(m)).toEqual(["/a", "/bc"]);
    });
});

describe("write scope", () => {
    it("the sync client still refuses every write opcode", async () => {
        const w = new FakeWatch();
        const c = new FtsClient(w.transport());
        const send = (c as unknown as { send(b: Uint8Array): Promise<void> }).send.bind(c);
        await expect(send(writeRequest(`${APP}/SleepLog.uapp`, 0, 1))).rejects.toThrow(/read-only/);
        expect(w.requests).toHaveLength(0);
    });

    it("refuses anything but this folder's .uapp files, before the radio", async () => {
        const w = new FakeWatch().add(`${APP}/Sleep/20261127/230000.bin`, { data: bytes(10) });
        const c = new FtsAppInstaller(w.transport(), "SleepLog");
        const send = (c as unknown as { send(b: Uint8Array): Promise<void> }).send.bind(c);
        const refused = [
            writeRequest(`${APP}/Sleep/20261127/230000.bin`, 0, 1),
            writeRequest(`${APP}/notes.txt`, 0, 1),
            writeRequest("/Apps/Other/Other.uapp", 0, 1),
            writeRequest(`${APP}/../Other/Other.uapp`, 0, 1),
            writeRequest("/settings.json", 0, 1),
            deleteRequest(`${APP}/Sleep`),
            deleteRequest(`${APP}/Sleep/20261127/230000.bin`),
            deleteRequest(APP),
            mkdirRequest(`${APP}/Sleep`),
            mkdirRequest("/Apps/Other2"),
            moveRequest(`${APP}/SleepLog.uapp`, "/Update/fw.ota"),
            moveRequest(`${APP}/Sleep/20261127/230000.bin`, `${APP}/x.uapp`),
            // WRITE_DATA with no permitted WRITE open.
            writeDataRequest(0, bytes(4)),
        ];
        for (const r of refused) {
            await expect(send(r)).rejects.toThrow(/writes only \/Apps\/SleepLog\/\*\.uapp/);
        }
        expect(w.requests).toHaveLength(0);
        await expect(c.writeFile(`${APP}/Sleep/x.bin`, bytes(4), fast)).rejects.toThrow(FtsError);
        expect(w.files.get(`${APP}/Sleep/20261127/230000.bin`)?.data).toHaveLength(10);
    });

    it("rejects a folder name that could escape /Apps", () => {
        const t = new FakeWatch().transport();
        for (const bad of ["..", "a/b", "", "Sleep Log"]) {
            expect(() => new FtsAppInstaller(t, bad)).toThrow(FtsError);
        }
    });
});

describe("writeFile", () => {
    async function write(w: FakeWatch, data: Uint8Array, opts = {}) {
        w.add(`${APP}/.keep`, { data: new Uint8Array(0) });
        const c = new FtsAppInstaller(w.transport(), "SleepLog");
        const progress: number[] = [];
        await c.writeFile(`${APP}/SleepLog.uapp`, data, {
            ...fast,
            chunk: 200,
            onProgress: (n) => progress.push(n),
            ...opts,
        });
        return progress;
    }

    it("streams a file in a window and lands it whole", async () => {
        const w = new FakeWatch();
        const data = bytes(28_448);
        const progress = await write(w, data);
        expect(w.files.get(`${APP}/SleepLog.uapp`)?.data).toEqual(data);
        expect(progress.at(-1)).toBe(data.length);
        // Never more than a window past the last ACK, so no burst outruns the watch.
        const chunks = w.requests.filter((r) => r[0] === Command.WRITE_DATA);
        expect(Math.max(...chunks.map((r) => r.length - 12))).toBeLessThanOrEqual(200);
    });

    it("writes an empty file with no WRITE_DATA at all", async () => {
        const w = new FakeWatch();
        await write(w, new Uint8Array(0));
        expect(w.files.get(`${APP}/SleepLog.uapp`)?.data).toHaveLength(0);
        expect(w.requests.some((r) => r[0] === Command.WRITE_DATA)).toBe(false);
    });

    it("recovers lost chunks go-back-N, without holes", async () => {
        const w = new FakeWatch();
        w.dropRequest = (b, i) => b[0] === Command.WRITE_DATA && i % 7 === 3;
        const data = bytes(9_000);
        await write(w, data);
        expect(crc32(w.files.get(`${APP}/SleepLog.uapp`)!.data!)).toBe(crc32(data));
    });

    it("survives lost ACKs, including the final one", async () => {
        const w = new FakeWatch();
        let acks = 0;
        w.drop = (b) => b[0] === Command.WRITE_PACING && ++acks % 3 === 0;
        const data = bytes(5_000);
        await write(w, data);
        expect(w.files.get(`${APP}/SleepLog.uapp`)?.data).toEqual(data);
    });

    it("halves the chunk when the link cuts packets short", async () => {
        const w = new FakeWatch();
        // An MTU of 67: the WRITE and its path fit, a 200-byte chunk does not.
        w.maxRequest = 67 - 3;
        const data = bytes(600);
        await write(w, data);
        expect(w.files.get(`${APP}/SleepLog.uapp`)?.data).toEqual(data);
    });

    it("gives up when the watch goes silent", async () => {
        const w = new FakeWatch();
        w.dropRequest = (b) => b[0] === Command.WRITE_DATA;
        await expect(write(w, bytes(1000), { maxStalls: 2 })).rejects.toThrow(/no progress/);
    });
});

describe("installApp", () => {
    const app = { fileName: "SleepLog.uapp", bytes: bytes(3000, 3), appId: "64313DF28C1B15C8" };
    const opts = { write: { ...fast, chunk: 200 } };

    it("creates the folder, installs, and verifies against the watch's own CRC", async () => {
        const w = watchWithApps();
        const c = new FtsAppInstaller(w.transport(), "SleepLog");
        const steps: string[] = [];
        const result = await installApp(c, app, { ...opts, onStep: (s) => steps.push(s.step) });
        expect(result.status).toBe("installed");
        expect(w.files.get(APP)?.dir).toBe(true);
        expect(w.files.get(`${APP}/SleepLog.uapp`)?.data).toEqual(app.bytes);
        expect(w.files.has(`${APP}/SleepLog.uapp.part`)).toBe(false);
        expect(steps).toEqual(["check", "mkdir", "upload", "verify", "swap", "done"]);
        // Other apps untouched.
        expect(w.files.get("/Apps/Other/Other.uapp")?.data).toHaveLength(10);
    });

    it("does nothing when the watch already has this exact file", async () => {
        const w = watchWithApps().add(`${APP}/SleepLog.uapp`, { data: app.bytes });
        const c = new FtsAppInstaller(w.transport(), "SleepLog");
        const result = await installApp(c, app, opts);
        expect(result.status).toBe("unchanged");
        expect(w.requests.some((r) => r[0] === Command.WRITE)).toBe(false);
    });

    it("replaces an older build and removes stray copies, leaving the recordings", async () => {
        const w = watchWithApps()
            .add(`${APP}/SleepLog.uapp`, { data: bytes(2000, 9) })
            .add(`${APP}/SleepLog_0.0.0-dev.uapp`, { data: bytes(2000, 9) })
            .add(`${APP}/Sleep/20261127/230000.bin`, { data: bytes(50) });
        const c = new FtsAppInstaller(w.transport(), "SleepLog");
        const result = await installApp(c, app, opts);
        expect(result.status).toBe("installed");
        expect(result.removed).toEqual([`${APP}/SleepLog_0.0.0-dev.uapp`]);
        expect(w.files.get(`${APP}/SleepLog.uapp`)?.data).toEqual(app.bytes);
        expect(w.files.get(`${APP}/Sleep/20261127/230000.bin`)?.data).toHaveLength(50);
    });

    it("warns about a USB copy in a folder named for the app ID, without touching it", async () => {
        const w = watchWithApps().add("/Apps/64313DF28C1B15C8/SleepLog.uapp", { data: bytes(5) });
        const c = new FtsAppInstaller(w.transport(), "SleepLog");
        const result = await installApp(c, app, opts);
        expect(result.warnings.join(" ")).toMatch(/64313DF28C1B15C8/);
        expect(w.files.get("/Apps/64313DF28C1B15C8/SleepLog.uapp")?.data).toHaveLength(5);
    });

    it("keeps the old app when the upload does not verify", async () => {
        const old = bytes(2000, 9);
        const w = watchWithApps().add(`${APP}/SleepLog.uapp`, { data: old });
        const c = new FtsAppInstaller(w.transport(), "SleepLog");
        // Corrupt what lands, as a flipped bit on eMMC would.
        const digest = c.digest.bind(c);
        c.digest = async (p, o) => {
            const d = await digest(p, o);
            return p.endsWith(".part") ? { ...d, crc32: d.crc32 ^ 1 } : d;
        };
        await expect(installApp(c, app, opts)).rejects.toThrow(/does not match/);
        expect(w.files.get(`${APP}/SleepLog.uapp`)?.data).toEqual(old);
        expect(w.files.has(`${APP}/SleepLog.uapp.part`)).toBe(false);
    });
});
