import { useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { DemoAccounts } from "@/components/auth/DemoAccounts";
import { LoginForm } from "@/components/auth/LoginForm";
import { DEMO_ACCOUNTS, SHOW_DEMO_ACCOUNTS, type DemoAccount } from "@/config/demoAccounts";
import { useAuth } from "@/context/useAuth";
import { roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api";

const DEFAULT_DESTINATION = "/app/dashboard";

function loginErrorMessage(error: unknown): string {
  const status = error instanceof ApiError ? error.status : -1;
  // The server answers wrong password, unknown email and inactive account identically.
  if (status === 401) return "Invalid email or password. Inactive accounts cannot log in.";
  if (status === 422) return "Enter a valid email address and password.";
  if (status === 0) return "Can't reach the Nexora server. Check that the backend is running and try again.";
  if (status === 502 || status === 503) return "Login is temporarily unavailable. Please try again shortly.";
  return "Login failed unexpectedly. Please try again.";
}

function findDemoAccount(email: string, password: string): DemoAccount | null {
  if (!SHOW_DEMO_ACCOUNTS) return null;
  const normalized = email.trim().toLowerCase();
  return DEMO_ACCOUNTS.find((account) => account.email === normalized && account.password === password) ?? null;
}

export function LoginPage() {
  const { status, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const destination = from?.startsWith("/app") ? from : DEFAULT_DESTINATION;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitButton = useRef<HTMLButtonElement>(null);

  // Derived, so editing either field after picking a card clears the selection.
  const selected = findDemoAccount(email, password);

  if (status === "authenticated") return <Navigate to={destination} replace />;

  function selectDemoAccount(account: DemoAccount) {
    setEmail(account.email);
    setPassword(account.password);
    setError(null);
    submitButton.current?.focus();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      // Always the real backend: POST /api/v1/auth/login, then GET /api/v1/auth/me.
      await login(email.trim(), password);
      navigate(destination, { replace: true });
    } catch (caught) {
      setError(loginErrorMessage(caught));
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-full place-items-center bg-background px-4 py-6 sm:px-8 sm:py-7">
      <div
        className={cn(
          "grid w-full gap-6 lg:gap-8",
          SHOW_DEMO_ACCOUNTS ? "max-w-[720px] lg:max-w-[1160px] lg:grid-cols-[minmax(360px,440px)_minmax(0,1fr)]" : "max-w-[440px]",
        )}
      >
        <LoginForm
          email={email}
          password={password}
          onEmailChange={setEmail}
          onPasswordChange={setPassword}
          onSubmit={handleSubmit}
          submitting={submitting}
          submitLabel={submitting ? "Logging in…" : selected ? `Log in as ${roleLabel(selected.role)}` : "Log in"}
          error={error}
          notice={notice}
          submitRef={submitButton}
        />
        {SHOW_DEMO_ACCOUNTS ? <DemoAccounts selected={selected} onSelect={selectDemoAccount} /> : null}
      </div>
    </div>
  );
}
