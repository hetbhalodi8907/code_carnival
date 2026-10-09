import { FlaskConical, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AssistantMessage } from "@/components/chat/AssistantMessage";
import { ChatEmptyState } from "@/components/chat/ChatEmptyState";
import { Composer } from "@/components/chat/Composer";
import { QuickPrompts } from "@/components/chat/QuickPrompts";
import type { ChatEntry } from "@/components/chat/types";
import { UserMessage } from "@/components/chat/UserMessage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

  async function submit() {
    const question = draft.trim();
    if (!question || pending || !user) return;
    const userId = `m${nextId.current++}`;
    const replyId = `m${nextId.current++}`;
    setEntries((current) => [
      ...current,
      { id: userId, role: "user", text: question },
      { id: replyId, role: "assistant", state: "pending" },
    ]);
    setDraft("");
    setPending(true);

    const controller = new AbortController();
    inFlight.current = controller;
    try {
      const result = await askAssistant(question, user, controller.signal);
      setEntries((current) =>
        current.map((entry) => (entry.id === replyId ? { id: replyId, role: "assistant", state: "done", result } : entry)),
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setEntries((current) =>
        current.map((entry) =>
          entry.id === replyId ? { id: replyId, role: "assistant", state: "error", error: toFriendlyError(error) } : entry,
        ),
      );
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setPending(false);
      }
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border px-4 py-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-semibold tracking-tight sm:text-xl">Secure AI Assistant</h1>
            <p className="truncate text-sm text-muted-foreground">Ask about authorized company information</p>
          </div>
          {USE_MOCK_ASSISTANT ? (
            <Badge variant="warning" title="VITE_USE_MOCK_API=true: simulated responses, not the real backend">
              <FlaskConical aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">Mock responses</span>
            </Badge>
          ) : null}
          {entries.length > 0 ? (
            <Button variant="outline" size="sm" onClick={resetConversation} title="New chat">
              <RotateCcw aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">New chat</span>
            </Button>
          ) : null}
        </div>
      </div>

      <div ref={scrollRegion} className="min-h-0 flex-1 overflow-y-auto px-4 sm:px-8">
        <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col py-6">
          {entries.length === 0 ? (
            <ChatEmptyState onSelect={fillPrompt} />
          ) : (
            <div className="space-y-5" aria-live="polite" aria-relevant="additions text">
              {entries.map((entry) =>
                entry.role === "user" ? (
                  <UserMessage key={entry.id} text={entry.text} />
                ) : (
                  <AssistantMessage key={entry.id} entry={entry} />
                ),
              )}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-border bg-background/80 px-4 pb-4 pt-3 backdrop-blur sm:px-8">
        <div className="mx-auto w-full max-w-3xl space-y-3">
          <QuickPrompts onSelect={fillPrompt} disabled={pending} />
          <Composer value={draft} onChange={setDraft} onSubmit={submit} pending={pending} textareaRef={composer} />
          <p className="text-center text-xs text-muted-foreground">
            Unauthorized information never reaches the AI — access is enforced by the server for every request.
          </p>
        </div>
      </div>
    </div>
  );
}
