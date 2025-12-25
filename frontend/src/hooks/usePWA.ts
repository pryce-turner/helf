import { useEffect, useState } from "react";

export function usePWA() {
    const [isOnline, setIsOnline] = useState(navigator.onLine);
    const [isInstalled, setIsInstalled] = useState(false);

    useEffect(() => {
        // Check if app is installed
        if (window.matchMedia("(display-mode: standalone)").matches) {
            setIsInstalled(true);
        }

        // Listen for online/offline events
        const handleOnline = () => setIsOnline(true);
        const handleOffline = () => setIsOnline(false);

        window.addEventListener("online", handleOnline);
        window.addEventListener("offline", handleOffline);

        return () => {
            window.removeEventListener("online", handleOnline);
            window.removeEventListener("offline", handleOffline);
        };
    }, []);

    return { isOnline, isInstalled };
}
