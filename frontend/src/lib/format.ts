/** Presentation helpers only. They format backend values; they never decide access. */

import type { Citation } from "@/types/assistant";

export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? "?").slice(0, 2);
  return letters.toUpperCase();
}

/** Cosine similarity (0–1) as a whole percentage. */
export function formatSimilarity(similarity: number): string {
  const clamped = Math.min(1, Math.max(0, similarity));
  return `${Math.round(clamped * 100)}%`;
}

/** "finance:read" -> "finance · read". */
export function formatPermission(permission: string): string {
  return permission.replace(":", " · ");
}

/** A source's display name; vector search results carry no document title. */
export function citationLabel(citation: Citation): string {
  return citation.title ?? "Authorized source";
}
