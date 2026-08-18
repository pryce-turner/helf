import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Mount one page with the providers it actually needs.
 *
 * `retry: false` matters: React Query's default retries turn a stubbed 404
 * into a multi-second test, and an error state we deliberately provoked into a
 * timeout instead of an assertion.
 *
 * `path` is the pattern to register the page under, defaulting to the route
 * itself. Pages that read `useParams` need the two to differ — mounting
 * `/day/2026-08-11` under its own literal path matches, but binds no params,
 * so the page renders as though it had no date at all.
 */
export function renderPage(ui: ReactElement, route = "/", path = route) {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: 0 },
            mutations: { retry: false },
        },
    });

    return render(
        <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={[route]}>
                <Routes>
                    <Route path={path} element={ui} />
                </Routes>
            </MemoryRouter>
        </QueryClientProvider>,
    );
}
