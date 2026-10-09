import { ImageUp, Lock, ScanText } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { FileDropzone } from "@/components/documents/FileDropzone";
import { ImageIndexedOutcome, ImageIndexingFailedOutcome } from "@/components/documents/ImageOutcome";
import { SelectedFile } from "@/components/documents/SelectedFile";
import { StateBlock } from "@/components/feedback/StateBlock";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/context/useAuth";
import { MAX_IMAGE_SIZE_MB, validateImageFile } from "@/lib/imageFile";
import { describeUploadFailure, indexDocument } from "@/services/documents";
import { describeImageIndexingStatus, describeImageUploadFailure, uploadImage } from "@/services/images";
import type { StoredImage, UploadFailure } from "@/types/documents";

/** What the server has confirmed so far. "ready" is reached only from a real "completed" response. */
type Phase =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "upload_failed"; failure: UploadFailure }
  | { kind: "indexing"; image: StoredImage }
  | { kind: "index_failed"; image: StoredImage; failure: UploadFailure }
  | { kind: "ready"; image: StoredImage };

export function ImageUploadPage() {
  const { user } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => () => inFlight.current?.abort(), []);

  // A convenience only: the server checks documents:write on every upload request.
  const canUpload = user?.permissions.includes("documents:write") ?? false;
  const busy = phase.kind === "uploading" || phase.kind === "indexing";

  if (!canUpload) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="mx-auto max-w-[720px]">
          <StateBlock
            icon={Lock}
            tone="warning"
            title="Uploading isn't available for your account"
            hint="Uploading documents requires the documents:write permission, which the server grants by role."
          >
            Your account can ask the assistant about documents it has been granted access to, but it cannot add new
            images.
          </StateBlock>
        </div>
      </div>
    );
  }

  function choose(files: File[]) {
    if (busy) return;
    setPhase({ kind: "idle" });
    if (files.length === 0) return;
    if (files.length > 1) {
      setFile(null);
      setFileError("Upload one image at a time.");
      return;
    }
    const problem = validateImageFile(files[0]);
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
    setPhase({ kind: "uploading" });
    try {
      // One request validates, reads (OCR), stores and indexes the image. The embeddings endpoint is only a retry.
      const { image, indexing } = await uploadImage(file, controller.signal);
      if (indexing === "completed") {
        setPhase({ kind: "ready", image });
        setFile(null);
      } else {
        setPhase({ kind: "index_failed", image, failure: describeImageIndexingStatus(indexing) });
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setPhase({ kind: "upload_failed", failure: describeImageUploadFailure(error) });
    } finally {
      if (inFlight.current === controller) inFlight.current = null;
    }
  }

  async function retryIndexing(image: StoredImage) {
    if (busy || inFlight.current) return;
    const controller = new AbortController();
    inFlight.current = controller;
    setPhase({ kind: "indexing", image });
    try {
      // Re-embeds the stored text. The image is not uploaded or read by OCR again.
      await indexDocument(image.id, controller.signal);
      setPhase({ kind: "ready", image });
      setFile(null);
    } catch (error) {
      if (controller.signal.aborted) return;
      setPhase({ kind: "index_failed", image, failure: describeUploadFailure(error, "index") });
    } finally {
      if (inFlight.current === controller) inFlight.current = null;
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <div className="flex shrink-0 items-start gap-3.5 border-b border-border bg-card px-4 py-4 sm:px-6 sm:py-5">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-primary/20 bg-primary-soft text-primary">
          <ScanText className="size-[22px]" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="text-[17px] font-semibold">Upload Images</h2>
          <p className="mt-[3px] max-w-[74ch] text-[13.5px] text-muted-foreground">
            Add a scanned page, photo or screenshot. The server reads its text with OCR and indexes it, then the
            assistant can answer questions about it.
          </p>
        </div>
      </div>

      <div className="mx-auto flex max-w-[720px] flex-col gap-4 p-4 sm:p-6">
        <section className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-5" aria-label="Upload an image">
          <div className="space-y-3">
            {file ? (
              <SelectedFile file={file} onRemove={reset} disabled={busy} icon={ImageUp} />
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
            {phase.kind === "upload_failed" ? (
              <Alert variant="error" role="alert">
                <strong className="font-semibold">{phase.failure.title}.</strong> {phase.failure.message}
              </Alert>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void submit()} disabled={!file || busy}>
                {busy ? <Spinner /> : null}
                {phase.kind === "uploading" ? "Reading image…" : phase.kind === "indexing" ? "Indexing…" : "Upload and read"}
              </Button>
              {busy ? (
                <span className="text-[13px] text-muted-foreground" role="status" aria-live="polite">
                  {phase.kind === "uploading" ? "Uploading, reading text with OCR and indexing…" : "Indexing for search…"}
                </span>
              ) : null}
            </div>
          </div>
        </section>

        {phase.kind === "ready" ? <ImageIndexedOutcome image={phase.image} onReset={reset} /> : null}
        {phase.kind === "index_failed" ? (
          <ImageIndexingFailedOutcome
            image={phase.image}
            failure={phase.failure}
            onRetry={() => void retryIndexing(phase.image)}
            onReset={reset}
          />
        ) : null}
        {phase.kind === "indexing" ? (
          <Alert variant="info" role="status">
            <strong className="font-semibold">{phase.image.filename}</strong> is stored. Its text is not searchable
            until indexing finishes.
          </Alert>
        ) : null}

        <p className="flex items-start gap-2 text-[12.5px] leading-normal text-subtle">
          <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          Images are checked by the server (type, size and contents, up to 25 megapixels), which also decides who may
          upload and who may read the extracted text afterwards.
        </p>
      </div>
    </div>
  );
}
