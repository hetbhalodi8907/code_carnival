import { Eye, EyeOff, Fingerprint, KeyRound, Loader2, LockKeyhole, ScanSearch, X } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { DemoAccounts } from "@/components/auth/DemoAccounts";
import { NexoraMark, NexoraWordmark } from "@/components/brand/NexoraLogo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEMO_ACCOUNTS, SHOW_DEMO_ACCOUNTS, type DemoAccount } from "@/config/demoAccounts";
import { useAuth } from "@/context/useAuth";
import { roleAppearance, roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api";

const DEFAULT_DESTINATION = "/app/chat";

function loginErrorMessage(error: unknown): string {
  const status = error instanceof ApiError ? error.status : -1;
  // The server answers wrong password, unknown email and inactive account identically.
  if (status === 401) return "Invalid email or password. Inactive accounts cannot log in.";
  if (status === 422) return "Enter a valid email address and password.";
  if (status === 0) return "Can't reach the Nexora server. Check that the backend is running and try again.";
  if (status === 502 || status === 503) return "Login is temporarily unavailable. Please try again shortly.";
  return "Login failed unexpectedly. Please try again.";
}

const PRINCIPLES = [
  { icon: Fingerprint, title: "Verified identity", text: "Every request is tied to your signed-in account." },
  { icon: ScanSearch, title: "Authorized retrieval", text: "Only sources your role may access are searched." },
  { icon: LockKeyhole, title: "Server-side enforcement", text: "Access rules live on the server, not in the browser." },
];

function findDemoAccount(email: string, password: string): DemoAccount | null {
  if (!SHOW_DEMO_ACCOUNTS) return null;
  const normalized = email.trim().toLowerCase();
  return DEMO_ACCOUNTS.find((account) => account.email === normalized && account.password === password) ?? null;
}

function Principles({ compact = false }: { compact?: boolean }) {
  return (
    <ul className={cn(compact ? "grid gap-4 sm:grid-cols-3" : "space-y-5")}>
      {PRINCIPLES.map(({ icon: Icon, title, text }) => (
        <li key={title} className="flex gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-border bg-card/70 text-primary">
            <Icon className="size-4" aria-hidden="true" />
          </span>
          <span>
            <span className="block text-sm font-semibold">{title}</span>
            <span className="block text-xs leading-relaxed text-muted-foreground">{text}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function LoginPage() {
  const { status, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const destination = from?.startsWith("/app") ? from : DEFAULT_DESTINATION;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitButton = useRef<HTMLButtonElement>(null);

  // Derived, so editing either field after picking a card clears the selection.
  const selected = findDemoAccount(email, password);
  const selectedLook = roleAppearance(selected?.role);

  if (status === "authenticated") return <Navigate to={destination} replace />;

  function selectDemoAccount(account: DemoAccount) {
    setEmail(account.email);
    setPassword(account.password);
    setError(null);
    submitButton.current?.focus();
  }

  function clearForm() {
    setEmail("");
    setPassword("");
    setError(null);
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
    <div className="grid min-h-full lg:grid-cols-[minmax(0,1fr)_minmax(400px,460px)]">
      <section
        className={cn(
          "nexora-glow order-2 flex flex-col gap-7 border-border px-4 py-10 sm:px-8 lg:order-1 lg:border-r lg:px-12 lg:py-9",
          !SHOW_DEMO_ACCOUNTS && "hidden justify-between lg:flex",
        )}
      >
        <NexoraWordmark className="hidden lg:flex" />
        {SHOW_DEMO_ACCOUNTS ? (
          <>
            <DemoAccounts selected={selected} onSelect={selectDemoAccount} />
            <div className="mt-auto space-y-5 border-t border-border pt-6">
              <Principles compact />
              <p className="text-xs text-muted-foreground">
                Demo environment · Nexora Technologies is a fictional company · all data is synthetic.
              </p>
            </div>
          </>
        ) : (
          <>
            <div className="max-w-md">
              <p className="text-[11px] font-medium uppercase tracking-[0.24em] text-primary">Secure AI Intelligence</p>
              <h2 className="mt-4 text-4xl font-semibold leading-tight tracking-tight">
                Ask questions. Get answers from information you’re authorized to access.
              </h2>
              <div className="mt-10">
                <Principles />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Demo environment · Nexora Technologies is a fictional company.</p>
          </>
        )}
      </section>

      <section className="nexora-glow order-1 flex items-center justify-center px-4 py-10 sm:px-8 lg:sticky lg:top-0 lg:order-2 lg:h-screen lg:bg-none">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="mb-8 flex flex-col items-center text-center lg:hidden">
            <NexoraMark className="size-12" />
            <div className="mt-4 text-sm font-semibold tracking-[0.24em]">NEXORA</div>
            <div className="text-xs text-muted-foreground">Secure AI Workspace</div>
          </div>

          <div className="rounded-2xl border border-border bg-card/90 p-6 shadow-[0_24px_80px_-32px_rgb(0_0_0/0.7)] backdrop-blur sm:p-8">
            <div className="mb-6">
              <p className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.18em] text-success">
                <KeyRound className="size-3.5" aria-hidden="true" />
                Enterprise secure access
              </p>
              <h1 className="mt-3 text-2xl font-semibold tracking-tight">Log in to NEXORA</h1>
              <p className="mt-1 text-sm text-muted-foreground">Secure AI Workspace</p>
            </div>

            {selected ? (
              <div
                className={cn("mb-4 flex items-center gap-3 rounded-xl border bg-background/60 p-3", selectedLook.selected)}
                role="status"
                aria-live="polite"
                data-testid="selected-demo-account"
              >
                <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg", selectedLook.tone)}>
                  <selectedLook.icon className="size-[18px]" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1 leading-tight">
                  <span className="block text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
                    Demo account selected
                  </span>
                  <span className="block truncate text-sm font-semibold">{roleLabel(selected.role)}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {selected.name} · {selected.email}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={clearForm}
                  className="grid size-7 place-items-center rounded-md text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Clear selected demo account"
                >
                  <X className="size-4" aria-hidden="true" />
                </button>
              </div>
            ) : null}

            {notice && !error ? (
              <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-sm text-warning" role="status">
                {notice}
              </div>
            ) : null}
            {error ? (
              <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive" role="alert">
                {error}
              </div>
            ) : null}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Work email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@company.com"
                  aria-invalid={error ? true : undefined}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    aria-invalid={error ? true : undefined}
                    className="pr-11"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute inset-y-0 right-1 my-auto grid size-9 place-items-center rounded-md text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                  >
                    {showPassword ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
                  </button>
                </div>
              </div>
              <Button ref={submitButton} type="submit" size="lg" className="mt-2 w-full" disabled={submitting}>
                {submitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : null}
                {submitting ? "Logging in…" : selected ? `Log in as ${roleLabel(selected.role)}` : "Log in"}
              </Button>
            </form>
          </div>

          <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">
            Every login is verified by the Nexora server. Permissions are enforced on the server for every request.
          </p>
        </div>
      </section>
    </div>
  );
}
