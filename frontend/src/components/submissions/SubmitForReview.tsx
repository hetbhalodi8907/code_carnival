import { CircleCheck, ImageUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { FileDropzone } from "@/components/documents/FileDropzone";
import { SelectedFile } from "@/components/documents/SelectedFile";
import { SubmissionStatusBadge } from "@/components/submissions/SubmissionStatus";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { formatDateTime } from "@/lib/dashboardFormat";
import { MAX_IMAGE_SIZE_MB, validateImageFile } from "@/lib/imageFile";
import { MAX_PDF_SIZE_MB, validatePdfFile } from "@/lib/pdfFile";
import { ApiError } from "@/services/api";
import { submitForReview, UnexpectedSubmissionResponseError } from "@/services/submissions";
import type { Submission } from "@/types/submissions";

export type SubmissionKind = "pdf" | "image";

/** A safe reason for a failed submission. Validation messages come from the server; everything else is fixed copy. */
function describeFailure(error: unknown): string {
  if (error instanceof UnexpectedSubmissionResponseError) return "The server returned an unexpected response. Please try again.";
  if (error instanceof ApiError) {
    if (error.status === 0) return "Check your connection and that the Nexora server is running, then try again.";
    if (error.status === 401) return "Your session has expired. Please sign in again.";
    if (error.status === 403) return "Your account isn't permitted to submit documents.";
    if ([400, 413, 422, 429].includes(error.status)) {
      return error.serverMessage ?? "The server rejected this file. Check that it is a valid PDF or image and try again.";
    }
  }
  return "The submission could not be completed. Please try again.";
}

type Phase =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "failed"; message: string }
  | { kind: "submitted"; submission: Submission };

interface SubmitForReviewProps {
  kind: SubmissionKind;
  /** Called with the server's record once the submission is stored in quarantine. */
  onSubmitted: (submission: Submission) => void;
}

/**
 * The upload form for accounts that submit files for CEO review instead of ingesting them directly. A submitted file
 * is validated by the server and kept in quarantine: it cannot be searched or chatted with until the CEO approves it
 * and indexing completes.
 */
export function SubmitForReview({ kind, onSubmitted }: SubmitForReviewProps) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const inFlight = useRef<AbortController | null>(null);
  useEffect(() => () => inFlight.current?.abort(), []);

  const busy = phase.kind === "submitting";
  const noun = kind === "pdf" ? "PDF" : "image";

  function choose(files: File[]) {
    if (busy) return;
    setPhase({ kind: "idle" });
    if (files.length === 0) return;
    if (files.length > 1) {
      setFile(null);
      setFileError(`Submit one ${noun} at a time.`);
      return;
    }
    const problem = kind === "pdf" ? validatePdfFile(files[0]) : validateImageFile(files[0]);
    setFileError(problem);
    setFile(problem ? null : files[0]);
  }

  function reset() {
    setFile(null);
    setFileError(null);
    setPhase({ kind: "idle" });
  }

  async function submit() {
    if (!file || busy || inFlight.current) return;
    const controller = new AbortController();
    inFlight.current = controller;
    setPhase({ kind: "submitting" });
    try {
      const submission = await submitForReview(file, controller.signal);
      setPhase({ kind: "submitted", submission });
      setFile(null);
      onSubmitted(submission);
    } catch (error) {
      if (controller.signal.aborted) return;
      setPhase({ kind: "failed", message: describeFailure(error) });
    } finally {
      if (inFlight.current === controller) inFlight.current = null;
    }
  }

  return (
    <section className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-5" aria-label={`Submit a ${noun} for approval`}>
      <div className="space-y-3">
        {file ? (
          <SelectedFile file={file} onRemove={reset} disabled={busy} icon={kind === "image" ? ImageUp : undefined} />
        ) : kind === "pdf" ? (
          <FileDropzone onFiles={choose} disabled={busy} />
        ) : (
          <FileDropzone
            onFiles={choose}
            disabled={busy}
            accept="image/png,image/jpeg,.png,.jpg,.jpeg"
            noun="image"
            hint={`PNG or JPEG, up to ${MAX_IMAGE_SIZE_MB} MB`}
            icon={ImageUp}
          />
        )}

        {fileError ? (
          <Alert variant="error" role="alert">
            {fileError}
          </Alert>
        ) : null}
        {phase.kind === "failed" ? (
          <Alert variant="error" role="alert">
            <strong className="font-semibold">Submission failed.</strong> {phase.message}
          </Alert>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => void submit()} disabled={!file || busy}>
            {busy ? <Spinner /> : null}
            {busy ? "Validating and uploading…" : "Submit for approval"}
          </Button>
          {busy ? (
            <span className="text-[13px] text-muted-foreground" role="status" aria-live="polite">
              Checking the file and placing it in quarantine…
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">
              {kind === "pdf" ? `PDF, up to ${MAX_PDF_SIZE_MB} MB.` : `PNG or JPEG, up to ${MAX_IMAGE_SIZE_MB} MB.`} It is reviewed by the CEO before
              anyone can search it.
            </span>
          )}
        </div>

        {phase.kind === "submitted" ? (
          <div className="rounded-lg border border-success/25 bg-success-soft px-3.5 py-3" role="status" data-testid="submission-received">
            <p className="flex flex-wrap items-center gap-2 text-[13.5px] font-semibold text-success-strong">
              <CircleCheck className="size-4" aria-hidden="true" />
              Submitted for approval
              <SubmissionStatusBadge status={phase.submission.status} />
            </p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-foreground">
              <span className="font-semibold">{phase.submission.filename}</span> was received on {formatDateTime(phase.submission.createdAt)}.
              It will not be searchable until the CEO approves it and indexing finishes. Track it under My submissions below.
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
