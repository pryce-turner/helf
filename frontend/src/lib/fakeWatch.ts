/**
 * A simulated UNA Watch FTS server, for tests.
 *
 * Mirrors `FileTransferService.cpp` where it matters to a client: READ and
 * READ_PACING answer with a burst of READ_DATA capped at the MTU's payload,
 * errors are two bytes carrying the *request* opcode, LISTDIR ends on an
 * entry with `pathLength == 0`, and mtimes are `seconds * 1e6` exactly as the
 * firmware computes them (not the nanoseconds the doc promises).
 *
 * `drop` decides, per outgoing notification, whether it is lost in the air.
 */

import type { FtsTransport } from "./fts";
import { Command, Status, crc32 } from "./fts";

export interface FakeNode {
    data?: Uint8Array;
    dir?: boolean;
    mtimeSeconds?: number;
}

export class FakeWatch {
    files = new Map<string, FakeNode>();
    /** Data bytes per READ_DATA: (MTU 220 − 3) − 16 header. */
    maxChunk = 201;
    drop: (bytes: Uint8Array, index: number) => boolean = () => false;
    /** Every request the client wrote, for assertions. */
    requests: Uint8Array[] = [];
    /** Called before each READ_DATA burst; lets a test grow a file mid-read. */
    beforeBurst: (path: string) => void = () => {};
    private listeners = new Set<(v: DataView) => void>();
    private closeListeners = new Set<() => void>();
    private sent = 0;
    private readPath = "";

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
                // Answer asynchronously, as the radio would.
                setTimeout(() => this.handle(new Uint8Array(data)), 0);
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

        switch (cmd) {
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
