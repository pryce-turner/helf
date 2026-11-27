/**
 * A simulated UNA Watch FTS server, for tests.
 *
 * Mirrors `FileTransferService.cpp` where it matters to a client: READ and
 * READ_PACING answer with a burst of READ_DATA capped at the MTU's payload,
 * errors are two bytes carrying the *request* opcode, LISTDIR ends on an
 * entry with `pathLength == 0`, and mtimes are `seconds * 1e6` exactly as the
 * firmware computes them (not the nanoseconds the doc promises).
 *
 * The write path (plan 0026) follows `writeHandler` and friends: WRITE opens
 * and truncates, each WRITE_DATA is ACKed with `freeSpace = total −
 * contiguousEnd` (so a lost chunk stalls the ACK at the hole), the file is
 * committed only when the last byte lands, a resent tail after completion is
 * re-ACKed with 0, and any other command abandons an open write. MKDIR, DELETE
 * and MOVE fail as FatFs would: existing directory, missing or non-empty
 * target, rename over an existing file.
 *
 * `drop` decides, per outgoing notification, whether it is lost in the air;
 * `dropRequest` does the same for what the client writes. `maxRequest`
 * truncates longer requests, as a link with a small MTU would.
 */

import type { FtsTransport } from "./fts";
import { Command, Status, crc32 } from "./fts";

export interface FakeNode {
    data?: Uint8Array;
    dir?: boolean;
    mtimeSeconds?: number;
}

interface OpenWrite {
    path: string;
    total: number;
    contiguousEnd: number;
    buffer: Uint8Array;
}

export class FakeWatch {
    files = new Map<string, FakeNode>();
    /** Data bytes per READ_DATA: (MTU 220 − 3) − 16 header. */
    maxChunk = 201;
    drop: (bytes: Uint8Array, index: number) => boolean = () => false;
    /** Whether a request the client wrote is lost before the watch sees it. */
    dropRequest: (bytes: Uint8Array, index: number) => boolean = () => false;
    /** Longest request the link carries whole (ATT payload); longer ones are cut. */
    maxRequest = Infinity;
    /** Every request the client wrote, for assertions. */
    requests: Uint8Array[] = [];
    /** Called before each READ_DATA burst; lets a test grow a file mid-read. */
    beforeBurst: (path: string) => void = () => {};
    private listeners = new Set<(v: DataView) => void>();
    private closeListeners = new Set<() => void>();
    private sent = 0;
    private received = 0;
    private readPath = "";
    private writing: OpenWrite | null = null;
    /** The last write that completed, for the lost-final-ACK re-ACK. */
    private completed: { total: number } | null = null;

    add(path: string, node: FakeNode): this {
        this.files.set(path, node);
        // Create parent directories implicitly.
        const parts = path.split("/").filter(Boolean);
        for (let i = 1; i < parts.length; i++) {
            const dir = "/" + parts.slice(0, i).join("/");
            if (!this.files.has(dir)) this.files.set(dir, { dir: true });
        }
        return this;
    }

    addText(path: string, text: string, mtimeSeconds = 1_763_800_000): this {
        return this.add(path, { data: new TextEncoder().encode(text), mtimeSeconds });
    }

    disconnect(): void {
        for (const l of this.closeListeners) l();
    }

    transport(): FtsTransport {
        return {
            write: async (data) => {
                this.requests.push(new Uint8Array(data));
                if (this.dropRequest(data, this.received++)) return;
                const carried = new Uint8Array(data.subarray(0, Math.min(data.length, this.maxRequest)));
                // Answer asynchronously, as the radio would.
                setTimeout(() => this.handle(carried), 0);
            },
            subscribe: (listener) => {
                this.listeners.add(listener);
                return () => this.listeners.delete(listener);
            },
            onClose: (listener) => {
                this.closeListeners.add(listener);
                return () => this.closeListeners.delete(listener);
            },
        };
    }

    private notify(bytes: Uint8Array): void {
        const index = this.sent++;
        if (this.drop(bytes, index)) return;
        const copy = new Uint8Array(bytes);
        for (const l of this.listeners) l(new DataView(copy.buffer));
    }

    private err(cmd: number, status: number): void {
        this.notify(Uint8Array.from([cmd, status]));
    }

