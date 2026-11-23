import { describe, expect, it } from "vitest";
import { FakeWatch } from "./fakeWatch";
import {
    Command,
    FtsClient,
    FtsDisconnectedError,
    FtsError,
    Status,
    crc32,
    listDirRequest,
    mtimeToDate,
    parseResponse,
    readPacingRequest,
    readRequest,
} from "./fts";

function bytes(n: number, seed = 7): Uint8Array {
    const out = new Uint8Array(n);
    let x = seed;
    for (let i = 0; i < n; i++) {
        x = (x * 1103515245 + 12345) >>> 0;
        out[i] = x >>> 24;
    }
    return out;
}

const fast = { idleMs: 30 };

describe("encoders", () => {
    it("lays out LISTDIR as the firmware's own test vector", () => {
        // FileTransferService.cpp: "path: /  ->  50 00 01 00 2F"
        expect([...listDirRequest("/")]).toEqual([0x50, 0x00, 0x01, 0x00, 0x2f]);
    });

    it("lays out READ as the firmware's own test vector", () => {
        // "15 bytes of /Update/test.ota"
        expect([...readRequest("/Update/test.ota", 0, 15)]).toEqual([
            0x10, 0x00, 0x10, 0x00, 0, 0, 0, 0, 0x0f, 0, 0, 0,
            ...new TextEncoder().encode("/Update/test.ota"),
        ]);
    });

    it("puts the contiguous offset and window in READ_PACING", () => {
        const p = new DataView(readPacingRequest(4096, 4096).buffer);
        expect(p.getUint8(0)).toBe(Command.READ_PACING);
        expect(p.getUint8(1)).toBe(Status.OK);
        expect(p.getUint32(4, true)).toBe(4096);
        expect(p.getUint32(8, true)).toBe(4096);
    });

    it("rejects relative paths before they reach the watch", () => {
        expect(() => listDirRequest("DailyHealth")).toThrow(FtsError);
    });
});

describe("parseResponse", () => {
    it("reads a two-byte error as the request opcode plus a status", () => {
        const r = parseResponse(new DataView(Uint8Array.from([0x10, 0x03]).buffer));
        expect(r).toEqual({ kind: "error", command: Command.READ, status: Status.NO_FILE });
    });

    it("never trusts chunkLength beyond what the notification carried", () => {
        const out = new Uint8Array(16 + 4);
        const v = new DataView(out.buffer);
        v.setUint8(0, Command.READ_DATA);
        v.setUint8(1, Status.OK);
        v.setUint32(8, 100, true);
        v.setUint32(12, 50, true); // claims 50, carries 4
        const r = parseResponse(v);
        expect(r?.kind === "data" && r.data.length).toBe(4);
    });
});

describe("crc32", () => {
    it("matches the standard check value", () => {
        expect(crc32(new TextEncoder().encode("123456789"))).toBe(0xcbf43926);
    });
});

describe("mtimeToDate", () => {
    it("reads the firmware's microseconds and the doc's nanoseconds alike", () => {
        const s = 1_763_800_000;
        expect(mtimeToDate(String(BigInt(s) * 1_000_000n))?.getTime()).toBe(s * 1000);
        expect(mtimeToDate(String(BigInt(s) * 1_000_000_000n))?.getTime()).toBe(s * 1000);
        expect(mtimeToDate("0")).toBeNull();
    });
});

describe("FtsClient.listDir", () => {
    it("collects entries until the terminator", async () => {
        const w = new FakeWatch()
            .addText("/DailyHealth/202611/dh_20261121.json", "{}", 1_763_800_000)
            .add("/DailyHealth/202611/dh.tmp", { data: bytes(10) });
        const c = new FtsClient(w.transport());
        const entries = await c.listDir("/DailyHealth/202611", fast);
        expect(entries.map((e) => e.name).sort()).toEqual(["dh.tmp", "dh_20261121.json"]);
        const json = entries.find((e) => e.name.endsWith(".json"))!;
        expect(json).toMatchObject({ isDir: false, size: 2, mtime: "1763800000000000" });
    });

    it("reports a missing directory as NO_FILE", async () => {
        const c = new FtsClient(new FakeWatch().transport());
        await expect(c.listDir("/Nope", fast)).rejects.toMatchObject({ status: Status.NO_FILE });
    });
});

