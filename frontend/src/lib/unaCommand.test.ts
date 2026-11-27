import { describe, expect, it } from "vitest";
import { type CommandChannel, rebootWatch, resetRequest } from "./unaCommand";
import { exclusive } from "./watchConnector";
import type { WatchSession } from "./unaSync";

function channel(reply: (write: Uint8Array) => { notify?: number[]; close?: boolean }) {
    const listeners = new Set<(v: DataView) => void>();
    const closers = new Set<() => void>();
    const written: number[][] = [];
    const ch: CommandChannel = {
        write: async (data) => {
            written.push([...data]);
            const r = reply(data);
            setTimeout(() => {
                if (r.notify) for (const l of listeners) l(new DataView(Uint8Array.from(r.notify).buffer));
                if (r.close) for (const c of closers) c();
            }, 0);
        },
        subscribe: (l) => {
            listeners.add(l);
            return () => listeners.delete(l);
        },
        onClose: (l) => {
            closers.add(l);
            return () => closers.delete(l);
        },
    };
    return { ch, written };
}

describe("RESET", () => {
    it("is exactly ResetReq {0x01, 0x00}: nothing else is encodable", () => {
        expect([...resetRequest()]).toEqual([0x01, 0x00]);
    });

    it("resolves on the watch's OK", async () => {
        const { ch, written } = channel(() => ({ notify: [0x01, 0x01] }));
        await rebootWatch(ch);
        expect(written).toEqual([[0x01, 0x00]]);
    });

    it("resolves when the watch drops the link before answering", async () => {
        const { ch } = channel(() => ({ close: true }));
        await rebootWatch(ch);
    });

    it("rejects a refusal and silence", async () => {
        await expect(rebootWatch(channel(() => ({ notify: [0x01, 0x02] })).ch)).rejects.toThrow(/refused/);
        await expect(rebootWatch(channel(() => ({})).ch, { timeoutMs: 20 })).rejects.toThrow(/did not answer/);
    });
});

describe("exclusive", () => {
    it("holds a second session until the first disconnects", async () => {
        const order: string[] = [];
        const open = (name: string) => async () =>
            ({ client: null, version: 5, disconnect: () => order.push(`close ${name}`) }) as unknown as WatchSession;

        const first = await exclusive(open("poll"));
        order.push("poll open");
        let secondOpen = false;
        const second = exclusive(open("install")).then((s) => {
            secondOpen = true;
            order.push("install open");
            return s;
        });
        await new Promise((r) => setTimeout(r, 10));
        expect(secondOpen).toBe(false);
        first.disconnect();
        (await second).disconnect();
        expect(order).toEqual(["poll open", "close poll", "install open", "close install"]);
    });

    it("releases the lock when connecting fails", async () => {
        await expect(exclusive(() => Promise.reject(new Error("out of range")))).rejects.toThrow();
        const s = await exclusive(async () => ({ client: null, version: 5, disconnect: () => {} }) as unknown as WatchSession);
        s.disconnect();
    });
});
