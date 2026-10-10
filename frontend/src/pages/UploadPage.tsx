import { FileUp, Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { DocumentChat } from "@/components/documents/DocumentChat";
import { UploadLocked } from "@/components/documents/UploadLocked";
import { ReviewUploadPage } from "@/components/submissions/ReviewUploadPage";
import { FileDropzone } from "@/components/documents/FileDropzone";
import { SelectedFile } from "@/components/documents/SelectedFile";
import { IndexedOutcome, IndexingFailedOutcome } from "@/components/documents/UploadOutcome";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/context/useAuth";
import { validatePdfFile } from "@/lib/pdfFile";
import { describeIndexingStatus, describeUploadFailure, indexDocument, uploadDocument } from "@/services/documents";
import type { IndexedDocument, StoredDocument, UploadFailure } from "@/types/documents";

/** What the server has confirmed so far. Success is only ever reached from real responses. */
type Phase =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "upload_failed"; failure: UploadFailure }
  | { kind: "indexing"; document: StoredDocument }
  | { kind: "index_failed"; document: StoredDocument; failure: UploadFailure }
  | { kind: "ready"; document: StoredDocument; indexed: IndexedDocument };

export function UploadPage() {
  const { user } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => () => inFlight.current?.abort(), []);

  // A convenience only: the server checks documents:write on every upload request.
  const canUpload = user?.permissions.includes("documents:write") ?? false;
  const busy = phase.kind === "uploading" || phase.kind === "indexing";

  // Accounts without documents:write submit PDFs for CEO approval instead of ingesting them directly.
  const canSubmit = user?.permissions.includes("documents:submit") ?? false;
  if (!canUpload) return canSubmit ? <ReviewUploadPage kind="pdf" /> : <UploadLocked kind="PDFs" />;

  function choose(files: File[]) {
    if (busy) return;
    setPhase({ kind: "idle" });
    if (files.length === 0) return;
    if (files.length > 1) {
      setFile(null);
      setFileError("Upload one PDF at a time.");
      return;
    }
    const problem = validatePdfFile(files[0]);
    setFileError(problem);
    setFile(problem ? null : files[0]);
  }

  function reset() {
    setFile(null);
    setFileError(null);
    setPhase({ kind: "idle" });
  }

  async function index(document: StoredDocument, controller: AbortController) {
    setPhase({ kind: "indexing", document });
    try {
      const indexed = await indexDocument(document.id, controller.signal);
      setPhase({ kind: "ready", document, indexed });
      setFile(null);
    } catch (error) {
      if (controller.signal.aborted) return;
      setPhase({ kind: "index_failed", document, failure: describeUploadFailure(error, "index") });
    } finally {
      if (inFlight.current === controller) inFlight.current = null;
    }
  }

  async function submit() {
    if (!file || busy || inFlight.current) return;
    const controller = new AbortController();
    inFlight.current = controller;
    setPhase({ kind: "uploading" });
    try {
      // One request stores the PDF and indexes it. The embeddings endpoint is only a retry.
      const { document, indexing } = await uploadDocument(file, controller.signal);
      if (indexing.status === "completed") {
        setPhase({
          kind: "ready",
          document,
          indexed: { embeddingsCreated: null, embeddingModel: indexing.embeddingModel },
        });
        setFile(null);
      } else {
        setPhase({ kind: "index_failed", document, failure: describeIndexingStatus(indexing.status) });
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setPhase({ kind: "upload_failed", failure: describeUploadFailure(error, "upload") });
    } finally {
      if (inFlight.current === controller) inFlight.current = null;
    }
  }

  function retryIndexing(document: StoredDocument) {
    if (busy || inFlight.current) return;
    const controller = new AbortController();
    inFlight.current = controller;
    void index(document, controller);
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <div className="flex shrink-0 items-start gap-3.5 border-b border-border bg-card px-4 py-4 sm:px-6 sm:py-5">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-primary/20 bg-primary-soft text-primary">
          <FileUp className="size-[22px]" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="text-[17px] font-semibold">Upload Documents</h2>
          <p className="mt-[3px] max-w-[74ch] text-[13.5px] text-muted-foreground">
            Add a PDF to the knowledge base. The server stores it and indexes its text, then the assistant can answer
            questions about it.
          </p>
        </div>
      </div>

      <div className="mx-auto flex max-w-[820px] flex-col gap-4 p-4 sm:p-6">
        <section className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-5" aria-label="Upload a PDF">
          <div className="space-y-3">
            {file ? (
              <SelectedFile file={file} onRemove={reset} disabled={busy} />
            ) : (
              <FileDropzone onFiles={choose} disabled={busy} />
            )}

            {fileError ? (
              <Alert variant="error" role="alert">
                {fileError}
              </Alert>
            ) : null}
            {phase.kind === "upload_failed" ? (
              <Alert variant="error" role="alert">
                <strong className="font-semibold">{phase.failure.title}.</strong> {phase.failure.message}
              </Alert>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void submit()} disabled={!file || busy}>
                {busy ? <Spinner /> : null}
                {phase.kind === "uploading" ? "Uploading…" : phase.kind === "indexing" ? "Indexing…" : "Upload and index"}
              </Button>
              {busy ? (
                <span className="text-[13px] text-muted-foreground" role="status" aria-live="polite">
                  {phase.kind === "uploading" ? "Uploading, extracting text and indexing…" : "Indexing for search…"}
                </span>
              ) : null}
            </div>
          </div>
        </section>

        {phase.kind === "ready" ? (
          <>
            <IndexedOutcome document={phase.document} indexed={phase.indexed} onReset={reset} />
            {/* Reached only from a confirmed "completed" indexing response. The key gives each document its own conversation. */}
            <DocumentChat key={phase.document.id} documentId={phase.document.id} filename={phase.document.filename} kind="pdf" />
          </>
        ) : null}
        {phase.kind === "index_failed" ? (
          <IndexingFailedOutcome
            document={phase.document}
            failure={phase.failure}
            onRetry={() => retryIndexing(phase.document)}
            onReset={reset}
          />
        ) : null}
        {phase.kind === "indexing" ? (
          <Alert variant="info" role="status">
            <strong className="font-semibold">{phase.document.filename}</strong> is stored. It is not searchable until
            indexing finishes.
          </Alert>
        ) : null}

        <p className="flex items-start gap-2 text-[12.5px] leading-normal text-subtle">
          <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          Uploads are checked by the server, which also decides who may upload and who may read the document afterwards.
        </p>
      </div>
    </div>
  );
}