    private handle(req: Uint8Array): void {
        const v = new DataView(req.buffer, req.byteOffset, req.byteLength);
        const cmd = req[0];
        const pathAt = (offset: number, len: number) =>
            new TextDecoder().decode(req.subarray(offset, offset + len));

        // Firmware: any command but WRITE_DATA ends the lost-final-ACK window,
        // and anything that is not a write continuation closes an open file
        // (setPath closes it; the bytes so far stay on disk, uncommitted here).
        if (cmd !== Command.WRITE_DATA) this.completed = null;
        if (cmd !== Command.WRITE_DATA && cmd !== Command.WRITE) this.writing = null;

        switch (cmd) {
            case Command.WRITE: {
                const pathLength = v.getUint16(2, true);
                if (req.length !== 20 + pathLength) return this.err(cmd, Status.PROTOCOL);
                const path = pathAt(20, pathLength);
                const offset = v.getUint32(4, true);
                const total = v.getUint32(16, true);
                if (!path.startsWith("/") || offset > total) return this.err(cmd, Status.PROTOCOL);
                if (!this.files.get(this.parent(path))?.dir || this.files.get(path)?.dir) {
                    return this.err(cmd, Status.ERROR);
                }
                // Offset 0 truncates (FA_CREATE_ALWAYS); a resume keeps the head.
                const buffer = new Uint8Array(total);
                const old = this.files.get(path)?.data;
                if (offset > 0 && old) buffer.set(old.subarray(0, Math.min(offset, old.length)));
                this.files.set(path, { data: buffer.slice(0, offset), mtimeSeconds: 1_763_800_000 });
                this.writing = { path, total, contiguousEnd: offset, buffer };
                if (total - offset === 0) this.commit();
                return this.notify(this.writePacing(offset, total - offset));
            }
            case Command.WRITE_DATA: {
                const offset = v.getUint32(4, true);
                const size = v.getUint32(8, true);
                if (req.length !== 12 + size) return this.err(cmd, Status.PROTOCOL);
                const w = this.writing;
                if (!w) {
                    const done = this.completed;
                    if (done && offset <= done.total && size <= done.total - offset) {
                        return this.notify(this.writePacing(offset, 0));
                    }
                    return this.err(cmd, Status.ERROR);
                }
                if (size > w.total || offset > w.total - size) return this.err(cmd, Status.PROTOCOL);
                w.buffer.set(req.subarray(12, 12 + size), offset);
                if (offset <= w.contiguousEnd && offset + size > w.contiguousEnd) {
                    w.contiguousEnd = offset + size;
                }
                const free = w.total - w.contiguousEnd;
                if (free === 0) this.commit();
                return this.notify(this.writePacing(offset, free));
            }
            case Command.MKDIR: {
                const pathLength = v.getUint16(2, true);
                if (req.length !== 16 + pathLength) return this.err(cmd, Status.PROTOCOL);
                const path = pathAt(16, pathLength);
                if (this.files.has(path) || !this.files.get(this.parent(path))?.dir) {
                    return this.err(cmd, Status.ERROR);
                }
                this.files.set(path, { dir: true });
                const out = new Uint8Array(16);
                out[0] = Command.MKDIR_STATUS;
                out[1] = Status.OK;
                return this.notify(out);
            }
            case Command.DELETE: {
                const pathLength = v.getUint16(2, true);
                if (req.length !== 4 + pathLength) return this.err(cmd, Status.PROTOCOL);
                const path = pathAt(4, pathLength);
                const node = this.files.get(path);
                if (!node || (node.dir && this.children(path).length > 0)) return this.err(cmd, Status.ERROR);
                this.files.delete(path);
                return this.notify(Uint8Array.from([Command.DELETE_STATUS, Status.OK]));
            }
            case Command.MOVE: {
                const a = v.getUint16(2, true);
                const b = v.getUint16(4, true);
                if (req.length !== 6 + a + 1 + b) return this.err(cmd, Status.PROTOCOL);
                const from = pathAt(6, a);
                const to = pathAt(6 + a + 1, b);
                const node = this.files.get(from);
                if (!node || node.dir || this.files.has(to) || !this.files.get(this.parent(to))?.dir) {
                    return this.err(cmd, Status.ERROR);
                }
                this.files.delete(from);
                this.files.set(to, node);
                return this.notify(Uint8Array.from([Command.MOVE_STATUS, Status.OK]));
            }
            case Command.LISTDIR: {
                const path = pathAt(4, v.getUint16(2, true));
                const node = this.files.get(path);
                if (path !== "/" && !node?.dir) return this.err(cmd, Status.NO_FILE);
                const prefix = path === "/" ? "/" : `${path}/`;
                const children = [...this.files.entries()].filter(
                    ([p]) => p.startsWith(prefix) && p !== path && !p.slice(prefix.length).includes("/"),
                );
                children.forEach(([p, n], i) => {
                    const name = new TextEncoder().encode(p.slice(prefix.length));
                    const out = new Uint8Array(28 + name.length);
                    const o = new DataView(out.buffer);
                    o.setUint8(0, Command.LISTDIR_ENTRY);
                    o.setUint8(1, Status.OK);
                    o.setUint16(2, name.length, true);
                    o.setUint32(4, i, true);
                    o.setUint32(8, children.length, true);
                    o.setUint32(12, n.dir ? 1 : 0, true);
                    o.setBigUint64(16, BigInt(n.mtimeSeconds ?? 0) * 1_000_000n, true);
                    o.setUint32(24, n.data?.length ?? 0, true);
                    out.set(name, 28);
                    this.notify(out);
                });
                const end = new Uint8Array(28);
                const e = new DataView(end.buffer);
                e.setUint8(0, Command.LISTDIR_ENTRY);
                e.setUint8(1, Status.OK);
                e.setUint32(4, children.length, true);
                e.setUint32(8, children.length, true);
                return this.notify(end);
            }
            case Command.READ:
            case Command.READ_PACING: {
                let offset: number;
                let size: number;
                if (cmd === Command.READ) {
                    this.readPath = pathAt(12, v.getUint16(2, true));
                    offset = v.getUint32(4, true);
                    size = v.getUint32(8, true);
                } else {
                    offset = v.getUint32(4, true);
                    size = v.getUint32(8, true);
                }
                this.beforeBurst(this.readPath);
                const node = this.files.get(this.readPath);
                if (!node?.data) return this.err(cmd, Status.NO_FILE);
                const data = node.data;
                const end = Math.min(data.length, offset + size);
                if (offset >= end) {
                    return this.notify(this.readData(offset, data.length, new Uint8Array(0)));
                }
                for (let at = offset; at < end; at += this.maxChunk) {
                    const chunk = data.subarray(at, Math.min(end, at + this.maxChunk));
                    this.notify(this.readData(at, data.length, chunk));
                }
                return;
            }
            case Command.DIGEST: {
                const path = pathAt(4, v.getUint16(2, true));
                const node = this.files.get(path);
                if (!node?.data) return this.err(cmd, Status.NO_FILE);
                const out = new Uint8Array(12);
                const o = new DataView(out.buffer);
                o.setUint8(0, Command.DIGEST_STATUS);
                o.setUint8(1, Status.OK);
                o.setUint32(4, node.data.length, true);
                o.setUint32(8, crc32(node.data), true);
                return this.notify(out);
            }
            default:
                return this.err(cmd, Status.PROTOCOL);
        }
    }

