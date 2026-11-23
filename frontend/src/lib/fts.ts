/**
 * The UNA Watch File Transfer Service (FTS), read-only.
 *
 * The wire protocol is the Adafruit BLE file transfer protocol with UNA's
 * version-5 extensions — `una-sdk/Docs/BLE-File-Transfer-Service.md` is the
 * contract, and `FileTransferService.cpp` in `una-kernel-public` is what the
 * watch actually does. Where the two disagree this file follows the firmware
 * and says so (plan 0023 §3).
 *
 * Everything here is pure: the client runs over an abstract `FtsTransport`, so
 * the reassembly and loss recovery are tested against a simulated watch that
 * drops notifications on purpose. `unaWatch.ts` is the Web Bluetooth plumbing
 * that supplies a real transport, and holds no logic.
 *
 * **Read-only by construction.** Only READ, READ_PACING, LISTDIR and DIGEST
 * have encoders, and `send()` refuses any other opcode, so a bug elsewhere
 * cannot turn into a WRITE, DELETE, MKDIR or MOVE on the watch.
 */

export const FTS_SERVICE = "0000febb-0000-1000-8000-00805f9b34fb";
/** UNA-specific: Adafruit upstream uses ADAF0100 / ADAF0200. */
export const FTS_VERSION_CHAR = "adaf0001-4669-6c65-5472-616e73666572";
export const FTS_RAW_CHAR = "adaf0002-4669-6c65-5472-616e73666572";

export const Command = {
    READ: 0x10,
    READ_DATA: 0x11,
    READ_PACING: 0x12,
    LISTDIR: 0x50,
    LISTDIR_ENTRY: 0x51,
    DIGEST: 0x70,
    DIGEST_STATUS: 0x71,
} as const;

/** The only opcodes this client will ever put on the wire. */
const ALLOWED_REQUESTS: ReadonlySet<number> = new Set([
    Command.READ,
    Command.READ_PACING,
    Command.LISTDIR,
    Command.DIGEST,
]);

export const Status = {
    OK: 0x01,
    ERROR: 0x02,
    NO_FILE: 0x03,
    PROTOCOL: 0x04,
    READ_ONLY: 0x05,
} as const;

const STATUS_NAMES: Record<number, string> = {
    [Status.ERROR]: "error",
    [Status.NO_FILE]: "no such file",
    [Status.PROTOCOL]: "protocol error",
    [Status.READ_ONLY]: "read-only",
};

export class FtsError extends Error {
    readonly status?: number;
    constructor(message: string, status?: number, options?: ErrorOptions) {
        super(message, options);
        this.status = status;
    }
}

/** The link went away mid-command. The poll loop treats this as "try later". */
export class FtsDisconnectedError extends FtsError {}

/**
 * A write-without-response characteristic with notifications on it.
 *
 * `subscribe` must deliver every notification on the Raw Transfer
 * characteristic, in arrival order, and return an unsubscribe function.
 * `onClose`, where supplied, fires when the GATT link drops, so an in-flight
 * command fails at once instead of waiting out its timer.
 */
export interface FtsTransport {
    write(data: Uint8Array<ArrayBuffer>): Promise<void>;
    subscribe(listener: (data: DataView) => void): () => void;
    onClose?(listener: () => void): () => void;
}

// ---------------------------------------------------------------- encoders

const utf8 = new TextEncoder();
const utf8Decoder = new TextDecoder();

function withPath(header: number, path: string): {
    bytes: Uint8Array<ArrayBuffer>;
    view: DataView;
    pathOffset: number;
} {
    if (!path.startsWith("/")) {
        // The firmware rejects these with ERROR_PROTOCOL; failing here names
        // the actual mistake.
        throw new FtsError(`FTS paths are absolute: ${JSON.stringify(path)}`);
    }
    const encoded = utf8.encode(path);
    if (encoded.length > 0xffff) throw new FtsError("Path too long");
    const bytes = new Uint8Array(header + encoded.length);
    bytes.set(encoded, header);
    return { bytes, view: new DataView(bytes.buffer), pathOffset: header };
}

export function listDirRequest(path: string): Uint8Array<ArrayBuffer> {
    const { bytes, view } = withPath(4, path);
    view.setUint8(0, Command.LISTDIR);
    view.setUint16(2, bytes.length - 4, true);
    return bytes;
}

export function readRequest(
    path: string,
    offset: number,
    size: number,
): Uint8Array<ArrayBuffer> {
    const { bytes, view } = withPath(12, path);
    view.setUint8(0, Command.READ);
    view.setUint16(2, bytes.length - 12, true);
    view.setUint32(4, offset, true);
    view.setUint32(8, size, true);
    return bytes;
}

