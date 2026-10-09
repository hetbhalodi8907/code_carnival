import { ChevronDown, FileText } from "lucide-react";
import { useId, useState } from "react";

import { citationLabel, formatSimilarity } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types/assistant";

function CitationMeta({ citation }: { citation: Citation }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground tabular-nums">
      {citation.pageNumber !== null ? <span>Page {citation.pageNumber}</span> : null}
      {citation.similarity !== null ? <span>Similarity {formatSimilarity(citation.similarity)}</span> : null}
    </div>
  );
}

/** Expanded view of one source: title, page, similarity and the passage text. */
export function SourceCard({ citation, defaultExpanded = false }: { citation: Citation; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const passageId = useId();
  const excerpt = citation.excerpt?.trim();
  // Only long passages get a show-more toggle.
  const collapsible = (excerpt?.length ?? 0) > 220 || (excerpt?.split("\n").length ?? 0) > 3;

  return (
    <div className="animate-fade-in rounded-lg border border-border bg-background/50 p-3.5" data-testid="source-card">
      <div className="flex items-start gap-2.5">
        <FileText className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{citationLabel(citation)}</div>
          <CitationMeta citation={citation} />
        </div>
      </div>
      {excerpt ? (
        <>
          <p
            id={passageId}
            className={cn(
              "mt-2.5 whitespace-pre-line border-l-2 border-primary/40 pl-3 text-[13px] leading-relaxed text-muted-foreground",
              collapsible && !expanded && "line-clamp-3",
            )}
          >
            {excerpt}
          </p>
          {collapsible ? (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              aria-expanded={expanded}
              aria-controls={passageId}
              className="mt-2 inline-flex items-center gap-1 rounded text-xs font-medium text-primary outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
            >
              {expanded ? "Show less" : "Show full passage"}
              <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} aria-hidden="true" />
            </button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
