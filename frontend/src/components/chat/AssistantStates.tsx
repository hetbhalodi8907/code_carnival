import { CircleAlert, RotateCcw, SearchX, ShieldAlert, Unplug } from "lucide-react";

import { StateBlock } from "@/components/feedback/StateBlock";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { FriendlyError } from "@/services/api";

/** One request is in flight. There are no progress steps: the server answers in a single call. */
export function AssistantLoading() {
  return (
    <div className="rounded-xl border border-border bg-card px-[18px] py-4 shadow-xs" role="status" aria-live="polite">
      <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
        <Spinner className="size-[22px]" />
        <span>Retrieving authorized sources…</span>
      </div>
    </div>
  );
}

/** No authorized source: the server's fixed message. No document names, counts or policy internals. */
export function NoAuthorizedContext({ message }: { message: string }) {
  return (
    <StateBlock
      data-testid="no-authorized-context"
      icon={ShieldAlert}
      tone="warning"
      tag="No authorized sources"
      title="No authorized information found"
      hint="Permissions are applied during retrieval. Sources your account may not read are never retrieved, so the interface cannot see or reveal them."
    >
      {message}
    </StateBlock>
  );
}

/** Authorized sources were found but do not answer the question. */
export function InsufficientContext({ message }: { message: string }) {
  return (
    <StateBlock
      data-testid="insufficient-context"
      icon={SearchX}
      tone="info"
      tag="Not enough information"
      title="Not enough information"
      hint="Try rephrasing the question, or ask about a topic covered by documents available to your account."
      hintIcon="info"
    >
      {message}
    </StateBlock>
  );
}

interface AssistantErrorProps {
  error: FriendlyError;
  onRetry?: () => void;
  retryDisabled?: boolean;
}

/** A failed request, in calm language. Raw server payloads never reach this component. */
export function AssistantError({ error, onRetry, retryDisabled }: AssistantErrorProps) {
  return (
    <StateBlock
      role="alert"
      icon={error.retryable ? Unplug : CircleAlert}
      tone={error.retryable ? "warning" : "error"}
      title={error.title}
      actions={
        error.retryable && onRetry ? (
          <Button size="sm" onClick={onRetry} disabled={retryDisabled}>
            <RotateCcw aria-hidden="true" />
            Retry
          </Button>
        ) : null
      }
    >
      {error.message}
    </StateBlock>
  );
}
