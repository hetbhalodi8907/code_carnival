/**
 * Image (OCR) upload client: POST /api/v1/documents/ingest-image, multipart field "file", through
 * the shared API client. The server validates the image, runs OCR, chunks and stores the text and
 * embeds it in the same request; embedding_status says whether it is searchable.
 *
 * Retrying indexing reuses indexDocument() (POST /api/v1/embeddings/documents/{id}) from
 * services/documents.ts and never uploads the image again. Nothing here is simulated, and a
 * response that does not match the documented shape is an error, never a success.
 */

import { ApiError, api } from "@/services/api";
import { UnexpectedUploadResponseError, describeUploadFailure } from "@/services/documents";
import type { ImageIngestionResponse } from "@/types/api";
import type { ImageUploadResult, IndexingStatus, UploadFailure } from "@/types/documents";

const INGEST_IMAGE_PATH = "/api/v1/documents/ingest-image";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseEmbeddingStatus(value: unknown): IndexingStatus {
  // Anything other than the three documented values is not success.
  return value === "completed" || value === "failed" || value === "not_configured" ? value : "unconfirmed";
}

function parseImageIngestion(payload: unknown): ImageUploadResult {
  if (
    !isRecord(payload) ||
    typeof payload.document_id !== "string" ||
    !payload.document_id ||
    typeof payload.filename !== "string" ||
    payload.source_type !== "image" ||
    payload.status !== "processed" ||
    !Number.isInteger(payload.chunk_count)
  ) {
    throw new UnexpectedUploadResponseError();
  }
  const body = payload as unknown as ImageIngestionResponse;
  // OCR statistics are shown only when the server reported plausible values.
  const lines = Number.isInteger(body.ocr_line_count) && body.ocr_line_count >= 1 ? body.ocr_line_count : null;
  const confidence =
    typeof body.ocr_mean_confidence === "number" && body.ocr_mean_confidence >= 0 && body.ocr_mean_confidence <= 1
      ? body.ocr_mean_confidence
      : null;
  return {
    image: {
      id: body.document_id,
      filename: body.filename,
      chunkCount: body.chunk_count,
      ocrLineCount: lines,
      ocrConfidence: confidence,
    },
    indexing: parseEmbeddingStatus(body.embedding_status),
  };
}

/** Store, OCR and index the image in one request. */
export async function uploadImage(file: File, signal?: AbortSignal): Promise<ImageUploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  return parseImageIngestion(await api.post<unknown>(INGEST_IMAGE_PATH, form, { signal }));
}

/** Why a stored image is not searchable, using only what the upload response reported. */
export function describeImageIndexingStatus(status: Exclude<IndexingStatus, "completed">): UploadFailure {
  switch (status) {
    case "failed":
      return { title: "Indexing did not complete", message: "The server reported that indexing failed.", retryable: true };
    case "not_configured":
      return {
        title: "Indexing isn't available",
        message: "The server reported that the embedding service is not configured.",
        retryable: true,
      };
    case "unconfirmed":
      return {
        title: "Indexing not confirmed",
        message: "The server did not confirm that indexing completed.",
        retryable: true,
      };
  }
}

/**
 * Copy for a failed image upload. The server's own message is shown only for its documented
 * validation and OCR failures (400, 413, 422); everything else is fixed copy. Sign-in, permission
 * and network failures share the PDF page's wording.
 */
export function describeImageUploadFailure(error: unknown): UploadFailure {
  const status = error instanceof ApiError ? error.status : -1;
  const reason = error instanceof ApiError ? error.serverMessage : null;
  switch (status) {
    case 400:
      return {
        title: "This image can't be uploaded",
        message: reason ?? "The server rejected this file. Check that it is a valid PNG or JPEG image.",
        retryable: false,
      };
    case 413:
      return {
        title: "Image too large",
        message: reason ?? "The server rejected this image because it is too large.",
        retryable: false,
      };
    case 422:
      return {
        title: "No readable text found",
        message: reason ?? "OCR could not find readable text in this image. Try a clearer or higher-resolution image.",
        retryable: false,
      };
    case 502:
      return {
        title: "Text recognition failed",
        message: "The server's OCR engine couldn't process this image. Try again or use a different image.",
        retryable: true,
      };
    case 503:
      return {
        title: "OCR isn't available",
        message: "Text recognition isn't installed on the server, so images can't be read yet.",
        retryable: false,
      };
    default:
      return describeUploadFailure(error, "upload");
  }
}
