import { useCallback, useEffect, useRef, useState } from "react";

import { AssistantHeader } from "@/components/chat/AssistantHeader";
import { AssistantMessage } from "@/components/chat/AssistantMessage";
import { ChatEmptyState } from "@/components/chat/ChatEmptyState";
import { Composer } from "@/components/chat/Composer";
import type { ChatEntry } from "@/components/chat/types";
import { UserMessage } from "@/components/chat/UserMessage";
import { USE_MOCK_ASSISTANT } from "@/config/env";
import { useAuth } from "@/context/useAuth";
import { toFriendlyError } from "@/services/api";
import { askAssistant } from "@/services/assistant";

export function ChatPage() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const nextId = useRef(0);
  const inFlight = useRef<AbortController | null>(null);
  const scrollRegion = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  // Conversations live only in memory and are dropped on sign-out or reload.
  useEffect(() => () => inFlight.current?.abort(), []);

  useEffect(() => {
    const region = scrollRegion.current;
    // Follow new messages; never scroll the empty state's hero out of view.
    if (region && entries.length > 0) region.scrollTop = region.scrollHeight;
  }, [entries]);

  const fillPrompt = useCallback((question: string) => {
    setDraft(question);
    composer.current?.focus();
  }, []);

  const resetConversation = useCallback(() => {
    inFlight.current?.abort();
    setEntries([]);
    setPending(false);
    composer.current?.focus();
  }, []);

  /** Ask the server and settle the existing reply entry, so a reply is never duplicated. */
  async function answer(replyId: string, question: string) {
    if (!user) return;
    const controller = new AbortController();
    inFlight.current = controller;
    setPending(true);
    try {
      const result = await askAssistant(question, user, controller.signal);
      setEntries((current) =>
        current.map((entry) =>
          entry.id === replyId ? { id: replyId, role: "assistant", question, state: "done", result } : entry,
        ),
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setEntries((current) =>
        current.map((entry) =>
          entry.id === replyId
            ? { id: replyId, role: "assistant", question, state: "error", error: toFriendlyError(error) }
            : entry,
        ),
      );
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setPending(false);
      }
    }
  }

  async function submit() {
    const question = draft.trim();
    // One request at a time; the ref also blocks repeats before the next render.
    if (!question || pending || inFlight.current || !user) return;
    const userId = `m${nextId.current++}`;
    const replyId = `m${nextId.current++}`;
    setEntries((current) => [
      ...current,
      { id: userId, role: "user", text: question },
      { id: replyId, role: "assistant", question, state: "pending" },
    ]);
    setDraft("");
    await answer(replyId, question);
  }

  /** Re-ask a failed question in place: the same reply entry goes back to pending. */
  function retry(replyId: string) {
    if (pending || inFlight.current) return;
    const failed = entries.find((entry) => entry.id === replyId);
    if (!failed || failed.role !== "assistant" || failed.state !== "error") return;
    const { question } = failed;
    setEntries((current) =>
      current.map((entry) => (entry.id === replyId ? { id: replyId, role: "assistant", question, state: "pending" } : entry)),
    );
    void answer(replyId, question);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <AssistantHeader mock={USE_MOCK_ASSISTANT} canReset={entries.length > 0} onReset={resetConversation} />

      <div ref={scrollRegion} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {entries.length === 0 ? (
          <ChatEmptyState onSelect={fillPrompt} />
        ) : (
          <div
            className="mx-auto flex max-w-[908px] flex-col gap-[22px] px-4 pb-2 pt-[18px] sm:px-6 sm:pt-6"
            aria-live="polite"
            aria-relevant="additions text"
          >
            {entries.map((entry) =>
              entry.role === "user" ? (
                <UserMessage key={entry.id} text={entry.text} />
              ) : (
                <AssistantMessage
                  key={entry.id}
                  entry={entry}
                  onRetry={() => retry(entry.id)}
                  retryDisabled={pending}
                />
              ),
            )}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-border bg-card px-4 pb-4 pt-3 sm:px-6 sm:pt-3.5">
        <div className="mx-auto max-w-[860px]">
          <Composer value={draft} onChange={setDraft} onSubmit={submit} pending={pending} textareaRef={composer} />
        </div>
      </div>
    </div>
  );
}
