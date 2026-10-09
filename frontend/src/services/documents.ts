/**
 * Document upload client. Real backend calls through the shared API client (bearer token,
 * 401 handling), all requiring the documents:write permission:
 *
 * 1. POST /api/v1/documents/ingest: multipart field "file". Stores the PDF and its text chunks
 *    and embeds them in the same request. The response's embedding_status says whether the
 *    document is now searchable.
 * 2. POST /api/v1/embeddings/documents/{document_id}: only a RETRY when embedding_status was not
 *    "completed". It is never called after a successful upload.
 *
 * Nothing here is simulated: results come from the server's responses, and an unexpected
 * response is an error, never a success.
 */

import { ApiError, api } from "@/services/api";
import type { DocumentIngestionResponse, EmbeddingStorageResponse } from "@/types/api";
import type {
  IndexedDocument,
  IndexingStatus,
  UploadFailure,
  UploadIndexing,
  UploadResult,
} from "@/types/documents";

const INGEST_PATH = "/api/v1/documents/ingest";
const EMBEDDINGS_PATH = "/api/v1/embeddings/documents";

/** The server answered successfully, but not with the documented response. */
export class UnexpectedUploadResponseError extends Error {
  constructor() {
    super("The server returned an unexpected response.");
    this.name = "UnexpectedUploadResponseError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseIndexingStatus(body: DocumentIngestionResponse): UploadIndexing {
  const model = typeof body.embedding_model === "string" ? body.embedding_model.trim() : "";
  // "completed" is believed only together with the model that did the indexing.
  if (body.embedding_status === "completed" && model) return { status: "completed", embeddingModel: model };
  if (body.embedding_status === "failed" || body.embedding_status === "not_configured") {
    return { status: body.embedding_status };
  }
  return { status: "unconfirmed" };
}

function parseIngestion(payload: unknown): UploadResult {
  if (
    !isRecord(payload) ||
    typeof payload.document_id !== "string" ||
    !payload.document_id ||
    typeof payload.filename !== "string" ||
    !Number.isInteger(payload.page_count) ||
    !Number.isInteger(payload.chunk_count) ||
    payload.status !== "processed"
  ) {
    throw new UnexpectedUploadResponseError();
  }
  const body = payload as unknown as DocumentIngestionResponse;
  return {
    document: { id: body.document_id, filename: body.filename, pageCount: body.page_count, chunkCount: body.chunk_count },
    indexing: parseIndexingStatus(body),
  };
}

function parseEmbedding(payload: unknown, documentId: string): IndexedDocument {
  if (
    !isRecord(payload) ||
    payload.document_id !== documentId ||
    payload.status !== "completed" ||
    !Number.isInteger(payload.embeddings_created) ||
    (payload.embeddings_created as number) < 1 ||
    typeof payload.embedding_model !== "string"
  ) {
    throw new UnexpectedUploadResponseError();
  }
  const body = payload as unknown as EmbeddingStorageResponse;
  return { embeddingsCreated: body.embeddings_created, embeddingModel: body.embedding_model };
}

/** Store and index the PDF in one request. The server validates the file type, size and PDF structure. */
export async function uploadDocument(file: File, signal?: AbortSignal): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  return parseIngestion(await api.post<unknown>(INGEST_PATH, form, { signal }));
}

/** Retry indexing for an already stored document (never re-uploads). Safe to repeat. */
export async function indexDocument(documentId: string, signal?: AbortSignal): Promise<IndexedDocument> {
  const payload = await api.post<unknown>(`${EMBEDDINGS_PATH}/${encodeURIComponent(documentId)}`, undefined, { signal });
  return parseEmbedding(payload, documentId);
}

const NETWORK: UploadFailure = {
  title: "Can't reach Nexora",
  message: "Check your connection and that the Nexora server is running, then try again.",
  retryable: true,
};
const SESSION: UploadFailure = { title: "Session expired", message: "Please sign in again to continue.", retryable: false };
const FORBIDDEN: UploadFailure = {
  title: "Upload not permitted",
  message: "Your account doesn't have permission to upload documents. The server decides who can upload.",
  retryable: false,
};
/** Why a stored document is not searchable, using only what the upload response reported. */
export function describeIndexingStatus(status: Exclude<IndexingStatus, "completed">): UploadFailure {
  switch (status) {
    case "failed":
      return {
        title: "Indexing did not complete",
        message: "The server reported that indexing failed.",
        retryable: true,
      };
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

const UNEXPECTED: UploadFailure = {
  title: "Something went wrong",
  message: "The server returned an unexpected response. Please try again.",
  retryable: true,
};

/**
 * Calm, specific copy for a failed step. The server's own message is shown only for the
 * documented validation failures of the upload step (400, 413, 422); everything else is fixed copy.
 */
export function describeUploadFailure(error: unknown, step: "upload" | "index"): UploadFailure {
  if (error instanceof UnexpectedUploadResponseError) return UNEXPECTED;
  const status = error instanceof ApiError ? error.status : -1;
  if (status === 0) return NETWORK;
  if (status === 401) return SESSION;
  if (status === 403) return FORBIDDEN;

  if (step === "upload") {
    if (status === 400 || status === 413 || status === 422) {
      const reason = error instanceof ApiError ? error.serverMessage : null;
      return {
        title: status === 413 ? "File too large" : "This PDF can't be uploaded",
        message: reason ?? "The server rejected this file. Check that it is a valid PDF and try again.",
        retryable: false,
      };
    }
    return {
      title: "Upload failed",
      message: "The server couldn't store the document. Please try again.",
      retryable: true,
    };
  }

  switch (status) {
    case 503:
      return {
        title: "Indexing isn't available",
        message: "The embedding service isn't configured on the server, so this document can't be searched yet.",
        retryable: true,
      };
    case 502:
      return {
        title: "Indexing failed",
        message: "The embedding service returned an error. Please try again.",
        retryable: true,
      };
    case 404:
      return {
        title: "Document not found",
        message: "The server no longer has this document, so it can't be indexed. Upload it again.",
        retryable: false,
      };
    case 422:
      return {
        title: "Nothing to index",
        message: "The document has no text passages to index (for example, a scanned PDF without readable text).",
        retryable: false,
      };
    default:
      return {
        title: "Indexing failed",
        message: "The server couldn't index the document. Please try again.",
        retryable: true,
      };
  }
}
