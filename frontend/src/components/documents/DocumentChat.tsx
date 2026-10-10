import { CircleCheck, FileText, ImageIcon, MessagesSquare, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AssistantMessage } from "@/components/chat/AssistantMessage";
import { Composer } from "@/components/chat/Composer";
import type { ChatEntry } from "@/components/chat/types";
import { UserMessage } from "@/components/chat/UserMessage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, toFriendlyError, type FriendlyError } from "@/services/api";
import { MAX_HISTORY_TURNS, askAboutDocument } from "@/services/assistant";
import type { ChatTurnPayload } from "@/types/api";

type AssistantEntry = Extract<ChatEntry, { role: "assistant" }>;

export type DocumentChatKind = "pdf" | "image";

interface DocumentChatProps {
  /** The server-assigned ID of a document this page just indexed. The server re-checks access on every question. */
  documentId: string;
  filename: string;
  kind: DocumentChatKind;
}

/** Document-specific wording for the two statuses the shared error mapping does not know. */
function documentError(error: unknown): FriendlyError {
  if (error instanceof ApiError && error.status === 404) {
    return {
      title: "Document not available",
      message: "This document can't be found or isn't available to your account.",
      retryable: false,
    };
  }
  if (error instanceof ApiError && error.status === 409) {
    return {
      title: "Not ready to chat",
      message: "This document isn't indexed yet. Retry indexing, then ask again.",
      retryable: true,
    };
  }
  return toFriendlyError(error);
}

/**
 * The earlier turns the server may use to understand a follow-up. Only completed exchanges are included, newest
 * last and capped. They are context for wording ("that", "it"), never evidence: the server re-retrieves from the
 * document for every question and never trusts them.
 */
function historyBefore(entries: ChatEntry[], upTo: string): ChatTurnPayload[] {
  const turns: ChatTurnPayload[] = [];
  for (const entry of entries) {
    if (entry.id === upTo) break;
    if (entry.role !== "assistant" || entry.state !== "done") continue;
    const { result } = entry;
    if (result.kind === "answered") {
      turns.push({ role: "user", content: entry.question }, { role: "assistant", content: result.answer });
    } else if (result.kind === "insufficient_context") {
      turns.push({ role: "user", content: entry.question }, { role: "assistant", content: result.message });
    }
  }
  return turns.slice(-MAX_HISTORY_TURNS);
}

/**
 * Chat with one indexed document. It appears only after the page has confirmed indexing, asks the document-scoped
 * endpoint (real requests only), keeps the conversation in memory for this page visit and clears it when the user
 * starts over, the document changes or the page is left.
 */
