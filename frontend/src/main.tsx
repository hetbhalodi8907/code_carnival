import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { AppErrorBoundary } from "@/app/AppErrorBoundary";
import { AppProviders } from "@/app/providers";
import { AppRoutes } from "@/app/router";

import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppErrorBoundary>
      <BrowserRouter>
        <AppProviders>
          <AppRoutes />
        </AppProviders>
      </BrowserRouter>
    </AppErrorBoundary>
  </StrictMode>,
);
