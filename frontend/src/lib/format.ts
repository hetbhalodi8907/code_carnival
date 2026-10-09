/** Presentation helpers only. They format backend values; they never decide access. */

import type { RetrievedSource } from "@/types/assistant";

export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? "?").slice(0, 2);
  return letters.toUpperCase();
}

/** Cosine similarity as a plain two-decimal score (it is not a confidence percentage). */
export function formatSimilarity(similarity: number): string {
  return Math.min(1, Math.max(-1, similarity)).toFixed(2);
}

/** "finance:read" -> "finance · read". */
export function formatPermission(permission: string): string {
  return permission.replace(":", " · ");
}

/** A source's display name, as the server sent it. */
export function sourceLabel(source: RetrievedSource): string {
  return source.title.trim() || "Untitled document";
}

/** A file size for people: "812 B", "340 KB", "1.4 MB". */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