export function readPacingRequest(
    offset: number,
    size: number,
): Uint8Array<ArrayBuffer> {
    const bytes = new Uint8Array(12);
    const view = new DataView(bytes.buffer);
    view.setUint8(0, Command.READ_PACING);
    view.setUint8(1, Status.OK);
    view.setUint32(4, offset, true);
    view.setUint32(8, size, true);
    return bytes;
}

export function digestRequest(path: string): Uint8Array<ArrayBuffer> {
    const { bytes, view } = withPath(4, path);
    view.setUint8(0, Command.DIGEST);
    view.setUint16(2, bytes.length - 4, true);
    return bytes;
}

// ---------------------------------------------------------------- decoders

export interface DirEntry {
    name: string;
    isDir: boolean;
    size: number;
    /**
     * The raw `modificationTime`, as a decimal string.
     *
     * Kept raw and compared raw. The doc says nanoseconds; the firmware sends
     * `utc_seconds * 1_000_000` (microseconds), and a value that may change
     * meaning between firmware versions is safest never interpreted for
     * deduplication. `mtimeToDate` reads it for display only.
     */
    mtime: string;
}

export type FtsResponse =
    | { kind: "error"; command: number; status: number }
    | {
          kind: "entry";
          status: number;
          entryNumber: number;
          totalEntries: number;
          /** Absent on the terminator. */
          entry: DirEntry | null;
      }
    | {
          kind: "data";
          status: number;
          chunkOffset: number;
          totalLength: number;
          /** Never longer than what the notification actually carried. */
          data: Uint8Array;
      }
    | { kind: "digest"; status: number; fileSize: number; crc32: number };

/**
 * Decode one Raw Transfer notification.
 *
 * Errors are the firmware's `sendErr`: two bytes, the **request** opcode and a
 * status — so a missing file answers a READ with `10 03`, not a READ_DATA.
 * Returns null for anything it cannot place; the caller ignores it.
 */
export function parseResponse(view: DataView): FtsResponse | null {
    if (view.byteLength < 2) return null;
    const command = view.getUint8(0);
    const status = view.getUint8(1);

    if (ALLOWED_REQUESTS.has(command)) {
        return { kind: "error", command, status };
    }

    switch (command) {
        case Command.LISTDIR_ENTRY: {
            if (view.byteLength < 28) return null;
            const pathLength = view.getUint16(2, true);
            const entryNumber = view.getUint32(4, true);
            const totalEntries = view.getUint32(8, true);
            if (pathLength === 0) {
                return {
                    kind: "entry",
                    status,
                    entryNumber,
                    totalEntries,
                    entry: null,
                };
            }
            const flags = view.getUint32(12, true);
            const mtime = view.getBigUint64(16, true).toString();
            const size = view.getUint32(24, true);
            const nameBytes = new Uint8Array(
                view.buffer,
                view.byteOffset + 28,
                Math.min(pathLength, view.byteLength - 28),
            );
            return {
                kind: "entry",
                status,
                entryNumber,
                totalEntries,
                entry: {
                    name: utf8Decoder.decode(nameBytes),
                    isDir: (flags & 1) === 1,
                    size,
                    mtime,
                },
            };
        }
        case Command.READ_DATA: {
            if (view.byteLength < 16) return null;
            const chunkOffset = view.getUint32(4, true);
            const totalLength = view.getUint32(8, true);
            const chunkLength = view.getUint32(12, true);
            const carried = Math.min(chunkLength, view.byteLength - 16);
            return {
                kind: "data",
                status,
                chunkOffset,
                totalLength,
                data: new Uint8Array(
                    view.buffer,
                    view.byteOffset + 16,
                    carried,
                ),
            };
        }
        case Command.DIGEST_STATUS: {
            if (view.byteLength < 12) {
                return { kind: "digest", status, fileSize: 0, crc32: 0 };
            }
            return {
                kind: "digest",
                status,
                fileSize: view.getUint32(4, true),
                crc32: view.getUint32(8, true),
            };
        }
        default:
            return null;
    }
}

/** Wall-clock reading of a raw mtime, for display. Never used to compare. */
export function mtimeToDate(raw: string): Date | null {
    let value: bigint;
    try {
        value = BigInt(raw);
    } catch {
        return null;
    }
    if (value === 0n) return null;
    // 2026 is ~1.8e15 in microseconds and ~1.8e18 in nanoseconds; a cut at
    // 1e17 separates the two for any date this watch will ever see.
    const ms = value >= 100_000_000_000_000_000n ? value / 1_000_000n : value / 1_000n;
    return new Date(Number(ms));
}

// ------------------------------------------------------------------- CRC-32

let crcTable: Uint32Array | null = null;

