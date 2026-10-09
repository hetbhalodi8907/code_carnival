import type { FriendlyError } from "@/services/api";
import type { AssistantResult } from "@/types/assistant";

/** Assistant entries keep their question, so a reply stays tied to it and can be retried in place. */
export type ChatEntry =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; question: string; state: "pending" }
  | { id: string; role: "assistant"; question: string; state: "done"; result: AssistantResult }
  | { id: string; role: "assistant"; question: string; state: "error"; error: FriendlyError };
