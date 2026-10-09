import { BookOpenCheck } from "lucide-react";
import { useState } from "react";

import { SourceCard } from "@/components/citations/SourceCard";
import { citationLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types/assistant";

/** Compact source chips under an answer; selecting one expands its source card. */
export function CitationList({ citations }: { citations: Citation[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  if (citations.length === 0) return null;
  const open = citations.find((citation) => citation.id === openId) ?? null;

  return (
    <section className="mt-5 border-t border-border pt-4" aria-label="Sources">
      <div className="mb-2.5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        <BookOpenCheck className="size-3.5" aria-hidden="true" />
        Sources
      </div>
      <ul className="flex flex-wrap gap-2">
        {citations.map((citation) => {
          const selected = citation.id === openId;
          return (
            <li key={citation.id}>
              <button
                type="button"
                onClick={() => setOpenId(selected ? null : citation.id)}
                aria-expanded={selected}
                className={cn(
                  "inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                  selected
                    ? "border-primary/50 bg-primary/15 text-foreground"
                    : "border-border bg-background/60 text-muted-foreground hover:border-primary/40 hover:text-foreground",
                )}
              >
                <span className="truncate">{citationLabel(citation)}</span>
                {citation.pageNumber !== null ? (
                  <span className="tabular-nums text-primary">· p. {citation.pageNumber}</span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
      {open ? (
        <div className="mt-3">
          <SourceCard key={open.id} citation={open} defaultExpanded />
        </div>
      ) : null}
    </section>
  );
}
