import { useQuery } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { androidAppApi } from "@/lib/api";

/** The URL the download button points at. Not under /api/, on purpose. */
export const ANDROID_APK_URL = "/download/helf.apk";

const isAndroidBrowser = () =>
    typeof navigator !== "undefined" && /android/i.test(navigator.userAgent);

/**
 * The native app, when this page is somewhere it could be offered: an Android
 * browser that is not already inside the app. Null otherwise, including while
 * the answer is loading, and the request is not made at all elsewhere.
 *
 * This is "eligible", not "showing": a dismissal of the download prompt does
 * not make the PWA install prompt come back, because on Android the app
 * supersedes the PWA.
 */
export function useAndroidAppOffer() {
    const eligible = isAndroidBrowser() && !Capacitor.isNativePlatform();
    const { data } = useQuery({
        queryKey: ["android-app"],
        queryFn: async () => (await androidAppApi.info()).data,
        enabled: eligible,
        // A build changes only on redeploy; asking again mid-session buys nothing.
        staleTime: Infinity,
    });
    return eligible && data?.available ? data : null;
}
