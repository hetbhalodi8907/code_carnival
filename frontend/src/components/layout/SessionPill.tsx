import { Lock } from "lucide-react";

/** States that the session is authenticated. It does not evaluate access; the server does on every request. */
export function SessionPill() {
  return (
    <span
      className="inline-flex h-[30px] items-center gap-1.5 rounded-full border border-success/25 bg-success-soft px-2.5 text-xs font-semibold text-success-strong"
      title="This session is authenticated. Access is enforced by the Nexora server on every request."
    >
      <span className="size-[7px] rounded-full bg-success" aria-hidden="true" />
      <Lock className="size-3.5" aria-hidden="true" />
      <span className="sr-only md:not-sr-only">Secure session</span>
    </span>
  );
}
