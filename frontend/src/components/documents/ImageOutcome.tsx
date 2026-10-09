import { CircleCheck, CloudAlert } from "lucide-react";
import { Link } from "react-router";

import { StateBlock } from "@/components/feedback/StateBlock";
import { Button } from "@/components/ui/button";
import type { StoredImage, UploadFailure } from "@/types/documents";

/** "4 lines read, 98% average OCR confidence": only the parts the server reported validly. */
function ocrSummary(image: StoredImage): string | null {
  const parts: string[] = [];
  if (image.ocrLineCount !== null) parts.push(`${image.ocrLineCount} ${image.ocrLineCount === 1 ? "line" : "lines"} read`);
  if (image.ocrConfidence !== null) parts.push(`${Math.round(image.ocrConfidence * 100)}% average OCR confidence`);
  return parts.length ? parts.join(", ") : null;
}

function stored(image: StoredImage): string {
  const passages = `${image.chunkCount} text ${image.chunkCount === 1 ? "passage" : "passages"}`;
  const ocr = ocrSummary(image);
  return ocr ? `${passages}; ${ocr}` : passages;
}

/** Shown only when the server reported embedding_status "completed" (or a retry confirmed indexing). */
export function ImageIndexedOutcome({ image, onReset }: { image: StoredImage; onReset: () => void }) {
  return (
    <StateBlock
      data-testid="image-ready"
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
      hint="Only your account has been granted access to this image. Other accounts cannot retrieve its text."
    >
      Text was read from <span className="font-semibold text-foreground">{image.filename}</span> ({stored(image)}) and
      indexed. You can now ask the assistant about it. OCR can misread text, so check important details against the
      original image.
    </StateBlock>
  );
}

/** The image is stored but indexing did not complete, so the assistant cannot find its text yet. */
export function ImageIndexingFailedOutcome({
  image,
  failure,
  onRetry,
  onReset,
}: {
  image: StoredImage;
  failure: UploadFailure;
  onRetry: () => void;
  onReset: () => void;
}) {
  return (
    <StateBlock
      role="alert"
      data-testid="image-index-failed"
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
      Text was read from <span className="font-semibold text-foreground">{image.filename}</span> ({stored(image)}), but
      indexing did not finish. {failure.message} The assistant cannot find this image's text until indexing succeeds.
      Retrying does not upload the image again.
    </StateBlock>
  );
}
