import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "@/app/AppErrorBoundary";

function Broken(): never {
  throw new Error("secret internal detail at /srv/app.py:42");
}

describe("AppErrorBoundary", () => {
  it("renders its children when nothing fails", () => {
    render(
      <AppErrorBoundary>
        <p>Workspace</p>
      </AppErrorBoundary>,
    );
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("replaces a crashed tree with a recovery screen that hides error details", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <AppErrorBoundary>
        <Broken />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Nexora encountered an unexpected UI error.");
    expect(screen.getByRole("button", { name: "Reload application" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("secret internal detail");
  });
});
