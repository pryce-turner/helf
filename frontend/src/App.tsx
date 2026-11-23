import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { format } from "date-fns";
import ErrorBoundary from "@/components/ErrorBoundary";
import Calendar from "./pages/Calendar";
import WorkoutSession from "./pages/WorkoutSession";
import Progression from "./pages/Progression";
import BodyComposition from "./pages/BodyComposition";
import Upcoming from "./pages/Upcoming";
import Library from "./pages/Library";
import LibraryItemView from "./pages/LibraryItemView";
import ProgramEditor from "./pages/ProgramEditor";
import PresetEditor from "./pages/PresetEditor";
import Exercises from "./pages/Exercises";
import Food from "./pages/Food";
import Supplements from "./pages/Supplements";
import Watch from "./pages/Watch";
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
                    <ErrorBoundary>
                    <Routes>
                        <Route path="/" element={<Calendar />} />
                        <Route path="/day/:date" element={<WorkoutSession />} />
                        {/* The standalone timer is gone (plan 0018): the day
                            player does its work from the day view. The
                            redirect stays for bookmarks. */}
                        <Route
                            path="/timer"
                            element={
                                <Navigate
                                    to={`/day/${format(new Date(), "yyyy-MM-dd")}`}
                                    replace
                                />
                            }
                        />
                        <Route path="/progression" element={<Progression />} />
                        <Route
                            path="/progression/:exercise"
                            element={<Progression />}
                        />
                        <Route
                            path="/body-composition"
                            element={<BodyComposition />}
                        />
                        <Route path="/watch" element={<Watch />} />
                        <Route path="/food" element={<Food />} />
                        <Route path="/supplements" element={<Supplements />} />
                        <Route path="/upcoming" element={<Upcoming />} />
                        {/* The Preset tab became the library (plan 0022). */}
                        <Route path="/presets" element={<Navigate to="/library" replace />} />
                        <Route path="/library" element={<Library />} />
                        <Route path="/library/blocks/:key" element={<LibraryItemView kind="block" />} />
                        <Route path="/library/programs/builtin/:key" element={<LibraryItemView kind="program" />} />
                        <Route path="/library/programs/:id" element={<ProgramEditor />} />
                        <Route path="/presets/:id" element={<PresetEditor />} />
                        {/* The page merged into /upcoming (9c4e7b21f806): one
                            queue, the mobility element flagged per set. The
                            redirect stays for bookmarks. */}
                        <Route
                            path="/mobility"
                            element={<Navigate to="/upcoming" replace />}
                        />
                        <Route path="/exercises" element={<Exercises />} />
                    </Routes>
                    </ErrorBoundary>
                    <InstallPrompt />
                </div>
            </BrowserRouter>
        </QueryClientProvider>
    );
}

export default App;
