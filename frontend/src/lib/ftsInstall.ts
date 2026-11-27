/**
 * Installing a watch app over Bluetooth (plan 0026).
 *
 * The official phone app installs apps the same way: it writes the `.uapp`
 * into `/Apps/<folder>/` over the File Transfer Service, which the kernel
 * recognises as an app file (`Backend::isBleAppFile`, "2:/Apps/*\/*.uapp").
 * The app manager scans `/Apps` once, at boot (`App::Manager::scan`), so a new
 * or changed app runs from the next restart. The loader reads a `.uapp` into
 * RAM and closes it, so replacing the file under a running app is safe; the
 * running copy carries on until then.
 *
 * Everything here is pure over an `FtsTransport`, and tested against
 * `FakeWatch`, which mirrors `FileTransferService.cpp`'s write path.
 *
 * **Narrow by construction.** `FtsAppInstaller` extends the read-only
 * `FtsClient`, and its `permits()` admits writes for one app folder only:
 *
 * - WRITE, DELETE and MOVE only on `/Apps/<folder>/<name>.uapp` or
 *   `.uapp.part`, directly in the folder. Never a directory, never a path
 *   below it, so the app's own data (`/Apps/SleepLog/Sleep/…`, the sleep
 *   recordings) is out of reach.
 * - MKDIR only on `/Apps/<folder>` itself.
 * - WRITE_DATA only while one of those WRITEs is open.
 *
 * The sync never creates one of these; it gets a plain `FtsClient`.
 */

import {
    Command,
    type DirEntry,
    FtsClient,
    FtsError,
    type FtsTransport,
    READ_REQUESTS,
    Status,
    crc32,
    statusName,
} from "./fts";

// ---------------------------------------------------------------- encoders

const utf8 = new TextEncoder();
const utf8Decoder = new TextDecoder();

function encodePath(path: string): Uint8Array {
    if (!path.startsWith("/")) {
        throw new FtsError(`FTS paths are absolute: ${JSON.stringify(path)}`);
    }
    const encoded = utf8.encode(path);
    if (encoded.length > 0xffff) throw new FtsError("Path too long");
    return encoded;
}

function nowNs(): bigint {
    return BigInt(Date.now()) * 1_000_000n;
}

/** WRITE `{cmd, 0, pathLength u16, offset u32, currentTime u64, totalSize u32}` + path. */
export function writeRequest(
    path: string,
    offset: number,
    totalSize: number,
    timeNs: bigint = nowNs(),
): Uint8Array<ArrayBuffer> {
    const p = encodePath(path);
    const out = new Uint8Array(20 + p.length);
    const v = new DataView(out.buffer);
    v.setUint8(0, Command.WRITE);
    v.setUint16(2, p.length, true);
    v.setUint32(4, offset, true);
    v.setBigUint64(8, timeNs, true);
    v.setUint32(16, totalSize, true);
    out.set(p, 20);
    return out;
}

/** WRITE_DATA `{cmd, status 0x01, reserved u16, offset u32, dataSize u32}` + data. */
export function writeDataRequest(offset: number, data: Uint8Array): Uint8Array<ArrayBuffer> {
    const out = new Uint8Array(12 + data.length);
    const v = new DataView(out.buffer);
    v.setUint8(0, Command.WRITE_DATA);
    v.setUint8(1, Status.OK);
    v.setUint32(4, offset, true);
    v.setUint32(8, data.length, true);
    out.set(data, 12);
    return out;
}

/** MKDIR `{cmd, 0, pathLength u16, reserved u32, currentTime u64}` + path. */
export function mkdirRequest(path: string, timeNs: bigint = nowNs()): Uint8Array<ArrayBuffer> {
    const p = encodePath(path);
    const out = new Uint8Array(16 + p.length);
    const v = new DataView(out.buffer);
    v.setUint8(0, Command.MKDIR);
    v.setUint16(2, p.length, true);
    v.setBigUint64(8, timeNs, true);
    out.set(p, 16);
    return out;
}

/** DELETE `{cmd, 0, pathLength u16}` + path. */
export function deleteRequest(path: string): Uint8Array<ArrayBuffer> {
    const p = encodePath(path);
    const out = new Uint8Array(4 + p.length);
    const v = new DataView(out.buffer);
    v.setUint8(0, Command.DELETE);
    v.setUint16(2, p.length, true);
    out.set(p, 4);
    return out;
}

