import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { X, Download } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
    prompt: () => Promise<void>;
    userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function InstallPrompt() {
    const [deferredPrompt, setDeferredPrompt] =
        useState<BeforeInstallPromptEvent | null>(null);
    const [showPrompt, setShowPrompt] = useState(() => {
        const dismissed = localStorage.getItem("pwa-prompt-dismissed");
        if (dismissed) {
            const dismissedTime = parseInt(dismissed);
            const sevenDaysInMs = 7 * 24 * 60 * 60 * 1000;
            if (Date.now() - dismissedTime < sevenDaysInMs) {
                return false;
            }
        }
        return false;
    });

    useEffect(() => {
        const handler = (e: Event) => {
            e.preventDefault();
            setDeferredPrompt(e as BeforeInstallPromptEvent);
            setShowPrompt(true);
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
        <div
            className="fixed z-50 animate-in"
            style={{
                bottom: 'calc(80px + env(safe-area-inset-bottom, 0px))',
                left: 'var(--space-4)',
                right: 'var(--space-4)',
                maxWidth: '400px',
                margin: '0 auto',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                boxShadow: 'var(--shadow-lg)',
                padding: 'var(--space-4)',
            }}
        >
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
