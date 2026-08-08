import { useEffect, useState } from "react";

export function usePWA() {
    const [isOnline, setIsOnline] = useState(navigator.onLine);
    const [isInstalled] = useState(
        () => window.matchMedia("(display-mode: standalone)").matches
    );

    useEffect(() => {
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