/** MOVE `{cmd, 0, oldLength u16, newLength u16}` + old + one separator byte + new. */
export function moveRequest(from: string, to: string): Uint8Array<ArrayBuffer> {
    const a = encodePath(from);
    const b = encodePath(to);
    const out = new Uint8Array(6 + a.length + 1 + b.length);
    const v = new DataView(out.buffer);
    v.setUint8(0, Command.MOVE);
    v.setUint16(2, a.length, true);
    v.setUint16(4, b.length, true);
    out.set(a, 6);
    // The firmware skips the separator without reading it; 0 as Adafruit sends.
    out.set(b, 6 + a.length + 1);
    return out;
}

/** The path(s) a write-family request names, decoded back off the wire. */
export function requestPaths(bytes: Uint8Array): string[] {
    const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const at = (offset: number, len: number) => utf8Decoder.decode(bytes.subarray(offset, offset + len));
    switch (bytes[0]) {
        case Command.WRITE:
            return [at(20, v.getUint16(2, true))];
        case Command.MKDIR:
            return [at(16, v.getUint16(2, true))];
        case Command.DELETE:
            return [at(4, v.getUint16(2, true))];
        case Command.MOVE: {
            const a = v.getUint16(2, true);
            const b = v.getUint16(4, true);
            return [at(6, a), at(6 + a + 1, b)];
        }
        default:
            return [];
    }
}

// ------------------------------------------------------------------ client

const FOLDER = /^[A-Za-z0-9_-]{1,32}$/;
const APP_FILE = /^[A-Za-z0-9_.-]+\.uapp(\.part)?$/;

export interface WriteOptions {
    /** Bytes allowed in flight past the last ACK. The doc's WRITE_WINDOW is 2048. */
    window?: number;
    /** Data bytes per WRITE_DATA. Must fit one ATT packet: MTU − 3 − 12. */
    chunk?: number;
    /** Silence after which the window is resent from the last ACK. */
    idleMs?: number;
    /** Resends in a row with no ACK progress before giving up. */
    maxStalls?: number;
    onProgress?: (written: number, total: number) => void;
}

/** The smallest WRITE_DATA the halving falls back to (MTU 23 − 3 − 12). */
const MIN_CHUNK = 8;

export class FtsAppInstaller extends FtsClient {
    /** `/Apps/<folder>` */
    readonly appDir: string;
    /** True only while a permitted WRITE is open, which is what WRITE_DATA rides on. */
    private writing = false;

    constructor(transport: FtsTransport, folder: string) {
        super(transport);
        if (!FOLDER.test(folder)) throw new FtsError(`Not an app folder name: ${JSON.stringify(folder)}`);
        this.appDir = `/Apps/${folder}`;
    }

    /** A `.uapp` (or its `.part`) directly in this app's folder. */
    isAppFile(path: string): boolean {
        const prefix = `${this.appDir}/`;
        if (!path.startsWith(prefix)) return false;
        const name = path.slice(prefix.length);
        return !name.includes("/") && APP_FILE.test(name) && !name.startsWith(".");
    }

    protected override permits(bytes: Uint8Array): boolean {
        const op = bytes[0];
        if (READ_REQUESTS.has(op)) return true;
        if (op === Command.WRITE_DATA) return this.writing;
        const paths = requestPaths(bytes);
        switch (op) {
            case Command.WRITE:
            case Command.DELETE:
            case Command.MOVE:
                return paths.length > 0 && paths.every((p) => this.isAppFile(p));
            case Command.MKDIR:
                return paths.length === 1 && paths[0] === this.appDir;
            default:
                return false;
        }
    }

    protected override refusal(): string {
        return `this installer writes only ${this.appDir}/*.uapp`;
    }

    private simple(
        command: number,
        reply: number,
        bytes: Uint8Array<ArrayBuffer>,
        what: string,
        idleMs: number,
    ): Promise<void> {
        return this.exchange<void>(idleMs, ({ resolve, reject, send, onResponse }) => {
            onResponse((r) => {
                if (r.kind === "error" && r.command === command) {
                    reject(new FtsError(`${what}: ${statusName(r.status)}`, r.status));
                } else if (r.kind === "done" && r.command === reply) {
                    if (r.status === Status.OK) resolve();
                    else reject(new FtsError(`${what}: ${statusName(r.status)}`, r.status));
                }
            });
            void send(bytes);
        });
    }

    mkdir(path: string, { idleMs = 5000 } = {}): Promise<void> {
        return this.simple(Command.MKDIR, Command.MKDIR_STATUS, mkdirRequest(path), `MKDIR ${path}`, idleMs);
    }

    remove(path: string, { idleMs = 5000 } = {}): Promise<void> {
        return this.simple(Command.DELETE, Command.DELETE_STATUS, deleteRequest(path), `DELETE ${path}`, idleMs);
    }

