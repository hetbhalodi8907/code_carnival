import { formatFileSize } from "@/lib/format";

/**
 * Mirrors the backend's default MAX_IMAGE_SIZE_MB so people get instant feedback. This is a
 * usability check only: the server validates the extension, declared type, file signature, real
 * image contents, size and pixel count (25 million) itself, and its answer is final.
 */
export const MAX_IMAGE_SIZE_MB = 10;
const MAX_IMAGE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024;

const TYPES_BY_EXTENSION: Record<string, string[]> = {
  ".png": ["image/png"],
  ".jpg": ["image/jpeg", "image/jpg"],
  ".jpeg": ["image/jpeg", "image/jpg"],
};

/** A user-facing reason the file cannot be uploaded, or null when it looks acceptable. */
export function validateImageFile(file: File): string | null {
  const name = file.name.toLowerCase();
  const extension = Object.keys(TYPES_BY_EXTENSION).find((candidate) => name.endsWith(candidate));
  if (!extension) return "Only PNG and JPEG images are supported.";
  if (file.type !== "" && !TYPES_BY_EXTENSION[extension].includes(file.type.toLowerCase())) {
    return "This file's type doesn't match its extension. Only PNG and JPEG images are supported.";
  }
  if (file.size === 0) return "This image is empty.";
  if (file.size > MAX_IMAGE_BYTES) {
    return `This file is ${formatFileSize(file.size)}. Images must be no larger than ${MAX_IMAGE_SIZE_MB} MB.`;
  }
  return null;
}
