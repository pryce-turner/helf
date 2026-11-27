import { useState } from "react";
import { Button } from "@/components/ui/button";
import { X, Smartphone } from "lucide-react";
import { ANDROID_APK_URL, useAndroidAppOffer } from "@/hooks/useAndroidApp";

const DISMISSED_KEY = "android-app-prompt-dismissed";
const DISMISSAL_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * True while a recent dismissal should still be honoured.
 *
 * Read at render, when the offer is about to show, not once at mount: the
 * answer to "is there an app" arrives from the network after mount, and
 * `InstallPrompt` learned that a check made only in initial state gets
 * overwritten by whatever arrives later.
 */
const recentlyDismissed = () => {
    try {
        const at = parseInt(localStorage.getItem(DISMISSED_KEY) ?? "", 10);
        return !Number.isNaN(at) && Date.now() - at < DISMISSAL_WINDOW_MS;
    } catch {
        return false;
    }
};

const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

/**
 * Offers the Android app to an Android browser. Not for the watch only: the
 * app is Helf in a native shell, and the watch is just what needs it most.
 */
export function AndroidAppPrompt() {
    const app = useAndroidAppOffer();
    const [dismissedNow, setDismissedNow] = useState(false);

    const handleDismiss = () => {
        setDismissedNow(true);
        try {
            localStorage.setItem(DISMISSED_KEY, Date.now().toString());
        } catch {
            // Private mode: the prompt is merely gone for this page view.
        }
    };

    if (!app || dismissedNow || recentlyDismissed()) return null;

    const detail = [
        app.version_name && `Version ${app.version_name}`,
        app.size_bytes != null && megabytes(app.size_bytes),
    ]
        .filter(Boolean)
        .join(" · ");

    return (
        <div className="install-prompt animate-in" role="dialog" aria-label="Helf for Android">
            <div className="flex items-start" style={{ gap: 'var(--space-3)' }}>
                <div style={{ flexShrink: 0, marginTop: '2px' }}>
                    <Smartphone style={{ width: '16px', height: '16px', color: 'var(--text-secondary)' }} />
                </div>
                <div style={{ flex: 1 }}>
                    <h3 style={{
                        fontFamily: 'var(--font-display)',
                        fontSize: '15px',
                        fontWeight: 600,
                        marginBottom: 'var(--space-1)',
                    }}>
                        Helf for Android
                    </h3>
                    <p style={{
                        fontSize: '13px',
                        color: 'var(--text-secondary)',
                        marginBottom: 'var(--space-3)',
                        lineHeight: 1.4,
                    }}>
                        {detail}
                    </p>
                    <div className="flex" style={{ gap: 'var(--space-2)' }}>
                        <Button size="sm" asChild style={{ flex: 1 }}>
                            <a href={ANDROID_APK_URL} download>
                                Download
                            </a>
                        </Button>
                        <Button size="sm" variant="ghost" onClick={handleDismiss}>
                            Not now
                        </Button>
                    </div>
                </div>
                <button
                    onClick={handleDismiss}
                    className="action-btn"
                    aria-label="Dismiss"
                    style={{ flexShrink: 0, width: '28px', height: '28px' }}
                >
                    <X style={{ width: '16px', height: '16px' }} />
                </button>
            </div>
        </div>
    );
}
