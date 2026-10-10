/**
 * Document approval client. Real backend calls through the shared API client (bearer token, 401 handling):
 *
 * - POST /api/v1/document-submissions            submit a PDF or image for review (documents:submit)
 * - GET  /api/v1/document-submissions/mine       the caller's own submissions
 * - GET  /api/v1/document-submissions/queue      the approver's queue (documents:approve)
 * - GET  /api/v1/document-submissions/{id}/preview   the quarantined file, for its submitter or an approver
 * - POST /api/v1/document-submissions/{id}/approve | /reject   (documents:approve)
 *
 * A response that is not the documented shape is an error, never a status. The server enforces every permission;
 * nothing here decides who may see or approve a submission.
 */

import { api } from "@/services/api";
import type { Submission, SubmissionStatus } from "@/types/submissions";

const BASE = "/api/v1/document-submissions";
const STATUSES: ReadonlySet<string> = new Set(["pending_approval", "indexing", "ready", "rejected", "failed"]);

/** The server answered successfully, but not with a valid submission. */
export class UnexpectedSubmissionResponseError extends Error {
  constructor() {
    super("The server returned an unexpected response.");
    this.name = "UnexpectedSubmissionResponseError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const text = (value: unknown): string | null => (typeof value === "string" && value ? value : null);
const integer = (value: unknown): number | null => (Number.isInteger(value) ? (value as number) : null);

function parseSubmission(value: unknown): Submission {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    typeof value.filename !== "string" ||
    (value.source_type !== "pdf" && value.source_type !== "image") ||
    typeof value.status !== "string" ||
    !STATUSES.has(value.status) ||
    typeof value.created_at !== "string" ||
    !Number.isInteger(value.size_bytes)
  ) {
    throw new UnexpectedSubmissionResponseError();
  }
  const submitter = isRecord(value.submitter) && typeof value.submitter.name === "string" && typeof value.submitter.email === "string"
    ? { name: value.submitter.name, email: value.submitter.email }
    : null;
  return {
    id: value.id,
    filename: value.filename,
    sourceType: value.source_type,
    mimeType: text(value.mime_type) ?? "",
    sizeBytes: value.size_bytes as number,
    pageCount: integer(value.page_count),
    imageWidth: integer(value.image_width),
    imageHeight: integer(value.image_height),
    status: value.status as SubmissionStatus,
    createdAt: value.created_at,
    updatedAt: text(value.updated_at) ?? value.created_at,
    decidedAt: text(value.decided_at),
    rejectionReason: text(value.rejection_reason),
    failureMessage: text(value.failure_message),
    attempts: integer(value.attempts) ?? 0,
    // A document ID is believed only together with the "ready" status.
    documentId: value.status === "ready" ? text(value.document_id) : null,
    previewAvailable: value.preview_available === true,
    submitter,
  };
}

function parseList(payload: unknown): Submission[] {
  if (!isRecord(payload) || !Array.isArray(payload.submissions)) throw new UnexpectedSubmissionResponseError();
  return payload.submissions.map(parseSubmission);
}

/** Submit a PDF or image. The file is validated and quarantined; it is NOT searchable until approved and indexed. */
export async function submitForReview(file: File, signal?: AbortSignal): Promise<Submission> {
  const form = new FormData();
  form.append("file", file, file.name);
  return parseSubmission(await api.post<unknown>(BASE, form, { signal }));
}

export async function listMySubmissions(signal?: AbortSignal): Promise<Submission[]> {
  return parseList(await api.get<unknown>(`${BASE}/mine`, { signal }));
}

export async function listApprovalQueue(signal?: AbortSignal): Promise<Submission[]> {
  return parseList(await api.get<unknown>(`${BASE}/queue`, { signal }));
}

/** The quarantined file, fetched with the bearer token (never a public URL). */
export function fetchSubmissionPreview(id: string, signal?: AbortSignal): Promise<Blob> {
  return api.getBlob(`${BASE}/${encodeURIComponent(id)}/preview`, { signal });
}

/** Approve and index. The returned submission says what happened: "ready", or "failed" with a safe message. */
export async function approveSubmission(id: string, signal?: AbortSignal): Promise<Submission> {
  return parseSubmission(await api.post<unknown>(`${BASE}/${encodeURIComponent(id)}/approve`, {}, { signal }));
}

export async function rejectSubmission(id: string, reason: string | null, signal?: AbortSignal): Promise<Submission> {
  return parseSubmission(
    await api.post<unknown>(`${BASE}/${encodeURIComponent(id)}/reject`, reason ? { reason } : {}, { signal }),
  );
}
