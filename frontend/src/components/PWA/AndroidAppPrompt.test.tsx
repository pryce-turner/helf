/**
 * The download prompt's whole job is deciding whether to appear: Android
 * browser, not already the app, and an APK actually built into the image.
 * Getting any one wrong either hides the app from the phone that needs it or
 * offers an Android download to an iPhone or to the app itself.
 */
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderPage } from "@/test/renderPage";
import { AndroidAppPrompt } from "./AndroidAppPrompt";
import { InstallPrompt } from "./InstallPrompt";
import { androidAppApi } from "@/lib/api";

const native = vi.hoisted(() => ({ isNativePlatform: vi.fn(() => false) }));
vi.mock("@capacitor/core", () => ({ Capacitor: native }));

vi.mock("@/lib/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/api")>();
    return { ...actual, androidAppApi: { info: vi.fn() } };
});

const info = vi.mocked(androidAppApi.info);

const ANDROID_UA = "Mozilla/5.0 (Linux; Android 15; Pixel 9) Chrome/130 Mobile Safari/537.36";
const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1";

const BUILT = {
    available: true,
    version_name: "1.0",
    version_code: 1,
    size_bytes: 4652670,
    sha256: "ab".repeat(32),
    built_at: "2026-11-26T20:00:00Z",
};

const answer = (data: object) =>
    info.mockResolvedValue({ data } as Awaited<ReturnType<typeof androidAppApi.info>>);

const userAgent = (ua: string) =>
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(ua);

beforeEach(() => {
    localStorage.clear();
    native.isNativePlatform.mockReturnValue(false);
    userAgent(ANDROID_UA);
});

afterEach(() => {
    vi.restoreAllMocks();
    info.mockReset();
});

describe("AndroidAppPrompt", () => {
    it("offers the download with version and size", async () => {
        answer(BUILT);
        renderPage(<AndroidAppPrompt />);

        expect(await screen.findByText("Helf for Android")).toBeInTheDocument();
        expect(screen.getByText("Version 1.0 · 4.4 MB")).toBeInTheDocument();
        const link = screen.getByRole("link", { name: "Download" });
        expect(link).toHaveAttribute("href", "/download/helf.apk");
        expect(link).toHaveAttribute("download");
    });

    it("stays away from a browser that is not Android, without even asking", async () => {
        userAgent(IPHONE_UA);
        answer(BUILT);
        renderPage(<AndroidAppPrompt />);

        await act(async () => {});
        expect(screen.queryByText("Helf for Android")).not.toBeInTheDocument();
        expect(info).not.toHaveBeenCalled();
    });

    it("stays away inside the app itself", async () => {
        native.isNativePlatform.mockReturnValue(true);
        answer(BUILT);
        renderPage(<AndroidAppPrompt />);

        await act(async () => {});
        expect(screen.queryByText("Helf for Android")).not.toBeInTheDocument();
        expect(info).not.toHaveBeenCalled();
    });

    it("stays away when the image was built without an APK", async () => {
        answer({ ...BUILT, available: false, version_name: null, size_bytes: null });
        renderPage(<AndroidAppPrompt />);

        await waitFor(() => expect(info).toHaveBeenCalled());
        await act(async () => {});
        expect(screen.queryByText("Helf for Android")).not.toBeInTheDocument();
    });

    it("dismisses, and stays dismissed for a week", async () => {
        answer(BUILT);
        const first = renderPage(<AndroidAppPrompt />);

        await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
        expect(screen.queryByText("Helf for Android")).not.toBeInTheDocument();
        first.unmount();

        renderPage(<AndroidAppPrompt />);
        await waitFor(() => expect(info).toHaveBeenCalledTimes(2));
        await act(async () => {});
        expect(screen.queryByText("Helf for Android")).not.toBeInTheDocument();

        // Eight days on it is back.
        localStorage.setItem(
            "android-app-prompt-dismissed",
            String(Date.now() - 8 * 24 * 60 * 60 * 1000),
        );
        renderPage(<AndroidAppPrompt />);
        expect(await screen.findByText("Helf for Android")).toBeInTheDocument();
    });
});

describe("InstallPrompt beside it", () => {
    const fireInstallEvent = () =>
        act(() => {
            const e = new Event("beforeinstallprompt");
            Object.assign(e, { prompt: vi.fn(), userChoice: Promise.resolve({ outcome: "dismissed" }) });
            window.dispatchEvent(e);
        });

    it("steps aside on Android when the app is on offer", async () => {
        answer(BUILT);
        renderPage(
            <>
                <InstallPrompt />
                <AndroidAppPrompt />
            </>,
        );
        await screen.findByText("Helf for Android");
        fireInstallEvent();

        expect(screen.queryByRole("dialog", { name: "Install Helf" })).not.toBeInTheDocument();
    });

    it("still shows when there is no app to offer", async () => {
        answer({ ...BUILT, available: false });
        renderPage(<InstallPrompt />);
        await waitFor(() => expect(info).toHaveBeenCalled());
        await act(async () => {});
        fireInstallEvent();

        expect(await screen.findByRole("dialog", { name: "Install Helf" })).toBeInTheDocument();
    });
});
