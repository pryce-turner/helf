import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Calendar from "./pages/Calendar";
import WorkoutSession from "./pages/WorkoutSession";
import Progression from "./pages/Progression";
import BodyComposition from "./pages/BodyComposition";
import Upcoming from "./pages/Upcoming";
import Exercises from "./pages/Exercises";
import { InstallPrompt } from "./components/PWA/InstallPrompt";
import { usePWA } from "./hooks/usePWA";
import { WifiOff } from "lucide-react";

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 5 * 60 * 1000, // 5 minutes
        },
    },
});

function App() {
    const { isOnline } = usePWA();

    return (
        <QueryClientProvider client={queryClient}>
            <BrowserRouter>
                <div className="min-h-screen bg-background text-foreground dark">
                    {!isOnline && (
                        <div
                            className="px-4 py-2 text-center text-sm flex items-center justify-center gap-2"
                            style={{
                                background: 'var(--warning)',
                                color: 'var(--text-inverse)'
                            }}
                        >
                            <WifiOff className="h-4 w-4" />
                            <span>
                                You are offline. Some features may be limited.
                            </span>
                        </div>
                    )}
                    <Routes>
                        <Route path="/" element={<Calendar />} />
                        <Route path="/day/:date" element={<WorkoutSession />} />
                        <Route path="/progression" element={<Progression />} />
                        <Route
                            path="/progression/:exercise"
                            element={<Progression />}
                        />
                        <Route
                            path="/body-composition"
                            element={<BodyComposition />}
                        />
                        <Route path="/upcoming" element={<Upcoming />} />
                        <Route path="/exercises" element={<Exercises />} />
                    </Routes>
                    <InstallPrompt />
                </div>
            </BrowserRouter>
        </QueryClientProvider>
    );
}

export default App;
