import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { FakeWatch } from "./fakeWatch";
import { FtsClient, crc32 } from "./fts";
import { FtsAppInstaller } from "./ftsInstall";
import type { ConnectOptions, WatchSession } from "./unaSync";
import { installWatchApp, restartWatch } from "./watchAppInstall";
import type { WatchAppInfo } from "../types/watchApp";

const bytes = new Uint8Array(4000).map((_, i) => (i * 7) % 256);

const info: WatchAppInfo = {
    available: true,
    name: "Sleep Log",
    folder: "SleepLog",
    file_name: "SleepLog.uapp",
    app_id: "64313DF28C1B15C8",
    size_bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    crc32: crc32(bytes).toString(16).padStart(8, "0"),
    sdk_commit: null,
    toolchain: null,
    built_at: null,
};

function connector(watch: FakeWatch, version = 5) {
    const opened: ConnectOptions[] = [];
    let open = 0;
    let rebooted = false;
    const connect = async (options: ConnectOptions): Promise<WatchSession> => {
        opened.push(options);
        open++;
        const t = watch.transport();
        return {
            client: options.installFolder ? new FtsAppInstaller(t, options.installFolder) : new FtsClient(t),
            version,
            maxWritePayload: 200,
            reboot: async () => void (rebooted = true),
            disconnect: () => void open--,
        };
    };
    return { connect, opened, isOpen: () => open > 0, rebooted: () => rebooted };
}

describe("installWatchApp", () => {
    it("downloads, checks, installs into the app's folder, and lets go of the watch", async () => {
        const watch = new FakeWatch().add("/Apps/Other/Other.uapp", { data: new Uint8Array(3) });
        const c = connector(watch);
        const r = await installWatchApp(info, { download: async () => bytes, connect: c.connect });
        expect(r.status).toBe("installed");
        expect(c.opened).toEqual([{ installFolder: "SleepLog" }]);
        expect(watch.files.get("/Apps/SleepLog/SleepLog.uapp")?.data).toEqual(bytes);
        expect(c.isOpen()).toBe(false);
    });

    it("never connects with a download that fails its checksum", async () => {
        const c = connector(new FakeWatch());
        const bad = bytes.slice(0, 3999);
        await expect(installWatchApp(info, { download: async () => bad, connect: c.connect })).rejects.toThrow(
            /checksum/,
        );
        expect(c.opened).toHaveLength(0);
    });

    it("rejects a different file with the same size and CRC, by its SHA-256", async () => {
        const c = connector(new FakeWatch());
        // Size and CRC agree; only the SHA-256 on record differs.
        const other = { ...info, sha256: "0".repeat(64) };
        await expect(installWatchApp(other, { download: async () => bytes, connect: c.connect })).rejects.toThrow(
            /checksum/,
        );
        expect(c.opened).toHaveLength(0);
    });

    it("refuses a watch too old to verify, and still disconnects", async () => {
        const c = connector(new FakeWatch(), 4);
        await expect(installWatchApp(info, { download: async () => bytes, connect: c.connect })).rejects.toThrow(
            /FTS version 4/,
        );
        expect(c.isOpen()).toBe(false);
    });

    it("says so when Helf has nothing to install", async () => {
        const c = connector(new FakeWatch());
        await expect(
            installWatchApp({ ...info, available: false }, { download: async () => bytes, connect: c.connect }),
        ).rejects.toThrow(/no watch app/);
    });
});

describe("restartWatch", () => {
    it("sends the restart on an install session and disconnects", async () => {
        const c = connector(new FakeWatch());
        await restartWatch(info, c.connect);
        expect(c.rebooted()).toBe(true);
        expect(c.isOpen()).toBe(false);
    });
});
