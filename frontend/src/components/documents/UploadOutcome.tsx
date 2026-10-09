import { CircleCheck, CloudAlert } from "lucide-react";
import { Link } from "react-router";

import { StateBlock } from "@/components/feedback/StateBlock";
import { Button } from "@/components/ui/button";
import type { IndexedDocument, StoredDocument, UploadFailure } from "@/types/documents";

function counts(document: StoredDocument): string {
  const pages = `${document.pageCount} ${document.pageCount === 1 ? "page" : "pages"}`;
  const passages = `${document.chunkCount} text ${document.chunkCount === 1 ? "passage" : "passages"}`;
  return `${pages}, ${passages}`;
}

/** Shown only after the server confirmed that the document's embeddings were created. */
export function IndexedOutcome({
  document,
  indexed,
  onReset,
}: {
  document: StoredDocument;
  indexed: IndexedDocument;
  onReset: () => void;
}) {
  return (
    <StateBlock
      data-testid="upload-ready"
      icon={CircleCheck}
      tone="success"
      title="Ready to search"
      actions={
        <>
          <Button asChild size="sm">
            <Link to="/app/chat">Ask the assistant</Link>
          </Button>
          <Button variant="secondary" size="sm" onClick={onReset}>
            Upload another
          </Button>
        </>
      }
      hint="Only your account has been granted access to this document. Other accounts cannot retrieve it."
    >
      <span className="font-semibold text-foreground">{document.filename}</span> was stored ({counts(document)}) and{" "}
      {indexed.embeddingsCreated === null
        ? `indexed with ${indexed.embeddingModel}`
        : `${indexed.embeddingsCreated} ${indexed.embeddingsCreated === 1 ? "passage was" : "passages were"} indexed`}
      . You can now ask the assistant about it.
    </StateBlock>
  );
}

/** The PDF is stored but indexing did not complete, so the assistant cannot find it yet. */
export function IndexingFailedOutcome({
  document,
  failure,
  onRetry,
  onReset,
}: {
  document: StoredDocument;
  failure: UploadFailure;
  onRetry: () => void;
  onReset: () => void;
}) {
  return (
    <StateBlock
      role="alert"
      data-testid="upload-index-failed"
      icon={CloudAlert}
      tone="warning"
      title="Stored, but not searchable yet"
      actions={
        <>
          {failure.retryable ? (
            <Button size="sm" onClick={onRetry}>
              Retry indexing
            </Button>
          ) : null}
          <Button variant="secondary" size="sm" onClick={onReset}>
            Upload another
          </Button>
        </>
      }
    >
      <span className="font-semibold text-foreground">{document.filename}</span> was stored ({counts(document)}), but
      indexing did not finish. {failure.message} The assistant cannot find this document until indexing succeeds.
    </StateBlock>
  );
}
