import { AlertTriangle, ShieldAlert } from "lucide-react";

import { NexoraMark } from "@/components/brand/NexoraLogo";
import { CitationList } from "@/components/citations/CitationList";
import { SourceCard } from "@/components/citations/SourceCard";
import type { ChatEntry } from "@/components/chat/types";
import type { FriendlyError } from "@/services/api";
import type { AssistantResult } from "@/types/assistant";

type AssistantEntry = Extract<ChatEntry, { role: "assistant" }>;

function Thinking() {
  return (
    <div className="flex items-center gap-3 py-1" role="status" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className="size-1.5 animate-thinking rounded-full bg-primary"
            style={{ animationDelay: `${dot * 160}ms` }}
          />
        ))}
      </span>
      <span className="text-sm text-muted-foreground">Retrieving authorized sources…</span>
    </div>
  );
}

function AnswerText({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-[15px] leading-[1.7]">
      {text.split(/\n{2,}/).map((paragraph, index) => (
        <p key={index} className="whitespace-pre-line">
          {paragraph}
        </p>
      ))}
    </div>
  );
}

/** Safe denial: no document names, departments, counts or policy internals. */
export function AccessRestricted() {
  return (
    <div className="flex gap-3.5" data-testid="access-restricted">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-warning/12 text-warning">
        <ShieldAlert className="size-[18px]" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <div className="text-sm font-semibold text-warning">Access restricted</div>
        <p className="mt-1 text-[15px] leading-relaxed">
          I don’t have access to information required to answer this question.
        </p>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          Secure retrieval policy: your identity is verified on every request, access rules are enforced by the
          server, and sources you aren’t authorized to view are never retrieved.
        </p>
      </div>
    </div>
  );
}

function Passages({ result }: { result: Extract<AssistantResult, { kind: "passages" }> }) {
  return (
    <div>
      <p className="text-[15px] leading-relaxed">
        Here are the most relevant passages from sources you’re authorized to access.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        AI answer generation isn’t enabled on this server yet, so passages are shown without a written answer.
      </p>
      <div className="mt-4 space-y-2.5">
        {result.passages.map((passage) => (
          <SourceCard key={passage.id} citation={passage} />
        ))}
      </div>
    </div>
  );
}

function ErrorNotice({ error }: { error: FriendlyError }) {
  return (
    <div className="flex gap-3.5" role="alert">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-destructive/12 text-destructive">
        <AlertTriangle className="size-[18px]" aria-hidden="true" />
      </span>
      <div>
        <div className="text-sm font-semibold text-destructive">{error.title}</div>
        <p className="mt-1 text-sm text-muted-foreground">{error.message}</p>
      </div>
    </div>
  );
}

function Body({ entry }: { entry: AssistantEntry }) {
  if (entry.state === "pending") return <Thinking />;
  if (entry.state === "error") return <ErrorNotice error={entry.error} />;
  const { result } = entry;
  if (result.kind === "restricted") return <AccessRestricted />;
  if (result.kind === "passages") return <Passages result={result} />;
  return (
    <>
      <AnswerText text={result.answer} />
      <CitationList citations={result.citations} />
    </>
  );
}

export function AssistantMessage({ entry }: { entry: AssistantEntry }) {
  return (
    <article className="animate-fade-up rounded-2xl border border-border bg-card p-4 shadow-sm sm:p-5" aria-label="Nexora AI response">
      <header className="mb-3 flex items-center gap-2.5">
        <NexoraMark className="size-6" />
        <span className="text-sm font-semibold">Nexora AI</span>
      </header>
      <Body entry={entry} />
    </article>
  );
}
