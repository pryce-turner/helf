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
 */
export function renderPage(ui: ReactElement, route = "/") {
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
                    <Route path={route} element={ui} />
                </Routes>
            </MemoryRouter>
        </QueryClientProvider>,
    );
}