export function DocumentChat({ documentId, filename, kind }: DocumentChatProps) {
  const [scope, setScope] = useState(documentId);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const nextId = useRef(0);
  const inFlight = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  // A different document is a different conversation: nothing carries over.
  if (scope !== documentId) {
    inFlight.current?.abort();
    inFlight.current = null;
    setScope(documentId);
    setEntries([]);
    setDraft("");
    setPending(false);
  }

  useEffect(() => () => inFlight.current?.abort(), []);

  useEffect(() => {
    const region = scroller.current;
    if (region) region.scrollTop = region.scrollHeight;
  }, [entries]);

  const clear = useCallback(() => {
    inFlight.current?.abort();
    inFlight.current = null;
    setEntries([]);
    setDraft("");
    setPending(false);
    composer.current?.focus();
  }, []);

  /** Ask the server and settle the existing reply entry, so a reply is never duplicated. */
  async function answer(replyId: string, question: string, history: ChatTurnPayload[]) {
    const controller = new AbortController();
    inFlight.current = controller;
    setPending(true);
    try {
      const result = await askAboutDocument(documentId, question, history, controller.signal);
      setEntries((current) =>
        current.map((entry) => (entry.id === replyId ? { id: replyId, role: "assistant", question, state: "done", result } : entry)),
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setEntries((current) =>
        current.map((entry) =>
          entry.id === replyId ? { id: replyId, role: "assistant", question, state: "error", error: documentError(error) } : entry,
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
    // One request at a time, and never an automatic repeat: the ref blocks double sends before the next render.
    if (!question || pending || inFlight.current) return;
    const userId = `d${nextId.current++}`;
    const replyId = `d${nextId.current++}`;
    const history = historyBefore(entries, replyId);
    setEntries((current) => [
      ...current,
      { id: userId, role: "user", text: question },
      { id: replyId, role: "assistant", question, state: "pending" },
    ]);
    setDraft("");
    await answer(replyId, question, history);
  }

  /** Re-ask a failed question in place, with the history it originally had. The user's message is kept. */
  function retry(replyId: string) {
    if (pending || inFlight.current) return;
    const failed = entries.find((entry): entry is AssistantEntry => entry.id === replyId && entry.role === "assistant");
    if (!failed || failed.state !== "error") return;
    const { question } = failed;
    const history = historyBefore(entries, replyId);
    setEntries((current) =>
      current.map((entry) => (entry.id === replyId ? { id: replyId, role: "assistant", question, state: "pending" } : entry)),
    );
    void answer(replyId, question, history);
  }

  const SourceIcon = kind === "image" ? ImageIcon : FileText;
  const noun = kind === "image" ? "image" : "PDF";

  return (
    <section
      className="overflow-hidden rounded-xl border border-border bg-card shadow-xs"
      aria-labelledby="document-chat-title"
      data-testid="document-chat"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3.5 sm:px-5">
        <div className="min-w-0">
          <h3 id="document-chat-title" className="flex items-center gap-2 text-base font-semibold">
            <MessagesSquare className="size-[18px] text-primary" aria-hidden="true" />
            Chat with this document
          </h3>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted-foreground">
            <SourceIcon className="size-4 shrink-0" aria-hidden="true" />
            <span className="break-all font-medium text-foreground">{filename}</span>
            <Badge variant="success">
              <CircleCheck aria-hidden="true" />
              Indexed
            </Badge>
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={clear} disabled={entries.length === 0 && draft === ""}>
          <RotateCcw aria-hidden="true" />
          New conversation
        </Button>
      </div>

      <div
        ref={scroller}
        className="max-h-[min(62vh,560px)] min-h-[160px] overflow-y-auto overscroll-contain px-4 py-4 sm:px-5"
        role="log"
        aria-label="Conversation about this document"
        aria-live="polite"
        aria-relevant="additions text"
      >
        <div className="flex flex-col gap-5">
          <div className="rounded-xl border border-border bg-surface-2 px-4 py-3 text-[14px] leading-relaxed" data-testid="document-chat-welcome">
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-primary">
              <MessagesSquare className="size-[15px]" aria-hidden="true" />
              NEXORA Assistant
            </div>
            I&apos;m answering only from <strong className="font-semibold">{filename}</strong>. Ask anything about this {noun}, then
            follow up as you like. If the {noun} doesn&apos;t say, I&apos;ll tell you rather than guess.
          </div>
          {entries.map((entry) =>
            entry.role === "user" ? (
              <UserMessage key={entry.id} text={entry.text} />
            ) : (
              <AssistantMessage key={entry.id} entry={entry} onRetry={() => retry(entry.id)} retryDisabled={pending} />
            ),
          )}
        </div>
      </div>

      <div className="border-t border-border bg-card px-4 pb-3.5 pt-3 sm:px-5">
        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={() => void submit()}
          pending={pending}
          textareaRef={composer}
          inputId="document-question"
          label="Ask about this document"
          sendLabel="Send document question"
          placeholder={`Ask about this ${noun}…`}
          footnote="Answers use only this document."
        />
        <p className="mt-2 text-xs text-muted-foreground">
          This conversation is kept on this page only. It is cleared when you start a new one, upload another file or leave.
        </p>
      </div>
    </section>
  );
}
