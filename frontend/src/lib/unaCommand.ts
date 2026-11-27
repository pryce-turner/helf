/**
 * The one Custom Command Service request Helf sends: RESET, to restart the
 * watch after an app install (plan 0026).
 *
 * The watch registers apps only when it scans `/Apps` at boot, so a newly
 * written `.uapp` does nothing until a restart. RESET is what the phone app
 * uses for that (`CustomCommandService::resetHandler` → `onRebootReq` →
 * `Power::reboot()`).
 *
 * Plan 0023 §6 put RESET under "never" for the sync, and that stands: nothing
 * in the poll loop can reach this. The encoder below produces exactly one
 * request, the two bytes `01 00`, and nothing else is encodable here, so the
 * opcode next door (0x02, START_FW_UPDATE, which flashes firmware) cannot be
 * sent by a typo.
 */

/** Custom Command Service and its command characteristic (write w/o response + notify). */
export const CMD_SERVICE = "554e4100-a2cf-4df8-0000-7e1e48595106";
export const CMD_CHAR = "554e4100-a2cf-4df8-0001-7e1e48595106";

const RESET = 0x01;
const OK = 0x01;

/** `ResetReq {command = 0x01, reserved = 0}`. The firmware checks the length is exactly 2. */
export function resetRequest(): Uint8Array<ArrayBuffer> {
    return Uint8Array.from([RESET, 0x00]);
}

/** The command characteristic, with notifications already on (the watch ignores commands until they are). */
export interface CommandChannel {
    write(data: Uint8Array<ArrayBuffer>): Promise<void>;
    subscribe(listener: (data: DataView) => void): () => void;
    onClose?(listener: () => void): () => void;
}

/**
 * Ask the watch to restart. Resolves once it has said OK or dropped the link
 * (it answers, then reboots, so either can come first); rejects on a refusal
 * or on silence.
 */
export function rebootWatch(channel: CommandChannel, { timeoutMs = 8000 } = {}): Promise<void> {
    return new Promise<void>((resolve, reject) => {
        let settled = false;
        const cleanups: (() => void)[] = [];
        const finish = (fn: () => void) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            for (const c of cleanups) c();
            fn();
        };
        const timer = setTimeout(
            () => finish(() => reject(new Error("The watch did not answer the restart request."))),
            timeoutMs,
        );
        cleanups.push(
            channel.subscribe((v) => {
                if (v.byteLength < 2 || v.getUint8(0) !== RESET) return;
                const status = v.getUint8(1);
                if (status === OK) finish(resolve);
                else finish(() => reject(new Error(`The watch refused to restart (status ${status}).`)));
            }),
        );
        if (channel.onClose) cleanups.push(channel.onClose(() => finish(resolve)));
        channel.write(resetRequest()).catch((e) => finish(() => reject(e)));
    });
}
