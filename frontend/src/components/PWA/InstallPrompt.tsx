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
    const [showPrompt, setShowPrompt] = useState(false);

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

    useEffect(() => {
        const dismissed = localStorage.getItem("pwa-prompt-dismissed");
        if (dismissed) {
            const dismissedTime = parseInt(dismissed);
            const sevenDaysInMs = 7 * 24 * 60 * 60 * 1000;
            if (Date.now() - dismissedTime < sevenDaysInMs) {
                setShowPrompt(false);
            }
        }
    }, []);

    if (!showPrompt || !deferredPrompt) return null;

    return (
        <div className="fixed bottom-4 left-4 right-4 md:left-auto md:right-4 md:max-w-md z-50 bg-card border border-border rounded-lg shadow-lg p-4">
            <div className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-0.5">
                    <Download className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1">
                    <h3 className="font-semibold text-sm mb-1">
                        Install Helf
                    </h3>
                    <p className="text-xs text-muted-foreground mb-3">
                        Install this app on your device for a better experience
                        and offline access.
                    </p>
                    <div className="flex gap-2">
                        <Button
                            size="sm"
                            onClick={handleInstallClick}
                            className="flex-1"
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
                    className="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                    aria-label="Dismiss"
                >
                    <X className="h-4 w-4" />
                </button>
            </div>
        </div>
    );
}