describe("FtsClient.readFile", () => {
    it("reassembles a multi-window file", async () => {
        const data = bytes(10_000);
        const w = new FakeWatch().add("/f.bin", { data });
        const got = await new FtsClient(w.transport()).readFile("/f.bin", fast);
        expect(got).toEqual(data);
        // One READ, then one READ_PACING per further 4096-byte window.
        expect(w.requests.map((r) => r[0])).toEqual([0x10, 0x12, 0x12]);
    });

    it("re-requests a chunk lost in the middle of a burst", async () => {
        const data = bytes(9_000);
        const w = new FakeWatch().add("/f.bin", { data });
        w.drop = (_, i) => i === 3; // a mid-burst chunk of the first window
        const got = await new FtsClient(w.transport()).readFile("/f.bin", fast);
        expect(got).toEqual(data);
        // The second window starts at the hole, not at 4096.
        const firstPacing = new DataView(w.requests[1].buffer);
        expect(firstPacing.getUint32(4, true)).toBe(3 * 201);
    });

    it("recovers when the last chunk of a burst is lost (silence, then re-pace)", async () => {
        const data = bytes(4096 + 50);
        const w = new FakeWatch().add("/f.bin", { data });
        const lastOfFirstWindow = Math.ceil(4096 / 201) - 1;
        w.drop = (_, i) => i === lastOfFirstWindow;
        const got = await new FtsClient(w.transport()).readFile("/f.bin", fast);
        expect(got).toEqual(data);
    });

    it("survives heavy random loss", async () => {
        const data = bytes(20_000, 3);
        const w = new FakeWatch().add("/f.bin", { data });
        let x = 42;
        w.drop = () => ((x = (x * 1103515245 + 12345) >>> 0) >>> 24) < 40; // ~15%
        const got = await new FtsClient(w.transport()).readFile("/f.bin", { ...fast, maxStalls: 20 });
        expect(got).toEqual(data);
    });

    it("reads an empty file", async () => {
        const w = new FakeWatch().add("/empty", { data: new Uint8Array(0) });
        expect(await new FtsClient(w.transport()).readFile("/empty", fast)).toEqual(new Uint8Array(0));
    });

    it("rejects a file that changes size mid-read", async () => {
        const w = new FakeWatch().add("/grow", { data: bytes(5000) });
        let bursts = 0;
        w.beforeBurst = () => {
            if (++bursts === 2) w.files.set("/grow", { data: bytes(6000) });
        };
        await expect(new FtsClient(w.transport()).readFile("/grow", fast)).rejects.toThrow(/changed size/);
    });

    it("gives up after repeated silence", async () => {
        const w = new FakeWatch().add("/f", { data: bytes(100) });
        w.drop = () => true;
        await expect(
            new FtsClient(w.transport()).readFile("/f", { idleMs: 5, maxStalls: 2 }),
        ).rejects.toThrow(/no progress/);
    });

    it("fails at once when the link drops", async () => {
        const w = new FakeWatch().add("/f", { data: bytes(100) });
        w.drop = () => true;
        const c = new FtsClient(w.transport());
        const p = c.readFile("/f", { idleMs: 10_000 });
        setTimeout(() => w.disconnect(), 5);
        await expect(p).rejects.toBeInstanceOf(FtsDisconnectedError);
    });
});

describe("FtsClient.digest", () => {
    it("returns the watch's CRC and size", async () => {
        const data = bytes(777);
        const w = new FakeWatch().add("/f", { data });
        expect(await new FtsClient(w.transport()).digest("/f", fast)).toEqual({
            fileSize: 777,
            crc32: crc32(data),
        });
    });
});

describe("read-only guarantee", () => {
    it("only ever writes READ, READ_PACING, LISTDIR and DIGEST", async () => {
        const w = new FakeWatch().add("/a/b", { data: bytes(5000) });
        const c = new FtsClient(w.transport());
        await c.listDir("/a", fast);
        await c.readFile("/a/b", fast);
        await c.digest("/a/b", fast);
        const allowed = new Set([0x10, 0x12, 0x50, 0x70]);
        expect(w.requests.every((r) => allowed.has(r[0]))).toBe(true);
    });

    it("refuses to put a write opcode on the wire", async () => {
        const w = new FakeWatch();
        const c = new FtsClient(w.transport());
        // Reach the private sender the way a future bug would.
        const send = (c as unknown as { send(b: Uint8Array): Promise<void> }).send.bind(c);
        for (const op of [0x20, 0x22, 0x30, 0x40, 0x60]) {
            await expect(send(Uint8Array.from([op, 0, 0, 0]))).rejects.toThrow(/read-only/);
        }
        expect(w.requests).toHaveLength(0);
    });
});
