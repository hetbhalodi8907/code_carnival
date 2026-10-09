/** UI-level models for document upload, adapted from the backend ingestion and embedding responses. */

/** A PDF the server validated, extracted and stored. It is not searchable until it is indexed. */
export interface StoredDocument {
  id: string;
  filename: string;
  pageCount: number;
  chunkCount: number;
}

/** The server confirmed embeddings for the document, so the assistant can retrieve from it. */
export interface IndexedDocument {
  /** Known only from the retry endpoint; the upload response reports the model but not a count. */
  embeddingsCreated: number | null;
  embeddingModel: string;
}

/**
 * What the upload response says about indexing. "unconfirmed" means the server did not report a
 * usable status (missing, null or unrecognized), which is never treated as success.
 */
export type IndexingStatus = "completed" | "failed" | "not_configured" | "unconfirmed";

export type UploadIndexing =
  | { status: "completed"; embeddingModel: string }
  | { status: Exclude<IndexingStatus, "completed"> };

export interface UploadResult {
  document: StoredDocument;
  indexing: UploadIndexing;
}

export interface UploadFailure {
  title: string;
  message: string;
  /** Whether trying the same step again can succeed. */
  retryable: boolean;
}

/** An image the server validated, read with OCR and stored. Searchable only when indexing completed. */
export interface StoredImage {
  id: string;
  filename: string;
  chunkCount: number;
  /** Null unless the server reported a valid line count. */
  ocrLineCount: number | null;
  /** Mean OCR confidence from 0 to 1; null unless the server reported a valid value. */
  ocrConfidence: number | null;
}

export interface ImageUploadResult {
  image: StoredImage;
  indexing: IndexingStatus;
}
