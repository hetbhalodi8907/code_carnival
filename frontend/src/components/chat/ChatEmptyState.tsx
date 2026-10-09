import { MessagesSquare, Sparkles } from "lucide-react";

import { SAMPLE_QUESTIONS } from "@/components/chat/samplePrompts";

export function ChatEmptyState({ onSelect }: { onSelect: (question: string) => void }) {
  return (
    <div className="mx-auto max-w-[720px] px-4 py-10 text-center sm:px-6 sm:py-14">
      <span className="mx-auto mb-4 inline-flex size-12 items-center justify-center rounded-xl border border-border bg-card text-primary shadow-xs">
        <MessagesSquare className="size-[26px]" aria-hidden="true" />
      </span>
      <h3 className="mb-2 text-[19px] font-semibold">Ask across your company knowledge</h3>
      <p className="mx-auto max-w-[56ch] text-sm text-muted-foreground">
        Query policies, guidelines and department documents. Nexora retrieves the most relevant passages and answers
        only from sources your account is authorized to read.
      </p>
      <p className="mb-2.5 mt-6 text-xs font-semibold uppercase tracking-[0.05em] text-subtle">Try a sample question</p>
      <ul className="flex flex-wrap justify-center gap-2" aria-label="Sample questions">
        {SAMPLE_QUESTIONS.map((question) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => onSelect(question)}
              className="group inline-flex h-9 items-center gap-[7px] rounded-full border border-border-strong bg-card px-3.5 text-[13.5px] text-muted-foreground transition-colors hover:border-primary hover:bg-primary-soft hover:text-primary"
            >
              <Sparkles className="size-[15px] text-subtle group-hover:text-primary" aria-hidden="true" />
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
