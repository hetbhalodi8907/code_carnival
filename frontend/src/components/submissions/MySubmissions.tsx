import { FileText, ImageIcon, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyNote } from "@/components/dashboard/primitives";
import { DocumentChat } from "@/components/documents/DocumentChat";
import { SubmissionNote, SubmissionStatusBadge } from "@/components/submissions/SubmissionStatus";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { formatDateTime } from "@/lib/dashboardFormat";
import { formatFileSize } from "@/lib/format";
import { toFriendlyError, type FriendlyError } from "@/services/api";
import { listMySubmissions } from "@/services/submissions";
import type { Submission } from "@/types/submissions";

/** How often the list refreshes while a submission is still waiting or being indexed. */
const POLL_MS = 8000;

/**
 * The signed-in user's OWN submissions (the server returns nobody else's). Statuses come only from the server;
 * "Chat with this document" appears only for a submission the server reports as ready, i.e. approved and indexed.
 */
export function MySubmissions({ refreshKey = 0, kind }: { refreshKey?: number; kind?: "pdf" | "image" }) {
  const [items, setItems] = useState<Submission[] | null>(null);
  const [error, setError] = useState<FriendlyError | null>(null);
  const [loading, setLoading] = useState(true);
  const [chatId, setChatId] = useState<string | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  const load = useCallback((silent = false) => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    if (!silent) setLoading(true);
    listMySubmissions(controller.signal)
      .then((list) => {
        setItems(list);
        setError(null);
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(toFriendlyError(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
    return () => inFlight.current?.abort();
  }, [load, refreshKey]);

  const waiting = items?.some((item) => item.status === "pending_approval" || item.status === "indexing") ?? false;
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => load(true), POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting, load]);

  const shown = (items ?? []).filter((item) => !kind || item.sourceType === kind);

  return (
    <section className="rounded-xl border border-border bg-card shadow-xs" aria-labelledby="my-submissions-title">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3.5 sm:px-5">
        <div>
          <h3 id="my-submissions-title" className="text-base font-semibold">
            My submissions
          </h3>
          <p className="mt-0.5 text-[12.5px] text-muted-foreground">Only your own submissions are listed here.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => load()} disabled={loading} aria-label="Refresh my submissions">
          {loading ? <Spinner /> : <RefreshCw aria-hidden="true" />}
          Refresh
        </Button>
      </div>
      <div className="p-4 sm:p-5">
        {error ? (
          <Alert variant="error" role="alert">
            <strong className="font-semibold">{error.title}.</strong> {error.message}
          </Alert>
        ) : null}
        {!error && items === null ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading your submissions…
          </p>
        ) : null}
        {items !== null && shown.length === 0 && !error ? <EmptyNote>You haven&apos;t submitted anything yet.</EmptyNote> : null}
        {shown.length > 0 ? (
          <ul className="m-0 flex list-none flex-col divide-y divide-border p-0" data-testid="my-submissions">
            {shown.map((item) => {
              const Icon = item.sourceType === "image" ? ImageIcon : FileText;
              return (
                <li key={item.id} className="py-3.5 first:pt-0 last:pb-0" data-testid="submission-row">
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
                    <div className="flex min-w-0 items-start gap-2.5">
                      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                      <div className="min-w-0">
                        <p className="break-all text-[13.5px] font-semibold leading-snug">{item.filename}</p>
                        <p className="text-xs text-muted-foreground">
                          {item.sourceType === "pdf" ? "PDF" : "Image"} · {formatFileSize(item.sizeBytes)} · submitted {formatDateTime(item.createdAt)}
                        </p>
                      </div>
                    </div>
                    <SubmissionStatusBadge status={item.status} />
                  </div>
                  <div className="mt-1.5 pl-[26px]">
                    <SubmissionNote submission={item} />
                    {item.status === "ready" && item.documentId ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        className="mt-2"
                        aria-expanded={chatId === item.id}
                        onClick={() => setChatId(chatId === item.id ? null : item.id)}
                      >
                        {chatId === item.id ? "Hide chat" : "Chat with this document"}
                      </Button>
                    ) : null}
                  </div>
                  {chatId === item.id && item.documentId ? (
                    <div className="mt-3">
                      <DocumentChat key={item.documentId} documentId={item.documentId} filename={item.filename} kind={item.sourceType} />
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
