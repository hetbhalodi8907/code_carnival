import { SAMPLE_PROMPTS } from "@/components/chat/samplePrompts";

export function QuickPrompts({ onSelect, disabled }: { onSelect: (question: string) => void; disabled?: boolean }) {
  return (
    <div
      className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-0.5 [scrollbar-width:none] sm:flex-wrap sm:overflow-visible"
      role="group"
      aria-label="Quick prompts"
    >
      {SAMPLE_PROMPTS.map(({ label, question, icon: Icon }) => (
        <button
          key={label}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(question)}
          title={question}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-muted-foreground outline-none transition-colors hover:border-primary/40 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <Icon className="size-3.5" aria-hidden="true" />
          {label}
        </button>
      ))}
    </div>
  );
}
