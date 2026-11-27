import { describe, expect, it } from "vitest";
import type { BleDevice } from "@capacitor-community/bluetooth-le";

import { FakeWatch } from "./fakeWatch";
import { FTS_RAW_CHAR, FTS_SERVICE, FTS_VERSION_CHAR } from "./fts";
import { FtsAppInstaller, installApp } from "./ftsInstall";
import { CMD_CHAR, CMD_SERVICE } from "./unaCommand";
import { type BleApi, type KeyValue, NativeWatch } from "./nativeBle";
import { WatchNotPairedError, WatchUnreachableError, syncOnce } from "./unaSync";

/**
 * A stand-in for the Capacitor plugin, wired to FakeWatch: writes to Raw
 * Transfer go to the simulated watch, its notifications come back through
 * startNotifications, and the version characteristic reads 5.
 */
function fakeBle(watch: FakeWatch, opts: { bonded?: BleDevice[]; reachable?: boolean; versionFailures?: number } = {}) {
    const transport = watch.transport();
    const calls: string[] = [];
    let failures = opts.versionFailures ?? 0;
    let onDisconnect: ((id: string) => void) | undefined;
    let onCommand: ((v: DataView) => void) | undefined;
    const ble: BleApi = {
        initialize: async () => void calls.push("initialize"),
        getBondedDevices: async () => opts.bonded ?? [],
        requestDevice: async () => {
            calls.push("requestDevice");
            return { deviceId: "AA:BB", name: "UNA Watch 418271" };
        },
        createBond: async (id) => void calls.push(`createBond ${id}`),
        connect: async (id, cb) => {
            calls.push(`connect ${id}`);
            if (opts.reachable === false) throw new Error("timeout");
            onDisconnect = cb;
        },
        disconnect: async (id) => void calls.push(`disconnect ${id}`),
        read: async (_id, svc, chr) => {
            expect([svc, chr]).toEqual([FTS_SERVICE, FTS_VERSION_CHAR]);
            if (failures-- > 0) throw new Error("insufficient authentication");
            return new DataView(Uint32Array.of(5).buffer);
        },
        writeWithoutResponse: async (_id, svc, chr, value) => {
            if (svc === CMD_SERVICE) {
                // RESET: answer OK, then the watch goes away.
                const req = [...new Uint8Array(value.buffer, value.byteOffset, value.byteLength)];
                calls.push(`command ${req.map((b) => b.toString(16).padStart(2, "0")).join(" ")}`);
                setTimeout(() => {
                    onCommand?.(new DataView(Uint8Array.from([0x01, 0x01]).buffer));
                    onDisconnect?.("AA:BB");
                }, 0);
                return;
            }
            expect([svc, chr]).toEqual([FTS_SERVICE, FTS_RAW_CHAR]);
            const bytes = new Uint8Array(value.byteLength);
            bytes.set(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
            await transport.write(bytes);
        },
        startNotifications: async (_id, svc, chr, cb) => {
            if (svc === CMD_SERVICE) {
                expect(chr).toBe(CMD_CHAR);
                onCommand = cb;
                return;
            }
            transport.subscribe(cb);
        },
        stopNotifications: async () => {},
        getMtu: async () => 247,
    };
    return { ble, calls, drop: () => onDisconnect?.("AA:BB") };
}

function memory(): KeyValue {
    const m = new Map<string, string>();
    return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v) };
}

describe("NativeWatch.pair", () => {
    it("takes a watch already bonded on Android without scanning", async () => {
        const { ble, calls } = fakeBle(new FakeWatch(), {
            bonded: [{ deviceId: "11:22", name: "Earbuds" }, { deviceId: "AA:BB", name: "UNA Watch 418271" }],
        });
        const w = new NativeWatch(ble, "android", memory());
        expect(await w.pair()).toEqual({ name: "UNA Watch 418271" });
        expect(calls).not.toContain("requestDevice");
        expect(w.remembered()).toEqual({ name: "UNA Watch 418271" });
    });

    it("scans and bonds on Android when nothing is bonded", async () => {
        const { ble, calls } = fakeBle(new FakeWatch());
        await new NativeWatch(ble, "android", memory()).pair();
        expect(calls).toContain("requestDevice");
        expect(calls).toContain("createBond AA:BB");
    });

    it("lets iOS bond by itself", async () => {
        const { ble, calls } = fakeBle(new FakeWatch());
        await new NativeWatch(ble, "ios", memory()).pair();
        expect(calls.some((c) => c.startsWith("createBond"))).toBe(false);
    });
});

