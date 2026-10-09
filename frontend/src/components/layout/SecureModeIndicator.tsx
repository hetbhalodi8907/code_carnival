import { ShieldCheck } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Describes the system's operating mode. It does not evaluate access; the server
 * enforces authorization on every request.
 */
export function SecureModeIndicator() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-success/25 bg-success/10 px-3 py-1.5 text-xs font-medium text-success outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Secure retrieval active. Only information authorized for your account is used to answer questions."
        >
          <span className="relative flex size-2">
            <span className="size-2 animate-signal rounded-full bg-success" />
          </span>
          <ShieldCheck className="size-3.5" aria-hidden="true" />
          <span className="hidden tracking-wide sm:inline">SECURE RETRIEVAL</span>
          <span className="hidden text-success/80 lg:inline">· Active</span>
        </button>
      </TooltipTrigger>
      <TooltipContent>
        Only information authorized for your account is used to answer questions. Access is enforced by the
        Nexora server on every request.
      </TooltipContent>
    </Tooltip>
  );
}
