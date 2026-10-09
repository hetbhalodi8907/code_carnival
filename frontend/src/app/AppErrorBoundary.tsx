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
      <div className="grid min-h-full place-items-center bg-background px-4 py-10" role="alert">
        <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 text-center shadow-sm sm:p-8">
          <div className="text-[15px] font-bold tracking-[0.14em]">NEXORA</div>
          <h1 className="mt-4 text-xl font-semibold tracking-tight">Nexora encountered an unexpected UI error.</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Reload the application to continue. Access to company data is still enforced by the server.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-6 inline-flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-xs hover:bg-primary-hover"
          >
            Reload application
          </button>
        </div>
      </div>
    );
  }
}
