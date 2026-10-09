import { useId, useState } from "react";

import { SourceCard } from "@/components/citations/SourceCard";
import type { RetrievedSource } from "@/types/assistant";

/**
 * The authorized sources the server gave the model, as expandable cards. These are
 * retrieved sources, not verified citations of the answer.
 */
export function CitationList({ sources }: { sources: RetrievedSource[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const idPrefix = useId();
  if (sources.length === 0) return null;

  return (
    <section className="mt-4" aria-label="Sources retrieved for this answer">
      <div className="flex items-center gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-[0.05em] text-subtle">Sources</h4>
        <span className="rounded-full bg-muted px-2 py-px text-[11.5px] text-subtle">{sources.length}</span>
      </div>
      <p className="mb-2.5 mt-1 text-xs text-muted-foreground">
        Authorized passages the assistant was given. They are not yet verified as support for each statement.
      </p>
      <ul className="flex flex-col gap-2.5">
        {sources.map((source) => (
          <li key={source.id}>
            <SourceCard
              source={source}
              expanded={source.id === openId}
              onToggle={() => setOpenId(source.id === openId ? null : source.id)}
              detailId={`${idPrefix}-${source.id}`}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
