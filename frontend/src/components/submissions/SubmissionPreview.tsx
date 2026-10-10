import { useEffect, useState } from "react";

import { Spinner } from "@/components/ui/spinner";
import { toFriendlyError } from "@/services/api";
import { fetchSubmissionPreview } from "@/services/submissions";
import type { Submission } from "@/types/submissions";

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; url: string };

/**
 * A preview of the quarantined file. It is fetched through the authenticated preview endpoint with the bearer token
 * and shown from a temporary in-memory URL that is released when the preview closes. The file is never served from a
 * public address, and nothing is extracted or indexed for it.
 */
export function SubmissionPreview({ submission }: { submission: Submission }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    fetchSubmissionPreview(submission.id, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setState({ kind: "ready", url: objectUrl });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ kind: "error", message: toFriendlyError(error).message });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [submission.id]);

  if (state.kind === "loading") {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <Spinner /> Loading preview…
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <p className="text-sm text-destructive-strong" role="alert">
        The preview couldn&apos;t be loaded. {state.message}
      </p>
    );
  }
  return submission.sourceType === "pdf" ? (
    <iframe title={`Preview of ${submission.filename}`} src={state.url} className="h-[480px] w-full rounded-lg border border-border bg-muted" />
  ) : (
    <img
      src={state.url}
      alt={`Preview of ${submission.filename}`}
      className="max-h-[480px] max-w-full rounded-lg border border-border bg-muted object-contain"
    />
  );
}
