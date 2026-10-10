import { MessagesSquare, Search } from "lucide-react";

import { AccessDenied, AssistantError, AssistantLoading, InsufficientContext, NoAuthorizedContext } from "@/components/chat/AssistantStates";
import type { ChatEntry } from "@/components/chat/types";
import { TrustProofReceipt } from "@/components/chat/TrustProofReceipt";
import { CitationList } from "@/components/citations/CitationList";
import type { AssistantResult } from "@/types/assistant";

type AssistantEntry = Extract<ChatEntry, { role: "assistant" }>;
type Answered = Extract<AssistantResult, { kind: "answered" }>;

function AnswerText({ text }: { text: string }) {
  return (
    <div className="space-y-2.5 text-[14.5px] leading-[1.7]">
      {text.split(/\n{2,}/).map((paragraph, index) => (
        <p key={index} className="whitespace-pre-line">
          {paragraph}
        </p>
      ))}
    </div>
  );
}

/** The model's [S<n>] references, shown only as unverified suggestions (validation is not built yet). */
function UnverifiedReferences({ numbers }: { numbers: number[] }) {
  if (numbers.length === 0) return null;
  return (
    <p className="mt-3 text-xs leading-relaxed text-muted-foreground" data-testid="unverified-references">
      References {numbers.map((number) => `[S${number}]`).join(", ")} in this answer were suggested by the AI and
      have not been verified against the sources.
    </p>
  );
}

function AnswerCard({ result }: { result: Answered }) {
  const count = result.sources.length;
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-4 shadow-xs sm:px-[18px]">
      <div className="mb-2.5 flex items-center gap-2 text-xs font-semibold text-primary">
        <MessagesSquare className="size-[15px]" aria-hidden="true" />
        NEXORA Assistant
      </div>
      <AnswerText text={result.answer} />
      {count > 0 ? (
        <div className="mt-3.5 flex items-center gap-2 border-t border-border pt-2.5 text-[12.5px] text-muted-foreground">
          <Search className="size-[15px] text-subtle" aria-hidden="true" />
          {count} authorized {count === 1 ? "source" : "sources"} retrieved
        </div>
      ) : null}
      <CitationList sources={result.sources} />
      <UnverifiedReferences numbers={result.unverifiedSourceNumbers} />
    </div>
  );
}

interface RetryProps {
  onRetry?: () => void;
  retryDisabled?: boolean;
}

function Body({ entry, onRetry, retryDisabled }: { entry: AssistantEntry } & RetryProps) {
  if (entry.state === "pending") return <AssistantLoading />;
  if (entry.state === "error") return <AssistantError error={entry.error} onRetry={onRetry} retryDisabled={retryDisabled} />;
  const { result } = entry;
  switch (result.kind) {
    case "access_denied":
      return <AccessDenied />;
    case "no_authorized_context":
      return <NoAuthorizedContext message={result.message} />;
    case "insufficient_context":
      return <InsufficientContext message={result.message} />;
    case "answered":
      return <AnswerCard result={result} />;
  }
}

export function AssistantMessage({ entry, ...retry }: { entry: AssistantEntry } & RetryProps) {
  // The receipt exists only for a completed reply: never for pending, error or access-denied entries.
  const receipt =
    entry.state === "done" && (entry.result.kind === "answered" || entry.result.kind === "insufficient_context")
      ? entry.result
      : null;
  return (
    <article aria-label="Nexora AI response">
      <Body entry={entry} {...retry} />
      {receipt ? <TrustProofReceipt result={receipt} /> : null}
    </article>
  );
}
