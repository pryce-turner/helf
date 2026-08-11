import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { X, Download } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
    prompt: () => Promise<void>;
    userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISSED_KEY = "pwa-prompt-dismissed";
const DISMISSAL_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * True while a recent "Not now" should still be honoured.
 *
 * Read at the moment `beforeinstallprompt` fires, not once at mount. Chrome
 * re-fires that event on every page load, so a check that only ran in the
 * initial state was overwritten a moment later and the prompt came back on the
 * next navigation — for a whole session, on every page.
 */
const recentlyDismissed = () => {
    const dismissed = localStorage.getItem(DISMISSED_KEY);
    if (!dismissed) return false;
    const at = parseInt(dismissed, 10);
    if (Number.isNaN(at)) return false;
    return Date.now() - at < DISMISSAL_WINDOW_MS;
};

export function InstallPrompt() {
    const [deferredPrompt, setDeferredPrompt] =
        useState<BeforeInstallPromptEvent | null>(null);
    const [showPrompt, setShowPrompt] = useState(false);

    useEffect(() => {
        const handler = (e: Event) => {
            e.preventDefault();
            setDeferredPrompt(e as BeforeInstallPromptEvent);
            if (!recentlyDismissed()) setShowPrompt(true);
        };

        window.addEventListener("beforeinstallprompt", handler);

        return () => {
            window.removeEventListener("beforeinstallprompt", handler);
        };
    }, []);

    const handleInstallClick = async () => {
        if (!deferredPrompt) return;

        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;

        if (outcome === "accepted") {
            console.log("User accepted the install prompt");
        } else {
            console.log("User dismissed the install prompt");
        }

        setDeferredPrompt(null);
        setShowPrompt(false);
    };

    const handleDismiss = () => {
        setShowPrompt(false);
        // Remember dismissal for 7 days
        localStorage.setItem(
            "pwa-prompt-dismissed",
            Date.now().toString(),
        );
    };

    if (!showPrompt || !deferredPrompt) return null;

    return (
        <div className="install-prompt animate-in" role="dialog" aria-label="Install Helf">
            <div className="flex items-start" style={{ gap: 'var(--space-3)' }}>
                <div style={{ flexShrink: 0, marginTop: '2px' }}>
                    <Download style={{ width: '20px', height: '20px', color: 'var(--accent)' }} />
                </div>
                <div style={{ flex: 1 }}>
                    <h3 style={{
                        fontFamily: 'var(--font-display)',
                        fontSize: '15px',
                        fontWeight: 600,
                        marginBottom: 'var(--space-1)',
                    }}>
                        Install Helf
                    </h3>
                    <p style={{
                        fontSize: '13px',
                        color: 'var(--text-secondary)',
                        marginBottom: 'var(--space-3)',
                        lineHeight: 1.4,
                    }}>
                        Install for a better experience and offline access.
                    </p>
                    <div className="flex" style={{ gap: 'var(--space-2)' }}>
                        <Button
                            size="sm"
                            onClick={handleInstallClick}
                            style={{ flex: 1 }}
                        >
                            Install
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleDismiss}
                        >
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