/** Standard CRC-32 (IEEE 802.3 / zlib), matching the watch's DIGEST. */
export function crc32(bytes: Uint8Array): number {
    if (!crcTable) {
        crcTable = new Uint32Array(256);
        for (let n = 0; n < 256; n++) {
            let c = n;
            for (let k = 0; k < 8; k++) {
                c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
            }
            crcTable[n] = c >>> 0;
        }
    }
    let crc = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) {
        crc = crcTable[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
}

// ------------------------------------------------------------------- client

export interface ReadOptions {
    /** Bytes per READ_PACING burst. 4096 is the documented sweet spot. */
    window?: number;
    /** Silence after which the window is re-requested from the contiguous end. */
    idleMs?: number;
    /** Re-requests in a row with no new bytes before giving up. */
    maxStalls?: number;
    onProgress?: (received: number, total: number) => void;
}

export interface Digest {
    fileSize: number;
    crc32: number;
}

/**
 * One command at a time over one Raw Transfer characteristic.
 *
 * The serialisation is not a nicety. The firmware cancels a parked read
 * window the moment any other command arrives (`mReadState.active = false`),
 * so a LISTDIR sent mid-READ silently truncates the read.
 */
export class FtsClient {
    private readonly transport: FtsTransport;
    private queue: Promise<unknown> = Promise.resolve();
    private listener: ((r: FtsResponse) => void) | null = null;
    private closeHandler: (() => void) | null = null;
    private closed = false;
    private readonly unsubscribe: () => void;
    private readonly unsubscribeClose: () => void;

    constructor(transport: FtsTransport) {
        this.transport = transport;
        this.unsubscribe = transport.subscribe((view) => {
            const response = parseResponse(view);
            if (response) this.listener?.(response);
        });
        this.unsubscribeClose =
            transport.onClose?.(() => {
                this.closed = true;
                this.closeHandler?.();
            }) ?? (() => {});
    }

    dispose(): void {
        this.unsubscribe();
        this.unsubscribeClose();
    }

    private async send(bytes: Uint8Array<ArrayBuffer>): Promise<void> {
        if (!ALLOWED_REQUESTS.has(bytes[0])) {
            throw new FtsError(
                `Refusing to send opcode 0x${bytes[0].toString(16)}: this client is read-only.`,
            );
        }
        if (this.closed) throw new FtsDisconnectedError("The watch disconnected.");
        await this.transport.write(bytes);
    }

    /**
     * Run one exchange exclusively. `run` receives every decoded response
     * until it settles; the idle timer restarts on each one.
     */
    private exchange<T>(
        idleMs: number,
        body: (ctx: {
            resolve: (v: T) => void;
            reject: (e: unknown) => void;
            send: (b: Uint8Array<ArrayBuffer>) => Promise<void>;
            onResponse: (fn: (r: FtsResponse) => void) => void;
            onIdle: (fn: () => void) => void;
        }) => void,
    ): Promise<T> {
        const task = this.queue.then(
            () =>
                new Promise<T>((resolve, reject) => {
                    let timer: ReturnType<typeof setTimeout> | undefined;
                    let idleFn: () => void = () =>
                        finish(() => reject(new FtsError("The watch stopped answering.")));
                    let settled = false;

                    const arm = () => {
                        if (timer) clearTimeout(timer);
                        timer = setTimeout(() => idleFn(), idleMs);
                    };
                    const finish = (fn: () => void) => {
                        if (settled) return;
                        settled = true;
                        if (timer) clearTimeout(timer);
                        this.listener = null;
                        this.closeHandler = null;
                        fn();
                    };

                    this.closeHandler = () =>
                        finish(() =>
                            reject(new FtsDisconnectedError("The watch disconnected.")),
                        );

                    body({
                        resolve: (v) => finish(() => resolve(v)),
                        reject: (e) => finish(() => reject(e)),
                        send: async (b) => {
                            arm();
                            try {
                                await this.send(b);
                            } catch (e) {
                                finish(() => reject(e));
                            }
                        },
                        onResponse: (fn) => {
                            this.listener = (r) => {
                                if (settled) return;
                                arm();
                                fn(r);
                            };
                        },
                        onIdle: (fn) => {
                            idleFn = () => {
                                if (!settled) fn();
                            };
                        },
                    });
                }),
        );
        // A failed command must not wedge the queue for the next one.
        this.queue = task.catch(() => {});
        return task;
    }

    /** LISTDIR. Resolves on the terminating entry. */
    listDir(path: string, { idleMs = 4000 } = {}): Promise<DirEntry[]> {
        return this.exchange<DirEntry[]>(idleMs, ({ resolve, reject, send, onResponse }) => {
            const entries: DirEntry[] = [];
            onResponse((r) => {
                if (r.kind === "error" && r.command === Command.LISTDIR) {
                    reject(
                        new FtsError(
                            `LISTDIR ${path}: ${STATUS_NAMES[r.status] ?? `status ${r.status}`}`,
                            r.status,
                        ),
                    );
                    return;
                }
                if (r.kind !== "entry") return;
                if (r.entry === null) {
                    if (r.entryNumber === r.totalEntries) resolve(entries);
                    return;
                }
                // A per-entry error is a name too long for the MTU: skip it
                // rather than fail the whole directory.
                if (r.status === Status.OK) entries.push(r.entry);
            });
            void send(listDirRequest(path));
        });
    }

    /** DIGEST — the watch's own CRC-32 of the whole file. Needs version ≥ 5. */
    digest(path: string, { idleMs = 15000 } = {}): Promise<Digest> {
        // Generous: the watch hashes the whole file off eMMC before answering.
        return this.exchange<Digest>(idleMs, ({ resolve, reject, send, onResponse }) => {
            onResponse((r) => {
                if (r.kind === "error" && r.command === Command.DIGEST) {
                    reject(
                        new FtsError(
                            `DIGEST ${path}: ${STATUS_NAMES[r.status] ?? `status ${r.status}`}`,
                            r.status,
                        ),
                    );
                } else if (r.kind === "digest") {
                    if (r.status === Status.OK) {
                        resolve({ fileSize: r.fileSize, crc32: r.crc32 });
                    } else {
                        reject(new FtsError(`DIGEST ${path}: status ${r.status}`, r.status));
                    }
                }
            });
            void send(digestRequest(path));
        });
    }

    /**
     * READ with windowed pacing, reassembled by offset.
     *
     * Each READ_DATA names its own offset, so arrival order does not matter
     * and a duplicate is harmless. The next window is always requested from
     * the **contiguous end** — the first byte not yet held — so a dropped
     * notification is re-requested instead of leaving a hole. A burst is over
     * when the chunk ending at the window's end arrives, or when the watch
     * goes quiet for `idleMs` (the last chunk was the one lost).
     *
     * A file whose length changes mid-read is rejected: it is being written,
     * and its next listing will show a new size anyway.
     */
    readFile(path: string, options: ReadOptions = {}): Promise<Uint8Array> {
        const { window = 4096, idleMs = 2000, maxStalls = 6, onProgress } = options;

        return this.exchange<Uint8Array>(idleMs, ({ resolve, reject, send, onResponse, onIdle }) => {
            let total = -1;
            let buffer = new Uint8Array(0);
            let have = new Uint8Array(0); // 1 per byte held
            let contiguous = 0;
            let windowEnd = window;
            let stalls = 0;
            let lastContiguous = 0;

            const requestFrom = (offset: number) => {
                windowEnd = total >= 0 ? Math.min(offset + window, total) : offset + window;
                void send(readPacingRequest(offset, window));
            };

            const advance = () => {
                while (contiguous < total && have[contiguous]) contiguous++;
            };

            onIdle(() => {
                if (contiguous > lastContiguous) {
                    stalls = 0;
                } else if (++stalls > maxStalls) {
                    reject(
                        new FtsError(
                            `READ ${path}: no progress after ${maxStalls} re-requests at byte ${contiguous}.`,
                        ),
                    );
                    return;
                }
                lastContiguous = contiguous;
                if (total < 0) {
                    // Not even the first chunk arrived; ask again from scratch.
                    void send(readRequest(path, 0, window));
                } else {
                    requestFrom(contiguous);
                }
            });

            onResponse((r) => {
                if (
                    r.kind === "error" &&
                    (r.command === Command.READ || r.command === Command.READ_PACING)
                ) {
                    reject(
                        new FtsError(
                            `READ ${path}: ${STATUS_NAMES[r.status] ?? `status ${r.status}`}`,
                            r.status,
                        ),
                    );
                    return;
                }
                if (r.kind !== "data") return;
                if (r.status !== Status.OK) {
                    reject(new FtsError(`READ ${path}: status ${r.status}`, r.status));
                    return;
                }

                if (total < 0) {
                    total = r.totalLength;
                    buffer = new Uint8Array(total);
                    have = new Uint8Array(total);
                    windowEnd = Math.min(windowEnd, total);
                } else if (r.totalLength !== total) {
                    reject(
                        new FtsError(
                            `READ ${path}: the file changed size mid-read (${total} → ${r.totalLength}).`,
                        ),
                    );
                    return;
                }

                const start = r.chunkOffset;
                const end = Math.min(start + r.data.length, total);
                if (end > start) {
                    buffer.set(r.data.subarray(0, end - start), start);
                    have.fill(1, start, end);
                    advance();
                }
                onProgress?.(contiguous, total);

                if (contiguous >= total) {
                    resolve(buffer);
                    return;
                }
                // End of this burst: ask for the next window from the first
                // missing byte, which re-covers any hole the burst left.
                if (end >= windowEnd) {
                    stalls = 0;
                    lastContiguous = contiguous;
                    requestFrom(contiguous);
                }
            });

            void send(readRequest(path, 0, window));
        });
    }
}
