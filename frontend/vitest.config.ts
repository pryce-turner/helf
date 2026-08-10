import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

/**
 * Separate from `vite.config.ts` on purpose.
 *
 * The app config carries `VitePWA`, which registers a service worker and
 * generates a manifest — neither of which means anything in jsdom, and both of
 * which slow every run down for nothing. This config is the same React
 * pipeline and the same `@` alias, without it.
 */
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: { "@": path.resolve(__dirname, "./src") },
    },
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: ["./src/test/setup.ts"],
        include: ["src/**/*.test.{ts,tsx}"],
    },
});
