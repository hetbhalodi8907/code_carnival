import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { resetAssistantRouteCache } from "@/services/assistant";
import { clearSession } from "@/services/session";

afterEach(() => {
  cleanup();
  clearSession();
  resetAssistantRouteCache();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
