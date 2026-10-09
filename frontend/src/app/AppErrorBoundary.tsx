import { Component, type ReactNode } from "react";

interface State {
  failed: boolean;
}

/**
 * Last-resort boundary: a render error anywhere shows a recovery screen instead of an
 * unexplained blank page. Error details stay in the developer console (React logs
 * them) and are never rendered. Plain elements only, so the fallback cannot fail on
 * the same shared component that crashed.
 */
export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="grid min-h-full place-items-center px-4 py-10" role="alert">
        <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 text-center shadow-sm sm:p-8">
          <div className="text-sm font-semibold tracking-[0.24em]">NEXORA</div>
          <h1 className="mt-4 text-xl font-semibold tracking-tight">Nexora encountered an unexpected UI error.</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Reload the application to continue. Access to company data is still enforced by the server.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-6 inline-flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground outline-none hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring"
          >
            Reload application
          </button>
        </div>
      </div>
    );
  }
}
