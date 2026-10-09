import { formatFileSize } from "@/lib/format";

/**
 * Mirrors the backend's default MAX_PDF_SIZE_MB so people get instant feedback. This is a
 * usability check only: the server validates the type, size and PDF structure itself and
 * its answer is final (if its limit differs, its own message is shown).
 */
export const MAX_PDF_SIZE_MB = 25;
const MAX_PDF_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024;
const PDF_MIME_TYPES = new Set(["application/pdf", "application/x-pdf"]);

/** A user-facing reason the file cannot be uploaded, or null when it looks acceptable. */
export function validatePdfFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf") || (file.type !== "" && !PDF_MIME_TYPES.has(file.type.toLowerCase()))) {
    return "Only PDF files are supported.";
  }
  if (file.size === 0) return "This PDF is empty.";
  if (file.size > MAX_PDF_BYTES) {
    return `This file is ${formatFileSize(file.size)}. PDFs must be no larger than ${MAX_PDF_SIZE_MB} MB.`;
  }
  return null;
}
