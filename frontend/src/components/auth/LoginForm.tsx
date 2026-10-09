import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useState, type FormEvent, type RefObject } from "react";

import { NexoraWordmark } from "@/components/brand/NexoraLogo";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";

interface LoginFormProps {
  email: string;
  password: string;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  submitting: boolean;
  submitLabel: string;
  /** A failed sign-in. */
  error: string | null;
  /** A one-off message such as "session expired". */
  notice: string | null;
  submitRef: RefObject<HTMLButtonElement | null>;
}

/** The sign-in card. It only collects credentials; the page performs the real login call. */
export function LoginForm({
  email,
  password,
  onEmailChange,
  onPasswordChange,
  onSubmit,
  submitting,
  submitLabel,
  error,
  notice,
  submitRef,
}: LoginFormProps) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <section
      className="flex flex-col rounded-xl border border-border bg-card p-5 shadow-sm sm:p-8"
      aria-labelledby="login-title"
    >
      <NexoraWordmark className="mb-6 lg:mb-7" />

      <h1 id="login-title" className="mb-1.5 text-[26px] font-semibold leading-tight">
        Log in to NEXORA
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Access company knowledge through role-aware, source-grounded answers.
      </p>

      {notice && !error ? (
        <Alert variant="warning" role="status" className="mb-4">
          {notice}
        </Alert>
      ) : null}
      {error ? (
        <Alert variant="error" role="alert" className="mb-4">
          {error}
        </Alert>
      ) : null}

      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">Work email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            inputMode="email"
            required
            value={email}
            onChange={(event) => onEmailChange(event.target.value)}
            placeholder="name@company.com"
            aria-invalid={error ? true : undefined}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder="Enter your password"
              aria-invalid={error ? true : undefined}
              className="pr-11"
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              className="absolute inset-y-0 right-1 my-auto grid size-8 place-items-center rounded-md text-subtle hover:bg-muted hover:text-muted-foreground"
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
            >
              {showPassword ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
            </button>
          </div>
        </div>
        <Button ref={submitRef} type="submit" className="w-full" disabled={submitting}>
          {submitting ? <Spinner /> : null}
          {submitLabel}
        </Button>
      </form>

      <p className="mt-6 flex items-start gap-2 border-t border-border pt-5 text-[12.5px] leading-normal text-muted-foreground">
        <ShieldCheck className="mt-px size-4 shrink-0 text-subtle" aria-hidden="true" />
        Every login is verified by the Nexora server. Permissions are enforced on the server for every request.
      </p>
    </section>
  );
}
