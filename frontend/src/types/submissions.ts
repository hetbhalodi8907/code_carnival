/** UI models for the document approval workflow (backend/app/schemas/submissions.py). */

export type SubmissionStatus = "pending_approval" | "indexing" | "ready" | "rejected" | "failed";

export interface Submission {
  id: string;
  filename: string;
  sourceType: "pdf" | "image";
  mimeType: string;
  sizeBytes: number;
  /** PDFs only. */
  pageCount: number | null;
  /** Images only. */
  imageWidth: number | null;
  imageHeight: number | null;
  status: SubmissionStatus;
  createdAt: string;
  updatedAt: string;
  decidedAt: string | null;
  rejectionReason: string | null;
  /** A fixed, safe explanation from the server; never a traceback. */
  failureMessage: string | null;
  attempts: number;
  /** Set only once the document is indexed and searchable (status "ready"). */
  documentId: string | null;
  previewAvailable: boolean;
  /** Only in the approver's queue. */
  submitter: { name: string; email: string } | null;
}
