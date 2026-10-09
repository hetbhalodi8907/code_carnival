import { ArrowUpRight } from "lucide-react";

import { NexoraMark } from "@/components/brand/NexoraLogo";
import { SAMPLE_PROMPTS } from "@/components/chat/samplePrompts";

export function ChatEmptyState({ onSelect }: { onSelect: (question: string) => void }) {
  return (
    <div className="nexora-glow-soft flex flex-1 flex-col items-center justify-center rounded-2xl px-2 py-10 text-center">
      <NexoraMark className="size-14 animate-fade-up" />
      <div className="mt-5 animate-fade-up text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
        NEXORA
      </div>
      <h2 className="mt-1 animate-fade-up text-2xl font-semibold tracking-tight sm:text-3xl">Secure AI Workspace</h2>
      <p className="mt-3 max-w-md animate-fade-up text-[15px] text-muted-foreground">
        Ask a question about your authorized company information.
      </p>
      <ul className="mt-8 grid w-full max-w-2xl gap-3 sm:grid-cols-2" aria-label="Example questions">
        {SAMPLE_PROMPTS.map(({ label, question, icon: Icon }, index) => (
          <li key={label} className="animate-fade-up" style={{ animationDelay: `${80 + index * 50}ms` }}>
            <button
              type="button"
              onClick={() => onSelect(question)}
              className="group flex h-full w-full items-start gap-3 rounded-xl border border-border bg-card/70 p-4 text-left outline-none transition-[border-color,background-color,transform] hover:-translate-y-0.5 hover:border-primary/40 hover:bg-card focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-medium text-muted-foreground">{label}</span>
                <span className="mt-0.5 block text-sm font-medium">{question}</span>
              </span>
              <ArrowUpRight
                className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary"
                aria-hidden="true"
              />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
