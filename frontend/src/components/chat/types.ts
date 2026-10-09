import type { FriendlyError } from "@/services/api";
import type { AssistantResult } from "@/types/assistant";

export type ChatEntry =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; state: "pending" }
  | { id: string; role: "assistant"; state: "done"; result: AssistantResult }
  | { id: string; role: "assistant"; state: "error"; error: FriendlyError };