    private parent(path: string): string {
        const i = path.lastIndexOf("/");
        return i <= 0 ? "/" : path.slice(0, i);
    }

    private children(path: string): string[] {
        const prefix = `${path}/`;
        return [...this.files.keys()].filter((p) => p.startsWith(prefix));
    }

    /** The last byte landed: the file is closed and on "disk". */
    private commit(): void {
        const w = this.writing!;
        this.files.set(w.path, { data: w.buffer, mtimeSeconds: 1_763_800_000 });
        this.completed = { total: w.total };
        this.writing = null;
    }

    private writePacing(offset: number, freeSpace: number): Uint8Array {
        const out = new Uint8Array(20);
        const o = new DataView(out.buffer);
        o.setUint8(0, Command.WRITE_PACING);
        o.setUint8(1, Status.OK);
        o.setUint32(4, offset, true);
        o.setUint32(16, freeSpace, true);
        return out;
    }

    private readData(offset: number, total: number, chunk: Uint8Array): Uint8Array {
        const out = new Uint8Array(16 + chunk.length);
        const o = new DataView(out.buffer);
        o.setUint8(0, Command.READ_DATA);
        o.setUint8(1, Status.OK);
        o.setUint32(4, offset, true);
        o.setUint32(8, total, true);
        o.setUint32(12, chunk.length, true);
        out.set(chunk, 16);
        return out;
    }
}
