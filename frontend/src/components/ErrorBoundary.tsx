import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Catch a render throw and *show* it.
 *
 * The app had none, which is why "the page went black" was an unanswerable
 * bug report: React unmounts the whole tree when a render throws, leaving the
 * `--bg-base` background and no message, and a reload is the only recovery.
 * That is indistinguishable from a compositor failure or the service worker
 * swapping the shell — three very different causes, one identical symptom.
 *
 * So this is a diagnostic as much as a safety net. If a blank screen now
 * carries an error, the cause is JavaScript. If it is still blank, it is
 * definitively not, and the search moves to the GPU or the service worker.
 *
 * Deliberately not styled with the design system's cards or tokens: whatever
 * broke may have broken them, and this has to render when the rest cannot.
 */
interface State {
    error: Error | null;
    info: string | null;
}

export default class ErrorBoundary extends Component<
    { children: ReactNode },
    State
> {
    state: State = { error: null, info: null };

    static getDerivedStateFromError(error: Error): Partial<State> {
        return { error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        // Keep it in the console too, so remote debugging over chrome://inspect
        // sees it even if the screen is photographed rather than read.
        console.error("[helf] render failed:", error, info.componentStack);
        this.setState({ info: info.componentStack ?? null });
    }

    render() {
        const { error, info } = this.state;
        if (!error) return this.props.children;

        return (
            <div
                style={{
                    padding: "16px",
                    margin: "16px",
                    border: "2px solid #ef4444",
                    borderRadius: "8px",
                    background: "#1a0a0a",
                    color: "#fafafa",
                    font: "13px/1.5 ui-monospace, monospace",
                    overflowX: "auto",
                }}
            >
                <p style={{ color: "#ef4444", fontWeight: 700, marginBottom: 8 }}>
                    Something in this page threw while rendering.
                </p>
                <p style={{ marginBottom: 8 }}>{String(error.message || error)}</p>
                {error.stack && (
                    <pre style={{ whiteSpace: "pre-wrap", opacity: 0.75, marginBottom: 8 }}>
                        {error.stack.split("\n").slice(0, 6).join("\n")}
                    </pre>
                )}
                {info && (
                    <pre style={{ whiteSpace: "pre-wrap", opacity: 0.6 }}>
                        {info.split("\n").slice(0, 8).join("\n")}
                    </pre>
                )}
                <button
                    onClick={() => location.reload()}
                    style={{
                        marginTop: 12,
                        padding: "8px 14px",
                        borderRadius: 6,
                        border: "1px solid #ef4444",
                        background: "transparent",
                        color: "#fafafa",
                    }}
                >
                    Reload
                </button>
            </div>
        );
    }
}
