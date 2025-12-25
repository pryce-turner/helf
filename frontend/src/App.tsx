import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Calendar from "./pages/Calendar";
import WorkoutSession from "./pages/WorkoutSession";
import Progression from "./pages/Progression";
import BodyComposition from "./pages/BodyComposition";
import Upcoming from "./pages/Upcoming";

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
    return (
        <QueryClientProvider client={queryClient}>
            <BrowserRouter>
                <div className="min-h-screen bg-background text-foreground dark">
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
                    </Routes>
                </div>
            </BrowserRouter>
        </QueryClientProvider>
    );
}

export default App;
