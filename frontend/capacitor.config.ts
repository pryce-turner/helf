import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Helf as a native app for Android and iOS (plan 0025).
 *
 * The UI is loaded from the Helf server, not bundled (0025 §3a): the app and
 * its watch-sync code update with every redeploy, like the PWA, instead of a
 * rebuilt APK per change. Capacitor still injects its plugin bridge into the
 * remote page, which is what gives the page native Bluetooth.
 *
 * `webDir` is still required, and holds the bundled fallback should the
 * remote mode ever need to be dropped (remove `server.url` and set
 * VITE_API_BASE_URL to the server instead).
 */
const config: CapacitorConfig = {
    appId: "app.helf",
    appName: "Helf",
    webDir: "dist",
    server: {
        url: "https://helf.pryce.fyi",
        // HTTPS only: no cleartext exception.
        cleartext: false,
    },
    android: {
        // A remote https page must not be blocked from the plugin bridge.
        allowMixedContent: false,
    },
};

export default config;