    move(from: string, to: string, { idleMs = 5000 } = {}): Promise<void> {
        return this.simple(Command.MOVE, Command.MOVE_STATUS, moveRequest(from, to), `MOVE ${from}`, idleMs);
    }

    /**
     * WRITE a whole file, streamed in a window of WRITE_DATA and recovered
     * go-back-N, as the doc's v5 flow control describes.
     *
     * The watch ACKs every chunk with `freeSpace = totalSize − contiguousEnd`,
     * a hole-free high-water mark, and sends 0 only once the file is complete
     * and closed (committed to eMMC). So: keep at most `window` bytes past the
     * last ACK in flight; on `idleMs` of silence, rewind to the last ACK and
     * resend from there. A rewritten chunk lands on the same offset, so
     * duplicates are harmless. A WRITE_DATA answered with a protocol error is
     * most likely a packet cut short by the link's MTU, so the chunk is halved
     * and the window resent.
     */
    async writeFile(path: string, data: Uint8Array, options: WriteOptions = {}): Promise<void> {
        const { window = 2048, idleMs = 2000, maxStalls = 6, onProgress } = options;
        let chunk = Math.max(MIN_CHUNK, options.chunk ?? 128);
        const total = data.length;

        if (!this.isAppFile(path)) {
            throw new FtsError(`Refusing to write ${path}: ${this.refusal()}.`);
        }
        this.writing = true;
        try {
            await this.exchange<void>(idleMs, ({ resolve, reject, send, onResponse, onIdle }) => {
                let opened = false;
                let acked = 0;
                let sent = 0;
                let stalls = 0;
                let lastAcked = 0;
                let pumping = false;
                // WRITE_DATA sent and not yet answered. The watch answers each
                // one, ACK or error, in order, so after a halving the errors
                // still due for the old oversized burst are known in number
                // and skipped rather than each halving again.
                let outstanding = 0;
                let staleErrors = 0;

                const pump = async () => {
                    if (pumping) return;
                    pumping = true;
                    try {
                        while (opened && sent < total && sent - acked < window) {
                            const at = sent;
                            const n = Math.min(chunk, total - at);
                            sent = at + n;
                            outstanding++;
                            await send(writeDataRequest(at, data.subarray(at, at + n)));
                        }
                    } finally {
                        pumping = false;
                    }
                };

                onIdle(() => {
                    if (!opened) {
                        if (++stalls > maxStalls) {
                            reject(new FtsError(`WRITE ${path}: the watch never acknowledged the write.`));
                            return;
                        }
                        void send(writeRequest(path, 0, total));
                        return;
                    }
                    if (acked > lastAcked) {
                        stalls = 0;
                    } else if (++stalls > maxStalls) {
                        reject(new FtsError(`WRITE ${path}: no progress after ${maxStalls} resends at byte ${acked}.`));
                        return;
                    }
                    lastAcked = acked;
                    // Silence: whatever was in flight is lost, replies included.
                    outstanding = 0;
                    staleErrors = 0;
                    sent = acked;
                    void pump();
                });

                onResponse((r) => {
                    if (r.kind === "error" && r.command === Command.WRITE_DATA) {
                        outstanding = Math.max(0, outstanding - 1);
                        if (r.status === Status.PROTOCOL && staleErrors > 0) {
                            staleErrors--;
                            return;
                        }
                        if (r.status === Status.PROTOCOL && chunk > MIN_CHUNK) {
                            chunk = Math.max(MIN_CHUNK, Math.floor(chunk / 2));
                            staleErrors = outstanding;
                            sent = acked;
                            void pump();
                            return;
                        }
                    }
                    if (r.kind === "error" && (r.command === Command.WRITE || r.command === Command.WRITE_DATA)) {
                        reject(new FtsError(`WRITE ${path}: ${statusName(r.status)}`, r.status));
                        return;
                    }
                    if (r.kind !== "write") return;
                    if (r.status !== Status.OK) {
                        reject(new FtsError(`WRITE ${path}: ${statusName(r.status)}`, r.status));
                        return;
                    }
                    if (!opened) {
                        // The ACK to WRITE itself: the file is open (truncated,
                        // offset 0), and freeSpace is the whole file.
                        opened = true;
                        stalls = 0;
                        if (r.freeSpace === 0) {
                            resolve();
                            return;
                        }
                        void pump();
                        return;
                    }
                    outstanding = Math.max(0, outstanding - 1);
                    const nowAcked = total - r.freeSpace;
                    if (nowAcked > acked) {
                        acked = nowAcked;
                        onProgress?.(acked, total);
                    }
                    if (r.freeSpace === 0) {
                        resolve();
                        return;
                    }
                    void pump();
                });

                void send(writeRequest(path, 0, total));
            });
        } finally {
            this.writing = false;
        }
    }
}