describe("NativeWatch.connect", () => {
    it("refuses before pairing", async () => {
        const { ble } = fakeBle(new FakeWatch());
        await expect(new NativeWatch(ble, "android", memory()).connect()).rejects.toBeInstanceOf(WatchNotPairedError);
    });

    it("names an unreachable watch", async () => {
        const store = memory();
        const { ble } = fakeBle(new FakeWatch(), { reachable: false });
        const w = new NativeWatch(ble, "android", store);
        await w.pair();
        await expect(w.connect()).rejects.toBeInstanceOf(WatchUnreachableError);
    });

    it("runs a whole sync over the plugin, then disconnects", async () => {
        const watch = new FakeWatch().addText("/DailyHealth/202611/dh_20261121.json", '{"dailySteps":2096}');
        const { ble, calls } = fakeBle(watch, { bonded: [{ deviceId: "AA:BB", name: "UNA Watch 418271" }] });
        const w = new NativeWatch(ble, "android", memory());
        await w.pair();
        const session = await w.connect();
        expect(session.version).toBe(5);

        const uploads: string[] = [];
        const report = await syncOnce(session.client, {
            manifest: async () => [],
            upload: async (f) => {
                uploads.push(f.path);
                return { status: "stored" };
            },
        });
        session.disconnect();
        expect(report.fetched).toEqual(["/DailyHealth/202611/dh_20261121.json"]);
        expect(uploads).toEqual(report.fetched);
        await new Promise((r) => setTimeout(r, 0));
        expect(calls).toContain("disconnect AA:BB");
    });

    it("waits out a passkey: the version read is retried while the link holds", async () => {
        const { ble } = fakeBle(new FakeWatch(), {
            bonded: [{ deviceId: "AA:BB", name: "UNA Watch 418271" }],
            versionFailures: 1,
        });
        const w = new NativeWatch(ble, "android", memory());
        await w.pair();
        const session = await w.connect();
        expect(session.version).toBe(5);
        session.disconnect();
    }, 10_000);
});

describe("NativeWatch install sessions (plan 0026)", () => {
    async function paired(watch: FakeWatch) {
        const fake = fakeBle(watch);
        const store = memory();
        store.setItem("helf.watch.deviceId", "AA:BB");
        const w = new NativeWatch(fake.ble, "android", store);
        return { w, ...fake };
    }

    it("hands the sync a read-only client and no reboot", async () => {
        const { w } = await paired(new FakeWatch());
        const s = await w.connect();
        expect(s.client).not.toBeInstanceOf(FtsAppInstaller);
        expect(s.reboot).toBeUndefined();
        s.disconnect();
    });

    it("installs over the scoped client, sized to the MTU, then restarts the watch", async () => {
        const watch = new FakeWatch().add("/Apps/Other/Other.uapp", { data: new Uint8Array(3) });
        const { w, calls } = await paired(watch);
        const s = await w.connect({ installFolder: "SleepLog" });
        expect(s.client).toBeInstanceOf(FtsAppInstaller);
        expect(s.maxWritePayload).toBe(247 - 3 - 12);
        const app = new Uint8Array(1500).map((_, i) => i % 251);
        const r = await installApp(s.client as FtsAppInstaller, { fileName: "SleepLog.uapp", bytes: app }, {
            write: { chunk: s.maxWritePayload, idleMs: 30 },
        });
        expect(r.status).toBe("installed");
        expect(watch.files.get("/Apps/SleepLog/SleepLog.uapp")?.data).toEqual(app);
        await s.reboot!();
        expect(calls).toContain("command 01 00");
        s.disconnect();
    });
});
