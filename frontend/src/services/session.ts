/**
 * Access-token storage.
 *
 * sessionStorage keeps the token for the browser tab only (cleared when the tab
 * closes) and survives page reloads during a demo. Like any script-readable storage
 * it relies on the app not being vulnerable to XSS; an httpOnly cookie would need
 * backend changes. The token is never logged or rendered.
 */

const STORAGE_KEY = "nexora.session";

interface StoredSession {
  accessToken: string;
  /** Epoch milliseconds. */
  expiresAt: number;
}

// In-memory copy so the session still works when sessionStorage is unavailable.
let memorySession: StoredSession | null = null;

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function saveSession(accessToken: string, expiresInSeconds: number): StoredSession {
  const session = { accessToken, expiresAt: Date.now() + expiresInSeconds * 1000 };
  try {
    storage()?.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage unavailable (private mode): the session lives only in memory for this page.
  }
  memorySession = session;
  return session;
}

/** The current session, or null when missing, malformed or expired (expired ones are cleared). */
export function loadSession(): StoredSession | null {
  let session = memorySession;
  if (!session) {
    try {
      const raw = storage()?.getItem(STORAGE_KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (
        parsed &&
        typeof parsed === "object" &&
        typeof (parsed as StoredSession).accessToken === "string" &&
        typeof (parsed as StoredSession).expiresAt === "number"
      ) {
        session = parsed as StoredSession;
      }
    } catch {
      session = null;
    }
  }
  if (!session || session.expiresAt <= Date.now()) {
    clearSession();
    return null;
  }
  memorySession = session;
  return session;
}

export function getAccessToken(): string | null {
  return loadSession()?.accessToken ?? null;
}

export function clearSession(): void {
  memorySession = null;
  try {
    storage()?.removeItem(STORAGE_KEY);
  } catch {
    // Nothing else to clear.
  }
}