// ----------------------------------------------------------------- install

export interface InstallStep {
    step: "check" | "mkdir" | "upload" | "verify" | "swap" | "tidy" | "done";
    message: string;
}

export interface InstallResult {
    /**
     * Always `installed`: there is no "already up to date" shortcut, because
     * the watch cannot tell. A .uapp ends with the CRC-32 of everything before
     * it, so the CRC-32 of any intact .uapp is the residue 0x2144DF1C, and
     * DIGEST (whole-file CRC-32) gives the same answer for every build of
     * every app. Size plus DIGEST would skip a changed build of the same size.
     * Corruption still shows: a damaged file no longer hits the residue.
     */
    status: "installed";
    /** Other `.uapp` files removed from the folder (e.g. a copy put there over USB). */
    removed: string[];
    /** Things worth telling the user that did not stop the install. */
    warnings: string[];
}

function sameDigest(d: { fileSize: number; crc32: number }, size: number, crc: number): boolean {
    return d.fileSize === size && d.crc32 === crc;
}

async function listOrNull(client: FtsClient, path: string): Promise<DirEntry[] | null> {
    try {
        return await client.listDir(path);
    } catch (e) {
        if (e instanceof FtsError && e.status === Status.NO_FILE) return null;
        throw e;
    }
}

/**
 * Put `bytes` on the watch as `/Apps/<folder>/<fileName>`, verified.
 *
 * Never a half-written app: the bytes go to `<fileName>.part`, the watch's
 * own CRC of it is checked against ours, and only then is the old file
 * deleted and the new one moved into place (FatFs will not rename over an
 * existing file). The result is checked once more under its final name.
 *
 * Any other `.uapp` in the folder is removed afterwards: the kernel registers
 * the first one it meets, so a stale copy could win.
 */
export async function installApp(
    client: FtsAppInstaller,
    app: { fileName: string; bytes: Uint8Array; appId?: string },
    options: { write?: WriteOptions; onStep?: (s: InstallStep) => void } = {},
): Promise<InstallResult> {
    const step = options.onStep ?? (() => {});
    const dir = client.appDir;
    const target = `${dir}/${app.fileName}`;
    const part = `${target}.part`;
    if (!client.isAppFile(target)) throw new FtsError(`Not an app file name: ${app.fileName}`);
    const size = app.bytes.length;
    const crc = crc32(app.bytes);
    const warnings: string[] = [];

    step({ step: "check", message: `Looking in ${dir}` });
    // An install over USB that followed the blog's advice lives in a folder
    // named for the app ID. Both would register; say so rather than touch it.
    if (app.appId) {
        const apps = (await listOrNull(client, "/Apps")) ?? [];
        if (apps.some((e) => e.isDir && e.name.toUpperCase() === app.appId!.toUpperCase())) {
            warnings.push(
                `/Apps/${app.appId} also holds a copy of this app (installed over USB?). Delete that folder over USB, or the watch runs whichever it finds first.`,
            );
        }
    }

    let entries = await listOrNull(client, dir);
    if (entries === null) {
        step({ step: "mkdir", message: `Creating ${dir}` });
        await client.mkdir(dir);
        entries = [];
    }
    const others = entries.filter(
        (e) => !e.isDir && e.name !== app.fileName && client.isAppFile(`${dir}/${e.name}`) && e.name !== `${app.fileName}.part`,
    );
    const existing = entries.find((e) => !e.isDir && e.name === app.fileName);

    step({ step: "upload", message: `Sending ${size} bytes` });
    await client.writeFile(part, app.bytes, options.write);

    step({ step: "verify", message: "Checking the watch's copy" });
    if (!sameDigest(await client.digest(part), size, crc)) {
        await client.remove(part).catch(() => {});
        throw new FtsError("The watch's copy does not match what was sent; nothing was installed.");
    }

    step({ step: "swap", message: `Installing as ${target}` });
    if (existing) await client.remove(target);
    await client.move(part, target);
    if (!sameDigest(await client.digest(target), size, crc)) {
        throw new FtsError(`${target} does not match after the move. Install again.`);
    }

    const removed: string[] = [];
    if (others.length) step({ step: "tidy", message: "Removing older copies" });
    for (const e of others) {
        const p = `${dir}/${e.name}`;
        await client.remove(p);
        removed.push(p);
    }

    step({ step: "done", message: "Installed. It runs from the watch's next restart." });
    return { status: "installed", removed, warnings };
}
