import { ChevronDown, FileText } from "lucide-react";

import { formatSimilarity, sourceLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RetrievedSource } from "@/types/assistant";

interface SourceCardProps {
  source: RetrievedSource;
  expanded: boolean;
  onToggle: () => void;
  detailId: string;
}

/** One retrieved source: document title and page, with page and similarity expanded, exactly as the server sent them. */
export function SourceCard({ source, expanded, onToggle, detailId }: SourceCardProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={detailId}
        className="flex w-full items-start gap-3 px-3.5 py-3 text-left hover:bg-surface-2"
      >
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-[7px] border border-border bg-muted text-muted-foreground">
          <FileText className="size-[18px]" aria-hidden="true" />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-[13.5px] font-semibold">{sourceLabel(source)}</span>
          {source.pageNumber !== null ? (
            <span className="font-mono text-[11.5px] text-subtle">p. {source.pageNumber}</span>
          ) : null}
        </span>
        <ChevronDown
          className={cn("mt-1 size-4 shrink-0 text-subtle transition-transform", expanded && "rotate-180")}
          aria-hidden="true"
        />
      </button>
      {expanded ? (
        <div
          id={detailId}
          data-testid="source-card"
          className="flex flex-wrap gap-x-5 gap-y-1 border-t border-border bg-surface-2 px-3.5 py-3 text-[13px] tabular-nums"
        >
          {source.pageNumber !== null ? <span>Page {source.pageNumber}</span> : null}
          <span title="Cosine similarity between the question and this passage (higher is closer). Not a confidence score.">
            Similarity {formatSimilarity(source.similarity)}
          </span>
        </div>
      ) : null}
    </div>
  );
}
