/** The single place that controls where the backend lives. Empty = same origin (Vite proxy). */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

/**
 * Development-only simulated assistant (the real /assistant/query endpoint is not built yet).
 * `import.meta.env.DEV` is false in production builds, so the mock is compiled out entirely.
 */
export const USE_MOCK_ASSISTANT = import.meta.env.DEV && import.meta.env.VITE_USE_MOCK_API === "true";
